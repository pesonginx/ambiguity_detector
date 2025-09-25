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

