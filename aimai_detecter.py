import pandas as pd
import numpy as np
from nltk.corpus import wordnet as wn
import jaconv
from janome.tokenizer import Tokenizer
from collections import Counter
import nltk
import ssl

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# NLTKデータのダウンロード
nltk.download('punkt')         # トークン化に必要なデータ
nltk.download('averaged_perceptron_tagger') # 品詞タグ付けに必要なデータ
nltk.download('wordnet')       # WordNet（英語の辞書）
nltk.download('omw-1.4')       # Open Multilingual Wordnet (多言語WordNet)
nltk.download('maxent_ne_chunker') # 固有表現抽出に必要なデータ
nltk.download('words')           # 固有表現抽出に必要なデータ

def get_word_senses(word):
    """
    単語の意味の数を取得する関数
    """
    synsets = wn.synsets(word, lang='jpn')
    return len(synsets)

def calculate_ambiguity_score(text):
    """
    文章の曖昧さスコアを計算する関数
    """
    # Janomeで形態素解析
    tokenizer = Tokenizer()
    words = [token.surface for token in tokenizer.tokenize(text)]
    
    # 各単語の意味の数を取得
    sense_counts = []
    for word in words:
        # ひらがなに変換して検索
        word_hira = jaconv.kata2hira(word)
        senses = get_word_senses(word_hira)
        if senses > 0:  # WordNetに登録されている単語のみを考慮
            sense_counts.append(senses)
    
    if not sense_counts:
        return 0
    
    # 曖昧さスコアの計算
    # 1. 平均的な意味の数
    avg_senses = np.mean(sense_counts)
    # 2. 意味の数の分散（ばらつき）
    sense_variance = np.var(sense_counts)
    # 3. 多義語の割合
    polysemy_ratio = sum(1 for x in sense_counts if x > 1) / len(sense_counts)
    
    # 総合スコアの計算（重み付けは調整可能）
    ambiguity_score = (avg_senses * 0.4 + sense_variance * 0.3 + polysemy_ratio * 0.3)
    
    return round(ambiguity_score, 3)

def main():
    # 入力Excelファイルの読み込み
    input_file = r"C:\ppg\aimai_detect\input.xlsx"  # 入力ファイル名を指定
    df = pd.read_excel(input_file, sheet_name="Sheet1")
    
    # 質問文の曖昧さスコアを計算
    ambiguity_scores = []
    for question in df['Q']:
        score = calculate_ambiguity_score(question)
        ambiguity_scores.append(score)
    
    # 結果を新しいDataFrameに格納
    result_df = pd.DataFrame({
        '質問文': df['Q'],
        '曖昧スコア': ambiguity_scores
    })
    
    # 結果をExcelファイルに出力
    output_file = "ambiguity_scores.xlsx"
    result_df.to_excel(output_file, index=False)
    print(f"結果を {output_file} に保存しました。")

if __name__ == "__main__":
    main()