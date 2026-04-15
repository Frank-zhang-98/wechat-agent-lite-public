import unittest
from types import SimpleNamespace

from app.agents.base import AgentContext
from app.agents.section_planner_agent import SectionPlannerAgent
from app.policies import DeepDivePolicy, GithubPolicy, NewsPolicy, PolicyRegistry
from app.rubrics import DeepDiveRubric, GithubRubric, NewsRubric, RubricRegistry
from app.runtime.state_models import ArticleIntent


class SectionPlannerAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        ctx = AgentContext(
            support=SimpleNamespace(),
            policy_registry=PolicyRegistry([NewsPolicy(), GithubPolicy(), DeepDivePolicy()]),
            rubric_registry=RubricRegistry([NewsRubric(), GithubRubric(), DeepDiveRubric()]),
        )
        self.agent = SectionPlannerAgent(ctx)

    def test_project_explainer_preserves_source_sections_and_benchmark_section(self) -> None:
        plan, _ = self.agent.plan(
            topic={"title": "Context Engine walkthrough"},
            fact_pack={
                "article_variant": "project_explainer",
                "section_blueprint": [
                    {"heading": "Problem framing", "summary": "Why the project exists."},
                    {"heading": "Component architecture", "summary": "Core modules and responsibilities."},
                    {"heading": "Implementation pipeline", "summary": "Execution chain and request flow."},
                    {"heading": "Benchmark and evaluation", "summary": "Latency and retrieval quality."},
                    {"heading": "Tradeoffs and failure modes", "summary": "Known boundaries."},
                ],
                "coverage_checklist": ["Context engine", "Benchmark"],
                "key_points": ["Project overview"],
            },
            fact_compress={
                "component_points": ["Context engine", "Cache module"],
                "evaluation_points": ["Compared against baseline retriever"],
                "benchmark_points": ["Latency dropped by 20%"],
                "implementation_chain": ["Fetch -> compose -> rerank"],
            },
            intent=ArticleIntent(pool="deep_dive", subtype="tutorial", core_angle="Explain the system", audience="builder"),
        )

        self.assertGreaterEqual(len(plan.sections), 5)
        headings = [section.heading_hint for section in plan.sections]
        roles = [section.role for section in plan.sections]
        self.assertIn("Benchmark and evaluation", headings)
        self.assertIn("Component architecture", headings)
        self.assertIn("constraint_or_boundary", roles)

    def test_standard_deep_dive_keeps_policy_template_shape(self) -> None:
        plan, _ = self.agent.plan(
            topic={"title": "General technical deep dive"},
            fact_pack={"article_variant": "standard"},
            fact_compress={},
            intent=ArticleIntent(pool="deep_dive", subtype="technical_walkthrough", core_angle="Explain", audience="builder"),
        )

        self.assertEqual(len(plan.sections), 4)


if __name__ == "__main__":
    unittest.main()
