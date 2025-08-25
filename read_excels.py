import os
import pandas as pd
import glob
from typing import Union

def read_all_excel_files(folder_path: str, 
                        sheet_name: Union[str, int] = 0,
                        file_pattern: str = "*.xlsx") -> pd.DataFrame:
    """
    指定されたフォルダ内のすべてのExcelファイルを読み込み、1つのDataFrameに結合する
    
    Parameters:
    -----------
    folder_path : str
        Excelファイルが格納されているフォルダのパス
    sheet_name : str or int, default 0
        読み込むシート名またはインデックス
    file_pattern : str, default "*.xlsx"
        検索するファイルのパターン（"*.xlsx", "*.xls", "*.xl*"など）
    
    Returns:
    --------
    pd.DataFrame
        結合されたDataFrame
    """
    
    # フォルダが存在するかチェック
    if not os.path.exists(folder_path):
        raise ValueError(f"指定されたフォルダが存在しません: {folder_path}")
    
    # Excelファイルのパスを取得
    excel_files = glob.glob(os.path.join(folder_path, file_pattern))
    
    # .xlsファイルも含める場合
    if file_pattern == "*.xlsx":
        excel_files.extend(glob.glob(os.path.join(folder_path, "*.xls")))
    
    if not excel_files:
        print(f"指定されたフォルダにExcelファイルが見つかりませんでした: {folder_path}")
        return pd.DataFrame()
    
    all_dataframes = []
    
    print(f"{len(excel_files)}個のExcelファイルが見つかりました:")
    
    for file_path in excel_files:
        filename = os.path.basename(file_path)
        
        try:
            print(f"読み込み中: {filename}")
            
            # Excelファイルを読み込み
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # ファイル名カラムを追加
            df['ファイル名'] = filename
            
            all_dataframes.append(df)
                    
        except Exception as e:
            print(f"エラー: {filename} の読み込みに失敗しました - {str(e)}")
            continue
    
    if all_dataframes:
        combined_df = pd.concat(all_dataframes, ignore_index=True)
        print(f"合計 {len(combined_df)} 行のデータを結合しました")
        return combined_df
    else:
        print("読み込みに成功したファイルがありませんでした")
        return pd.DataFrame()

# 使用例
if __name__ == "__main__":
    # フォルダパスを指定
    folder_path = "./data"  # フォルダパスを指定
    
    print("=== Excelファイル結合読み込み ===")
    try:
        # デフォルト（最初のシート）で読み込み
        combined_df = read_all_excel_files(folder_path)
        print(f"結合されたデータ: {combined_df.shape[0]}行 x {combined_df.shape[1]}列")
        print(combined_df.head())
        
        # 特定のシート名で読み込み
        # combined_df = read_all_excel_files(folder_path, sheet_name="Sheet1")
        
        # 特定のシートインデックスで読み込み
        # combined_df = read_all_excel_files(folder_path, sheet_name=1)
        
    except Exception as e:
        print(f"エラー: {e}")
