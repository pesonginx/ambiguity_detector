# 環境変数設定ガイド

このドキュメントでは、`excel_to_index_processor.py` のStep10（Git操作、タグ作成、Jenkins実行、デプロイ）に必要な環境変数について説明します。

## 必須環境変数

以下の環境変数を `.env` ファイルに設定してください。

### GitLab設定

```bash
# GitLab API Base URL
API_BASE=https://gitlab.com/api/v4

# GitLab Project ID
PROJECT_ID=your_project_id

# GitLab Personal Access Token
GIT_TOKEN=your_gitlab_token

# GitLab Username
GIT_USER=your_username

# 対象ブランチ（デフォルト: main）
BRANCH=main

# タグメッセージ（デフォルト: "auto tag"）
TAG_MESSAGE="auto tag"
```

### FastAPI設定

```bash
# FastAPI Base URL（デフォルト: http://localhost:8085）
FASTAPI_BASE_URL=http://localhost:8085
```

### Jenkins設定

```bash
# Jenkins Base URL
JENKINS_BASE=https://your-jenkins-server.com

# Jenkins Job Path（完全なジョブパスを指定）
JENKINS_JOB=your/job/path

# Jenkins認証情報
JENKINS_USER=your_jenkins_user
JENKINS_TOKEN=your_jenkins_api_token

# Jenkins Job Token（buildWithParameters用）
JENKINS_JOB_TOKEN=your_job_token
```

### Azure OpenAI設定

```bash
# Azure OpenAI Endpoint
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/

# Azure OpenAI API Key
AZURE_OPENAI_API_KEY=your_api_key

# Azure OpenAI Embedding Engine
AZURE_OPENAI_API_ENGINE_EMBEDDING=text-embedding-ada-002

# Azure OpenAI GPT Engine
AZURE_OPENAI_API_ENGINE_GPT=gpt-4

# Azure OpenAI ITB設定（キーワード抽出用）
AOAI_ITB_API_KEY=your_itb_api_key
AOAI_ITB_ENDPOINT=https://your-itb-resource.openai.azure.com/
```

### インデックス設定

```bash
# インデックス名（短縮形）
# 将来的にはFlask Appのフロントから指定可能にする予定
INDEX_NAME_SHORT=default_index
```

### プロキシ設定（必要に応じて）

```bash
# HTTP/HTTPS Proxy
HTTP_PROXY=http://proxy.example.com:8080
HTTPS_PROXY=https://proxy.example.com:8443

# No Proxy
NO_PROXY=localhost,127.0.0.1
```

### SSL検証設定

```bash
# SSL証明書検証（デフォルト: true）
VERIFY_SSL=true
```

## .envファイルの配置場所

`.env` ファイルは以下の場所に配置してください：

```
aimai_detect/
├── .env  ← ここに配置
├── flask_app/
│   ├── app.py
│   └── excel_to_index_processor.py
└── app/
    └── api/
        └── deploy_api.py
```

## 環境変数の読み込み順序

1. `flask_app/excel_to_index_processor.py` は親ディレクトリの `.env` を読み込みます
2. 各モジュールは `python-dotenv` を使用して環境変数を読み込みます

## 設定例

```bash
# .env ファイルの例

# GitLab
API_BASE=https://gitlab.com/api/v4
PROJECT_ID=12345678
GIT_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
GIT_USER=your_username
BRANCH=main
TAG_MESSAGE="auto deploy tag"

# FastAPI
FASTAPI_BASE_URL=http://localhost:8085

# Jenkins
JENKINS_BASE=https://jenkins.example.com
JENKINS_JOB=aimai-detect/deploy-job
JENKINS_USER=jenkins_user
JENKINS_TOKEN=11xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
JENKINS_JOB_TOKEN=your_job_token

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AZURE_OPENAI_API_ENGINE_EMBEDDING=text-embedding-ada-002
AZURE_OPENAI_API_ENGINE_GPT=gpt-4
AOAI_ITB_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AOAI_ITB_ENDPOINT=https://your-itb-resource.openai.azure.com/

# Index
INDEX_NAME_SHORT=my_index

# Proxy（必要に応じて）
HTTP_PROXY=http://proxy.example.com:8080
HTTPS_PROXY=https://proxy.example.com:8443
NO_PROXY=localhost,127.0.0.1

# SSL
VERIFY_SSL=true
```

## トラブルシューティング

### GitLab APIエラー

- `401 Unauthorized`: `GIT_TOKEN` が無効または期限切れ
- `404 Not Found`: `PROJECT_ID` が間違っている、またはアクセス権限がない

### Jenkins接続エラー

- `401 Unauthorized`: `JENKINS_USER` または `JENKINS_TOKEN` が無効
- `404 Not Found`: `JENKINS_JOB` のパスが間違っている

### FastAPI接続エラー

- `Connection refused`: FastAPIサーバーが起動していない（ポート8085を確認）
- `404 Not Found`: `FASTAPI_BASE_URL` が間違っている

### Azure OpenAIエラー

- `401 Unauthorized`: APIキーが無効
- `429 Too Many Requests`: レート制限に達している（しばらく待ってから再実行）

## 関連ドキュメント

- [Excel Processor README](flask_app/EXCEL_PROCESSOR_README.md)
- [Deploy API README](README_DEPLOY_API.md)
- [Deploy Automation README](deploy_automation.md)

