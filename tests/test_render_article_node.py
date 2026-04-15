import unittest
from types import SimpleNamespace

from app.graphs.nodes.render_article_node import build_render_article_node


class RenderArticleNodeTests(unittest.TestCase):
    def test_render_article_sets_omitted_by_decision_when_no_items_planned(self) -> None:
        support = SimpleNamespace(
            article_renderer=SimpleNamespace(
                render=lambda *args, **kwargs: SimpleNamespace(
                    html="<div>ok</div>",
                    layout_name="default",
                    layout_label="Default",
                    description="desc",
                    source="rule",
                    block_count=3,
                    inserted_illustration_count=0,
                    render_anchor_failures=[],
                ),
                save_html=lambda html, run_id: f"/tmp/{run_id}.html",
            )
        )
        node = build_render_article_node(support)
        state = {
            "run": SimpleNamespace(id="run-omit"),
            "article_draft": SimpleNamespace(article_markdown="## Section\n\nBody"),
            "title_plan_state": SimpleNamespace(article_title="Title"),
            "visual_assets_state": SimpleNamespace(body_assets=[]),
            "article_intent": SimpleNamespace(pool="news", subtype="breaking_news", audience="reader"),
            "visual_diagnostics": {
                "planned_item_count": 0,
                "qualified_body_asset_count": 0,
                "visual_fit_failures": [],
                "omitted_by_policy": True,
            },
            "node_audits": {},
        }

        output = node(state)
        self.assertEqual(output["article_render"]["visual_body_result"], "omitted_by_decision")
        self.assertTrue(output["article_render"]["visual_body_warning"])

    def test_render_article_sets_anchor_failed_when_assets_exist_but_none_inserted(self) -> None:
        support = SimpleNamespace(
            article_renderer=SimpleNamespace(
                render=lambda *args, **kwargs: SimpleNamespace(
                    html="<div>ok</div>",
                    layout_name="default",
                    layout_label="Default",
                    description="desc",
                    source="rule",
                    block_count=3,
                    inserted_illustration_count=0,
                    render_anchor_failures=[{"placement_key": "section_1", "reason": "anchor_miss"}],
                ),
                save_html=lambda html, run_id: f"/tmp/{run_id}.html",
            )
        )
        node = build_render_article_node(support)
        state = {
            "run": SimpleNamespace(id="run-anchor"),
            "article_draft": SimpleNamespace(article_markdown="## Section\n\nBody"),
            "title_plan_state": SimpleNamespace(article_title="Title"),
            "visual_assets_state": SimpleNamespace(body_assets=[{"placement_key": "section_1"}]),
            "article_intent": SimpleNamespace(pool="deep_dive", subtype="technical_walkthrough", audience="reader"),
            "visual_diagnostics": {
                "planned_item_count": 1,
                "qualified_body_asset_count": 1,
                "visual_fit_failures": [],
                "omitted_by_policy": False,
            },
            "node_audits": {},
        }

        output = node(state)
        self.assertEqual(output["article_render"]["visual_body_result"], "anchor_failed")
        self.assertEqual(output["article_render"]["render_anchor_failures"][0]["reason"], "anchor_miss")

    def test_render_article_keeps_inserted_result_but_warns_on_partial_failures(self) -> None:
        support = SimpleNamespace(
            article_renderer=SimpleNamespace(
                render=lambda *args, **kwargs: SimpleNamespace(
                    html="<div>ok</div>",
                    layout_name="default",
                    layout_label="Default",
                    description="desc",
                    source="rule",
                    block_count=3,
                    inserted_illustration_count=1,
                    render_anchor_failures=[{"placement_key": "section_2", "reason": "anchor_miss"}],
                ),
                save_html=lambda html, run_id: f"/tmp/{run_id}.html",
            )
        )
        node = build_render_article_node(support)
        state = {
            "run": SimpleNamespace(id="run-partial"),
            "article_draft": SimpleNamespace(article_markdown="## Section\n\nBody"),
            "title_plan_state": SimpleNamespace(article_title="Title"),
            "visual_assets_state": SimpleNamespace(body_assets=[{"placement_key": "section_1"}]),
            "article_intent": SimpleNamespace(pool="news", subtype="breaking_news", audience="reader"),
            "visual_diagnostics": {
                "planned_item_count": 2,
                "qualified_body_asset_count": 2,
                "visual_fit_failures": [{"placement_key": "section_3", "reason": "no_candidate"}],
                "omitted_by_policy": False,
            },
            "node_audits": {},
        }

        output = node(state)
        self.assertEqual(output["article_render"]["visual_body_result"], "inserted")
        self.assertTrue(output["article_render"]["visual_body_warning"])
        self.assertEqual(len(output["article_render"]["visual_fit_failures"]), 1)
        self.assertEqual(len(output["article_render"]["render_anchor_failures"]), 1)


if __name__ == "__main__":
    unittest.main()
