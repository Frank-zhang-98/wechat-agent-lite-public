import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Run, RunStatus
from app.runtime.facade import RuntimeFacade


class PoolRuntimeFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()
        self.runtime = RuntimeFacade(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_run_main_without_target_pool_uses_three_pool_preselection(self) -> None:
        run = SimpleNamespace(id="run-main", trigger_source="manual-ui")
        ctx: dict = {}
        executed_steps: list[str] = []

        def fake_execute_step(run_obj, name, step_fn, step_ctx, retry_policy):
            executed_steps.append(name)
            if name == "FINAL_SELECT":
                step_ctx["selected_topic"] = {
                    "title": "Winner topic",
                    "summary": "Winner summary",
                    "url": "https://example.com/winner",
                    "primary_pool": "github",
                }

        with patch.object(self.runtime, "_execute_step", side_effect=fake_execute_step):
            with patch.object(self.runtime, "_execute_generation_runtime"):
                self.runtime._run_main(run, ctx)

        self.assertEqual(
            executed_steps,
            [
                "HEALTH_CHECK",
                "SOURCE_MAINTENANCE",
                "PRESELECT_NEWS",
                "PRESELECT_GITHUB",
                "PRESELECT_DEEP_DIVE",
                "FINAL_SELECT",
                "SOURCE_ENRICH",
                "SOURCE_STRUCTURE",
                "WEB_SEARCH_PLAN",
                "WEB_SEARCH_FETCH",
                "FACT_GROUNDING",
            ],
        )

    def test_step_fetch_filters_sources_to_target_pool(self) -> None:
        cfg = {
            "ai_companies": [
                {
                    "name": "OpenAI Blog",
                    "url": "https://openai.com/blog/rss.xml",
                    "enabled": True,
                    "pools": ["news"],
                }
            ],
            "tech_media": [
                {
                    "name": "Towards Data Science",
                    "url": "https://towardsdatascience.com/feed",
                    "enabled": True,
                    "pools": ["deep_dive"],
                }
            ],
            "tutorial_communities": [],
            "github": {
                "enabled": True,
                "pools": ["github"],
            },
            "max_age_hours": 168,
            "max_hotspots_per_source": 10,
        }
        ctx = {
            "failed_logs": [],
            "trigger_request": {
                "target_pool": "news",
                "target_pool_label": "AI 新闻池",
            },
        }

        with patch.object(self.runtime.fetch, "load_sources", return_value=cfg):
            with patch.object(
                self.runtime.fetch,
                "fetch_source",
                side_effect=lambda source, **kwargs: [
                    {
                        "title": source["name"],
                        "summary": "summary",
                        "url": source["url"],
                        "source": source["name"],
                        "published": "2026-04-12T00:00:00+00:00",
                        "source_pools": list(source.get("pools") or []),
                    }
                ],
            ) as fetch_source_mock:
                with patch.object(self.runtime.fetch, "fetch_github", return_value=[]) as fetch_github_mock:
                    with patch.object(self.runtime.fetch, "dump_debug"):
                        self.runtime._step_fetch(SimpleNamespace(id="run-fetch"), ctx)

        self.assertEqual(fetch_source_mock.call_count, 1)
        self.assertFalse(fetch_github_mock.called)
        self.assertEqual([item["title"] for item in ctx["fetched_items"]], ["OpenAI Blog"])

    def test_step_rule_score_filters_to_target_pool_using_inferred_primary_pool(self) -> None:
        now = "2026-04-12T00:00:00+00:00"
        ctx = {
            "trigger_request": {
                "target_pool": "news",
                "target_pool_label": "AI 新闻池",
            },
            "deduped_items": [
                {
                    "title": "OpenAI launches new API pricing",
                    "summary": "OpenAI announced a pricing update and product launch for its API platform.",
                    "url": "https://openai.com/blog/pricing-update",
                    "published": now,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_pools": ["news", "deep_dive"],
                },
                {
                    "title": "How we built a multi-agent evaluation pipeline",
                    "summary": "A technical walkthrough covering architecture, retries, evaluation, and workflow design.",
                    "url": "https://openai.com/blog/multi-agent-pipeline",
                    "published": now,
                    "source": "OpenAI Blog",
                    "source_weight": 1.0,
                    "source_category": "ai_companies",
                    "source_pools": ["news", "deep_dive"],
                },
            ],
        }

        self.runtime._step_rule_score(SimpleNamespace(id="run-rule"), ctx)

        self.assertEqual([item["title"] for item in ctx["top_n"]], ["OpenAI launches new API pricing"])
        self.assertTrue(all(item.get("primary_pool") == "news" for item in ctx["top_n"]))

    def test_classifier_respects_target_pool_and_constrains_subtype(self) -> None:
        bootstrap = {
            "selected_topic": {
                "title": "Agent Armor",
                "summary": "An open-source agent runtime with policy engine, audit logs, and repository code examples.",
                "url": "https://example.com/agent-armor",
                "source": "OpenAI Blog",
            },
            "trigger_request": {
                "target_pool": "github",
                "target_pool_label": "GitHub 项目池",
            },
        }
        fact_pack = {
            "primary_pool": "deep_dive",
            "implementation_steps": [{"title": "Indexing"}],
            "architecture_points": [{"component": "Policy engine"}],
            "github_source_code_blocks": [{"source_path": "src/runtime/policy.py"}],
        }

        with patch.object(self.runtime.writing_templates, "build_fact_pack", return_value=dict(fact_pack)):
            with patch.object(
                self.runtime.llm,
                "call",
                return_value=SimpleNamespace(
                    text='{"one_sentence_summary":"Agent runtime","what_it_is":[],"key_mechanisms":[],"concrete_scenarios":[],"numbers":[],"risks":[],"uncertainties":[],"recommended_angle":[]}'
                ),
            ):
                fact_pack_out, fact_compress, intent, audit = self.runtime.graph_runner.classifier_agent.classify(
                    run_id="run-classifier",
                    bootstrap_context=bootstrap,
                )

        self.assertEqual(intent.pool, "github")
        self.assertEqual(intent.subtype, "code_explainer")
        self.assertEqual(fact_pack_out["primary_pool"], "github")

    def test_execute_step_persists_runtime_summary_after_success(self) -> None:
        run = self.runtime.create_run(run_type="main", trigger_source="test", status=RunStatus.running.value)
        ctx = {"failed_logs": [], "quality_scores": []}

        def handler(_run, step_ctx):
            step_ctx["selected_topic"] = {"title": "Winner topic", "url": "https://example.com/winner"}
            step_ctx["pool_winners"] = {"github": {"title": "Winner topic"}}
            step_ctx["top_k"] = [{"title": "Winner topic"}]
            step_ctx["top_k_requested"] = 8
            step_ctx["top_k_actual"] = 1

        self.runtime._execute_step(run, "SELECT", handler, ctx, self.runtime._policy_generate())
        self.session.refresh(run)
        summary = json.loads(run.summary_json or "{}")

        self.assertEqual(summary["selected_topic"]["title"], "Winner topic")
        self.assertEqual(summary["pool_winners"]["github"]["title"], "Winner topic")
        self.assertEqual(summary["top_k_requested"], 8)
        self.assertEqual(summary["top_k_actual"], 1)

    def test_runtime_facade_no_longer_exposes_legacy_visual_step_helpers(self) -> None:
        for attr in (
            "_step_visual_strategy",
            "_step_body_illustration_gen",
            "_step_article_render",
            "_step_cover_5d",
            "_step_cover_gen",
            "_step_cover_check",
            "_step_wechat_draft",
            "_fallback_cover_prompt",
            "_parse_cover_dims",
        ):
            self.assertFalse(hasattr(self.runtime, attr), attr)

    def test_source_enrich_uses_text_only_article_extraction(self) -> None:
        ctx = {
            "selected_topic": {"title": "Winner topic", "url": "https://example.com/main"},
            "top_k": [{"title": "Related topic", "url": "https://example.com/related"}],
        }
        calls: list[dict] = []

        def fake_extract(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return {
                "status": "ok",
                "title": "Fetched title",
                "reason": "",
                "content_text": "Body text",
                "paragraphs": ["Body text"],
                "images": [{"url": "https://example.com/image.png"}],
            }

        with patch.object(self.runtime.fetch, "extract_article_content", side_effect=fake_extract):
            self.runtime._step_source_enrich(SimpleNamespace(id="run-enrich"), ctx)

        self.assertEqual([item["url"] for item in calls], ["https://example.com/main", "https://example.com/related"])
        self.assertTrue(all(item["include_images"] is False for item in calls))
        self.assertEqual(ctx["source_pack"]["primary"]["paragraphs"], ["Body text"])


if __name__ == "__main__":
    unittest.main()
