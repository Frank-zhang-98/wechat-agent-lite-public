from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.runtime.state_models import SectionPlan


@dataclass(frozen=True, slots=True)
class RubricResult:
    passed: bool
    score: float
    warnings: list[str]
    hard_failures: list[str]
    feedback: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "warnings": self.warnings,
            "hard_failures": self.hard_failures,
            "feedback": self.feedback,
        }


class BaseRubric:
    pool: str = "deep_dive"

    def validate_plan(self, section_plan: SectionPlan) -> RubricResult:
        warnings: list[str] = []
        hard_failures: list[str] = []
        feedback: list[str] = []
        if not section_plan.sections:
            hard_failures.append("missing_sections")
            feedback.append("章节规划为空")
        for section in section_plan.sections:
            if not section.heading_hint:
                warnings.append(f"missing_heading_hint:{section.role}")
            if not section.evidence_refs:
                warnings.append(f"missing_evidence:{section.role}")
        passed = not hard_failures
        score = 92.0 - 4.0 * len(warnings) - 10.0 * len(hard_failures)
        return RubricResult(
            passed=passed,
            score=max(score, 0.0),
            warnings=list(dict.fromkeys(warnings)),
            hard_failures=list(dict.fromkeys(hard_failures)),
            feedback=list(dict.fromkeys(feedback)),
        )


class RubricRegistry:
    def __init__(self, rubrics: list[BaseRubric]):
        self._rubrics = {rubric.pool: rubric for rubric in rubrics}

    def get(self, pool: str) -> BaseRubric:
        return self._rubrics.get(str(pool or "").strip(), self._rubrics["deep_dive"])

