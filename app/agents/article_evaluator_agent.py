from __future__ import annotations

from app.agents.base import AgentContext
from app.runtime.state_models import ArticleDraft, ArticleIntent, SectionPlan


class ArticleEvaluatorAgent:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    def evaluate(
        self,
        *,
        run_id: str,
        fact_pack: dict,
        fact_grounding: dict,
        intent: ArticleIntent,
        section_plan: SectionPlan,
        draft: ArticleDraft,
    ) -> tuple[dict, dict]:
        support = self.ctx.support
        humanizer_analysis = support.humanizer.analyze(draft.article_markdown)
        hard_checks = support._quality_hard_checks(
            article=draft.article_markdown,
            fact_pack=fact_pack,
            humanizer_analysis=humanizer_analysis,
        )
        hallucination = support.hallucination_checker.check(
            run_id=run_id,
            article_markdown=draft.article_markdown,
            fact_grounding=fact_grounding,
            llm=support.llm,
        )
        warnings = list(hard_checks.get("soft_warnings") or [])
        feedback = []
        if hallucination.get("rewrite_required"):
            warnings.append("hallucination_rewrite_required")
            feedback.extend(
                list(hallucination.get("unsupported_claims") or [])
                + list(hallucination.get("inference_written_as_fact") or [])
                + list(hallucination.get("forbidden_claim_violations") or [])
            )
        hard_failures = list(hard_checks.get("hard_failures") or [])
        if hallucination.get("severity") == "high":
            hard_failures.append("hallucination_high_severity")
        passed = not hard_failures
        score = max(0.0, 92.0 - 4.0 * len(set(warnings)) - 12.0 * len(set(hard_failures)))
        result = {
            "passed": passed,
            "score": score,
            "warnings": list(dict.fromkeys(warnings)),
            "hard_failures": list(dict.fromkeys(hard_failures)),
            "feedback": list(dict.fromkeys(feedback))[:10],
            "hallucination_check": hallucination,
            "quality_gate_status": "passed_with_warnings" if passed and warnings else "passed" if passed else "failed",
            "attempts": 1,
            "scores": [score],
            "fallback_used": False,
        }
        return result, {
            "outputs": [{"title": "runtime_article_evaluation", "text": str(result), "language": "json"}]
        }
