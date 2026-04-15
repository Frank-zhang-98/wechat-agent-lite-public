import unittest
from types import SimpleNamespace

from app.services.visual_strategy_service import VisualStrategyService


class VisualStrategyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = VisualStrategyService()

    def test_build_blueprint_parses_new_decision_schema(self) -> None:
        llm = SimpleNamespace(
            call=lambda *args, **kwargs: SimpleNamespace(
                text="""{
                    "cover_family": "structure",
                    "cover_brief": {"main_claim": "Agent Runtime", "subject_hint": "Agent Runtime"},
                    "items": [
                        {
                            "placement_key": "section_1",
                            "anchor_heading": "System",
                            "section_role": "architecture",
                            "intent_kind": "reference",
                            "preferred_mode": "acquire",
                            "visual_goal": "锚定核心项目",
                            "visual_claim": "先展示真实项目对象",
                            "subject_ref": {"kind": "project", "name": "Agent Runtime"},
                            "subject_slots": {
                                "project_subject": {"name": "Agent Runtime", "priority": "high"},
                                "page_subject": {"name": "Docs", "priority": "medium"}
                            },
                            "task_priorities": {
                                "reference": "high",
                                "evidence": "medium",
                                "explanatory": "low",
                                "none": "disabled"
                            },
                            "facts_to_visualize": ["repo", "docs"]
                        }
                    ]
                }"""
            )
        )
        blueprint = self.service.build_blueprint(
            run_id="run-1",
            topic={"title": "Agent Runtime"},
            fact_pack={"primary_pool": "github", "subtype": "code_explainer"},
            fact_grounding={},
            source_structure={},
            image_candidates=[],
            llm=llm,
            max_body_illustrations=2,
        )
        self.assertEqual(blueprint.cover_family, "structure")
        self.assertEqual(blueprint.body_policy["max_allowed"], 2)
        self.assertNotIn("min_required", blueprint.body_policy)
        self.assertEqual(blueprint.items[0]["intent_kind"], "reference")
        self.assertEqual(blueprint.items[0]["preferred_mode"], "acquire")
        self.assertEqual(blueprint.items[0]["subject_ref"]["kind"], "project")
        self.assertEqual(blueprint.items[0]["subject_slots"]["project_subject"]["priority"], "high")

    def test_build_blueprint_empty_response_does_not_force_generated_item(self) -> None:
        llm = SimpleNamespace(call=lambda *args, **kwargs: SimpleNamespace(text='{"cover_family":"structure","cover_brief":{},"items":[]}'))
        blueprint = self.service.build_blueprint(
            run_id="run-empty",
            topic={"title": "Breaking model pricing change"},
            fact_pack={
                "primary_pool": "news",
                "subtype": "breaking_news",
                "topic_title": "Breaking model pricing change",
                "section_blueprint": [{"heading": "事件脉络", "summary": "What changed and why it matters."}],
            },
            fact_grounding={},
            source_structure={},
            image_candidates=[],
            llm=llm,
            max_body_illustrations=1,
        )
        self.assertEqual(blueprint.body_policy["max_allowed"], 1)
        self.assertNotIn("min_required", blueprint.body_policy)
        self.assertEqual(blueprint.items, [])

    def test_build_blueprint_clamps_body_illustration_count_without_minimum(self) -> None:
        llm = SimpleNamespace(call=lambda *args, **kwargs: SimpleNamespace(text='{"cover_family":"structure","cover_brief":{},"items":[]}'))
        blueprint = self.service.build_blueprint(
            run_id="run-zero",
            topic={"title": "Deep dive topic"},
            fact_pack={"primary_pool": "deep_dive", "subtype": "technical_walkthrough"},
            fact_grounding={},
            source_structure={},
            image_candidates=[],
            llm=llm,
            max_body_illustrations=0,
        )
        self.assertEqual(blueprint.body_policy["max_allowed"], 0)
        self.assertEqual(blueprint.items, [])

    def test_build_blueprint_ignores_legacy_body_illustrations_payload(self) -> None:
        llm = SimpleNamespace(
            call=lambda *args, **kwargs: SimpleNamespace(
                text="""{
                    "cover_family": "structure",
                    "cover_brief": {},
                    "body_illustrations": [
                        {
                            "type": "architecture_diagram",
                            "section": "Architecture",
                            "title": "Old schema diagram"
                        }
                    ]
                }"""
            )
        )
        blueprint = self.service.build_blueprint(
            run_id="run-legacy",
            topic={"title": "Legacy topic"},
            fact_pack={"primary_pool": "github", "subtype": "code_explainer"},
            fact_grounding={},
            source_structure={},
            image_candidates=[],
            llm=llm,
            max_body_illustrations=1,
        )
        self.assertEqual(blueprint.items, [])

    def test_strategy_profile_enables_capture_for_product_release_news(self) -> None:
        profile = self.service._strategy_profile(pool="news", subtype="industry_news", variant="product_release_news")

        self.assertEqual(profile["mode_order"], ["acquire", "capture", "none"])
        self.assertTrue(profile["allow_capture"])
        self.assertEqual(profile["reference_subject_order"][0], "company_subject")

    def test_strategy_profile_for_project_explainer_prefers_repo_visuals_without_generate(self) -> None:
        profile = self.service._strategy_profile(
            pool="deep_dive",
            subtype="tutorial",
            variant="project_explainer",
            article_variant="project_explainer",
        )

        self.assertEqual(profile["mode_order"], ["acquire", "capture", "none"])
        self.assertTrue(profile["allow_capture"])
        self.assertFalse(profile["allow_explanatory_generate"])
        self.assertEqual(profile["reference_subject_order"][0], "project_subject")


if __name__ == "__main__":
    unittest.main()
