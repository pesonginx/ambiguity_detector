from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from datetime import datetime

class ScrapingRequest(BaseModel):
    """スクレイピングリクエストのモデル"""
    filename: str
    description: Optional[str] = None

class ScrapingResponse(BaseModel):
    """スクレイピングレスポンスのモデル"""
    success: bool
    message: str
    processed_urls: int
    generated_files: int
    download_url: Optional[str] = None
    errors: Optional[List[str]] = None

class URLData(BaseModel):
    """URLデータのモデル"""
    url: HttpUrl
    title: Optional[str] = None
    content: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None

class ScrapingStatus(BaseModel):
    """スクレイピング処理の状態を表すモデル"""
    task_id: str
    status: str  # "pending", "processing", "completed", "failed"
    progress: float  # 0.0 to 1.0
    total_urls: int
    processed_urls: int
    created_at: datetime
    updated_at: datetime
    message: Optional[str] = None

class MarkdownFile(BaseModel):
    """マークダウンファイルの情報"""
    filename: str
    original_url: str
    size_bytes: int
    created_at: datetime
    download_url: str

class TaskFilesResponse(BaseModel):
    """タスクに紐づくファイル一覧のレスポンス"""
    task_id: str
    files: List[MarkdownFile]
    total_files: int
    zip_download_url: Optional[str] = None
