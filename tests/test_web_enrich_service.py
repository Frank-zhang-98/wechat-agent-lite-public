import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.fetch_service import FetchService
from app.services.search_providers.base import SearchHit
from app.services.settings_service import SettingsService
from app.services.web_enrich_service import WebEnrichService


class WebEnrichServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()
        self.settings = SettingsService(self.session)
        self.settings.ensure_defaults()
        self.fetch = FetchService()
        self.service = WebEnrichService(self.settings, self.fetch)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_build_search_plan_skips_when_evidence_is_strong(self) -> None:
        plan = self.service.build_search_plan(
            run_id="run-1",
            topic={"title": "Strong article"},
            source_pack={},
            source_structure={},
            subtype="technical_walkthrough",
            evidence_score=80.0,
            llm=Mock(),
            primary_pool="deep_dive",
        )
        self.assertFalse(plan["should_search"])
        self.assertIn("above_threshold", plan["reason"])

    def test_build_search_plan_forces_news_image_backfill_when_primary_images_are_missing(self) -> None:
        plan = self.service.build_search_plan(
            run_id="run-news-images",
            topic={
                "title": "Claude Code subscription pricing changes",
                "url": "https://openai.com/blog/claude-code-pricing",
                "primary_pool": "news",
            },
            source_pack={"primary": {"images": []}},
            source_structure={},
            subtype="industry_news",
            evidence_score=95.0,
            llm=Mock(),
            primary_pool="news",
        )
        self.assertTrue(plan["should_search"])
        self.assertEqual(plan["reason"], "news_image_backfill_low_primary_images")

    def test_build_search_plan_forces_repo_background_search_for_github_topics(self) -> None:
        plan = self.service.build_search_plan(
            run_id="run-github",
            topic={
                "title": "Firecrawl",
                "url": "https://github.com/firecrawl/firecrawl",
                "primary_pool": "github",
            },
            source_pack={"primary": {"content_text": "Quick Start for the Firecrawl CLI and SDK."}},
            source_structure={
                "lead": "Quick Start and deployment docs are available for the CLI and SDK.",
                "sections": [{"heading": "Quick Start", "summary": "Install and run commands."}],
            },
            subtype="code_explainer",
            evidence_score=92.0,
            llm=Mock(),
            primary_pool="github",
        )
        self.assertTrue(plan["should_search"])
        self.assertTrue(plan["reason"].startswith("github_repo_background_required:"))

    def test_fetch_search_results_filters_official_domains(self) -> None:
        fake_provider = Mock()
        fake_provider.is_available.return_value = True
        fake_provider.search.return_value = [
            SearchHit(title="Official Doc", url="https://docs.example.com/plan", snippet="official", domain="docs.example.com"),
            SearchHit(title="Random Blog", url="https://blog.other.com/post", snippet="context", domain="blog.other.com"),
        ]
        with patch.object(self.service, "_build_provider", return_value=fake_provider):
            with patch.object(
                self.fetch,
                "extract_article_content",
                side_effect=lambda url, max_chars=2500: {
                    "status": "ok",
                    "reason": "",
                    "content_text": f"content for {url}",
                    "images": [],
                },
            ):
                result = self.service.fetch_search_results(
                    plan={
                        "should_search": True,
                        "official_domains": ["example.com"],
                        "queries": [
                            {
                                "q": "official docs",
                                "intent": "verify",
                                "source_type": "official",
                                "must_include": [],
                                "must_exclude": [],
                            }
                        ],
                    }
                )
        self.assertEqual(len(result["official_sources"]), 1)
        self.assertEqual(result["official_sources"][0]["domain"], "docs.example.com")


if __name__ == "__main__":
    unittest.main()
