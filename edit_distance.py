import pandas as pd
import numpy as np
from Levenshtein import distance
import ast
from typing import List, Dict

def load_dictionary(file_path: str) -> List[str]:
    """
    辞書ファイルから単語リストを読み込む関数
    
    Args:
        file_path (str): 辞書ファイルのパス
        
    Returns:
        List[str]: 辞書の単語リスト
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"警告: 辞書ファイル {file_path} が見つかりません。空のリストを返します。")
        return []

def normalize_edit_distance(edit_distance: int, word_length: int) -> float:
    """
    文字数による編集距離の正規化を行う関数
    
    Args:
        edit_distance (int): 元の編集距離
        word_length (int): 単語の長さ
        
    Returns:
        float: 正規化された編集距離（0-1の範囲）
    """
    if word_length == 0:
        return 0.0
    
    # 編集距離を文字数で割って正規化
    normalized_distance = edit_distance / word_length
    
    # 0-1の範囲に収める（必要に応じて調整可能）
    return min(normalized_distance, 1.0)

def calculate_edit_distance_scores(keywords: List[str], dictionary: List[str]) -> float:
    """
    キーワードリストと辞書の間の編集距離スコアを計算する関数
    
    Args:
        keywords (List[str]): キーワードのリスト
        dictionary (List[str]): 辞書の単語リスト
        
    Returns:
        float: 編集距離スコア
    """
    if not keywords or not dictionary:
        return 0.0
    
    # 各キーワードと辞書の単語との最小編集距離を計算
    min_distances = []
    for keyword in keywords:
        # 各キーワードと辞書の単語との編集距離を計算
        distances = []
        for dict_word in dictionary:
            # 編集距離を計算
            raw_distance = distance(keyword, dict_word)
            # 文字数による正規化
            normalized_distance = normalize_edit_distance(raw_distance, len(keyword))
            distances.append(normalized_distance)
        
        # 最小の編集距離を記録
        min_distances.append(min(distances))
    
    # スコアの計算
    # 1. 平均編集距離
    avg_distance = np.mean(min_distances)
    # 2. 編集距離の分散
    distance_variance = np.var(min_distances)
    # 3. 大きな編集距離を持つキーワードの割合（正規化された距離が0.3以上のキーワード）
    high_distance_ratio = sum(1 for d in min_distances if d >= 0.3) / len(min_distances)
    
    # 総合スコアの計算（重み付けは調整可能）
    ambiguity_score = (avg_distance * 0.4 + distance_variance * 0.3 + high_distance_ratio * 0.3)
    
    return round(ambiguity_score, 3)

def main():
    # 入力Excelファイルの読み込み
    input_file = r"C:\ppg\aimai_detect\input.xlsx"
    df = pd.read_excel(input_file, sheet_name="Sheet1")
    
    # 辞書の読み込み
    dictionary = load_dictionary("dictionary.txt")
    
    # キーワードの曖昧さスコアを計算
    ambiguity_scores = []
    for keywords_str in df['keyword']:
        # 文字列形式のリストをPythonのリストに変換
        try:
            keywords = ast.literal_eval(keywords_str)
            score = calculate_edit_distance_scores(keywords, dictionary)
        except (ValueError, SyntaxError):
            # リスト形式でない場合は単一のキーワードとして処理
            score = calculate_edit_distance_scores([keywords_str], dictionary)
        ambiguity_scores.append(score)
    
    # 結果を新しいDataFrameに格納
    result_df = pd.DataFrame({
        'キーワード': df['keyword'],
        '曖昧スコア': ambiguity_scores
    })
    
    # 結果をExcelファイルに出力
    output_file = "keyword_ambiguity_scores.xlsx"
    result_df.to_excel(output_file, index=False)
    print(f"結果を {output_file} に保存しました。")

if __name__ == "__main__":
    main()
