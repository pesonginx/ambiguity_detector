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
    for i, file in enumerate(excel_files):
        try:
            if callback:
                callback.log_info("ファイル検証", f"読み込み中: {file.name}", 5 + int((i / len(excel_files)) * 10))
            
            df = pd.read_excel(file, sheet_name="rag")
            data_frames.append(df)
            
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
    for rag_id in delete_list:
        file_path = OUTPUT_DIR / f"{rag_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                local_delete_count += 1
            except Exception as e:
                if callback:
                    callback.log_warning("旧データ削除", f"ファイル削除失敗: {rag_id} - {str(e)}", 50)
    
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
    
    for i, (idx, data) in enumerate(df.iterrows()):
        # 進捗報告
        if callback and i % 100 == 0:
            progress = 55 + int((i / total_rows) * 5)
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


def add_embeddings_batch(json_records: List[Dict], callback=None, max_workers: int = 4) -> List[Dict]:
    """
    複数レコードにEmbeddingを並列で追加
    
    Args:
        json_records: JSONレコードリスト
        callback: 進捗報告用コールバック
        max_workers: 並列処理のワーカー数
        
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
    
    # 並列処理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # タスクを投入
        future_to_record = {
            executor.submit(add_embeddings_to_record, record, embedding_client): i 
            for i, record in enumerate(json_records)
        }
        
        # 完了したタスクから結果を取得
        for i, future in enumerate(as_completed(future_to_record)):
            try:
                result = future.result()
                processed_records.append(result)
                
                # 進捗報告
                if callback and i % 10 == 0:
                    progress = 60 + int((i / total_records) * 10)
                    callback.log_info("Embedding取得", f"処理中: {i+1}/{total_records}", progress)
                    
            except Exception as e:
                record_idx = future_to_record[future]
                if callback:
                    callback.log_error("Embedding取得", 
                                     f"レコード{record_idx}でエラー: {str(e)}", 65)
                raise
    
    if callback:
        callback.log_info("Embedding取得", f"{len(processed_records)}件の処理完了", 70)
    
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


def extract_keywords_batch(json_records: List[Dict], callback=None, max_workers: int = 4) -> List[Dict]:
    """
    複数レコードからキーワードを並列で抽出
    
    Args:
        json_records: JSONレコードリスト
        callback: 進捗報告用コールバック
        max_workers: 並列処理のワーカー数
        
    Returns:
        List[Dict]: キーワードが追加されたレコードリスト
    """
    total_records = len(json_records)
    processed_records = []
    
    if callback:
        callback.log_info("キーワード抽出", f"{total_records}件の処理を開始", 70)
    
    # 並列処理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # タスクを投入
        future_to_record = {
            executor.submit(extract_keywords_for_record, record): i 
            for i, record in enumerate(json_records)
        }
        
        # 完了したタスクから結果を取得
        for i, future in enumerate(as_completed(future_to_record)):
            try:
                result = future.result()
                processed_records.append(result)
                
                # 進捗報告
                if callback and i % 10 == 0:
                    progress = 70 + int((i / total_records) * 20)
                    callback.log_info("キーワード抽出", f"処理中: {i+1}/{total_records}", progress)
                    
            except Exception as e:
                record_idx = future_to_record[future]
                if callback:
                    callback.log_error("キーワード抽出", 
                                     f"レコード{record_idx}でエラー: {str(e)}", 80)
                # エラーでも処理継続（空のキーワードリスト）
                record = json_records[record_idx].copy()
                record["content_keywords"] = []
                processed_records.append(record)
    
    if callback:
        callback.log_info("キーワード抽出", f"{len(processed_records)}件の処理完了", 90)
    
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
    
    for i, record in enumerate(json_records):
        rag_id = record.get("rag_id")
        if not rag_id:
            if callback:
                callback.log_warning("ファイル出力", f"レコード{i}にrag_idがありません", 90)
            continue
        
        output_file = output_dir / f"{rag_id}.json"
        
        try:
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=4, default=custom_encoder)
            
            # 進捗報告
            if callback and i % 50 == 0:
                progress = 90 + int((i / total_records) * 10)
                callback.log_info("ファイル出力", f"保存中: {i+1}/{total_records}", progress)
                
        except Exception as e:
            if callback:
                callback.log_error("ファイル出力", 
                                 f"ファイル保存失敗: {rag_id} - {str(e)}", 95)
            raise
    
    if callback:
        callback.log_info("ファイル出力", f"{total_records}件のファイル出力完了", 100)


# =====================================================
# メイン処理関数
# =====================================================
def process_excel_to_index(input_dir: Path, output_dir: Path, callback=None) -> Path:
    """
    Excelファイルを読み込み、インデックスJSONファイルを生成するメイン処理
    
    Args:
        input_dir: 入力ディレクトリ
        output_dir: 出力ディレクトリ
        callback: 進捗報告用コールバック
        
    Returns:
        Path: 生成されたインデックス化データ一覧.xlsxのパス
    """
    # Step 1: ファイル検証（読み込みと検証）
    df = read_and_validate_excel_files(input_dir, callback)
    
    # Step 2: バリデーションチェック
    df_registration, delete_list = validate_data_content(df, callback)
    
    # Step 3: UUID生成
    excel_output_path = BASE_DIR / "data" / "インデックス化データ一覧.xlsx"
    df_registration = add_uuid_to_dataframe(df_registration, excel_output_path, callback)
    
    # Step 4: データクレンジング（重複チェック）
    df_registration = check_duplicates(df_registration, callback)
    
    # Step 5: 旧データ削除
    delete_old_files_from_git(delete_list, callback)
    
    # Step 6: JSON生成
    json_records = create_json_records(df_registration, callback)
    
    # メモリ効率のため、DataFrameを削除
    del df, df_registration
    
    # Step 7: Embedding取得（並列処理）
    json_records = add_embeddings_batch(json_records, callback, max_workers=4)
    
    # Step 8: キーワード抽出（並列処理）
    json_records = extract_keywords_batch(json_records, callback, max_workers=4)
    
    # Step 9: ファイル出力
    save_individual_json_files(json_records, output_dir, callback)
    
    return excel_output_path


