from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graphs.nodes.classify_node import build_classify_node
from app.graphs.nodes.plan_sections_node import build_plan_sections_node
from app.graphs.nodes.validate_plan_node import build_validate_plan_node
from app.graphs.nodes.write_article_node import build_write_article_node
from app.graphs.nodes.generate_title_node import build_generate_title_node
from app.graphs.nodes.evaluate_article_node import build_evaluate_article_node
from app.graphs.nodes.plan_visuals_node import build_plan_visuals_node
from app.graphs.nodes.render_article_node import build_render_article_node
from app.graphs.nodes.publish_node import build_publish_node


def _after_plan(state: dict) -> str:
    evaluation = dict(state.get("plan_evaluation") or {})
    if evaluation.get("passed"):
        return "write_article"
    if int(state.get("plan_attempts", 0) or 0) < 2:
        return "plan_sections"
    raise RuntimeError("plan evaluation failed: " + ", ".join(str(item) for item in evaluation.get("hard_failures", [])))


def _after_article(state: dict) -> str:
    evaluation = dict(state.get("article_evaluation") or {})
    if evaluation.get("passed"):
        return "plan_visuals"
    if int(state.get("article_attempts", 0) or 0) < 2:
        return "write_article"
    raise RuntimeError("article evaluation failed: " + ", ".join(str(item) for item in evaluation.get("hard_failures", [])))


def _after_render(state: dict):
    return "publish" if state.get("publish_enabled") else END


def compile_article_generation_graph(*, classifier_agent, section_planner_agent, plan_evaluator_agent, writer_agent, title_agent, article_evaluator_agent, visual_agent, publisher_agent, support):
    def with_progress(step_name: str, node_fn):
        def _wrapped(state: dict) -> dict:
            run = state.get("run")
            if run is not None and hasattr(support, "update_graph_progress"):
                support.update_graph_progress(run=run, status="running", active_node=step_name)
            return node_fn(state)

        return _wrapped

    graph = StateGraph(dict)
    graph.add_node("classify", with_progress("CLASSIFY", build_classify_node(classifier_agent)))
    graph.add_node("plan_sections", with_progress("PLAN_SECTIONS", build_plan_sections_node(section_planner_agent)))
    graph.add_node("validate_plan", with_progress("VALIDATE_PLAN", build_validate_plan_node(plan_evaluator_agent)))
    graph.add_node("write_article", with_progress("WRITE_ARTICLE", build_write_article_node(writer_agent)))
    graph.add_node("generate_title", with_progress("GENERATE_TITLE", build_generate_title_node(title_agent)))
    graph.add_node("evaluate_article", with_progress("EVALUATE_ARTICLE", build_evaluate_article_node(article_evaluator_agent)))
    graph.add_node("plan_visuals", with_progress("PLAN_VISUALS", build_plan_visuals_node(visual_agent, support)))
    graph.add_node("render_article", with_progress("RENDER_ARTICLE", build_render_article_node(support)))
    graph.add_node("publish", with_progress("PUBLISH", build_publish_node(publisher_agent)))

    graph.set_entry_point("classify")
    graph.add_edge("classify", "plan_sections")
    graph.add_edge("plan_sections", "validate_plan")
    graph.add_conditional_edges("validate_plan", _after_plan, {"plan_sections": "plan_sections", "write_article": "write_article"})
    graph.add_edge("write_article", "generate_title")
    graph.add_edge("generate_title", "evaluate_article")
    graph.add_conditional_edges("evaluate_article", _after_article, {"write_article": "write_article", "plan_visuals": "plan_visuals"})
    graph.add_edge("plan_visuals", "render_article")
    graph.add_conditional_edges("render_article", _after_render, {"publish": "publish", END: END})
    graph.add_edge("publish", END)
    return graph.compile()
