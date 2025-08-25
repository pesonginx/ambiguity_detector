import uvicorn
import os

if __name__ == "__main__":
    # 必要なディレクトリを作成
    os.makedirs("app/static/markdown", exist_ok=True)
    os.makedirs("app/static/task_files", exist_ok=True)
    os.makedirs("temp_uploads", exist_ok=True)
    
    # アプリケーションを起動
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
