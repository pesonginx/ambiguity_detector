#!/usr/bin/env python
"""
ロック状態を手動でリセットするユーティリティスクリプト

使い方:
    python reset_lock.py
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'uploads.db')

def reset_lock():
    """ロック状態を強制的にリセット"""
    try:
        if not os.path.exists(DB_PATH):
            print(f"エラー: データベースファイルが見つかりません: {DB_PATH}")
            return False
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 現在のロック状態を確認
        cursor.execute('SELECT * FROM lock_status WHERE id = 1')
        result = cursor.fetchone()
        
        if result:
            is_locked = result[1]
            current_task_id = result[2]
            locked_at = result[3]
            
            print("=" * 60)
            print("現在のロック状態:")
            print(f"  ロック状態: {'ロック中' if is_locked else '解除'}")
            print(f"  タスクID: {current_task_id if current_task_id else 'なし'}")
            print(f"  ロック時刻: {locked_at if locked_at else 'なし'}")
            print("=" * 60)
            
            if is_locked:
                # ロックを解除
                cursor.execute('''
                    UPDATE lock_status 
                    SET is_locked = 0, current_task_id = NULL, locked_at = NULL
                    WHERE id = 1
                ''')
                conn.commit()
                print("\n✓ ロックを解除しました")
                print(f"  時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 解除後の状態を確認
                cursor.execute('SELECT * FROM lock_status WHERE id = 1')
                new_result = cursor.fetchone()
                print("\n新しいロック状態:")
                print(f"  ロック状態: {'ロック中' if new_result[1] else '解除'}")
                print("=" * 60)
            else:
                print("\n✓ ロックは既に解除されています")
                print("=" * 60)
        else:
            print("エラー: lock_statusテーブルが初期化されていません")
            return False
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"\nデータベースエラー: {e}")
        return False
    except Exception as e:
        print(f"\n予期しないエラー: {e}")
        return False

def show_status():
    """現在のロック状態のみを表示"""
    try:
        if not os.path.exists(DB_PATH):
            print(f"エラー: データベースファイルが見つかりません: {DB_PATH}")
            return
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM lock_status WHERE id = 1')
        result = cursor.fetchone()
        
        if result:
            is_locked = result[1]
            current_task_id = result[2]
            locked_at = result[3]
            
            print("=" * 60)
            print("現在のロック状態:")
            print(f"  ロック状態: {'ロック中' if is_locked else '解除'}")
            print(f"  タスクID: {current_task_id if current_task_id else 'なし'}")
            print(f"  ロック時刻: {locked_at if locked_at else 'なし'}")
            print("=" * 60)
        else:
            print("エラー: lock_statusテーブルが初期化されていません")
        
        conn.close()
        
    except Exception as e:
        print(f"エラー: {e}")

if __name__ == '__main__':
    import sys
    
    print("\n" + "=" * 60)
    print("Flask Uploader - ロック状態管理ツール")
    print("=" * 60 + "\n")
    
    if len(sys.argv) > 1 and sys.argv[1] == 'status':
        # ステータス表示のみ
        show_status()
    else:
        # ロックリセット
        success = reset_lock()
        
        if success:
            print("\n処理が完了しました")
        else:
            print("\n処理が失敗しました")
            sys.exit(1)

