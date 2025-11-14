from __future__ import annotations
import os
import sys
from typing import Any, Dict
import requests


FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8085")
RUN_N8N_ENDPOINT = f"{FASTAPI_BASE_URL.rstrip('/')}/api/v1/deploy/run/n8n"
INDEX_NAME_SHORT = os.getenv("INDEX_NAME_SHORT_FOR_N8N", "default_index")
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() != "false"

# 一旦なしで。n8nでエラーが出たらしっかりレスポンス返すようにする
REQUEST_TIMEOUT = 0


def trigger_n8n_flow(index_name_short: str = INDEX_NAME_SHORT) -> Dict[str, Any]:
    """/run/n8n エンドポイントを呼び出して結果を返す。"""
    payload = {"index_name_short": index_name_short}
    response = requests.post(
        RUN_N8N_ENDPOINT,
        json=payload,
        timeout=REQUEST_TIMEOUT,
        verify=VERIFY_SSL,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    print(f"POST {RUN_N8N_ENDPOINT}")
    print(f"Payload: {{'index_name_short': '{INDEX_NAME_SHORT}'}}")

    try:
        result = trigger_n8n_flow()
    except requests.HTTPError as http_error:
        print(f"HTTP {http_error.response.status_code}: {http_error.response.text}")
        sys.exit(1)
    except requests.RequestException as request_error:
        print(f"リクエスト失敗: {request_error}")
        sys.exit(1)

    print("=== n8nフロー実行結果 ===")
    print(result)


if __name__ == "__main__":
    main()

