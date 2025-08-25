#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import math
import argparse
from dataclasses import dataclass
from typing import List, Tuple, Dict

import numpy as np
import pandas as pd
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import normalize
import hdbscan
import umap
import matplotlib.pyplot as plt

# --- Azure OpenAI (v1) ---
try:
    from openai import AzureOpenAI
except ImportError:
    raise SystemExit(
        "openai>=1.35.0 が必要です。`pip install openai>=1.35.0` を実行してください。"
    )


# ============ 設定データクラス ============
@dataclass
class Config:
    input_path: str
    question_col: str
    answer_col: str
    combine: str  # 'question' | 'answer' | 'question+answer'
    output_path: str
    deployment: str  # Azure OpenAI の埋め込みデプロイ名
    api_version: str
    batch_size: int = 128
    min_cluster_size: int = 5
    min_samples: int = None  # NoneならHDBSCANが自動調整
    random_state: int = 42
    umap_neighbors: int = 15
    umap_min_dist: float = 0.1


# ============ ユーティリティ ============
def chunked(lst: List[str], size: int) -> List[List[str]]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def combine_text(q: str, a: str, how: str) -> str:
    q = "" if pd.isna(q) else str(q).strip()
    a = "" if pd.isna(a) else str(a).strip()
    if how == "question":
        return q
    if how == "answer":
        return a
    if how == "question+answer":
        # QAを一つのドキュメントとして検索したい場合
        return f"Q: {q}\nA: {a}"
    raise ValueError("--combine は question / answer / question+answer のいずれか")


# ============ Azure OpenAI embeddings ============
def get_azure_client() -> AzureOpenAI:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION") or "2024-05-01-preview"

    if not endpoint or not api_key:
        raise EnvironmentError(
            "AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY が環境変数に設定されていません。"
        )

    return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)


class TransientAZError(Exception):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    retry=retry_if_exception_type(TransientAZError),
)
def embed_batch(client: AzureOpenAI, deployment: str, texts: List[str]) -> List[List[float]]:
    try:
        # Azureでは "model" にデプロイ名を渡す
        resp = client.embeddings.create(model=deployment, input=texts)
        return [d.embedding for d in resp.data]
    except Exception as e:
        # レート制限/一時的エラーはリトライ
        msg = str(e).lower()
        transient = any(s in msg for s in ["rate", "timeout", "temporar", "service unavailable", "429"])
        if transient:
            raise TransientAZError(e)
        raise


def build_embeddings(client: AzureOpenAI, deployment: str, texts: List[str], batch_size: int = 128) -> np.ndarray:
    # 同一テキストの重複を省いてコスト削減（キャッシュ）
    unique_texts = list(dict.fromkeys(texts))
    text_to_vec: Dict[str, List[float]] = {}

    for batch in tqdm(chunked(unique_texts, batch_size), desc="Embedding"):
        vecs = embed_batch(client, deployment, batch)
        for t, v in zip(batch, vecs):
            text_to_vec[t] = v

    # 元の順序に合わせて並べ直し
    arr = np.array([text_to_vec[t] for t in texts], dtype=np.float32)
    return arr


# ============ クラスタ分析 ============
def cluster_embeddings(
    X: np.ndarray,
    min_cluster_size: int,
    min_samples: int = None,
    metric: str = "cosine",
    random_state: int = 42,
) -> np.ndarray:
    # Cosine距離でのクラスタリングを推奨
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric=metric,
        cluster_selection_method="eom",
        prediction_data=False,
        core_dist_n_jobs=0,
    )
    labels = clusterer.fit_predict(X)
    return labels


def summarize_clusters(X: np.ndarray, labels: np.ndarray) -> pd.DataFrame:
    """クラスタごとのサイズ、代表点（メドイド）、密集度（平均類似度/距離）などを算出"""
    df_list = []
    # Cosine距離（0=同一, 2=真逆; ただし通常は[0,2]範囲。距離→小さいほど近い）
    for c in sorted(set(labels)):
        if c == -1:
            # ノイズクラスタは後でまとめて扱う
            continue
        idx = np.where(labels == c)[0]
        sub = X[idx]
        # ペア距離行列
        D = pairwise_distances(sub, metric="cosine")
        # メドイド（平均距離が最小の点）
        medoid_local = np.argmin(D.mean(axis=1))
        medoid_global_idx = idx[medoid_local]
        avg_dist = D[np.triu_indices_from(D, 1)].mean() if len(idx) > 1 else 0.0

        df_list.append(
            {
                "cluster": c,
                "size": len(idx),
                "avg_cosine_distance": float(avg_dist),
                "medoid_index": int(medoid_global_idx),
            }
        )

    summary = pd.DataFrame(df_list).sort_values(["size", "avg_cosine_distance"], ascending=[False, True])
    return summary


def assign_cluster_roles(
    texts: List[str],
    labels: np.ndarray,
    X: np.ndarray,
    summary: pd.DataFrame,
) -> pd.DataFrame:
    """各行にクラスタ番号/代表フラグ/代表との距離などを付与"""
    n = len(texts)
    out = pd.DataFrame({
        "row_id": np.arange(n),
        "text_for_embedding": texts,
        "cluster": labels,
    })

    # 代表インデックス集合
    medoids = {int(r["cluster"]): int(r["medoid_index"]) for _, r in summary.iterrows()}

    # 各行について代表/距離
    role = []
    dist_to_medoid = []
    for i in range(n):
        c = labels[i]
        if c == -1:
            role.append("noise")
            dist_to_medoid.append(np.nan)
            continue
        m = medoids[c]
        d = pairwise_distances(X[i].reshape(1, -1), X[m].reshape(1, -1), metric="cosine")[0, 0]
        if i == m:
            role.append("rep")
        else:
            role.append("member")
        dist_to_medoid.append(float(d))

    out["role_in_cluster"] = role
    out["distance_to_rep"] = dist_to_medoid

    # クラスタサイズ/密集度の付与
    size_map = summary.set_index("cluster")["size"].to_dict()
    avgd_map = summary.set_index("cluster")["avg_cosine_distance"].to_dict()
    out["cluster_size"] = out["cluster"].map(size_map).fillna(1).astype(int)
    out["cluster_avg_cosine_distance"] = out["cluster"].map(avgd_map)

    return out


def plot_umap(X: np.ndarray, labels: np.ndarray, path_png: str, n_neighbors: int, min_dist: float, random_state: int):
    reducer = umap.UMAP(n_neighbors=n_neighbors, min_dist=min_dist, random_state=random_state, metric="cosine")
    coords = reducer.fit_transform(X)

    # 描画（色指定はしない：環境規約に従いデフォルト）
    plt.figure(figsize=(8, 6))
    scatter = plt.scatter(coords[:, 0], coords[:, 1], s=10, c=labels, alpha=0.8)
    plt.title("UMAP projection of QA embeddings (colored by cluster)")
    plt.xlabel("UMAP-1")
    plt.ylabel("UMAP-2")
    # 凡例はクラスタ数が多いと見づらいので省略
    plt.tight_layout()
    plt.savefig(path_png, dpi=200)
    plt.close()
    return coords


# ============ メイン ============
def main(cfg: Config):
    # 入力
    df = pd.read_excel(cfg.input_path)
    for col in [cfg.question_col, cfg.answer_col]:
        if col not in df.columns:
            # answer_col は combine=answer/question+answer のとき必須
            if col == cfg.answer_col and cfg.combine == "question":
                continue
            raise ValueError(f"列が見つかりません: {col}")

    # 埋め込み用テキスト生成
    texts = [
        combine_text(df.loc[i, cfg.question_col], df.loc[i, cfg.answer_col] if cfg.answer_col in df.columns else "", cfg.combine)
        for i in range(len(df))
    ]

    # Azure OpenAI で埋め込み
    client = get_azure_client()
    X = build_embeddings(client, cfg.deployment, texts, batch_size=cfg.batch_size)

    # Cosine計算の安定化のため正規化（任意）
    Xn = normalize(X, norm="l2", copy=True)

    # クラスタリング
    labels = cluster_embeddings(
        Xn,
        min_cluster_size=cfg.min_cluster_size,
        min_samples=cfg.min_samples,
        metric="cosine",
        random_state=cfg.random_state,
    )

    # サマリ
    summary = summarize_clusters(Xn, labels)
    roles = assign_cluster_roles(texts, labels, Xn, summary)

    # 元データに結合
    result = pd.concat([df.reset_index(drop=True), roles.drop(columns=["row_id"])], axis=1)

    # UMAP 可視化
    umap_png = os.path.splitext(cfg.output_path)[0] + "_umap.png"
    coords = plot_umap(
        Xn, labels, umap_png, n_neighbors=cfg.umap_neighbors, min_dist=cfg.umap_min_dist, random_state=cfg.random_state
    )
    result["umap_x"] = coords[:, 0]
    result["umap_y"] = coords[:, 1]

    # 便利な「削減候補フラグ」：密集クラスタで代表に極端に近いメンバー
    # しきい値は要調整（例：代表とのcosine距離が0.05未満）
    THRESH_NEAR = 0.05
    result["dedup_candidate"] = (
        (result["role_in_cluster"] == "member")
        & (result["distance_to_rep"] < THRESH_NEAR)
        & (result["cluster_size"] >= cfg.min_cluster_size)
    )

    # 便利な「補強候補フラグ」：サイズ1～2など過疎クラスタ
    result["sparse_topic_candidate"] = (
        (result["cluster"] != -1) & (result["cluster_size"] <= 2)
    ) | (result["cluster"] == -1)

    # 出力（Excel 複数シート）
    with pd.ExcelWriter(cfg.output_path, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="rows_with_clusters", index=False)

        # クラスタごとの代表＋サマリ
        if not summary.empty:
            rep_rows = result[result["role_in_cluster"] == "rep"].copy()
            rep_rows = rep_rows[[
                cfg.question_col,
                cfg.answer_col if cfg.answer_col in result.columns else cfg.question_col,
                "text_for_embedding",
                "cluster",
                "cluster_size",
                "cluster_avg_cosine_distance",
            ]].sort_values(["cluster_size", "cluster"], ascending=[False, True])
            rep_rows.to_excel(writer, sheet_name="cluster_representatives", index=False)

            summary.to_excel(writer, sheet_name="cluster_summary", index=False)

        # 削減候補/補強候補
        result[result["dedup_candidate"]].to_excel(writer, sheet_name="dedup_candidates", index=False)
        result[result["sparse_topic_candidate"]].to_excel(writer, sheet_name="sparse_candidates", index=False)

    print(f"[OK] 分析完了: {cfg.output_path}")
    print(f"[OK] UMAP 図: {umap_png}")
    print("ヒント: 'dedup_candidates' シートが重複削減対象、'sparse_candidates' が補強対象の目安です。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QAクラスタリング分析 (Azure OpenAI Embeddings + HDBSCAN)")
    parser.add_argument("--input", required=True, help="入力Excelファイルパス（例: qa_dataset.xlsx）")
    parser.add_argument("--question-col", default="question", help="質問列名（デフォルト: question）")
    parser.add_argument("--answer-col", default="answer", help="回答列名（デフォルト: answer）")
    parser.add_argument(
        "--combine",
        choices=["question", "answer", "question+answer"],
        default="question",
        help="埋め込みに使うテキストの組み方",
    )
    parser.add_argument("--deployment", required=True, help="Azure OpenAI の埋め込みデプロイ名（model= に渡す値）")
    parser.add_argument("--output", default="qa_clustered.xlsx", help="出力Excelファイルパス")
    parser.add_argument("--min-cluster-size", type=int, default=5, help="HDBSCAN: 最小クラスタサイズ")
    parser.add_argument("--min-samples", type=int, default=None, help="HDBSCAN: min_samples（未指定なら自動）")
    parser.add_argument("--batch-size", type=int, default=128, help="埋め込みAPIのバッチサイズ")
    parser.add_argument("--umap-neighbors", type=int, default=15, help="UMAP: 近傍数")
    parser.add_argument("--umap-min-dist", type=float, default=0.1, help="UMAP: min_dist")
    args = parser.parse_args()

    cfg = Config(
        input_path=args.input,
        question_col=args.question_col,
        answer_col=args.answer_col,
        combine=args.combine,
        output_path=args.output,
        deployment=args.deployment,
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION") or "2024-05-01-preview",
        batch_size=args.batch_size,
        min_cluster_size=args.min_cluster_size,
        min_samples=args.min_samples,
        random_state=42,
        umap_neighbors=args.umap_neighbors,
        umap_min_dist=args.umap_min_dist,
    )

    main(cfg)
