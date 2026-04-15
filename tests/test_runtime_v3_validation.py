import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import get_run_detail, redo_run_step
from app.db import Base
from app.models import Run, RunStatus, RunStep, StepStatus
from app.runtime.facade import RuntimeFacade
from app.runtime.state_models import ArticleDraft, ArticleIntent, ArticlePackage, RuntimeTitlePlan, SectionPlan, SectionSpec, VisualAssetSet, VisualBlueprint


class RuntimeV3ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.session = SessionLocal()
        self.runtime = RuntimeFacade(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _runtime_package(self) -> ArticlePackage:
        return ArticlePackage(
            intent=ArticleIntent(
                pool="news",
                subtype="controversy_risk",
                subtype_label="Controversy Risk",
                core_angle="Narrative controversy spills into real-world trust risk",
                audience="ai_product_manager",
            ),
            fact_pack={"primary_pool": "news", "subtype": "controversy_risk", "subtype_label": "Controversy Risk"},
            fact_compress={"one_sentence_summary": "Risk is spilling outward"},
            section_plan=SectionPlan(
                pool="news",
                strategy_label="News Pool",
                sections=[
                    SectionSpec(role="event_frame", goal="Explain the event", heading_hint="Event Frame"),
                    SectionSpec(role="meaning_or_risk", goal="Explain the risk", heading_hint="Meaning or Risk"),
                ],
            ),
            article_draft=ArticleDraft(article_markdown="# New Title\n\n## Event Frame\n\nBody", h1_title="New Title"),
            title_plan=RuntimeTitlePlan(article_title="New Title", wechat_title="New Title", source="heuristic"),
            visual_blueprint=VisualBlueprint(cover_family="structure"),
            visual_assets=VisualAssetSet(),
            article_layout={"name": "news", "label": "News"},
            article_render={"html_path": "F:/runs/test/article.html", "html_length": 100, "block_count": 4},
            article_html="<h1>New Title</h1>",
            wechat_result={"success": True, "draft_id": "draft-123"},
            quality={"score": 90.0, "status": "passed", "attempts": 1, "scores": [90.0]},
            draft_status="saved",
            step_audits={"WRITE_ARTICLE": {"outputs": [{"title": "draft", "text": "ok"}]}},
        )

    def _create_runtime_run(self) -> Run:
        package = self._runtime_package()
        run = Run(
            id="runtime-run",
            run_type="main",
            status=RunStatus.success.value,
            trigger_source="manual-test",
            article_title=package.title_plan.article_title,
            article_markdown=package.article_draft.article_markdown,
            draft_status="saved",
            started_at=datetime.now(timezone.utc),
            summary_json=json.dumps(
                {
                    "selected_topic": {
                        "title": "Original Topic",
                        "url": "https://example.com/source",
                        "summary": "Original summary",
                        "source": "example",
                    },
                    "runtime_graph": {
                        "runtime": {
                            "engine": "langgraph",
                            "graph_status": "running",
                            "active_graph_node": "WRITE_ARTICLE",
                        },
                        "article_package": package.as_dict(),
                    },
                },
                ensure_ascii=False,
            ),
        )
        self.session.add(run)
        self.session.flush()
        self.session.add(RunStep(run_id=run.id, name="WRITE_ARTICLE", status=StepStatus.success.value))
        self.session.commit()
        return run

    def test_runtime_run_detail_uses_runtime_projection(self) -> None:
        run = self._create_runtime_run()

        @contextmanager
        def fake_get_session():
            yield self.session

        with patch("app.api.get_session", fake_get_session), patch("app.api._load_run_article_html", return_value="<div>runtime</div>"):
            data = get_run_detail(run.id)

        projection = data["run"]["projection"]
        self.assertEqual(projection["selected_pool"], "news")
        self.assertEqual(projection["subtype"], "controversy_risk")
        self.assertEqual(projection["active_graph_node"], "WRITE_ARTICLE")
        self.assertTrue(projection["raw_runtime_snapshot"])

    def test_api_step_redo_creates_child_run(self) -> None:
        source = self._create_runtime_run()

        @contextmanager
        def fake_get_session():
            yield self.session

        with patch("app.api.get_session", fake_get_session):
            result = redo_run_step(source.id, "WRITE_ARTICLE", BackgroundTasks())

        self.assertTrue(result["ok"])
        child = self.session.get(Run, result["new_run_id"])
        summary = json.loads(child.summary_json or "{}")
        self.assertEqual(summary["source_run_id"], source.id)
        self.assertEqual(summary["redo_request"]["step_name"], "WRITE_ARTICLE")

    def test_write_article_redo_executes_chain(self) -> None:
        source = self._create_runtime_run()
        redo_run = self.runtime.create_step_redo_run(source_run_id=source.id, step_name="WRITE_ARTICLE")

        with patch.object(self.runtime.graph_runner, "redo_from_step", return_value=self._runtime_package()) as redo_mock:
            self.runtime.execute_existing(redo_run.id)

        kwargs = redo_mock.call_args.kwargs
        self.assertEqual(kwargs["start_step"], "WRITE_ARTICLE")
        self.assertEqual(kwargs["bootstrap_context"]["selected_topic"]["title"], "Original Topic")


if __name__ == "__main__":
    unittest.main()
