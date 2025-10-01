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
from typing import Dict, Tuple, Optional, Any
from requests.auth import HTTPBasicAuth
from datetime import datetime
from zoneinfo import ZoneInfo
from git import Repo, GitCommandError
from dotenv import load_dotenv
load_dotenv()


# ===== 設定 =====
JENKINS_BASE = os.getenv("JENKINS_BASE", "")
JENKINS_JOB  = os.getenv("JENKINS_JOB",  "")  # 完全なジョブパスを指定
JENKINS_USER = os.getenv("JENKINS_USER", "")
JENKINS_TOKEN= os.getenv("JENKINS_TOKEN","")
VERIFY_SSL   = os.getenv("VERIFY_SSL", "true").lower() != "false"
JENKINS_JOB_TOKEN = os.getenv("JENKINS_JOB_TOKEN", "")

# Git設定
REPO_URL = os.getenv("REPO_URL", "")
PROJECT_ID = os.getenv("PROJECT_ID", "")
GIT_USER = os.getenv("GIT_USER", "")
GIT_TOKEN = os.getenv("GIT_TOKEN", "")
API_BASE = os.getenv("API_BASE", "https://gitlab.com/api/v4")
BRANCH = os.getenv("BRANCH", "main")
WORKDIR = os.getenv("WORKDIR", "")
TARGET_PATH = os.getenv("TARGET_PATH", ".")
COMMIT_MESSAGE = os.getenv("COMMIT_MESSAGE", "chore: update files")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tokyo")
TAG_MESSAGE = os.getenv("TAG_MESSAGE", "auto tag")

# マージリクエスト設定
MR_APPROVER = os.getenv("MR_APPROVER", GIT_USER)
MR_AUTHOR   = os.getenv("MR_AUTHOR",   GIT_USER)
MR_TITLE_TEMPLATE = os.getenv("MR_TITLE_TEMPLATE", "Auto MR for {branch}")
MR_DESCRIPTION_TEMPLATE = os.getenv(
    "MR_DESCRIPTION_TEMPLATE",
    "Automated MR created by deploy_automation.py for {branch}",
)
MR_TIMEOUT_SEC = int(os.getenv("MR_TIMEOUT_SEC", str(5 * 24 * 3600)))
MR_POLL_INTERVAL_SEC = int(os.getenv("MR_POLL_INTERVAL_SEC", "60"))
MR_REMOVE_SOURCE_BRANCH = os.getenv("MR_REMOVE_SOURCE_BRANCH", "true").lower() != "false"

# プロキシ設定
HTTP_PROXY = os.getenv('HTTP_PROXY')
HTTPS_PROXY = os.getenv('HTTPS_PROXY')
PROXY_CERT = os.getenv('REQUESTS_CA_BUNDLE')

# タグ情報保存ファイル
TAG_INFO_FILE = "tag_info.json"

# タグ形式: NNN-YYYYMMDD（例: 008-20250904）
TAG_PATTERN = re.compile(r"^(\d{3})-(\d{8})$")

PARAMS = {
    "NEW_TAG":   os.getenv("NEW_TAG", ""),
    "OLD_TAG":   os.getenv("OLD_TAG", ""),
    "GIT_USER":  os.getenv("GIT_USER", ""),
    "GIT_TOKEN": os.getenv("GIT_TOKEN", ""),
    "WORK_ENV":  "",  # argsで設定
    "INDEX_NAME_SHORT": "",
}

QUEUE_WAIT_SEC = int(300)
BUILD_WAIT_SEC = int(1800)
POLL_INTERVAL  = float(2)

# n8n
N8N_FLOW1_URL = os.getenv("N8N_FLOW1_URL", "")
N8N_FLOW2_URL = os.getenv("N8N_FLOW2_URL", "")
N8N_FLOW3_URL = os.getenv("N8N_FLOW3_URL", "")
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
    url = jenkins_url(f"/job/{JENKINS_JOB}/buildWithParameters?token={JENKINS_JOB_TOKEN}")
    # Jenkins認証情報をauthパラメータで渡す
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    r = session.post(url, params=params, auth=auth,
                     allow_redirects=False, timeout=TIMEOUT, verify=VERIFY_SSL)
    r.raise_for_status()
    queue_url = r.headers.get("Location")
    if not queue_url:
        raise RuntimeError("Jenkins: queue Location header がありません。")
    return queue_url

def resolve_queue_to_build(session: requests.Session, queue_url: str, wait_sec: int) -> str:
    api = queue_url.rstrip("/") + "/api/json"
    deadline = time.time() + wait_sec
    
    # Jenkins認証情報をauthパラメータで渡す
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    while time.time() < deadline:
        q = session.get(api, auth=auth, timeout=TIMEOUT, verify=VERIFY_SSL)
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
    
    # Jenkins認証情報をauthパラメータで渡す
    auth = (JENKINS_USER, JENKINS_TOKEN)
    
    while time.time() < deadline:
        r = session.get(api, auth=auth, timeout=TIMEOUT, verify=VERIFY_SSL)
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
    r = requests.post(url, headers=headers, data=data, timeout=TIMEOUT, verify=VERIFY_SSL)
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

def stage_commit_push(workdir: str, target_path: str, branch: str, message: str) -> bool:
    """GitPythonを使用してステージング、コミット、プッシュを実行し、コミットした場合はTrueを返す"""
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
        return True
    else:
        logging.info("ステージングする変更がありません")
        # 変更がなくても一応 push 試行（no-op）
        try:
            origin = repo.remotes.origin
            origin.push(branch)
            logging.info("プッシュ完了（変更なし）")
        except GitCommandError as e:
            logging.info(f"プッシュスキップ: {e}")
        return False


def build_auto_branch_name(tag_name: str) -> str:
    suffix = tag_name.replace("-", "_")
    return f"auto_branch_{suffix}"


def checkout_new_branch(workdir: str, base_branch: str, new_branch: str):
    repo = Repo(workdir)
    logging.info(f"ベースブランチ '{base_branch}' にチェックアウト中")
    repo.git.checkout(base_branch)
    try:
        logging.info(f"新規ブランチ '{new_branch}' を作成してチェックアウト")
        repo.git.checkout('-b', new_branch)
    except GitCommandError as e:
        if "already exists" in str(e) or "already exists" in getattr(e, 'stderr', ''):
            logging.info(f"ブランチ '{new_branch}' は既に存在します。チェックアウトします。")
            repo.git.checkout(new_branch)
        else:
            raise


def checkout_branch(workdir: str, branch: str):
    repo = Repo(workdir)
    try:
        repo.git.checkout(branch)
        logging.info(f"ブランチ '{branch}' に戻しました")
    except GitCommandError as exc:
        logging.warning(f"ブランチ '{branch}' へのチェックアウトに失敗しました: {exc}")


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


def gitlab_request(method: str, url: str, token: str, *, params: Optional[Dict[str, Any]] = None,
                   json_body: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None,
                   timeout: int = 30) -> requests.Response:
    headers = {"PRIVATE-TOKEN": token}
    proxies = {}
    if HTTP_PROXY:
        proxies['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies['https'] = HTTPS_PROXY
    resp = requests.request(method.upper(), url, headers=headers, params=params, json=json_body,
                            data=data, timeout=timeout, proxies=proxies, verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp


def find_open_merge_request(api_base: str, project_id: str, token: str,
                            source_branch: str, target_branch: str) -> Optional[Dict[str, Any]]:
    url = f"{api_base}/projects/{project_id}/merge_requests"
    params = {
        "state": "opened",
        "source_branch": source_branch,
        "target_branch": target_branch,
        "order_by": "updated",
        "sort": "desc",
    }
    resp = gitlab_request("get", url, token, params=params)
    items = resp.json()
    return items[0] if items else None


def create_merge_request(api_base: str, project_id: str, token: str, source_branch: str,
                         target_branch: str, title: str, description: str,
                         remove_source_branch: bool, approver: Optional[str],
                         author_username: Optional[str]) -> Dict[str, Any]:
    url = f"{api_base}/projects/{project_id}/merge_requests"
    payload: Dict[str, Any] = {
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": title,
        "description": description,
        "remove_source_branch": remove_source_branch,
    }
    if approver:
        payload["approver_usernames"] = [approver]
    if author_username:
        payload["assignee_username"] = author_username

    try:
        resp = gitlab_request("post", url, token, json_body=payload)
        mr = resp.json()
        logging.info(f"マージリクエスト作成: IID={mr.get('iid')}, URL={mr.get('web_url')}")
        return mr
    except requests.HTTPError as e:
        status = getattr(e.response, 'status_code', None)
        text = getattr(e.response, 'text', '')
        if status in (400, 409) and "Another open merge request" in text:
            logging.info("既存のオープンなマージリクエストを再利用します")
            mr = find_open_merge_request(api_base, project_id, token, source_branch, target_branch)
            if mr:
                return mr
        raise


def wait_for_merge_request_merged(api_base: str, project_id: str, token: str, mr_iid: int,
                                  timeout_sec: int, poll_interval: int):
    url = f"{api_base}/projects/{project_id}/merge_requests/{mr_iid}"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        resp = gitlab_request("get", url, token)
        data = resp.json()
        state = data.get("state")
        merged_at = data.get("merged_at")
        logging.info(f"MR状態チェック: state={state}, merged_at={merged_at}")
        if merged_at or state == "merged":
            logging.info("マージリクエストがマージされました")
            return data
        if state in ("closed", "locked"):
            raise RuntimeError(f"MRがマージされずに終了しました: state={state}")
        time.sleep(poll_interval)
    raise TimeoutError("MRがタイムアウトまでにマージされませんでした")

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

def prepare_branch_and_push():
    """自動ブランチを作成し、変更をpushしてタグ作成に必要な情報を返す"""
    logging.info("=== ブランチ作成/ファイルpushフロー開始 ===")
    branch_name: Optional[str] = None
    try:
        # 1) 最新化（mainブランチ）
        ensure_repo(REPO_URL, BRANCH, WORKDIR)

        # 2) 既存タグ情報を取得
        pre_old_tag = get_latest_tag_from_git()
        max_seq = get_max_seq_from_tags(API_BASE, PROJECT_ID, GIT_TOKEN)
        next_tag = build_next_tag(max_seq, tz_name=TIMEZONE)
        branch_name = build_auto_branch_name(next_tag)

        # 3) 新ブランチ作成
        checkout_new_branch(WORKDIR, BRANCH, branch_name)

        # 4) ファイル変更（ダミー）
        apply_file_changes(WORKDIR)

        # 5) ステージ→コミット→プッシュ
        committed = stage_commit_push(WORKDIR, TARGET_PATH, branch_name, COMMIT_MESSAGE)
        if not committed:
            logging.info("変更がないためタグとマージリクエストの作成をスキップします")

        logging.info("=== ブランチ作成/ファイルpushフロー完了 ===")
        return {
            "new_tag": next_tag,
            "pre_old_tag": pre_old_tag,
            "branch_name": branch_name,
            "committed": committed,
        }
    finally:
        if branch_name:
            try:
                checkout_branch(WORKDIR, BRANCH)
            except Exception as exc:  # pylint: disable=broad-except
                logging.warning("ベースブランチへの戻しに失敗しました: %s", exc)


def process_push_and_tag_flow() -> Optional[Dict[str, Any]]:
    try:
        result = prepare_branch_and_push()
        if not result["committed"]:
            logging.info("コミットがないため処理を終了します")
            return None
        old_tag_info = load_tag_info()
        old_tag = old_tag_info.get("new_tag", "") or result["pre_old_tag"]
        PARAMS["NEW_TAG"] = result["new_tag"]
        PARAMS["OLD_TAG"] = old_tag
        return result
    except Exception as e:
        logging.error(f"ブランチ作成/コミット準備エラー: {e}")
        raise SystemExit(f"ブランチ作成/コミット準備に失敗しました: {e}")


def process_merge_request(branch_name: str):
    title = MR_TITLE_TEMPLATE.format(branch=branch_name)
    description = MR_DESCRIPTION_TEMPLATE.format(branch=branch_name)
    try:
        mr = create_merge_request(
            API_BASE,
            PROJECT_ID,
            GIT_TOKEN,
            source_branch=branch_name,
            target_branch=BRANCH,
            title=title,
            description=description,
            remove_source_branch=MR_REMOVE_SOURCE_BRANCH,
            approver=MR_APPROVER,
            author_username=MR_AUTHOR,
        )
        wait_for_merge_request_merged(
            API_BASE,
            PROJECT_ID,
            GIT_TOKEN,
            mr_iid=mr["iid"],
            timeout_sec=MR_TIMEOUT_SEC,
            poll_interval=MR_POLL_INTERVAL_SEC,
        )
    except Exception as e:
        logging.error(f"マージリクエスト処理エラー: {e}")
        raise SystemExit(f"マージリクエスト処理に失敗しました: {e}")


def create_new_tag():
    try:
        create_tag(API_BASE, PROJECT_ID, GIT_TOKEN, PARAMS["NEW_TAG"], BRANCH, TAG_MESSAGE)
        logging.info(f"Created tag: {PARAMS['NEW_TAG']}")
    except Exception as e:
        logging.error(f"タグ作成エラー: {e}")
        raise SystemExit(f"タグ作成に失敗しました: {e}")


def run_jenkins_flow():
    s = requests.Session()
    s.auth = HTTPBasicAuth(JENKINS_USER, JENKINS_TOKEN)

    s.auth = None
    s.proxies = {}
    s.verify = VERIFY_SSL
    original_http_proxy = os.environ.pop('HTTP_PROXY', None)
    original_https_proxy = os.environ.pop('HTTPS_PROXY', None)

    try:
        queue_url = trigger_jenkins_build(s, PARAMS)
        build_url = resolve_queue_to_build(s, queue_url, QUEUE_WAIT_SEC)
        result_status = wait_for_build_result(s, build_url, BUILD_WAIT_SEC)
        if result_status not in ("SUCCESS", "UNSTABLE"):
            raise SystemExit(f"Jenkins finished with {result_status} → n8n は実行しません。")
    except Exception as e:
        logging.error(f"Jenkinsフローエラー: {e}")
        raise SystemExit(f"Jenkinsフローに失敗しました: {e}")
    finally:
        if original_http_proxy:
            os.environ['HTTP_PROXY'] = original_http_proxy
        if original_https_proxy:
            os.environ['HTTPS_PROXY'] = original_https_proxy


def main():
    args = parse_args()
    PARAMS["WORK_ENV"] = args.work_env
    PARAMS["INDEX_NAME_SHORT"] = args.index_name_short

    logging.info(f"作業環境: {args.work_env}")
    logging.info(f"push/tag作成スキップ: {args.skip_push}")

    branch_result = None
    if not args.skip_push:
        branch_result = process_push_and_tag_flow()
        if branch_result is None:
            return
        process_merge_request(branch_result["branch_name"])
        create_new_tag()
        run_jenkins_flow()
    else:
        logging.info("push/tag作成フローをスキップ")
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
