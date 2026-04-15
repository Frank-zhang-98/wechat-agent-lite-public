from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext
from app.runtime.state_models import ArticleDraft, ArticleIntent, SectionPlan


class WriterAgent:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    def write(
        self,
        *,
        run: Any,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        intent: ArticleIntent,
        section_plan: SectionPlan,
        rewrite_feedback: list[str] | None = None,
    ) -> tuple[ArticleDraft, dict[str, Any]]:
        support = self.ctx.support
        outline_plan = self._build_outline_plan(intent=intent, section_plan=section_plan)
        if str(fact_pack.get("article_variant", "") or "").strip() == "project_explainer":
            outline_plan["structure_mode"] = "source_preserving"
        prompt = support.writing_templates.build_write_prompt(
            topic=topic,
            fact_pack=fact_pack,
            audience_key=intent.audience,
            subtype=intent.subtype,
            pool=intent.pool,
            pool_blueprint={
                "pool": intent.pool,
                "pool_label": intent.pool,
                "strategy": section_plan.strategy_label,
                "subtype": intent.subtype,
                "subtype_label": intent.subtype_label,
            },
            outline_plan=outline_plan,
        )
        if fact_compress:
            prompt += "\n\n【事实压缩】\n" + str(fact_compress)
        if rewrite_feedback:
            prompt += "\n\n【重写反馈】\n" + "\n".join(f"- {item}" for item in rewrite_feedback[:8] if str(item).strip())
        result = support.llm.call(run.id, "WRITE", "writer", prompt, temperature=0.45)
        article = result.text.strip()
        used_generic_fallback = False
        if str(result.model or "").strip() == "mock-model":
            article = support._fallback_article(topic)
            used_generic_fallback = True
        elif not support._writer_output_is_acceptable(article):
            if support.settings.get_bool("writing.allow_generic_fallback", False):
                article = support._fallback_article(topic)
                used_generic_fallback = True
            else:
                raise RuntimeError("writer output too short or structurally incomplete")
        temp_ctx = {
            "selected_topic": topic,
            "fact_pack": fact_pack,
            "target_audience": intent.audience,
            "pool": intent.pool,
            "subtype": intent.subtype,
            "subtype_label": intent.subtype_label,
            "fact_compress": fact_compress,
        }
        humanizer_meta = support._humanize_article_if_needed(
            run=run,
            ctx=temp_ctx,
            article=article,
            topic=topic,
            fact_pack=fact_pack,
            audience_key=intent.audience,
            pool=intent.pool,
            subtype=intent.subtype,
            skip_rewrite=used_generic_fallback or str(result.model or "").strip() == "mock-model",
        )
        article = str(humanizer_meta.get("article", article) or article)
        prepared = support._prepare_generated_article_markdown(article, temp_ctx)
        draft = ArticleDraft(
            article_markdown=prepared,
            h1_title=self._extract_markdown_h1(prepared),
            section_outputs=[{"role": section.role, "heading": section.heading_hint} for section in section_plan.sections],
            humanizer={key: value for key, value in humanizer_meta.items() if key != "article"},
            write_output_meta={
                "model": str(result.model or ""),
                "provider": str(result.provider or ""),
                "estimated": bool(result.estimated),
                "used_generic_fallback": used_generic_fallback,
                "humanizer_before_score": float((humanizer_meta.get("before") or {}).get("score", 0.0) or 0.0),
                "humanizer_after_score": float((humanizer_meta.get("after") or {}).get("score", 0.0) or 0.0),
                "humanizer_rewrite_applied": bool(humanizer_meta.get("rewrite_applied", False)),
            },
        )
        return draft, {
            "prompts": [{"title": "runtime_write_prompt", "text": prompt}],
            "outputs": [
                {"title": "runtime_article_markdown", "text": prepared, "language": "markdown"},
                {"title": "runtime_humanizer", "text": str(draft.humanizer), "language": "json"},
            ],
        }

    @staticmethod
    def _build_outline_plan(*, intent: ArticleIntent, section_plan: SectionPlan) -> dict[str, Any]:
        return {
            "pool": intent.pool,
            "strategy": section_plan.strategy_label,
            "article_intent": intent.core_angle,
            "subtype": intent.subtype,
            "subtype_label": intent.subtype_label,
            "structure_mode": "standard",
            "section_count": len(section_plan.sections),
            "sections": [
                {
                    "heading": section.heading_hint,
                    "purpose": section.goal,
                    "role": section.role,
                    "evidence_points": list(section.evidence_refs),
                }
                for section in section_plan.sections
            ],
        }

    @staticmethod
    def _extract_markdown_h1(article_markdown: str) -> str:
        for line in str(article_markdown or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""
