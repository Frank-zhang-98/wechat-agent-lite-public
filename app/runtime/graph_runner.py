from __future__ import annotations

from app.agents.article_evaluator_agent import ArticleEvaluatorAgent
from app.agents.base import AgentContext
from app.agents.classifier_agent import ClassifierAgent
from app.agents.plan_evaluator_agent import PlanEvaluatorAgent
from app.agents.publisher_agent import PublisherAgent
from app.agents.section_planner_agent import SectionPlannerAgent
from app.agents.title_agent import TitleAgent
from app.agents.visual_agent import VisualAgent
from app.agents.writer_agent import WriterAgent
from app.graphs.article_generation_graph import compile_article_generation_graph
from app.graphs.nodes.evaluate_article_node import build_evaluate_article_node
from app.graphs.nodes.generate_title_node import build_generate_title_node
from app.graphs.nodes.plan_visuals_node import build_plan_visuals_node
from app.graphs.nodes.publish_node import build_publish_node
from app.graphs.nodes.render_article_node import build_render_article_node
from app.graphs.nodes.write_article_node import build_write_article_node
from app.policies import DeepDivePolicy, GithubPolicy, NewsPolicy, PolicyRegistry
from app.rubrics import DeepDiveRubric, GithubRubric, NewsRubric, RubricRegistry
from app.runtime.state_models import ArticlePackage, build_graph_state


class ArticleGenerationGraphRunner:
    def __init__(self, support) -> None:
        self.support = support
        self.policy_registry = PolicyRegistry([NewsPolicy(), GithubPolicy(), DeepDivePolicy()])
        self.rubric_registry = RubricRegistry([NewsRubric(), GithubRubric(), DeepDiveRubric()])
        self.agent_ctx = AgentContext(
            support=support,
            policy_registry=self.policy_registry,
            rubric_registry=self.rubric_registry,
        )
        self.classifier_agent = ClassifierAgent(self.agent_ctx)
        self.section_planner_agent = SectionPlannerAgent(self.agent_ctx)
        self.plan_evaluator_agent = PlanEvaluatorAgent(self.agent_ctx)
        self.writer_agent = WriterAgent(self.agent_ctx)
        self.title_agent = TitleAgent(self.agent_ctx)
        self.article_evaluator_agent = ArticleEvaluatorAgent(self.agent_ctx)
        self.visual_agent = VisualAgent(self.agent_ctx)
        self.publisher_agent = PublisherAgent(self.agent_ctx)
        self._write_article_node = build_write_article_node(self.writer_agent)
        self._generate_title_node = build_generate_title_node(self.title_agent)
        self._evaluate_article_node = build_evaluate_article_node(self.article_evaluator_agent)
        self._plan_visuals_node = build_plan_visuals_node(self.visual_agent, support)
        self._render_article_node = build_render_article_node(support)
        self._publish_node = build_publish_node(self.publisher_agent)
        self._graph = compile_article_generation_graph(
            classifier_agent=self.classifier_agent,
            section_planner_agent=self.section_planner_agent,
            plan_evaluator_agent=self.plan_evaluator_agent,
            writer_agent=self.writer_agent,
            title_agent=self.title_agent,
            article_evaluator_agent=self.article_evaluator_agent,
            visual_agent=self.visual_agent,
            publisher_agent=self.publisher_agent,
            support=support,
        )

    def run(self, *, run, trigger: str, input_payload: dict, include_cover_assets: bool, publish_enabled: bool) -> ArticlePackage:
        state = build_graph_state(
            run_id=run.id,
            trigger=trigger,
            bootstrap_context=input_payload,
            include_cover_assets=include_cover_assets,
            publish_enabled=publish_enabled,
        )
        state["run"] = run
        self.support.update_graph_progress(run=run, status="running", active_node="CLASSIFY")
        try:
            result = self._graph.invoke(state)
        except Exception:
            self.support.update_graph_progress(run=run, status="failed", active_node="")
            raise
        self.support.update_graph_progress(run=run, status="completed", active_node="")
        return self._package_from_state(result)

    def redo_from_step(
        self,
        *,
        run,
        trigger: str,
        bootstrap_context: dict,
        source_package: ArticlePackage,
        start_step: str,
        include_cover_assets: bool,
        publish_enabled: bool,
    ) -> ArticlePackage:
        state = build_graph_state(
            run_id=run.id,
            trigger=trigger,
            bootstrap_context=dict(bootstrap_context or {}),
            include_cover_assets=include_cover_assets,
            publish_enabled=publish_enabled,
        )
        state.update(
            {
                "run": run,
                "fact_pack": dict(source_package.fact_pack or {}),
                "fact_compress": dict(source_package.fact_compress or {}),
                "article_intent": source_package.intent,
                "section_plan": source_package.section_plan,
                "article_draft": source_package.article_draft,
                "title_plan_state": source_package.title_plan,
                "visual_blueprint_state": source_package.visual_blueprint,
                "visual_assets_state": source_package.visual_assets,
                "visual_diagnostics": dict(source_package.visual_diagnostics or {}),
                "article_layout": dict(source_package.article_layout or {}),
                "article_render": dict(source_package.article_render or {}),
                "article_html": str(source_package.article_html or ""),
                "wechat_result": dict(source_package.wechat_result or {}),
                "article_evaluation": dict(source_package.quality or {}),
                "draft_status": str(source_package.draft_status or ("saved" if publish_enabled else "not_started")),
            }
        )
        flow = str(start_step or "").strip().upper()
        self.support.update_graph_progress(run=run, status="running", active_node=flow)
        try:
            if flow == "WRITE_ARTICLE":
                state = self._run_write_chain(state)
                state = self._run_visual_chain(state, publish_enabled=publish_enabled)
            elif flow == "GENERATE_TITLE":
                state = self._run_title_chain(state)
                state = self._run_visual_chain(state, publish_enabled=publish_enabled)
            elif flow == "PLAN_VISUALS":
                state = self._plan_visuals_node(state)
                state = self._run_render_publish_chain(state, publish_enabled=publish_enabled)
            elif flow == "RENDER_ARTICLE":
                state = self._run_render_publish_chain(state, publish_enabled=publish_enabled)
            elif flow == "PUBLISH":
                state = self._publish_node(state)
            else:
                raise ValueError(f"unsupported redo step: {start_step}")
        except Exception:
            self.support.update_graph_progress(run=run, status="failed", active_node="")
            raise
        self.support.update_graph_progress(run=run, status="completed", active_node="")
        return self._package_from_state(state)

    def _run_write_chain(self, state: dict) -> dict:
        state = self._write_article_node(state)
        return self._run_title_chain(state)

    def _run_title_chain(self, state: dict) -> dict:
        while True:
            state = self._generate_title_node(state)
            state = self._evaluate_article_node(state)
            evaluation = dict(state.get("article_evaluation") or {})
            if evaluation.get("passed"):
                return state
            if int(state.get("article_attempts", 0) or 0) >= 2:
                raise RuntimeError("article evaluation failed: " + ", ".join(str(item) for item in evaluation.get("hard_failures", [])))
            state = self._write_article_node(state)

    def _run_visual_chain(self, state: dict, *, publish_enabled: bool) -> dict:
        state = self._plan_visuals_node(state)
        return self._run_render_publish_chain(state, publish_enabled=publish_enabled)

    def _run_render_publish_chain(self, state: dict, *, publish_enabled: bool) -> dict:
        state = self._render_article_node(state)
        return self._publish_node(state) if publish_enabled else state

    @staticmethod
    def _package_from_state(result: dict) -> ArticlePackage:
        return ArticlePackage(
            intent=result["article_intent"],
            fact_pack=dict(result.get("fact_pack") or {}),
            fact_compress=dict(result.get("fact_compress") or {}),
            section_plan=result["section_plan"],
            article_draft=result["article_draft"],
            title_plan=result["title_plan_state"],
            visual_blueprint=result["visual_blueprint_state"],
            visual_assets=result["visual_assets_state"],
            visual_diagnostics=dict(result.get("visual_diagnostics") or {}),
            article_layout=dict(result.get("article_layout") or {}),
            article_render=dict(result.get("article_render") or {}),
            article_html=str(result.get("article_html") or ""),
            wechat_result=dict(result.get("wechat_result") or {}),
            quality=dict(result.get("article_evaluation") or {}),
            draft_status=str(result.get("draft_status") or ("saved" if result.get("publish_enabled") else "not_started")),
            step_audits=dict(result.get("node_audits") or {}),
        )
