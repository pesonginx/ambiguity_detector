"""index_name_short ごとの環境変数を解決するユーティリティ."""

from __future__ import annotations

import os
from typing import Dict, Iterable


INDEX_ENV_KEYS = {
    "JENKINS_BASE",
    "JENKINS_JOB",
    "JENKINS_USER",
    "JENKINS_TOKEN",
    "JENKINS_JOB_TOKEN",
    "REPO_URL",
    "PROJECT_ID",
    "GIT_USER",
    "GIT_TOKEN",
    "API_BASE",
    "N8N_FLOW1_URL",
    "N8N_FLOW2_URL",
    "N8N_FLOW3_URL",
}


def _normalized_variations(index_name_short: str) -> Iterable[str]:
    """環境変数参照用に index_name_short のバリエーションを生成."""

    base = index_name_short.strip()
    if not base:
        return []

    variants = {
        base,
        base.upper(),
        base.lower(),
        base.replace("-", "_"),
        base.replace("-", "_").upper(),
        base.replace("-", "_").lower(),
    }
    return [v for v in variants if v]


def _resolve_env_value(index_name_short: str, key: str, default: str) -> str:
    """index_name_short に対応する環境変数を解決."""

    for prefix in _normalized_variations(index_name_short):
        env_key = f"{prefix}_{key}"
        value = os.getenv(env_key)
        if value is not None:
            return value
    return default


def resolve_indexed_env(index_name_short: str) -> Dict[str, str]:
    """index_name_short をもとに Jenkins/Git/n8n 関連の環境変数を取得."""

    import deploy_automation as legacy  # 遅延インポート

    defaults = {
        "JENKINS_BASE": getattr(legacy, "JENKINS_BASE", ""),
        "JENKINS_JOB": getattr(legacy, "JENKINS_JOB", ""),
        "JENKINS_USER": getattr(legacy, "JENKINS_USER", ""),
        "JENKINS_TOKEN": getattr(legacy, "JENKINS_TOKEN", ""),
        "JENKINS_JOB_TOKEN": getattr(legacy, "JENKINS_JOB_TOKEN", ""),
        "REPO_URL": getattr(legacy, "REPO_URL", ""),
        "PROJECT_ID": getattr(legacy, "PROJECT_ID", ""),
        "GIT_USER": getattr(legacy, "GIT_USER", ""),
        "GIT_TOKEN": getattr(legacy, "GIT_TOKEN", ""),
        "API_BASE": getattr(legacy, "API_BASE", ""),
        "N8N_FLOW1_URL": getattr(legacy, "N8N_FLOW1_URL", ""),
        "N8N_FLOW2_URL": getattr(legacy, "N8N_FLOW2_URL", ""),
        "N8N_FLOW3_URL": getattr(legacy, "N8N_FLOW3_URL", ""),
    }

    resolved: Dict[str, str] = {}
    for key in INDEX_ENV_KEYS:
        resolved[key] = _resolve_env_value(index_name_short, key, defaults.get(key, ""))
    return resolved


def apply_indexed_env_to_legacy(index_name_short: str) -> Dict[str, str]:
    """指定された index の環境値を取得し、deploy_automation のグローバルに適用."""

    import deploy_automation as legacy  # 遅延インポート

    resolved = resolve_indexed_env(index_name_short)

    legacy.JENKINS_BASE = resolved["JENKINS_BASE"]
    legacy.JENKINS_JOB = resolved["JENKINS_JOB"]
    legacy.JENKINS_USER = resolved["JENKINS_USER"]
    legacy.JENKINS_TOKEN = resolved["JENKINS_TOKEN"]
    legacy.JENKINS_JOB_TOKEN = resolved["JENKINS_JOB_TOKEN"]

    legacy.REPO_URL = resolved["REPO_URL"]
    legacy.PROJECT_ID = resolved["PROJECT_ID"]
    legacy.GIT_USER = resolved["GIT_USER"]
    legacy.GIT_TOKEN = resolved["GIT_TOKEN"]
    legacy.API_BASE = resolved["API_BASE"]

    legacy.N8N_FLOW1_URL = resolved["N8N_FLOW1_URL"]
    legacy.N8N_FLOW2_URL = resolved["N8N_FLOW2_URL"]
    legacy.N8N_FLOW3_URL = resolved["N8N_FLOW3_URL"]

    legacy.PARAMS["GIT_USER"] = resolved["GIT_USER"]
    legacy.PARAMS["GIT_TOKEN"] = resolved["GIT_TOKEN"]

    return resolved


