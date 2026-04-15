from __future__ import annotations

from app.rubrics.base_rubric import BaseRubric, RubricResult
from app.runtime.state_models import SectionPlan


class GithubRubric(BaseRubric):
    pool = "github"

    def validate_plan(self, section_plan: SectionPlan) -> RubricResult:
        base = super().validate_plan(section_plan)
        warnings = list(base.warnings)
        hard_failures = list(base.hard_failures)
        feedback = list(base.feedback)
        roles = {section.role for section in section_plan.sections}
        required = {"project_positioning", "who_should_use", "how_it_works", "engineering_tradeoffs", "deployment_boundary"}
        missing = sorted(required - roles)
        if missing:
            hard_failures.append("missing_github_roles")
            feedback.append("GitHub 项目文章缺少关键章节角色")
        for section in section_plan.sections:
            if section.role == "deployment_boundary" and not any("仓库" in ref or "github" in ref.lower() for ref in section.evidence_refs):
                warnings.append("deployment_without_repo_reference")
        passed = not hard_failures
        score = 95.0 - 3.0 * len(set(warnings)) - 12.0 * len(set(hard_failures))
        return RubricResult(passed, max(score, 0.0), list(dict.fromkeys(warnings)), list(dict.fromkeys(hard_failures)), list(dict.fromkeys(feedback)))

