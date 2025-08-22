import pandas as pd
import re
import os
from pathlib import Path
from typing import Dict, List, Tuple


def load_icon_mapping(excel_file_path: str) -> Dict[str, str]:
    """
    Excelファイルからアイコンファイル名とアイコン説明のマッピングを読み込む
    
    Args:
        excel_file_path (str): アイコン一覧が格納されたExcelファイルのパス
        
    Returns:
        Dict[str, str]: アイコンファイル名をキー、アイコン説明を値とする辞書
        
    Raises:
        FileNotFoundError: 指定されたExcelファイルが見つからない場合
        ValueError: 必要な列が存在しない場合
    """
    try:
        # Excelファイルを読み込み
        df = pd.read_excel(excel_file_path)
        
        # 必要な列が存在するかチェック
        required_columns = ["アイコンファイル名", "アイコン説明"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"必要な列が見つかりません: {missing_columns}")
        
        # アイコンファイル名とアイコン説明のマッピングを作成
        icon_mapping = {}
        for _, row in df.iterrows():
            icon_filename = str(row["アイコンファイル名"]).strip()
            icon_description = str(row["アイコン説明"]).strip()
            
            # 空の値はスキップ
            if icon_filename and icon_description:
                # .png拡張子がある場合はそのまま、ない場合は追加
                if not icon_filename.endswith('.png'):
                    icon_filename += '.png'
                icon_mapping[icon_filename] = icon_description
        
        return icon_mapping
        
    except FileNotFoundError:
        raise FileNotFoundError(f"指定されたExcelファイルが見つかりません: {excel_file_path}")
    except Exception as e:
        raise Exception(f"Excelファイルの読み込み中にエラーが発生しました: {str(e)}")


def replace_icon_references_in_markdown(markdown_content: str, icon_mapping: Dict[str, str]) -> str:
    """
    マークダウンの内容でアイコン参照をアイコン説明に置換する
    
    Args:
        markdown_content (str): 処理対象のマークダウン内容
        icon_mapping (Dict[str, str]): アイコンファイル名とアイコン説明のマッピング
        
    Returns:
        str: 置換後のマークダウン内容
    """
    # 正規表現パターン: ![任意の文字列](http*/アイコンファイル名)
    # キャプチャグループを使用して置換対象を特定
    pattern = r'!\[([^\]]*)\]\([^)]*/([^)]+)\)'
    
    def replacement_function(match):
        alt_text = match.group(1)  # ![と]の間の文字列
        icon_filename = match.group(2)  # (と)の間の最後の部分（ファイル名）
        
        # アイコンファイル名がマッピングに存在するかチェック
        if icon_filename in icon_mapping:
            return icon_mapping[icon_filename]
        else:
            # マッピングに存在しない場合は元の文字列をそのまま返す
            return match.group(0)
    
    # 置換を実行
    replaced_content = re.sub(pattern, replacement_function, markdown_content)
    
    return replaced_content


def process_markdown_file(file_path: str, icon_mapping: Dict[str, str], 
                         backup: bool = True) -> bool:
    """
    個別のマークダウンファイルを処理する
    
    Args:
        file_path (str): 処理対象のマークダウンファイルのパス
        icon_mapping (Dict[str, str]): アイコンファイル名とアイコン説明のマッピング
        backup (bool): バックアップファイルを作成するかどうか
        
    Returns:
        bool: 処理が成功したかどうか
    """
    try:
        # ファイルを読み込み
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # アイコン参照を置換
        replaced_content = replace_icon_references_in_markdown(content, icon_mapping)
        
        # 内容が変更された場合のみ処理
        if content != replaced_content:
            # バックアップを作成
            if backup:
                backup_path = file_path + '.backup'
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            # 置換後の内容を書き込み
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(replaced_content)
            
            return True
        else:
            return False
            
    except Exception as e:
        print(f"ファイル {file_path} の処理中にエラーが発生しました: {str(e)}")
        return False


def process_markdown_folder(folder_path: str, icon_mapping: Dict[str, str], 
                          backup: bool = True) -> Tuple[int, int]:
    """
    フォルダ内のすべてのマークダウンファイルを処理する
    
    Args:
        folder_path (str): 処理対象のフォルダパス
        icon_mapping (Dict[str, str]): アイコンファイル名とアイコン説明のマッピング
        backup (bool): バックアップファイルを作成するかどうか
        
    Returns:
        Tuple[int, int]: (処理されたファイル数, 変更されたファイル数)
    """
    folder_path = Path(folder_path)
    
    if not folder_path.exists():
        raise FileNotFoundError(f"指定されたフォルダが見つかりません: {folder_path}")
    
    if not folder_path.is_dir():
        raise ValueError(f"指定されたパスはフォルダではありません: {folder_path}")
    
    # マークダウンファイルを検索
    markdown_files = list(folder_path.rglob("*.md"))
    
    processed_count = 0
    changed_count = 0
    
    for file_path in markdown_files:
        try:
            if process_markdown_file(str(file_path), icon_mapping, backup):
                changed_count += 1
            processed_count += 1
        except Exception as e:
            print(f"ファイル {file_path} の処理に失敗しました: {str(e)}")
    
    return processed_count, changed_count


def main():
    """
    メイン処理関数（使用例）
    """
    # 設定
    excel_file_path = "icon_list.xlsx"  # Excelファイルのパス
    markdown_folder_path = "."  # マークダウンファイルが格納されたフォルダのパス
    
    try:
        # アイコン一覧を読み込み
        print("アイコン一覧を読み込んでいます...")
        icon_mapping = load_icon_mapping(excel_file_path)
        print(f"アイコン一覧を読み込みました: {len(icon_mapping)}件")
        
        # マークダウンファイルを処理
        print("マークダウンファイルを処理しています...")
        processed_count, changed_count = process_markdown_folder(
            markdown_folder_path, icon_mapping, backup=True
        )
        
        print(f"処理完了: {processed_count}ファイル処理, {changed_count}ファイル変更")
        
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")


if __name__ == "__main__":
    main()
