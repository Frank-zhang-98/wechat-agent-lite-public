import unittest
from types import SimpleNamespace

from app.graphs.nodes.plan_visuals_node import build_plan_visuals_node
from app.runtime.state_models import VisualAssetSet, VisualBlueprint


class PlanVisualsNodeTests(unittest.TestCase):
    def test_plan_visuals_uses_compiler_and_does_not_auto_generate_fallback(self) -> None:
        captured = {}

        def build_candidates(**kwargs):
            return []

        def build_blueprint(**kwargs):
            return VisualBlueprint(
                cover_family="thesis",
                cover_brief={},
                body_policy={"max_allowed": 1, "prefer_mode": "acquire", "fallback_mode": "generate"},
                items=[
                    {
                        "placement_key": "section_1",
                        "anchor_heading": "事件脉络",
                        "section_role": "event_frame",
                        "intent_kind": "reference",
                        "preferred_mode": "acquire",
                        "subject_ref": {"kind": "event", "name": "定价调整"},
                        "visual_goal": "寻找真实事件图",
                    }
                ],
            )

        def compile_blueprint(**kwargs):
            captured["compiled"] = kwargs["visual_blueprint"].as_dict()
            return VisualBlueprint.from_dict(
                {
                    "cover_family": "thesis",
                    "cover_brief": {},
                    "body_policy": {"max_allowed": 1, "prefer_mode": "acquire", "fallback_mode": "generate"},
                    "items": [
                        {
                            "placement_key": "section_1",
                            "anchor_heading": "事件脉络",
                            "section_role": "event_frame",
                            "intent_kind": "reference",
                            "preferred_mode": "acquire",
                            "mode": "crawl",
                            "visual_goal": "寻找真实事件图",
                            "subject_ref": {"kind": "event", "name": "定价调整"},
                            "constraints": {},
                        }
                    ],
                }
            )

        support = SimpleNamespace(
            image_research=SimpleNamespace(build_candidates=build_candidates),
            visual_strategy=SimpleNamespace(build_blueprint=build_blueprint),
            visual_execution_compiler=SimpleNamespace(compile_blueprint=compile_blueprint),
            visual_fit_gate=SimpleNamespace(
                prepare_blueprint=lambda **kwargs: kwargs["visual_blueprint"],
                filter_body_assets=lambda **kwargs: ([], [{"reason": "no_candidate"}]),
            ),
            media_acquisition=SimpleNamespace(acquire=lambda **kwargs: []),
            page_capture=SimpleNamespace(capture=lambda **kwargs: []),
            settings=SimpleNamespace(get_int=lambda *args, **kwargs: 1, get=lambda *args, **kwargs: "1024*1024"),
            llm=SimpleNamespace(),
        )
        generated_blueprints: list[VisualBlueprint] = []

        def generate(**kwargs):
            generated_blueprints.append(kwargs["visual_blueprint"])
            return (VisualAssetSet(body_assets=[]), {"outputs": []})

        node = build_plan_visuals_node(SimpleNamespace(generate=generate), support)
        state = {
            "run": SimpleNamespace(id="run-news"),
            "bootstrap_context": {
                "selected_topic": {"title": "News topic", "url": "https://news.example.com/a"},
                "web_enrich": {},
                "source_structure": {},
            },
            "fact_pack": {"primary_pool": "news", "subtype": "breaking_news", "section_blueprint": [{"heading": "事件脉络"}]},
            "title_plan_state": SimpleNamespace(article_title="News title"),
            "include_cover_assets": False,
            "node_audits": {},
        }

        output = node(state)
        self.assertTrue(captured["compiled"]["items"])
        self.assertEqual(len(generated_blueprints[0].items), 0)
        self.assertEqual(output["visual_assets_state"].body_assets, [])
        self.assertEqual(output["visual_diagnostics"]["visual_fit_failures"][0]["reason"], "no_candidate")
        self.assertEqual(output["visual_diagnostics"]["image_search_path"], "no_image")

    def test_plan_visuals_no_qualified_assets_is_successful_with_diagnostics(self) -> None:
        support = SimpleNamespace(
            image_research=SimpleNamespace(build_candidates=lambda **kwargs: []),
            visual_strategy=SimpleNamespace(build_blueprint=lambda **kwargs: VisualBlueprint(cover_family="structure", cover_brief={}, body_policy={"max_allowed": 0}, items=[])),
            visual_execution_compiler=SimpleNamespace(compile_blueprint=lambda **kwargs: kwargs["visual_blueprint"]),
            visual_fit_gate=SimpleNamespace(
                prepare_blueprint=lambda **kwargs: kwargs["visual_blueprint"],
                filter_body_assets=lambda **kwargs: ([], [{"reason": "semantic_fit_failed"}]),
            ),
            media_acquisition=SimpleNamespace(acquire=lambda **kwargs: []),
            page_capture=SimpleNamespace(capture=lambda **kwargs: []),
            settings=SimpleNamespace(get_int=lambda *args, **kwargs: 1, get=lambda *args, **kwargs: "1024*1024"),
            llm=SimpleNamespace(),
        )
        node = build_plan_visuals_node(SimpleNamespace(generate=lambda **kwargs: (VisualAssetSet(), {"outputs": []})), support)
        state = {
            "run": SimpleNamespace(id="run-no-assets"),
            "bootstrap_context": {"selected_topic": {"title": "Repo topic"}, "web_enrich": {}, "source_structure": {}},
            "fact_pack": {"primary_pool": "github", "subtype": "code_explainer", "section_blueprint": [{"heading": "架构概览"}]},
            "title_plan_state": SimpleNamespace(article_title="Repo title"),
            "include_cover_assets": False,
            "node_audits": {},
        }

        output = node(state)
        self.assertEqual(output["visual_assets_state"].body_assets, [])
        self.assertEqual(output["visual_diagnostics"]["planned_item_count"], 0)
        self.assertTrue(output["visual_diagnostics"]["omitted_by_policy"])
        self.assertEqual(output["visual_diagnostics"]["image_search_path"], "no_image")

    def test_plan_visuals_runs_explicit_generate_items(self) -> None:
        support = SimpleNamespace(
            image_research=SimpleNamespace(build_candidates=lambda **kwargs: []),
            visual_strategy=SimpleNamespace(build_blueprint=lambda **kwargs: VisualBlueprint(cover_family="comparison", cover_brief={}, body_policy={"max_allowed": 1}, items=[])),
            visual_execution_compiler=SimpleNamespace(
                compile_blueprint=lambda **kwargs: VisualBlueprint.from_dict(
                    {
                        "cover_family": "comparison",
                        "cover_brief": {},
                        "body_policy": {"max_allowed": 1},
                        "items": [
                            {
                                "placement_key": "section_1",
                                "anchor_heading": "系统流程",
                                "section_role": "workflow",
                                "intent_kind": "explanatory",
                                "preferred_mode": "generate",
                                "mode": "generate",
                                "visual_goal": "解释系统流程",
                                "subject_ref": {"kind": "mechanism", "name": "工作流"},
                                "brief": {"type": "process_explainer_infographic", "title": "流程图", "caption": "系统流程"},
                                "allowed_families": ["process_explainer_infographic"],
                            }
                        ],
                    }
                )
            ),
            visual_fit_gate=SimpleNamespace(
                prepare_blueprint=lambda **kwargs: kwargs["visual_blueprint"],
                filter_body_assets=lambda **kwargs: (list(kwargs["body_assets"]), []),
            ),
            media_acquisition=SimpleNamespace(acquire=lambda **kwargs: []),
            page_capture=SimpleNamespace(capture=lambda **kwargs: []),
            settings=SimpleNamespace(get_int=lambda *args, **kwargs: 1, get=lambda *args, **kwargs: "1024*1024"),
            llm=SimpleNamespace(),
        )

        def generate(**kwargs):
            self.assertEqual(len(kwargs["visual_blueprint"].items), 1)
            return (
                VisualAssetSet(
                    body_assets=[
                        {
                            "placement_key": "section_1",
                            "anchor_heading": "系统流程",
                            "section_role": "workflow",
                            "type": "process_explainer_infographic",
                            "title": "流程图",
                            "caption": "系统流程",
                            "visual_goal": "解释系统流程",
                            "mode": "generate",
                            "path": "/tmp/generated-flow.png",
                        }
                    ]
                ),
                {"outputs": []},
            )

        node = build_plan_visuals_node(SimpleNamespace(generate=generate), support)
        state = {
            "run": SimpleNamespace(id="run-generate"),
            "bootstrap_context": {"selected_topic": {"title": "Repo topic"}, "web_enrich": {}, "source_structure": {}},
            "fact_pack": {"primary_pool": "github", "subtype": "code_explainer", "section_blueprint": [{"heading": "系统流程"}]},
            "title_plan_state": SimpleNamespace(article_title="Repo title"),
            "include_cover_assets": False,
            "node_audits": {},
        }
        output = node(state)
        self.assertEqual(len(output["visual_assets_state"].body_assets), 1)
        self.assertEqual(output["visual_assets_state"].body_assets[0]["mode"], "generate")

    def test_plan_visuals_records_product_release_variant_diagnostics(self) -> None:
        support = SimpleNamespace(
            image_research=SimpleNamespace(
                build_candidates=lambda **kwargs: [
                    {
                        "url": "https://official.example.com/hero.png",
                        "origin_type": "official",
                        "source_role": "object_official",
                        "image_kind": "photo",
                        "caption": "Official hero",
                        "source_page": "https://official.example.com/launch",
                    }
                ]
            ),
            visual_strategy=SimpleNamespace(build_blueprint=lambda **kwargs: VisualBlueprint(cover_family="thesis", cover_brief={}, body_policy={"max_allowed": 1}, items=[])),
            visual_execution_compiler=SimpleNamespace(compile_blueprint=lambda **kwargs: kwargs["visual_blueprint"]),
            visual_fit_gate=SimpleNamespace(
                prepare_blueprint=lambda **kwargs: kwargs["visual_blueprint"],
                filter_body_assets=lambda **kwargs: (list(kwargs["body_assets"]), []),
            ),
            media_acquisition=SimpleNamespace(
                acquire=lambda **kwargs: [
                    {
                        "status": "acquired",
                        "placement_key": "section_1",
                        "anchor_heading": "产品开放",
                        "section_role": "product_update",
                        "type": "news_photo",
                        "title": "Official hero",
                        "caption": "Official hero",
                        "visual_goal": "展示官方产品页",
                        "mode": "crawl",
                        "path": "/tmp/hero.png",
                        "source_role": "object_official",
                    }
                ]
            ),
            page_capture=SimpleNamespace(capture=lambda **kwargs: []),
            settings=SimpleNamespace(get_int=lambda *args, **kwargs: 1, get=lambda *args, **kwargs: "1024*1024"),
            llm=SimpleNamespace(),
        )
        node = build_plan_visuals_node(SimpleNamespace(generate=lambda **kwargs: (VisualAssetSet(), {"outputs": []})), support)
        state = {
            "run": SimpleNamespace(id="run-release"),
            "bootstrap_context": {
                "selected_topic": {"title": "Seedance 2.0 API 上线", "url": "https://news.example.com/a"},
                "web_enrich": {"official_sources": [{"url": "https://official.example.com/launch"}]},
                "source_structure": {},
            },
            "fact_pack": {"primary_pool": "news", "subtype": "industry_news", "section_blueprint": [{"heading": "产品开放", "summary": "API 发布"}]},
            "title_plan_state": SimpleNamespace(article_title="Seedance 2.0 API 上线"),
            "include_cover_assets": False,
            "node_audits": {},
        }

        output = node(state)
        self.assertEqual(output["fact_pack"]["image_strategy_variant"], "product_release_news")
        self.assertEqual(output["visual_diagnostics"]["image_strategy_variant"], "product_release_news")
        self.assertEqual(output["visual_diagnostics"]["image_search_path"], "primary_then_official")


if __name__ == "__main__":
    unittest.main()
