import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Run, RunStatus
from app.runtime.facade import RuntimeFacade
from app.runtime.state_models import VisualAssetSet


class GraphRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()
        self.runtime = RuntimeFacade(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    @staticmethod
    def _empty_blueprint():
        return SimpleNamespace(
            as_dict=lambda: {"cover_family": "structure", "cover_brief": {}, "items": []},
            items=[],
            cover_family="structure",
            cover_brief={},
        )

    def test_graph_runner_builds_news_package_and_syncs_title_from_h1(self) -> None:
        run = Run(run_type="manual", status=RunStatus.running.value, trigger_source="test")
        self.session.add(run)
        self.session.flush()
        article = "# Runtime Title\n\n## Event Frame\n\nA sufficiently long article body for validation."
        fact_pack = {
            "primary_pool": "news",
            "subtype": "controversy_risk",
            "subtype_label": "Controversy Risk",
            "key_points": ["official response", "trust risk"],
            "source_lead": "An official response triggered a broader trust discussion.",
            "grounded_hard_facts": ["A blog post was published."],
            "industry_context_points": ["Platform trust pressure increased."],
            "grounded_context_facts": ["Safety governance discussion resurfaced."],
            "soft_inferences": ["Trust may keep eroding."],
            "unknowns": ["Follow-up disclosures remain unclear."],
            "news_image_candidates": [],
        }
        bootstrap = {
            "selected_topic": {
                "title": "Sam Altman responds after a public controversy",
                "summary": "Official response and public reaction.",
                "url": "https://example.com/news",
            },
            "top_k": [],
            "source_pack": {"primary": {}, "related": []},
            "source_structure": {"sections": []},
            "fact_grounding": {},
            "web_enrich": {},
            "fact_compress": {
                "one_sentence_summary": "Public controversy spilled into platform trust risk.",
                "key_mechanisms": ["response and risk overlapped"],
                "risks": ["trust erosion"],
                "uncertainties": ["future disclosures"],
            },
        }

        with patch.object(self.runtime.writing_templates, "build_fact_pack", return_value=fact_pack):
            with patch.object(self.runtime.writing_templates, "build_write_prompt", return_value="WRITE PROMPT"):
                with patch.object(
                    self.runtime.title_generator,
                    "generate",
                    return_value=SimpleNamespace(
                        article_title="Fallback Title",
                        wechat_title="Fallback Title",
                        source="heuristic",
                        debug={},
                        as_dict=lambda: {
                            "article_title": "Fallback Title",
                            "wechat_title": "Fallback Title",
                            "source": "heuristic",
                            "debug": {},
                        },
                    ),
                ):
                    with patch.object(
                        self.runtime.llm,
                        "call",
                        side_effect=[
                            SimpleNamespace(text=article, model="qwen-plus", provider="test", estimated=False),
                            SimpleNamespace(text="{}", model="qwen-plus", provider="test", estimated=False),
                        ],
                    ):
                        with patch.object(
                            self.runtime,
                            "_humanize_article_if_needed",
                            return_value={
                                "article": article,
                                "before": {"score": 90.0},
                                "after": {"score": 90.0},
                                "rewrite_applied": False,
                            },
                        ):
                            with patch.object(self.runtime, "_writer_output_is_acceptable", return_value=True):
                                with patch.object(
                                    self.runtime,
                                    "_quality_hard_checks",
                                    return_value={"passed": True, "soft_warnings": [], "hard_failures": []},
                                ):
                                    with patch.object(
                                        self.runtime.hallucination_checker,
                                        "check",
                                        return_value={
                                            "unsupported_claims": [],
                                            "inference_written_as_fact": [],
                                            "forbidden_claim_violations": [],
                                            "severity": "low",
                                            "rewrite_required": False,
                                        },
                                    ):
                                        with patch.object(
                                            self.runtime.visual_strategy,
                                            "build_blueprint",
                                            return_value=self._empty_blueprint(),
                                        ):
                                            with patch.object(self.runtime.media_acquisition, "acquire", return_value=[]):
                                                with patch.object(self.runtime.graph_runner.visual_agent, "generate", return_value=(VisualAssetSet(), {"outputs": []})):
                                                    package = self.runtime.graph_runner.run(
                                                        run=run,
                                                        trigger="test",
                                                        input_payload=bootstrap,
                                                        include_cover_assets=False,
                                                        publish_enabled=False,
                                                    )

        self.assertEqual(package.intent.pool, "news")
        self.assertEqual(package.intent.subtype, "controversy_risk")
        self.assertTrue(package.title_plan.article_title)
        self.assertEqual(package.title_plan.source, "heuristic")
        self.assertTrue(package.article_html)

    def test_graph_runner_builds_fact_compress_when_bootstrap_missing(self) -> None:
        run = Run(run_type="manual", status=RunStatus.running.value, trigger_source="test")
        self.session.add(run)
        self.session.flush()
        fact_pack = {
            "primary_pool": "news",
            "subtype": "industry_news",
            "subtype_label": "Industry News",
            "key_points": ["OpenAI responded"],
            "source_lead": "Controversy escalated.",
            "grounded_hard_facts": ["Official response published."],
            "industry_context_points": ["Trust pressure increased."],
            "grounded_context_facts": ["Safety discussion intensified."],
            "soft_inferences": ["Trust may keep slipping."],
            "unknowns": ["Unknown follow-up."],
            "news_image_candidates": [],
        }
        bootstrap = {
            "selected_topic": {
                "title": "OpenAI responds after controversy",
                "summary": "Official response and public reaction.",
                "url": "https://example.com/news",
            },
            "top_k": [],
            "source_pack": {"primary": {}, "related": []},
            "source_structure": {"sections": []},
            "fact_grounding": {},
            "web_enrich": {},
        }
        article = "# New Title\n\n## Event Frame\n\nThis is a sufficiently long runtime article body."
        compress_payload = (
            '{"one_sentence_summary":"OpenAI responded after controversy",'
            '"what_it_is":["official response"],'
            '"key_mechanisms":["response and trust overlap"],'
            '"concrete_scenarios":["platform trust pressure"],'
            '"numbers":[],'
            '"risks":["trust erosion"],'
            '"uncertainties":["future disclosures"],'
            '"recommended_angle":["trust risk continues"]}'
        )

        with patch.object(self.runtime.writing_templates, "build_fact_pack", return_value=fact_pack):
            with patch.object(self.runtime.writing_templates, "build_write_prompt", return_value="WRITE PROMPT"):
                with patch.object(
                    self.runtime.title_generator,
                    "generate",
                    return_value=SimpleNamespace(
                        article_title="OpenAI responds after controversy",
                        wechat_title="OpenAI responds after controversy",
                        source="heuristic",
                        debug={},
                        as_dict=lambda: {
                            "article_title": "OpenAI responds after controversy",
                            "wechat_title": "OpenAI responds after controversy",
                            "source": "heuristic",
                            "debug": {},
                        },
                    ),
                ):
                    with patch.object(
                        self.runtime.llm,
                        "call",
                        side_effect=[
                            SimpleNamespace(text=compress_payload, model="qwen-plus", provider="test", estimated=False),
                            SimpleNamespace(text=article, model="qwen-plus", provider="test", estimated=False),
                            SimpleNamespace(text="{}", model="qwen-plus", provider="test", estimated=False),
                        ],
                    ):
                        with patch.object(self.runtime, "_writer_output_is_acceptable", return_value=True):
                            with patch.object(
                                self.runtime,
                                "_humanize_article_if_needed",
                                return_value={
                                    "article": article,
                                    "before": {"score": 90.0},
                                    "after": {"score": 90.0},
                                    "rewrite_applied": False,
                                },
                            ):
                                with patch.object(
                                    self.runtime,
                                    "_quality_hard_checks",
                                    return_value={"passed": True, "soft_warnings": [], "hard_failures": []},
                                ):
                                    with patch.object(
                                        self.runtime.hallucination_checker,
                                        "check",
                                        return_value={
                                            "unsupported_claims": [],
                                            "inference_written_as_fact": [],
                                            "forbidden_claim_violations": [],
                                            "severity": "low",
                                            "rewrite_required": False,
                                        },
                                    ):
                                        with patch.object(
                                            self.runtime.visual_strategy,
                                            "build_blueprint",
                                            return_value=self._empty_blueprint(),
                                        ):
                                            with patch.object(self.runtime.media_acquisition, "acquire", return_value=[]):
                                                with patch.object(self.runtime.graph_runner.visual_agent, "generate", return_value=(VisualAssetSet(), {"outputs": []})):
                                                    package = self.runtime.graph_runner.run(
                                                        run=run,
                                                        trigger="test",
                                                        input_payload=bootstrap,
                                                        include_cover_assets=False,
                                                        publish_enabled=False,
                                                    )

        self.assertEqual(package.fact_compress["one_sentence_summary"], "OpenAI responded after controversy")
        self.assertIn("trust erosion", package.fact_compress["risks"])


if __name__ == "__main__":
    unittest.main()
