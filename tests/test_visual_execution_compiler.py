import unittest

from app.runtime.state_models import VisualBlueprint
from app.services.visual_execution_compiler import VisualExecutionCompiler


class VisualExecutionCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = VisualExecutionCompiler()

    def test_compile_blueprint_news_does_not_emit_generated_body_item(self) -> None:
        blueprint = VisualBlueprint(
            cover_family="thesis",
            cover_brief={},
            body_policy={"max_allowed": 2},
            items=[
                {
                    "placement_key": "section_1",
                    "anchor_heading": "事件核心",
                    "section_role": "event_frame",
                    "intent_kind": "explanatory",
                    "preferred_mode": "generate",
                    "visual_goal": "解释融资事件关系",
                    "task_priorities": {
                        "reference": "low",
                        "evidence": "medium",
                        "explanatory": "high",
                        "none": "low",
                    },
                }
            ],
        )

        compiled = self.compiler.compile_blueprint(
            visual_blueprint=blueprint,
            pool="news",
            subtype="breaking_news",
            topic={"title": "新闻标题", "url": "https://example.com/story"},
            fact_pack={"topic_title": "新闻标题"},
            web_enrich={},
            source_structure={},
            image_candidates=[],
            max_body_illustrations=2,
        )

        self.assertEqual(compiled.items, [])

    def test_compile_blueprint_deep_dive_only_generates_when_explicitly_requested_for_non_first_item(self) -> None:
        blueprint = VisualBlueprint(
            cover_family="structure",
            cover_brief={},
            body_policy={"max_allowed": 2},
            items=[
                {
                    "placement_key": "section_1",
                    "anchor_heading": "产品背景",
                    "section_role": "overview",
                    "intent_kind": "reference",
                    "preferred_mode": "acquire",
                    "visual_goal": "先展示可信参考图",
                    "task_priorities": {
                        "reference": "high",
                        "evidence": "medium",
                        "explanatory": "low",
                        "none": "low",
                    },
                    "subject_ref": {"kind": "product", "name": "深度解析对象"},
                },
                {
                    "placement_key": "section_2",
                    "anchor_heading": "机制说明",
                    "section_role": "architecture",
                    "intent_kind": "explanatory",
                    "preferred_mode": "generate",
                    "visual_goal": "解释系统机制",
                    "task_priorities": {
                        "reference": "medium",
                        "evidence": "medium",
                        "explanatory": "high",
                        "none": "low",
                    },
                }
            ],
        )

        compiled = self.compiler.compile_blueprint(
            visual_blueprint=blueprint,
            pool="deep_dive",
            subtype="technical_walkthrough",
            topic={"title": "深度解析"},
            fact_pack={"topic_title": "深度解析"},
            web_enrich={},
            source_structure={},
            image_candidates=[],
            max_body_illustrations=2,
        )

        self.assertEqual(len(compiled.items), 2)
        self.assertEqual(compiled.items[1]["preferred_mode"], "generate")
        self.assertEqual(compiled.items[1]["mode"], "generate")

    def test_compile_blueprint_product_release_news_prefers_capture_after_acquire_candidates_fail(self) -> None:
        blueprint = VisualBlueprint(
            cover_family="thesis",
            cover_brief={},
            body_policy={"max_allowed": 1},
            items=[
                {
                    "placement_key": "section_1",
                    "anchor_heading": "产品开放",
                    "section_role": "product_update",
                    "intent_kind": "reference",
                    "preferred_mode": "acquire",
                    "visual_goal": "展示产品/API 的官方参考图",
                    "subject_ref": {"kind": "product", "name": "Seedance 2.0 API"},
                    "task_priorities": {"reference": "high", "evidence": "medium", "explanatory": "disabled", "none": "low"},
                }
            ],
        )

        compiled = self.compiler.compile_blueprint(
            visual_blueprint=blueprint,
            pool="news",
            subtype="industry_news",
            topic={"title": "火山引擎 Seedance 2.0 API 上线", "url": "https://media.example.com/post"},
            fact_pack={"topic_title": "火山引擎 Seedance 2.0 API 上线", "primary_pool": "news"},
            web_enrich={"official_sources": [{"url": "https://seed.example.com/docs", "title": "Seedance Docs"}]},
            source_structure={},
            image_candidates=[],
            max_body_illustrations=1,
        )

        self.assertEqual(len(compiled.items), 1)
        self.assertEqual(compiled.items[0]["preferred_mode"], "capture")
        self.assertEqual(compiled.items[0]["mode"], "capture")
        self.assertTrue(compiled.items[0]["constraints"]["capture_targets"])

    def test_compile_blueprint_product_release_news_allows_official_logo_only_after_capture_unavailable(self) -> None:
        blueprint = VisualBlueprint(
            cover_family="thesis",
            cover_brief={},
            body_policy={"max_allowed": 1},
            items=[
                {
                    "placement_key": "section_1",
                    "anchor_heading": "产品开放",
                    "section_role": "product_update",
                    "intent_kind": "reference",
                    "preferred_mode": "acquire",
                    "visual_goal": "建立品牌识别",
                    "subject_ref": {"kind": "product", "name": "Seedance"},
                    "task_priorities": {"reference": "high", "evidence": "medium", "explanatory": "disabled", "none": "low"},
                }
            ],
        )

        compiled = self.compiler.compile_blueprint(
            visual_blueprint=blueprint,
            pool="news",
            subtype="industry_news",
            topic={"title": "Seedance API 发布", "url": "https://media.example.com/post"},
            fact_pack={"topic_title": "Seedance API 发布", "primary_pool": "news"},
            web_enrich={},
            source_structure={},
            image_candidates=[
                {
                    "url": "https://seed.example.com/logo.png",
                    "source_role": "object_official",
                    "image_kind": "logo",
                }
            ],
            max_body_illustrations=1,
        )

        self.assertEqual(len(compiled.items), 1)
        self.assertEqual(compiled.items[0]["preferred_mode"], "acquire")
        self.assertTrue(compiled.items[0]["constraints"]["allow_logo_fallback"])

    def test_compile_blueprint_project_explainer_prefers_acquire_for_source_or_repo_tech_visuals(self) -> None:
        blueprint = VisualBlueprint(
            cover_family="structure",
            cover_brief={},
            body_policy={"max_allowed": 1},
            items=[
                {
                    "placement_key": "section_1",
                    "anchor_heading": "Component architecture",
                    "section_role": "architecture",
                    "intent_kind": "reference",
                    "preferred_mode": "acquire",
                    "visual_goal": "Preserve source or repo technical visuals",
                    "subject_ref": {"kind": "project", "name": "Context Engine"},
                    "task_priorities": {"reference": "high", "evidence": "medium", "explanatory": "disabled", "none": "low"},
                }
            ],
        )

        compiled = self.compiler.compile_blueprint(
            visual_blueprint=blueprint,
            pool="deep_dive",
            subtype="tutorial",
            topic={"title": "Context Engine deep dive", "url": "https://tds.example.com/post"},
            fact_pack={"topic_title": "Context Engine deep dive", "primary_pool": "deep_dive", "article_variant": "project_explainer"},
            web_enrich={},
            source_structure={},
            image_candidates=[{"url": "https://tds.example.com/diagram.png", "source_role": "source_article_tech_visual", "image_kind": "diagram"}],
            max_body_illustrations=1,
        )

        self.assertEqual(len(compiled.items), 1)
        self.assertEqual(compiled.items[0]["preferred_mode"], "acquire")
        self.assertEqual(compiled.items[0]["constraints"]["source_role_order"][0], "source_article_tech_visual")

    def test_compile_blueprint_project_explainer_uses_repo_capture_when_only_repo_pages_exist(self) -> None:
        blueprint = VisualBlueprint(
            cover_family="structure",
            cover_brief={},
            body_policy={"max_allowed": 1},
            items=[
                {
                    "placement_key": "section_1",
                    "anchor_heading": "Docs walkthrough",
                    "section_role": "implementation_or_evidence",
                    "intent_kind": "reference",
                    "preferred_mode": "acquire",
                    "visual_goal": "Show repo docs or demo page",
                    "subject_ref": {"kind": "project", "name": "Context Engine"},
                    "task_priorities": {"reference": "high", "evidence": "medium", "explanatory": "disabled", "none": "low"},
                }
            ],
        )

        compiled = self.compiler.compile_blueprint(
            visual_blueprint=blueprint,
            pool="deep_dive",
            subtype="tutorial",
            topic={"title": "Context Engine deep dive", "url": "https://tds.example.com/post"},
            fact_pack={
                "topic_title": "Context Engine deep dive",
                "primary_pool": "deep_dive",
                "article_variant": "project_explainer",
                "github_repo_url": "https://github.com/example/context-engine",
            },
            web_enrich={"official_sources": [{"url": "https://github.com/example/context-engine#readme", "title": "README"}]},
            source_structure={},
            image_candidates=[],
            max_body_illustrations=1,
        )

        self.assertEqual(len(compiled.items), 1)
        self.assertEqual(compiled.items[0]["preferred_mode"], "capture")
        self.assertTrue(compiled.items[0]["constraints"]["capture_targets"])


if __name__ == "__main__":
    unittest.main()
