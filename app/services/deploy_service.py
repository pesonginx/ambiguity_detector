import json
import logging
from dataclasses import dataclass
from typing import Dict, List

import deploy_automation as legacy

import requests

from app.schemas import (
    DeployWebhookResponse,
    FlowResult,
    GitLabWebhookPayload,
)

logger = logging.getLogger(__name__)


@dataclass
class DeployAutomationConfig:
    """deploy_automationで利用している環境変数をまとめて扱う"""

    params: Dict[str, str]
    flow_urls: Dict[str, str]
    send_json: bool
    verify_ssl: bool
    timeout: tuple[int, int]


class DeployService:
    """deploy_automationのn8nフロー呼び出し部分をラップするサービス"""

    def __init__(self, config: DeployAutomationConfig):
        self.config = config

    def _build_payload(self) -> Dict[str, str]:
        def extract_tag_number(tag: str) -> str:
            if not tag:
                return ""
            match = legacy.TAG_PATTERN.match(tag)
            return match.group(1) if match else ""

        new_tag_full = self.config.params.get("NEW_TAG", "")
        old_tag_full = self.config.params.get("OLD_TAG", "")

        payload = {
            "newTag": extract_tag_number(new_tag_full),
            "oldTag": extract_tag_number(old_tag_full),
            "newTagDate": self.config.params.get("NEW_TAG_DATE", ""),
            "oldTagDate": self.config.params.get("OLD_TAG_DATE", ""),
            "gitUser": self.config.params.get("GIT_USER", ""),
            "gitToken": self.config.params.get("GIT_TOKEN", ""),
            "workEnv": self.config.params.get("WORK_ENV", ""),
            "indexNameShort": self.config.params.get("INDEX_NAME_SHORT", ""),
        }

        return payload

    def _post(self, url: str, payload: Dict[str, str]) -> FlowResult:
        headers = (
            {"Content-Type": "application/json"}
            if self.config.send_json
            else {"Content-Type": "application/x-www-form-urlencoded"}
        )

        data = json.dumps(payload) if self.config.send_json else payload
        response = requests.post(
            url,
            headers=headers,
            data=data,
            timeout=self.config.timeout,
            verify=self.config.verify_ssl,
        )

        return FlowResult(flow=url, status_code=response.status_code, detail=response.text)

    def run_flows(self) -> List[FlowResult]:
        payload = self._build_payload()
        results: List[FlowResult] = []

        for name in ("flow1", "flow2", "flow3"):
            url = self.config.flow_urls.get(name)
            if not url:
                continue

            result = self._post(url, payload)
            results.append(result)

            if name == "flow1" and result.status_code != 200:
                break
            if name == "flow2" and result.status_code != 200:
                break

        return results

    def handle_webhook(self, payload: GitLabWebhookPayload, *, force: bool = False) -> DeployWebhookResponse:
        if not force and not payload.is_merge_event():
            return DeployWebhookResponse(
                triggered=False,
                status="ignored",
                detail="mergeイベントではありません",
                flows=[],
            )

        flows = self.run_flows()

        if not flows:
            return DeployWebhookResponse(
                triggered=False,
                status="skipped",
                detail="フローURLが設定されていません",
                flows=[],
            )

        success = all(result.status_code == 200 for result in flows)
        status = "success" if success else "failed"

        return DeployWebhookResponse(
            triggered=True,
            status=status,
            detail=None,
            flows=flows,
        )

