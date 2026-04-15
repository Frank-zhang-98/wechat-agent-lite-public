from __future__ import annotations

from typing import Any

from app.policies.base_policy import BasePolicy, SectionRoleTemplate, SubtypeProfile


class GithubPolicy(BasePolicy):
    pool = "github"
    label = "GitHub"
    title_preferences = ("project positioning first", "clear fit and audience", "concrete implementation path")
    visual_preferences = ("architecture_diagram", "workflow_diagram", "system_layers_infographic")
    subtype_profiles = {
        "repo_recommendation": SubtypeProfile(
            subtype="repo_recommendation",
            label="Repo Recommendation",
            default_audience="ai_product_manager",
            title_mode="repo_recommendation",
            visual_mode="product_review",
            layout_name="product_review",
        ),
        "code_explainer": SubtypeProfile(
            subtype="code_explainer",
            label="Code Explainer",
            default_audience="ai_builder",
            title_mode="code_explainer",
            visual_mode="architecture_diagram",
            layout_name="practical_tutorial",
        ),
        "stack_analysis": SubtypeProfile(
            subtype="stack_analysis",
            label="Stack Analysis",
            default_audience="ai_builder",
            title_mode="stack_analysis",
            visual_mode="workflow_diagram",
            layout_name="practical_tutorial",
        ),
        "collection_repo": SubtypeProfile(
            subtype="collection_repo",
            label="Collection Repo",
            default_audience="ai_product_manager",
            title_mode="repo_collection",
            visual_mode="product_review",
            layout_name="product_review",
        ),
    }
    default_subtype = "repo_recommendation"
    banned_heading_phrases = ("发生了什么", "对产品经理的影响")

    def section_templates(self, fact_pack: dict[str, Any]) -> list[SectionRoleTemplate]:
        return [
            SectionRoleTemplate(
                role="project_positioning",
                goal="State what the project is and what problem it solves.",
                default_heading="Project positioning",
                must_cover=("project", "problem"),
            ),
            SectionRoleTemplate(
                role="who_should_use",
                goal="Clarify target users and the right usage scenarios.",
                default_heading="Who should use it",
                must_cover=("scenarios", "reader fit"),
            ),
            SectionRoleTemplate(
                role="how_it_works",
                goal="Explain the implementation chain and the major moving parts.",
                default_heading="How it works",
                must_cover=("implementation", "architecture", "code"),
            ),
            SectionRoleTemplate(
                role="engineering_tradeoffs",
                goal="Discuss engineering tradeoffs, limitations, and adoption cost.",
                default_heading="Tradeoffs",
                must_cover=("tradeoffs", "limits", "cost"),
            ),
            SectionRoleTemplate(
                role="deployment_boundary",
                goal="Explain repo link, deployment mode, and integration boundary.",
                default_heading="Deployment boundary",
                must_cover=("deployment", "integration", "repo link"),
            ),
        ]

    def subtype(self, *, topic: dict[str, Any], fact_pack: dict[str, Any]) -> str:
        archetype = str(fact_pack.get("github_repo_archetype", "") or "").strip()
        if archetype == "collection_repo":
            return "collection_repo"
        if archetype in {"sdk", "agent_framework", "workflow_runtime"}:
            return "stack_analysis"
        code_blocks = len(fact_pack.get("github_source_code_blocks") or [])
        implementation_steps = len(fact_pack.get("implementation_steps") or [])
        architecture_points = len(fact_pack.get("architecture_points") or [])
        if code_blocks >= 1 and (implementation_steps >= 1 or architecture_points >= 1):
            return "code_explainer"
        return "repo_recommendation"
