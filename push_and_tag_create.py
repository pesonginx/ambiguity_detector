import os
import re
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

# ===== 固定設定 =====
REPO_URL = "git@gitlab.com:your-group/your-repo.git"
PROJECT_ID = "your-group%2Fyour-repo"   # 数値IDでもOK
TOKEN = "YOUR_GITLAB_TOKEN"            # 個人アクセストークン(apiスコープ推奨)
API_BASE = "https://gitlab.com/api/v4" # self-hostedなら書き換え
BRANCH = "main"
WORKDIR = "/path/to/local/repo"        # 既存cloneを使い、無ければclone
TARGET_PATH = "."                      # push対象(リポジトリ内相対)。"."で全体
COMMIT_MESSAGE = "chore: update files"
TIMEZONE = "Asia/Tokyo"
TAG_MESSAGE = "auto tag"

# プロキシ設定（.envから取得）
HTTP_PROXY = os.getenv('HTTP_PROXY')
HTTPS_PROXY = os.getenv('HTTPS_PROXY')
# ===================

# タグ形式: NNN-YYYYMMDD（例: 008-20250904）
TAG_PATTERN = re.compile(r"^(\d{3})-(\d{8})$")


def run(cmd, cwd=None, check=True):
    # プロキシ設定を環境変数に追加
    env = os.environ.copy()
    if HTTP_PROXY:
        env['HTTP_PROXY'] = HTTP_PROXY
    if HTTPS_PROXY:
        env['HTTPS_PROXY'] = HTTPS_PROXY
    
    proc = subprocess.run(
        cmd, cwd=cwd, text=True, capture_output=True, check=False, env=env
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    # None チェックを追加して安全に strip() を実行
    stdout = proc.stdout.strip() if proc.stdout is not None else ""
    stderr = proc.stderr.strip() if proc.stderr is not None else ""
    return proc.returncode, stdout, stderr


def ensure_repo(repo_url: str, branch: str, workdir: str):
    """
    手元のクローンを優先使用。無ければclone。あればfetch/checkoutで最新化。
    """
    if not os.path.isdir(workdir):
        parent = os.path.dirname(os.path.abspath(workdir)) or "."
        os.makedirs(parent, exist_ok=True)
        run(["git", "clone", "--branch", branch, "--single-branch", repo_url, workdir])
    else:
        git_dir = os.path.join(workdir, ".git")
        if os.path.isdir(git_dir):
            run(["git", "fetch", "origin", branch], cwd=workdir)
            rc, _, _ = run(["git", "rev-parse", "--verify", branch], cwd=workdir, check=False)
            if rc != 0:
                run(["git", "checkout", "-b", branch, f"origin/{branch}"], cwd=workdir)
            else:
                run(["git", "checkout", branch], cwd=workdir)
                run(["git", "reset", "--hard", f"origin/{branch}"], cwd=workdir)
        else:
            if not os.listdir(workdir):
                run(["git", "init"], cwd=workdir)
                run(["git", "remote", "add", "origin", repo_url], cwd=workdir)
                run(["git", "fetch", "origin", branch], cwd=workdir)
                run(["git", "checkout", "-b", branch, f"origin/{branch}"], cwd=workdir)
            else:
                raise RuntimeError(f"'{workdir}' は空でない非リポジトリです。")


# ① ダミー：追加・削除の実処理はここに書く想定（今回は何もしない）
def apply_file_changes(workdir: str):
    # ここにファイル生成/削除/同期などの処理を実装できる
    # 今回はダミー
    pass


# ② 追加・削除をまとめて拾う: git add -A を使用
def stage_commit_push(workdir: str, target_path: str, branch: str, message: str):
    target = (target_path or ".").strip().strip("/")
    run(["git", "checkout", branch], cwd=workdir)

    # 追加・変更・削除を全てステージ
    run(["git", "add", "-A", target if target else "."], cwd=workdir)

    rc, out, _ = run(["git", "diff", "--cached", "--name-only"], cwd=workdir, check=False)
    if out.strip():
        run(["git", "commit", "-m", message], cwd=workdir)
        run(["git", "push", "origin", branch], cwd=workdir)
    else:
        # 変更がなくても一応 push 試行（no-op）
        run(["git", "push", "origin", branch], cwd=workdir, check=False)


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
    一致が無ければ 0。
    """
    max_seq = 0
    for name in iter_tags(api_base, project_id, token):
        m = TAG_PATTERN.match(name)
        if not m:
            continue
        seq = int(m.group(1))
        if seq > max_seq:
            max_seq = seq
    return max_seq


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


def main():
    # ③ 呼び出し順：最新化 → 追加/削除 → ステージ/コミット/プッシュ → タグ
    ensure_repo(REPO_URL, BRANCH, WORKDIR)                     # 1) 最新化
    apply_file_changes(WORKDIR)                                # 2) 追加/削除（ダミー）
    stage_commit_push(WORKDIR, TARGET_PATH, BRANCH, COMMIT_MESSAGE)  # 3) ステージ→コミット→プッシュ
    max_seq = get_max_seq_from_tags(API_BASE, PROJECT_ID, TOKEN)     # 4) 既存NNN最大
    next_tag = build_next_tag(max_seq, tz_name=TIMEZONE)             # 5) 次タグ名生成
    create_tag(API_BASE, PROJECT_ID, TOKEN, next_tag, BRANCH, TAG_MESSAGE)  # 6) タグ作成
    print(f"Created tag: {next_tag}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
