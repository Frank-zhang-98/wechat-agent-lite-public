from __future__ import annotations

from app.agents.base import AgentContext
from app.runtime.state_models import ArticleDraft, RuntimeTitlePlan, VisualAssetSet


class PublisherAgent:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    def publish(
        self,
        *,
        topic: dict,
        draft: ArticleDraft,
        title_plan: RuntimeTitlePlan,
        visual_assets: VisualAssetSet,
        article_html: str,
    ) -> tuple[dict, str, dict]:
        result = self.ctx.support.wechat.publish_draft(
            title=title_plan.wechat_title or title_plan.article_title,
            markdown_content=draft.article_markdown,
            html_content=article_html,
            source_url=str(topic.get("url", "") or ""),
            cover_image_path=str((visual_assets.cover_asset or {}).get("path", "") or ""),
        )
        payload = {
            "success": result.success,
            "draft_id": result.draft_id,
            "reason": result.reason,
            "thumb_media_id": result.thumb_media_id,
            "sent_title": result.sent_title,
            "sent_digest": result.sent_digest,
            "debug_info": result.debug_info,
        }
        return payload, ("saved" if result.success else "pending_manual"), {
            "outputs": [{"title": "runtime_publish_result", "text": str(payload), "language": "json"}]
        }
