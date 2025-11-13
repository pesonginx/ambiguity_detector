"""
Excel to Index JSON Processor
Excelファイルを読み込み、Azure OpenAI を使用してEmbeddingとキーワードを取得し、
個別JSONファイルとして出力する処理を実装
"""
import os
import json
import time
import logging
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

import pandas as pd
from dotenv import load_dotenv
from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_fixed
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import SimpleJsonOutputParser
import requests
from requests.auth import HTTPBasicAuth
from tqdm import tqdm

# .env ファイルをロード（flask_appの1つ上の階層）
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 環境変数設定
os.environ["HTTPS_PROXY"] = os.getenv("HTTPS_PROXY", "")
os.environ["NO_PROXY"] = os.getenv("NO_PROXY", "")

# パス設定
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "data" / "input_data"
OUTPUT_DIR = BASE_DIR / "data" / "output_data"
LOG_DIR = BASE_DIR / "logs"

# ディレクトリ作成
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# GitLab設定
GITLAB_API_BASE = os.getenv("API_BASE", "https://gitlab.com/api/v4")
GITLAB_PROJECT_ID = os.getenv("PROJECT_ID", "")
GITLAB_TOKEN = os.getenv("GIT_TOKEN", "")
GITLAB_BRANCH = os.getenv("BRANCH", "main")
GITLAB_REMOTE_PATH_PREFIX = "index/contents"
TAG_PATTERN = re.compile(r"^(\d{3})-(\d{8})$")
TAG_MESSAGE = os.getenv("TAG_MESSAGE", "auto tag")

# FastAPI設定
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8085")#検証環境のものに変更
DEPLOY_CONFIG_ENDPOINT = f"{FASTAPI_BASE_URL}/api/v1/deploy/config"

# Jenkins設定
JENKINS_BASE = os.getenv("JENKINS_BASE", "")
JENKINS_JOB = os.getenv("JENKINS_JOB", "")
JENKINS_USER = os.getenv("JENKINS_USER", "")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN", "")
JENKINS_JOB_TOKEN = os.getenv("JENKINS_JOB_TOKEN", "")
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() != "false"

# プロキシ設定
HTTP_PROXY = os.getenv('HTTP_PROXY')
HTTPS_PROXY = os.getenv('HTTPS_PROXY')

# バッチサイズ
BATCH_SIZE = 100

# タイムアウト設定
TIMEOUT = (10, 30)
QUEUE_WAIT_SEC = 300
BUILD_WAIT_SEC = 1800
POLL_INTERVAL = 2.0


# =====================================================
# ロガー設定
# =====================================================
def setup_logger(name: str, log_file: Path, level=logging.INFO):
    """ロガーをセットアップ"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 既存のハンドラーをクリア
    logger.handlers.clear()
    
    # ファイルハンドラー
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(level)
    
    # フォーマッター
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    return logger


# =====================================================
# ヘルパー関数
# =====================================================
def custom_encoder(obj):
    """Decimal型を処理するエンコーダー"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} is not JSON serializable")


def remove_urls_and_html(content: str) -> str:
    """文字列からURLとHTMLタグを削除"""
    # URLを削除
    content = re.sub(r'https?://\S+|www\.\S+', '', content)
    # HTMLタグを削除
    content = re.sub(r'<.*?>', '', content)
    # 不要な空白を削除
    content = content.strip()
    return content


def parse_category_id(value) -> str:
    """カテゴリIDを整数またはハイフンに変換"""
    if pd.isna(value) or value == "-":
        return "-"
    try:
        float_value = float(value)
        if float_value.is_integer():
            return str(int(float_value))
        else:
            return "-"
    except (ValueError, TypeError):
        return "-"


# =====================================================
# Step 1: ファイル検証（読み込みと検証）
# =====================================================
def read_and_validate_excel_files(input_dir: Path, callback=None) -> pd.DataFrame:
    """
    フォルダ内のすべてのExcelファイルを読み込み結合する
    
    Args:
        input_dir: 入力ディレクトリ
        callback: 進捗報告用コールバック
        
    Returns:
        pd.DataFrame: 結合されたデータフレーム
        
    Raises:
        FileNotFoundError: Excelファイルが見つからない場合
        ValueError: Excelファイルの読み込みに失敗した場合
    """
    excel_files = list(input_dir.glob("*.xlsx"))
    
    if not excel_files:
        raise FileNotFoundError(f"フォルダ内にExcelファイルが見つかりませんでした: {input_dir}")
    
    if callback:
        callback.log_info("ファイル検証", f"{len(excel_files)}個のExcelファイルを検出", 5)
    
    data_frames = []
    with tqdm(total=len(excel_files), desc="Excel読み込み", disable=callback is None) as pbar:
        for i, file in enumerate(excel_files):
            try:
                if callback:
                    callback.log_info("ファイル検証", f"読み込み中: {file.name}", 5 + int((i / len(excel_files)) * 10))
                
                df = pd.read_excel(file, sheet_name="rag")
                data_frames.append(df)
                pbar.update(1)
                
            except Exception as e:
                error_msg = f"ファイル読み込みエラー: {file.name} - {str(e)}"
                if callback:
                    callback.log_error("ファイル検証", error_msg, 5)
                raise ValueError(error_msg)
    
    # データフレームを結合
    merged_df = pd.concat(data_frames, ignore_index=True)
    
    if callback:
        callback.log_info("ファイル検証", f"全ファイル読み込み完了（{len(merged_df)}行）", 15)
    
    return merged_df


# =====================================================
# Step 2: バリデーションチェック
# =====================================================
def validate_data_content(df: pd.DataFrame, callback=None) -> Tuple[pd.DataFrame, List[str]]:
    """
    データの内容を確認し、必要な列が存在するかチェック
    
    Args:
        df: データフレーム
        callback: 進捗報告用コールバック
        
    Returns:
        Tuple[pd.DataFrame, List[str]]: (更新用データ, 削除対象rag_idリスト)
        
    Raises:
        ValueError: 必須列が存在しない場合
    """
    required_columns = [
        "thread_id", "group_id", "update_timestamp", "content", "content_embedding",
        "category_id_large", "category_id_medium", "category_id_small",
        "effective_start_date", "effective_end_date"
    ]
    
    # 必須列のチェック
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        error_msg = f"必須列が不足しています: {', '.join(missing_columns)}"
        if callback:
            callback.log_error("バリデーションチェック", error_msg, 20)
        raise ValueError(error_msg)
    
    if callback:
        callback.log_info("バリデーションチェック", "必須列の存在を確認", 20)
    
    # rag_id列が存在する行を抽出（削除対象）
    if "rag_id" in df.columns:
        delete_list = df[df["rag_id"].notna()]["rag_id"].astype(str).tolist()
        df_registration = df[df["rag_id"].isna()].copy()
    else:
        delete_list = []
        df_registration = df.copy()
    
    if callback:
        callback.log_info("バリデーションチェック", 
                         f"登録対象: {len(df_registration)}行, 削除対象: {len(delete_list)}件", 25)
    
    return df_registration, delete_list


# =====================================================
# Step 3: UUID生成
# =====================================================
def add_uuid_to_dataframe(df: pd.DataFrame, output_excel_path: Path, callback=None) -> pd.DataFrame:
    """
    データフレームにUUID列を追加し、Excelファイルとして出力
    
    Args:
        df: データフレーム
        output_excel_path: 出力Excelファイルパス
        callback: 進捗報告用コールバック
        
    Returns:
        pd.DataFrame: UUID列が追加されたデータフレーム
    """
    # UUID列を追加
    df["rag_id"] = [str(uuid.uuid4()) for _ in range(len(df))]
    
    if callback:
        callback.log_info("UUID生成", f"{len(df)}件のUUIDを生成", 30)
    
    # 日付列の変換
    df_export = df.copy()
    date_columns = ["update_timestamp", "effective_start_date", "effective_end_date"]
    
    for col in date_columns:
        if col in df_export.columns:
            df_export[col] = df_export[col].apply(
                lambda x: datetime.strptime(str(x), "%Y%m%d").strftime("%Y-%m-%d")
                if pd.notna(x) else x
            )
    
    # Excelファイルとして書き出す
    df_export.to_excel(output_excel_path, index=False, engine="openpyxl")
    
    if callback:
        callback.log_info("UUID生成", f"インデックス化データ一覧を出力: {output_excel_path.name}", 35)
    
    return df


# =====================================================
# Step 4: データクレンジング（重複チェック）
# =====================================================
def check_duplicates(df: pd.DataFrame, callback=None) -> pd.DataFrame:
    """
    重複行をチェック
    
    Args:
        df: データフレーム
        callback: 進捗報告用コールバック
        
    Returns:
        pd.DataFrame: データフレーム（変更なし）
    """
    duplicate_rows = df[df.duplicated(keep=False)]
    
    if not duplicate_rows.empty:
        warning_msg = f"重複行が{len(duplicate_rows)}件存在します"
        if callback:
            callback.log_warning("データクレンジング", warning_msg, 40)
    else:
        if callback:
            callback.log_info("データクレンジング", "重複行は存在しません", 40)
    
    return df


# =====================================================
# Step 5: 旧データ削除（Gitファイル削除 - ダミー実装）
# =====================================================
def delete_old_files_from_git(delete_list: List[str], callback=None):
    """
    Git管理下のファイルを削除する（ダミー実装）
    
    Args:
        delete_list: 削除対象のrag_idリスト
        callback: 進捗報告用コールバック
    """
    if not delete_list:
        if callback:
            callback.log_info("旧データ削除", "削除対象ファイルはありません", 45)
        return
    
    # TODO: 実際のGit削除処理を実装
    # 例: git rm コマンドの実行、または Git API の使用
    
    if callback:
        callback.log_info("旧データ削除", 
                         f"Git削除処理（ダミー）: {len(delete_list)}件の削除対象を検出", 50)
    
    # ダミー処理: ローカルファイル削除（開発用）
    local_delete_count = 0
    with tqdm(total=len(delete_list), desc="旧データ削除", disable=callback is None) as pbar:
        for rag_id in delete_list:
            file_path = OUTPUT_DIR / f"{rag_id}.json"
            if file_path.exists():
                try:
                    file_path.unlink()
                    local_delete_count += 1
                except Exception as e:
                    if callback:
                        callback.log_warning("旧データ削除", f"ファイル削除失敗: {rag_id} - {str(e)}", 50)
            pbar.update(1)
    
    if callback:
        callback.log_info("旧データ削除", f"ローカルファイル削除完了: {local_delete_count}件", 55)


# =====================================================
# Step 6: JSON生成
# =====================================================
def create_json_records(df: pd.DataFrame, callback=None) -> List[Dict]:
    """
    データフレームからJSON形式のレコードを作成
    
    Args:
        df: データフレーム
        callback: 進捗報告用コールバック
        
    Returns:
        List[Dict]: JSON形式のレコードリスト
    """
    json_list = []
    total_rows = len(df)
    
    with tqdm(total=total_rows, desc="JSON生成", disable=callback is None) as pbar:
        for i, (idx, data) in enumerate(df.iterrows()):
            # 進捗報告
            if callback and i % 100 == 0:
                progress = 55 + int((i / max(total_rows, 1)) * 5)
                callback.log_info("JSON生成", f"処理中: {i}/{total_rows}", progress)
            
            # カテゴリIDの変換
            category_id_large = parse_category_id(data.get("category_id_large"))
            category_id_medium = parse_category_id(data.get("category_id_medium"))
            category_id_small = parse_category_id(data.get("category_id_small"))
            
            # JSON レコード作成
            index_data = {
                "rag_id": str(data["rag_id"]),
                "thread_id": str(data["thread_id"]),
                "group_id": str(data["group_id"]),
                "update_timestamp": datetime.strptime(str(data["update_timestamp"]), "%Y%m%d").strftime("%Y-%m-%d"),
                "content": f"{data['content']} \n\n{data.get('content_en', '')}",
                "content_embedding": [],
                "content_keywords": [],
                "category_id_large": category_id_large,
                "category_id_medium": category_id_medium,
                "category_id_small": category_id_small,
                "effective_start_date": datetime.strptime(str(data["effective_start_date"]), "%Y%m%d").strftime("%Y-%m-%d"),
                "effective_end_date": datetime.strptime(str(data["effective_end_date"]), "%Y%m%d").strftime("%Y-%m-%d"),
                "extra_field_1": "",
                "extra_field_2": ""
            }
            
            json_list.append(index_data)
            pbar.update(1)
    
    if callback:
        callback.log_info("JSON生成", f"{len(json_list)}件のJSONレコードを作成完了", 60)
    
    return json_list


# =====================================================
# Step 7: Embedding取得
# =====================================================
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def get_embedding_with_retry(embedding_client: AzureOpenAI, text: str) -> List[float]:
    """
    テキストのEmbeddingを取得（リトライ機能付き）
    
    Args:
        embedding_client: Azure OpenAI クライアント
        text: テキスト
        
    Returns:
        List[float]: Embedding ベクトル
    """
    response = embedding_client.embeddings.create(
        input=text,
        model=os.getenv("AZURE_OPENAI_API_ENGINE_EMBEDDING")
    )
    return response.model_dump()["data"][0]["embedding"]


def add_embeddings_to_record(record: Dict, embedding_client: AzureOpenAI) -> Dict:
    """
    単一のレコードにEmbeddingを追加
    
    Args:
        record: JSONレコード
        embedding_client: Azure OpenAI クライアント
        
    Returns:
        Dict: Embeddingが追加されたレコード
    """
    # contentをクリーンアップ
    content = remove_urls_and_html(record["content"])
    
    # Embeddingを取得
    record["content_embedding"] = get_embedding_with_retry(embedding_client, content)
    
    return record


def add_embeddings_batch(json_records: List[Dict], callback=None, max_workers: int = 4, step_index: int = 7) -> List[Dict]:
    """
    複数レコードにEmbeddingを並列で追加
    
    Args:
        json_records: JSONレコードリスト
        callback: 進捗報告用コールバック
        max_workers: 並列処理のワーカー数
        step_index: 現在のステップインデックス
        
    Returns:
        List[Dict]: Embeddingが追加されたレコードリスト
    """
    # Azure OpenAI クライアント作成
    embedding_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-07-01-preview"
    )
    
    total_records = len(json_records)
    processed_records = []
    
    if callback:
        callback.log_info("Embedding取得", f"{total_records}件の処理を開始", 60)
    
    # tqdmでプログレスバーを作成
    with tqdm(total=total_records, desc="Embedding取得", disable=callback is None) as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_record = {
                executor.submit(add_embeddings_to_record, record, embedding_client): i 
                for i, record in enumerate(json_records)
            }
            
            for i, future in enumerate(as_completed(future_to_record)):
                try:
                    result = future.result()
                    processed_records.append(result)
                    pbar.update(1)
                    
                    if callback:
                        step_progress = (i + 1) / max(total_records, 1) * 100
                        elapsed = pbar.format_dict.get('elapsed', 0)
                        estimated_time = elapsed / (i + 1) * (total_records - i - 1) if i > 0 else 0
                        callback.update_step("Embedding取得", step_index, step_progress, estimated_time)
                        
                        if (i + 1) % 10 == 0 or i == total_records - 1:
                            progress = 60 + int((i / max(total_records, 1)) * 10)
                            callback.log_info("Embedding取得", f"処理中: {i+1}/{total_records}", progress)
                    
                except Exception as e:
                    record_idx = future_to_record[future]
                    if callback:
                        callback.log_error("Embedding取得", 
                                           f"レコード{record_idx}でエラー: {str(e)}", 65)
                    raise
    
    if callback:
        callback.log_info("Embedding取得", f"{len(processed_records)}件の処理完了", 70)
        callback.update_step("Embedding取得", step_index, 100, 0)
    
    return processed_records


# =====================================================
# Step 8: キーワード抽出
# =====================================================
@retry(stop=stop_after_attempt(60), wait=wait_fixed(1))
async def extract_keywords_async(content: str) -> List[str]:
    """
    Azure Chat を用いて非同期的にキーワードを抽出
    
    Args:
        content: テキスト
        
    Returns:
        List[str]: キーワードリスト
    """
    # Azure OpenAI クライアント
    chat_client = AzureChatOpenAI(
        model=os.getenv("AZURE_OPENAI_API_ENGINE_GPT"),
        api_key=os.getenv("AOAI_ITB_API_KEY"),
        api_version="2024-07-01-preview",
        azure_endpoint=os.getenv("AOAI_ITB_ENDPOINT"),
    )
    
    prompt = ChatPromptTemplate.from_template(
        """
# Role
あなたは自然言語処理のエキスパートです。あなたの仕事は与えられたContentから重要なキーワードを抽出することです。

# Instructions
- Azure AI Searchのキーワード検索用として、簡潔かつ関連性のあるキーワードをContentから抽出してください。
- キーワードには、引用元のファイル名や文書名（info.txtやdoc.pdfなど）を含めないでください。
- キーワードには「[」または「]」内のテキストを含めないでください。

## Important:
Outputs must strictly be in the form of a JSON array.

# Content
{content}

# Output format
["キーワード1", "キーワード2", "キーワード3", ...]

# Output
## Please provide the keywords in the form of a JSON array:
"""
    )
    
    llm = prompt | chat_client | SimpleJsonOutputParser()
    response = llm.invoke({"content": content})
    
    if isinstance(response, list):
        return response
    else:
        raise ValueError("Output is not in the expected list format.")


def extract_keywords_for_record(record: Dict) -> Dict:
    """
    単一のレコードからキーワードを抽出
    
    Args:
        record: JSONレコード
        
    Returns:
        Dict: キーワードが追加されたレコード
    """
    try:
        content = record.get("content", "")
        keywords = asyncio.run(extract_keywords_async(content))
        record["content_keywords"] = keywords
        return record
    except Exception as e:
        # エラー時は空のキーワードリスト
        record["content_keywords"] = []
        raise


def extract_keywords_batch(json_records: List[Dict], callback=None, max_workers: int = 4, step_index: int = 8) -> List[Dict]:
    """
    複数レコードからキーワードを並列で抽出
    
    Args:
        json_records: JSONレコードリスト
        callback: 進捗報告用コールバック
        max_workers: 並列処理のワーカー数
        step_index: 現在のステップインデックス
        
    Returns:
        List[Dict]: キーワードが追加されたレコードリスト
    """
    total_records = len(json_records)
    processed_records = []
    
    if callback:
        callback.log_info("キーワード抽出", f"{total_records}件の処理を開始", 70)
    
    with tqdm(total=total_records, desc="キーワード抽出", disable=callback is None) as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_record = {
                executor.submit(extract_keywords_for_record, record): i 
                for i, record in enumerate(json_records)
            }
            
            for i, future in enumerate(as_completed(future_to_record)):
                record_idx = future_to_record[future]
                try:
                    result = future.result()
                    processed_records.append(result)
                except Exception as e:
                    if callback:
                        callback.log_error("キーワード抽出", 
                                           f"レコード{record_idx}でエラー: {str(e)}", 80)
                    record = json_records[record_idx].copy()
                    record["content_keywords"] = []
                    processed_records.append(record)
                finally:
                    pbar.update(1)
                    
                    if callback:
                        step_progress = (i + 1) / max(total_records, 1) * 100
                        elapsed = pbar.format_dict.get('elapsed', 0)
                        estimated_time = elapsed / (i + 1) * (total_records - i - 1) if i > 0 else 0
                        callback.update_step("キーワード抽出", step_index, step_progress, estimated_time)
                        
                        if (i + 1) % 10 == 0 or i == total_records - 1:
                            progress = 70 + int((i / max(total_records, 1)) * 20)
                            callback.log_info("キーワード抽出", f"処理中: {i+1}/{total_records}", progress)
    
    if callback:
        callback.log_info("キーワード抽出", f"{len(processed_records)}件の処理完了", 90)
        callback.update_step("キーワード抽出", step_index, 100, 0)
    
    return processed_records


# =====================================================
# Step 9: ファイル出力
# =====================================================
def save_individual_json_files(json_records: List[Dict], output_dir: Path, callback=None):
    """
    個別JSONファイルとして保存
    
    Args:
        json_records: JSONレコードリスト
        output_dir: 出力ディレクトリ
        callback: 進捗報告用コールバック
    """
    total_records = len(json_records)
    
    if callback:
        callback.log_info("ファイル出力", f"{total_records}件のファイル出力を開始", 90)
    
    with tqdm(total=total_records, desc="ファイル出力", disable=callback is None) as pbar:
        for i, record in enumerate(json_records):
            rag_id = record.get("rag_id")
            if not rag_id:
                if callback:
                    callback.log_warning("ファイル出力", f"レコード{i}にrag_idがありません", 90)
                pbar.update(1)
                continue
            
            output_file = output_dir / f"{rag_id}.json"
            
            try:
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=4, default=custom_encoder)
                
                if callback and (i % 50 == 0 or i == total_records - 1):
                    progress = 90 + int((i / max(total_records, 1)) * 10)
                    callback.log_info("ファイル出力", f"保存中: {i+1}/{total_records}", progress)
                    
            except Exception as e:
                if callback:
                    callback.log_error("ファイル出力", 
                                     f"ファイル保存失敗: {rag_id} - {str(e)}", 95)
                raise
            finally:
                pbar.update(1)
    
    if callback:
        callback.log_info("ファイル出力", f"{total_records}件のファイル出力完了", 100)


# =====================================================
# メイン処理関数
# =====================================================
def process_excel_to_index(
    input_dir: Path, 
    output_dir: Path, 
    callback=None,
    index_name_short: Optional[str] = None,
    enable_git_deploy: bool = True
) -> Dict[str, any]:
    """
    Excelファイルを読み込み、インデックスJSONファイルを生成するメイン処理
    
    Args:
        input_dir: 入力ディレクトリ
        output_dir: 出力ディレクトリ
        callback: 進捗報告用コールバック
        index_name_short: インデックス名（短縮形）。Noneの場合は環境変数から取得
        enable_git_deploy: Git操作とデプロイを実行するか（デフォルト: True）
        
    Returns:
        Dict: 処理結果（excel_path, git_result等）
    """
    # index_name_shortの決定
    if index_name_short is None:
        index_name_short = os.getenv("INDEX_NAME_SHORT", "default_index")
    
    result = {
        "excel_path": None,
        "git_result": None,
        "success": False
    }
    
    # Step 1: ファイル検証（読み込みと検証）
    df = read_and_validate_excel_files(input_dir, callback)
    
    # Step 2: バリデーションチェック
    df_registration, delete_list = validate_data_content(df, callback)
    
    # 統計情報を記録
    record_count = len(df_registration)
    json_files_deleted = len(delete_list)
    if callback:
        callback.update_stats(
            record_count=record_count,
            json_files_deleted=json_files_deleted
        )
    
    # Step 3: UUID生成
    excel_output_path = BASE_DIR / "data" / "インデックス化データ一覧.xlsx"
    df_registration = add_uuid_to_dataframe(df_registration, excel_output_path, callback)
    result["excel_path"] = excel_output_path
    
    # Step 4: データクレンジング（重複チェック）
    df_registration = check_duplicates(df_registration, callback)
    
    # Step 5: 旧データ削除（ローカルのみ、Gitは後で削除）
    delete_old_files_from_git(delete_list, callback)
    
    # Step 6: JSON生成
    json_records = create_json_records(df_registration, callback)
    
    # メモリ効率のため、DataFrameを削除
    del df, df_registration
    
    # Step 7: Embedding取得（並列処理）
    json_records = add_embeddings_batch(json_records, callback, max_workers=4, step_index=6)
    
    # Step 8: キーワード抽出（並列処理）
    json_records = extract_keywords_batch(json_records, callback, max_workers=4, step_index=7)
    
    # Step 9: ファイル出力
    save_individual_json_files(json_records, output_dir, callback)
    
    # JSONファイル作成数を記録
    json_files_created = len(json_records)
    if callback:
        callback.update_stats(json_files_created=json_files_created)
    
    # Step 10: Git操作、タグ作成、Jenkins実行、デプロイ
    if enable_git_deploy:
        try:
            git_result = git_and_deploy_flow(
                json_records=json_records,
                delete_list=delete_list,
                output_dir=output_dir,
                index_name_short=index_name_short,
                callback=callback
            )
            result["git_result"] = git_result
            result["success"] = True
        except Exception as e:
            if callback:
                callback.log_error("処理失敗", f"Git/デプロイ処理でエラー: {str(e)}", 100)
            result["success"] = False
            raise
    else:
        result["success"] = True
    
    return result


# =====================================================
# Step 10: Git操作、タグ作成、デプロイ
# =====================================================
def _gitlab_request(method: str, url: str, **kwargs) -> requests.Response:
    """GitLab APIリクエストを実行"""
    headers = kwargs.pop("headers", {})
    headers["PRIVATE-TOKEN"] = GITLAB_TOKEN
    
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    
    response = requests.request(
        method.upper(),
        url,
        headers=headers,
        proxies=proxies,
        verify=VERIFY_SSL,
        timeout=TIMEOUT,
        **kwargs
    )
    response.raise_for_status()
    return response


def get_latest_commit_sha(branch: str = GITLAB_BRANCH) -> str:
    """指定ブランチの最新コミットSHAを取得"""
    url = f"{GITLAB_API_BASE}/projects/{GITLAB_PROJECT_ID}/repository/branches/{branch}"
    response = _gitlab_request("GET", url)
    return response.json()["commit"]["id"]


def commit_files_to_gitlab_batch(
    files_to_add: List[Path],
    files_to_delete: List[str],
    branch: str = GITLAB_BRANCH,
    callback=None
) -> Tuple[int, str, List[str]]:
    """
    GitLab Commits APIで複数ファイルをバッチコミット
    
    Args:
        files_to_add: 追加するファイルのパスリスト
        files_to_delete: 削除するrag_idリスト
        branch: ブランチ名
        callback: 進捗報告用コールバック
        
    Returns:
        Tuple[int, str, List[str]]: (コミット数, 最後のコミットSHA, 作成されたコミットSHAリスト)
    """
    total_files = len(files_to_add) + len(files_to_delete)
    
    if total_files == 0:
        if callback:
            callback.log_info("Git操作", "コミット対象のファイルがありません", 90)
        return 0, "", []
    
    if callback:
        callback.log_info("Git操作", f"コミット開始: 追加{len(files_to_add)}件, 削除{len(files_to_delete)}件", 90)
    
    # アクションリストを作成
    actions = []
    
    # 追加ファイル
    for file_path in files_to_add:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            actions.append({
                "action": "create",
                "file_path": f"{GITLAB_REMOTE_PATH_PREFIX}/{file_path.name}",
                "content": content
            })
        except Exception as e:
            if callback:
                callback.log_error("Git操作", f"ファイル読み込み失敗: {file_path.name} - {str(e)}", 90)
            raise
    
    # 削除ファイル
    for rag_id in files_to_delete:
        actions.append({
            "action": "delete",
            "file_path": f"{GITLAB_REMOTE_PATH_PREFIX}/{rag_id}.json"
        })
    
    # バッチ処理
    commit_count = 0
    last_commit_sha = ""
    commit_sha_list = []  # 作成されたコミットSHAのリスト（ロールバック用）
    
    with tqdm(total=len(actions), desc="Gitコミット", disable=callback is None) as pbar:
        for i in range(0, len(actions), BATCH_SIZE):
            batch_actions = actions[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            total_batches = (len(actions) + BATCH_SIZE - 1) // BATCH_SIZE
            
            commit_message = f"auto deploy: update index files (batch {batch_num}/{total_batches}, added: {len([a for a in batch_actions if a['action'] == 'create'])}, deleted: {len([a for a in batch_actions if a['action'] == 'delete'])})"
            
            url = f"{GITLAB_API_BASE}/projects/{GITLAB_PROJECT_ID}/repository/commits"
            payload = {
                "branch": branch,
                "commit_message": commit_message,
                "actions": batch_actions
            }
            
            try:
                response = _gitlab_request("POST", url, json=payload)
                commit_data = response.json()
                last_commit_sha = commit_data.get("id", "")
                commit_sha_list.append(last_commit_sha)  # コミットSHAを記録
                commit_count += 1
                
                if callback:
                    progress = 90 + int((i / max(len(actions), 1)) * 5)
                    callback.log_info("Git操作", f"バッチ{batch_num}/{total_batches}完了", progress)
            except requests.HTTPError as e:
                if callback:
                    callback.log_error("Git操作", f"コミット失敗 (batch {batch_num}): {str(e)}", 90)
                raise
            finally:
                pbar.update(len(batch_actions))
    
    if callback:
        callback.log_info("Git操作", f"すべてのコミット完了: {commit_count}個のコミットを作成", 95)
    
    return commit_count, last_commit_sha, commit_sha_list


def iter_gitlab_tags(per_page: int = 100):
    """GitLabのタグ一覧を取得"""
    page = 1
    while True:
        url = f"{GITLAB_API_BASE}/projects/{GITLAB_PROJECT_ID}/repository/tags"
        params = {"order_by": "updated", "sort": "desc", "per_page": per_page, "page": page}
        response = _gitlab_request("GET", url, params=params)
        batch = response.json()
        if not batch:
            break
        for t in batch:
            yield t.get("name", "")
        next_page = response.headers.get("X-Next-Page", "")
        if not next_page or next_page == "0":
            break
        page += 1


def get_max_seq_from_tags() -> int:
    """既存タグのNNN部分の最大値を取得"""
    max_seq = 0
    has_valid_tags = False
    
    for name in iter_gitlab_tags():
        if name == "initial-tag":
            continue
        m = TAG_PATTERN.match(name)
        if not m:
            continue
        has_valid_tags = True
        seq = int(m.group(1))
        if seq > max_seq:
            max_seq = seq
    
    return max_seq if has_valid_tags else 0


def build_next_tag(max_seq: int, tz_name: str = "Asia/Tokyo") -> str:
    """次のタグ名を生成"""
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d")
    return f"{(max_seq + 1):03d}-{today}"


def create_gitlab_tag(tag_name: str, ref: str, message: str = TAG_MESSAGE) -> None:
    """GitLabにタグを作成"""
    url = f"{GITLAB_API_BASE}/projects/{GITLAB_PROJECT_ID}/repository/tags"
    payload = {"tag_name": tag_name, "ref": ref}
    if message:
        payload["message"] = message
    
    try:
        _gitlab_request("POST", url, data=payload)
    except requests.HTTPError as e:
        # タグが既に存在する場合は無視
        if e.response.status_code == 400 and "already exists" in e.response.text:
            return
        raise


def revert_commits(commit_sha_list: List[str], branch: str = GITLAB_BRANCH, callback=None) -> int:
    """
    GitLab APIを使って複数のコミットをrevert
    
    Args:
        commit_sha_list: revert対象のコミットSHAリスト
        branch: ブランチ名
        callback: 進捗報告用コールバック
        
    Returns:
        int: revertしたコミット数
    """
    if not commit_sha_list:
        return 0
    
    reverted_count = 0
    total_commits = len(commit_sha_list)
    
    if callback:
        callback.log_warning("ロールバック", f"{total_commits}個のコミットをrevert中...", 100)
    
    with tqdm(total=total_commits, desc="コミットrevert", disable=callback is None) as pbar:
        for i, commit_sha in enumerate(reversed(commit_sha_list)):
            try:
                url = f"{GITLAB_API_BASE}/projects/{GITLAB_PROJECT_ID}/repository/commits/{commit_sha}/revert"
                payload = {
                    "branch": branch
                }
                
                _gitlab_request("POST", url, json=payload)
                reverted_count += 1
                
                if callback and ((i + 1) % 10 == 0 or i == total_commits - 1):
                    callback.log_info("ロールバック", f"revert進捗: {i + 1}/{total_commits}", 100)
                    
            except requests.HTTPError as e:
                if callback:
                    callback.log_warning("ロールバック", f"コミット {commit_sha[:8]} のrevertに失敗: {str(e)}", 100)
            finally:
                pbar.update(1)
    
    if callback:
        callback.log_info("ロールバック", f"{reverted_count}/{total_commits} 個のコミットをrevertしました", 100)
    
    return reverted_count


def save_deploy_config(
    new_tag: str,
    old_tag: Optional[str],
    branch_name: str,
    index_name_short: str,
    callback=None
) -> None:
    """
    FastAPI /api/v1/deploy/config エンドポイントを呼び出してデプロイ設定を保存
    """
    payload = {
        "new_tag": new_tag,
        "old_tag": old_tag,
        "branch_name": branch_name,
        "work_env": None,  # 環境リストで順次実行するため不要
        "index_name_short": index_name_short,
        "created_at": datetime.utcnow().isoformat(),
    }
    
    try:
        response = requests.post(
            DEPLOY_CONFIG_ENDPOINT,
            json=payload,
            timeout=TIMEOUT,
            verify=VERIFY_SSL
        )
        response.raise_for_status()
        
        if callback:
            callback.log_info("デプロイ設定保存", f"設定保存完了: tag={new_tag}", 96)
    except Exception as e:
        if callback:
            callback.log_error("デプロイ設定保存", f"設定保存失敗: {str(e)}", 96)
        raise


def trigger_jenkins_build(params: Dict[str, str]) -> str:
    """Jenkinsビルドをトリガーし、キューURLを返す"""
    url = f"{JENKINS_BASE.rstrip('/')}/job/{JENKINS_JOB}/buildWithParameters?token={JENKINS_JOB_TOKEN}"
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    response = requests.post(
        url,
        params=params,
        auth=auth,
        allow_redirects=False,
        timeout=TIMEOUT,
        verify=VERIFY_SSL
    )
    response.raise_for_status()
    
    queue_url = response.headers.get("Location")
    if not queue_url:
        raise RuntimeError("Jenkins: queue Location header がありません")
    return queue_url


def resolve_queue_to_build(queue_url: str, wait_sec: int = QUEUE_WAIT_SEC) -> str:
    """JenkinsキューからビルドURLを取得"""
    api = queue_url.rstrip("/") + "/api/json"
    deadline = time.time() + wait_sec
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    while time.time() < deadline:
        response = requests.get(api, auth=auth, timeout=TIMEOUT, verify=VERIFY_SSL)
        response.raise_for_status()
        data = response.json()
        
        if data.get("cancelled"):
            raise RuntimeError("Jenkins: queue cancelled")
        
        exe = data.get("executable")
        if exe and exe.get("url"):
            return exe["url"]
        
        time.sleep(POLL_INTERVAL)
    
    raise TimeoutError("Jenkins: queue → build 解決タイムアウト")


def wait_for_build_result(build_url: str, wait_sec: int = BUILD_WAIT_SEC) -> str:
    """Jenkinsビルドの完了を待機"""
    api = build_url.rstrip("/") + "/api/json"
    deadline = time.time() + wait_sec
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    while time.time() < deadline:
        response = requests.get(api, auth=auth, timeout=TIMEOUT, verify=VERIFY_SSL)
        response.raise_for_status()
        data = response.json()
        result = data.get("result")
        
        if result is not None:
            return result
        
        time.sleep(POLL_INTERVAL)
    
    raise TimeoutError("Jenkins: ビルド完了待ちタイムアウト")


def run_jenkins_flow(params: Dict[str, str], callback=None) -> str:
    """Jenkinsジョブを実行し、結果を返す"""
    if callback:
        callback.log_info("Jenkins実行", "Jenkinsビルドを開始", 97)
    
    try:
        queue_url = trigger_jenkins_build(params)
        
        if callback:
            callback.log_info("Jenkins実行", "キューに追加されました", 97)
        
        build_url = resolve_queue_to_build(queue_url)
        
        if callback:
            callback.log_info("Jenkins実行", "ビルドが開始されました", 98)
        
        result = wait_for_build_result(build_url)
        
        if callback:
            callback.log_info("Jenkins実行", f"ビルド完了: {result}", 99)
        
        return result
    except Exception as e:
        if callback:
            callback.log_error("Jenkins実行", f"Jenkins実行失敗: {str(e)}", 99)
        raise


def cleanup_output_files(callback=None) -> None:
    """出力ディレクトリのファイルをクリーンアップ"""
    try:
        files = list(OUTPUT_DIR.glob("*.json"))
        deleted_count = 0
        with tqdm(total=len(files), desc="ファイルクリーンアップ", disable=callback is None) as pbar:
            for file_path in files:
                file_path.unlink()
                deleted_count += 1
                pbar.update(1)
        
        if callback:
            callback.log_info("ファイルクリーンアップ", f"{deleted_count}件のファイルを削除", 100)
    except Exception as e:
        if callback:
            callback.log_warning("ファイルクリーンアップ", f"クリーンアップ失敗: {str(e)}", 100)


def git_and_deploy_flow(
    json_records: List[Dict],
    delete_list: List[str],
    output_dir: Path,
    index_name_short: str,
    callback=None
) -> Dict[str, any]:
    """
    Step 10: Git操作、タグ作成、Jenkins実行を統合したフロー
    
    Args:
        json_records: 生成されたJSONレコード
        delete_list: 削除対象のrag_idリスト
        output_dir: 出力ディレクトリ
        index_name_short: インデックス名（短縮形）
        callback: 進捗報告用コールバック
        
    Returns:
        Dict: 処理結果（new_tag, old_tag, commit_count, jenkins_result等）
    """
    result = {
        "new_tag": "",
        "old_tag": "",
        "commit_count": 0,
        "jenkins_result": "",
        "error": None,
        "reverted": False
    }
    
    commit_sha_list = []  # 作成されたコミットのSHAリスト（ロールバック用）
    
    try:
        if callback:
            callback.log_info("Step10開始", "Git操作とデプロイフローを開始", 90)
        
        # 1. GitLab Commits APIでバッチコミット
        files_to_add = [output_dir / f"{r['rag_id']}.json" for r in json_records]
        commit_count, last_commit_sha, commit_sha_list = commit_files_to_gitlab_batch(
            files_to_add, delete_list, GITLAB_BRANCH, callback
        )
        result["commit_count"] = commit_count
        
        if commit_count == 0:
            if callback:
                callback.log_info("Step10完了", "コミット対象がないため終了", 100)
            return result
        
        # 2. タグ作成
        max_seq = get_max_seq_from_tags()
        new_tag = build_next_tag(max_seq)
        
        # 最新タグを old_tag として取得
        old_tag = ""
        for name in iter_gitlab_tags():
            if name != "initial-tag" and TAG_PATTERN.match(name):
                old_tag = name
                break
        
        create_gitlab_tag(new_tag, last_commit_sha or GITLAB_BRANCH)
        result["new_tag"] = new_tag
        result["old_tag"] = old_tag
        
        if callback:
            callback.log_info("タグ作成", f"タグ作成完了: {new_tag}", 95)
        
        # 3. deploy_config.json保存
        save_deploy_config(
            new_tag=new_tag,
            old_tag=old_tag,
            branch_name=GITLAB_BRANCH,
            index_name_short=index_name_short,
            callback=callback
        )
        
        # 4. Jenkins実行
        git_user = os.getenv("GIT_USER", "")
        jenkins_params = {
            "NEW_TAG": new_tag,
            "OLD_TAG": old_tag or "",
            "GIT_USER": git_user,
            "GIT_TOKEN": GITLAB_TOKEN,
            "WORK_ENV": "",  # 環境リストで順次実行するため空
            "INDEX_NAME_SHORT": index_name_short,
        }
        
        jenkins_result = run_jenkins_flow(jenkins_params, callback)
        result["jenkins_result"] = jenkins_result
        
        if jenkins_result not in ("SUCCESS", "UNSTABLE"):
            raise RuntimeError(f"Jenkins実行が失敗しました: {jenkins_result}")
        
        # 5. ファイルクリーンアップ
        cleanup_output_files(callback)
        
        if callback:
            callback.log_info("Step10完了", "すべての処理が正常に完了しました", 100)
        
        return result
        
    except Exception as e:
        result["error"] = str(e)
        
        if callback:
            callback.log_error("Step10エラー", f"エラーが発生しました: {str(e)}", 100)
        
        # エラー時のロールバック（作成されたコミットをrevert）
        if commit_sha_list:
            try:
                if callback:
                    callback.log_warning("ロールバック", 
                                       f"{len(commit_sha_list)}個のコミットをrevertします...", 100)
                
                reverted_count = revert_commits(commit_sha_list, GITLAB_BRANCH, callback)
                result["reverted"] = True
                result["reverted_count"] = reverted_count
                
                if callback:
                    callback.log_info("ロールバック完了", 
                                    f"{reverted_count}個のコミットをrevertしました", 100)
                    
            except Exception as rollback_error:
                if callback:
                    callback.log_error("ロールバック失敗", 
                                     f"ロールバック中にエラー: {str(rollback_error)}", 100)
                # ロールバック失敗時はGitLabのWebインターフェースで手動revertが必要
                if callback:
                    callback.log_error("手動対応必要", 
                                     f"以下のコミットを手動でrevertしてください: {', '.join([sha[:8] for sha in commit_sha_list])}", 
                                     100)
        
        # ファイルクリーンアップ（エラー時も実行）
        try:
            cleanup_output_files(callback)
        except Exception:
            pass
        
        raise


