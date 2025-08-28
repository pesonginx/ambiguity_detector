import os
from typing import Optional

class Settings:
    """アプリケーション設定"""
    
    # Selenium設定
    DRIVER_PATH: str = os.getenv("DRIVER_PATH", "chromedriver.exe")  # Windowsの場合
    HTTP_PROXY: Optional[str] = os.getenv("HTTP_PROXY", None)
    NO_PROXY: Optional[str] = os.getenv("NO_PROXY", None)
    
    # スクレイピング設定
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    WAIT_TIME: int = int(os.getenv("WAIT_TIME", "10"))
    
    # 出力設定
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "app/static/markdown")
    TASK_FILES_DIR: str = os.getenv("TASK_FILES_DIR", "app/static/task_files")

settings = Settings()
