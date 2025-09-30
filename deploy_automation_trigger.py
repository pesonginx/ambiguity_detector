"""deploy_automationのマージリクエスト作成フェーズのみを実行するトリガースクリプト."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import requests

import deploy_automation as legacy

from dotenv import load_dotenv


load_dotenv()


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


DEPLOY_API_BASE = os.getenv("DEPLOY_API_BASE", "http://localhost:8000/api/v1/deploy")
CONFIG_ENDPOINT = f"{DEPLOY_API_BASE.rstrip('/')}/config"


class TriggerError(RuntimeError):
    """トリガーフローにおける例外."""


def _post_json(url: str, payload: Dict[str, Any], *, timeout: int = 30) -> Dict[str, Any]:
    logger.info("POST %s %s", url, json.dumps(payload, ensure_ascii=False))
    response = requests.post(url, json=payload, timeout=timeout, verify=legacy.VERIFY_SSL)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pylint: disable=broad-except
        logger.error("API呼び出しに失敗しました: status=%s body=%s", response.status_code, response.text)
        raise TriggerError(f"API呼び出しに失敗しました: {url}") from exc
    try:
        return response.json()
    except json.JSONDecodeError:  # pylint: disable=broad-except
        return {"status_code": response.status_code, "text": response.text}


def _build_old_tag(pre_old_tag: Optional[str]) -> Optional[str]:
    tag_info = legacy.load_tag_info()
    stored = tag_info.get("new_tag") if isinstance(tag_info, dict) else None
    if stored:
        return stored
    return pre_old_tag


def _save_parameters_via_api(result: Dict[str, Any], *, work_env: str, index_name_short: str) -> None:
    payload = {
        "new_tag": result["new_tag"],
        "old_tag": result.get("old_tag"),
        "branch_name": result["branch_name"],
        "work_env": work_env,
        "index_name_short": index_name_short,
        "created_at": datetime.utcnow().isoformat(),
    }
    api_result = _post_json(CONFIG_ENDPOINT, payload)
    logger.info("デプロイパラメータを保存しました: %s", api_result)


def _create_merge_request(branch_name: str) -> Dict[str, Any]:
    title = legacy.MR_TITLE_TEMPLATE.format(branch=branch_name)
    description = legacy.MR_DESCRIPTION_TEMPLATE.format(branch=branch_name)

    mr = legacy.create_merge_request(
        legacy.API_BASE,
        legacy.PROJECT_ID,
        legacy.GIT_TOKEN,
        source_branch=branch_name,
        target_branch=legacy.BRANCH,
        title=title,
        description=description,
        remove_source_branch=legacy.MR_REMOVE_SOURCE_BRANCH,
        approver=legacy.MR_APPROVER,
        author_username=legacy.MR_AUTHOR,
    )
    logger.info("マージリクエストを作成しました: iid=%s url=%s", mr.get("iid"), mr.get("web_url"))
    return mr


def main() -> None:
    args = legacy.parse_args()
    legacy.PARAMS["WORK_ENV"] = args.work_env
    legacy.PARAMS["INDEX_NAME_SHORT"] = args.index_name_short

    logger.info("=== deploy_automation trigger start ===")
    logger.info("作業環境: %s", args.work_env)
    logger.info("push/tag作成スキップ: %s", args.skip_push)

    branch_result: Optional[Dict[str, Any]] = None

    if not args.skip_push:
        branch_result = legacy.prepare_branch_and_push()
        if not branch_result["committed"]:
            logger.info("コミット対象の変更がないため処理を終了します")
            return

        branch_name = branch_result["branch_name"]
        mr = _create_merge_request(branch_name)
        branch_result["merge_request"] = {
            "iid": mr.get("iid"),
            "url": mr.get("web_url"),
        }

        old_tag = _build_old_tag(branch_result.get("pre_old_tag"))
        legacy.PARAMS["NEW_TAG"] = branch_result["new_tag"]
        legacy.PARAMS["OLD_TAG"] = old_tag or ""

        payload = {
            "new_tag": branch_result["new_tag"],
            "old_tag": old_tag,
            "branch_name": branch_name,
            "work_env": args.work_env,
            "index_name_short": args.index_name_short,
            "created_at": datetime.utcnow().isoformat(),
        }

        _post_json(CONFIG_ENDPOINT, payload)

        logger.info(
            "トリガー処理が完了しました new_tag=%s old_tag=%s branch=%s",
            branch_result["new_tag"],
            old_tag,
            branch_name,
        )
        logger.info("マージリクエストURL: %s", mr.get("web_url"))

    else:
        logger.info("--skip-push が指定されているため、ブランチ作成とMR作成をスキップします")

    logger.info("=== deploy_automation trigger finished ===")


if __name__ == "__main__":
    try:
        main()
    except TriggerError as exc:
        logger.error("トリガー処理でエラーが発生しました: %s", exc)
        raise SystemExit(str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("予期せぬエラーが発生しました", exc_info=exc)
        raise SystemExit("deploy_automation_triggerが失敗しました") from exc


