from __future__ import annotations

from app.rubrics.base_rubric import BaseRubric, RubricResult
from app.runtime.state_models import SectionPlan


class NewsRubric(BaseRubric):
    pool = "news"
    _BANNED = {"发生了什么", "真正重要的变化", "对谁有影响", "对产品经理的影响", "现在该关注什么"}

    def validate_plan(self, section_plan: SectionPlan) -> RubricResult:
        base = super().validate_plan(section_plan)
        warnings = list(base.warnings)
        hard_failures = list(base.hard_failures)
        feedback = list(base.feedback)
        roles = {section.role for section in section_plan.sections}
        required = {"event_frame", "change_focus", "meaning_or_risk", "watch_signals"}
        missing = sorted(required - roles)
        if missing:
            hard_failures.append("missing_news_roles")
            feedback.append("新闻文章缺少核心章节角色")
        for section in section_plan.sections:
            heading = str(section.heading_hint or "").strip()
            if heading in self._BANNED:
                hard_failures.append("template_heading_detected")
                feedback.append(f"新闻小标题仍然模板化：{heading}")
        passed = not hard_failures
        score = 94.0 - 3.0 * len(set(warnings)) - 12.0 * len(set(hard_failures))
        return RubricResult(passed, max(score, 0.0), list(dict.fromkeys(warnings)), list(dict.fromkeys(hard_failures)), list(dict.fromkeys(feedback)))

