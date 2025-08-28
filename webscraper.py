import re
import time
from typing import Tuple, Optional
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup
import html2text
import pandas as pd
import os
from datetime import datetime

from app.core.config import settings


class WebScraperClient:
    def __init__(self, headless: bool = True, wait_time: int = 10):
        """
        Initialize the web scraper client with Chrome WebDriver.
        """
        self.driver_path = settings.DRIVER_PATH
        self.wait_time = wait_time
        self.setup_driver(headless)
        self.setup_html2text()

    def setup_driver(self, headless: bool):
        """chromedriverのオプション設定"""
        options = Options()
        if headless:
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

        service = Service(self.driver_path)
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, self.wait_time)

    def setup_html2text(self) -> None:
        """html2textコンバータ（マークダウン化）の設定"""
        self.h = html2text.HTML2Text()
        self.h.ignore_links = False
        self.h.ignore_images = False
        self.h.body_width = 0  # No line wrapping
        self.h.unicode_snob = True
        self.h.skip_internal_links = False
        self.h.ignore_tables = False  # 表をhtml形式にする

    def remove_unwanted_elements(self, soup: BeautifulSoup) -> BeautifulSoup:
        """
        navigation, sidebar等の不要要素を除外する
        """
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
        """
        McAfee Web Gatewayの画面対応を行う
        """
        try:
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, "lxml")

            if (
                "McAfee Web Gateway" in soup.text
                or "blocked by the URL Filter database" in soup.text
            ):
                print("Detected McAfee Web Gateway screen")

                # "Yes, I want to continue the session!" ボタンを探してクリックする
                continue_button = self.driver.find_element(
                    "xpath",
                    "//input[@type='button' and @value='Yes, I want to continue the session!']",
                )
                if continue_button:
                    print("Clicking 'Continue' button to bypass McAfee Gateway")
                    self.driver.execute_script("arguments[0].click();", continue_button)
                    time.sleep(3)  # 遷移のために待機
                    return True
                else:
                    print("No 'Continue' button found on McAfee Gateway screen")
                    return False
            else:
                print("McAfee Web Gateway screen not detected")
                return False
        except Exception as e:
            print(f"Error handling McAfee Web Gateway: {str(e)}")
            return False

    def get_content_selector(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        URL patternに応じて取得する内容を設定する
        """
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
        """
        ウェブページから内容を抽出する
        """
        try:
            print(f"Accessing: {url}")
            self.driver.get(url)
            time.sleep(3)  # Wait for page to load

            # McAfee Web Gateway対応
            if not self.handle_mcafee_gateway():
                print("Aborting due to McAfee Web Gateway handling failure")
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
                    print(f"Found specific content selector: {selector_type}={selector_value}")
                    return content
                else:
                    print("Specific selector not found, falling back to general extraction")

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
                    print(f"Found main content using: {selector_type}={selector_value}")
                    break

            if not main_content:
                # If no main content found, use body but remove unwanted elements
                main_content = soup.find("body")
            if main_content:
                main_content = self.remove_unwanted_elements(main_content)
                print("Using body content after removing unwanted elements")

            return main_content if main_content else soup

        except Exception as e:
            print(f"Error extracting content from {url}: {str(e)}")
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
        markdown = self.h.handle(html_content)

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

    def scrape_url(self, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        ウェブページのURLをスクレイピングして、マークダウンに変換する。
        """
        try:
            content_soup = self.extract_content(url)
            if content_soup:
                markdown = self.convert_to_markdown(content_soup, url)
                return {
                    "success": True,
                    "content": markdown,
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "content": None,
                    "error": "Failed to extract content from the page.",
                }
        except Exception as e:
            return {
                "success": False,
                "content": None,
                "error": f"An error occurred while scraping the URL: {str(e)}",
            }

    def close(self) -> None:
        """Close the webdriver"""
        if hasattr(self, "driver"):
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[object]) -> None:
        self.close()


def create_safe_filename(url: str, index: int) -> str:
    """
    URLから安全なファイル名を生成する
    """
    try:
        # URLをパース
        parsed = urlparse(url)
        
        # ドメイン名を取得
        domain = parsed.netloc.replace('www.', '').replace('.', '_')
        
        # パスからファイル名部分を取得
        path = parsed.path.strip('/')
        if path:
            # パスを安全な文字に変換
            safe_path = re.sub(r'[^\w\-_.]', '_', path)
            # 長すぎる場合は短縮
            if len(safe_path) > 50:
                safe_path = safe_path[:50]
        else:
            safe_path = "index"
        
        # タイムスタンプ
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # ファイル名を組み立て
        filename = f"{domain}_{safe_path}_{timestamp}.md"
        
        # ファイル名が長すぎる場合は短縮
        if len(filename) > 200:
            filename = f"{domain}_{index:03d}_{timestamp}.md"
        
        return filename
    except Exception:
        # エラーの場合はフォールバック
        return f"scraped_{index:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"


def main():
    """
    ExcelファイルのURL列からURLを読み込んで順次スクレイピング処理を行う
    """
    # 入力ファイルのパス
    input_file = "input.xlsx"
    
    # 出力ディレクトリの作成
    output_dir = "scraped_content"
    os.makedirs(output_dir, exist_ok=True)
    
    # 結果を保存するリスト
    results = []
    
    try:
        # Excelファイルを読み込み
        print(f"Excelファイル '{input_file}' を読み込んでいます...")
        df = pd.read_excel(input_file)
        
        # URL列の存在確認
        if 'url' not in df.columns:
            print("エラー: 'url'列が見つかりません。列名を確認してください。")
            return
        
        # html列の存在確認
        if 'html' not in df.columns:
            print("警告: 'html'列が見つかりません。guide.line.meのURLの場合はHTMLコンテンツを取得できません。")
        
        # URLの数を表示
        url_count = len(df['url'].dropna())
        print(f"処理対象のURL数: {url_count}")
        
        # WebScraperClientの初期化
        with WebScraperClient(headless=True, wait_time=10) as scraper:
            for index, row in df.iterrows():
                url = row['url']
                
                # URLが空の場合はスキップ
                if pd.isna(url) or url.strip() == '':
                    print(f"行 {index + 1}: URLが空のためスキップ")
                    continue
                
                print(f"\n行 {index + 1}/{url_count}: {url} を処理中...")
                
                try:
                    # guide.line.meのURLの場合は、HTML列から直接処理
                    if url.startswith("https://guide.line.me/"):
                        print("  guide.line.meのURLを検出 - HTML列から直接処理します")
                        
                        # HTML列の存在確認
                        if 'html' in df.columns and not pd.isna(row['html']):
                            html_content = row['html']
                            print(f"  HTML列からコンテンツを読み込みました（長さ: {len(html_content)}文字）")
                            
                            # HTMLをBeautifulSoupでパース
                            soup = BeautifulSoup(html_content, "lxml")
                            
                            # 不要要素の除去
                            soup = scraper.remove_unwanted_elements(soup)
                            
                            # マークダウン化
                            markdown_content = scraper.convert_to_markdown(soup, url)
                            
                            result = {
                                'success': True,
                                'content': markdown_content,
                                'error': None
                            }
                        else:
                            print("  HTML列が空または存在しないため、スクレイピングを実行します")
                            result = scraper.scrape_url(url)
                    else:
                        # 通常のスクレイピング処理
                        result = scraper.scrape_url(url)
                    
                    # 結果を保存
                    result_data = {
                        'row_index': index + 1,
                        'url': url,
                        'success': result['success'],
                        'error': result['error'],
                        'timestamp': datetime.now().isoformat()
                    }
                    results.append(result_data)
                    
                    if result['success']:
                        print(f"✓ 成功: コンテンツを取得しました")
                        
                        # URLベースのファイル名を生成
                        filename = create_safe_filename(url, index + 1)
                        filepath = os.path.join(output_dir, filename)
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(f"# スクレイピング結果\n\n")
                            f.write(f"**URL:** {url}\n\n")
                            f.write(f"**取得日時:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                            f.write(f"---\n\n")
                            f.write(result['content'])
                        
                        print(f"  ファイル保存: {filepath}")
                        result_data['output_file'] = filepath
                        
                    else:
                        print(f"✗ 失敗: {result['error']}")
                        result_data['output_file'] = None
                        
                except Exception as e:
                    error_msg = f"処理中にエラーが発生: {str(e)}"
                    print(f"✗ エラー: {error_msg}")
                    
                    result_data = {
                        'row_index': index + 1,
                        'url': url,
                        'success': False,
                        'error': error_msg,
                        'timestamp': datetime.now().isoformat(),
                        'output_file': None
                    }
                    results.append(result_data)
                
                # 処理間隔を設ける（サーバーに負荷をかけないため）
                time.sleep(2)
        
        # 結果サマリーの表示
        print(f"\n{'='*50}")
        print("処理完了サマリー")
        print(f"{'='*50}")
        
        success_count = sum(1 for r in results if r['success'])
        error_count = len(results) - success_count
        
        print(f"総処理数: {len(results)}")
        print(f"成功: {success_count}")
        print(f"失敗: {error_count}")
        print(f"成功率: {success_count/len(results)*100:.1f}%" if results else "0%")
        
        # 結果をExcelファイルとして保存
        results_df = pd.DataFrame(results)
        output_excel = f"scraping_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        results_df.to_excel(output_excel, index=False)
        print(f"\n結果を '{output_excel}' に保存しました")
        
        # 失敗したURLの一覧表示
        if error_count > 0:
            print(f"\n失敗したURL:")
            for result in results:
                if not result['success']:
                    print(f"  - {result['url']} (エラー: {result['error']})")
        
    except FileNotFoundError:
        print(f"エラー: ファイル '{input_file}' が見つかりません。")
    except Exception as e:
        print(f"予期しないエラーが発生しました: {str(e)}")


if __name__ == "__main__":
    main()
