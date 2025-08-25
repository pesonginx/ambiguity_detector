import re
import time
from typing import Tuple, Optional
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup
import html2text

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
