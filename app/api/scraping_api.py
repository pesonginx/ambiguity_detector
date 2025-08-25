from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import os
import shutil
import uuid
from datetime import datetime
from typing import List
import logging
import zipfile
import tempfile

from app.schemas.scraping import ScrapingRequest, ScrapingResponse, ScrapingStatus, MarkdownFile, TaskFilesResponse
from app.services.scraping_service import ScrapingService

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# 一時ファイル保存用ディレクトリ
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# タスクの状態を保存する辞書（実際の運用ではRedis等を使用）
task_status = {}

@router.post("/upload-excel", response_model=ScrapingResponse)
async def upload_excel_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    description: str = None
):
    """Excelファイルをアップロードしてスクレイピング処理を開始"""
    
    # ファイル形式のチェック
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Excelファイル（.xlsx, .xls）のみアップロード可能です"
        )
    
    try:
        # 一時ファイルとして保存
        temp_file_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{file.filename}")
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # タスクIDを生成
        task_id = str(uuid.uuid4())
        
        # タスクの状態を初期化
        task_status[task_id] = ScrapingStatus(
            task_id=task_id,
            status="pending",
            progress=0.0,
            total_urls=0,
            processed_urls=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            message="処理待ち"
        )
        
        # バックグラウンドでスクレイピング処理を実行
        background_tasks.add_task(
            process_scraping_task,
            task_id,
            temp_file_path,
            description
        )
        
        return ScrapingResponse(
            success=True,
            message="ファイルのアップロードが完了し、スクレイピング処理を開始しました",
            processed_urls=0,
            generated_files=0,
            download_url=f"/api/v1/scraping/status/{task_id}"
        )
        
    except Exception as e:
        logger.error(f"ファイルアップロードエラー: {e}")
        raise HTTPException(status_code=500, detail=f"ファイルのアップロードに失敗しました: {e}")

@router.get("/status/{task_id}", response_model=ScrapingStatus)
async def get_scraping_status(task_id: str):
    """スクレイピング処理の状態を取得"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    return task_status[task_id]

@router.get("/files/{task_id}", response_model=TaskFilesResponse)
async def list_markdown_files(task_id: str):
    """タスクに紐づくマークダウンファイルの一覧を取得"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    task = task_status[task_id]
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="処理が完了していません")
    
    # スクレイピングサービスからタスクに紐づくファイル一覧を取得
    scraping_service = ScrapingService()
    try:
        task_files = scraping_service.get_task_files(task_id)
        
        # レスポンス用のファイル情報を作成
        markdown_files = []
        for file_info in task_files:
            filename = file_info["filename"]
            file_path = file_info["file_path"]
            
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                created_time = datetime.fromisoformat(file_info["created_at"])
                
                markdown_files.append(MarkdownFile(
                    filename=filename,
                    original_url=file_info["original_url"],
                    size_bytes=file_size,
                    created_at=created_time,
                    download_url=f"/api/v1/scraping/download-file/{task_id}/{filename}"
                ))
        
        return TaskFilesResponse(
            task_id=task_id,
            files=markdown_files,
            total_files=len(markdown_files),
            zip_download_url=f"/api/v1/scraping/download-all/{task_id}"
        )
    finally:
        scraping_service.close()

@router.get("/download-all/{task_id}")
async def download_all_task_files(task_id: str):
    """タスクに紐づくすべてのマークダウンファイルをZIPファイルとしてダウンロード"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    task = task_status[task_id]
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="処理が完了していません")
    
    # スクレイピングサービスからタスクに紐づくファイル一覧を取得
    scraping_service = ScrapingService()
    try:
        task_files = scraping_service.get_task_files(task_id)
        
        if not task_files:
            raise HTTPException(status_code=404, detail="タスクに紐づくファイルが見つかりません")
        
        # 一時的なZIPファイルを作成
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
            with zipfile.ZipFile(tmp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in task_files:
                    file_path = file_info["file_path"]
                    filename = file_info["filename"]
                    
                    if os.path.exists(file_path):
                        # ZIPファイルに追加
                        zipf.write(file_path, filename)
            
            # ZIPファイルのパスを取得
            zip_path = tmp_zip.name
        
        # ZIPファイルをレスポンスとして返す
        return FileResponse(
            path=zip_path,
            filename=f"task_{task_id}_files.zip",
            media_type='application/zip',
            background=lambda: os.unlink(zip_path)  # レスポンス後に一時ファイルを削除
        )
        
    except Exception as e:
        logger.error(f"ZIPファイル作成エラー: {e}")
        raise HTTPException(status_code=500, detail=f"ZIPファイルの作成に失敗しました: {e}")
    finally:
        scraping_service.close()

@router.get("/download-file/{task_id}/{filename}")
async def download_specific_task_file(task_id: str, filename: str):
    """タスクに紐づく特定のマークダウンファイルをダウンロード"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    task = task_status[task_id]
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="処理が完了していません")
    
    # スクレイピングサービスからタスクに紐づくファイル一覧を取得
    scraping_service = ScrapingService()
    try:
        task_files = scraping_service.get_task_files(task_id)
        
        # 指定されたファイルを探す
        target_file = None
        for file_info in task_files:
            if file_info["filename"] == filename:
                target_file = file_info
                break
        
        if not target_file:
            raise HTTPException(status_code=404, detail="指定されたファイルが見つかりません")
        
        file_path = target_file["file_path"]
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="ファイルが見つかりません")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='text/markdown'
        )
    finally:
        scraping_service.close()

@router.delete("/cleanup/{task_id}")
async def cleanup_task(task_id: str):
    """タスクと関連ファイルを削除"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    try:
        # スクレイピングサービスでタスクファイルをクリーンアップ
        scraping_service = ScrapingService()
        try:
            scraping_service.cleanup_task_files(task_id)
            
            # 古いファイルをクリーンアップ
            scraping_service.cleanup_old_files()
        finally:
            scraping_service.close()
        
        # タスクの状態を削除
        del task_status[task_id]
        
        return {"message": "タスクのクリーンアップが完了しました"}
        
    except Exception as e:
        logger.error(f"クリーンアップエラー: {e}")
        raise HTTPException(status_code=500, detail=f"クリーンアップに失敗しました: {e}")

def update_task_progress(task_id: str, progress: float, processed_urls: int, total_urls: int, message: str):
    """タスクの進捗状況を更新"""
    if task_id in task_status:
        task_status[task_id].progress = progress
        task_status[task_id].processed_urls = processed_urls
        task_status[task_id].total_urls = total_urls
        task_status[task_id].message = message
        task_status[task_id].updated_at = datetime.now()
        logger.info(f"タスク {task_id} 進捗更新: {progress:.1%} ({processed_urls}/{total_urls}) - {message}")

async def process_scraping_task(task_id: str, file_path: str, description: str = None):
    """バックグラウンドでスクレイピング処理を実行"""
    scraping_service = None
    try:
        # タスクの状態を更新
        task_status[task_id].status = "processing"
        task_status[task_id].message = "スクレイピング処理を開始しました"
        task_status[task_id].updated_at = datetime.now()
        
        # スクレイピングサービスの初期化
        scraping_service = ScrapingService()
        
        # 進捗更新用のコールバック関数を作成
        def progress_callback(progress: float, processed: int, total: int, message: str):
            update_task_progress(task_id, progress, processed, total, message)
        
        # Excelファイルの処理（task_idとprogress_callbackを渡す）
        processed_count, generated_count, errors = scraping_service.process_excel_file(
            file_path, 
            task_id, 
            progress_callback
        )
        
        # タスクの状態を更新
        task_status[task_id].status = "completed"
        task_status[task_id].progress = 1.0
        task_status[task_id].total_urls = processed_count
        task_status[task_id].processed_urls = processed_count
        task_status[task_id].message = f"処理完了: {generated_count}個のマークダウンファイルを生成しました"
        task_status[task_id].updated_at = datetime.now()
        
        # 一時ファイルを削除
        if os.path.exists(file_path):
            os.remove(file_path)
        
        logger.info(f"タスク {task_id} が完了しました")
        
    except Exception as e:
        logger.error(f"タスク {task_id} でエラーが発生しました: {e}")
        
        # エラー状態に更新
        task_status[task_id].status = "failed"
        task_status[task_id].message = f"エラーが発生しました: {e}"
        task_status[task_id].updated_at = datetime.now()
        
        # 一時ファイルを削除
        if os.path.exists(file_path):
            os.remove(file_path)
    
    finally:
        # WebDriverを確実に閉じる
        if scraping_service:
            try:
                scraping_service.close()
            except Exception as e:
                logger.error(f"WebDriverのクローズでエラーが発生しました: {e}")
