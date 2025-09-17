import requests
import time
import os

# Jenkins の設定
JENKINS_BASE = os.getenv("JENKINS_BASE", "https://jenkins.example.com")
JENKINS_JOB = os.getenv("JENKINS_JOB", "job/my-folder/job/my-job")
JENKINS_USER = os.getenv("JENKINS_USER", "user")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN", "apitoken")
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() != "false"

# パラメータ
PARAMS = {
    "NEW_TAG": "001-20250117",
    "OLD_TAG": "000-20250116",
    "GIT_USER": "user",
    "GIT_TOKEN": "token",
    "WORK_ENV": "dv0",
}

QUEUE_WAIT_SEC = 300
BUILD_WAIT_SEC = 1800
POLL_INTERVAL = 2.0
TIMEOUT = (10, 30)

def jenkins_url(path: str) -> str:
    return f"{JENKINS_BASE.rstrip('/')}/{path.lstrip('/')}"

def trigger_jenkins_build(session: requests.Session, params: dict) -> str:
    """Jenkinsビルドをトリガーしてqueue URLを取得"""
    url = jenkins_url(f"{JENKINS_JOB}/buildWithParameters")
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    print(f"Triggering Jenkins build: {url}")
    print(f"Parameters: {params}")
    
    r = session.post(url, params=params, auth=auth,
                     allow_redirects=False, timeout=TIMEOUT, verify=VERIFY_SSL)
    
    print(f"Response status: {r.status_code}")
    print(f"Response headers: {dict(r.headers)}")
    
    r.raise_for_status()
    queue_url = r.headers.get("Location")
    if not queue_url:
        raise RuntimeError("Jenkins: queue Location header がありません。")
    
    print(f"Jenkins queued: {queue_url}")
    return queue_url

def resolve_queue_to_build(session: requests.Session, queue_url: str, wait_sec: int) -> str:
    """QueueからBuild URLを解決"""
    api = queue_url.rstrip("/") + "/api/json"
    deadline = time.time() + wait_sec
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    print(f"Resolving queue to build: {api}")
    
    while time.time() < deadline:
        q = session.get(api, auth=auth, timeout=TIMEOUT, verify=VERIFY_SSL)
        q.raise_for_status()
        data = q.json()
        
        print(f"Queue status: cancelled={data.get('cancelled')}, executable={data.get('executable')}")
        
        if data.get("cancelled"):
            raise RuntimeError("Jenkins: queue cancelled")
        
        exe = data.get("executable")
        if exe and exe.get("url"):
            build_url = exe["url"]
            print(f"Queue resolved to build: {build_url}")
            return build_url
        
        time.sleep(POLL_INTERVAL)
    
    raise TimeoutError("Jenkins: queue → build 解決タイムアウト")

def wait_for_build_result(session: requests.Session, build_url: str, wait_sec: int) -> str:
    """ビルド完了まで待機"""
    api = build_url.rstrip("/") + "/api/json"
    deadline = time.time() + wait_sec
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    print(f"Waiting for build result: {api}")
    
    while time.time() < deadline:
        r = session.get(api, auth=auth, timeout=TIMEOUT, verify=VERIFY_SSL)
        r.raise_for_status()
        j = r.json()
        result = j.get("result")
        
        print(f"Build status: {result}")
        
        if result is not None:
            print(f"Jenkins result: {result}")
            return result
        
        time.sleep(POLL_INTERVAL)
    
    raise TimeoutError("Jenkins: ビルド完了待ちタイムアウト")

def main():
    """メイン処理"""
    s = requests.Session()
    
    # セッションをクリーンに初期化
    s.auth = None
    s.proxies = {}
    s.verify = VERIFY_SSL
    
    # 環境変数のプロキシ設定を一時的に無効化
    import os
    original_http_proxy = os.environ.pop('HTTP_PROXY', None)
    original_https_proxy = os.environ.pop('HTTPS_PROXY', None)
    
    try:
        # 1) Jenkinsビルドをトリガー
        queue_url = trigger_jenkins_build(s, PARAMS)
        
        # 2) QueueからBuild URLを解決
        build_url = resolve_queue_to_build(s, queue_url, QUEUE_WAIT_SEC)
        
        # 3) ビルド完了まで待機
        result = wait_for_build_result(s, build_url, BUILD_WAIT_SEC)
        
        if result in ("SUCCESS", "UNSTABLE"):
            print(f"✅ Jenkins build completed successfully: {result}")
        else:
            print(f"❌ Jenkins build failed: {result}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # 環境変数を復元
        if original_http_proxy:
            os.environ['HTTP_PROXY'] = original_http_proxy
        if original_https_proxy:
            os.environ['HTTPS_PROXY'] = original_https_proxy

if __name__ == "__main__":
    main()
