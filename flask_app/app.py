"""
Flaskアプリケーション - ファイルアップローダー
"""
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_file
from werkzeug.utils import secure_filename
import os
import uuid
import threading
import time
import re
import json
from datetime import datetime
from pathlib import Path

from database import (
    init_db, create_upload_record, get_all_uploads,
    get_upload_by_task_id, get_logs_by_task_id,
    get_lock_status, is_locked, set_lock
)
from processor_new import run_processing, OUTPUT_DIR

app = Flask(__name__)

# 設定
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'data', 'input_data')
ALLOWED_EXTENSIONS = {'xlsx'}

# エラーシミュレーション（デバッグ用）
# Trueにするとエラーが発生するテストが実行されます（80%の確率でエラー発生）
SIMULATE_ERROR = False

# データベース初期化
init_db()

# サーバー起動時にロックを解除（前回の異常終了時の残留ロックをクリア）
try:
    lock_status = get_lock_status()
    if lock_status.get('is_locked'):
        print(f"[WARNING] 起動時にロックが残っていました。解除します...")
        print(f"  - 前回のタスクID: {lock_status.get('current_task_id')}")
        print(f"  - ロック時刻: {lock_status.get('locked_at')}")
        set_lock(False)
        print("[INFO] ロックを解除しました。")
    else:
        print("[INFO] ロック状態: 正常（解除済み）")
except Exception as e:
    print(f"[WARNING] ロック状態の確認に失敗しました: {e}")
    print("[INFO] 念のためロックを解除します...")
    try:
        set_lock(False)
        print("[INFO] ロックを解除しました。")
    except Exception as reset_error:
        print(f"[ERROR] ロック解除に失敗しました: {reset_error}")

def allowed_file(filename):
    """ファイルの拡張子をチェック"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_filename(original_filename):
    """
    日本語を含むファイル名を安全に処理する
    UUIDを使用してファイル名を生成し、拡張子のみ元のファイルから取得
    
    Args:
        original_filename: 元のファイル名
        
    Returns:
        str: 安全なファイル名（UUID + 拡張子）
    """
    # 拡張子を取得
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()
    else:
        ext = ''
    
    # UUIDを生成してファイル名とする
    safe_name = str(uuid.uuid4())
    
    if ext:
        return f"{safe_name}.{ext}"
    else:
        return safe_name

def validate_email(email):
    """メールアドレスのバリデーション（@gmail.comドメインのみ許可）"""
    pattern = r'^[a-zA-Z0-9._%+-]+@gmail\.com$'
    return re.match(pattern, email) is not None

def cleanup_old_index_files():
    """
    古いインデックス化データ一覧ファイルを削除
    最新5件のみを保持し、それ以降は削除する
    """
    try:
        # すべてのアップロード記録を取得（新しい順）
        uploads = get_all_uploads()
        
        # 6件目以降のインデックスファイルを削除
        if len(uploads) > 5:
            for upload in uploads[5:]:
                index_excel_path = upload.get('index_excel_path')
                if index_excel_path and os.path.exists(index_excel_path):
                    try:
                        os.remove(index_excel_path)
                        print(f"[INFO] 古いインデックスファイルを削除: {index_excel_path}")
                    except Exception as e:
                        print(f"[ERROR] ファイル削除失敗: {e}")
    except Exception as e:
        print(f"[ERROR] cleanup_old_index_files: {e}")

@app.route('/')
def index():
    """メインページ"""
    return render_template('index.html')

@app.route('/uploads')
def uploads_list():
    """アップロード一覧ページ"""
    uploads = get_all_uploads()
    return render_template('uploads.html', uploads=uploads)

@app.route('/logs/<task_id>')
def logs_view(task_id):
    """ログ表示ページ"""
    upload = get_upload_by_task_id(task_id)
    if not upload:
        return "タスクが見つかりません", 404
    
    logs = get_logs_by_task_id(task_id)
    return render_template('logs.html', upload=upload, logs=logs)

@app.route('/processing/<task_id>')
def processing_view(task_id):
    """処理状況表示ページ"""
    upload = get_upload_by_task_id(task_id)
    if not upload:
        return "タスクが見つかりません", 404
    
    return render_template('processing.html', task_id=task_id, upload=upload)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """ファイルアップロードエンドポイント"""
    
    # ロック状態をチェック
    if is_locked():
        return jsonify({
            'success': False,
            'error': '現在、別の処理が実行中です。しばらくお待ちください。'
        }), 400
    
    # ファイルのチェック
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'ファイルが選択されていません'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'ファイルが選択されていません'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'xlsxファイルのみアップロード可能です'}), 400
    
    # メールアドレスの取得とバリデーション
    approver_email = request.form.get('approver_email', '').strip()
    worker_email = request.form.get('worker_email', '').strip()
    
    if not approver_email or not worker_email:
        return jsonify({'success': False, 'error': '承認者と作業者のメールアドレスを入力してください'}), 400
    
    if not validate_email(approver_email):
        return jsonify({'success': False, 'error': '承認者のメールアドレスが無効です'}), 400
    
    if not validate_email(worker_email):
        return jsonify({'success': False, 'error': '作業者のメールアドレスが無効です'}), 400
    
    # ファイルを保存
    original_filename = file.filename  # 元のファイル名を保存（日本語対応）
    task_id = str(uuid.uuid4())
    safe_name = safe_filename(original_filename)  # 安全なファイル名を生成
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    
    try:
        file.save(file_path)
    except Exception as e:
        return jsonify({'success': False, 'error': f'ファイルの保存に失敗しました: {str(e)}'}), 500
    
    # データベースに記録（元のファイル名を使用）
    try:
        create_upload_record(task_id, original_filename, approver_email, worker_email)
    except Exception as e:
        # ファイルを削除
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'success': False, 'error': f'データベースへの記録に失敗しました: {str(e)}'}), 500
    
    # バックグラウンド処理を開始
    thread = threading.Thread(
        target=run_processing,
        args=(task_id, file_path, SIMULATE_ERROR),  # エラーシミュレーションフラグを使用
        daemon=True
    )
    thread.start()
    
    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': 'ファイルのアップロードに成功しました。処理を開始します。'
    })

@app.route('/api/lock_status')
def lock_status():
    """ロック状態を取得"""
    status = get_lock_status()
    return jsonify({
        'is_locked': bool(status['is_locked']),
        'current_task_id': status.get('current_task_id')
    })

@app.route('/api/stream/<task_id>')
def stream_logs(task_id):
    """Server-Sent Eventsでログとステップ進捗をストリーミング"""
    
    def generate():
        """ログとステップ進捗をストリーミング生成"""
        last_log_id = 0
        upload = get_upload_by_task_id(task_id)
        
        if not upload:
            yield f"data: {{'error': 'タスクが見つかりません'}}\n\n"
            return
        
        # 処理が完了するまでループ
        while True:
            upload = get_upload_by_task_id(task_id)
            logs = get_logs_by_task_id(task_id)
            
            # 新しいログのみを送信
            new_logs = logs[last_log_id:]
            for log in new_logs:
                log_data = {
                    'type': 'log',
                    'timestamp': log['timestamp'],
                    'level': log['level'],
                    'step_name': log['step_name'],
                    'message': log['message'],
                    'progress': log['progress']
                }
                yield f"data: {json.dumps(log_data)}\n\n"
                last_log_id += 1
            
            # ステップ進捗情報を送信
            if upload:
                step_data = {
                    'type': 'step_progress',
                    'current_step': upload.get('current_step', ''),
                    'current_step_index': upload.get('current_step_index', 0),
                    'total_steps': upload.get('total_steps', 10),
                    'step_progress': upload.get('step_progress', 0),
                    'estimated_remaining_time': upload.get('estimated_remaining_time', 0),
                    'record_count': upload.get('record_count', 0),
                    'json_files_created': upload.get('json_files_created', 0),
                    'json_files_deleted': upload.get('json_files_deleted', 0)
                }
                yield f"data: {json.dumps(step_data)}\n\n"
            
            # 処理が完了したかチェック
            if upload['status'] in ['completed', 'error']:
                # 最終ステータスを送信
                final_data = {
                    'type': 'final',
                    'status': upload['status'],
                    'duration': upload.get('duration', 0),
                    'error_message': upload.get('error_message'),
                    'is_final': True
                }
                yield f"data: {json.dumps(final_data)}\n\n"
                break
            
            # 1秒待機
            time.sleep(1)
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/uploads')
def api_uploads():
    """アップロード一覧をJSON形式で取得"""
    uploads = get_all_uploads()
    return jsonify({'uploads': uploads})

@app.route('/api/logs/<task_id>')
def api_logs(task_id):
    """ログをJSON形式で取得"""
    upload = get_upload_by_task_id(task_id)
    if not upload:
        return jsonify({'error': 'タスクが見つかりません'}), 404
    
    logs = get_logs_by_task_id(task_id)
    return jsonify({
        'upload': upload,
        'logs': logs
    })

@app.route('/api/task/<task_id>/stats')
def api_task_stats(task_id):
    """タスクの統計情報を取得"""
    upload = get_upload_by_task_id(task_id)
    if not upload:
        return jsonify({'error': 'タスクが見つかりません'}), 404
    
    return jsonify({
        'task_id': task_id,
        'status': upload.get('status'),
        'record_count': upload.get('record_count', 0),
        'json_files_created': upload.get('json_files_created', 0),
        'json_files_deleted': upload.get('json_files_deleted', 0),
        'current_step': upload.get('current_step', ''),
        'current_step_index': upload.get('current_step_index', 0),
        'total_steps': upload.get('total_steps', 10),
        'step_progress': upload.get('step_progress', 0),
        'estimated_remaining_time': upload.get('estimated_remaining_time', 0),
        'start_time': upload.get('start_time'),
        'end_time': upload.get('end_time'),
        'duration': upload.get('duration', 0)
    })

@app.route('/download/<task_id>')
def download_index_excel(task_id):
    """インデックス化データ一覧のダウンロード"""
    try:
        # タスク情報を取得
        upload = get_upload_by_task_id(task_id)
        if not upload:
            return jsonify({'success': False, 'error': 'タスクが見つかりません'}), 404
        
        # インデックスファイルパスを取得
        index_excel_path = upload.get('index_excel_path')
        if not index_excel_path or not os.path.exists(index_excel_path):
            return jsonify({'success': False, 'error': 'ファイルが見つかりません'}), 404
        
        # ファイルをダウンロード
        return send_file(
            index_excel_path,
            as_attachment=True,
            download_name=f"インデックス化データ一覧_{task_id}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"[ERROR] ダウンロードエラー: {e}")
        return jsonify({'success': False, 'error': f'ダウンロードに失敗しました: {str(e)}'}), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    """ファイルサイズ超過エラー"""
    return jsonify({
        'success': False,
        'error': 'ファイルサイズが200MBを超えています'
    }), 413

@app.errorhandler(500)
def internal_server_error(error):
    """サーバーエラー"""
    return jsonify({
        'success': False,
        'error': '内部サーバーエラーが発生しました'
    }), 500

if __name__ == '__main__':
    # input_dataディレクトリが存在しない場合は作成
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # アプリケーション起動
    app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)

