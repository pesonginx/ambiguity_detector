import re
import time
import pandas as pd
import os
import uuid
from datetime import datetime
from typing import List, Dict, Tuple, Callable, Optional
from urllib.parse import urljoin, urlparse
import logging
import json

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup
import html2text

from app.core.config import settings

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScrapingService:
    """Seleniumを使用した高度なスクレイピング処理を行うサービスクラス"""
    
    def __init__(self, output_dir: str = None, headless: bool = None, wait_time: int = None):
        self.output_dir = output_dir or settings.OUTPUT_DIR
        self.headless = headless if headless is not None else settings.HEADLESS
        self.wait_time = wait_time or settings.WAIT_TIME
        
        # 出力ディレクトリの作成
        os.makedirs(self.output_dir, exist_ok=True)
        
        # タスクとファイルの関連付けを管理するディレクトリ
        self.task_files_dir = settings.TASK_FILES_DIR
        os.makedirs(self.task_files_dir, exist_ok=True)
        
        # WebDriverの初期化
        self.driver = None
        self.wait = None
        self.html2text_converter = None
        
        # 初期化
        self.setup_driver()
        self.setup_html2text()
    
    def setup_driver(self):
        """Chrome WebDriverの設定"""
        try:
            options = Options()
            if self.headless:
                options.add_argument("--headless")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")
                options.add_argument(
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
            
            if settings.HTTP_PROXY:
                options.add_argument(f"--proxy-server={settings.HTTP_PROXY}")
            if settings.NO_PROXY:
                options.add_argument(f"--ignore-certificate-errors-spki-list={settings.NO_PROXY}")

            service = Service(settings.DRIVER_PATH)
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, self.wait_time)
            
            logger.info("Chrome WebDriverの初期化が完了しました")
            
        except Exception as e:
            logger.error(f"Chrome WebDriverの初期化に失敗しました: {e}")
            raise Exception(f"WebDriverの初期化に失敗しました: {e}")
    
    def setup_html2text(self):
        """html2textコンバータ（マークダウン化）の設定"""
        self.html2text_converter = html2text.HTML2Text()
        self.html2text_converter.ignore_links = False
        self.html2text_converter.ignore_images = False
        self.html2text_converter.body_width = 0  # No line wrapping
        self.html2text_converter.unicode_snob = True
        self.html2text_converter.skip_internal_links = False
        self.html2text_converter.ignore_tables = False  # 表をhtml形式にする
    
    def read_excel_urls(self, file_path: str) -> List[str]:
        """ExcelファイルからURLを読み込む"""
        try:
            # Excelファイルを読み込み
            df = pd.read_excel(file_path)
            urls = []
            
            # 全列をチェックしてURLを含むセルを探す
            for column in df.columns:
                for value in df[column].dropna():
                    value_str = str(value).strip()
                    if self._is_valid_url(value_str):
                        urls.append(value_str)
            
            logger.info(f"Excelファイルから {len(urls)} 個のURLを読み込みました")
            return urls
            
        except Exception as e:
            logger.error(f"Excelファイルの読み込みエラー: {e}")
            raise Exception(f"Excelファイルの読み込みに失敗しました: {e}")
    
    def _is_valid_url(self, url: str) -> bool:
        """URLが有効かどうかをチェック"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def remove_unwanted_elements(self, soup: BeautifulSoup) -> BeautifulSoup:
        """navigation, sidebar等の不要要素を除外する"""
        unwanted_selectors = [
            "nav", "navbar", "navigation", "sidebar", "side-bar", "aside", "header", "footer",
            "menu", "menubar", "menu-bar", "breadcrumb", "breadcrumbs", "advertisement", "ads",
            "social", "share", "sharing", "comment", "comments", "popup", "modal",
            "newsletter", "subscription"
        ]

        # tag名による除外
        for tag in ["nav", "aside", "header", "footer"]:
            for element in soup.find_all(tag):
                element.decompose()

        # class名やid名による除外
        for selector in unwanted_selectors:
            # Remove by class
            for element in soup.find_all(class_=re.compile(selector, re.I)):
                element.decompose()
            # Remove by id
            for element in soup.find_all(id=re.compile(selector, re.I)):
                element.decompose()

        # script, style, noscriptタグの除外
        for element in soup.find_all(["script", "style", "noscript"]):
            element.decompose()

        return soup
    
    def handle_mcafee_gateway(self) -> bool:
        """McAfee Web Gatewayの画面対応を行う"""
        try:
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, "lxml")

            if (
                "McAfee Web Gateway" in soup.text
                or "blocked by the URL Filter database" in soup.text
            ):
                logger.info("McAfee Web Gateway画面を検出しました")

                # "Yes, I want to continue the session!" ボタンを探してクリックする
                continue_button = self.driver.find_element(
                    "xpath",
                    "//input[@type='button' and @value='Yes, I want to continue the session!']",
                )
                if continue_button:
                    logger.info("'Continue'ボタンをクリックしてMcAfee Gatewayをバイパスします")
                    self.driver.execute_script("arguments[0].click();", continue_button)
                    time.sleep(3)  # 遷移のために待機
                    return True
                else:
                    logger.warning("McAfee Gateway画面で'Continue'ボタンが見つかりませんでした")
                    return False
            else:
                logger.debug("McAfee Web Gateway画面は検出されませんでした")
                return False
        except Exception as e:
            logger.error(f"McAfee Web Gateway処理でエラーが発生しました: {str(e)}")
            return False
    
    def get_content_selector(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """URL patternに応じて取得する内容を設定する"""
        url_patterns = {
            "https://help.line.me/": ("class", "LyContents"),
            "https://guide.line.me/": ("class", "contentWrap"),
            "https://linestep.jp/": ("id", "main-wrap"),
            "https://appllio.com": ("class", "main-content"),
        }

        for pattern, (selector_type, selector_value) in url_patterns.items():
            if url.startswith(pattern):
                return selector_type, selector_value

        return None, None
    
    def extract_content(self, url: str) -> Optional[BeautifulSoup]:
        """ウェブページから内容を抽出する"""
        try:
            logger.info(f"アクセス中: {url}")
            self.driver.get(url)
            time.sleep(3)  # Wait for page to load

            # McAfee Web Gateway対応
            if not self.handle_mcafee_gateway():
                logger.warning("McAfee Web Gateway処理の失敗により処理を中止します")
                return None

            # Get page source
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, "lxml")

            # Determine extraction method based on URL
            selector_type, selector_value = self.get_content_selector(url)

            if selector_type and selector_value:
                # Extract specific content for known sites
                if selector_type == "class":
                    content = soup.find("div", class_=selector_value)
                elif selector_type == "id":
                    content = soup.find("div", id=selector_value)

                if content:
                    logger.info(f"特定のコンテンツセレクターが見つかりました: {selector_type}={selector_value}")
                    return content
                else:
                    logger.info("特定のセレクターが見つからないため、一般的な抽出にフォールバックします")

            # General content extraction
            content_selectors = [
                ("tag", "main"), ("class", "content"), ("class", "main-content"),
                ("class", "post-content"), ("class", "entry-content"), ("id", "content"),
                ("id", "main"), ("class", "article"), ("tag", "article")
            ]

            main_content = None
            for selector_type, selector_value in content_selectors:
                if selector_type == "tag":
                    main_content = soup.find(selector_value)
                elif selector_type == "class":
                    main_content = soup.find(class_=re.compile(selector_value, re.I))
                elif selector_type == "id":
                    main_content = soup.find(id=re.compile(selector_value, re.I))

                if main_content:
                    logger.info(f"メインコンテンツが見つかりました: {selector_type}={selector_value}")
                    break

            if not main_content:
                # If no main content found, use body but remove unwanted elements
                main_content = soup.find("body")
            if main_content:
                main_content = self.remove_unwanted_elements(main_content)
                logger.info("不要な要素を除去したbodyコンテンツを使用します")

            return main_content if main_content else soup

        except Exception as e:
            logger.error(f"{url}からのコンテンツ抽出でエラーが発生しました: {str(e)}")
            return None
    
    def process_tables(self, soup: BeautifulSoup) -> BeautifulSoup:
        """表についてはHTML構造を維持するための処理"""
        if soup:
            for table in soup.find_all("table"):
                table["data-preserve-html"] = "true"
        return soup
    
    def convert_to_markdown(self, soup: BeautifulSoup, base_url: str) -> str:
        """BeautifulSoupコンテントをマークダウンへ変換する"""
        if not soup:
            return ""

        # Process tables to preserve HTML format
        soup = self.process_tables(soup)

        # Convert relative URLs to absolute URLs
        for link in soup.find_all("a", href=True):
            link["href"] = urljoin(base_url, link["href"])
        for img in soup.find_all("img", src=True):
            img["src"] = urljoin(base_url, img["src"])

        # Convert to markdown
        html_content = str(soup)
        markdown = self.html2text_converter.handle(html_content)

        # Post-process to preserve table HTML
        lines = markdown.split("\n")
        processed_lines = []
        in_table = False

        for line in lines:
            if "<table>" in line:
                in_table = True
            elif "</table>" in line:
                in_table = False
                processed_lines.append(line)
                continue

            if in_table and line.strip():
                processed_lines.append(line)
            elif not in_table:
                processed_lines.append(line)

        return "\n".join(processed_lines)
    
    def scrape_url(self, url: str) -> Dict[str, str]:
        """指定されたURLをスクレイピングする"""
        try:
            logger.info(f"スクレイピング開始: {url}")
            
            # コンテンツを抽出
            content_soup = self.extract_content(url)
            if content_soup:
                # マークダウンに変換
                markdown_content = self.convert_to_markdown(content_soup, url)
                
                # タイトルの取得
                title = self._extract_title(content_soup)
                
                return {
                    'url': url,
                    'title': title,
                    'content': markdown_content,
                    'status_code': 200,
                    'error': None
                }
            else:
                return {
                    'url': url,
                    'title': None,
                    'content': None,
                    'status_code': None,
                    'error': "ページからコンテンツを抽出できませんでした"
                }
                
        except Exception as e:
            logger.error(f"スクレイピングエラー ({url}): {e}")
            return {
                'url': url,
                'title': None,
                'content': None,
                'status_code': None,
                'error': str(e)
            }
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """HTMLからタイトルを抽出"""
        # 優先順位: titleタグ > h1 > h2 > h3
        title = soup.find('title')
        if title:
            return title.get_text().strip()
        
        h1 = soup.find('h1')
        if h1:
            return h1.get_text().strip()
        
        h2 = soup.find('h2')
        if h2:
            return h2.get_text().strip()
        
        h3 = soup.find('h3')
        if h3:
            return h3.get_text().strip()
        
        return "タイトルなし"
    
    def generate_markdown(self, scraped_data: Dict[str, str]) -> str:
        """スクレイピングしたデータからマークダウンファイルを生成"""
        url = scraped_data['url']
        title = scraped_data['title'] or "タイトルなし"
        content = scraped_data['content'] or "コンテンツなし"
        
        # マークダウンの生成
        markdown_content = f"""# {title}

## URL
{url}

## スクレイピング日時
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## コンテンツ

{content}

---
*このファイルは自動生成されました*
"""
        return markdown_content
    
    def save_markdown(self, markdown_content: str, url: str, task_id: str) -> str:
        """マークダウンファイルを保存し、タスクとの関連付けを記録"""
        # ファイル名の生成（URLから安全なファイル名を作成）
        safe_filename = self._create_safe_filename(url)
        file_path = os.path.join(self.output_dir, f"{safe_filename}.md")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            # タスクとファイルの関連付けを記録
            self._record_task_file(task_id, safe_filename, url, file_path)
            
            logger.info(f"マークダウンファイルを保存しました: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"ファイル保存エラー: {e}")
            raise Exception(f"ファイルの保存に失敗しました: {e}")
    
    def _record_task_file(self, task_id: str, filename: str, original_url: str, file_path: str):
        """タスクとファイルの関連付けを記録"""
        task_file_path = os.path.join(self.task_files_dir, f"{task_id}.json")
        
        # 既存の記録を読み込み
        task_files = []
        if os.path.exists(task_file_path):
            try:
                with open(task_file_path, 'r', encoding='utf-8') as f:
                    task_files = json.load(f)
            except:
                task_files = []
        
        # 新しいファイル情報を追加
        file_info = {
            "filename": f"{filename}.md",
            "original_url": original_url,
            "file_path": file_path,
            "created_at": datetime.now().isoformat()
        }
        
        # 重複を避けて追加
        existing_filenames = [f["filename"] for f in task_files]
        if f"{filename}.md" not in existing_filenames:
            task_files.append(file_info)
        
        # 記録を保存
        with open(task_file_path, 'w', encoding='utf-8') as f:
            json.dump(task_files, f, ensure_ascii=False, indent=2)
    
    def get_task_files(self, task_id: str) -> List[Dict]:
        """タスクに紐づくファイル一覧を取得"""
        task_file_path = os.path.join(self.task_files_dir, f"{task_id}.json")
        
        if not os.path.exists(task_file_path):
            return []
        
        try:
            with open(task_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    
    def _create_safe_filename(self, url: str) -> str:
        """URLから安全なファイル名を生成（元のURLに近い形で保存）"""
        try:
            # URLをパース
            parsed = urlparse(url)
            
            # スキーム（http/https）を除去
            scheme_removed = url.replace(f"{parsed.scheme}://", "")
            
            # ファイルシステムで使用できない文字を置換
            # より安全で読みやすい文字に置換
            safe_filename = scheme_removed.replace("/", "_")
            safe_filename = safe_filename.replace("\\", "_")
            safe_filename = safe_filename.replace(":", "_")
            safe_filename = safe_filename.replace("*", "_")
            safe_filename = safe_filename.replace("?", "_")
            safe_filename = safe_filename.replace('"', "_")
            safe_filename = safe_filename.replace("<", "_")
            safe_filename = safe_filename.replace(">", "_")
            safe_filename = safe_filename.replace("|", "_")
            safe_filename = safe_filename.replace(" ", "_")
            
            # 連続するアンダースコアを単一のアンダースコアに置換
            safe_filename = re.sub(r'_+', '_', safe_filename)
            
            # 先頭と末尾のアンダースコアを除去
            safe_filename = safe_filename.strip('_')
            
            # 空文字列の場合はデフォルト名を使用
            if not safe_filename:
                safe_filename = "index"
            
            # 長すぎる場合は短縮（ファイルシステムの制限を考慮）
            if len(safe_filename) > 200:  # より長いファイル名を許可
                # ドメイン部分を保持し、パス部分を短縮
                domain_part = parsed.netloc
                path_part = parsed.path[:100]  # パス部分を100文字に制限
                safe_filename = f"{domain_part}_{path_part}".replace("/", "_")
                safe_filename = re.sub(r'_+', '_', safe_filename)
                safe_filename = safe_filename.strip('_')
            
            # 最終的な安全チェック
            safe_filename = re.sub(r'[^\w\-_.]', '_', safe_filename)
            
            logger.info(f"URL '{url}' からファイル名 '{safe_filename}.md' を生成しました")
            return safe_filename
            
        except Exception as e:
            logger.error(f"ファイル名生成でエラーが発生しました: {e}")
            # エラーが発生した場合は従来の方法を使用
            parsed = urlparse(url)
            domain = parsed.netloc.replace('.', '_')
            path = parsed.path.strip('/')
            if path:
                filename = path.split('/')[-1]
                if filename:
                    filename = filename.split('.')[0]
                else:
                    filename = "index"
            else:
                filename = "index"
            
            safe_filename = re.sub(r'[^\w\-_]', '_', f"{domain}_{filename}")
            if len(safe_filename) > 100:
                safe_filename = safe_filename[:100]
            
            return safe_filename
    
    def process_excel_file(self, file_path: str, task_id: str, progress_callback: Optional[Callable] = None) -> Tuple[int, int, List[str]]:
        """Excelファイルを処理してスクレイピングとマークダウン生成を実行"""
        try:
            # URLの読み込み
            urls = self.read_excel_urls(file_path)
            if not urls:
                raise Exception("有効なURLが見つかりませんでした")
            
            total_urls = len(urls)
            processed_count = 0
            generated_count = 0
            errors = []
            
            # 初期進捗を通知
            if progress_callback:
                progress_callback(0.0, 0, total_urls, "スクレイピング処理を開始しました")
            
            # 各URLを処理
            for i, url in enumerate(urls, 1):
                try:
                    logger.info(f"処理中: {i}/{total_urls} - {url}")
                    
                    # 進捗を更新
                    progress = i / total_urls
                    if progress_callback:
                        progress_callback(progress, i, total_urls, f"URL {i}/{total_urls} を処理中: {url}")
                    
                    # スクレイピング
                    scraped_data = self.scrape_url(url)
                    processed_count += 1
                    
                    # エラーがない場合のみマークダウン生成
                    if not scraped_data['error']:
                        markdown_content = self.generate_markdown(scraped_data)
                        self.save_markdown(markdown_content, url, task_id)
                        generated_count += 1
                        
                        # 成功時の進捗更新
                        if progress_callback:
                            progress_callback(progress, i, total_urls, f"URL {i}/{total_urls} 完了: {url}")
                    else:
                        errors.append(f"{url}: {scraped_data['error']}")
                        
                        # エラー時の進捗更新
                        if progress_callback:
                            progress_callback(progress, i, total_urls, f"URL {i}/{total_urls} エラー: {url}")
                    
                except Exception as e:
                    logger.error(f"URL処理エラー ({url}): {e}")
                    errors.append(f"{url}: {e}")
                    
                    # エラー時の進捗更新
                    if progress_callback:
                        progress = i / total_urls
                        progress_callback(progress, i, total_urls, f"URL {i}/{total_urls} 例外エラー: {url}")
            
            # 完了時の進捗更新
            if progress_callback:
                progress_callback(1.0, total_urls, total_urls, f"処理完了: {generated_count}個のマークダウンファイルを生成しました")
            
            logger.info(f"処理完了: {processed_count}個のURLを処理し、{generated_count}個のマークダウンファイルを生成しました")
            
            return processed_count, generated_count, errors
            
        except Exception as e:
            logger.error(f"Excelファイル処理エラー: {e}")
            raise Exception(f"Excelファイルの処理に失敗しました: {e}")
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """古いファイルを削除"""
        try:
            current_time = datetime.now()
            deleted_count = 0
            
            for filename in os.listdir(self.output_dir):
                if filename.endswith('.md'):
                    file_path = os.path.join(self.output_dir, filename)
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    
                    if (current_time - file_time).total_seconds() > max_age_hours * 3600:
                        os.remove(file_path)
                        deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"{deleted_count}個の古いファイルを削除しました")
                
        except Exception as e:
            logger.error(f"ファイルクリーンアップエラー: {e}")
    
    def cleanup_task_files(self, task_id: str):
        """タスクに関連するファイルを削除"""
        try:
            # タスクファイルの記録を読み込み
            task_file_path = os.path.join(self.task_files_dir, f"{task_id}.json")
            if os.path.exists(task_file_path):
                try:
                    with open(task_file_path, 'r', encoding='utf-8') as f:
                        task_files = json.load(f)
                    
                    # 関連するマークダウンファイルを削除
                    deleted_markdown_count = 0
                    for file_info in task_files:
                        file_path = file_info.get("file_path")
                        if file_path and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                                deleted_markdown_count += 1
                                logger.info(f"マークダウンファイルを削除しました: {file_path}")
                            except Exception as e:
                                logger.error(f"マークダウンファイルの削除に失敗しました: {file_path} - {e}")
                    
                    if deleted_markdown_count > 0:
                        logger.info(f"タスク {task_id} に関連する {deleted_markdown_count} 個のマークダウンファイルを削除しました")
                    
                except Exception as e:
                    logger.error(f"タスクファイルの読み込みでエラーが発生しました: {e}")
                
                # タスクファイルの記録を削除
                try:
                    os.remove(task_file_path)
                    logger.info(f"タスク {task_id} のファイル記録を削除しました")
                except Exception as e:
                    logger.error(f"タスクファイル記録の削除に失敗しました: {e}")
            else:
                logger.info(f"タスク {task_id} のファイル記録が見つかりませんでした")
                
        except Exception as e:
            logger.error(f"タスクファイルクリーンアップエラー: {e}")
    
    def close(self):
        """WebDriverを閉じる"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriverを閉じました")
            except Exception as e:
                logger.error(f"WebDriverのクローズでエラーが発生しました: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
