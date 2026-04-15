import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import _load_run_article_html, _query_runs_page, get_run_asset, get_run_detail, get_run_step_detail, trigger_run
from app.db import Base
from app.models import Run, RunStatus, RunStep, StepStatus
from app.schemas import TriggerRunPayload


class ApiRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _add_run(
        self,
        *,
        run_id: str,
        minutes_ago: int,
        run_type: str,
        status: str,
        title: str,
        failed_step: str = "",
        selected_pool: str = "",
        subtype: str = "",
        subtype_label: str = "",
    ) -> None:
        summary = {}
        if selected_pool or subtype:
            summary = {
                "selected_pool": selected_pool,
                "subtype": subtype,
                "subtype_label": subtype_label,
                "selected_topic": {"title": title, "summary": "summary"},
                "fact_pack": {"primary_pool": selected_pool, "subtype": subtype, "subtype_label": subtype_label},
            }
        run = Run(
            id=run_id,
            run_type=run_type,
            status=status,
            article_title=title,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
            finished_at=datetime.now(timezone.utc) - timedelta(minutes=max(minutes_ago - 1, 0)),
            summary_json=json.dumps(summary, ensure_ascii=False),
        )
        self.session.add(run)
        self.session.flush()
        if failed_step:
            self.session.add(RunStep(run_id=run.id, name=failed_step, status=StepStatus.failed.value))

    def test_query_runs_page_supports_pagination_and_filters(self) -> None:
        self._add_run(run_id="run-1", minutes_ago=1, run_type="health", status=RunStatus.success.value, title="Health")
        self._add_run(
            run_id="run-2",
            minutes_ago=2,
            run_type="main",
            status=RunStatus.failed.value,
            title="Main Failed",
            failed_step="WRITE_ARTICLE",
            selected_pool="deep_dive",
            subtype="technical_walkthrough",
            subtype_label="Technical Walkthrough",
        )
        self._add_run(run_id="run-3", minutes_ago=3, run_type="manual_url", status=RunStatus.success.value, title="Manual URL")
        self._add_run(run_id="run-4", minutes_ago=4, run_type="main", status=RunStatus.success.value, title="Main Success")
        self.session.commit()

        page = _query_runs_page(
            self.session,
            page=1,
            page_size=2,
            keyword="Main",
            status="",
            run_type="",
            sort_order="time_desc",
            quick_filter="all",
        )

        self.assertEqual(page["pagination"]["total"], 2)
        self.assertEqual(page["runs"][0]["id"], "run-2")
        self.assertEqual(page["runs"][0]["selected_pool"], "deep_dive")
        self.assertEqual(page["runs"][0]["subtype"], "technical_walkthrough")
        self.assertEqual(page["runs"][0]["subtype_label"], "Technical Walkthrough")

    def test_run_detail_returns_runtime_projection(self) -> None:
        run = Run(
            id="run-step-preview",
            run_type="main",
            status=RunStatus.success.value,
            article_title="Step Preview",
            article_markdown="# Preview",
            started_at=datetime.now(timezone.utc),
            summary_json=json.dumps(
                {
                    "selected_topic": {"title": "Step Preview", "summary": "runtime summary", "source": "example"},
                    "runtime_graph": {
                        "runtime": {"active_graph_node": "WRITE_ARTICLE", "graph_status": "running"},
                        "article_package": {
                            "intent": {
                                "pool": "news",
                                "subtype": "breaking_news",
                                "subtype_label": "Breaking News",
                                "core_angle": "Angle",
                                "audience": "ai_reader",
                                "must_avoid": [],
                            },
                            "fact_pack": {"primary_pool": "news", "subtype": "breaking_news"},
                            "fact_compress": {"one_sentence_summary": "Runtime summary"},
                            "section_plan": {"pool": "news", "strategy_label": "News", "sections": []},
                            "article_draft": {"article_markdown": "# Preview", "h1_title": "Preview", "section_outputs": []},
                            "title_plan": {"article_title": "Preview", "wechat_title": "Preview", "source": "heuristic", "debug": {}},
                            "visual_blueprint": {"cover_family": "", "cover_brief": {}, "items": []},
                            "visual_assets": {"body_assets": [], "cover_5d": {}, "cover_asset": {}},
                            "article_layout": {},
                            "article_render": {},
                            "article_html": "<div>rendered</div>",
                            "wechat_result": {},
                            "quality": {"score": 88},
                            "draft_status": "saved",
                            "step_audits": {},
                        },
                    },
                },
                ensure_ascii=False,
            ),
        )
        self.session.add(run)
        self.session.flush()
        step = RunStep(
            run_id=run.id,
            name="WRITE_ARTICLE",
            status=StepStatus.success.value,
            details_json=json.dumps({"headline": "Write done", "summary": {"quality": 88}, "items": ["a", "b"]}),
        )
        self.session.add(step)
        self.session.commit()

        @contextmanager
        def fake_get_session():
            yield self.session

        with patch("app.api.get_session", fake_get_session), patch("app.api._load_run_article_html", return_value="<div>rendered</div>"):
            detail_data = get_run_detail(run.id)
            full_data = get_run_step_detail(run.id, step.id)

        self.assertEqual(detail_data["run"]["projection"]["selected_pool"], "news")
        self.assertEqual(detail_data["run"]["projection"]["subtype"], "breaking_news")
        self.assertEqual(detail_data["run"]["projection"]["active_graph_node"], "WRITE_ARTICLE")
        self.assertEqual(full_data["step"]["details"]["headline"], "Write done")

    def test_run_detail_compacts_heavy_runtime_summary(self) -> None:
        huge_text = "x" * 5000
        run = Run(
            id="run-compact-summary",
            run_type="main",
            status=RunStatus.running.value,
            article_title="Compact Summary",
            article_markdown="",
            started_at=datetime.now(timezone.utc),
            summary_json=json.dumps(
                {
                    "selected_topic": {"title": "Heavy Topic", "summary": "summary", "source": "example"},
                    "top_k": [
                        {"title": "Topic A", "summary": "A", "source": "src", "url": "https://example.com/a"},
                        {"title": "Topic B", "summary": "B", "source": "src", "url": "https://example.com/b"},
                    ],
                    "source_pack": {
                        "primary": {
                            "title": "Primary",
                            "url": "https://example.com/source",
                            "status": "ok",
                            "content_text": huge_text,
                            "paragraphs": ["p1", "p2", "p3"],
                            "images": [],
                        }
                    },
                    "runtime_graph": {
                        "runtime": {"active_graph_node": "SOURCE_ENRICH", "graph_status": "running"},
                        "article_package": {
                            "intent": {"pool": "github", "subtype": "code_explainer", "subtype_label": "Code Explainer"},
                            "fact_pack": {"primary_pool": "github", "subtype": "code_explainer"},
                            "fact_compress": {"one_sentence_summary": "summary"},
                            "section_plan": {"pool": "github", "sections": [{}, {}]},
                            "article_draft": {"article_markdown": huge_text, "h1_title": "Heavy Draft"},
                            "title_plan": {"article_title": "Heavy Draft", "wechat_title": "Heavy Draft", "source": "heuristic"},
                            "visual_blueprint": {"cover_family": "structure", "items": [{"mode": "generate"}]},
                            "visual_assets": {"body_assets": [{"path": "/tmp/body.png"}], "cover_asset": {"path": "/tmp/cover.png"}},
                            "visual_diagnostics": {
                                "planned_item_count": 1,
                                "qualified_body_asset_count": 1,
                                "omitted_by_policy": False,
                                "visual_fit_failures": [],
                            },
                            "article_layout": {"name": "default"},
                            "article_render": {"html_path": "/tmp/article.html", "visual_body_result": "inserted"},
                            "article_html": huge_text,
                            "wechat_result": {"success": True},
                            "quality": {"score": 88},
                            "draft_status": "saved",
                        },
                    },
                },
                ensure_ascii=False,
            ),
        )
        self.session.add(run)
        self.session.commit()

        @contextmanager
        def fake_get_session():
            yield self.session

        with patch("app.api.get_session", fake_get_session), patch("app.api._load_run_article_html", return_value=""):
            detail_data = get_run_detail(run.id)

        summary = detail_data["run"]["summary"]
        snapshot = detail_data["run"]["projection"]["raw_runtime_snapshot"]
        self.assertEqual(summary["source_pack"]["primary"]["content_text_length"], 5000)
        self.assertEqual(summary["top_k"]["count"], 2)
        self.assertNotIn("content_text", summary["source_pack"]["primary"])
        self.assertEqual(snapshot["article_package"]["article_draft"]["article_markdown_length"], 5000)
        self.assertEqual(snapshot["article_package"]["visual_assets"]["body_asset_count"], 1)
        self.assertEqual(snapshot["article_package"]["visual_diagnostics"]["planned_item_count"], 1)
        self.assertEqual(snapshot["article_package"]["article_render"]["visual_body_result"], "inserted")

    def test_load_run_article_html_fallback_uses_visual_assets_body_assets(self) -> None:
        run = Run(
            id="run-fallback-html",
            run_type="main",
            status=RunStatus.success.value,
            article_title="Fallback Preview",
            article_markdown="# Fallback Preview\n\n正文",
            started_at=datetime.now(timezone.utc),
            summary_json="{}",
        )
        summary = {
            "selected_pool": "deep_dive",
            "subtype": "tutorial",
            "visual_assets": {"body_assets": [{"path": "data/runs/run-fallback-html/illustrations/shot.png"}]},
        }

        class FakeRenderer:
            def __init__(self) -> None:
                self.kwargs = {}

            def render(self, *args, **kwargs):
                self.kwargs = kwargs
                return type("Rendered", (), {"html": "<div>ok</div>"})()

        renderer = FakeRenderer()
        with patch("app.api._get_article_renderer", return_value=renderer):
            html = _load_run_article_html(run, summary)

        self.assertEqual(html, "<div>ok</div>")
        self.assertEqual(renderer.kwargs["pool"], "deep_dive")
        self.assertEqual(renderer.kwargs["subtype"], "tutorial")

    def test_get_run_asset_serves_files_within_run_directory(self) -> None:
        run = Run(
            id="run-asset",
            run_type="main",
            status=RunStatus.success.value,
            article_title="Asset",
            started_at=datetime.now(timezone.utc),
            summary_json="{}",
        )
        self.session.add(run)
        self.session.commit()

        @contextmanager
        def fake_get_session():
            yield self.session

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            asset_path = data_dir / "runs" / run.id / "illustrations" / "shot.png"
            asset_path.parent.mkdir(parents=True)
            asset_path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x89\x17\x9b"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            config = type("Cfg", (), {"data_dir": data_dir})()
            with patch("app.api.get_session", fake_get_session), patch("app.api.CONFIG", config):
                response = get_run_asset(run.id, "illustrations/shot.png")

        self.assertEqual(Path(response.path).name, "shot.png")
        self.assertEqual(response.media_type, "image/png")

    def test_trigger_run_stores_target_pool_request(self) -> None:
        @contextmanager
        def fake_get_session():
            yield self.session

        with patch("app.api.get_session", fake_get_session):
            result = trigger_run(
                TriggerRunPayload(run_type="main", trigger_source="manual-ui", target_pool="github"),
                BackgroundTasks(),
            )

        self.assertTrue(result["ok"])
        run = self.session.get(Run, result["run_id"])
        summary = json.loads(run.summary_json or "{}")
        self.assertEqual(summary["trigger_request"]["target_pool"], "github")


if __name__ == "__main__":
    unittest.main()
