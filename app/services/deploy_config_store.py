"""デプロイ実行に必要なパラメータを永続化するストア."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass
class DeployParameters:
    """デプロイ実行時に必要となるパラメータ."""

    new_tag: str
    old_tag: Optional[str]
    branch_name: str
    work_env: Optional[str]
    index_name_short: Optional[str]
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_dict(cls, data: dict) -> "DeployParameters":
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not isinstance(created_at, datetime):
            created_at = datetime.utcnow()
        return cls(
            new_tag=data.get("new_tag", ""),
            old_tag=data.get("old_tag"),
            branch_name=data.get("branch_name", ""),
            work_env=data.get("work_env"),
            index_name_short=data.get("index_name_short"),
            created_at=created_at,
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


class DeployConfigStore:
    """デプロイパラメータをJSONファイルに保存するシンプルなストア."""

    def __init__(self, path: Optional[str] = None):
        base_dir = Path(__file__).resolve().parents[2]
        default_path = base_dir / "deploy_config.json"
        self.path = Path(path or os.getenv("DEPLOY_CONFIG_PATH", default_path))
        self._lock = Lock()

    def save(self, params: DeployParameters) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(params.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("デプロイパラメータを保存しました: %s", self.path)

    def load(self) -> Optional[DeployParameters]:
        if not self.path.exists():
            return None
        with self._lock:
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("デプロイパラメータの読み込みに失敗しました: %s", exc)
                return None
        return DeployParameters.from_dict(data)

    def clear(self) -> None:
        with self._lock:
            try:
                if self.path.exists():
                    self.path.unlink()
                    logger.info("デプロイパラメータを削除しました: %s", self.path)
            except OSError as exc:
                logger.warning("デプロイパラメータの削除に失敗しました: %s", exc)


