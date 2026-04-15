import unittest

from app.runtime.persistence import build_graph_snapshot
from app.runtime.state_models import (
    ArticleDraft,
    ArticleIntent,
    ArticlePackage,
    RuntimeTitlePlan,
    SectionPlan,
    SectionSpec,
    VisualAssetSet,
    VisualBlueprint,
)


class RuntimePersistenceTests(unittest.TestCase):
    def test_build_graph_snapshot_is_runtime_only(self) -> None:
        package = ArticlePackage(
            intent=ArticleIntent(
                pool="github",
                subtype="code_explainer",
                subtype_label="Code Explainer",
                core_angle="Explain the implementation chain",
                audience="ai_builder",
            ),
            fact_pack={"primary_pool": "github", "subtype": "code_explainer"},
            fact_compress={"one_sentence_summary": "summary"},
            section_plan=SectionPlan(
                pool="github",
                strategy_label="GitHub",
                sections=[
                    SectionSpec(
                        role="how_it_works",
                        goal="Explain the execution chain",
                        evidence_refs=["app/runtime.py"],
                        heading_hint="How it works",
                    )
                ],
            ),
            article_draft=ArticleDraft(article_markdown="# Title\n\nBody", h1_title="Title"),
            title_plan=RuntimeTitlePlan(article_title="Title", wechat_title="Title"),
            visual_blueprint=VisualBlueprint(cover_family="structure"),
            visual_assets=VisualAssetSet(),
            article_layout={"name": "default"},
            article_render={"html_path": "/tmp/article.html"},
            article_html="<h1>Title</h1>",
            quality={"score": 91.0, "status": "passed"},
            draft_status="saved",
            step_audits={"CLASSIFY": {"summary": {"pool": "github"}}},
        )

        snapshot = build_graph_snapshot(package, trigger="manual")

        self.assertEqual(snapshot["runtime"]["engine"], "langgraph")
        self.assertEqual(snapshot["runtime"]["pool"], "github")
        self.assertEqual(snapshot["runtime"]["subtype"], "code_explainer")
        self.assertNotIn("content_type", snapshot["runtime"])
        self.assertEqual(snapshot["article_package"]["intent"]["subtype"], "code_explainer")


if __name__ == "__main__":
    unittest.main()
