"""
データベース管理モジュール
SQLiteを使用してアップロード履歴とログを管理
"""
import sqlite3
import os
import time
from datetime import datetime
from typing import List, Dict, Optional
import threading

DB_PATH = os.path.join(os.path.dirname(__file__), 'uploads.db')
db_lock = threading.Lock()

def get_connection():
    """データベース接続を取得"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """データベースの初期化"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        # アップロード履歴テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                approver_email TEXT NOT NULL,
                worker_email TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                duration REAL,
                status TEXT NOT NULL,
                error_message TEXT,
                index_excel_path TEXT
            )
        ''')
        
        # 既存テーブルにindex_excel_path列を追加（既に存在する場合はスキップ）
        try:
            cursor.execute('ALTER TABLE uploads ADD COLUMN index_excel_path TEXT')
            print("[INFO] index_excel_path列を追加しました")
        except sqlite3.OperationalError:
            pass  # 既に列が存在する場合
        
        # ログテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                step_name TEXT NOT NULL,
                message TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                FOREIGN KEY (task_id) REFERENCES uploads (task_id)
            )
        ''')
        
        # ロック状態テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lock_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_locked INTEGER NOT NULL DEFAULT 0,
                current_task_id TEXT,
                locked_at TEXT
            )
        ''')
        
        # 初期ロック状態を挿入
        cursor.execute('''
            INSERT OR IGNORE INTO lock_status (id, is_locked) VALUES (1, 0)
        ''')
        
        conn.commit()
        conn.close()

def create_upload_record(task_id: str, filename: str, approver_email: str, 
                        worker_email: str) -> int:
    """アップロード記録を作成"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        upload_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            INSERT INTO uploads (task_id, filename, approver_email, worker_email, 
                               upload_date, status)
            VALUES (?, ?, ?, ?, ?, 'processing')
        ''', (task_id, filename, approver_email, worker_email, upload_date))
        
        upload_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return upload_id

def update_upload_status(task_id: str, status: str, error_message: Optional[str] = None):
    """アップロード記録のステータスを更新"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        if status == 'processing':
            start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                UPDATE uploads SET status = ?, start_time = ?
                WHERE task_id = ?
            ''', (status, start_time, task_id))
        elif status in ['completed', 'error']:
            end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                SELECT start_time FROM uploads WHERE task_id = ?
            ''', (task_id,))
            result = cursor.fetchone()
            
            duration = 0
            if result and result['start_time']:
                start = datetime.strptime(result['start_time'], '%Y-%m-%d %H:%M:%S')
                end = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
                duration = (end - start).total_seconds()
            
            cursor.execute('''
                UPDATE uploads SET status = ?, end_time = ?, duration = ?, error_message = ?
                WHERE task_id = ?
            ''', (status, end_time, duration, error_message, task_id))
        
        conn.commit()
        conn.close()

def update_index_excel_path(task_id: str, index_excel_path: str):
    """インデックス化データ一覧のファイルパスを更新"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE uploads SET index_excel_path = ?
            WHERE task_id = ?
        ''', (index_excel_path, task_id))
        
        conn.commit()
        conn.close()

def add_log(task_id: str, level: str, step_name: str, message: str, progress: int = 0):
    """ログを追加"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        cursor.execute('''
            INSERT INTO logs (task_id, timestamp, level, step_name, message, progress)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (task_id, timestamp, level, step_name, message, progress))
        
        conn.commit()
        conn.close()

def get_all_uploads() -> List[Dict]:
    """すべてのアップロード記録を取得"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM uploads ORDER BY upload_date DESC
        ''')
        
        uploads = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return uploads

def get_upload_by_task_id(task_id: str) -> Optional[Dict]:
    """タスクIDでアップロード記録を取得"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM uploads WHERE task_id = ?
        ''', (task_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return dict(result) if result else None

def get_logs_by_task_id(task_id: str) -> List[Dict]:
    """タスクIDでログを取得"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM logs WHERE task_id = ? ORDER BY timestamp ASC
        ''', (task_id,))
        
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return logs

def set_lock(is_locked: bool, task_id: Optional[str] = None):
    """ロック状態を設定"""
    max_retries = 3
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            with db_lock:
                conn = get_connection()
                cursor = conn.cursor()
                
                locked_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if is_locked else None
                
                cursor.execute('''
                    UPDATE lock_status SET is_locked = ?, current_task_id = ?, locked_at = ?
                    WHERE id = 1
                ''', (1 if is_locked else 0, task_id, locked_at))
                
                conn.commit()
                conn.close()
                
                # 成功したらリターン
                return
                
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"ロック設定失敗 (試行 {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                # 最後の試行でも失敗した場合
                print(f"ロック設定の全試行が失敗しました: {e}")
                raise

def get_lock_status() -> Dict:
    """ロック状態を取得"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM lock_status WHERE id = 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        return dict(result) if result else {'is_locked': 0, 'current_task_id': None}

def is_locked() -> bool:
    """ロックされているかチェック"""
    status = get_lock_status()
    return bool(status['is_locked'])

