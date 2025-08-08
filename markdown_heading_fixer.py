import os
import re
from pathlib import Path

def fix_markdown_headings(directory_path=".", backup=True):
    """
    指定されたディレクトリ配下のマークダウンファイルの見出しレベルを下げる関数
    
    Args:
        directory_path (str): 処理対象のディレクトリパス（デフォルト: カレントディレクトリ）
        backup (bool): バックアップファイルを作成するかどうか（デフォルト: True）
    
    Returns:
        dict: 処理結果の辞書（処理したファイル数、変更した行数など）
    """
    results = {
        "processed_files": 0,
        "modified_files": 0,
        "total_changes": 0,
        "errors": []
    }
    
    # ディレクトリ内のすべての.mdファイルを検索
    md_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith('.md'):
                md_files.append(os.path.join(root, file))
    
    print(f"見つかったマークダウンファイル: {len(md_files)}個")
    
    for file_path in md_files:
        try:
            print(f"処理中: {file_path}")
            
            # ファイルを読み込み
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            changes_made = 0
            
            # ## を # に変更（先に処理）
            content, count1 = re.subn(r'^##\s+', '# ', content, flags=re.MULTILINE)
            changes_made += count1
            
            # ### を ## に変更（後で処理）
            content, count2 = re.subn(r'^###\s+', '## ', content, flags=re.MULTILINE)
            changes_made += count2
            
            # 変更があった場合のみファイルを更新
            if changes_made > 0:
                # バックアップを作成
                if backup:
                    backup_path = file_path + '.backup'
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(original_content)
                    print(f"  バックアップ作成: {backup_path}")
                
                # ファイルを更新
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                results["modified_files"] += 1
                results["total_changes"] += changes_made
                print(f"  変更完了: {changes_made}箇所の見出しレベルを下げました")
            else:
                print(f"  変更なし")
            
            results["processed_files"] += 1
            
        except Exception as e:
            error_msg = f"エラー ({file_path}): {str(e)}"
            results["errors"].append(error_msg)
            print(f"  {error_msg}")
    
    return results

def preview_changes(directory_path="."):
    """
    変更内容をプレビューする関数（実際にはファイルを変更しない）
    
    Args:
        directory_path (str): 処理対象のディレクトリパス（デフォルト: カレントディレクトリ）
    
    Returns:
        dict: プレビュー結果の辞書
    """
    results = {
        "processed_files": 0,
        "files_with_changes": 0,
        "total_changes": 0,
        "preview": []
    }
    
    # ディレクトリ内のすべての.mdファイルを検索
    md_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith('.md'):
                md_files.append(os.path.join(root, file))
    
    print(f"プレビュー対象のマークダウンファイル: {len(md_files)}個")
    
    for file_path in md_files:
        try:
            # ファイルを読み込み
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            changes_made = 0
            preview_lines = []
            
            # 行ごとに処理して変更箇所を特定
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                original_line = line
                modified_line = line
                
                # ## を # に変更（先に処理）
                if re.match(r'^##\s+', line):
                    modified_line = re.sub(r'^##\s+', '# ', line)
                    changes_made += 1
                    preview_lines.append(f"  行 {i}: ## → #")
                
                # ### を ## に変更（後で処理）
                elif re.match(r'^###\s+', line):
                    modified_line = re.sub(r'^###\s+', '## ', line)
                    changes_made += 1
                    preview_lines.append(f"  行 {i}: ### → ##")
            
            if changes_made > 0:
                results["files_with_changes"] += 1
                results["total_changes"] += changes_made
                results["preview"].append({
                    "file": file_path,
                    "changes": changes_made,
                    "details": preview_lines
                })
                print(f"変更予定: {file_path} ({changes_made}箇所)")
                for detail in preview_lines:
                    print(f"  {detail}")
            
            results["processed_files"] += 1
            
        except Exception as e:
            print(f"エラー ({file_path}): {str(e)}")
    
    return results

if __name__ == "__main__":
    print("マークダウンファイル見出しレベル修正ツール")
    print("=" * 50)
    
    # プレビュー実行
    print("\n1. 変更内容のプレビュー:")
    preview_results = preview_changes()
    
    if preview_results["files_with_changes"] == 0:
        print("\n変更対象のファイルが見つかりませんでした。")
    else:
        print(f"\nプレビュー結果:")
        print(f"  処理対象ファイル: {preview_results['processed_files']}個")
        print(f"  変更予定ファイル: {preview_results['files_with_changes']}個")
        print(f"  総変更箇所: {preview_results['total_changes']}箇所")
        
        # 実際の変更を実行するか確認
        response = input("\n実際に変更を実行しますか？ (y/N): ").strip().lower()
        
        if response in ['y', 'yes']:
            print("\n2. 実際の変更を実行:")
            fix_results = fix_markdown_headings()
            
            print(f"\n実行結果:")
            print(f"  処理したファイル: {fix_results['processed_files']}個")
            print(f"  変更したファイル: {fix_results['modified_files']}個")
            print(f"  総変更箇所: {fix_results['total_changes']}箇所")
            
            if fix_results['errors']:
                print(f"\nエラー:")
                for error in fix_results['errors']:
                    print(f"  {error}")
        else:
            print("変更をキャンセルしました。")
