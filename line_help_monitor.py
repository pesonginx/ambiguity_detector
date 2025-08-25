#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LINEヘルプセンター監視スクリプト
指定されたURLの内容を定期的にチェックし、変更があった場合にスクレイピングしてマークダウン形式で出力
"""

import requests
import hashlib
import time
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import schedule
import logging
from pathlib import Path

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('line_help_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class LineHelpMonitor:
    def __init__(self, url, check_interval_minutes=30, download_images=False):
        self.url = url
        self.check_interval_minutes = check_interval_minutes
        self.download_images = download_images
        self.previous_hash = None
        self.previous_content = None
        self.output_dir = Path("line_help_output")
        self.output_dir.mkdir(exist_ok=True)
        
        # 画像保存用ディレクトリ
        if self.download_images:
            self.images_dir = self.output_dir / "images"
            self.images_dir.mkdir(exist_ok=True)
        
        # ヘッダー設定（ブラウザとして認識されるように）
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # 状態ファイルのパス
        self.state_file = self.output_dir / "monitor_state.json"
        self.load_state()
    
    def load_state(self):
        """前回の状態を読み込み"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.previous_hash = state.get('previous_hash')
                    self.previous_content = state.get('previous_content')
                    logging.info(f"前回の状態を読み込みました: {self.state_file}")
            except Exception as e:
                logging.error(f"状態ファイルの読み込みに失敗: {e}")
    
    def save_state(self):
        """現在の状態を保存"""
        try:
            state = {
                'previous_hash': self.previous_hash,
                'previous_content': self.previous_content,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"状態ファイルの保存に失敗: {e}")
    
    def fetch_content(self):
        """ウェブページの内容を取得"""
        try:
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return response.text
        except requests.RequestException as e:
            logging.error(f"ページの取得に失敗: {e}")
            return None
    
    def calculate_hash(self, content):
        """コンテンツのハッシュ値を計算"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def parse_content(self, html_content):
        """HTMLコンテンツをパースして構造化データを抽出"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 不要な要素を削除
        for element in soup(['script', 'style']):
            element.decompose()
        
        # メインコンテンツを抽出
        main_content = {
            'title': '',
            'meta_info': {},
            'sections': [],
            'timestamp': datetime.now().isoformat()
        }
        
        # メタ情報を取得
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if name and content:
                main_content['meta_info'][name] = content
        
        # タイトルを取得
        title_elem = soup.find('title') or soup.find('h1')
        if title_elem:
            main_content['title'] = title_elem.get_text(strip=True)
        
        # セクションを抽出
        sections = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        for section in sections:
            section_data = {
                'level': int(section.name[1]),
                'title': section.get_text(strip=True),
                'content': []
            }
            
            # セクションの内容を取得
            next_elem = section.find_next_sibling()
            while next_elem and next_elem.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                if next_elem.name:
                    # 要素の詳細情報を取得
                    element_data = {
                        'type': next_elem.name,
                        'text': next_elem.get_text(strip=True),
                        'html': str(next_elem),
                        'attributes': {}
                    }
                    
                    # 属性情報を保存
                    for attr, value in next_elem.attrs.items():
                        element_data['attributes'][attr] = value
                    
                    # 画像要素の特別処理
                    if next_elem.name == 'img':
                        element_data['image_info'] = {
                            'src': next_elem.get('src', ''),
                            'alt': next_elem.get('alt', ''),
                            'title': next_elem.get('title', ''),
                            'width': next_elem.get('width', ''),
                            'height': next_elem.get('height', '')
                        }
                    
                    section_data['content'].append(element_data)
                next_elem = next_elem.find_next_sibling()
            
            main_content['sections'].append(section_data)
        
        return main_content
    
    def content_to_markdown(self, content_data):
        """構造化データをマークダウン形式に変換"""
        markdown = []
        
        # タイトル
        if content_data['title']:
            markdown.append(f"# {content_data['title']}\n")
        
        # タイムスタンプ
        markdown.append(f"**最終更新**: {content_data['timestamp']}\n")
        markdown.append(f"**監視URL**: {self.url}\n\n")
        
        # メタ情報を表示
        if content_data.get('meta_info'):
            markdown.append("## ページ情報\n\n")
            for name, content in content_data['meta_info'].items():
                markdown.append(f"**{name}**: {content}\n")
            markdown.append("\n")
        
        # セクション
        for section in content_data['sections']:
            if section['title']:
                level = section['level']
                markdown.append(f"{'#' * level} {section['title']}\n")
            
            for item in section['content']:
                if item['type'] == 'p':
                    # 段落内の画像を処理
                    processed_text = self._process_inline_elements(item['html'])
                    markdown.append(f"{processed_text}\n\n")
                elif item['type'] in ['ul', 'ol']:
                    # リストの処理
                    soup = BeautifulSoup(item['html'], 'html.parser')
                    for li in soup.find_all('li'):
                        li_content = self._process_inline_elements(str(li))
                        # リストマーカーを除去してテキストを取得
                        li_text = li.get_text(strip=True)
                        markdown.append(f"- {li_text}\n")
                        # リスト項目内の画像があれば追加
                        for img in li.find_all('img'):
                            img_markdown = self._img_to_markdown(img)
                            if img_markdown:
                                markdown.append(f"  {img_markdown}\n")
                    markdown.append("\n")
                elif item['type'] in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    level = int(item['type'][1])
                    markdown.append(f"{'#' * level} {item['text']}\n")
                elif item['type'] == 'img':
                    # 独立した画像要素
                    img_markdown = self._img_to_markdown(item)
                    if img_markdown:
                        markdown.append(f"{img_markdown}\n\n")
                elif item['type'] == 'div':
                    # div要素の処理
                    processed_text = self._process_inline_elements(item['html'])
                    if processed_text.strip():
                        markdown.append(f"{processed_text}\n\n")
                else:
                    # その他の要素
                    processed_text = self._process_inline_elements(item['html'])
                    if processed_text.strip():
                        markdown.append(f"{processed_text}\n\n")
        
        return ''.join(markdown)
    
    def _process_inline_elements(self, html_content):
        """HTML内のインライン要素（画像、リンクなど）をマークダウンに変換"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 画像要素を処理
        for img in soup.find_all('img'):
            img_markdown = self._img_to_markdown(img)
            if img_markdown:
                img.replace_with(f" {img_markdown} ")
        
        # リンク要素を処理
        for link in soup.find_all('a'):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            if href and text:
                link_markdown = f"[{text}]({href})"
                link.replace_with(link_markdown)
        
        # 太字要素を処理
        for bold in soup.find_all(['strong', 'b']):
            text = bold.get_text(strip=True)
            bold.replace_with(f"**{text}**")
        
        # 斜体要素を処理
        for italic in soup.find_all(['em', 'i']):
            text = italic.get_text(strip=True)
            italic.replace_with(f"*{text}*")
        
        return soup.get_text()
    
    def _img_to_markdown(self, img_element):
        """画像要素をマークダウン形式に変換"""
        if isinstance(img_element, dict) and 'image_info' in img_element:
            # 構造化データから画像情報を取得
            img_info = img_element['image_info']
            src = img_info.get('src', '')
            alt = img_info.get('alt', '')
            title = img_info.get('title', '')
        else:
            # BeautifulSoup要素から画像情報を取得
            src = img_element.get('src', '')
            alt = img_element.get('alt', '')
            title = img_element.get('title', '')
        
        if not src:
            return ""
        
        # 相対URLを絶対URLに変換
        if src.startswith('/'):
            from urllib.parse import urljoin
            src = urljoin(self.url, src)
        elif src.startswith('./'):
            from urllib.parse import urljoin
            src = urljoin(self.url, src)
        
        # 画像をダウンロードする場合
        if self.download_images:
            local_path = self._download_image(src, alt)
            if local_path:
                src = str(local_path)
        
        # マークダウン形式で画像を出力
        if title:
            return f"![{alt}]({src} \"{title}\")"
        else:
            return f"![{alt}]({src})"
    
    def _download_image(self, image_url, alt_text):
        """画像をダウンロードしてローカルに保存"""
        try:
            import hashlib
            import os
            from urllib.parse import urlparse
            
            # 画像URLからファイル名を生成
            parsed_url = urlparse(image_url)
            original_filename = os.path.basename(parsed_url.path)
            
            if not original_filename or '.' not in original_filename:
                # ファイル名が取得できない場合はalt_textを使用
                filename = f"{hashlib.md5(alt_text.encode()).hexdigest()[:8]}.jpg"
            else:
                filename = original_filename
            
            # 重複を避けるためにタイムスタンプを追加
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{timestamp}{ext}"
            
            local_path = self.images_dir / filename
            
            # 画像をダウンロード
            response = requests.get(image_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            logging.info(f"画像をダウンロードしました: {local_path}")
            return local_path
            
        except Exception as e:
            logging.warning(f"画像のダウンロードに失敗: {image_url} - {e}")
            return None
    
    def check_for_changes(self):
        """変更をチェックして処理"""
        logging.info(f"LINEヘルプセンターの監視を開始: {self.url}")
        
        current_content = self.fetch_content()
        if current_content is None:
            logging.error("コンテンツの取得に失敗しました")
            return
        
        current_hash = self.calculate_hash(current_content)
        
        if self.previous_hash is None:
            logging.info("初回実行のため、現在のコンテンツを保存します")
            self.previous_hash = current_hash
            self.previous_content = current_content
            self.save_state()
            return
        
        if current_hash != self.previous_hash:
            logging.info("コンテンツの変更を検出しました！")
            
            # 変更されたコンテンツを処理
            parsed_content = self.parse_content(current_content)
            markdown_content = self.content_to_markdown(parsed_content)
            
            # ファイルに保存
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.output_dir / f"line_help_{timestamp}.md"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            logging.info(f"変更されたコンテンツを保存しました: {filename}")
            
            # 差分情報も保存
            diff_filename = self.output_dir / f"diff_{timestamp}.txt"
            with open(diff_filename, 'w', encoding='utf-8') as f:
                f.write(f"変更検出時刻: {datetime.now().isoformat()}\n")
                f.write(f"前回ハッシュ: {self.previous_hash}\n")
                f.write(f"現在ハッシュ: {current_hash}\n")
                f.write(f"URL: {self.url}\n")
            
            # 状態を更新
            self.previous_hash = current_hash
            self.previous_content = current_content
            self.save_state()
            
        else:
            logging.info("変更は検出されませんでした")
    
    def manual_check(self):
        """手動実行用のチェック関数"""
        logging.info(f"LINEヘルプセンターの手動チェックを開始: {self.url}")
        
        current_content = self.fetch_content()
        if current_content is None:
            logging.error("コンテンツの取得に失敗しました")
            return False
        
        current_hash = self.calculate_hash(current_content)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 現在のコンテンツを常に保存
        current_filename = self.output_dir / f"current_content_{timestamp}.md"
        parsed_current = self.parse_content(current_content)
        markdown_current = self.content_to_markdown(parsed_current)
        
        with open(current_filename, 'w', encoding='utf-8') as f:
            f.write(markdown_current)
        
        logging.info(f"現在のコンテンツを保存しました: {current_filename}")
        
        if self.previous_hash is None:
            logging.info("初回実行のため、現在のコンテンツを基準として保存します")
            self.previous_hash = current_hash
            self.previous_content = current_content
            self.save_state()
            return True
        
        if current_hash != self.previous_hash:
            logging.info("コンテンツの変更を検出しました！")
            
            # 前回のコンテンツも保存（変更があった場合）
            if self.previous_content:
                previous_filename = self.output_dir / f"previous_content_{timestamp}.md"
                parsed_previous = self.parse_content(self.previous_content)
                markdown_previous = self.content_to_markdown(parsed_previous)
                
                with open(previous_filename, 'w', encoding='utf-8') as f:
                    f.write(markdown_previous)
                
                logging.info(f"前回のコンテンツを保存しました: {previous_filename}")
            
            # 差分情報を保存
            diff_filename = self.output_dir / f"diff_{timestamp}.txt"
            with open(diff_filename, 'w', encoding='utf-8') as f:
                f.write(f"変更検出時刻: {datetime.now().isoformat()}\n")
                f.write(f"前回ハッシュ: {self.previous_hash}\n")
                f.write(f"現在ハッシュ: {current_hash}\n")
                f.write(f"URL: {self.url}\n")
                f.write(f"前回コンテンツファイル: {previous_filename if self.previous_content else 'なし'}\n")
                f.write(f"現在コンテンツファイル: {current_filename}\n")
            
            logging.info(f"差分情報を保存しました: {diff_filename}")
            
            # 状態を更新
            self.previous_hash = current_hash
            self.previous_content = current_content
            self.save_state()
            
            return True
            
        else:
            logging.info("変更は検出されませんでした")
            return False
    
    def start_monitoring(self):
        """監視を開始（スケジューラー使用）"""
        logging.info(f"LINEヘルプセンター監視を開始します（間隔: {self.check_interval_minutes}分）")
        
        # 初回実行
        self.check_for_changes()
        
        # 定期実行をスケジュール
        schedule.every(self.check_interval_minutes).minutes.do(self.check_for_changes)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # 1分ごとにスケジュールをチェック
        except KeyboardInterrupt:
            logging.info("監視を停止しました")
        except Exception as e:
            logging.error(f"監視中にエラーが発生: {e}")

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
    """メイン関数"""
    config = load_config()
    if config is None:
        logging.error("設定の読み込みに失敗しました。プログラムを終了します。")
        return
    
    monitor = LineHelpMonitor(
        config["url"], 
        config["check_interval_minutes"],
        config.get("download_images", False)
    )
    monitor.start_monitoring()

if __name__ == "__main__":
    main() 