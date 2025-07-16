import pandas as pd
from pathlib import Path
import logging

# --- ログ設定 ---
def setup_logger(log_path: Path):
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        encoding="utf-8"
    )

# --- Excel読み込みとrag_id抽出 ---
df = pd.read_excel("your_file.xlsx")  # ← ファイル名は適宜変更
delete_files = df[df["rag_id"].notna()]["rag_id"].astype(str).tolist()
df_registration = df[df["rag_id"].isna()].copy()

# --- 削除フォルダ指定 ---
folder_path = Path(input("削除対象のフォルダパスを入力してください: "))
log_file = folder_path / "deletion_log.logger"
setup_logger(log_file)

# --- ファイル削除 + ログ記録 ---
for rag_id in delete_files:
    file_path = folder_path / f"{rag_id}.json"
    try:
        if file_path.exists():
            file_path.unlink()
            logging.info(f"削除成功: {file_path.name}")
            print(f"削除しました: {file_path}")
        else:
            logging.warning(f"ファイル存在せず: {file_path.name}")
            print(f"存在しません: {file_path}")
    except Exception as e:
        logging.error(f"削除失敗: {file_path.name} - エラー: {str(e)}")
        print(f"エラーで削除できませんでした: {file_path}")