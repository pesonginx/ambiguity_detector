import pandas as pd
import xlwings as xw
import numpy as np
from typing import List, Tuple, Dict
import os
import re

class RAGAnalysisXlwings:
    """xlwingsを使用したRAG検索結果の分析クラス"""
    
    def __init__(self, excel_file_path: str):
        """
        RAG分析クラスの初期化
        
        Parameters:
        -----------
        excel_file_path : str
            分析対象のExcelファイルパス
        """
        self.excel_file_path = os.path.abspath(excel_file_path)
        self.app = None
        self.workbook = None
        self.worksheet = None
        self.df = None
        
    def load_excel(self, sheet_name: str = None):
        """
        Excelファイルを読み込み
        
        Parameters:
        -----------
        sheet_name : str, optional
            読み込むシート名（Noneの場合は最初のシート）
        """
        try:
            # xlwingsでExcelアプリケーションを起動
            self.app = xw.App(visible=False)
            self.workbook = self.app.books.open(self.excel_file_path)
            
            # シートを選択
            if sheet_name is None:
                self.worksheet = self.workbook.sheets[0]
                sheet_name = self.worksheet.name
            else:
                self.worksheet = self.workbook.sheets[sheet_name]
            
            # pandasでデータを読み込み（分析用）
            # より安全な方法でシート名を取得
            if sheet_name is None:
                # シート名を取得してから読み込み
                try:
                    excel_file = pd.ExcelFile(self.excel_file_path)
                    sheet_names = excel_file.sheet_names
                    sheet_name = sheet_names[0]
                    print(f"利用可能なシート: {sheet_names}")
                    print(f"最初のシート '{sheet_name}' を使用します")
                except Exception as e:
                    print(f"シート名の取得に失敗: {e}")
                    # デフォルトで最初のシートを使用
                    sheet_name = 0
            
            # 明示的にシートを指定して読み込み
            try:
                self.df = pd.read_excel(self.excel_file_path, sheet_name=sheet_name)
            except Exception as e:
                print(f"指定されたシート '{sheet_name}' の読み込みに失敗: {e}")
                # 最初のシートを試行
                self.df = pd.read_excel(self.excel_file_path, sheet_name=0)
                print("最初のシート（インデックス0）を使用します")
            
            # DataFrameかどうかチェック
            if not isinstance(self.df, pd.DataFrame):
                print(f"警告: 読み込まれたデータがDataFrameではありません。型: {type(self.df)}")
                if isinstance(self.df, dict):
                    print(f"利用可能なシート: {list(self.df.keys())}")
                    # 最初のシートを使用
                    first_sheet = list(self.df.keys())[0]
                    self.df = self.df[first_sheet]
                    print(f"最初のシート '{first_sheet}' を使用します")
            
            print(f"Excelファイルを読み込みました: {self.excel_file_path}")
            print(f"使用シート: {self.worksheet.name}")
            print(f"データ形状: {self.df.shape}")
            print(f"カラム: {list(self.df.columns)}")
            
        except Exception as e:
            print(f"Excelファイルの読み込みに失敗しました: {e}")
            if self.app:
                self.app.quit()
            raise
    
    def is_colored_cell_xlwings(self, row: int, col: int) -> bool:
        """
        xlwingsを使用してセルが塗りつぶされているかチェック
        
        Parameters:
        -----------
        row : int
            行番号（1ベース）
        col : int
            列番号（1ベース）
            
        Returns:
        --------
        bool
            塗りつぶされている場合True
        """
        try:
            # xlwingsでセルを取得
            cell = self.worksheet.range((row, col))
            
            # 背景色を取得
            interior_color = cell.api.Interior.Color
            
            # 白または無色の場合はFalse
            # Excelの白の色コード: -4142 (xlNone), 16777215 (白)
            if interior_color in [-4142, 16777215, -4105]:  # xlNone, 白, xlAutomatic
                return False
            
            # 色が設定されている場合はTrue
            return True
            
        except Exception as e:
            print(f"セル({row}, {col})の色取得でエラー: {e}")
            return False
    
    def debug_cell_color_xlwings(self, row: int, col: int) -> str:
        """
        xlwingsを使用してセルの色情報をデバッグ用に取得
        
        Parameters:
        -----------
        row : int
            行番号（1ベース）
        col : int
            列番号（1ベース）
            
        Returns:
        --------
        str
            色情報の文字列
        """
        try:
            cell = self.worksheet.range((row, col))
            
            # 背景色を取得
            interior_color = cell.api.Interior.Color
            interior_color_index = cell.api.Interior.ColorIndex
            interior_pattern = cell.api.Interior.Pattern
            
            # フォント色も取得
            font_color = cell.api.Font.Color
            font_color_index = cell.api.Font.ColorIndex
            
            color_info = f"Interior: {interior_color} (Index: {interior_color_index}, Pattern: {interior_pattern})"
            color_info += f", Font: {font_color} (Index: {font_color_index})"
            
            return color_info
            
        except Exception as e:
            return f"Error: {e}"
    
    def get_rag_columns(self) -> List[str]:
        """
        RAGカラム（RAG1〜RAG10）を取得
        
        Returns:
        --------
        List[str]
            RAGカラム名のリスト
        """
        rag_columns = []
        for i in range(1, 11):
            column_name = f"RAG{i}"
            if column_name in self.df.columns:
                rag_columns.append(column_name)
        
        return rag_columns
    
    def extract_score_and_similarity(self, text: str) -> Dict[str, float]:
        """
        RAGカラムのテキストからScoreと類似度を抽出
        
        Parameters:
        -----------
        text : str
            抽出対象のテキスト
            
        Returns:
        --------
        Dict[str, float]
            Scoreと類似度の値（抽出できない場合はNone）
        """
        if pd.isna(text) or not isinstance(text, str):
            return {'score': None, 'similarity': None}
        
        result = {'score': None, 'similarity': None}
        
        # Scoreの抽出パターン
        score_patterns = [
            r'Score[:\s]*([0-9]+\.?[0-9]*)',
            r'スコア[:\s]*([0-9]+\.?[0-9]*)',
            r'検索スコア[:\s]*([0-9]+\.?[0-9]*)',
            r'([0-9]+\.?[0-9]*)\s*\(Score\)',
            r'Score\s*=\s*([0-9]+\.?[0-9]*)'
        ]
        
        # 類似度の抽出パターン
        similarity_patterns = [
            r'類似度[:\s]*([0-9]+\.?[0-9]*)',
            r'LLM回答\s*⇔\s*【回答】類似度[:\s]*([0-9]+\.?[0-9]*)',
            r'回答類似度[:\s]*([0-9]+\.?[0-9]*)',
            r'([0-9]+\.?[0-9]*)\s*\(類似度\)',
            r'Similarity[:\s]*([0-9]+\.?[0-9]*)',
            r'([0-9]+\.?[0-9]*)\s*%?\s*\(類似度\)'
        ]
        
        # Scoreの抽出
        for pattern in score_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    result['score'] = float(match.group(1))
                    break
                except ValueError:
                    continue
        
        # 類似度の抽出
        for pattern in similarity_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    result['similarity'] = float(match.group(1))
                    break
                except ValueError:
                    continue
        
        return result
    
    def analyze_rag_adoption(self, debug_colors: bool = False) -> pd.DataFrame:
        """
        RAG検索結果の採択分析を実行
        
        Parameters:
        -----------
        debug_colors : bool, optional
            色情報のデバッグ出力を行うかどうか（デフォルト: False）
            
        Returns:
        --------
        pd.DataFrame
            採択分析結果を含むDataFrame
        """
        if self.df is None:
            raise ValueError("Excelファイルが読み込まれていません。load_excel()を先に実行してください。")
        
        rag_columns = self.get_rag_columns()
        if not rag_columns:
            raise ValueError("RAGカラム（RAG1〜RAG10）が見つかりません。")
        
        print(f"分析対象RAGカラム: {rag_columns}")
        
        # 結果を格納するリスト
        results = []
        
        # 全体のScoreと類似度の統計用
        all_scores = []
        all_similarities = []
        adopted_scores = []
        adopted_similarities = []
        
        # 各行を分析
        for row_idx, row_data in self.df.iterrows():
            adopted_count = 0
            adopted_rags = []
            row_scores = []
            row_similarities = []
            adopted_row_scores = []
            adopted_row_similarities = []
            
            # 各RAGカラムをチェック
            for rag_col in rag_columns:
                # Excelのセル座標を取得（1ベース）
                excel_row = row_idx + 2  # ヘッダー行を考慮
                excel_col = self.df.columns.get_loc(rag_col) + 1
                
                # デバッグ出力（座標確認）
                if debug_colors and row_idx < 2:
                    print(f"  座標: 行{excel_row}, 列{excel_col} ({rag_col})")
                
                # xlwingsでセルが塗りつぶされているかチェック
                is_adopted = self.is_colored_cell_xlwings(excel_row, excel_col)
                
                # デバッグ出力（必要に応じて）
                if debug_colors and row_idx < 5:  # 最初の5行のみデバッグ出力
                    color_info = self.debug_cell_color_xlwings(excel_row, excel_col)
                    print(f"行{row_idx+1}, {rag_col}: {color_info} -> {'採択' if is_adopted else '未採択'}")
                
                # Scoreと類似度を抽出
                cell_text = str(row_data[rag_col]) if not pd.isna(row_data[rag_col]) else ""
                extracted_values = self.extract_score_and_similarity(cell_text)
                
                # 統計用に値を記録
                if extracted_values['score'] is not None:
                    row_scores.append(extracted_values['score'])
                    all_scores.append(extracted_values['score'])
                    if is_adopted:
                        adopted_row_scores.append(extracted_values['score'])
                        adopted_scores.append(extracted_values['score'])
                
                if extracted_values['similarity'] is not None:
                    row_similarities.append(extracted_values['similarity'])
                    all_similarities.append(extracted_values['similarity'])
                    if is_adopted:
                        adopted_row_similarities.append(extracted_values['similarity'])
                        adopted_similarities.append(extracted_values['similarity'])
                
                if is_adopted:
                    adopted_count += 1
                    adopted_rags.append(rag_col)
            
            # 採択率を計算
            adoption_rate = (adopted_count / len(rag_columns)) * 100 if rag_columns else 0
            
            # 行内のScoreと類似度の統計
            row_score_stats = self._calculate_stats(row_scores)
            row_similarity_stats = self._calculate_stats(row_similarities)
            adopted_score_stats = self._calculate_stats(adopted_row_scores)
            adopted_similarity_stats = self._calculate_stats(adopted_row_similarities)
            
            # 結果を記録
            result = {
                '行番号': row_idx + 1,
                '採択数': adopted_count,
                '総検索結果数': len(rag_columns),
                '採択率(%)': round(adoption_rate, 2),
                '採択されたRAG': ', '.join(adopted_rags) if adopted_rags else 'なし',
                # Score統計
                'Score平均': row_score_stats['mean'],
                'Score最大': row_score_stats['max'],
                'Score最小': row_score_stats['min'],
                'Score標準偏差': row_score_stats['std'],
                '採択Score平均': adopted_score_stats['mean'],
                '採択Score最大': adopted_score_stats['max'],
                '採択Score最小': adopted_score_stats['min'],
                # 類似度統計
                '類似度平均': row_similarity_stats['mean'],
                '類似度最大': row_similarity_stats['max'],
                '類似度最小': row_similarity_stats['min'],
                '類似度標準偏差': row_similarity_stats['std'],
                '採択類似度平均': adopted_similarity_stats['mean'],
                '採択類似度最大': adopted_similarity_stats['max'],
                '採択類似度最小': adopted_similarity_stats['min']
            }
            
            # 元のデータも含める
            for col in self.df.columns:
                result[col] = row_data[col]
            
            results.append(result)
        
        # 全体統計を計算
        overall_score_stats = self._calculate_stats(all_scores)
        overall_similarity_stats = self._calculate_stats(all_similarities)
        overall_adopted_score_stats = self._calculate_stats(adopted_scores)
        overall_adopted_similarity_stats = self._calculate_stats(adopted_similarities)
        
        # 全体統計を保存
        self.overall_stats = {
            'score': overall_score_stats,
            'similarity': overall_similarity_stats,
            'adopted_score': overall_adopted_score_stats,
            'adopted_similarity': overall_adopted_similarity_stats
        }
        
        # DataFrameに変換
        result_df = pd.DataFrame(results)
        
        return result_df
    
    def _calculate_stats(self, values: List[float]) -> Dict[str, float]:
        """数値リストの統計を計算"""
        if not values:
            return {'mean': None, 'max': None, 'min': None, 'std': None, 'count': 0}
        
        return {
            'mean': round(np.mean(values), 3),
            'max': round(np.max(values), 3),
            'min': round(np.min(values), 3),
            'std': round(np.std(values), 3),
            'count': len(values)
        }
    
    def save_analysis_result(self, result_df: pd.DataFrame, output_file: str = None):
        """
        分析結果をExcelファイルに保存
        
        Parameters:
        -----------
        result_df : pd.DataFrame
            保存する分析結果
        output_file : str, optional
            出力ファイル名（Noneの場合は自動生成）
        """
        if output_file is None:
            base_name = os.path.splitext(self.excel_file_path)[0]
            output_file = f"{base_name}_xlwings_analysis_result.xlsx"
        
        try:
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                # 詳細分析結果
                result_df.to_excel(writer, sheet_name='RAG分析結果', index=False)
                
                # 全体統計サマリー
                if hasattr(self, 'overall_stats'):
                    overall_summary = []
                    for metric, stats in self.overall_stats.items():
                        if stats['count'] > 0:
                            overall_summary.append({
                                '指標': metric,
                                '平均値': stats['mean'],
                                '最大値': stats['max'],
                                '最小値': stats['min'],
                                '標準偏差': stats['std'],
                                'データ数': stats['count']
                            })
                    
                    if overall_summary:
                        overall_df = pd.DataFrame(overall_summary)
                        overall_df.to_excel(writer, sheet_name='全体統計サマリー', index=False)
            
            print(f"分析結果を保存しました: {output_file}")
            
        except Exception as e:
            print(f"ファイル保存に失敗しました: {e}")
            raise
    
    def print_summary(self, result_df: pd.DataFrame):
        """
        分析結果のサマリーを表示
        
        Parameters:
        -----------
        result_df : pd.DataFrame
            分析結果のDataFrame
        """
        print("\n=== RAG分析結果サマリー (xlwings版) ===")
        print(f"総行数: {len(result_df)}")
        print(f"平均採択率: {result_df['採択率(%)'].mean():.2f}%")
        print(f"最大採択率: {result_df['採択率(%)'].max():.2f}%")
        print(f"最小採択率: {result_df['採択率(%)'].min():.2f}%")
        print(f"標準偏差: {result_df['採択率(%)'].std():.2f}%")
        
        # Scoreと類似度の統計を表示
        if hasattr(self, 'overall_stats'):
            print("\n=== Score統計 ===")
            score_stats = self.overall_stats['score']
            if score_stats['count'] > 0:
                print(f"全体Score平均: {score_stats['mean']}")
                print(f"全体Score最大: {score_stats['max']}")
                print(f"全体Score最小: {score_stats['min']}")
                print(f"全体Score標準偏差: {score_stats['std']}")
                print(f"Scoreデータ数: {score_stats['count']}")
            
            adopted_score_stats = self.overall_stats['adopted_score']
            if adopted_score_stats['count'] > 0:
                print(f"採択Score平均: {adopted_score_stats['mean']}")
                print(f"採択Score最大: {adopted_score_stats['max']}")
                print(f"採択Score最小: {adopted_score_stats['min']}")
                print(f"採択Scoreデータ数: {adopted_score_stats['count']}")
            
            print("\n=== 類似度統計 ===")
            similarity_stats = self.overall_stats['similarity']
            if similarity_stats['count'] > 0:
                print(f"全体類似度平均: {similarity_stats['mean']}")
                print(f"全体類似度最大: {similarity_stats['max']}")
                print(f"全体類似度最小: {similarity_stats['min']}")
                print(f"全体類似度標準偏差: {similarity_stats['std']}")
                print(f"類似度データ数: {similarity_stats['count']}")
            
            adopted_similarity_stats = self.overall_stats['adopted_similarity']
            if adopted_similarity_stats['count'] > 0:
                print(f"採択類似度平均: {adopted_similarity_stats['mean']}")
                print(f"採択類似度最大: {adopted_similarity_stats['max']}")
                print(f"採択類似度最小: {adopted_similarity_stats['min']}")
                print(f"採択類似度データ数: {adopted_similarity_stats['count']}")
        
        print("\n=== 採択率分布 ===")
        adoption_ranges = [
            (0, 10, "0-10%"),
            (10, 30, "10-30%"),
            (30, 50, "30-50%"),
            (50, 70, "50-70%"),
            (70, 90, "70-90%"),
            (90, 101, "90-100%")
        ]
        
        for min_rate, max_rate, label in adoption_ranges:
            count = len(result_df[(result_df['採択率(%)'] >= min_rate) & (result_df['採択率(%)'] < max_rate)])
            percentage = (count / len(result_df)) * 100
            print(f"{label}: {count}行 ({percentage:.1f}%)")
        
        print("\n=== 高採択率の行（採択率50%以上） ===")
        high_adoption = result_df[result_df['採択率(%)'] >= 50]
        if len(high_adoption) > 0:
            for _, row in high_adoption.iterrows():
                print(f"行{row['行番号']}: 採択率{row['採択率(%)']}% ({row['採択数']}/{row['総検索結果数']})")
        else:
            print("採択率50%以上の行はありません")
    
    def close(self):
        """Excelアプリケーションを閉じる"""
        try:
            if self.workbook:
                self.workbook.close()
            if self.app:
                self.app.quit()
        except Exception as e:
            print(f"Excelアプリケーションの終了でエラー: {e}")

def main():
    """メイン実行関数"""
    # 分析対象のExcelファイル
    excel_file = "input.xlsx"
    
    # デバッグモード（色情報を表示するかどうか）
    debug_colors = True  # Trueにすると色情報が表示されます
    
    # RAG分析クラスのインスタンスを作成
    analyzer = RAGAnalysisXlwings(excel_file)
    
    try:
        # Excelファイルを読み込み
        analyzer.load_excel()
        
        # RAG採択分析を実行
        result_df = analyzer.analyze_rag_adoption(debug_colors=debug_colors)
        
        # サマリーを表示
        analyzer.print_summary(result_df)
        
        # 結果を保存
        analyzer.save_analysis_result(result_df)
        
        print("\n分析が完了しました！")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
    finally:
        # Excelアプリケーションを閉じる
        analyzer.close()

if __name__ == "__main__":
    main() 