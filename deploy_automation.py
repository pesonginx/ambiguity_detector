"""
デプロイOrchestrator:
1) ファイルpush/tag作成（オプション）
2) タグ差分チェック（JSONファイルで管理）
3) Jenkins buildWithParameters 起動（NEW/OLD/GIT_USER/GIT_TOKEN/WORK_ENV）
4) ビルド完了まで待機（SUCCESS/UNSTABLE）
5) n8n Flow1 を呼び出し（200の場合のみ）
6) n8n Flow2 を呼び出し（200の場合のみ）
7) n8n Flow3 を呼び出し
"""

import os, time, json, logging, requests, argparse, re, glob, random
from typing import Dict, Tuple, Optional
from requests.auth import HTTPBasicAuth
from datetime import datetime
from zoneinfo import ZoneInfo
from git import Repo, GitCommandError

# ===== 設定 =====
JENKINS_BASE = os.getenv("JENKINS_BASE", "https://jenkins.example.com")
JENKINS_JOB  = os.getenv("JENKINS_JOB",  "job/my-folder/job/my-job")  # 完全なジョブパスを指定
JENKINS_USER = os.getenv("JENKINS_USER", "user")
JENKINS_TOKEN= os.getenv("JENKINS_TOKEN","apitoken")
VERIFY_SSL   = os.getenv("VERIFY_SSL", "true").lower() != "false"

# Git設定
REPO_URL = os.getenv("REPO_URL", "git@gitlab.com:your-group/your-repo.git")
PROJECT_ID = os.getenv("PROJECT_ID", "your-group%2Fyour-repo")
GIT_TOKEN = os.getenv("GIT_TOKEN", "YOUR_GITLAB_TOKEN")
API_BASE = os.getenv("API_BASE", "https://gitlab.com/api/v4")
BRANCH = os.getenv("BRANCH", "main")
WORKDIR = os.getenv("WORKDIR", "/path/to/local/repo")
TARGET_PATH = os.getenv("TARGET_PATH", ".")
COMMIT_MESSAGE = os.getenv("COMMIT_MESSAGE", "chore: update files")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tokyo")
TAG_MESSAGE = os.getenv("TAG_MESSAGE", "auto tag")

# プロキシ設定
HTTP_PROXY = os.getenv('HTTP_PROXY')
HTTPS_PROXY = os.getenv('HTTPS_PROXY')

# タグ情報保存ファイル
TAG_INFO_FILE = "tag_info.json"

# タグ形式: NNN-YYYYMMDD（例: 008-20250904）
TAG_PATTERN = re.compile(r"^(\d{3})-(\d{8})$")

PARAMS = {
    "NEW_TAG":   os.getenv("NEW_TAG", "NNN-20250917"),
    "OLD_TAG":   os.getenv("OLD_TAG", "NNN-20250916"),
    "GIT_USER":  os.getenv("GIT_USER", ""),
    "GIT_TOKEN": os.getenv("GIT_TOKEN", ""),
    "WORK_ENV":  "",  # argsで設定
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

# ===== 引数解析 =====
def parse_args():
    parser = argparse.ArgumentParser(description="自動デプロイオーケストレーター")
    parser.add_argument("--work-env", "-e", required=True, 
                       choices=["dv0", "dv1", "itb", "uat", "pda", "pdb"],
                       help="作業環境を指定")
    parser.add_argument("--skip-push", "-s", action="store_true", default=True,
                       help="ファイルpush/tag作成をスキップする（デフォルト: True）")
    parser.add_argument("--no-skip-push", "-n", action="store_false", dest="skip_push",
                       help="ファイルpush/tag作成を実行する")
    parser.add_argument("--index-name-short", "-i", required=True,
                       help="インデックス名の短縮名を指定")
    return parser.parse_args()

# ===== Jenkins =====
def jenkins_url(path: str) -> str:
    return f"{JENKINS_BASE.rstrip('/')}/{path.lstrip('/')}"

def trigger_jenkins_build(session: requests.Session, params: Dict[str, str]) -> str:
    url = jenkins_url(f"{JENKINS_JOB}/buildWithParameters")
    
    # プロキシ設定
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    
    r = session.post(url, params=params, proxies=proxies,
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
    
    # プロキシ設定
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    
    while time.time() < deadline:
        q = session.get(api, proxies=proxies, timeout=TIMEOUT, verify=VERIFY_SSL)
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
    
    # プロキシ設定
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    
    while time.time() < deadline:
        r = session.get(api, proxies=proxies, timeout=TIMEOUT, verify=VERIFY_SSL)
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
    # タグからNNN部分を抽出（例: "008-20250117" → "008"）
    def extract_tag_number(tag: str) -> str:
        if not tag:
            return ""
        m = TAG_PATTERN.match(tag)
        return m.group(1) if m else ""
    
    def extract_tag_date(tag: str) -> str:
        if not tag:
            return ""
        m = TAG_PATTERN.match(tag)
        return m.group(2) if m else ""
    
    return {
        "newTag":   extract_tag_number(PARAMS["NEW_TAG"]),
        "oldTag":   extract_tag_number(PARAMS["OLD_TAG"]),
        "newTagDate": extract_tag_date(PARAMS["NEW_TAG"]),
        "oldTagDate": extract_tag_date(PARAMS["OLD_TAG"]),
        "gitUser":  PARAMS["GIT_USER"] + "@gmail.com",
        "gitToken": PARAMS["GIT_TOKEN"],
        "workEnv":  PARAMS["WORK_ENV"],
        "indexNameShort": PARAMS["INDEX_NAME_SHORT"],
    }

def call_n8n_sync(url: str, payload: Dict[str, str]) -> requests.Response:
    headers = {"Content-Type": "application/json"} if N8N_SEND_JSON else {"Content-Type": "application/x-www-form-urlencoded"}
    data = json.dumps(payload) if N8N_SEND_JSON else payload
    
    # プロキシ設定
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    
    r = requests.post(url, headers=headers, data=data, proxies=proxies, timeout=TIMEOUT, verify=VERIFY_SSL)
    logging.info("Call %s → %s", url, r.status_code)
    return r

# ===== Git操作 =====
def ensure_repo(repo_url: str, branch: str, workdir: str):
    """
    手元のクローンを優先使用。無ければclone。
    """
    if not os.path.isdir(workdir):
        parent = os.path.dirname(os.path.abspath(workdir)) or "."
        os.makedirs(parent, exist_ok=True)
        logging.info(f"クローン中: {repo_url} -> {workdir}")
        Repo.clone_from(repo_url, workdir, branch=branch, single_branch=True)
    else:
        git_dir = os.path.join(workdir, ".git")
        if os.path.isdir(git_dir):
            repo = Repo(workdir)
            logging.info(f"リポジトリを確認中: {workdir}")
            
            # リモートから最新を取得（ローカル変更は保持）
            origin = repo.remotes.origin
            origin.fetch()
            
            # ブランチの存在確認と切り替え
            try:
                repo.git.checkout(branch)
                # リモートブランチにリセットはしない（ローカル変更を保持）
                logging.info(f"ブランチ '{branch}' に切り替え完了（ローカル変更保持）")
            except GitCommandError:
                # ブランチが存在しない場合は作成
                repo.git.checkout('-b', branch, f'origin/{branch}')
                logging.info(f"ブランチ '{branch}' を作成して切り替え完了")
        else:
            if not os.listdir(workdir):
                logging.info(f"新しいリポジトリを初期化中: {workdir}")
                repo = Repo.init(workdir)
                origin = repo.create_remote('origin', repo_url)
                origin.fetch()
                repo.git.checkout('-b', branch, f'origin/{branch}')
            else:
                raise RuntimeError(f"'{workdir}' は空でない非リポジトリです。")

def apply_file_changes(workdir: str):
    return

def stage_commit_push(workdir: str, target_path: str, branch: str, message: str):
    """
    GitPythonを使用してステージング、コミット、プッシュを実行
    """
    repo = Repo(workdir)
    
    # ブランチに切り替え
    logging.info(f"ブランチ '{branch}' に切り替え中...")
    repo.git.checkout(branch)
    
    # プロキシ設定を環境変数に設定
    env = os.environ.copy()
    if HTTP_PROXY:
        env['HTTP_PROXY'] = HTTP_PROXY
    if HTTPS_PROXY:
        env['HTTPS_PROXY'] = HTTPS_PROXY
    
    # プロキシ設定をGitに適用
    if HTTP_PROXY or HTTPS_PROXY:
        if HTTP_PROXY:
            repo.config_writer().set_value("http", "proxy", HTTP_PROXY).release()
        if HTTPS_PROXY:
            repo.config_writer().set_value("https", "proxy", HTTPS_PROXY).release()
    
    # 変更をステージング
    target = (target_path or ".").strip().strip("/")
    logging.info(f"変更をステージング中: {target}")
    
    # 全ての変更をステージング（追加・変更・削除）
    repo.git.add('-A', target if target else ".")
    
    # ステージングされた変更を確認
    staged_files = repo.index.diff("HEAD")
    if staged_files:
        logging.info(f"ステージングされたファイル数: {len(staged_files)}")
        for item in staged_files:
            logging.info(f"  - {item.a_path}")
        
        # コミット
        logging.info(f"コミット中: {message}")
        repo.index.commit(message)
        
        # プッシュ
        logging.info(f"プッシュ中: origin/{branch}")
        origin = repo.remotes.origin
        origin.push(branch)
        logging.info("プッシュ完了")
    else:
        logging.info("ステージングする変更がありません")
        # 変更がなくても一応 push 試行（no-op）
        try:
            origin = repo.remotes.origin
            origin.push(branch)
            logging.info("プッシュ完了（変更なし）")
        except GitCommandError as e:
            logging.info(f"プッシュスキップ: {e}")

def iter_tags(api_base: str, project_id: str, token: str, per_page: int = 100):
    headers = {"PRIVATE-TOKEN": token}
    
    # プロキシ設定
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    
    page = 1
    while True:
        url = f"{api_base}/projects/{project_id}/repository/tags"
        params = {"order_by": "updated", "sort": "desc", "per_page": per_page, "page": page}
        resp = requests.get(url, headers=headers, params=params, proxies=proxies, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for t in batch:
            yield t.get("name", "")
        next_page = resp.headers.get("X-Next-Page", "")
        if not next_page or next_page == "0":
            break
        page += 1

def get_max_seq_from_tags(api_base: str, project_id: str, token: str) -> int:
    """
    既存タグ NNN-YYYYMMDD の NNN 最大値を返す。
    initial-tagのみの場合は 0 を返す。
    一致が無ければ 0。
    """
    max_seq = 0
    has_valid_tags = False
    
    for name in iter_tags(api_base, project_id, token):
        # initial-tagは無視
        if name == "initial-tag":
            continue
            
        m = TAG_PATTERN.match(name)
        if not m:
            continue
            
        has_valid_tags = True
        seq = int(m.group(1))
        if seq > max_seq:
            max_seq = seq
    
    # 有効なタグがない場合（initial-tagのみの場合）は0を返す
    return max_seq if has_valid_tags else 0

def build_next_tag(max_seq: int, tz_name: str = "Asia/Tokyo") -> str:
    """
    次のタグ名 'NNN-YYYYMMDD' を作成。
    - 数字は max_seq + 1（※日付が変わっても連番継続）
    - 日付は常に今日
    """
    today = datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d")
    return f"{(max_seq + 1):03d}-{today}"

def create_tag(api_base: str, project_id: str, token: str, tag_name: str, ref: str, message: str | None = None):
    headers = {"PRIVATE-TOKEN": token}
    
    # プロキシ設定
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    
    url = f"{api_base}/projects/{project_id}/repository/tags"
    payload = {"tag_name": tag_name, "ref": ref}
    if message:
        payload["message"] = message
    resp = requests.post(url, headers=headers, data=payload, proxies=proxies, timeout=30)
    # 重複タグ（already exists）は成功扱いで返す
    if resp.status_code == 400 and "already exists" in resp.text:
        return
    resp.raise_for_status()

# ===== タグ情報管理 =====
def load_tag_info() -> Dict[str, str]:
    """タグ情報をJSONファイルから読み込み"""
    if os.path.exists(TAG_INFO_FILE):
        try:
            with open(TAG_INFO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logging.warning(f"タグ情報ファイル読み込みエラー: {e}")
    return {"new_tag": "", "old_tag": ""}

def save_tag_info(new_tag: str, old_tag: str):
    """タグ情報をJSONファイルに保存"""
    tag_info = {"new_tag": new_tag, "old_tag": old_tag}
    try:
        with open(TAG_INFO_FILE, 'w', encoding='utf-8') as f:
            json.dump(tag_info, f, ensure_ascii=False, indent=2)
        logging.info(f"タグ情報を保存: new={new_tag}, old={old_tag}")
    except IOError as e:
        logging.error(f"タグ情報ファイル保存エラー: {e}")

def get_latest_tag_from_git() -> str:
    """Git上の最新タグ（NNN-YYYYMMDD形式）を取得"""
    latest_tag = ""
    for name in iter_tags(API_BASE, PROJECT_ID, GIT_TOKEN):
        # initial-tagは無視
        if name == "initial-tag":
            continue
            
        m = TAG_PATTERN.match(name)
        if m:
            latest_tag = name
            break  # iter_tagsは降順でソートされているので最初の一致が最新
    return latest_tag

def has_tag_changes() -> bool:
    """Git上の最新タグとtag_info.jsonのnew_tagを比較して差分があるかチェック"""
    tag_info = load_tag_info()
    stored_new_tag = tag_info.get("new_tag", "")
    
    if not stored_new_tag:
        logging.info("tag_info.jsonにnew_tagがありません → 初回実行として処理")
        return True
    
    try:
        # Git上の最新タグを直接取得
        latest_tag = get_latest_tag_from_git()
        
        if not latest_tag or latest_tag == "initial-tag":
            logging.info("Git上にタグがありません → 初回実行として処理")
            return True
        
        logging.info(f"Git最新タグ: {latest_tag}, 保存済みnew_tag: {stored_new_tag}")
        
        # タグが異なる場合は差分あり
        has_diff = latest_tag != stored_new_tag
        if has_diff:
            logging.info("タグに差分があります → Jenkins/n8nフローを実行")
        else:
            logging.info("タグに差分がありません → Jenkins/n8nフローをスキップ")
        
        return has_diff
        
    except Exception as e:
        logging.warning(f"Gitタグ比較エラー: {e} → 差分ありとして処理")
        return True

def push_and_create_tag():
    """ファイルpush/tag作成フロー"""
    logging.info("=== ファイルpush/tag作成フロー開始 ===")
    
    # 1) 最新化
    ensure_repo(REPO_URL, BRANCH, WORKDIR)
    
    # 2) 追加/削除（ダミー）
    apply_file_changes(WORKDIR)
    
    # 3) ステージ→コミット→プッシュ
    stage_commit_push(WORKDIR, TARGET_PATH, BRANCH, COMMIT_MESSAGE)
    
    # 4) 既存NNN最大
    max_seq = get_max_seq_from_tags(API_BASE, PROJECT_ID, GIT_TOKEN)
    
    # 5) 次タグ名生成
    next_tag = build_next_tag(max_seq, tz_name=TIMEZONE)
    
    # 6) タグ作成
    create_tag(API_BASE, PROJECT_ID, GIT_TOKEN, next_tag, BRANCH, TAG_MESSAGE)
    logging.info(f"Created tag: {next_tag}")
    
    # 7) 前回のタグ情報を取得（保存はn8nフロー完了後）
    old_tag_info = load_tag_info()
    old_tag = old_tag_info.get("new_tag", "")  # 前回のnew_tagが今回のold_tag
    
    logging.info("=== ファイルpush/tag作成フロー完了 ===")
    return next_tag, old_tag

# ===== メイン =====
def main():
    # 引数解析
    args = parse_args()
    
    # WORK_ENVをPARAMSに設定
    PARAMS["WORK_ENV"] = args.work_env
    
    logging.info(f"作業環境: {args.work_env}")
    logging.info(f"push/tag作成スキップ: {args.skip_push}")
    
    # 1) ファイルpush/tag作成フロー（オプション）
    if not args.skip_push:
        # 1) ファイルpush/tag作成フロー
        try:
            new_tag, old_tag = push_and_create_tag()
            PARAMS["NEW_TAG"] = new_tag
            PARAMS["OLD_TAG"] = old_tag
        except Exception as e:
            logging.error(f"push/tag作成エラー: {e}")
         
            raise SystemExit(f"push/tag作成に失敗しました: {e}")
        
        # 2) Jenkinsフロー
        s = requests.Session()
        s.auth = HTTPBasicAuth(JENKINS_USER, JENKINS_TOKEN)

        try:
            queue_url = trigger_jenkins_build(s, PARAMS)
            build_url = resolve_queue_to_build(s, queue_url, QUEUE_WAIT_SEC)
            result = wait_for_build_result(s, build_url, BUILD_WAIT_SEC)
            if result not in ("SUCCESS", "UNSTABLE"):
                raise SystemExit(f"Jenkins finished with {result} → n8n は実行しません。")
        except Exception as e:
            logging.error(f"Jenkinsフローエラー: {e}")
            raise SystemExit(f"Jenkinsフローに失敗しました: {e}")
    else:
        logging.info("push/tag作成フローをスキップ")
        # 既存のタグ情報を使用
        tag_info = load_tag_info()
        PARAMS["NEW_TAG"] = tag_info.get("new_tag", "")
        PARAMS["OLD_TAG"] = tag_info.get("old_tag", "")
    
    logging.info(f"タグ情報: NEW={PARAMS['NEW_TAG']}, OLD={PARAMS['OLD_TAG']}")

    # 3) タグ差分チェック
    if not has_tag_changes():
        logging.info("タグに変更がありません → n8nフローをスキップ")
        return

    # 4) n8nフロー
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
        logging.info("デプロイ作業が完了しました。")
        
        # n8nフロー完了後にタグ情報を保存
        if not args.skip_push:
            save_tag_info(PARAMS["NEW_TAG"], PARAMS["OLD_TAG"])
            logging.info("タグ情報を保存しました。")
    else:
        logging.warning("Flow3 status=%s", r3.status_code)

if __name__ == "__main__":
    main()
