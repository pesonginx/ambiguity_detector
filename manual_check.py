#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LINEヘルプセンター監視スクリプト（手動実行版）
指定されたURLの内容を手動でチェックし、変更があった場合にスクレイピングしてマークダウン形式で出力
"""

import json
import logging
import sys
from pathlib import Path
from line_help_monitor import LineHelpMonitor

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('line_help_manual.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
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

def show_help():
    """ヘルプメッセージを表示"""
    print("""
LINEヘルプセンター監視スクリプト（手動実行版）

使用方法:
    python manual_check.py [オプション]

オプション:
    --help, -h          このヘルプメッセージを表示
    --force, -f         強制的に現在のコンテンツを保存（変更チェックをスキップ）
    --list, -l          保存されたファイルの一覧を表示
    --clear, -c         保存された状態をクリア（初回実行状態に戻す）

例:
    python manual_check.py          # 通常のチェック実行
    python manual_check.py --force  # 強制保存
    python manual_check.py --list   # ファイル一覧表示
    python manual_check.py --clear  # 状態クリア
""")

def list_files(output_dir):
    """保存されたファイルの一覧を表示"""
    output_path = Path(output_dir)
    if not output_path.exists():
        print("出力ディレクトリが存在しません。")
        return
    
    print(f"\n保存されたファイル一覧 ({output_dir}):")
    print("-" * 50)
    
    # ファイルタイプ別に分類
    file_types = {
        'current': [],
        'previous': [],
        'diff': [],
        'state': []
    }
    
    for file in output_path.glob("*"):
        if file.name.startswith("current_content_"):
            file_types['current'].append(file)
        elif file.name.startswith("previous_content_"):
            file_types['previous'].append(file)
        elif file.name.startswith("diff_"):
            file_types['diff'].append(file)
        elif file.name == "monitor_state.json":
            file_types['state'].append(file)
    
    for file_type, files in file_types.items():
        if files:
            print(f"\n{file_type.upper()} ファイル:")
            for file in sorted(files, reverse=True):
                size = file.stat().st_size
                print(f"  {file.name} ({size:,} bytes)")
    
    if not any(file_types.values()):
        print("保存されたファイルがありません。")

def clear_state(output_dir):
    """保存された状態をクリア"""
    output_path = Path(output_dir)
    state_file = output_path / "monitor_state.json"
    
    if state_file.exists():
        state_file.unlink()
        print(f"状態ファイルを削除しました: {state_file}")
    else:
        print("状態ファイルが見つかりません。")
    
    print("状態がクリアされました。次回実行時は初回実行として扱われます。")

def force_save(monitor):
    """強制的に現在のコンテンツを保存"""
    logging.info("強制保存モードで実行します")
    
    current_content = monitor.fetch_content()
    if current_content is None:
        logging.error("コンテンツの取得に失敗しました")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_filename = monitor.output_dir / f"current_content_{timestamp}.md"
    
    parsed_current = monitor.parse_content(current_content)
    markdown_current = monitor.content_to_markdown(parsed_current)
    
    with open(current_filename, 'w', encoding='utf-8') as f:
        f.write(markdown_current)
    
    logging.info(f"強制保存完了: {current_filename}")
    print(f"コンテンツを強制保存しました: {current_filename}")
    return True

def main():
    """メイン関数"""
    # コマンドライン引数の処理
    args = sys.argv[1:]
    
    if '--help' in args or '-h' in args:
        show_help()
        return
    
    config = load_config()
    if config is None:
        logging.error("設定の読み込みに失敗しました。プログラムを終了します。")
        return
    
    monitor = LineHelpMonitor(
        config["url"], 
        config["check_interval_minutes"],
        config.get("download_images", False)
    )
    
    if '--list' in args or '-l' in args:
        list_files(config["output_directory"])
        return
    
    if '--clear' in args or '-c' in args:
        clear_state(config["output_directory"])
        return
    
    if '--force' in args or '-f' in args:
        from datetime import datetime
        success = force_save(monitor)
        if success:
            print("強制保存が完了しました。")
        else:
            print("強制保存に失敗しました。")
        return
    
    # 通常の手動チェック実行
    print("LINEヘルプセンターの手動チェックを開始します...")
    print(f"URL: {config['url']}")
    print(f"出力ディレクトリ: {config['output_directory']}")
    print("-" * 50)
    
    try:
        changed = monitor.manual_check()
        
        if changed:
            print("\n✅ 変更が検出されました！")
            print("詳細はログファイルと出力ディレクトリを確認してください。")
        else:
            print("\nℹ️  変更は検出されませんでした。")
            print("現在のコンテンツは保存されました。")
        
        print(f"\n出力ディレクトリ: {monitor.output_dir}")
        
    except KeyboardInterrupt:
        print("\n\nユーザーによって中断されました。")
    except Exception as e:
        logging.error(f"実行中にエラーが発生: {e}")
        print(f"\n❌ エラーが発生しました: {e}")

if __name__ == "__main__":
    main() 