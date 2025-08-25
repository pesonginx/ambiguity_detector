from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.api import scraping_api

app = FastAPI(
    title="スクレイピングAPI",
    description="ExcelファイルからURLを読み取り、スクレイピングしてマークダウンファイルを生成するAPI",
    version="1.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイルの提供
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# APIルーターの登録
app.include_router(scraping_api.router, prefix="/api/v1", tags=["scraping"])

@app.get("/")
async def root():
    return {"message": "スクレイピングAPIへようこそ！"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
