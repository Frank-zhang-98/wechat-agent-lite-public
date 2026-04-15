from __future__ import annotations

from typing import Any

from app.policies.base_policy import BasePolicy, SectionRoleTemplate, SubtypeProfile


class DeepDivePolicy(BasePolicy):
    pool = "deep_dive"
    label = "Deep Dive"
    title_preferences = ("problem first", "clear mechanism", "explicit boundary")
    visual_preferences = ("architecture_diagram", "process_explainer_infographic", "comparison_infographic")
    subtype_profiles = {
        "tutorial": SubtypeProfile(
            subtype="tutorial",
            label="Tutorial",
            default_audience="ai_builder",
            title_mode="tutorial",
            visual_mode="tutorial",
            layout_name="practical_tutorial",
        ),
        "technical_walkthrough": SubtypeProfile(
            subtype="technical_walkthrough",
            label="Technical Walkthrough",
            default_audience="ai_builder",
            title_mode="technical_walkthrough",
            visual_mode="technical_walkthrough",
            layout_name="practical_tutorial",
        ),
        "tool_review": SubtypeProfile(
            subtype="tool_review",
            label="Tool Review",
            default_audience="ai_product_manager",
            title_mode="tool_review",
            visual_mode="product_review",
            layout_name="product_review",
        ),
    }
    default_subtype = "tool_review"
    banned_heading_phrases = ("发生了什么", "对产品经理的影响")

    def section_templates(self, fact_pack: dict[str, Any]) -> list[SectionRoleTemplate]:
        return [
            SectionRoleTemplate(
                role="problem_frame",
                goal="Define the problem and the background context.",
                default_heading="Problem frame",
                must_cover=("problem", "background"),
            ),
            SectionRoleTemplate(
                role="mechanism",
                goal="Explain the underlying mechanism and key ideas.",
                default_heading="Core mechanism",
                must_cover=("mechanism", "key ideas"),
            ),
            SectionRoleTemplate(
                role="implementation_or_evidence",
                goal="Show implementation details or evidence chain.",
                default_heading="Implementation and evidence",
                must_cover=("implementation", "evidence"),
            ),
            SectionRoleTemplate(
                role="constraint_or_boundary",
                goal="Describe the usable boundary, tradeoffs, and constraints.",
                default_heading="Boundary and constraints",
                must_cover=("boundary", "constraints"),
            ),
        ]

    def subtype(self, *, topic: dict[str, Any], fact_pack: dict[str, Any]) -> str:
        title = " ".join(
            [
                str(topic.get("title", "") or ""),
                str(topic.get("summary", "") or ""),
                " ".join(str(item).strip() for item in (fact_pack.get("key_points") or [])[:5]),
            ]
        ).lower()
        implementation_steps = len(fact_pack.get("implementation_steps") or [])
        architecture_points = len(fact_pack.get("architecture_points") or [])
        code_blocks = len(fact_pack.get("code_artifacts") or []) + len(fact_pack.get("github_source_code_blocks") or [])
        if any(token in title for token in ("tutorial", "guide", "how to", "step-by-step", "入门", "教程", "上手")):
            return "tutorial"
        if implementation_steps >= 2 or architecture_points >= 2 or code_blocks >= 1:
            return "technical_walkthrough"
        return "tool_review"
