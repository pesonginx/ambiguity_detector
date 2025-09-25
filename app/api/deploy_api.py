import logging
import os
from typing import Dict

from fastapi import APIRouter, HTTPException

from app.schemas import DeployWebhookResponse, GitLabWebhookPayload
from app.services import DeployAutomationConfig, DeployService


router = APIRouter()
logger = logging.getLogger(__name__)


def build_config(payload: GitLabWebhookPayload) -> DeployAutomationConfig:
    params: Dict[str, str] = {
        "NEW_TAG": os.getenv("NEW_TAG", ""),
        "OLD_TAG": os.getenv("OLD_TAG", ""),
        "NEW_TAG_DATE": os.getenv("NEW_TAG_DATE", ""),
        "OLD_TAG_DATE": os.getenv("OLD_TAG_DATE", ""),
        "GIT_USER": os.getenv("GIT_USER", ""),
        "GIT_TOKEN": os.getenv("GIT_TOKEN", ""),
        "WORK_ENV": payload.work_env or os.getenv("WORK_ENV", ""),
        "INDEX_NAME_SHORT": payload.index_name_short or os.getenv("INDEX_NAME_SHORT", ""),
    }

    flow_urls: Dict[str, str] = {
        "flow1": os.getenv("N8N_FLOW1_URL", ""),
        "flow2": os.getenv("N8N_FLOW2_URL", ""),
        "flow3": os.getenv("N8N_FLOW3_URL", ""),
    }

    send_json = os.getenv("N8N_SEND_JSON", "false").lower() == "true"
    verify_ssl = os.getenv("VERIFY_SSL", "true").lower() != "false"
    timeout = (int(os.getenv("N8N_TIMEOUT_CONNECT", "10")), int(os.getenv("N8N_TIMEOUT_READ", "30")))

    return DeployAutomationConfig(
        params=params,
        flow_urls=flow_urls,
        send_json=send_json,
        verify_ssl=verify_ssl,
        timeout=timeout,
    )


@router.post("/gitlab-webhook", response_model=DeployWebhookResponse)
async def gitlab_webhook(payload: GitLabWebhookPayload) -> DeployWebhookResponse:
    try:
        config = build_config(payload)
        service = DeployService(config)
        result = service.handle_webhook(payload)
        return result
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Webhook処理でエラーが発生", exc_info=exc)
        raise HTTPException(status_code=500, detail="Webhook処理に失敗しました") from exc

