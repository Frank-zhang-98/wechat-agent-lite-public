from __future__ import annotations

from app.rubrics.base_rubric import BaseRubric, RubricResult
from app.runtime.state_models import SectionPlan


class DeepDiveRubric(BaseRubric):
    pool = "deep_dive"

    def validate_plan(self, section_plan: SectionPlan) -> RubricResult:
        base = super().validate_plan(section_plan)
        warnings = list(base.warnings)
        hard_failures = list(base.hard_failures)
        feedback = list(base.feedback)
        roles = {section.role for section in section_plan.sections}
        required = {"problem_frame", "mechanism", "implementation_or_evidence", "constraint_or_boundary"}
        if required - roles:
            hard_failures.append("missing_deep_dive_roles")
            feedback.append("深挖文章缺少问题/机制/实现/边界四段结构")
        passed = not hard_failures
        score = 93.0 - 3.0 * len(set(warnings)) - 12.0 * len(set(hard_failures))
        return RubricResult(passed, max(score, 0.0), list(dict.fromkeys(warnings)), list(dict.fromkeys(hard_failures)), list(dict.fromkeys(feedback)))
