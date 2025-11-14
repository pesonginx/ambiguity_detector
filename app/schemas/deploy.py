from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


class GitLabMergeAttributes(BaseModel):
    """GitLabのマージリクエストに関する属性"""

    action: Optional[str] = None
    state: Optional[str] = None
    merge_status: Optional[str] = None

    class Config:
        extra = "allow"


class GitLabWebhookPayload(BaseModel):
    """GitLab Webhookのペイロード"""

    object_kind: Optional[str] = None
    event_type: Optional[str] = None
    work_env: Optional[str] = None
    index_name_short: Optional[str] = None
    object_attributes: Optional[GitLabMergeAttributes] = None

    class Config:
        extra = "allow"

    def is_merge_event(self) -> bool:
        """マージ完了イベントかを判定"""

        attrs = self.object_attributes or GitLabMergeAttributes()
        action = (attrs.action or "").lower()
        state = (attrs.state or "").lower()
        merge_status = (attrs.merge_status or "").lower() if isinstance(attrs.merge_status, str) else ""

        if action in {"merge", "merged"}:
            return True
        if state == "merged":
            return True
        if merge_status == "merged":
            return True

        if (self.event_type or "").lower() == "merge":
            return True
        if (self.object_kind or "").lower() == "merge":
            return True

        return False


class FlowResult(BaseModel):
    """n8nフローの個別結果"""

    flow: str
    status_code: Optional[int] = None
    detail: Optional[str] = None


class DeployWebhookResponse(BaseModel):
    """Webhook処理結果レスポンス"""

    triggered: bool
    status: Literal["success", "failed", "skipped", "ignored"]
    detail: Optional[str] = None
    flows: List[FlowResult] = []


class DeployParameterPayload(BaseModel):
    """トリガーフローから渡されるデプロイパラメータ."""

    new_tag: str
    old_tag: Optional[str] = None
    branch_name: str
    work_env: Optional[str] = None
    index_name_short: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "new_tag": "009-20250930",
                "old_tag": "008-20250925",
                "branch_name": "auto_branch_009_20250930",
                "work_env": "uat",
                "index_name_short": "sample",
            }
        }


class IndexNameShortPayload(BaseModel):
    """index_name_shortのみを受け取る簡易リクエスト."""

    index_name_short: str

    class Config:
        json_schema_extra = {"example": {"index_name_short": "sample"}}


