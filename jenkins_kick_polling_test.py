import requests
import time
import os

# Jenkins の設定
JENKINS_URL = "https://jenkins.example.com"  # あなたのJenkins URL
JOB_PATH    = "my-job"                       # フォルダなしの場合
JOB_TOKEN   = "abc123"                       # 「Build Triggers」で設定したトークン
JENKINS_USER = os.getenv("JENKINS_USER", "user")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN", "apitoken")


# パラメータ（ジョブで定義されている必要あり）
params = {
    "NEW_TAG": "001-20250117",
    "OLD_TAG": "000-20250116",
    "GIT_USER": "user",
    "GIT_TOKEN": "token",
    "WORK_ENV": "dv0",
}

# ポーリング設定
QUEUE_WAIT_SEC = 300
BUILD_WAIT_SEC = 1800
POLL_INTERVAL = 2.0
TIMEOUT = (10, 30)

def trigger_jenkins_build():
    """Jenkinsビルドをトリガーしてqueue URLを取得"""
    # URLを組み立て
    url = f"{JENKINS_URL}/job/{JOB_PATH}/buildWithParameters?token={JOB_TOKEN}"
    
    print(f"Triggering Jenkins build: {url}")
    print(f"Parameters: {params}")
    
    # POSTでパラメータ送信
    resp = requests.post(url, data=params, auth=(JENKINS_USER, JENKINS_TOKEN), 
                        timeout=TIMEOUT, verify=False)
    
    print("status:", resp.status_code)
    print("headers:", resp.headers)
    print("text:", resp.text)
    
    resp.raise_for_status()
    queue_url = resp.headers.get("Location")
    if not queue_url:
        raise RuntimeError("Jenkins: queue Location header がありません。")
    
    print(f"Jenkins queued: {queue_url}")
    return queue_url

def resolve_queue_to_build(queue_url):
    """QueueからBuild URLを解決"""
    api = queue_url.rstrip("/") + "/api/json"
    deadline = time.time() + QUEUE_WAIT_SEC
    
    print(f"Resolving queue to build: {api}")
    
    while time.time() < deadline:
        q = requests.get(api, auth=(JENKINS_USER, JENKINS_TOKEN), 
                        timeout=TIMEOUT, verify=False)
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

def wait_for_build_result(build_url):
    """ビルド完了まで待機"""
    api = build_url.rstrip("/") + "/api/json"
    deadline = time.time() + BUILD_WAIT_SEC
    
    print(f"Waiting for build result: {api}")
    
    while time.time() < deadline:
        r = requests.get(api, auth=(JENKINS_USER, JENKINS_TOKEN), 
                        timeout=TIMEOUT, verify=False)
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
    try:
        # 1) Jenkinsビルドをトリガー
        queue_url = trigger_jenkins_build()
        
        # 2) QueueからBuild URLを解決
        build_url = resolve_queue_to_build(queue_url)
        
        # 3) ビルド完了まで待機
        result = wait_for_build_result(build_url)
        
        if result in ("SUCCESS", "UNSTABLE"):
            print(f"✅ Jenkins build completed successfully: {result}")
        else:
            print(f"❌ Jenkins build failed: {result}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
