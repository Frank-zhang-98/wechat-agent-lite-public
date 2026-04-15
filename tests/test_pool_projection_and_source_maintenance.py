import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Run
from app.runtime.projections import STEP_LABELS, build_run_projection
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
from app.services.source_maintenance_service import SourceMaintenanceService


class _FakeSettings:
    def get_bool(self, key, default=False):
        return default

    def get_int(self, key, default=0):
        return default

    def get_float(self, key, default=0.0):
        return default


class _FakeFetch:
    def __init__(self, cfg):
        self._cfg = cfg

    def load_sources(self):
        return self._cfg

    def save_sources(self, cfg):
        self._cfg = cfg


class PoolProjectionAndSourceMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_runtime_projection_exposes_pool_and_subtype_only(self) -> None:
        run = Run(id="run-projection", run_type="main", trigger_source="manual", status="success")
        package = ArticlePackage(
            intent=ArticleIntent(
                pool="github",
                subtype="code_explainer",
                subtype_label="Code Explainer",
                core_angle="Explain the implementation path",
                audience="ai_builder",
            ),
            fact_pack={},
            fact_compress={"one_sentence_summary": "A GitHub runtime worth explaining."},
            section_plan=SectionPlan(
                pool="github",
                strategy_label="GitHub",
                sections=[SectionSpec(role="how_it_works", goal="Explain architecture", heading_hint="How it works")],
            ),
            article_draft=ArticleDraft(article_markdown="# Demo\n\nHello", h1_title="Demo"),
            title_plan=RuntimeTitlePlan(article_title="Demo title", wechat_title="Demo title"),
            visual_blueprint=VisualBlueprint(),
            visual_assets=VisualAssetSet(body_assets=[{"type": "source_news", "path": "a.png"}]),
            quality={"score": 88},
            draft_status="saved",
        )
        summary = {
            "selected_topic": {"title": "Repo winner", "summary": "Winner summary", "primary_pool_label": "GitHub"},
            "trigger_request": {"target_pool_label": "GitHub"},
            "pool_candidates": {
                "github": {
                    "pool_label": "GitHub",
                    "status": "selected",
                    "top_k_requested": 8,
                    "top_k_actual": 8,
                    "winner": {"title": "Repo winner", "summary": "Winner summary"},
                },
            },
            "pool_winners": {"github": {"title": "Repo winner", "primary_pool": "github"}},
            "final_pool_selection": {"selected_pool": "github", "selected_pool_label": "GitHub", "winner_count": 1},
            "runtime_graph": {"runtime": {"graph_status": "completed"}, "article_package": package.as_dict()},
        }

        projection = build_run_projection(
            run=run,
            summary=summary,
            steps=[],
            article_html="<html></html>",
            cover_url="",
        )

        self.assertEqual(projection["selected_pool"], "github")
        self.assertEqual(projection["subtype"], "code_explainer")
        self.assertEqual(projection["subtype_label"], "Code Explainer")
        self.assertNotIn("content_type", projection)
        self.assertEqual(projection["final_pool_selection"]["selected_pool"], "github")

    def test_topic_section_strips_html_and_truncates_summary(self) -> None:
        run = Run(id="run-projection-summary", run_type="main", trigger_source="manual", status="success")
        html_summary = (
            "<p>First paragraph with <strong>HTML</strong> tags.</p>"
            "<p class=\"heading-3\">Second paragraph with a very long explanation that should be compacted "
            "for the business summary card instead of rendering raw markup in the UI. </p>"
        ) * 8
        package = ArticlePackage(
            intent=ArticleIntent(
                pool="news",
                subtype="breaking_news",
                subtype_label="Breaking News",
                core_angle="Angle",
                audience="ai_reader",
            ),
            fact_pack={},
            fact_compress={"one_sentence_summary": "summary"},
            section_plan=SectionPlan(pool="news", strategy_label="News", sections=[]),
            article_draft=ArticleDraft(article_markdown="# Demo", h1_title="Demo"),
            title_plan=RuntimeTitlePlan(article_title="Demo title", wechat_title="Demo title"),
            visual_blueprint=VisualBlueprint(),
            visual_assets=VisualAssetSet(),
        )
        summary = {
            "selected_topic": {"title": "Winner", "summary": html_summary, "primary_pool_label": "AI 新闻池"},
            "runtime_graph": {"runtime": {"graph_status": "completed"}, "article_package": package.as_dict()},
        }

        projection = build_run_projection(
            run=run,
            summary=summary,
            steps=[],
            article_html="",
            cover_url="",
        )

        topic_section = projection["summary_sections"][0]
        self.assertEqual(topic_section["title"], "Current Topic")
        subtitle = topic_section["entries"][0]["subtitle"]
        self.assertNotIn("<p>", subtitle)
        self.assertNotIn("class=", subtitle)
        self.assertIn("First paragraph", subtitle)
        self.assertTrue(subtitle.endswith("…"))

    def test_runtime_projection_formats_core_angle_list_like_string(self) -> None:
        run = Run(id="run-projection-angle", run_type="main", trigger_source="manual", status="success")
        package = ArticlePackage(
            intent=ArticleIntent(
                pool="news",
                subtype="breaking_news",
                subtype_label="Breaking News",
                core_angle="['第一点观察', '第二点观察', '第三点观察']",
                audience="ai_reader",
            ),
            fact_pack={},
            fact_compress={"one_sentence_summary": "summary"},
            section_plan=SectionPlan(pool="news", strategy_label="News", sections=[]),
            article_draft=ArticleDraft(article_markdown="# Demo", h1_title="Demo"),
            title_plan=RuntimeTitlePlan(article_title="Demo title", wechat_title="Demo title"),
            visual_blueprint=VisualBlueprint(),
            visual_assets=VisualAssetSet(),
        )
        summary = {
            "selected_topic": {"title": "Winner", "summary": "summary"},
            "runtime_graph": {"runtime": {"graph_status": "completed"}, "article_package": package.as_dict()},
        }

        projection = build_run_projection(
            run=run,
            summary=summary,
            steps=[],
            article_html="",
            cover_url="",
        )

        intent_section = projection["summary_sections"][1]
        core_angle = next(item["value"] for item in intent_section["keyvals"] if item["label"] == "Core Angle")
        self.assertEqual(core_angle, "第一点观察；第二点观察；第三点观察")

    def test_source_maintenance_filters_sources_to_target_pool(self) -> None:
        cfg = {
            "ai_companies": [
                {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "enabled": True, "pools": ["news"]},
                {"name": "Deep Dive Blog", "url": "https://example.com/feed.xml", "enabled": True, "pools": ["deep_dive"]},
            ],
            "tech_media": [],
            "tutorial_communities": [],
        }
        service = SourceMaintenanceService(
            session=self.session,
            settings=_FakeSettings(),
            fetch=_FakeFetch(cfg),
            llm=SimpleNamespace(),
            scrapling=None,
        )

        def fake_inspect(job):
            return {
                "index": int(job.get("index", 0)),
                "source_key": str(job.get("source_key", "")),
                "name": str(job.get("name", "")),
                "category": str(job.get("category", "")),
                "enabled": True,
                "mode": "rss",
                "weight": 0.7,
                "source_ref": dict(job.get("source_ref") or {}),
                "probe": {"ok": True, "mode": "rss", "status_code": 200, "reason": "", "source_type": "feed_source"},
                "candidates": [],
                "html_fallback": {},
            }

        with patch.object(service, "_inspect_source_network", side_effect=fake_inspect):
            with patch.object(service, "_select_llm_review_items", return_value=[]):
                with patch.object(
                    service,
                    "_resolve_action",
                    side_effect=lambda item, llm_decision=None: {
                        "source_key": item["source_key"],
                        "name": item["name"],
                        "final_action": "keep",
                        "applied_action": "",
                        "applied": False,
                        "reason": "",
                        "candidate_url": "",
                        "decision_source": "heuristic",
                        "confidence": 1.0,
                    },
                ):
                    result = service.run(run_id="run-maint", target_pool="news")

        self.assertEqual(result["checked_sources"], 1)
        self.assertEqual(result["healthy_sources"], 1)
        self.assertEqual([item["name"] for item in result["actions"]], ["OpenAI Blog"])

    def test_runtime_step_labels_drop_legacy_visual_steps(self) -> None:
        for step_name in (
            "VISUAL_STRATEGY",
            "BODY_ILLUSTRATION_GEN",
            "ARTICLE_RENDER",
            "COVER_5D",
            "COVER_GEN",
            "COVER_CHECK",
            "WECHAT_DRAFT",
        ):
            self.assertNotIn(step_name, STEP_LABELS)


if __name__ == "__main__":
    unittest.main()
