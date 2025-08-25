#!/usr/bin/env python3
"""
ChromeDriverセットアップ支援スクリプト
"""

import os
import sys
import platform
import subprocess
import urllib.request
import zipfile
import tarfile
import shutil

def get_chrome_version():
    """Chromeのバージョンを取得"""
    try:
        if platform.system() == "Windows":
            # Windowsの場合
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
            version, _ = winreg.QueryValueEx(key, "version")
            return version
        elif platform.system() == "Darwin":
            # macOSの場合
            result = subprocess.run(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'], 
                                 capture_output=True, text=True)
            return result.stdout.strip().split()[-1]
        else:
            # Linuxの場合
            result = subprocess.run(['google-chrome', '--version'], capture_output=True, text=True)
            return result.stdout.strip().split()[-1]
    except Exception as e:
        print(f"Chromeのバージョン取得に失敗しました: {e}")
        return None

def download_chromedriver(version):
    """ChromeDriverをダウンロード"""
    # メジャーバージョンを取得
    major_version = version.split('.')[0]
    
    # ダウンロードURL
    base_url = "https://chromedriver.storage.googleapis.com"
    
    # 利用可能なバージョンを確認
    try:
        version_url = f"{base_url}/LATEST_RELEASE_{major_version}"
        with urllib.request.urlopen(version_url) as response:
            chromedriver_version = response.read().decode('utf-8').strip()
    except:
        print(f"ChromeDriver {major_version}系の最新バージョンが見つかりません")
        return None
    
    print(f"ChromeDriver {chromedriver_version} をダウンロード中...")
    
    # プラットフォームに応じたファイル名
    if platform.system() == "Windows":
        filename = "chromedriver_win32.zip"
    elif platform.system() == "Darwin":
        if platform.machine() == "arm64":
            filename = "chromedriver_mac_arm64.zip"
        else:
            filename = "chromedriver_mac64.zip"
    else:
        filename = "chromedriver_linux64.zip"
    
    download_url = f"{base_url}/{chromedriver_version}/{filename}"
    
    try:
        # ダウンロード
        urllib.request.urlretrieve(download_url, filename)
        print(f"ダウンロード完了: {filename}")
        
        # 解凍
        if filename.endswith('.zip'):
            with zipfile.ZipFile(filename, 'r') as zip_ref:
                zip_ref.extractall('.')
        elif filename.endswith('.tar.gz'):
            with tarfile.open(filename, 'r:gz') as tar_ref:
                tar_ref.extractall('.')
        
        # 実行権限を付与（Linux/macOS）
        if platform.system() != "Windows":
            os.chmod("chromedriver", 0o755)
        
        # ダウンロードファイルを削除
        os.remove(filename)
        
        print("ChromeDriverのセットアップが完了しました！")
        return True
        
    except Exception as e:
        print(f"ChromeDriverのダウンロードに失敗しました: {e}")
        return False

def main():
    """メイン処理"""
    print("ChromeDriverセットアップ支援スクリプト")
    print("=" * 50)
    
    # Chromeのバージョンを確認
    chrome_version = get_chrome_version()
    if not chrome_version:
        print("Chromeがインストールされていないか、バージョンの取得に失敗しました")
        print("Chromeをインストールしてから再実行してください")
        return
    
    print(f"Chromeバージョン: {chrome_version}")
    
    # ChromeDriverが既に存在するかチェック
    if os.path.exists("chromedriver") or os.path.exists("chromedriver.exe"):
        print("ChromeDriverは既に存在します")
        return
    
    # ChromeDriverをダウンロード
    if download_chromedriver(chrome_version):
        print("\nセットアップ完了！")
        print("以下のコマンドでアプリケーションを起動できます:")
        print("python run_app.py")
    else:
        print("\nセットアップに失敗しました")
        print("手動でChromeDriverをダウンロードしてください:")
        print("https://chromedriver.chromium.org/")

if __name__ == "__main__":
    main()
