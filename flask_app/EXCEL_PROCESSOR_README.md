# Excel to Index JSON Processor

Excelファイルを読み込み、Azure OpenAIを使用してEmbeddingとキーワードを抽出し、個別JSONファイルとして出力する処理システムです。

## 📋 機能概要

このプロセッサは以下の9ステップで処理を実行します：

1. **ファイル検証**: Excelファイルの読み込みと検証
2. **バリデーションチェック**: データの内容を確認
3. **UUID生成**: rag_id列の追加
4. **データクレンジング**: 重複チェックと削除対象特定
5. **旧データ削除**: 既存JSONファイルの削除（Git管理）
6. **JSON生成**: 登録用JSONデータの作成
7. **Embedding取得**: Azure OpenAIでEmbedding生成（並列処理）
8. **キーワード抽出**: GPTによるキーワード抽出（並列処理）
9. **ファイル出力**: 個別JSONファイルの分割と保存

## 📁 ディレクトリ構造

```
flask_app/
├── excel_to_index_processor.py  # 処理ロジック
├── processor_new.py              # Flaskアプリ統合版
├── data/
│   ├── input_data/              # 入力Excelファイル（*.xlsx）
│   ├── output_data/             # 出力JSONファイル（{rag_id}.json）
│   └── インデックス化データ一覧.xlsx  # 中間ファイル（ダウンロード用）
└── logs/                        # 各種ログファイル
```

## 🔧 必要な環境変数（.envファイル）

`.env`ファイルは`flask_app`の1つ上の階層に配置してください。

```bash
# Azure OpenAI Embedding
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_ENGINE_EMBEDDING=text-embedding-ada-002

# Azure OpenAI GPT (キーワード抽出用)
AOAI_ITB_ENDPOINT=https://your-endpoint.openai.azure.com/
AOAI_ITB_API_KEY=your-api-key
AZURE_OPENAI_API_ENGINE_GPT=gpt-4

# プロキシ設定（必要な場合）
HTTPS_PROXY=http://proxy.example.com:8080
NO_PROXY=localhost,127.0.0.1

# Azure AI Search（今回は使用しないが環境変数として必要な場合）
AZURE_AI_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_AI_SEARCH_API_KEY=your-search-key
```

## 📝 入力Excelファイルの形式

### 必須シート名
- `rag`

### 必須列
- `thread_id`: スレッドID
- `group_id`: グループID
- `update_timestamp`: 更新日時（YYYYMMDD形式）
- `content`: コンテンツ（日本語）
- `content_embedding`: embeddingベクトル
- `category_id_large`: 大カテゴリID
- `category_id_medium`: 中カテゴリID
- `category_id_small`: 小カテゴリID
- `effective_start_date`: 有効開始日（YYYYMMDD形式）
- `effective_end_date`: 有効終了日（YYYYMMDD形式）

### オプション列
- `rag_id`: 既存データの更新時に使用（削除対象の特定）

## 🚀 使用方法

### 1. パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. Excelファイルの配置

処理したいExcelファイルを`flask_app/data/input_data/`に配置します。

```bash
flask_app/data/input_data/
├── data_001.xlsx
├── data_002.xlsx
└── data_003.xlsx
```

### 3. Flaskアプリからの実行

Webインターフェースからファイルをアップロードすると自動的に処理が開始されます。

```bash
cd flask_app
python app.py
```

ブラウザで`http://localhost:5000`にアクセスし、Excelファイルをアップロードします。

### 4. スタンドアロンでの実行

プロセッサを直接実行することもできます：

```python
from pathlib import Path
from excel_to_index_processor import process_excel_to_index, INPUT_DIR, OUTPUT_DIR

# 処理実行
excel_output_path = process_excel_to_index(
    input_dir=INPUT_DIR,
    output_dir=OUTPUT_DIR,
    callback=None  # コールバックなし
)

print(f"処理完了: {excel_output_path}")
```

## 📤 出力ファイル

### 個別JSONファイル

`flask_app/data/output_data/{rag_id}.json`

```json
{
    "rag_id": "uuid-here",
    "thread_id": "12345",
    "group_id": "67890",
    "update_timestamp": "2025-01-01",
    "content": "質問内容 \n\n English content",
    "content_embedding": [0.123, 0.456, ...],  // 1536次元のベクトル
    "content_keywords": ["キーワード1", "キーワード2", "キーワード3"],
    "category_id_large": "1",
    "category_id_medium": "2",
    "category_id_small": "3",
    "effective_start_date": "2025-01-01",
    "effective_end_date": "2099-12-31",
    "extra_field_1": "",
    "extra_field_2": ""
}
```

### インデックス化データ一覧

`flask_app/data/インデックス化データ一覧.xlsx`

処理されたすべてのデータが含まれるExcelファイル（ユーザーダウンロード用）

## ⚙️ 処理のカスタマイズ

### 並列処理のワーカー数変更

`processor_new.py`で並列処理の設定を変更できます：

```python
# Embedding取得の並列処理（デフォルト: 4）
json_records = add_embeddings_batch(json_records, callback, max_workers=8)

# キーワード抽出の並列処理（デフォルト: 4）
json_records = extract_keywords_batch(json_records, callback, max_workers=8)
```

### リトライ回数の変更

`excel_to_index_processor.py`で設定：

```python
# Embedding取得のリトライ（デフォルト: 3回、2秒間隔）
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def get_embedding_with_retry(...):
    ...

# キーワード抽出のリトライ（デフォルト: 60回、1秒間隔）
@retry(stop=stop_after_attempt(60), wait=wait_fixed(1))
async def extract_keywords_async(...):
    ...
```

## 🔍 ログ

処理ログは以下に記録されます：

- **データベース**: `flask_app/uploads.db` - ログテーブル
- **ファイル**: `flask_app/logs/` - 各種ログファイル

## ⚠️ 注意事項

### メモリ管理

- 大量のデータを処理する場合、メモリ使用量に注意してください
- 処理が完了したDataFrameは適時削除されます
- 並列処理のワーカー数を増やすとメモリ使用量が増加します

### API制限

- Azure OpenAIのレート制限に注意してください
- リトライ機能により一時的なエラーは自動的に回復します
- 大量のデータを処理する場合は、バッチサイズを調整してください

### Git削除機能

現在の`delete_old_files_from_git()`はダミー実装です。実際のGit操作を行う場合は以下を実装してください：

```python
import subprocess

def delete_old_files_from_git(delete_list: List[str], callback=None):
    """Git管理下のファイルを削除"""
    for rag_id in delete_list:
        file_path = f"data/output_data/{rag_id}.json"
        try:
            # git rm コマンドを実行
            subprocess.run(['git', 'rm', file_path], check=True)
            # またはGit APIを使用
        except Exception as e:
            if callback:
                callback.log_error("旧データ削除", f"削除失敗: {rag_id}", 50)
```

## 🐛 トラブルシューティング

### Excelファイルが見つからない

```
FileNotFoundError: フォルダ内にExcelファイルが見つかりませんでした
```

**解決策**: `flask_app/data/input_data/`にxlsxファイルが存在するか確認

### 必須列が不足している

```
ValueError: 必須列が不足しています: content, thread_id
```

**解決策**: Excelファイルに必須列が含まれているか確認

### Azure APIエラー

```
openai.error.RateLimitError: Rate limit exceeded
```

**解決策**: 
- レート制限を確認
- リトライ設定を調整
- 並列処理のワーカー数を減らす

### メモリエラー

```
MemoryError: Unable to allocate array
```

**解決策**:
- 入力ファイルを分割
- 並列処理のワーカー数を減らす
- サーバーのメモリを増やす

## 📞 サポート

問題が発生した場合は、以下の情報と共に報告してください：

- エラーメッセージ
- 処理していたファイルの行数
- ログファイルの内容
- 環境変数の設定（機密情報は除く）

