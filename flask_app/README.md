# Flaskファイルアップローダーシステム

Excelファイルをアップロードし、バックグラウンドで自動処理を実行するFlaskアプリケーションです。

## 🚀 機能

### 主要機能
- **Excelファイルアップロード**: xlsxファイルのみ対応（最大200MB）
- **日本語ファイル名対応**: 日本語を含むファイル名も安全に処理
- **メールアドレス認証**: @gmail.comドメインのみ許可
- **リアルタイム進捗表示**: Server-Sent Events (SSE)による処理状況のライブ更新
- **同時アクセス制御**: 処理中は全ユーザーのアップロードを自動的に無効化
- **詳細ログ管理**: 処理の各ステップを記録・表示
- **処理履歴管理**: 過去のアップロードとログを確認可能
- **インデックスファイルダウンロード**: 処理完了後、インデックス化データ一覧をダウンロード可能
- **自動履歴管理**: インデックス化データ一覧は最新5件のみ保持、古いファイルは自動削除

### 画面
1. **アップロード画面** (`/`): ファイルアップロードとリアルタイム進捗表示
2. **ファイル一覧画面** (`/uploads`): アップロード履歴の一覧表示
3. **ログ詳細画面** (`/logs/<task_id>`): 個別タスクの詳細ログ表示

## 📋 システム要件

- Python 3.8以上
- Flask 3.0.0
- SQLite3（標準ライブラリ）

## 🔧 インストール

### 1. 依存パッケージのインストール

```bash
cd flask_app
pip install -r requirements.txt
```

### 2. ディレクトリ構造の確認

```
flask_app/
├── app.py                       # メインアプリケーション
├── database.py                  # データベース管理
├── processor.py                 # バックグラウンド処理
├── excel_to_index_processor.py # Excel→JSON変換処理
├── requirements.txt             # 依存パッケージ
├── README.md                   # このファイル
├── EXCEL_PROCESSOR_README.md   # Excel処理の詳細ドキュメント
├── data/                       # データディレクトリ
│   ├── input_data/             # アップロードファイル格納先
│   ├── output_data/            # 処理済みJSONファイル
│   └── インデックス化データ一覧.xlsx  # 処理結果Excel
├── templates/                  # HTMLテンプレート
│   ├── base.html
│   ├── index.html
│   ├── uploads.html
│   └── logs.html
├── static/                     # 静的ファイル
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── main.js
├── logs/                       # ログファイル
└── uploads.db                 # SQLiteデータベース（自動生成）
```

## 🎯 起動方法

### 開発モードで起動

```bash
cd flask_app
python app.py
```

アプリケーションは `http://localhost:5000` で起動します。

### 本番環境での起動（推奨）

Gunicornを使用する場合:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 app:app
```

## 📖 使用方法

### 1. ファイルのアップロード

1. ブラウザで `http://localhost:5000` にアクセス
2. 承認者のメールアドレスを入力（@gmail.comドメイン）
3. 作業者のメールアドレスを入力（@gmail.comドメイン）
4. xlsxファイルを選択
5. 「アップロード開始」ボタンをクリック

### 2. 処理の監視

- アップロード後、自動的に処理が開始されます
- 画面上でリアルタイムに進捗状況が表示されます
- プログレスバーと詳細ログで処理状況を確認できます

### 3. 処理履歴の確認

- ナビゲーションバーの「ファイル一覧」をクリック
- 過去のアップロード履歴が表示されます
- 「ログ表示」ボタンで各処理の詳細ログを確認できます

## 🔐 セキュリティ機能

### メールアドレス検証
- 承認者・作業者のメールアドレスは@gmail.comドメインのみ許可
- 無効なドメインの場合、エラーメッセージを表示して処理を拒否

### ファイル検証
- 拡張子チェック: xlsxファイルのみ許可
- ファイルサイズ制限: 200MB
- 日本語ファイル名対応: UUID使用で安全にファイル名を処理

### 同時アクセス制御
- データベースレベルでのロック管理
- 処理中は全クライアントのアップロード機能を自動的に無効化
- 2秒ごとのポーリングでロック状態をチェック

### インデックスファイル管理
- 処理完了後、インデックス化データ一覧を`data/output_data/`に保存
- ファイル名形式: `インデックス化データ一覧_{task_id}.xlsx`
- 最新5件のみ保持、6件以降は自動削除
- アップロード履歴画面からダウンロード可能
- ファイルが存在しない場合はダウンロードボタンが無効化

## 🗄️ データベース構造

### uploads テーブル
アップロード情報を管理

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | 主キー |
| task_id | TEXT | タスク固有ID（UUID） |
| filename | TEXT | ファイル名 |
| approver_email | TEXT | 承認者メールアドレス |
| worker_email | TEXT | 作業者メールアドレス |
| upload_date | TEXT | アップロード日時 |
| start_time | TEXT | 処理開始時刻 |
| end_time | TEXT | 処理終了時刻 |
| duration | REAL | 所要時間（秒） |
| status | TEXT | ステータス（processing/completed/error） |
| error_message | TEXT | エラーメッセージ |
| index_excel_path | TEXT | インデックス化データ一覧のファイルパス |

### logs テーブル
処理ログを管理

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | 主キー |
| task_id | TEXT | タスクID（外部キー） |
| timestamp | TEXT | タイムスタンプ |
| level | TEXT | ログレベル（INFO/WARNING/ERROR） |
| step_name | TEXT | 処理ステップ名 |
| message | TEXT | ログメッセージ |
| progress | INTEGER | 進捗率（0-100） |

### lock_status テーブル
ロック状態を管理

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | 主キー（常に1） |
| is_locked | INTEGER | ロック状態（0/1） |
| current_task_id | TEXT | 現在実行中のタスクID |
| locked_at | TEXT | ロック開始時刻 |

## 🔄 処理フロー

### ファイルアップロード～処理完了までの流れ

1. **ファイルアップロード**
   - クライアントがファイルとメールアドレスをPOST
   - サーバーがバリデーションを実行
   - ファイルを`input_data/`に保存
   - データベースに記録を作成

2. **ロック取得**
   - `lock_status`テーブルでロックを設定
   - 他のユーザーのアップロードを無効化

3. **バックグラウンド処理開始**
   - 別スレッドで9ステップの処理を実行
   - 各ステップで進捗をログに記録

4. **リアルタイム更新**
   - Server-Sent Events (SSE)でクライアントにログを配信
   - プログレスバーと詳細ログをリアルタイム更新

5. **処理完了**
   - 処理結果をデータベースに記録
   - インデックス化データ一覧をtask_id付きでリネーム
   - ファイルパスをデータベースに記録
   - 古いインデックスファイルを削除（最新5件のみ保持）
   - ファイルを`input_data/`から削除
   - ロックを解放

6. **エラー発生時**
   - エラー情報をログに記録
   - ファイルを削除
   - ロックを解放
   - エラーメッセージを表示

## 🌐 APIエンドポイント

### ページエンドポイント
- **`GET /`**: アップロード画面
- **`GET /uploads`**: アップロード履歴一覧
- **`GET /logs/<task_id>`**: 詳細ログ表示

### APIエンドポイント
- **`POST /upload`**: ファイルアップロード
  - パラメータ: `file`, `approver_email`, `worker_email`
  - レスポンス: `{ success: bool, task_id: str, message: str }`

- **`GET /api/lock_status`**: ロック状態取得
  - レスポンス: `{ is_locked: bool, current_task_id: str }`

- **`GET /api/stream/<task_id>`**: ログストリーミング（SSE）
  - Server-Sent Eventsでログをリアルタイム配信

- **`GET /api/uploads`**: アップロード履歴取得（JSON）
  - レスポンス: アップロード履歴の配列

- **`GET /api/logs/<task_id>`**: 詳細ログ取得（JSON）
  - レスポンス: `{ upload: {...}, logs: [...] }`

- **`GET /download/<task_id>`**: インデックスファイルダウンロード
  - レスポンス: Excelファイル（`インデックス化データ一覧_{task_id}.xlsx`）

## 🎨 カスタマイズ

### 処理ステップの変更

`processor.py`の`PROCESSING_STEPS`を編集:

```python
PROCESSING_STEPS = [
    {"name": "ステップ名", "description": "説明"},
    # ... 追加のステップ
]
```

### 実際の処理ロジックの実装

`processor.py`の`process_step()`関数を編集して、実際の処理ロジックを実装してください。

### メールドメインの変更

`app.py`の`validate_email()`関数を編集:

```python
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@yourdomain\.com$'
    return re.match(pattern, email) is not None
```

### ファイルサイズ制限の変更

`app.py`の設定を変更:

```python
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
```

## 🐛 トラブルシューティング

### データベースエラー

データベースをリセットする場合:

```bash
rm uploads.db
python app.py  # 自動的に再作成されます
```

### ロックが解除されない

エラーが発生してロックが残っている場合、専用のリセットスクリプトを使用してください:

```bash
# ロック状態を確認してリセット
python reset_lock.py

# ロック状態の確認のみ
python reset_lock.py status
```

または、手動でロックを解除:

```python
python -c "from database import set_lock, init_db; init_db(); set_lock(False)"
```

**注意**: システムは自動的に以下の対策を行います：
- **サーバー起動時**: 前回の異常終了で残ったロックを自動的に解除
- **エラー発生時**: `finally` ブロックでロックを確実に解除
- **ロック解除失敗時**: 3回までリトライ
- **全て失敗した場合**: 直接データベースを更新してロックを強制解除

通常は手動でのロック解除は不要です。サーバーを再起動するだけで自動的にリセットされます。

### ポートが既に使用されている

別のポートで起動:

```python
# app.pyの最終行を変更
app.run(debug=True, host='0.0.0.0', port=8080, threaded=True)
```

## 📝 API エンドポイント

### POST /api/upload
ファイルをアップロード

**リクエスト:**
- `file`: xlsxファイル
- `approver_email`: 承認者メールアドレス
- `worker_email`: 作業者メールアドレス

**レスポンス:**
```json
{
  "success": true,
  "task_id": "uuid",
  "message": "メッセージ"
}
```

### GET /api/lock_status
ロック状態を取得

**レスポンス:**
```json
{
  "is_locked": true,
  "current_task_id": "uuid"
}
```

### GET /api/stream/<task_id>
処理ログをSSEでストリーミング

**レスポンス:** Server-Sent Events形式

### GET /api/uploads
アップロード一覧を取得（JSON）

### GET /api/logs/<task_id>
タスクのログを取得（JSON）

## 📄 ライセンス

このプロジェクトは内部使用を目的としています。

## 👥 サポート

問題が発生した場合は、システム管理者に連絡してください。


