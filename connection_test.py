import os
import requests
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

# プロキシ設定（.envから取得）
HTTP_PROXY = os.getenv('HTTP_PROXY')
HTTPS_PROXY = os.getenv('HTTPS_PROXY')

def test_connection():
    """接続テストを実行"""
    print("=== 接続テスト開始 ===")
    
    # プロキシ設定
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
        print(f"HTTP_PROXY: {HTTP_PROXY}")
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
        print(f"HTTPS_PROXY: {HTTPS_PROXY}")
    
    if not proxies:
        print("プロキシ設定なし - 直接接続")
    else:
        print(f"プロキシ設定: {proxies}")
    
    print()
    
    # テスト用URL（複数試す）
    test_urls = [
        "https://gitlab.com",       # GitLab
    ]
    
    for url in test_urls:
        print(f"テスト中: {url}")
        try:
            response = requests.get(url, proxies=proxies, timeout=10)
            print(f"  ✅ 成功 - ステータス: {response.status_code}")
            print(f"  �� レスポンス時間: {response.elapsed.total_seconds():.2f}秒")
        except requests.exceptions.ProxyError as e:
            print(f"  ❌ プロキシエラー: {e}")
        except requests.exceptions.ConnectTimeout as e:
            print(f"  ❌ タイムアウト: {e}")
        except requests.exceptions.ConnectionError as e:
            print(f"  ❌ 接続エラー: {e}")
        except requests.exceptions.HTTPError as e:
            print(f"  ❌ HTTPエラー: {e}")
        except Exception as e:
            print(f"  ❌ その他のエラー: {e}")
        print()

def test_gitlab_api():
    """GitLab API接続テスト"""
    print("=== GitLab API接続テスト ===")
    
    # 設定（実際の値に変更してください）
    API_BASE = "https://gitlab.com/api/v4"
    PROJECT_ID = "your-group%2Fyour-repo"
    TOKEN = "YOUR_GITLAB_TOKEN"
    
    if TOKEN == "YOUR_GITLAB_TOKEN":
        print("⚠️  TOKENが設定されていません。.envファイルでTOKENを設定してください。")
        return
    
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    
    headers = {"PRIVATE-TOKEN": TOKEN}
    url = f"{API_BASE}/projects/{PROJECT_ID}"
    
    try:
        print(f"テスト中: {url}")
        response = requests.get(url, headers=headers, proxies=proxies, timeout=30)
        print(f"  ✅ 成功 - ステータス: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  �� プロジェクト名: {data.get('name', 'N/A')}")
    except Exception as e:
        print(f"  ❌ エラー: {e}")

if __name__ == "__main__":
    test_connection()
    print()
    test_gitlab_api()
    print("=== テスト完了 ===")