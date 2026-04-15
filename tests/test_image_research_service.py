import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.image_search_providers.search_backed_provider import SearchBackedImageProvider
from app.services.image_research_service import ImageResearchService
from app.services.news_visual_policy import classify_news_visual_variant


class ImageResearchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = SimpleNamespace(
            get_int=lambda key, default=0: {
                "visual.image_research.max_queries": 2,
                "visual.image_research.max_results_per_query": 2,
                "visual.image_research.max_candidates": 10,
            }.get(key, default),
            get=lambda key, default="": {
                "search.base_url": "https://search.example.com",
                "search.api_key": "token",
                "search.model": "web",
                "search.proxy": "",
                "search.timeout": "30",
            }.get(key, default),
        )
        self.fetch = SimpleNamespace(
            extract_lightweight_image_candidates=lambda url, **kwargs: [
                {
                    "url": f"{url.rstrip('/')}/hero.jpg",
                    "alt": "Hero image",
                    "caption": "Hero caption",
                    "context": "Context from page",
                    "score": 88,
                    "relevance_hits": 2,
                }
            ]
        )
        self.service = ImageResearchService(settings, self.fetch)

    def test_build_candidates_collects_primary_official_context_and_search(self) -> None:
        fake_provider = SimpleNamespace(
            is_available=lambda: True,
            search_images=lambda query, limit=5: [
                SimpleNamespace(
                    source_page="https://context.example.com/post",
                    title=f"result for {query}",
                    snippet="Context snippet",
                    domain="context.example.com",
                    provider="search_backed",
                )
            ]
        )
        with patch.object(self.service, "_build_image_search_provider", return_value=fake_provider):
            result = self.service.build_candidates(
                topic={"title": "AI infra update", "url": "https://news.example.com/post"},
                fact_pack={"primary_pool": "news", "subtype": "industry_news"},
                web_enrich={
                    "official_sources": [{"url": "https://official.example.com/a"}],
                    "context_sources": [{"url": "https://context.example.com/b", "snippet": "extra context"}],
                },
                source_structure={},
            )

        origin_types = {item["origin_type"] for item in result}
        self.assertIn("primary", origin_types)
        self.assertIn("official", origin_types)
        self.assertIn("context", origin_types)
        self.assertIn("search", origin_types)
        self.assertTrue(all(item.get("provenance_score", 0) >= 0 for item in result))
        primary_candidate = next(item for item in result if item["origin_type"] == "primary")
        self.assertEqual(primary_candidate["source_role"], "primary_source")

    def test_build_candidates_marks_search_hits_on_official_hosts_as_object_official(self) -> None:
        fake_provider = SimpleNamespace(
            is_available=lambda: True,
            search_images=lambda query, limit=5: [
                SimpleNamespace(
                    source_page="https://official.example.com/docs",
                    title="Official docs",
                    snippet="Docs landing page",
                    domain="official.example.com",
                    provider="search_backed",
                )
            ]
        )
        with patch.object(self.service, "_build_image_search_provider", return_value=fake_provider):
            result = self.service.build_candidates(
                topic={"title": "Seedance API 上线", "url": "https://news.example.com/post"},
                fact_pack={"primary_pool": "news", "subtype": "industry_news"},
                web_enrich={"official_sources": [{"url": "https://official.example.com/launch"}], "context_sources": []},
                source_structure={},
            )

        search_candidate = next(item for item in result if item["origin_type"] == "search")
        self.assertEqual(search_candidate["source_role"], "object_official")
        self.assertTrue(search_candidate["is_official_host"])

    def test_build_search_queries_uses_product_release_templates_for_api_news(self) -> None:
        queries = self.service._search_queries(
            topic={"title": "火山引擎 Seedance 2.0 API 上线"},
            fact_pack={"primary_pool": "news", "subtype": "industry_news"},
            variant="product_release_news",
            article_variant="standard",
            source_structure={},
        )

        self.assertTrue(any("API" in query for query in queries))
        self.assertTrue(any("官方 发布" in query for query in queries))

    def test_search_backed_provider_maps_page_hits_to_image_hits(self) -> None:
        provider = SearchBackedImageProvider(
            SimpleNamespace(
                is_available=lambda: True,
                search=lambda query, limit=5: [
                    SimpleNamespace(title="Example", url="https://example.com/post", snippet="snippet", domain="example.com")
                ],
            )
        )

        hits = provider.search_images("agent runtime", limit=3)

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source_page, "https://example.com/post")
        self.assertEqual(hits[0].provider, "search_backed")

    def test_classify_news_visual_variant_detects_product_release_news(self) -> None:
        result = classify_news_visual_variant(
            topic={"title": "火山引擎 Seedance 2.0 API 上线", "summary": "官方发布新的 API 与开发者文档"},
            fact_pack={"primary_pool": "news", "section_blueprint": [{"heading": "产品开放", "summary": "API 可调用"}]},
        )

        self.assertEqual(result["variant"], "product_release_news")
        self.assertIn("release_signal", result["matched_features"])
        self.assertIn("product_signal", result["matched_features"])

    def test_classify_news_visual_variant_blocks_financing_news_with_product_terms(self) -> None:
        result = classify_news_visual_variant(
            topic={"title": "某公司完成新一轮融资，继续加码 AI 平台能力", "summary": "投资方看好其 API 平台与模型服务"},
            fact_pack={"primary_pool": "news", "section_blueprint": [{"heading": "融资进展", "summary": "投资与估值提升"}]},
        )

        self.assertEqual(result["variant"], "standard_news")
        self.assertTrue(result["blocked_by"])


    def test_build_search_queries_for_project_explainer_include_repo_and_docs(self) -> None:
        service = ImageResearchService(
            SimpleNamespace(
                get_int=lambda key, default=0: {
                    "visual.image_research.max_queries": 5,
                    "visual.image_research.max_results_per_query": 2,
                    "visual.image_research.max_candidates": 10,
                }.get(key, default),
                get=lambda key, default="": default,
            ),
            self.fetch,
        )

        queries = service._search_queries(
            topic={"title": "Context Engine deep dive"},
            fact_pack={"primary_pool": "deep_dive", "project_subject": "Context Engine"},
            variant="standard",
            article_variant="project_explainer",
            source_structure={"github_repo_context": {"repo_slug": "example/context-engine"}},
        )

        self.assertTrue(any("github readme" in query.lower() for query in queries))
        self.assertTrue(any("docs" in query.lower() for query in queries))

    def test_build_candidates_tags_repo_docs_visuals_for_project_explainer(self) -> None:
        fake_provider = SimpleNamespace(
            is_available=lambda: True,
            search_images=lambda query, limit=5: [
                SimpleNamespace(
                    source_page="https://github.com/example/context-engine#readme",
                    title="GitHub README",
                    snippet="architecture diagram",
                    domain="github.com",
                    provider="search_backed",
                )
            ]
        )
        with patch.object(self.service, "_build_image_search_provider", return_value=fake_provider):
            result = self.service.build_candidates(
                topic={"title": "Context Engine deep dive", "url": "https://tds.example.com/post"},
                fact_pack={"primary_pool": "deep_dive", "article_variant": "project_explainer", "project_subject": "Context Engine"},
                web_enrich={},
                source_structure={"github_repo_context": {"repo_slug": "example/context-engine"}},
            )

        repo_candidate = next(item for item in result if "github.com/example/context-engine" in item["source_page"])
        self.assertEqual(repo_candidate["source_role"], "repo_readme_or_docs_visual")

    def test_build_candidates_seeds_repo_pages_directly_when_repo_url_is_known(self) -> None:
        with patch.object(self.service, "_build_image_search_provider", return_value=SimpleNamespace(is_available=lambda: False)):
            result = self.service.build_candidates(
                topic={"title": "Context Engine deep dive", "url": "https://tds.example.com/post"},
                fact_pack={
                    "primary_pool": "deep_dive",
                    "article_variant": "project_explainer",
                    "project_subject": "context-engine",
                    "github_repo_url": "https://github.com/example/context-engine",
                },
                web_enrich={},
                source_structure={},
            )

        repo_candidate = next(item for item in result if item["source_page"].startswith("https://github.com/example/context-engine"))
        self.assertEqual(repo_candidate["source_role"], "repo_readme_or_docs_visual")


if __name__ == "__main__":
    unittest.main()
