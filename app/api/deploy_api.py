import logging
import os
from datetime import datetime
from typing import Dict, Optional

import deploy_automation as legacy
from fastapi import APIRouter, Body, HTTPException

from app.schemas import (
    DeployParameterPayload,
    DeployWebhookResponse,
    GitLabWebhookPayload,
)
from app.services import (
    DeployAutomationConfig,
    DeployConfigStore,
    DeployParameters,
    DeployService,
)


router = APIRouter()
logger = logging.getLogger(__name__)
config_store = DeployConfigStore()


def build_config(payload: GitLabWebhookPayload, overrides: Optional[Dict[str, str]] = None) -> DeployAutomationConfig:
    overrides = overrides or {}
    params: Dict[str, str] = {
        "NEW_TAG": overrides.get("NEW_TAG", os.getenv("NEW_TAG", "")),
        "OLD_TAG": overrides.get("OLD_TAG", os.getenv("OLD_TAG", "")),
        "NEW_TAG_DATE": overrides.get("NEW_TAG_DATE", os.getenv("NEW_TAG_DATE", "")),
        "OLD_TAG_DATE": overrides.get("OLD_TAG_DATE", os.getenv("OLD_TAG_DATE", "")),
        "GIT_USER": overrides.get("GIT_USER", os.getenv("GIT_USER", "")),
        "GIT_TOKEN": overrides.get("GIT_TOKEN", os.getenv("GIT_TOKEN", "")),
        "WORK_ENV": overrides.get("WORK_ENV", payload.work_env or os.getenv("WORK_ENV", "")),
        "INDEX_NAME_SHORT": overrides.get("INDEX_NAME_SHORT", payload.index_name_short or os.getenv("INDEX_NAME_SHORT", "")),
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


def _extract_tag_date(tag: Optional[str]) -> str:
    if not tag:
        return ""
    match = legacy.TAG_PATTERN.match(tag)
    return match.group(2) if match else ""


def _load_saved_params() -> DeployParameters:
    params = config_store.load()
    if not params:
        raise HTTPException(status_code=404, detail="デプロイパラメータが保存されていません")
    return params


def _build_overrides(params: DeployParameters, payload: GitLabWebhookPayload) -> Dict[str, str]:
    work_env = params.work_env or payload.work_env or os.getenv("WORK_ENV", "")
    index_name_short = params.index_name_short or payload.index_name_short or os.getenv("INDEX_NAME_SHORT", "")

    overrides: Dict[str, str] = {
        "NEW_TAG": params.new_tag,
        "OLD_TAG": params.old_tag or "",
        "WORK_ENV": work_env,
        "INDEX_NAME_SHORT": index_name_short,
        "NEW_TAG_DATE": _extract_tag_date(params.new_tag),
        "OLD_TAG_DATE": _extract_tag_date(params.old_tag),
    }

    return overrides


def _update_legacy_params(overrides: Dict[str, str]) -> None:
    legacy.PARAMS.update(
        {
            "NEW_TAG": overrides.get("NEW_TAG", ""),
            "OLD_TAG": overrides.get("OLD_TAG", ""),
            "WORK_ENV": overrides.get("WORK_ENV", ""),
            "INDEX_NAME_SHORT": overrides.get("INDEX_NAME_SHORT", ""),
            "GIT_USER": os.getenv("GIT_USER", legacy.PARAMS.get("GIT_USER", "")),
            "GIT_TOKEN": os.getenv("GIT_TOKEN", legacy.PARAMS.get("GIT_TOKEN", "")),
        }
    )


def _run_n8n_flows(payload: GitLabWebhookPayload, overrides: Dict[str, str], *, force: bool) -> DeployWebhookResponse:
    config = build_config(payload, overrides)
    service = DeployService(config)
    return service.handle_webhook(payload, force=force)


def _run_full_sequence(payload: GitLabWebhookPayload, params: DeployParameters) -> DeployWebhookResponse:
    overrides = _build_overrides(params, payload)
    payload.work_env = overrides.get("WORK_ENV") or payload.work_env
    payload.index_name_short = overrides.get("INDEX_NAME_SHORT") or payload.index_name_short

    if not overrides.get("NEW_TAG"):
        raise HTTPException(status_code=400, detail="NEW_TAG が設定されていません")

    _update_legacy_params(overrides)

    token = os.getenv("GIT_TOKEN", legacy.GIT_TOKEN)
    logging.info(f"GIT_TOKEN: {token}")
    logging.info(f"API_BASE: {legacy.API_BASE}")
    logging.info(f"PROJECT_ID: {legacy.PROJECT_ID}")
    logging.info(f"BRANCH: {legacy.BRANCH}")
    logging.info(f"TAG_MESSAGE: {legacy.TAG_MESSAGE}")
    try:
        legacy.create_tag(
            legacy.API_BASE,
            legacy.PROJECT_ID,
            token,
            overrides["NEW_TAG"],
            legacy.BRANCH,
            legacy.TAG_MESSAGE,
        )
        logger.info("GitLabタグを作成しました: %s", overrides["NEW_TAG"])
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("タグ作成に失敗", exc_info=exc)
        raise HTTPException(status_code=500, detail="タグ作成に失敗しました") from exc

    try:
        legacy.run_jenkins_flow()
    except SystemExit as exc:  # legacyコードがSystemExitを送出するため
        logger.exception("Jenkinsフローに失敗", exc_info=exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Jenkinsフローに失敗", exc_info=exc)
        raise HTTPException(status_code=500, detail="Jenkinsフローに失敗しました") from exc

    response = _run_n8n_flows(payload, overrides, force=True)

    if response.triggered and response.status == "success":
        try:
            legacy.save_tag_info(overrides["NEW_TAG"], overrides.get("OLD_TAG", ""))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("タグ情報の保存に失敗しました: %s", exc)

    response.detail = (response.detail or "") + " | full sequence" if response.detail else "full sequence"
    return response


@router.post("/gitlab-webhook", response_model=DeployWebhookResponse)
async def gitlab_webhook(payload: GitLabWebhookPayload) -> DeployWebhookResponse:
    if not payload.is_merge_event():
        return DeployWebhookResponse(
            triggered=False,
            status="ignored",
            detail="mergeイベントではありません",
            flows=[],
        )

    try:
        params = _load_saved_params()
        return _run_full_sequence(payload, params)
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Webhook処理でエラーが発生", exc_info=exc)
        raise HTTPException(status_code=500, detail="Webhook処理に失敗しました") from exc


@router.post("/config")
async def save_deploy_config(payload: DeployParameterPayload) -> dict:
    """トリガーフローから送られてきたパラメータを保存する."""

    if not payload.new_tag or not payload.branch_name:
        raise HTTPException(status_code=400, detail="new_tag と branch_name は必須です")

    params = DeployParameters(
        new_tag=payload.new_tag,
        old_tag=payload.old_tag,
        branch_name=payload.branch_name,
        work_env=payload.work_env,
        index_name_short=payload.index_name_short,
        created_at=payload.created_at or datetime.utcnow(),
    )

    config_store.save(params)

    return {
        "status": "saved",
        "created_at": params.created_at.isoformat(),
        "branch_name": params.branch_name,
    }


@router.post("/run/full", response_model=DeployWebhookResponse)
async def run_full(payload: GitLabWebhookPayload = Body(default_factory=GitLabWebhookPayload)) -> DeployWebhookResponse:
    params = _load_saved_params()
    return _run_full_sequence(payload, params)


@router.post("/run/n8n", response_model=DeployWebhookResponse)
async def run_n8n_only(payload: GitLabWebhookPayload = Body(default_factory=GitLabWebhookPayload)) -> DeployWebhookResponse:
    params = _load_saved_params()
    overrides = _build_overrides(params, payload)
    payload.work_env = overrides.get("WORK_ENV") or payload.work_env
    payload.index_name_short = overrides.get("INDEX_NAME_SHORT") or payload.index_name_short

    _update_legacy_params(overrides)

    response = _run_n8n_flows(payload, overrides, force=True)
    response.detail = (response.detail or "") + " | n8n only" if response.detail else "n8n only"
    return response


