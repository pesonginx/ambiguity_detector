# LINEヘルプセンター監視スクリプト（手動実行版）

このスクリプトは、指定されたLINEヘルプセンターのウェブページを手動でチェックし、内容に変更があった場合に自動的にスクレイピングしてマークダウン形式で出力します。

## 主な特徴

- **手動実行**: スケジューラーを使わず、人間が手動で実行
- **前回コンテンツ保存**: 変更があった場合、前回のコンテンツも保存
- **現在コンテンツ保存**: 毎回実行時に現在のコンテンツを保存
- **画像・表情報対応**: 画像やメタ情報を適切にマークダウン形式で出力
- **画像ダウンロード**: オプションで画像をローカルに保存可能
- **柔軟なオプション**: 強制保存、ファイル一覧表示、状態クリアなどの機能

## 必要な環境

- Python 3.7以上
- 必要なパッケージ（requirements.txtに記載）

## インストール

1. 依存関係をインストール:
```bash
pip install -r requirements.txt
```

## 使用方法

### 基本的な使用方法

```bash
python manual_check.py
```

### オプション

#### ヘルプ表示
```bash
python manual_check.py --help
# または
python manual_check.py -h
```

#### 強制保存（変更チェックをスキップ）
```bash
python manual_check.py --force
# または
python manual_check.py -f
```

#### 保存されたファイルの一覧表示
```bash
python manual_check.py --list
# または
python manual_check.py -l
```

#### 状態クリア（初回実行状態に戻す）
```bash
python manual_check.py --clear
# または
python manual_check.py -c
```

## 出力ファイル

### 現在のコンテンツファイル
毎回実行時に作成されます：
- `current_content_YYYYMMDD_HHMMSS.md`: 現在のコンテンツのマークダウン形式

### 前回のコンテンツファイル
変更が検出された場合に作成されます：
- `previous_content_YYYYMMDD_HHMMSS.md`: 前回のコンテンツのマークダウン形式

### 差分情報ファイル
変更が検出された場合に作成されます：
- `diff_YYYYMMDD_HHMMSS.txt`: 変更検出時の詳細情報

### 画像ファイル（download_images: trueの場合）
画像がダウンロードされる場合：
- `images/`: ダウンロードされた画像の保存ディレクトリ
- 画像ファイル名: `{元ファイル名}_{タイムスタンプ}.{拡張子}`

### 状態ファイル
- `monitor_state.json`: 前回の監視状態を保存

### ログファイル
- `line_help_manual.log`: 詳細なログ情報

## 実行例

### 初回実行
```bash
$ python manual_check.py
LINEヘルプセンターの手動チェックを開始します...
URL: https://help.line.me/...
出力ディレクトリ: line_help_output
--------------------------------------------------
2024-01-01 12:00:00 - INFO - LINEヘルプセンターの手動チェックを開始: https://help.line.me/...
2024-01-01 12:00:01 - INFO - 現在のコンテンツを保存しました: line_help_output/current_content_20240101_120001.md
2024-01-01 12:00:01 - INFO - 初回実行のため、現在のコンテンツを基準として保存します

ℹ️  変更は検出されませんでした。
現在のコンテンツは保存されました。

出力ディレクトリ: line_help_output
```

### 変更が検出された場合
```bash
$ python manual_check.py
LINEヘルプセンターの手動チェックを開始します...
URL: https://help.line.me/...
出力ディレクトリ: line_help_output
--------------------------------------------------
2024-01-01 12:30:00 - INFO - LINEヘルプセンターの手動チェックを開始: https://help.line.me/...
2024-01-01 12:30:01 - INFO - 現在のコンテンツを保存しました: line_help_output/current_content_20240101_123001.md
2024-01-01 12:30:01 - INFO - コンテンツの変更を検出しました！
2024-01-01 12:30:01 - INFO - 前回のコンテンツを保存しました: line_help_output/previous_content_20240101_123001.md
2024-01-01 12:30:01 - INFO - 差分情報を保存しました: line_help_output/diff_20240101_123001.txt

✅ 変更が検出されました！
詳細はログファイルと出力ディレクトリを確認してください。

出力ディレクトリ: line_help_output
```

### ファイル一覧表示
```bash
$ python manual_check.py --list

保存されたファイル一覧 (line_help_output):
--------------------------------------------------

CURRENT ファイル:
  current_content_20240101_123001.md (15,234 bytes)
  current_content_20240101_120001.md (15,123 bytes)

PREVIOUS ファイル:
  previous_content_20240101_123001.md (15,123 bytes)

DIFF ファイル:
  diff_20240101_123001.txt (156 bytes)

STATE ファイル:
  monitor_state.json (245 bytes)
```

## マークダウン出力の形式

出力されるマークダウンファイルには以下の情報が含まれます：

```markdown
# ページタイトル

**最終更新**: 2024-01-01T12:00:00
**監視URL**: https://help.line.me/...

## セクション1
セクションの内容...

### サブセクション
サブセクションの内容...

- リスト項目1
- リスト項目2
```

## 差分情報ファイルの内容

```txt
変更検出時刻: 2024-01-01T12:30:01.123456
前回ハッシュ: a1b2c3d4e5f6...
現在ハッシュ: f6e5d4c3b2a1...
URL: https://help.line.me/...
前回コンテンツファイル: line_help_output/previous_content_20240101_123001.md
現在コンテンツファイル: line_help_output/current_content_20240101_123001.md
```

## 設定のカスタマイズ

`config.json`ファイルを編集して設定を変更できます：

```json
{
  "url": "監視したいURL",
  "check_interval_minutes": 30,
  "output_directory": "line_help_output",
  "log_file": "line_help_monitor.log",
  "user_agent": "ブラウザのUser-Agent",
  "timeout_seconds": 30,
  "max_retries": 3,
  "download_images": false
}
```

### 設定項目の説明

- `url`: 監視するLINEヘルプセンターのURL
- `check_interval_minutes`: 監視間隔（分）
- `output_directory`: 出力ファイルの保存ディレクトリ
- `log_file`: ログファイルの名前
- `user_agent`: ブラウザとして認識されるためのUser-Agent
- `timeout_seconds`: ページ取得のタイムアウト時間
- `max_retries`: 失敗時の再試行回数
- `download_images`: 画像をローカルにダウンロードするかどうか（true/false）

## 画像・表情報の処理

### 画像の処理
- 画像は `![alt](src)` 形式でマークダウンに変換されます
- 相対URLは自動的に絶対URLに変換されます
- `download_images: true` に設定すると、画像がローカルにダウンロードされます

### 表情報の処理
- ページのメタ情報（description、keywords等）が「ページ情報」セクションに表示されます
- リンク、太字、斜体などのHTML要素も適切にマークダウン形式に変換されます

## トラブルシューティング

### よくある問題

1. **ページが取得できない**
   - ネットワーク接続を確認
   - URLが正しいか確認
   - サイトがアクセス可能か確認

2. **変更が検出されない**
   - 実際にページの内容が変更されているか確認
   - ログファイルでエラーがないか確認

3. **権限エラー**
   - 出力ディレクトリの書き込み権限を確認

### ログの確認

ログファイル（`line_help_manual.log`）を確認して、詳細なエラー情報を取得できます。

## 注意事項

- このスクリプトは教育・研究目的で作成されています
- ウェブサイトの利用規約を遵守してご利用ください
- 過度なアクセスは避けてください
- 取得したデータの取り扱いには十分ご注意ください

## ライセンス

このスクリプトはMITライセンスの下で提供されています。 