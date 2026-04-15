from __future__ import annotations

from app.agents.base import AgentContext
from app.runtime.state_models import SectionPlan


class PlanEvaluatorAgent:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    def evaluate(self, *, section_plan: SectionPlan) -> tuple[dict, dict]:
        rubric = self.ctx.rubric_registry.get(section_plan.pool)
        result = rubric.validate_plan(section_plan)
        return result.as_dict(), {
            "summary": {
                "passed": result.passed,
                "score": result.score,
                "warnings": len(result.warnings),
                "hard_failures": len(result.hard_failures),
            },
            "outputs": [{"title": "plan_evaluation", "text": str(result.as_dict()), "language": "json"}],
        }
