"""
バックグラウンド処理モジュール（実装版）
Excel to Index JSONプロセッサを統合
"""
import time
import os
from pathlib import Path
import shutil
from database import (
    add_log, update_upload_status, set_lock, update_index_excel_path,
    update_processing_stats, update_step_progress
)

# 古いインデックスファイルを削除する関数をインポート
# 循環インポートを避けるため、関数内でインポートする

# excel_to_index_processorをインポート
from excel_to_index_processor import (
    process_excel_to_index,
    INPUT_DIR,
    OUTPUT_DIR
)

# インデックス化データ一覧の出力先ディレクトリ
INDEX_LIST_DIR = Path(__file__).parent / 'data' / 'output_index_list'
INDEX_LIST_DIR.mkdir(parents=True, exist_ok=True)

# 処理ステップの定義
PROCESSING_STEPS = [
    {"name": "ファイル検証", "description": "Excelファイルの読み込みと検証"},
    {"name": "バリデーションチェック", "description": "データの内容を確認"},
    {"name": "UUID生成", "description": "rag_id列の追加"},
    {"name": "データクレンジング", "description": "重複チェックと削除対象特定"},
    {"name": "旧データ削除", "description": "既存JSONファイルの削除"},
    {"name": "JSON生成", "description": "登録用JSONデータの作成"},
    {"name": "Embedding取得", "description": "Azure OpenAIでEmbedding生成"},
    {"name": "キーワード抽出", "description": "GPTによるキーワード抽出"},
    {"name": "ファイル出力", "description": "個別JSONファイルの分割と保存"},
    {"name": "Git操作とデプロイ", "description": "GitLabコミット、タグ作成、Jenkins実行"}
]


class ProcessorCallback:
    """処理の進捗をコールバックで通知するためのクラス"""
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.current_progress = 0
        self.current_step_index = 0
        self.total_steps = 10
    
    def log_info(self, step_name: str, message: str, progress: int):
        """INFOレベルのログを記録"""
        add_log(self.task_id, 'INFO', step_name, message, progress)
        self.current_progress = progress
    
    def log_warning(self, step_name: str, message: str, progress: int):
        """WARNINGレベルのログを記録"""
        add_log(self.task_id, 'WARNING', step_name, message, progress)
        self.current_progress = progress
    
    def log_error(self, step_name: str, message: str, progress: int):
        """ERRORレベルのログを記録"""
        add_log(self.task_id, 'ERROR', step_name, message, progress)
        self.current_progress = progress
    
    def update_step(self, step_name: str, step_index: int, step_progress: float, 
                    estimated_remaining_time: float = 0):
        """ステップ進捗を更新（tqdm用）"""
        self.current_step_index = step_index
        update_step_progress(
            self.task_id, 
            step_name, 
            step_index, 
            step_progress, 
            estimated_remaining_time
        )
    
    def update_stats(self, record_count: int = None, json_files_created: int = None,
                    json_files_deleted: int = None):
        """統計情報を更新"""
        update_processing_stats(
            self.task_id,
            record_count=record_count,
            json_files_created=json_files_created,
            json_files_deleted=json_files_deleted
        )


def run_processing(task_id: str, file_path: str, simulate_error: bool = False):
    """
    メイン処理を実行
    
    Args:
        task_id: タスクID
        file_path: 処理対象ファイルのパス（使用しない - input_dataディレクトリから読み込む）
        simulate_error: エラーをシミュレートするかどうか（実装版では使用しない）
    """
    callback = ProcessorCallback(task_id)
    
    try:
        # ロックを設定
        set_lock(True, task_id)
        
        # 処理開始
        update_upload_status(task_id, 'processing')
        callback.log_info('処理開始', 'Excel to Index処理を開始します', 0)
        
        # Excelファイルを input_data ディレクトリに移動（既にアップロードされている場合）
        # file_path は input_data/{task_id}_{filename}.xlsx の形式
        # そのままで処理できるので移動は不要
        
        # メイン処理を実行
        try:
            # index_name_shortを環境変数または設定から取得
            index_name_short = os.getenv("INDEX_NAME_SHORT", "default_index")
            
            result = process_excel_to_index(
                input_dir=INPUT_DIR,
                output_dir=OUTPUT_DIR,
                callback=callback,
                index_name_short=index_name_short,
                enable_git_deploy=True  # Git操作とデプロイを実行
            )
            
            excel_output_path = result.get("excel_path")
            
            # インデックス化データ一覧をINDEX_LIST_DIRに移動してtask_id付きでリネーム
            if excel_output_path and Path(excel_output_path).exists():
                # 新しいファイル名: インデックス化データ一覧_{task_id}.xlsx
                index_excel_filename = f"インデックス化データ一覧_{task_id}.xlsx"
                index_excel_path = INDEX_LIST_DIR / index_excel_filename
                
                # ファイルを移動してリネーム
                shutil.move(str(excel_output_path), str(index_excel_path))
                
                # データベースに記録
                update_index_excel_path(task_id, str(index_excel_path))
                
                # Git/デプロイ結果を含めたメッセージ
                git_result = result.get("git_result", {})
                new_tag = git_result.get("new_tag", "N/A")
                commit_count = git_result.get("commit_count", 0)
                
                callback.log_info('処理完了', 
                                f'すべての処理が正常に終了しました。インデックス化データ: {index_excel_filename}, タグ: {new_tag}, コミット数: {commit_count}', 
                                100)
            else:
                callback.log_info('処理完了', 
                                'すべての処理が正常に終了しました', 
                                100)
            
            update_upload_status(task_id, 'completed')
            
            # 古いインデックスファイルを削除（最新5件のみ保持）
            try:
                from app import cleanup_old_index_files
                cleanup_old_index_files()
            except Exception as cleanup_error:
                print(f"[WARNING] 古いファイルのクリーンアップに失敗: {cleanup_error}")
            
        except FileNotFoundError as e:
            # ファイルが見つからない
            error_msg = f"ファイルエラー: {str(e)}"
            callback.log_error('ファイル検証', error_msg, callback.current_progress)
            update_upload_status(task_id, 'error', error_msg)
            raise
            
        except ValueError as e:
            # バリデーションエラー
            error_msg = f"バリデーションエラー: {str(e)}"
            callback.log_error('バリデーションチェック', error_msg, callback.current_progress)
            update_upload_status(task_id, 'error', error_msg)
            raise
            
        except Exception as e:
            # その他のエラー
            error_msg = f"処理エラー: {str(e)}"
            callback.log_error('システムエラー', error_msg, callback.current_progress)
            update_upload_status(task_id, 'error', error_msg)
            raise
        
        # アップロードされたファイルを削除
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                callback.log_info('クリーンアップ', f'アップロードファイルを削除: {Path(file_path).name}', 100)
        except Exception as e:
            print(f"[ERROR] ファイル削除失敗: {e}")
        
    except Exception as e:
        # 予期しないエラー
        error_msg = f"予期しないエラーが発生しました: {str(e)}"
        try:
            callback.log_error('システムエラー', error_msg, callback.current_progress)
            update_upload_status(task_id, 'error', error_msg)
        except Exception as log_error:
            print(f"ログ記録エラー: {log_error}")
        
        # ファイルを削除
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as file_error:
            print(f"ファイル削除エラー: {file_error}")
    
    finally:
        # ロックを確実に解除（エラーが発生しても必ず実行）
        try:
            set_lock(False)
            print(f"[INFO] ロックを解除しました (task_id: {task_id})")
        except Exception as lock_error:
            print(f"[ERROR] ロック解除に失敗しました: {lock_error}")
            # 最後の手段：直接データベースを更新
            try:
                import sqlite3
                DB_PATH = os.path.join(os.path.dirname(__file__), 'uploads.db')
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('UPDATE lock_status SET is_locked = 0, current_task_id = NULL WHERE id = 1')
                conn.commit()
                conn.close()
                print(f"[INFO] 直接データベース操作でロックを解除しました")
            except Exception as db_error:
                print(f"[CRITICAL] ロック解除が完全に失敗しました: {db_error}")

