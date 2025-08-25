#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LINEヘルプセンター監視スクリプトのテスト用
一度だけ実行して動作確認を行います
"""

import json
import logging
from pathlib import Path
from line_help_monitor import LineHelpMonitor

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def load_config():
    """設定ファイルを読み込み"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning("config.jsonが見つかりません。デフォルト設定を使用します。")
        return {
            "url": "https://help.line.me/line/smartphone/categoryId/20007850/3/pc?utm_term=help&utm_campaign=contentsId20000367_contentsId10002423&utm_medium=messaging&lang=ja&utm_source=help&contentId=20007005",
            "check_interval_minutes": 30,
            "output_directory": "line_help_output",
            "log_file": "line_help_monitor.log",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "timeout_seconds": 30,
            "max_retries": 3
        }
    except Exception as e:
        logging.error(f"設定ファイルの読み込みに失敗: {e}")
        return None

def main():
    """テスト実行"""
    print("LINEヘルプセンター監視スクリプトのテストを開始します...")
    
    config = load_config()
    if config is None:
        print("設定の読み込みに失敗しました。")
        return
    
    # 監視オブジェクトを作成
    monitor = LineHelpMonitor(config["url"], config["check_interval_minutes"])
    
    # 一度だけチェックを実行
    print(f"URL: {config['url']}")
    print("コンテンツをチェック中...")
    
    monitor.check_for_changes()
    
    print("テスト完了！")
    print(f"出力ディレクトリ: {monitor.output_dir}")
    
    # 出力ファイルの一覧を表示
    if monitor.output_dir.exists():
        files = list(monitor.output_dir.glob("*.md"))
        if files:
            print("\n作成されたマークダウンファイル:")
            for file in files:
                print(f"  - {file.name}")
        else:
            print("\n変更は検出されませんでした。")

if __name__ == "__main__":
    main() 