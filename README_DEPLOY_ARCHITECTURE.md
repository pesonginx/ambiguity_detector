# デプロイアーキテクチャガイド

このドキュメントでは、新しいデプロイアーキテクチャの全体像と使用方法について説明します。

## 目次

1. [アーキテクチャ概要](#アーキテクチャ概要)
2. [処理フロー](#処理フロー)
3. [使用方法](#使用方法)
4. [環境変数設定](#環境変数設定)
5. [トラブルシューティング](#トラブルシューティング)

## アーキテクチャ概要

新しいアーキテクチャでは、以下の3つのコンポーネントが連携してデプロイを実行します：

```
┌─────────────────────────────────────────────────────────────────┐
│                     Flask App (ポート 5000)                      │
│                                                                 │
│  [Excel処理] Steps 1-9                                          │
│  ├── ファイル検証                                                │
│  ├── バリデーションチェック                                       │
│  ├── UUID生成                                                   │
│  ├── データクレンジング                                          │
│  ├── 旧データ削除（ローカル）                                     │
│  ├── JSON生成                                                   │
│  ├── Embedding取得                                              │
│  ├── キーワード抽出                                              │
│  └── ファイル出力                                                │
│                                                                 │
│  [Git/デプロイ] Step 10                                         │
│  ├── GitLab Commits API（バッチコミット 100件/回）              │
│  ├── タグ作成                                                   │
│  ├── deploy_config.json保存（FastAPI呼び出し）                  │
│  ├── Jenkins実行                                                │
│  └── ファイルクリーンアップ                                      │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI (ポート 8085)                         │
│                                                                 │
│  [デプロイAPI]                                                   │
│  ├── POST /api/v1/deploy/config (deploy_config.json保存)       │
│  ├── POST /api/v1/deploy/gitlab-webhook (GitLabからの呼び出し)  │
│  ├── POST /api/v1/deploy/run/full (完全デプロイ実行)            │
│  └── POST /api/v1/deploy/run/n8n (n8nフローのみ実行)            │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
                        ┌───────────┴───────────┐
                        │                       │
                        ↓                       ↓
              ┌──────────────┐        ┌──────────────┐
              │   Jenkins    │        │  n8n Flows   │
              │              │        │              │
              │ - ビルド実行  │        │ - Flow1      │
              │ - テスト実行  │        │ - Flow2      │
              │              │        │ - Flow3      │
              └──────────────┘        └──────────────┘
```

## 処理フロー

### 1. Excel処理フロー（Flask App）

```
ユーザー → Flask App (http://localhost:5000)
           │
           ├── Excelファイルアップロード
           │
           ↓
     [excel_to_index_processor.py]
           │
           ├── Steps 1-9: Excel処理
           │   └── JSONファイル生成 (output_data/*.json)
           │
           └── Step 10: Git/デプロイ
               ├── GitLab Commits API
               │   └── index/contents/*.json にコミット（100件/回バッチ）
               │
               ├── タグ作成
               │   └── NNN-YYYYMMDD 形式のタグを作成
               │
               ├── deploy_config.json保存
               │   └── POST http://localhost:8085/api/v1/deploy/config
               │
               ├── Jenkins実行
               │   ├── ビルドトリガー
               │   ├── キュー待機
               │   ├── ビルド実行
               │   └── 結果確認 (SUCCESS/UNSTABLE)
               │
               └── ファイルクリーンアップ
                   └── output_data/*.json を削除
```

### 2. n8nフロー実行（FastAPI経由）

```
ユーザー → POST http://localhost:8085/api/v1/deploy/run/n8n
           │
           ├── deploy_config.json から設定読み込み
           │
           ├── 環境リスト取得 (WORK_ENVS)
           │   └── ["dv0", "dv1", "itb", "uat", "pda", "pdb"]
           │
           └── 各環境に対して順次実行
               ├── Flow1 実行
               │   └── status != 200 なら終了
               │
               ├── Flow2 実行
               │   └── status != 200 なら終了
               │
               └── Flow3 実行
```

## 使用方法

### 前提条件

1. Python 3.9以上がインストールされていること
2. 必要なパッケージがインストールされていること
3. `.env` ファイルが設定されていること（[環境変数設定](#環境変数設定)参照）

### 1. サーバー起動

#### Flask App起動

```bash
cd flask_app
python app.py
```

Flask Appは `http://localhost:5000` で起動します。

#### FastAPI起動

```bash
cd app
uvicorn main:app --host 0.0.0.0 --port 8085
```

FastAPIは `http://localhost:8085` で起動します。

### 2. Excel処理の実行

1. ブラウザで `http://localhost:5000` にアクセス
2. Excelファイルをアップロード
3. 処理が自動的に実行されます
   - Steps 1-9: Excel処理
   - Step 10: Git操作、タグ作成、Jenkins実行

### 3. n8nフロー実行

Excel処理が完了した後、n8nフローを実行する場合：

```bash
curl -X POST http://localhost:8085/api/v1/deploy/run/n8n \
  -H "Content-Type: application/json" \
  -d '{
    "index_name_short": "your_index_name"
  }'
```

または、GitLabからのWebhookで自動実行：

```bash
# GitLabのWebhook設定でURLを登録
POST http://your-server:8085/api/v1/deploy/gitlab-webhook
```

## 環境変数設定

詳細は [README_ENV_SETUP.md](README_ENV_SETUP.md) を参照してください。

### 最小限の必須設定

```bash
# GitLab
API_BASE=https://gitlab.com/api/v4
PROJECT_ID=your_project_id
GIT_TOKEN=your_token
GIT_USER=your_username

# FastAPI
FASTAPI_BASE_URL=http://localhost:8085

# Jenkins
JENKINS_BASE=https://jenkins.example.com
JENKINS_JOB=your/job/path
JENKINS_USER=your_user
JENKINS_TOKEN=your_jenkins_token
JENKINS_JOB_TOKEN=your_job_token

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_API_ENGINE_EMBEDDING=text-embedding-ada-002
AZURE_OPENAI_API_ENGINE_GPT=gpt-4
AOAI_ITB_API_KEY=your_itb_key
AOAI_ITB_ENDPOINT=https://your-itb-resource.openai.azure.com/

# Index
INDEX_NAME_SHORT=your_index_name
```

## 主要な変更点（旧バージョンとの比較）

### 旧アーキテクチャ

```
deploy_automation_trigger.py
  ↓
ブランチ作成 → マージリクエスト → 手動マージ待機
  ↓
deploy_automation.py
  ↓
タグ作成 → Jenkins → n8n
```

### 新アーキテクチャ

```
Flask App (excel_to_index_processor.py)
  ↓
Steps 1-9: Excel処理
  ↓
Step 10: 直接mainへコミット → タグ作成 → Jenkins
  ↓
FastAPI (/run/n8n)
  ↓
環境リストに対して順次n8nフロー実行
```

### 主な改善点

1. **ブランチ不要**: 直接mainブランチにコミット
2. **マージリクエスト不要**: 手動マージ待機が不要
3. **統合フロー**: Excel処理からデプロイまで一貫したフロー
4. **バッチコミット**: 大量ファイルを100件/回でバッチ処理
5. **環境変数管理**: work_envをコード内リストで管理
6. **自動ロールバック**: エラー時に作成されたすべてのコミットを自動revert
   - 100個のコミットでも自動的に逆順revert
   - Revert進捗のログ記録（10コミットごと）
   - Revert失敗時は手動対応用のコミットSHA一覧を表示

## ファイル構成

```
aimai_detect/
├── .env                              # 環境変数設定
├── README_ENV_SETUP.md               # 環境変数設定ガイド
├── README_DEPLOY_ARCHITECTURE.md     # このファイル
│
├── flask_app/                        # Flask App
│   ├── app.py                        # Flask Appメイン
│   ├── processor_new.py              # バックグラウンド処理
│   ├── excel_to_index_processor.py   # Excel処理 + Step10
│   ├── EXCEL_PROCESSOR_README.md     # Excel処理ガイド
│   └── data/
│       ├── input_data/               # 入力Excelファイル
│       ├── output_data/              # 出力JSONファイル（処理後削除）
│       └── output_index_list/        # インデックス化データ一覧
│
├── app/                              # FastAPI
│   ├── main.py                       # FastAPIメイン
│   ├── api/
│   │   └── deploy_api.py            # デプロイAPI
│   ├── services/
│   │   ├── deploy_service.py        # デプロイサービス
│   │   ├── deploy_config_store.py   # 設定ストア
│   │   └── deploy_env.py            # 環境変数解決
│   └── schemas/
│       └── deploy.py                # スキーマ定義
│
├── deploy_automation.py              # レガシーコード（参考用）
└── deploy_automation_trigger.py      # 非推奨（削除予定）
```

## トラブルシューティング

### Excel処理が失敗する

**症状**: Flask Appでアップロード後にエラー

**確認事項**:
1. `.env` ファイルが正しく設定されているか
2. Azure OpenAIの認証情報が正しいか
3. `flask_app/logs/` のログファイルを確認

### Git操作が失敗する

**症状**: Step10でGitLabへのコミットが失敗

**確認事項**:
1. `GIT_TOKEN` が有効か（有効期限を確認）
2. `PROJECT_ID` が正しいか
3. GitLabリポジトリへの書き込み権限があるか
4. プロキシ設定が必要な場合は `HTTP_PROXY` を設定

### Jenkins実行が失敗する

**症状**: Step10でJenkins実行が失敗

**確認事項**:
1. `JENKINS_USER` と `JENKINS_TOKEN` が正しいか
2. `JENKINS_JOB` のパスが正しいか
3. `JENKINS_JOB_TOKEN` が設定されているか
4. Jenkinsサーバーにアクセスできるか

### FastAPI接続エラー

**症状**: deploy_config.json保存が失敗

**確認事項**:
1. FastAPIサーバーが起動しているか
2. ポート8085が使用可能か
3. `FASTAPI_BASE_URL` が正しいか

### ファイルが大量にある場合

**症状**: コミットに時間がかかる

**対策**:
- バッチサイズは100件/回で設定済み
- GitLab APIのレート制限に注意
- 必要に応じて `BATCH_SIZE` を調整可能

### エラー時に自動ロールバックが実行される

**症状**: エラー発生後、コミットが自動的にrevertされる

**確認事項**:
1. ログに「ロールバック」メッセージが表示されているか確認
2. `reverted_count` で何個のコミットがrevertされたか確認
3. GitLabのコミット履歴でrevertコミットを確認

**注意点**:
- Revertは新しいコミットから古いコミットへ逆順に実行されます
- 各revertは新しいコミットとして記録されます（履歴は残ります）
- 自動revertが失敗した場合は、ログに表示されるコミットSHAを手動でrevertしてください

### ロールバックが途中で失敗する

**症状**: 一部のコミットはrevertされたが、一部は失敗

**確認事項**:
1. ログで「手動対応必要」メッセージを確認
2. 失敗したコミットのSHAを確認
3. GitLabのコミット履歴で、どこまでrevertされたか確認

**対策**:
1. GitLabのWebインターフェースにアクセス
2. 該当コミットを手動でrevert
3. または、GitLab APIを直接使用してrevert

```bash
# 手動revert例
curl -X POST "https://gitlab.com/api/v4/projects/{PROJECT_ID}/repository/commits/{COMMIT_SHA}/revert" \
  -H "PRIVATE-TOKEN: {YOUR_TOKEN}" \
  -d "branch=main"
```

## よくある質問

### Q1. Excel処理だけ実行してGit操作をスキップできますか？

A. はい、可能です。`process_excel_to_index()` 関数の `enable_git_deploy` パラメータを `False` にしてください。

```python
result = process_excel_to_index(
    input_dir=INPUT_DIR,
    output_dir=OUTPUT_DIR,
    callback=callback,
    index_name_short=index_name_short,
    enable_git_deploy=False  # Git操作をスキップ
)
```

### Q2. n8nフローだけを実行できますか？

A. はい、FastAPIの `/run/n8n` エンドポイントを使用してください。

```bash
curl -X POST http://localhost:8085/api/v1/deploy/run/n8n \
  -H "Content-Type: application/json" \
  -d '{"index_name_short": "your_index"}'
```

### Q3. 環境リストを変更するには？

A. `.env` ファイルに `WORK_ENVS` を追加してください（将来実装予定）。

現在はハードコードされているため、コードの修正が必要です。

### Q4. タグの命名規則は？

A. `NNN-YYYYMMDD` 形式です。
- `NNN`: 連番（001, 002, ...）
- `YYYYMMDD`: 作成日（例: 20241113）

例: `001-20241113`, `002-20241113`

### Q5. ロールバックはどうすればいいですか？

A. エラー時は自動的に以下の処理が実行されます：

**自動ロールバック機能**:
1. Step10でバッチコミットを実行する際、すべてのコミットSHAを記録
2. エラー発生時、作成されたすべてのコミットを逆順でrevert
   - 例: 100個のコミットが作成された場合、新しいコミットから古いコミットへ順にrevert
3. Revert処理の進捗をログに記録（10コミットごと）
4. ファイルクリーンアップを実行

**ロールバックの仕組み**:
```
正常時:
Commit 1 → Commit 2 → ... → Commit 100 → Tag作成 → Jenkins実行

エラー時（例: Jenkins実行失敗）:
Commit 1 → Commit 2 → ... → Commit 100 → [エラー発生]
                                          ↓
                         Revert 100 → Revert 99 → ... → Revert 1
```

**手動ロールバックが必要な場合**:
- 自動revert処理が失敗した場合
- ログに表示される「手動対応必要」メッセージを確認
- GitLabのWebインターフェースから該当コミット（SHA表示）をrevert

**ロールバック結果の確認**:
処理結果の`reverted`フィールドで確認可能：
```json
{
  "reverted": true,
  "reverted_count": 100,
  "error": "Jenkins実行が失敗しました: FAILURE"
}
```

## 関連ドキュメント

- [Excel Processor README](flask_app/EXCEL_PROCESSOR_README.md) - Excel処理の詳細
- [環境変数設定ガイド](README_ENV_SETUP.md) - 環境変数の設定方法
- [Deploy Automation](deploy_automation.md) - レガシーコードの説明

## サポート

問題が発生した場合は、以下の情報を含めて報告してください：

1. エラーメッセージ
2. `flask_app/logs/` のログファイル
3. 実行時の環境変数設定（機密情報は除く）
4. 実行したコマンドまたは操作

