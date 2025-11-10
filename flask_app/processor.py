"""
バックグラウンド処理モジュール
9ステップのダミー処理を実行し、進捗をログに記録
"""
import time
import random
import os
from datetime import datetime
from typing import Callable
import pandas as pd
from database import (
    add_log, update_upload_status, set_lock
)

# 処理ステップの定義
PROCESSING_STEPS = [
    {"name": "ファイル検証", "description": "アップロードされたファイルの検証"},
    {"name": "データ読み込み", "description": "Excelファイルからデータを読み込み"},
    {"name": "データクレンジング", "description": "データの整形と不要データの除去"},
    {"name": "データ変換", "description": "データフォーマットの変換"},
    {"name": "バリデーション", "description": "データの妥当性チェック"},
    {"name": "中間ファイル生成", "description": "処理途中のデータを一時保存"},
    {"name": "最終処理", "description": "最終的なデータ処理"},
    {"name": "出力ファイル作成", "description": "処理結果を出力"},
    {"name": "クリーンアップ", "description": "一時ファイルの削除と後処理"}
]

class ProcessorCallback:
    """処理の進捗をコールバックで通知するためのクラス"""
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.total_files = 100  # ダミーファイル数
        self.current_progress = 0
    
    def log_info(self, step_name: str, message: str, progress: int):
        """INFOレベルのログを記録"""
        add_log(self.task_id, 'INFO', step_name, message, progress)
    
    def log_warning(self, step_name: str, message: str, progress: int):
        """WARNINGレベルのログを記録"""
        add_log(self.task_id, 'WARNING', step_name, message, progress)
    
    def log_error(self, step_name: str, message: str, progress: int):
        """ERRORレベルのログを記録"""
        add_log(self.task_id, 'ERROR', step_name, message, progress)

def process_step(callback: ProcessorCallback, step: dict, step_index: int, 
                 total_steps: int, simulate_error: bool = False) -> bool:
    """
    個別の処理ステップを実行
    
    Args:
        callback: コールバックオブジェクト
        step: 処理ステップの情報
        step_index: 現在のステップインデックス
        total_steps: 総ステップ数
        simulate_error: エラーをシミュレートするかどうか
    
    Returns:
        成功した場合True、エラーの場合False
    """
    step_name = step['name']
    step_description = step['description']
    
    # ステップ開始ログ
    start_progress = int((step_index / total_steps) * 100)
    callback.log_info(step_name, f"{step_description}を開始", start_progress)
    
    # ファイル処理のシミュレーション（各ステップで処理するファイル数を変化させる）
    files_to_process = random.randint(5, 15)
    
    for i in range(files_to_process):
        # 処理時間のシミュレーション（ランダムに0.2〜0.5秒）
        time.sleep(random.uniform(0.2, 0.5))
        
        # 進捗率の計算
        file_progress = (i + 1) / files_to_process
        step_progress = (step_index + file_progress) / total_steps
        overall_progress = int(step_progress * 100)
        
        # エラーシミュレーション（80%の確率でエラー発生）
        if simulate_error and step_index >= 3 and random.random() < 0.80:
            error_msg = f"データ処理中にエラーが発生しました: ファイル #{i+1} の処理に失敗"
            callback.log_warning(step_name, f"{step_description}: エラー発生", overall_progress)
            callback.log_error(step_name, error_msg, overall_progress)
            return False
        
        # 定期的に進捗ログを出力
        if i % 3 == 0:
            callback.log_info(
                step_name, 
                f"処理中... ({i+1}/{files_to_process} ファイル)", 
                overall_progress
            )
    
    # ステップ完了ログ
    end_progress = int(((step_index + 1) / total_steps) * 100)
    callback.log_info(step_name, f"{step_description}: 成功", end_progress)
    
    return True

def run_processing(task_id: str, file_path: str, simulate_error: bool = False):
    """
    メイン処理を実行
    
    Args:
        task_id: タスクID
        file_path: 処理対象ファイルのパス
        simulate_error: エラーをシミュレートするかどうか
    """
    callback = ProcessorCallback(task_id)
    
    try:
        # ロックを設定
        set_lock(True, task_id)
        
        # 処理開始
        update_upload_status(task_id, 'processing')
        callback.log_info('処理開始', 'ファイル処理を開始します', 0)
        
        # Excelファイルの読み込み（実際の処理）
        try:
            df = pd.read_excel(file_path)
            row_count = len(df)
            callback.log_info('ファイル検証', f'Excelファイルを読み込みました（{row_count}行）', 5)
        except Exception as e:
            callback.log_error('ファイル検証', f'Excelファイルの読み込みに失敗: {str(e)}', 5)
            raise
        
        # 各ステップを実行
        total_steps = len(PROCESSING_STEPS)
        for i, step in enumerate(PROCESSING_STEPS):
            success = process_step(callback, step, i, total_steps, simulate_error)
            
            if not success:
                # エラーが発生した場合
                # エラー終了メッセージを追加
                current_progress = int(((i + 1) / total_steps) * 100)
                try:
                    callback.log_error('処理終了', '処理が中断されました', current_progress)
                    update_upload_status(task_id, 'error', '処理中にエラーが発生しました')
                except Exception as e:
                    print(f"エラーログ記録失敗: {e}")
                
                # ファイルを削除
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    print(f"ファイル削除失敗: {e}")
                
                # ロックを解除（finally節でも解除されるが、早期に解除する）
                try:
                    set_lock(False)
                    print(f"[INFO] エラー発生によりロックを解除しました (task_id: {task_id})")
                except Exception as e:
                    print(f"ロック解除失敗（finally節で再試行します）: {e}")
                return
        
        # すべての処理が成功
        callback.log_info('処理完了', 'すべての処理が正常に終了しました', 100)
        update_upload_status(task_id, 'completed')
        
        # ファイルを削除
        if os.path.exists(file_path):
            os.remove(file_path)
        
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

