"""FastAPI deployエンドポイントの動作確認用スクリプト."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any, Dict

import requests


DEFAULT_BASE_URL = "http://localhost:8000/api/v1/deploy"


def _print_response(resp: requests.Response) -> None:
    try:
        body = resp.json()
        formatted = json.dumps(body, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        formatted = resp.text

    print("=== Response ===")
    print(f"Status : {resp.status_code}")
    print(f"Headers: {dict(resp.headers)}")
    print(formatted)


def _request_json(method: str, url: str, payload: Dict[str, Any], verify: bool) -> requests.Response:
    print("=== Request ===")
    print(f"Method : {method}")
    print(f"URL    : {url}")
    print("Payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    response = requests.request(method, url, json=payload, timeout=60, verify=verify)
    _print_response(response)
    return response


def run_config(args: argparse.Namespace) -> None:
    created_at = args.created_at or datetime.utcnow().isoformat()
    payload = {
        "new_tag": args.new_tag,
        "old_tag": args.old_tag,
        "branch_name": args.branch_name,
        "work_env": args.work_env,
        "index_name_short": args.index_name_short,
        "created_at": created_at,
    }

    url = f"{args.base_url}/config"
    _request_json("POST", url, payload, not args.skip_verify)


def run_full(args: argparse.Namespace) -> None:
    payload = {
        "object_kind": "merge_request",
        "event_type": "merge",
        "work_env": args.work_env,
        "index_name_short": args.index_name_short,
        "object_attributes": {"action": "merge", "state": "merged"},
    }

    url = f"{args.base_url}/run/full"
    _request_json("POST", url, payload, not args.skip_verify)


def run_n8n(args: argparse.Namespace) -> None:
    payload = {
        "object_kind": "merge_request",
        "event_type": "merge",
        "work_env": args.work_env,
        "index_name_short": args.index_name_short,
        "object_attributes": {"action": "merge", "state": "merged"},
    }

    url = f"{args.base_url}/run/n8n"
    _request_json("POST", url, payload, not args.skip_verify)


def run_webhook(args: argparse.Namespace) -> None:
    payload = {
        "object_kind": "merge_request",
        "event_type": "merge_request",
        "work_env": args.work_env,
        "index_name_short": args.index_name_short,
        "object_attributes": {
            "action": "merge",
            "state": "merged",
            "merge_status": "merged",
        },
    }

    url = f"{args.base_url}/gitlab-webhook"
    _request_json("POST", url, payload, not args.skip_verify)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="deploy API テストクライアント")
    parser.add_argument(
        "command",
        choices=["config", "run_full", "run_n8n", "webhook"],
        help="実行する操作",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="APIベースURL")
    parser.add_argument("--skip-verify", action="store_true", help="SSL検証を行わない")

    # 共通オプション
    parser.add_argument("--work-env", default="uat", help="work_env の値")
    parser.add_argument("--index-name-short", default="sample", help="index_name_short の値")

    # config用
    parser.add_argument("--new-tag", default="999-20991231", help="config用 new_tag")
    parser.add_argument("--old-tag", default="998-20991230", help="config用 old_tag")
    parser.add_argument("--branch-name", default="auto_branch_999_20991231", help="config用 branch_name")
    parser.add_argument("--created-at", default=None, help="config用 created_at (ISO8601)")

    return parser.parse_args(argv)


def main(argv: list[str]) -> None:
    args = parse_args(argv)

    commands = {
        "config": run_config,
        "run_full": run_full,
        "run_n8n": run_n8n,
        "webhook": run_webhook,
    }

    handler = commands[args.command]
    handler(args)


if __name__ == "__main__":
    main(sys.argv[1:])


