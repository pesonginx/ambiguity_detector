# RAG検索結果分析ツール

このツールは、RAG検索結果のExcelファイルを分析し、LLMが参考情報として使用したデータの採択率を計算するためのPythonスクリプトです。

## 機能概要

- **黄色セル検出**: Excelファイル内で黄色で塗りつぶされたセルを自動検出
- **採択率計算**: 各行のRAG検索結果10件のうち、LLMが採択した個数をカウントし、採択率を算出
- **Score・類似度分析**: RAGカラム内のテキストからScoreと類似度の値を自動抽出し、統計分析を実行
- **詳細分析**: 採択パターンの分析、統計情報の算出
- **可視化**: 採択率の分布、Score・類似度の分布、パターンのヒートマップを生成
- **レポート生成**: 分析結果をExcelファイルとして出力

## ファイル構成

- `rag_analysis.py`: 基本的なRAG分析機能
- `rag_detailed_analysis.py`: 詳細な分析機能（可視化、パターン分析含む）
- `RAG_ANALYSIS_README.md`: このファイル

## 必要なライブラリ

```bash
pip install pandas openpyxl numpy matplotlib seaborn
```

## 使用方法

### 1. 基本的な分析（rag_analysis.py）

```python
from rag_analysis import RAGAnalysis

# 分析クラスのインスタンスを作成
analyzer = RAGAnalysis("input.xlsx")

# Excelファイルを読み込み
analyzer.load_excel()

# RAG採択分析を実行
result_df = analyzer.analyze_rag_adoption()

# サマリーを表示
analyzer.print_summary(result_df)

# 結果を保存
analyzer.save_analysis_result(result_df)
```

### 2. 詳細分析（rag_detailed_analysis.py）

```python
from rag_detailed_analysis import RAGDetailedAnalysis

# 詳細分析クラスのインスタンスを作成
analyzer = RAGDetailedAnalysis("input.xlsx")

# Excelファイルを読み込み
analyzer.load_excel()

# 詳細分析を実行
result_df = analyzer.analyze_rag_adoption_detailed()

# 詳細サマリーを表示
analyzer.print_detailed_summary()

# 可視化を作成
analyzer.create_visualizations()

# 詳細レポートを生成
analyzer.generate_detailed_report()
```

### 3. コマンドライン実行

```bash
# 基本的な分析
python rag_analysis.py

# 詳細分析
python rag_detailed_analysis.py
```

## 入力ファイル形式

Excelファイルは以下の形式である必要があります：

- RAG1〜RAG10のカラムが存在すること
- LLMが参考情報として使用したデータは黄色で塗りつぶされていること
- 各行が1つの質問とその検索結果を表していること

### 期待されるカラム構成

| カラム名 | 説明 |
|---------|------|
| RAG1〜RAG10 | RAG検索結果（黄色で塗りつぶされたセルが採択されたデータ）<br>各セルには以下の情報が含まれることが期待されます：<br>・検索スコア（Score）<br>・LLM回答 ⇔【回答】類似度<br>・RAG情報のテキスト |
| オペロボ回答 | LLMの回答 |
| その他のカラム | 質問内容やその他の情報 |

## 出力ファイル

### 基本分析（rag_analysis.py）

- `input_analysis_result.xlsx`: 分析結果を含むExcelファイル
  - RAG分析結果シート
  - 全体統計サマリーシート（Score・類似度の統計情報）

### 詳細分析（rag_detailed_analysis.py）

- `input_detailed_analysis_report.xlsx`: 詳細分析レポート
  - 詳細分析結果シート
  - パターン分析サマリーシート
  - Score・類似度統計シート
  - 採択率ランキングシート
  - Scoreランキングシート
  - 類似度ランキングシート
  - 高採択率行シート
  - 低採択率行シート

- `analysis_plots/`: 可視化ファイル
  - `adoption_rate_distribution.png`: 採択率の分布ヒストグラム
  - `adoption_count_distribution.png`: 採択数の分布
  - `score_analysis.png`: Scoreの分析（分布、採択率との関係、箱ひげ図）
  - `similarity_analysis.png`: 類似度の分析（分布、採択率との関係、箱ひげ図）
  - `adoption_patterns_heatmap.png`: 採択パターンのヒートマップ

## 分析結果の解釈

### 採択率の意味

- **0%**: LLMが検索結果を一切使用しなかった
- **10%**: 10件中1件を使用
- **50%**: 10件中5件を使用
- **100%**: 全検索結果を使用

### 統計情報

- **平均採択率**: 全行の採択率の平均値
- **採択率の標準偏差**: 採択率のばらつきを示す指標
- **採択パターン**: どのRAGカラムが採択されたかのパターン
- **Score統計**: 全体・採択別のScoreの平均、最大、最小、標準偏差
- **類似度統計**: 全体・採択別の類似度の平均、最大、最小、標準偏差

## カスタマイズ

### 黄色の判定基準の変更

`is_yellow_cell`メソッドを修正することで、異なる色や塗りつぶしパターンに対応できます：

```python
def is_yellow_cell(self, cell) -> bool:
    # カスタムの色判定ロジックを実装
    pass
```

### 分析対象カラムの変更

`get_rag_columns`メソッドを修正することで、異なるカラム名に対応できます：

```python
def get_rag_columns(self) -> List[str]:
    # カスタムのカラム名パターンを実装
    pass
```

### Score・類似度の抽出パターンの変更

`extract_score_and_similarity`メソッドを修正することで、異なる形式のScoreや類似度に対応できます：

```python
def extract_score_and_similarity(self, text: str) -> Dict[str, float]:
    # カスタムの抽出パターンを実装
    pass
```

## トラブルシューティング

### よくある問題

1. **黄色セルが検出されない**
   - Excelファイルの色設定を確認
   - 異なる黄色の色コードを使用している可能性

2. **RAGカラムが見つからない**
   - カラム名が「RAG1」「RAG2」...の形式になっているか確認
   - 大文字小文字を確認

3. **ファイル読み込みエラー**
   - ファイルパスが正しいか確認
   - ファイルが破損していないか確認

4. **Score・類似度が抽出されない**
   - RAGカラム内のテキスト形式を確認
   - 抽出パターンが正しいか確認
   - 数値の形式（小数点、単位など）を確認

### デバッグ方法

```python
# デバッグ情報を表示
analyzer = RAGAnalysis("input.xlsx")
analyzer.load_excel()

# カラム名を確認
print(analyzer.df.columns.tolist())

# 最初の数行を確認
print(analyzer.df.head())
```

## ライセンス

このツールはMITライセンスの下で提供されています。

## 更新履歴

- v1.0: 基本的なRAG分析機能を実装
- v1.1: 詳細分析機能と可視化機能を追加 