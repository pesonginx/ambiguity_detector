"""
Orchestrator:
1) Jenkins buildWithParameters 起動（NEW/OLD/GIT_USER/GIT_TOKEN）
2) ビルド完了まで待機（SUCCESS/UNSTABLE）
3) n8n Flow1 を同期呼び出し（200なら）
4) n8n Flow2 を同期呼び出し（200なら）
5) n8n Flow3 を同期呼び出し
※ 各フローの返り値は次に渡さない
"""

import os, time, json, logging, requests
from typing import Dict, Tuple
from requests.auth import HTTPBasicAuth

# ===== 設定 =====
JENKINS_BASE = os.getenv("JENKINS_BASE", "https://jenkins.example.com")
JENKINS_JOB  = os.getenv("JENKINS_JOB",  "job/my-folder/job/my-job")  # 完全なジョブパスを指定
JENKINS_USER = os.getenv("JENKINS_USER", "user")
JENKINS_TOKEN= os.getenv("JENKINS_TOKEN","apitoken")
VERIFY_SSL   = os.getenv("VERIFY_SSL", "true").lower() != "false"

PARAMS = {
    "NEW_TAG":   os.getenv("NEW_TAG", "NNN-20250917"),
    "OLD_TAG":   os.getenv("OLD_TAG", "NNN-20250916"),
    "GIT_USER":  os.getenv("GIT_USER", ""),
    "GIT_TOKEN": os.getenv("GIT_TOKEN",""),
}

QUEUE_WAIT_SEC = int(300)
BUILD_WAIT_SEC = int(1800)
POLL_INTERVAL  = float(2)

# n8n
N8N_FLOW1_URL = os.getenv("N8N_FLOW1_URL", "https://n8n/webhook/flow1")
N8N_FLOW2_URL = os.getenv("N8N_FLOW2_URL", "https://n8n/webhook/flow2")
N8N_FLOW3_URL = os.getenv("N8N_FLOW3_URL", "https://n8n/webhook/flow3")
N8N_SEND_JSON = os.getenv("N8N_SEND_JSON", "false").lower() == "true"

TIMEOUT: Tuple[int,int] = (10, 30)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")

# ===== Jenkins =====
def jenkins_url(path: str) -> str:
    return f"{JENKINS_BASE.rstrip('/')}/{path.lstrip('/')}"

def trigger_jenkins_build(session: requests.Session, params: Dict[str, str]) -> str:
    url = jenkins_url(f"{JENKINS_JOB}/buildWithParameters")
    r = session.post(url, params=params,
                     allow_redirects=False, timeout=TIMEOUT, verify=VERIFY_SSL)
    r.raise_for_status()
    queue_url = r.headers.get("Location")
    if not queue_url:
        raise RuntimeError("Jenkins: queue Location header がありません。")
    logging.info("Jenkins queued: %s", queue_url)
    return queue_url

def resolve_queue_to_build(session: requests.Session, queue_url: str, wait_sec: int) -> str:
    api = queue_url.rstrip("/") + "/api/json"
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        q = session.get(api, timeout=TIMEOUT, verify=VERIFY_SSL)
        q.raise_for_status()
        data = q.json()
        if data.get("cancelled"):
            raise RuntimeError("Jenkins: queue cancelled")
        exe = data.get("executable")
        if exe and exe.get("url"):
            build_url = exe["url"]
            logging.info("Queue resolved to build: %s", build_url)
            return build_url
        time.sleep(POLL_INTERVAL)
    raise TimeoutError("Jenkins: queue → build 解決タイムアウト")

def wait_for_build_result(session: requests.Session, build_url: str, wait_sec: int) -> str:
    api = build_url.rstrip("/") + "/api/json"
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        r = session.get(api, timeout=TIMEOUT, verify=VERIFY_SSL)
        r.raise_for_status()
        j = r.json()
        result = j.get("result")
        if result is not None:
            logging.info("Jenkins result: %s", result)
            return result
        time.sleep(POLL_INTERVAL)
    raise TimeoutError("Jenkins: ビルド完了待ちタイムアウト")

# ===== n8n =====
def build_n8n_payload() -> Dict[str, str]:
    return {
        "newTag":   PARAMS["NEW_TAG"],
        "oldTag":   PARAMS["OLD_TAG"],
        "gitUser":  PARAMS["GIT_USER"],
        "gitToken": PARAMS["GIT_TOKEN"],
    }

def call_n8n_sync(url: str, payload: Dict[str, str]) -> requests.Response:
    headers = {"Content-Type": "application/json"} if N8N_SEND_JSON else {"Content-Type": "application/x-www-form-urlencoded"}
    data = json.dumps(payload) if N8N_SEND_JSON else payload
    r = requests.post(url, headers=headers, data=data, timeout=TIMEOUT, verify=VERIFY_SSL)
    logging.info("Call %s → %s", url, r.status_code)
    return r

# ===== メイン =====
def main():
    s = requests.Session()
    s.auth = HTTPBasicAuth(JENKINS_USER, JENKINS_TOKEN)

    # Jenkins
    queue_url = trigger_jenkins_build(s, PARAMS)
    build_url = resolve_queue_to_build(s, queue_url, QUEUE_WAIT_SEC)
    result = wait_for_build_result(s, build_url, BUILD_WAIT_SEC)
    if result not in ("SUCCESS", "UNSTABLE"):
        raise SystemExit(f"Jenkins finished with {result} → n8n は実行しません。")

    payload = build_n8n_payload()

    # Flow1
    r1 = call_n8n_sync(N8N_FLOW1_URL, payload)
    if r1.status_code != 200:
        logging.warning("Flow1 status=%s → Flow2/Flow3 スキップ", r1.status_code)
        return

    # Flow2
    r2 = call_n8n_sync(N8N_FLOW2_URL, payload)
    if r2.status_code != 200:
        logging.warning("Flow2 status=%s → Flow3 スキップ", r2.status_code)
        return

    # Flow3
    r3 = call_n8n_sync(N8N_FLOW3_URL, payload)
    if r3.status_code == 200:
        logging.info("Flow3 完了 (200)")
    else:
        logging.warning("Flow3 status=%s", r3.status_code)

if __name__ == "__main__":
    main()
