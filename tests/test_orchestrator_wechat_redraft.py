import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Run, RunStatus
from app.runtime.facade import RuntimeFacade
from app.runtime.state_models import ArticleDraft, ArticleIntent, ArticlePackage, RuntimeTitlePlan, SectionPlan, SectionSpec, VisualAssetSet, VisualBlueprint


class RuntimeFacadeRedoTests(unittest.TestCase):
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
                core_angle="叙事争议开始外溢成现实风险",
                audience="ai_product_manager",
            ),
            fact_pack={"primary_pool": "news", "subtype": "controversy_risk"},
            fact_compress={"one_sentence_summary": "风险开始外溢"},
            section_plan=SectionPlan(
                pool="news",
                strategy_label="新闻池",
                sections=[
                    SectionSpec(role="event_frame", goal="交代事件", heading_hint="事件脉络"),
                    SectionSpec(role="meaning_or_risk", goal="解释意义", heading_hint="真正重要的变化"),
                ],
            ),
            article_draft=ArticleDraft(
                article_markdown="# 新标题\n\n## 事件脉络\n\n正文内容",
                h1_title="新标题",
            ),
            title_plan=RuntimeTitlePlan(
                article_title="新标题",
                wechat_title="新标题",
                source="heuristic",
            ),
            visual_blueprint=VisualBlueprint(cover_family="structure"),
            visual_assets=VisualAssetSet(cover_asset={"path": "F:/covers/test-cover.png"}),
            article_layout={"name": "news"},
            article_render={"html_path": "F:/runs/test/article.html"},
            article_html="<h1>新标题</h1>",
            wechat_result={"success": True, "draft_id": "draft-123"},
            quality={"score": 90.0, "status": "passed", "attempts": 1, "scores": [90.0]},
            draft_status="saved",
            step_audits={"WRITE_ARTICLE": {"outputs": [{"title": "draft", "text": "ok"}]}},
        )

    def _create_runtime_run(self) -> Run:
        package = self._runtime_package()
        run = Run(
            run_type="main",
            status=RunStatus.success.value,
            trigger_source="manual-test",
            article_title=package.title_plan.article_title,
            article_markdown=package.article_draft.article_markdown,
            draft_status="saved",
            summary_json=json.dumps(
                {
                    "selected_topic": {
                        "title": "原始主题",
                        "url": "https://example.com/source",
                        "summary": "原始摘要",
                        "source": "example",
                    },
                    "source_pack": {"primary": {"url": "https://example.com/source"}, "related": []},
                    "source_structure": {"sections": [{"heading": "事件脉络"}]},
                    "fact_grounding": {"citations": ["https://example.com/source"]},
                    "fact_pack": {"primary_pool": "news", "subtype": "controversy_risk"},
                    "fact_compress": {"one_sentence_summary": "原始压缩摘要"},
                    "runtime_graph": {
                        "runtime": {"engine": "langgraph"},
                        "article_package": package.as_dict(),
                    },
                },
                ensure_ascii=False,
            ),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def test_create_step_redo_run_stores_child_metadata(self) -> None:
        source = self._create_runtime_run()

        redo_run = self.runtime.create_step_redo_run(source_run_id=source.id, step_name="WRITE_ARTICLE")

        self.assertEqual(redo_run.run_type, "manual")
        self.assertEqual(redo_run.trigger_source, "redo:write_article")
        summary = json.loads(redo_run.summary_json)
        self.assertEqual(summary["source_run_id"], source.id)
        self.assertEqual(summary["redo_request"]["step_name"], "WRITE_ARTICLE")
        self.assertEqual(summary["redo_request"]["redo_chain"], "to_end")

    def test_execute_existing_redo_reuses_runtime_snapshot(self) -> None:
        source = self._create_runtime_run()
        redo_run = self.runtime.create_step_redo_run(source_run_id=source.id, step_name="RENDER_ARTICLE")
        returned_package = self._runtime_package()

        with patch.object(
            self.runtime.graph_runner,
            "redo_from_step",
            return_value=returned_package,
        ) as redo_mock:
            finished = self.runtime.execute_existing(redo_run.id)

        self.assertEqual(finished.status, RunStatus.success.value)
        self.assertEqual(finished.article_title, "新标题")
        self.assertTrue(redo_mock.called)
        kwargs = redo_mock.call_args.kwargs
        self.assertEqual(kwargs["start_step"], "RENDER_ARTICLE")
        self.assertEqual(kwargs["bootstrap_context"]["selected_topic"]["title"], "原始主题")
        self.assertEqual(kwargs["source_package"].title_plan.article_title, "新标题")
        summary = json.loads(finished.summary_json)
        self.assertEqual(summary["source_run_id"], source.id)
        self.assertEqual(summary["redo_request"]["step_name"], "RENDER_ARTICLE")

    def test_execute_generation_runtime_writes_runtime_snapshot(self) -> None:
        run = Run(run_type="manual", status=RunStatus.running.value, trigger_source="test")
        self.session.add(run)
        self.session.flush()
        ctx = {
            "selected_topic": {"title": "原始主题", "url": "https://example.com/source"},
            "source_pack": {"primary": {"url": "https://example.com/source"}},
            "source_structure": {"sections": [{"heading": "事件脉络"}]},
            "fact_grounding": {"citations": ["https://example.com/source"]},
            "quality_scores": [],
            "failed_logs": [],
        }
        package = self._runtime_package()

        with patch.object(self.runtime.graph_runner, "run", return_value=package) as run_mock:
            self.runtime._execute_generation_runtime(
                run,
                ctx,
                trigger="manual_url",
                include_cover_assets=True,
                publish_enabled=True,
            )

        self.assertTrue(run_mock.called)
        self.assertEqual(run.article_title, "新标题")
        self.assertIn("runtime_graph", ctx)
        summary = json.loads(run.summary_json)
        self.assertIn("runtime_graph", summary)
        self.assertEqual(summary["runtime_graph"]["runtime"]["engine"], "langgraph")


if __name__ == "__main__":
    unittest.main()
