from __future__ import annotations

from app.agents.base import AgentContext
from app.runtime.state_models import ArticleDraft, ArticleIntent, RuntimeTitlePlan, SectionPlan


class TitleAgent:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    def generate(
        self,
        *,
        run_id: str,
        topic: dict,
        fact_pack: dict,
        fact_compress: dict,
        intent: ArticleIntent,
        section_plan: SectionPlan,
        draft: ArticleDraft,
    ) -> tuple[RuntimeTitlePlan, dict]:
        support = self.ctx.support
        generated = support.title_generator.generate(
            run_id=run_id,
            topic=topic,
            fact_pack=fact_pack,
            fact_compress=fact_compress,
            pool=intent.pool,
            subtype=intent.subtype,
            llm=support.llm,
        )
        heading_line = next((section.heading_hint for section in section_plan.sections if section.heading_hint), "")
        title_plan = RuntimeTitlePlan(
            article_title=str(generated.article_title or "").strip(),
            wechat_title=str(generated.wechat_title or "").strip(),
            title_rationale=f"{intent.core_angle} / {heading_line}".strip(" /")[:200],
            source=str(generated.source or "agent"),
            debug=dict(generated.debug or {}),
        )
        return title_plan, {
            "outputs": [{"title": "runtime_title_plan", "text": str(title_plan.as_dict()), "language": "json"}]
        }

    @staticmethod
    def _sync_titles_from_draft(*, temp_ctx: dict, draft: ArticleDraft, intent: ArticleIntent, support) -> None:
        return
