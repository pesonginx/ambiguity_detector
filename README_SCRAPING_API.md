# スクレイピングAPI デモ

このプロジェクトは、Excelファイルに記載されたURLをSeleniumを使用した高度なスクレイピングで処理し、マークダウンファイルを生成するFastAPIアプリケーションです。

## 機能

- Excelファイル（.xlsx, .xls）のアップロード
- ファイル内のURLの自動検出
- **Selenium WebDriverを使用した高度なスクレイピング**
- **JavaScript対応と動的コンテンツの処理**
- **McAfee Web Gateway対応**
- **特定サイト向けの最適化されたコンテンツ抽出**
- 各URLのスクレイピング（タイトルと本文の抽出）
- マークダウンファイルの自動生成
- 非同期処理によるバックグラウンド実行
- **リアルタイム進捗管理** - スクレイピング処理中の詳細な進捗状況を監視
- 処理状況の監視
- 生成されたファイルのダウンロード
- **タスクとファイルの関連付け管理**
- **タスクに紐づいたファイルの一括ダウンロード（ZIP形式）**

## セットアップ

### 1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 2. ChromeDriverのインストール

Seleniumを使用するため、ChromeDriverが必要です：

#### Windows:
1. [ChromeDriver公式サイト](https://chromedriver.chromium.org/)から最新版をダウンロード
2. `chromedriver.exe`をプロジェクトルートに配置
3. 環境変数`DRIVER_PATH`でパスを指定（例：`DRIVER_PATH=C:\path\to\chromedriver.exe`）

#### Linux/Mac:
```bash
# Ubuntu/Debian
sudo apt-get install chromium-chromedriver

# macOS
brew install chromedriver
```

### 3. サンプルExcelファイルの作成

```bash
python create_sample_excel.py
```

### 4. アプリケーションの起動

```bash
python run_app.py
```

アプリケーションは `http://localhost:8000` で起動します。

## 環境変数設定

以下の環境変数で動作をカスタマイズできます：

```bash
# ChromeDriverのパス
DRIVER_PATH=chromedriver.exe

# プロキシ設定（必要に応じて）
HTTP_PROXY=http://proxy.example.com:8080
NO_PROXY=localhost,127.0.0.1

# スクレイピング設定
HEADLESS=true  # ヘッドレスモード（true/false）
WAIT_TIME=10   # ページ読み込み待機時間（秒）

# 出力設定
OUTPUT_DIR=app/static/markdown
TASK_FILES_DIR=app/static/task_files
```

## API エンドポイント

### 1. Excelファイルのアップロード

**POST** `/api/v1/scraping/upload-excel`

Excelファイルをアップロードしてスクレイピング処理を開始します。

**リクエスト:**
- `file`: Excelファイル（.xlsx, .xls）
- `description`: 説明（オプション）

**レスポンス:**
```json
{
  "success": true,
  "message": "ファイルのアップロードが完了し、スクレイピング処理を開始しました",
  "processed_urls": 0,
  "generated_files": 0,
  "download_url": "/api/v1/scraping/status/{task_id}"
}
```

### 2. 処理状況の確認

**GET** `/api/v1/scraping/status/{task_id}`

スクレイピング処理の現在の状況を取得します。

**レスポンス:**
```json
{
  "task_id": "uuid",
  "status": "processing",
  "progress": 0.5,
  "total_urls": 5,
  "processed_urls": 2,
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "message": "URL 2/5 完了: https://example.com"
}
```

### 3. タスクに紐づくファイル一覧の取得

**GET** `/api/v1/scraping/files/{task_id}`

タスクに紐づくマークダウンファイルの一覧を取得します。

**レスポンス:**
```json
{
  "task_id": "uuid",
  "files": [
    {
      "filename": "example_com_page.md",
      "original_url": "https://example.com/page",
      "size_bytes": 1024,
      "created_at": "2024-01-01T00:00:00",
      "download_url": "/api/v1/scraping/download-file/{task_id}/example_com_page.md"
    }
  ],
  "total_files": 1,
  "zip_download_url": "/api/v1/scraping/download-all/{task_id}"
}
```

### 4. 個別ファイルのダウンロード

**GET** `/api/v1/scraping/download-file/{task_id}/{filename}`

タスクに紐づく特定のマークダウンファイルをダウンロードします。

### 5. 全ファイルの一括ダウンロード（ZIP）

**GET** `/api/v1/scraping/download-all/{task_id}`

タスクに紐づくすべてのマークダウンファイルをZIPファイルとしてダウンロードします。

### 6. タスクのクリーンアップ

**DELETE** `/api/v1/scraping/cleanup/{task_id}`

タスクと関連ファイルを削除します。

## 使用方法

### 1. ブラウザでの確認

1. アプリケーションを起動
2. ブラウザで `http://localhost:8000/docs` にアクセス
3. Swagger UIでAPIをテスト

### 2. サンプルExcelファイルでのテスト

1. `create_sample_excel.py` を実行してサンプルファイルを作成
2. 作成された `sample_urls.xlsx` をアップロード
3. 処理状況を確認
4. 生成されたマークダウンファイルをダウンロード

### 3. カスタムExcelファイルでの使用

以下の形式のExcelファイルを準備してください：

| URL | 説明 | カテゴリ |
|-----|------|----------|
| https://example.com | サンプルサイト | テスト |
| https://example.org | 別のサイト | サンプル |

## ファイル構造

```
app/
├── __init__.py
├── main.py                 # FastAPIアプリケーションのメインファイル
├── core/
│   ├── __init__.py
│   └── config.py          # アプリケーション設定
├── api/
│   ├── __init__.py
│   └── scraping_api.py    # スクレイピングAPIエンドポイント
├── schemas/
│   ├── __init__.py
│   └── scraping.py        # データモデルの定義
├── services/
│   ├── __init__.py
│   └── scraping_service.py # Seleniumベースのスクレイピング処理
└── static/
    ├── markdown/          # 生成されたマークダウンファイルの保存先
    └── task_files/        # タスクとファイルの関連付け情報

temp_uploads/               # 一時アップロードファイル
run_app.py                  # アプリケーション起動スクリプト
create_sample_excel.py      # サンプルExcelファイル作成スクリプト
requirements.txt            # 依存関係
```

## 技術仕様

### 使用技術

- **FastAPI**: Webフレームワーク
- **Selenium**: ブラウザ自動化とスクレイピング
- **Chrome WebDriver**: Chromeブラウザの制御
- **BeautifulSoup4**: HTMLパースとコンテンツ抽出
- **html2text**: HTMLからマークダウンへの変換
- **Pandas**: Excelファイルの読み込み
- **Uvicorn**: ASGIサーバー

### 特徴

- **高度なスクレイピング**: SeleniumによるJavaScript対応と動的コンテンツ処理
- **サイト最適化**: LINE、Appllio等の特定サイト向け最適化
- **セキュリティ対応**: McAfee Web Gateway等の企業セキュリティ対策対応
- **非同期処理**: バックグラウンドでスクレイピングを実行
- **エラーハンドリング**: 各URLの処理エラーを個別に管理
- **ファイル管理**: 安全なファイル名生成とクリーンアップ
- **リアルタイム進捗管理**: スクレイピング処理中の詳細な進捗状況を監視
- **スケーラビリティ**: 大量のURLにも対応
- **タスク管理**: タスクとファイルの関連付けによる整理された管理
- **一括ダウンロード**: ZIPファイルによる効率的なファイル配布

## Seleniumスクレイピングの特徴

### 1. **JavaScript対応**
- 動的に生成されるコンテンツの取得
- SPA（Single Page Application）対応
- Ajax通信後のコンテンツ更新に対応

### 2. **サイト最適化**
- LINE公式サイト（help.line.me, guide.line.me）
- Appllio（appllio.com）
- その他の企業サイト向け最適化

### 3. **セキュリティ対策対応**
- McAfee Web Gateway画面の自動バイパス
- 企業のプロキシ環境での動作
- 証明書エラーの処理

### 4. **コンテンツ抽出の最適化**
- 不要要素（ナビゲーション、サイドバー等）の自動除去
- メインコンテンツの優先抽出
- 表（table）のHTML形式保持

## 進捗管理の仕組み

### リアルタイム進捗更新

スクレイピング処理中、以下のタイミングで進捗が更新されます：

1. **処理開始時**: `progress: 0.0`, `message: "スクレイピング処理を開始しました"`
2. **各URL処理時**: `progress: i/total_urls`, `message: "URL i/total を処理中: {url}"`
3. **URL完了時**: `progress: i/total_urls`, `message: "URL i/total 完了: {url}"`
4. **エラー発生時**: `progress: i/total_urls`, `message: "URL i/total エラー: {url}"`
5. **処理完了時**: `progress: 1.0`, `message: "処理完了: X個のマークダウンファイルを生成しました"`

### 進捗監視の例

```bash
# 処理開始直後
GET /api/v1/scraping/status/{task_id}
{
  "progress": 0.0,
  "processed_urls": 0,
  "total_urls": 5,
  "message": "スクレイピング処理を開始しました"
}

# 2番目のURL処理中
GET /api/v1/scraping/status/{task_id}
{
  "progress": 0.4,
  "processed_urls": 2,
  "total_urls": 5,
  "message": "URL 2/5 を処理中: https://example.com"
}

# 処理完了
GET /api/v1/scraping/status/{task_id}
{
  "progress": 1.0,
  "processed_urls": 5,
  "total_urls": 5,
  "message": "処理完了: 5個のマークダウンファイルを生成しました"
}
```

## タスク管理の仕組み

### タスクとファイルの関連付け

各スクレイピングタスクは一意のタスクIDを持ち、生成されたマークダウンファイルはそのタスクIDと関連付けられます。

1. **タスク作成**: Excelファイルアップロード時にタスクIDが生成
2. **ファイル生成**: スクレイピング処理中にファイルがタスクIDと関連付け
3. **ファイル管理**: タスクIDでファイル一覧の取得・ダウンロードが可能
4. **クリーンアップ**: タスク削除時に関連ファイルも整理

### ファイルダウンロードオプション

- **個別ダウンロード**: 特定のファイルを個別にダウンロード
- **一括ダウンロード**: タスクに紐づく全ファイルをZIP形式でダウンロード

## 注意事項

1. **ChromeDriver**: 適切なバージョンのChromeDriverが必要
2. **レート制限**: スクレイピング対象サイトの利用規約を確認してください
3. **エラー処理**: ネットワークエラーやサイトの変更に対応
4. **ファイルサイズ**: 大きなExcelファイルは処理時間が長くなる可能性があります
5. **セキュリティ**: 本番環境では適切な認証・認可を実装してください
6. **ストレージ**: タスクファイル情報は永続化されるため、定期的なクリーンアップを推奨
7. **進捗監視**: 大量のURLを処理する場合は、適切な間隔で進捗状況を確認してください
8. **WebDriver管理**: 各リクエストでWebDriverが適切にクローズされることを確認

## カスタマイズ

### スクレイピングルールの変更

`app/services/scraping_service.py` の以下のメソッドを編集して、特定のサイトに最適化されたコンテンツ抽出ルールを実装できます：

- `get_content_selector()`: サイト固有のセレクター設定
- `remove_unwanted_elements()`: 除外要素の設定
- `handle_mcafee_gateway()`: セキュリティ画面の対応

### 出力形式の変更

`generate_markdown` メソッドを編集して、HTML、JSON、CSVなど、異なる出力形式に対応できます。

### データベース連携

現在はメモリ上でタスク状態を管理していますが、PostgreSQL、Redisなどのデータベースに変更することで、永続化とスケーラビリティを向上できます。

### ファイル管理の拡張

現在のJSONベースのファイル管理を、より高度なデータベースベースの管理に変更することで、検索・フィルタリング機能を追加できます。

### 進捗管理の拡張

現在のコールバックベースの進捗管理を、WebSocketやServer-Sent Eventsを使用したリアルタイム通知に変更することで、より高度な進捗監視が可能になります。

### Selenium設定のカスタマイズ

`app/core/config.py` で以下の設定をカスタマイズできます：

- ヘッドレスモードの有効/無効
- 待機時間の調整
- プロキシ設定
- ユーザーエージェントの変更

