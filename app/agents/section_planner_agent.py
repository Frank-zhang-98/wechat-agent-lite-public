from __future__ import annotations

import re
from typing import Any

from app.agents.base import AgentContext
from app.policies.base_policy import SectionRoleTemplate
from app.runtime.state_models import ArticleIntent, SectionPlan, SectionSpec


class SectionPlannerAgent:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    def plan(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        intent: ArticleIntent,
    ) -> tuple[SectionPlan, dict[str, Any]]:
        policy = self.ctx.policy_registry.get(intent.pool)
        if str(fact_pack.get("article_variant", "") or "").strip() == "project_explainer":
            sections = self._build_project_explainer_sections(
                topic=topic,
                fact_pack=fact_pack,
                fact_compress=fact_compress,
                intent=intent,
            )
        else:
            sections = [
                self._build_section(
                    template=template,
                    topic=topic,
                    fact_pack=fact_pack,
                    fact_compress=fact_compress,
                    intent=intent,
                )
                for template in policy.section_templates(fact_pack)
            ]
        plan = SectionPlan(pool=intent.pool, sections=sections, strategy_label=policy.label)
        return plan, {
            "summary": {"pool": intent.pool, "sections": len(sections), "strategy": policy.label},
            "outputs": [{"title": "section_plan", "text": str(plan.as_dict()), "language": "json"}],
        }

    def _build_section(
        self,
        *,
        template: SectionRoleTemplate,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        intent: ArticleIntent,
    ) -> SectionSpec:
        evidence = self._evidence_for_role(
            role=template.role,
            topic=topic,
            fact_pack=fact_pack,
            fact_compress=fact_compress,
            intent=intent,
        )
        heading_hint = evidence[0] if evidence else template.default_heading
        return SectionSpec(
            role=template.role,
            goal=template.goal,
            must_cover=list(template.must_cover),
            must_avoid=list(template.must_avoid),
            evidence_refs=evidence[:6],
            heading_hint=self._clean_heading_hint(heading_hint, fallback=template.default_heading, intent=intent),
        )

    def _evidence_for_role(
        self,
        *,
        role: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        intent: ArticleIntent,
    ) -> list[str]:
        if intent.pool == "news":
            mapping = {
                "event_frame": [
                    *list(fact_compress.get("what_it_is") or []),
                    str(topic.get("title", "") or ""),
                    str(fact_pack.get("source_lead", "") or ""),
                    *list(fact_pack.get("key_points") or []),
                ],
                "change_focus": [
                    *list(fact_compress.get("key_mechanisms") or []),
                    *list(fact_pack.get("grounded_hard_facts") or []),
                    *list(fact_pack.get("key_points") or []),
                ],
                "meaning_or_risk": [
                    *list(fact_compress.get("concrete_scenarios") or []),
                    *list(fact_pack.get("industry_context_points") or []),
                    *list(fact_pack.get("grounded_context_facts") or []),
                    *list(fact_compress.get("risks") or []),
                    *list(fact_pack.get("soft_inferences") or []),
                ],
                "watch_signals": [
                    *list(fact_compress.get("risks") or []),
                    *list(fact_compress.get("uncertainties") or []),
                    *list(fact_pack.get("unknowns") or []),
                ],
            }
            return self._merge_unique(mapping.get(role, []))
        if intent.pool == "github":
            mapping = {
                "project_positioning": [
                    str(topic.get("title", "") or ""),
                    str(topic.get("summary", "") or ""),
                    *list(fact_pack.get("key_points") or []),
                ],
                "who_should_use": list(fact_pack.get("coverage_checklist") or []),
                "how_it_works": [
                    *list(fact_pack.get("architecture_points") or []),
                    *list(fact_pack.get("implementation_steps") or []),
                    *[
                        str(item.get("source_path", "") or "")
                        for item in (fact_pack.get("github_source_code_blocks") or [])
                        if isinstance(item, dict)
                    ],
                ],
                "engineering_tradeoffs": [
                    *list(fact_pack.get("unknowns") or []),
                    *list(fact_pack.get("soft_inferences") or []),
                ],
                "deployment_boundary": [
                    str(fact_pack.get("github_repo_url", "") or ""),
                    *list(fact_pack.get("deployment_points") or []),
                ],
            }
            return self._merge_unique(mapping.get(role, []))
        mapping = {
            "problem_frame": [str(topic.get("title", "") or ""), *list(fact_pack.get("key_points") or [])],
            "mechanism": [
                *list(fact_compress.get("key_mechanisms") or []),
                *list(fact_pack.get("architecture_points") or []),
            ],
            "implementation_or_evidence": [
                *list(fact_pack.get("implementation_steps") or []),
                *list(fact_pack.get("grounded_hard_facts") or []),
            ],
            "constraint_or_boundary": [
                *list(fact_compress.get("risks") or []),
                *list(fact_pack.get("unknowns") or []),
                *list(fact_pack.get("soft_inferences") or []),
            ],
        }
        return self._merge_unique(mapping.get(role, []))

    def _build_project_explainer_sections(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        intent: ArticleIntent,
    ) -> list[SectionSpec]:
        blueprint = [dict(item) for item in (fact_pack.get("section_blueprint") or []) if isinstance(item, dict)]
        ranked = sorted(
            blueprint,
            key=lambda item: (-self._project_section_priority(item=item), blueprint.index(item)),
        )
        selected = sorted(ranked[:7], key=lambda item: blueprint.index(item))
        if len(selected) < 5:
            selected = blueprint[: min(7, len(blueprint))]
        sections: list[SectionSpec] = []
        for item in selected:
            heading = str(item.get("heading", "") or item.get("source_heading", "") or "").strip()
            summary = str(item.get("summary", "") or "").strip()
            role = self._project_section_role(heading=heading, summary=summary)
            evidence = self._merge_unique(
                [heading, summary],
                fact_compress.get("component_points", []) if role == "mechanism" else [],
                fact_compress.get("evaluation_points", []) if role == "implementation_or_evidence" else [],
                fact_compress.get("benchmark_points", []) if role == "implementation_or_evidence" else [],
                fact_compress.get("implementation_chain", []) if role == "implementation_or_evidence" else [],
                fact_pack.get("coverage_checklist", []),
                fact_pack.get("key_points", []),
            )[:6]
            sections.append(
                SectionSpec(
                    role=role,
                    goal=self._project_section_goal(role=role),
                    must_cover=self._project_must_cover(role=role),
                    must_avoid=list(intent.must_avoid),
                    evidence_refs=evidence,
                    heading_hint=heading,
                )
            )
        return self._ensure_project_role_coverage(
            sections=sections,
            topic=topic,
            fact_pack=fact_pack,
            fact_compress=fact_compress,
            intent=intent,
        )

    @staticmethod
    def _project_section_priority(*, item: dict[str, Any]) -> int:
        text = " ".join(
            [
                str(item.get("heading", "") or "").lower(),
                str(item.get("source_heading", "") or "").lower(),
                str(item.get("summary", "") or "").lower(),
            ]
        )
        score = 0
        if re.search(r"benchmark|evaluation|compare|comparison|latency|performance|评测|对比|基准|延迟|性能", text, flags=re.IGNORECASE):
            score += 5
        if re.search(r"architecture|module|component|system|workflow|pipeline|模块|组件|架构|流程|链路", text, flags=re.IGNORECASE):
            score += 4
        if re.search(r"implementation|build|code|how it works|实现|代码|构建", text, flags=re.IGNORECASE):
            score += 3
        if re.search(r"problem|pain|why|背景|问题|痛点", text, flags=re.IGNORECASE):
            score += 2
        if re.search(r"limit|boundary|tradeoff|failure|risk|边界|限制|失败|取舍|who this is for|when to use|when not to use|skip it|token budget|dedup", text, flags=re.IGNORECASE):
            score += 2
        return score

    @staticmethod
    def _project_section_role(*, heading: str, summary: str) -> str:
        text = f"{heading} {summary}".lower()
        if re.search(r"problem|pain|why|背景|问题|痛点", text, flags=re.IGNORECASE):
            return "problem_frame"
        if re.search(r"limit|boundary|tradeoff|failure|risk|边界|限制|失败|取舍|who this is for|when to use|when not to use|skip it|token budget|dedup", text, flags=re.IGNORECASE):
            return "constraint_or_boundary"
        if re.search(r"benchmark|evaluation|compare|comparison|latency|performance|评测|对比|基准|延迟|性能", text, flags=re.IGNORECASE):
            return "implementation_or_evidence"
        if re.search(r"architecture|module|component|system|workflow|pipeline|模块|组件|架构|流程|链路", text, flags=re.IGNORECASE):
            return "mechanism"
        return "implementation_or_evidence"

    @staticmethod
    def _project_section_goal(*, role: str) -> str:
        return {
            "problem_frame": "Explain the original problem and why the project exists.",
            "mechanism": "Explain concrete components and how they fit together.",
            "implementation_or_evidence": "Preserve implementation steps, evaluation, and benchmark evidence.",
            "constraint_or_boundary": "Explain tradeoffs, boundaries, and failure cases.",
        }.get(role, "Preserve the original high-value technical section.")

    @staticmethod
    def _project_must_cover(*, role: str) -> list[str]:
        return {
            "problem_frame": ["problem", "motivation"],
            "mechanism": ["component", "architecture"],
            "implementation_or_evidence": ["implementation", "benchmark", "evaluation"],
            "constraint_or_boundary": ["boundary", "tradeoff"],
        }.get(role, ["technical detail"])

    def _ensure_project_role_coverage(
        self,
        *,
        sections: list[SectionSpec],
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_compress: dict[str, Any],
        intent: ArticleIntent,
    ) -> list[SectionSpec]:
        present = {section.role for section in sections}
        additions: list[SectionSpec] = []

        if "constraint_or_boundary" not in present:
            evidence = self._merge_unique(
                fact_compress.get("risks", []),
                fact_compress.get("uncertainties", []),
                fact_compress.get("evaluation_points", []),
                fact_pack.get("unknowns", []),
                fact_pack.get("coverage_checklist", []),
            )[:6]
            if evidence:
                additions.append(
                    SectionSpec(
                        role="constraint_or_boundary",
                        goal=self._project_section_goal(role="constraint_or_boundary"),
                        must_cover=self._project_must_cover(role="constraint_or_boundary"),
                        must_avoid=list(intent.must_avoid),
                        evidence_refs=evidence,
                        heading_hint="Limits, tradeoffs, and boundaries",
                    )
                )

        if "problem_frame" not in present:
            evidence = self._merge_unique(
                str(topic.get("title", "") or "").strip(),
                fact_pack.get("key_points", []),
                fact_compress.get("what_it_is", []),
            )[:6]
            if evidence:
                additions.append(
                    SectionSpec(
                        role="problem_frame",
                        goal=self._project_section_goal(role="problem_frame"),
                        must_cover=self._project_must_cover(role="problem_frame"),
                        must_avoid=list(intent.must_avoid),
                        evidence_refs=evidence,
                        heading_hint="Problem framing and motivation",
                    )
                )

        if "mechanism" not in present:
            evidence = self._merge_unique(
                fact_compress.get("component_points", []),
                fact_pack.get("architecture_points", []),
                fact_pack.get("coverage_checklist", []),
            )[:6]
            if evidence:
                additions.append(
                    SectionSpec(
                        role="mechanism",
                        goal=self._project_section_goal(role="mechanism"),
                        must_cover=self._project_must_cover(role="mechanism"),
                        must_avoid=list(intent.must_avoid),
                        evidence_refs=evidence,
                        heading_hint="Core components and architecture",
                    )
                )

        if "implementation_or_evidence" not in present:
            evidence = self._merge_unique(
                fact_compress.get("implementation_chain", []),
                fact_compress.get("benchmark_points", []),
                fact_pack.get("implementation_steps", []),
            )[:6]
            if evidence:
                additions.append(
                    SectionSpec(
                        role="implementation_or_evidence",
                        goal=self._project_section_goal(role="implementation_or_evidence"),
                        must_cover=self._project_must_cover(role="implementation_or_evidence"),
                        must_avoid=list(intent.must_avoid),
                        evidence_refs=evidence,
                        heading_hint="Implementation and evaluation",
                    )
                )

        return (sections + additions)[:8]

    @staticmethod
    def _merge_unique(*values: Any) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                text = str(entry or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                output.append(text)
        return output

    @staticmethod
    def _clean_heading_hint(text: str, *, fallback: str, intent: ArticleIntent) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return fallback
        if len(cleaned) > 28:
            cleaned = cleaned.split("，", 1)[0].split(":", 1)[0].strip() or cleaned[:28]
        for banned in intent.must_avoid:
            if banned and banned in cleaned:
                return fallback
        return cleaned
