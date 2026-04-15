import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Run, RunStatus
from app.runtime.facade import RuntimeFacade


class TopicSelectionFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()
        self.orch = RuntimeFacade(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _add_historical_run(self, *, title: str, source: str, url: str, days_ago: float) -> None:
        started_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
        run = Run(
            run_type="main",
            status=RunStatus.success.value,
            trigger_source="test",
            started_at=started_at,
            finished_at=started_at + timedelta(minutes=3),
            summary_json=json.dumps(
                {
                    "selected_topic": {
                        "title": title,
                        "source": source,
                        "url": url,
                    }
                },
                ensure_ascii=False,
            ),
        )
        self.session.add(run)
        self.session.flush()

    def test_should_reject_workshop_registration_topic(self) -> None:
        item = {
            "title": "April 8 - Getting Started with Computer Vision Workflows Workshop",
            "summary": "Join us on April 8 at 10 AM Pacific for a free, 60-minute, virtual hands-on workshop. Register for the Zoom.",
            "url": "https://dev.to/voxel51/april-8-getting-started-with-computer-vision-workflows-workshop-1mf8",
        }

        self.assertTrue(RuntimeFacade._should_reject_topic(item))
        self.assertGreaterEqual(RuntimeFacade._topic_editorial_penalty_score(item), 85.0)

    def test_should_reject_direct_sales_topic(self) -> None:
        item = {
            "title": "Cycle 248: Launching the P2P API Monetization Stack ($19) - Direct Honor System Sales",
            "summary": "PayPal and IBAN included for $19 direct honor system sales. A monetization stack for AI agents and solo developers.",
            "url": "https://dev.to/universe7creator/cycle-248-launching-the-p2p-api-monetization-stack-19-direct-honor-system-sales-4agh",
        }

        self.assertTrue(RuntimeFacade._should_reject_topic(item))
        self.assertGreaterEqual(RuntimeFacade._topic_editorial_penalty_score(item), 85.0)

    def test_rule_score_filters_workshop_and_sales_topics(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "April 8 - Getting Started with Computer Vision Workflows Workshop",
                    "summary": "Join us for a free virtual workshop. Register for the Zoom.",
                    "url": "https://example.com/workshop",
                    "published": now,
                    "source": "Dev.to AI",
                    "source_weight": 0.8,
                },
                {
                    "title": "Cycle 248: Launching the P2P API Monetization Stack ($19) - Direct Honor System Sales",
                    "summary": "PayPal and IBAN included for $19 direct honor system sales.",
                    "url": "https://example.com/direct-sales",
                    "published": now,
                    "source": "Dev.to AI",
                    "source_weight": 0.8,
                },
                {
                    "title": "How we built a multi-agent evaluation pipeline",
                    "summary": "An engineering walkthrough covering architecture, retries, evaluation, and production guardrails.",
                    "url": "https://example.com/agent-pipeline",
                    "published": now,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                },
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-1"), ctx)

        titles = [item["title"] for item in ctx["top_n"]]
        self.assertEqual(titles, ["How we built a multi-agent evaluation pipeline"])

    def test_rule_score_skips_url_like_titles_even_if_published_is_recent(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "https://example.com/blog/2024-ai-first",
                    "summary": "",
                    "url": "https://example.com/blog/2024-ai-first",
                    "published": now,
                    "source": "HTML Source",
                    "source_weight": 0.9,
                },
                {
                    "title": "Real Engineering Deep Dive",
                    "summary": "A real architecture walkthrough.",
                    "url": "https://example.com/deep-dive",
                    "published": now,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                },
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-url-like-title"), ctx)

        titles = [item["title"] for item in ctx["top_n"]]
        self.assertEqual(titles, ["Real Engineering Deep Dive"])

    def test_rule_score_uses_soft_topic_gate_warning_instead_of_failing(self) -> None:
        self.orch.settings.set("quality.min_topic_score", "90")
        self.session.flush()
        now = datetime.now(timezone.utc).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "Useful but ordinary post",
                    "summary": "A solid engineering post that should still continue to rerank.",
                    "url": "https://example.com/ordinary",
                    "published": now,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                }
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-soft-gate"), ctx)

        self.assertEqual(len(ctx["top_n"]), 1)
        self.assertIn("No topic passed minimum topic score 90.0", ctx.get("topic_gate_warning", ""))

    def test_rule_score_applies_source_diversity_cap(self) -> None:
        self.orch.settings.set("selection.top_n_per_source_family", "1")
        self.session.flush()
        now = datetime.now(timezone.utc).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "Dev Post A",
                    "summary": "Architecture walkthrough for agents.",
                    "url": "https://dev.to/post-a",
                    "published": now,
                    "source": "Dev.to AI",
                    "source_weight": 0.8,
                },
                {
                    "title": "Dev Post B",
                    "summary": "Workflow and API design.",
                    "url": "https://dev.to/post-b",
                    "published": now,
                    "source": "Dev.to Machine Learning",
                    "source_weight": 0.8,
                },
                {
                    "title": "OpenAI Deep Dive",
                    "summary": "Model architecture and production details.",
                    "url": "https://openai.com/blog/deep-dive",
                    "published": now,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                },
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-diversity"), ctx)

        families = [self.orch._topic_source_family(item) for item in ctx["top_n"]]
        self.assertEqual(len(families), len(set(families)))

    def test_rule_score_builds_three_topic_pools(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "OpenAI launches a new agent runtime",
                    "summary": "Official release notes covering runtime updates, API changes, and launch details.",
                    "url": "https://example.com/news-runtime",
                    "published": now,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_tier": "core",
                    "source_pools": ["news"],
                },
                {
                    "title": "Agent Armor",
                    "summary": "Open-source MCP runtime with policy engine, sandboxing, audit logs, and command controls.",
                    "url": "https://github.com/example/agent-armor",
                    "published": now,
                    "source": "GitHub",
                    "source_weight": 0.95,
                    "source_category": "github",
                    "source_tier": "core",
                    "source_pools": ["github"],
                    "type": "github",
                    "stars": 4200,
                },
                {
                    "title": "How we built a multimodal evaluation pipeline",
                    "summary": "A technical walkthrough covering architecture, inference stack, caching, and benchmarking.",
                    "url": "https://example.com/deep-dive",
                    "published": now,
                    "source": "Towards Data Science",
                    "source_weight": 0.85,
                    "source_category": "tutorial_communities",
                    "source_tier": "core",
                    "source_pools": ["deep_dive"],
                },
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-three-pools"), ctx)

        topic_pools = ctx.get("topic_pools") or {}
        self.assertEqual(set(topic_pools.keys()), set(self.orch.TOPIC_POOLS))
        self.assertEqual(topic_pools["news"]["winner"]["primary_pool"], "news")
        self.assertEqual(topic_pools["github"]["winner"]["primary_pool"], "github")
        self.assertEqual(topic_pools["deep_dive"]["winner"]["primary_pool"], "deep_dive")
        self.assertTrue(all(item.get("primary_pool_label") for item in ctx["top_n"]))

    def test_rule_score_hard_rejects_stale_news_even_with_evergreen_signals(self) -> None:
        stale_time = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        fresh_time = datetime.now(timezone.utc).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "Weekly AI news roundup with architecture notes",
                    "summary": "News recap covering architecture, implementation patterns, and API changes.",
                    "url": "https://example.com/news-roundup",
                    "published": stale_time,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_tier": "core",
                    "source_pools": ["news"],
                },
                {
                    "title": "Fresh product release",
                    "summary": "A new model release with concrete downstream impact.",
                    "url": "https://example.com/fresh-release",
                    "published": fresh_time,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_tier": "core",
                    "source_pools": ["news"],
                },
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-stale-news-hard-reject"), ctx)

        titles = [item["title"] for item in ctx["top_n"]]
        self.assertEqual(titles, ["Fresh product release"])

    def test_rule_score_limits_unknown_time_news_and_keeps_fresh_news_first(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "Official model launch update",
                    "summary": "Breaking release details from the official blog.",
                    "url": "https://example.com/official-launch",
                    "published": now,
                    "published_status": "fresh",
                    "published_confidence": "high",
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_tier": "core",
                    "source_pools": ["news"],
                },
                {
                    "title": "Product update without timestamp",
                    "summary": "Breaking launch notes for a new model tier, API workflow changes, and agent rollout details.",
                    "url": "https://example.com/no-time-one",
                    "published": "",
                    "published_status": "unknown",
                    "published_confidence": "low",
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_tier": "core",
                    "source_pools": ["news"],
                },
                {
                    "title": "Another release note without timestamp",
                    "summary": "Breaking update on pricing and launch packaging with agent runtime and API details.",
                    "url": "https://example.com/no-time-two",
                    "published": "",
                    "published_status": "unknown",
                    "published_confidence": "low",
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_tier": "core",
                    "source_pools": ["news"],
                },
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-unknown-news-limit"), ctx)

        news_candidates = (ctx.get("topic_pools") or {}).get("news", {}).get("candidates") or []
        self.assertEqual(news_candidates[0]["title"], "Official model launch update")
        self.assertEqual(sum(1 for item in news_candidates if item.get("published_status") == "unknown"), 1)

    def test_rule_score_filters_top_n_to_target_pool(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ctx = {
            "trigger_request": {
                "target_pool": "github",
                "target_pool_label": "GitHub ???",
            },
            "deduped_items": [
                {
                    "title": "OpenAI launches a new agent runtime",
                    "summary": "Official release notes covering runtime updates, API changes, and launch details.",
                    "url": "https://example.com/news-runtime",
                    "published": now,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_tier": "core",
                    "source_pools": ["news"],
                },
                {
                    "title": "Agent Armor",
                    "summary": "Open-source MCP runtime with policy engine, sandboxing, audit logs, and command controls.",
                    "url": "https://github.com/example/agent-armor",
                    "published": now,
                    "source": "GitHub Trending",
                    "source_weight": 0.95,
                    "source_category": "github",
                    "source_tier": "core",
                    "source_pools": ["github"],
                    "type": "github",
                    "stars": 4200,
                },
                {
                    "title": "How we built a multimodal evaluation pipeline",
                    "summary": "A technical walkthrough covering architecture, inference stack, caching, and benchmarking.",
                    "url": "https://example.com/deep-dive",
                    "published": now,
                    "source": "Towards Data Science",
                    "source_weight": 0.85,
                    "source_category": "tutorial_communities",
                    "source_tier": "core",
                    "source_pools": ["deep_dive"],
                },
            ],
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-target-pool-topn"), ctx)

        self.assertEqual([item["title"] for item in ctx["top_n"]], ["Agent Armor"])
        self.assertTrue(all(item.get("primary_pool") == "github" for item in ctx["top_n"]))

    def test_rerank_v2_filters_candidates_to_target_pool(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ctx = {
            "trigger_request": {
                "target_pool": "github",
                "target_pool_label": "GitHub ???",
            },
            "top_n": [
                {
                    "title": "MiniMax Speech 2.5 launch",
                    "summary": "A consequential speech model release.",
                    "url": "https://example.com/news",
                    "published": now,
                    "source": "MiniMax News",
                    "primary_pool": "news",
                    "primary_pool_label": "AI 鏂伴椈姹?,
                    "rule_score": 84.0,
                    "pool_score": 86.0,
                    "freshness_score": 91.0,
                    "depth_score": 63.0,
                    "value_score": 76.0,
                    "novelty_score": 80.0,
                    "recommendation_score": 58.0,
                    "stack_analysis_score": 52.0,
                },
                {
                    "title": "Agent Armor",
                    "summary": "A GitHub project with strong recommendation and technical-stack analysis value.",
                    "url": "https://github.com/example/agent-armor",
                    "published": now,
                    "source": "GitHub Trending",
                    "primary_pool": "github",
                    "primary_pool_label": "GitHub 椤圭洰姹?,
                    "rule_score": 82.0,
                    "pool_score": 90.0,
                    "freshness_score": 87.0,
                    "depth_score": 79.0,
                    "value_score": 86.0,
                    "novelty_score": 78.0,
                    "recommendation_score": 91.0,
                    "stack_analysis_score": 87.0,
                },
                {
                    "title": "everything-claude-code",
                    "summary": "A GitHub repository with code, docs, and architecture signals.",
                    "url": "https://github.com/example/everything-claude-code",
                    "published": now,
                    "source": "GitHub Search",
                    "primary_pool": "github",
                    "primary_pool_label": "GitHub 椤圭洰姹?,
                    "rule_score": 80.0,
                    "pool_score": 88.0,
                    "freshness_score": 84.0,
                    "depth_score": 81.0,
                    "value_score": 82.0,
                    "novelty_score": 74.0,
                    "recommendation_score": 88.0,
                    "stack_analysis_score": 85.0,
                },
                {
                    "title": "How we built a multimodal evaluation pipeline",
                    "summary": "A technical deep dive.",
                    "url": "https://example.com/deep-dive",
                    "published": now,
                    "source": "Towards Data Science",
                    "primary_pool": "deep_dive",
                    "primary_pool_label": "鎶€鏈繁鎸栨睜",
                    "rule_score": 81.0,
                    "pool_score": 83.0,
                    "freshness_score": 74.0,
                    "depth_score": 88.0,
                    "value_score": 79.0,
                    "novelty_score": 72.0,
                    "recommendation_score": 62.0,
                    "stack_analysis_score": 89.0,
                },
            ],
            "topic_pools": {
                "news": {"candidates": []},
                "github": {
                    "candidates": [
                        {
                            "title": "Agent Armor",
                            "summary": "A GitHub project with strong recommendation and technical-stack analysis value.",
                            "url": "https://github.com/example/agent-armor",
                            "published": now,
                            "source": "GitHub Trending",
                            "primary_pool": "github",
                            "primary_pool_label": "GitHub 椤圭洰姹?,
                            "rule_score": 82.0,
                            "pool_score": 90.0,
                            "freshness_score": 87.0,
                            "depth_score": 79.0,
                            "value_score": 86.0,
                            "novelty_score": 78.0,
                            "recommendation_score": 91.0,
                            "stack_analysis_score": 87.0,
                        },
                        {
                            "title": "everything-claude-code",
                            "summary": "A GitHub repository with code, docs, and architecture signals.",
                            "url": "https://github.com/example/everything-claude-code",
                            "published": now,
                            "source": "GitHub Search",
                            "primary_pool": "github",
                            "primary_pool_label": "GitHub 椤圭洰姹?,
                            "rule_score": 80.0,
                            "pool_score": 88.0,
                            "freshness_score": 84.0,
                            "depth_score": 81.0,
                            "value_score": 82.0,
                            "novelty_score": 74.0,
                            "recommendation_score": 88.0,
                            "stack_analysis_score": 85.0,
                        },
                    ],
                    "winner": {},
                },
                "deep_dive": {"candidates": []},
            },
        }

        with patch.object(self.orch.fetch, "extract_rerank_excerpt_light") as extract_mock:
            with patch.object(
                self.orch.llm,
                "rerank_documents",
                return_value=[
                    {"index": 0, "relevance_score": 0.91, "reason": "Best GitHub candidate"},
                    {"index": 1, "relevance_score": 0.86, "reason": "Strong second GitHub candidate"},
                ],
            ) as rerank_mock:
                self.orch._step_rerank_v2(SimpleNamespace(id="run-target-pool-rerank"), ctx)

        extract_mock.assert_not_called()
        self.assertEqual(rerank_mock.call_args.kwargs["top_n"], 2)
        self.assertIn("only from the", rerank_mock.call_args.kwargs["query"])
        self.assertTrue(all(item.get("primary_pool") == "github" for item in ctx["top_k"]))
        self.assertEqual(len(ctx["pool_winners"]), 1)
        self.assertEqual(ctx["pool_winners"][0]["primary_pool"], "github")
        self.assertTrue(all(item.get("rerank_excerpt_mode") == "repo_signal" for item in ctx["top_k"]))

    def test_rerank_v2_uses_light_excerpt_only_for_boundary_non_github_candidates(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.orch.settings.set("selection.rerank_enrich_m", "2")
        self.orch.settings.set("selection.rerank_boundary_gap_score", "5")
        ctx = {
            "top_n": [
                {
                    "title": "Major AI release",
                    "summary": "An official product launch with clear changes.",
                    "url": "https://example.com/news-a",
                    "published": now,
                    "source": "OpenAI Blog",
                    "primary_pool": "news",
                    "primary_pool_label": "AI 鏂伴椈姹?,
                    "rule_score": 90.0,
                    "pool_score": 92.0,
                    "freshness_score": 96.0,
                    "depth_score": 60.0,
                    "value_score": 82.0,
                    "novelty_score": 84.0,
                    "recommendation_score": 58.0,
                    "stack_analysis_score": 52.0,
                },
                {
                    "title": "Agent Armor",
                    "summary": "A GitHub project with strong recommendation value.",
                    "url": "https://github.com/example/agent-armor",
                    "published": now,
                    "source": "GitHub Trending",
                    "primary_pool": "github",
                    "primary_pool_label": "GitHub 椤圭洰姹?,
                    "rule_score": 86.0,
                    "pool_score": 88.0,
                    "freshness_score": 84.0,
                    "depth_score": 80.0,
                    "value_score": 86.0,
                    "novelty_score": 76.0,
                    "recommendation_score": 91.0,
                    "stack_analysis_score": 87.0,
                    "type": "github",
                    "stars": 4200,
                    "github_query_groups": ["agents-python"],
                },
                {
                    "title": "Deep evaluation pipeline",
                    "summary": "A dense technical walkthrough.",
                    "url": "https://example.com/deep-dive",
                    "published": now,
                    "source": "Towards Data Science",
                    "primary_pool": "deep_dive",
                    "primary_pool_label": "鎶€鏈繁鎸栨睜",
                    "rule_score": 84.0,
                    "pool_score": 86.0,
                    "freshness_score": 78.0,
                    "depth_score": 90.0,
                    "value_score": 80.0,
                    "novelty_score": 70.0,
                    "recommendation_score": 60.0,
                    "stack_analysis_score": 89.0,
                },
            ]
        }

        with patch.object(
            self.orch.fetch,
            "extract_rerank_excerpt_light",
            side_effect=[
                {"status": "ok", "excerpt": "news excerpt", "fetch_mode": "http_light"},
                {"status": "ok", "excerpt": "deep dive excerpt", "fetch_mode": "http_light"},
            ],
        ) as extract_mock:
            with patch.object(
                self.orch.llm,
                "rerank_documents",
                return_value=[
                    {"index": 0, "relevance_score": 0.93, "reason": "Best overall candidate"},
                    {"index": 1, "relevance_score": 0.88, "reason": "Strong GitHub project"},
                    {"index": 2, "relevance_score": 0.84, "reason": "Solid deep dive"},
                ],
            ):
                self.orch._step_rerank_v2(SimpleNamespace(id="run-mixed-rerank"), ctx)

        self.assertGreaterEqual(extract_mock.call_count, 1)
        self.assertLessEqual(extract_mock.call_count, 2)
        github_item = next(item for item in ctx["top_k"] if item["primary_pool"] == "github")
        self.assertEqual(github_item["rerank_excerpt_mode"], "repo_signal")
        self.assertIn("Repository:", github_item["rerank_excerpt"])

    def test_rule_score_filters_stale_low_value_topic(self) -> None:
        now = datetime.now(timezone.utc)
        stale = (now - timedelta(days=18)).isoformat()
        fresh = now.isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "AI Weekly News Roundup",
                    "summary": "This week in AI: product updates, launch news, and hot takes.",
                    "url": "https://example.com/weekly-roundup",
                    "published": stale,
                    "source": "AI Weekly",
                    "source_weight": 0.8,
                },
                {
                    "title": "How we built a multi-agent evaluation pipeline",
                    "summary": "An engineering walkthrough covering architecture, retries, evaluation, and production guardrails.",
                    "url": "https://example.com/agent-pipeline",
                    "published": fresh,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                },
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-stale-filter"), ctx)

        titles = [item["title"] for item in ctx["top_n"]]
        self.assertIn("How we built a multi-agent evaluation pipeline", titles)
        self.assertNotIn("AI Weekly News Roundup", titles)

    def test_rule_score_keeps_old_evergreen_walkthrough(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "LangGraph architecture deep dive",
                    "summary": "A technical walkthrough covering implementation details, workflow patterns, APIs, and benchmark tradeoffs.",
                    "url": "https://example.com/langgraph-deep-dive",
                    "published": old,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                }
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-old-evergreen"), ctx)

        self.assertEqual(len(ctx["top_n"]), 1)
        self.assertEqual(ctx["top_n"][0]["title"], "LangGraph architecture deep dive")
        self.assertGreater(ctx["top_n"][0].get("evergreen_score", 0), 58.0)

    def test_rule_score_filters_week_old_low_value_roundup_under_stricter_stale_gate(self) -> None:
        stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "This Week in AI roundup",
                    "summary": "Daily and weekly launch announcements, breaking AI news, and hot takes.",
                    "url": "https://example.com/weekly-ai-roundup",
                    "published": stale,
                    "source": "AI Weekly",
                    "source_weight": 0.8,
                }
            ]
        }

        with self.assertRaisesRegex(RuntimeError, "No suitable items left after topic filtering"):
            self.orch._step_rule_score(SimpleNamespace(id="run-week-old-roundup"), ctx)

    def test_timeliness_profile_uses_news_product_and_technical_windows(self) -> None:
        self.assertEqual(
            self.orch._topic_timeliness_profile(
                {"title": "This Week in AI roundup", "summary": "Daily news brief", "url": "https://example.com/news"}
            ),
            "news",
        )
        self.assertEqual(
            self.orch._topic_timeliness_profile(
                {"title": "MiMo V2 release review", "summary": "Hands-on benchmark and product update", "url": "https://example.com/review"}
            ),
            "product",
        )
        self.assertEqual(
            self.orch._topic_timeliness_profile(
                {"title": "LangGraph architecture deep dive", "summary": "Implementation walkthrough and guide", "url": "https://example.com/guide"}
            ),
            "technical",
        )

        self.assertEqual(self.orch._timeliness_thresholds("news"), (72.0, 168.0))
        self.assertEqual(self.orch._timeliness_thresholds("product"), (168.0, 504.0))
        self.assertEqual(self.orch._timeliness_thresholds("technical"), (720.0, 1440.0))

    def test_rule_score_keeps_month_old_technical_tutorial(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        ctx = {
            "deduped_items": [
                {
                    "title": "Agent memory architecture deep dive",
                    "summary": "A technical walkthrough and implementation guide for long-term memory design.",
                    "url": "https://example.com/agent-memory-guide",
                    "published": old,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                }
            ]
        }

        self.orch._step_rule_score(SimpleNamespace(id="run-month-old-technical"), ctx)

        self.assertEqual(len(ctx["top_n"]), 1)
        self.assertEqual(ctx["top_n"][0]["timeliness_profile"], "technical")

    def test_fatigue_penalty_is_gentle_and_recovers_over_time(self) -> None:
        item = {
            "title": "Engineering Deep Dive",
            "summary": "Architecture walkthrough.",
            "url": "https://openai.com/blog/deep-dive",
            "source": "OpenAI Blog",
        }
        self._add_historical_run(
            title="Engineering Deep Dive",
            source="OpenAI Blog",
            url="https://openai.com/blog/deep-dive",
            days_ago=1.0,
        )
        recent_penalty = self.orch._topic_fatigue_penalty_score(item, current_run_id="run-fatigue")

        self.session.query(Run).delete()
        self.session.flush()
        self._add_historical_run(
            title="Engineering Deep Dive",
            source="OpenAI Blog",
            url="https://openai.com/blog/deep-dive",
            days_ago=7.0,
        )
        old_penalty = self.orch._topic_fatigue_penalty_score(item, current_run_id="run-fatigue")

        self.assertGreater(recent_penalty, old_penalty)
        self.assertGreater(recent_penalty, 0.0)
        self.assertLessEqual(recent_penalty, 12.0)
        self.assertLess(old_penalty, recent_penalty * 0.5)

    def test_step_select_prompt_includes_exclusion_rules(self) -> None:
        ctx = {
            "top_k": [
                {
                    "title": "How we built a multi-agent evaluation pipeline",
                    "summary": "An engineering walkthrough with real implementation details.",
                    "url": "",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "OpenAI Blog",
                    "rule_score": 82.0,
                    "pool_score": 84.0,
                    "final_score": 83.0,
                    "primary_pool": "deep_dive",
                    "primary_pool_label": "鎶€鏈繁鎸栨睜",
                    "recommendation_score": 58.0,
                    "stack_analysis_score": 86.0,
                    "freshness_score": 80.0,
                    "depth_score": 85.0,
                    "value_score": 78.0,
                    "novelty_score": 70.0,
                    "editorial_penalty_score": 0.0,
                    "fatigue_penalty_score": 0.0,
                    "rerank_excerpt": "",
                },
                {
                    "title": "Secondary candidate",
                    "summary": "A weaker alternative that keeps LLM arbitration active.",
                    "url": "https://example.com/secondary",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "Dev.to AI",
                    "rule_score": 70.0,
                    "pool_score": 71.0,
                    "final_score": 70.5,
                    "primary_pool": "news",
                    "primary_pool_label": "AI News",
                    "recommendation_score": 45.0,
                    "stack_analysis_score": 40.0,
                    "freshness_score": 78.0,
                    "depth_score": 52.0,
                    "value_score": 50.0,
                    "novelty_score": 60.0,
                    "editorial_penalty_score": 0.0,
                    "fatigue_penalty_score": 0.0,
                    "rerank_excerpt": "",
                }
            ]
        }

        with patch.object(self.orch.llm, "call", return_value=SimpleNamespace(text='{"index": 0, "reason": "ok"}')) as call_mock:
            with patch.object(self.orch, "_probe_topic_evidence", return_value={"score": 72.0, "summary": "sections=6, code=2", "status": "ok"}):
                self.orch._step_select(SimpleNamespace(id="run-select"), ctx)

        prompt = call_mock.call_args.args[3]
        self.assertIn("workshop/webinar/conference", prompt)
        self.assertIn("鍗栦唬鐮?鍗栨ā鏉?寮曞浠樻", prompt)
        self.assertIn("鍘熸枃璇佹嵁鍒?, prompt)
        self.assertIn("鎵€灞炴睜", prompt)
        self.assertIn("鎺ㄨ崘浠峰€煎垎", prompt)

    def test_step_select_fallback_uses_evidence_score(self) -> None:
        ctx = {
            "top_k": [
                {
                    "title": "Shallow Post",
                    "summary": "Looks trendy but has little structure.",
                    "url": "https://example.com/shallow",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "Dev.to AI",
                    "rule_score": 80.0,
                    "pool_score": 81.0,
                    "final_score": 79.0,
                    "freshness_score": 90.0,
                    "depth_score": 60.0,
                    "value_score": 60.0,
                    "novelty_score": 75.0,
                    "editorial_penalty_score": 0.0,
                    "fatigue_penalty_score": 0.0,
                    "rerank_excerpt": "",
                },
                {
                    "title": "Real Engineering Deep Dive",
                    "summary": "A real architecture walkthrough.",
                    "url": "https://example.com/deep",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "OpenAI Blog",
                    "rule_score": 76.0,
                    "pool_score": 78.0,
                    "final_score": 77.0,
                    "freshness_score": 75.0,
                    "depth_score": 88.0,
                    "value_score": 80.0,
                    "novelty_score": 68.0,
                    "editorial_penalty_score": 0.0,
                    "fatigue_penalty_score": 0.0,
                    "rerank_excerpt": "",
                },
            ]
        }

        evidence_side_effect = [
            {"score": 15.0, "summary": "sections=1, code=0", "status": "ok"},
            {"score": 82.0, "summary": "sections=6, code=2", "status": "ok"},
        ]

        with patch.object(self.orch.llm, "call", return_value=SimpleNamespace(text="not-json")):
            with patch.object(self.orch, "_probe_topic_evidence", side_effect=evidence_side_effect):
                self.orch._step_select(SimpleNamespace(id="run-fallback"), ctx)

        self.assertEqual(ctx["selected_topic"]["title"], "Real Engineering Deep Dive")

    def test_step_select_uses_pool_winners_for_arbitration(self) -> None:
        ctx = {
            "top_k": [
                {
                    "title": "Low-value extra topic",
                    "summary": "Should not be part of pool-winner arbitration.",
                    "url": "https://example.com/extra",
                    "source": "Newsletter",
                    "final_score": 99.0,
                    "pool_score": 40.0,
                }
            ],
            "pool_winners": [
                {
                    "title": "Model launch with broad impact",
                    "summary": "An official release with meaningful downstream changes.",
                    "url": "https://example.com/news",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "OpenAI Blog",
                    "primary_pool": "news",
                    "primary_pool_label": "AI 鏂伴椈姹?,
                    "rule_score": 86.0,
                    "pool_score": 88.0,
                    "final_score": 87.0,
                    "recommendation_score": 60.0,
                    "stack_analysis_score": 58.0,
                },
                {
                    "title": "Agent Armor",
                    "summary": "A GitHub project with both recommendation value and technical-stack analysis value.",
                    "url": "https://github.com/example/agent-armor",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "GitHub",
                    "primary_pool": "github",
                    "primary_pool_label": "GitHub 椤圭洰姹?,
                    "rule_score": 82.0,
                    "pool_score": 90.0,
                    "final_score": 88.0,
                    "recommendation_score": 91.0,
                    "stack_analysis_score": 87.0,
                },
                {
                    "title": "Long-context evaluation deep dive",
                    "summary": "A strong technical post with reusable methodology.",
                    "url": "https://example.com/deep",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "Towards Data Science",
                    "primary_pool": "deep_dive",
                    "primary_pool_label": "鎶€鏈繁鎸栨睜",
                    "rule_score": 84.0,
                    "pool_score": 85.0,
                    "final_score": 84.5,
                    "recommendation_score": 62.0,
                    "stack_analysis_score": 89.0,
                },
            ],
        }

        with patch.object(
            self.orch.llm,
            "call",
            return_value=SimpleNamespace(text='{"index": 1, "reason": "GitHub 椤圭洰鍚屾椂鍏峰鎺ㄨ崘浠峰€煎拰鎶€鏈媶瑙ｄ环鍊?}'),
        ):
            with patch.object(
                self.orch,
                "_probe_topic_evidence",
                side_effect=[
                    {"score": 76.0, "summary": "official release", "status": "ok"},
                    {
                        "score": 81.0,
                        "summary": "readme + code",
                        "status": "ok",
                        "source_backed_code_count": 2,
                        "code_block_count": 3,
                        "implementation_hits": 3,
                        "architecture_hits": 2,
                    },
                    {"score": 79.0, "summary": "sections=7, code=2", "status": "ok"},
                ],
            ):
                self.orch._step_select(SimpleNamespace(id="run-pool-select"), ctx)

        self.assertEqual(ctx["selected_topic"]["title"], "Agent Armor")
        self.assertEqual(ctx["selection_arbitration"]["mode"], "pool_winner_arbitration")
        self.assertEqual(ctx["selection_arbitration"]["selected_pool"], "github")
        self.assertEqual(len(ctx["selection_arbitration"]["candidates"]), 3)

    def test_step_select_respects_target_pool_request(self) -> None:
        ctx = {
            "trigger_request": {
                "target_pool": "news",
                "target_pool_label": "AI ???",
            },
            "top_k": [
                {
                    "title": "Agent Armor",
                    "summary": "A GitHub project.",
                    "url": "https://github.com/example/agent-armor",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "GitHub",
                    "primary_pool": "github",
                    "primary_pool_label": "GitHub 椤圭洰姹?,
                    "rule_score": 82.0,
                    "pool_score": 90.0,
                    "final_score": 88.0,
                    "recommendation_score": 91.0,
                    "stack_analysis_score": 87.0,
                },
                {
                    "title": "Model launch with broad impact",
                    "summary": "An official release with meaningful downstream changes.",
                    "url": "https://example.com/news",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "OpenAI Blog",
                    "primary_pool": "news",
                    "primary_pool_label": "AI 鏂伴椈姹?,
                    "rule_score": 86.0,
                    "pool_score": 88.0,
                    "final_score": 87.0,
                    "recommendation_score": 60.0,
                    "stack_analysis_score": 58.0,
                },
            ],
            "pool_winners": [
                {
                    "title": "Model launch with broad impact",
                    "summary": "An official release with meaningful downstream changes.",
                    "url": "https://example.com/news",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "OpenAI Blog",
                    "primary_pool": "news",
                    "primary_pool_label": "AI 鏂伴椈姹?,
                    "rule_score": 86.0,
                    "pool_score": 88.0,
                    "final_score": 87.0,
                    "recommendation_score": 60.0,
                    "stack_analysis_score": 58.0,
                },
                {
                    "title": "Agent Armor",
                    "summary": "A GitHub project.",
                    "url": "https://github.com/example/agent-armor",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "GitHub",
                    "primary_pool": "github",
                    "primary_pool_label": "GitHub 椤圭洰姹?,
                    "rule_score": 82.0,
                    "pool_score": 90.0,
                    "final_score": 88.0,
                    "recommendation_score": 91.0,
                    "stack_analysis_score": 87.0,
                },
            ],
        }

        with patch.object(
            self.orch.llm,
            "call",
            return_value=SimpleNamespace(text='{"index": 0, "reason": "鎸夌洰鏍囨睜浠呬繚鐣欐柊闂诲€欓€?}'),
        ):
            with patch.object(
                self.orch,
                "_probe_topic_evidence",
                return_value={"score": 76.0, "summary": "official release", "status": "ok"},
            ) as probe_mock:
                self.orch._step_select(SimpleNamespace(id="run-target-pool-select"), ctx)

        self.assertEqual(probe_mock.call_count, 1)
        self.assertEqual(ctx["selected_topic"]["primary_pool"], "news")
        self.assertEqual(ctx["selection_arbitration"]["mode"], "target_pool_arbitration")
        self.assertEqual(ctx["selection_arbitration"]["requested_pool"], "news")
        self.assertEqual(ctx["selection_arbitration"]["candidate_count"], 1)

    def test_step_select_skips_llm_when_only_one_candidate_remains(self) -> None:
        ctx = {
            "trigger_request": {
                "target_pool": "github",
                "target_pool_label": "GitHub ???",
            },
            "top_k": [
                {
                    "title": "Firecrawl",
                    "summary": "API-first web data platform for agents.",
                    "url": "https://github.com/firecrawl/firecrawl",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "GitHub Trending",
                    "primary_pool": "github",
                    "primary_pool_label": "GitHub 椤圭洰姹?,
                    "rule_score": 84.0,
                    "pool_score": 91.0,
                    "final_score": 89.0,
                    "recommendation_score": 92.0,
                    "stack_analysis_score": 88.0,
                    "rerank_excerpt": "Repo excerpt for select arbitration.",
                }
            ],
            "pool_winners": [
                {
                    "title": "Firecrawl",
                    "summary": "API-first web data platform for agents.",
                    "url": "https://github.com/firecrawl/firecrawl",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "GitHub Trending",
                    "primary_pool": "github",
                    "primary_pool_label": "GitHub 椤圭洰姹?,
                    "rule_score": 84.0,
                    "pool_score": 91.0,
                    "final_score": 89.0,
                    "recommendation_score": 92.0,
                    "stack_analysis_score": 88.0,
                    "rerank_excerpt": "Repo excerpt for select arbitration.",
                }
            ],
        }

        with patch.object(
            self.orch,
            "_probe_topic_evidence",
            return_value={"score": 82.0, "summary": "readme + source", "status": "ok"},
        ):
            with patch.object(self.orch, "_is_viable_github_candidate", return_value=True):
                with patch.object(self.orch.llm, "call") as llm_call:
                    self.orch._step_select(SimpleNamespace(id="run-single-candidate-select"), ctx)

        llm_call.assert_not_called()
        self.assertEqual(ctx["selected_topic"]["title"], "Firecrawl")
        self.assertEqual(ctx["selection_arbitration"]["candidate_count"], 1)
        self.assertIn("褰撳墠浠呮湁 1 涓彲鐢ㄥ€欓€?, ctx["selected_topic"]["selection_reason"])

    def test_probe_topic_evidence_penalizes_podcast_page_without_transcript(self) -> None:
        item = {
            "title": "Episode #289: Limitations in Human and Automated Code Review",
            "summary": "The Real Python Podcast episode page.",
            "url": "https://realpython.com/podcasts/rpp/289/#t=775",
        }

        with patch.object(
            self.orch.fetch,
            "extract_article_structure",
            return_value={
                "status": "ok",
                "title": "Episode #289: Limitations in Human and Automated Code Review 鈥?The Real Python Podcast",
                "lead": "",
                "sections": [
                    {"heading": "Episode 289", "summary": ""},
                    {"heading": "The Real Python Podcast", "summary": "RSS Apple Spotify Download MP3"},
                    {"heading": "Level Up Your Python Skills", "summary": "Course links"},
                ],
                "code_blocks": [],
                "lists": [],
                "tables": [],
                "coverage_checklist": ["Episode 289", "The Real Python Podcast", "Level Up Your Python Skills"],
            },
        ):
            evidence = self.orch._probe_topic_evidence(item)

        self.assertTrue(evidence["is_audio_page"])
        self.assertFalse(evidence["has_transcript_signal"])
        self.assertLess(evidence["score"], 40.0)

    def test_probe_topic_evidence_penalizes_data_service_page(self) -> None:
        item = {
            "title": "鏈哄櫒涔嬪績路鏁版嵁鏈嶅姟",
            "summary": "data service landing page for paid/reference access.",
            "url": "https://pro.jiqizhixin.com/reference/e2d2143f-d160-4756-88b1-966801a41a4b",
        }

        with patch.object(
            self.orch.fetch,
            "extract_article_structure",
            return_value={
                "status": "ok",
                "title": "鏈哄櫒涔嬪績路鏁版嵁鏈嶅姟",
                "lead": "",
                "sections": [
                    {"heading": "杩樺湪璐瑰姴鐖暟鎹紵鏈哄櫒涔嬪績鏁版嵁鏈嶅姟宸蹭笂绾?鐩存帴鑾峰彇鏁版嵁锛岄珮鏁堝張绋冲畾锛?, "summary": "娣卞叆鍚堜綔璇疯仈绯伙細zhaoyunfeng@jiqizhixin.com"},
                ],
                "code_blocks": [],
                "lists": [],
                "tables": [],
                "coverage_checklist": ["杩樺湪璐瑰姴鐖暟鎹紵鏈哄櫒涔嬪績鏁版嵁鏈嶅姟宸蹭笂绾?],
            },
        ):
            evidence = self.orch._probe_topic_evidence(item)

        self.assertTrue(evidence["has_data_service_signal"])
        self.assertLess(evidence["score"], 20.0)

    def test_step_fact_pack_auto_switches_builder_audience_for_technical_topic(self) -> None:
        ctx = {
            "selected_topic": {
                "title": "Session Management for AI Agents",
                "summary": "TTL, renewals, absolute lifetime, and implementation walkthrough.",
                "url": "https://example.com/session",
                "source": "dev.to",
                "published": datetime.now(timezone.utc).isoformat(),
            },
            "source_pack": {
                "primary": {
                    "status": "ok",
                    "content_text": "lead text",
                    "paragraphs": ["para1", "para2", "para3"],
                },
                "related": [],
            },
            "top_k": [],
            "source_structure": {
                "lead": "This system explains TTL, renewal controls, and hard expiry.",
                "coverage_checklist": ["TTL timeout", "Renewal control", "Absolute lifetime"],
                "sections": [
                    {
                        "heading": "Step 1: TTL",
                        "summary": "Idle expiry logic.",
                        "paragraphs": ["Track last active time"],
                        "code_refs": [0],
                    },
                    {
                        "heading": "Session architecture",
                        "summary": "Gateway, policy engine, and wallet adapter.",
                        "paragraphs": ["Role split", "Guardrails"],
                        "code_refs": [],
                    },
                ],
                "code_blocks": [{"language": "ts", "code_excerpt": "const session = createSession({...})"}],
            },
        }

        self.orch._step_fact_pack(SimpleNamespace(id="run-fact-pack"), ctx)

        self.assertEqual(ctx["content_type"], "technical_walkthrough")
        self.assertEqual(ctx["target_audience"], "ai_builder")


if __name__ == "__main__":
    unittest.main()

