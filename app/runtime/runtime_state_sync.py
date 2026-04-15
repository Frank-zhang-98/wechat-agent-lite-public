from __future__ import annotations

from typing import Any

from app.runtime.state_models import ArticlePackage


def apply_runtime_package_to_ctx(ctx: dict[str, Any], package: ArticlePackage) -> None:
    ctx.update(
        {
            "fact_pack": dict(package.fact_pack or {}),
            "article_intent": package.intent.as_dict(),
            "pool": package.intent.pool,
            "subtype": package.intent.subtype,
            "subtype_label": package.intent.subtype_label,
            "target_audience": package.intent.audience,
            "fact_compress": dict(package.fact_compress or {}),
            "section_plan": package.section_plan.as_dict(),
            "article_draft": package.article_draft.as_dict(),
            "article_title": package.title_plan.article_title,
            "wechat_title": package.title_plan.wechat_title,
            "title_plan": package.title_plan.as_dict(),
            "article_markdown": package.article_draft.article_markdown,
            "humanizer": dict(package.article_draft.humanizer or {}),
            "write_output_meta": dict(package.article_draft.write_output_meta or {}),
            "visual_blueprint": package.visual_blueprint.as_dict(),
            "visual_assets": package.visual_assets.as_dict(),
            "visual_diagnostics": dict(package.visual_diagnostics or {}),
            "article_layout": dict(package.article_layout or {}),
            "article_render": dict(package.article_render or {}),
            "article_html": package.article_html,
            "wechat_result": dict(package.wechat_result or {}),
            "draft_status": package.draft_status,
            "quality_score": float(package.quality.get("score", 0) or 0),
            "best_quality_score": float(package.quality.get("score", 0) or 0),
            "best_quality_title": package.title_plan.article_title,
            "quality_attempts": int(package.quality.get("attempts", 1) or 1),
            "quality_fallback_used": bool(package.quality.get("fallback_used", False)),
            "quality_scores": list(package.quality.get("scores") or []),
            "quality_warnings": list(package.quality.get("warnings") or []),
            "quality_gate_status": str(package.quality.get("status", "") or ""),
            "step_audits": dict(package.step_audits or {}),
        }
    )


def build_runtime_summary_payload(
    *,
    existing_summary: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "trigger_request": dict(ctx.get("trigger_request") or existing_summary.get("trigger_request") or {}),
        "pool_candidates": dict(ctx.get("pool_candidates") or existing_summary.get("pool_candidates") or {}),
        "pool_winners": dict(ctx.get("pool_winners") or existing_summary.get("pool_winners") or {}),
        "final_pool_selection": dict(ctx.get("final_pool_selection") or existing_summary.get("final_pool_selection") or {}),
        "selection_arbitration": dict(ctx.get("selection_arbitration") or existing_summary.get("selection_arbitration") or {}),
        "selected_topic": dict(ctx.get("selected_topic") or existing_summary.get("selected_topic") or {}),
        "top_n": list(ctx.get("top_n") or existing_summary.get("top_n") or []),
        "top_k": list(ctx.get("top_k") or existing_summary.get("top_k") or []),
        "top_k_requested": int(ctx.get("top_k_requested") or existing_summary.get("top_k_requested") or 0),
        "top_k_actual": int(ctx.get("top_k_actual") or existing_summary.get("top_k_actual") or 0),
        "source_pack": dict(ctx.get("source_pack") or existing_summary.get("source_pack") or {}),
        "source_structure": dict(ctx.get("source_structure") or existing_summary.get("source_structure") or {}),
        "web_search_plan": dict(ctx.get("web_search_plan") or existing_summary.get("web_search_plan") or {}),
        "web_enrich": dict(ctx.get("web_enrich") or existing_summary.get("web_enrich") or {}),
        "fact_grounding": dict(ctx.get("fact_grounding") or existing_summary.get("fact_grounding") or {}),
        "fact_pack": dict(ctx.get("fact_pack") or existing_summary.get("fact_pack") or {}),
        "fact_compress": dict(ctx.get("fact_compress") or existing_summary.get("fact_compress") or {}),
        "article_intent": dict(ctx.get("article_intent") or existing_summary.get("article_intent") or {}),
        "section_plan": dict(ctx.get("section_plan") or existing_summary.get("section_plan") or {}),
        "article_draft": dict(ctx.get("article_draft") or existing_summary.get("article_draft") or {}),
        "title_plan": dict(ctx.get("title_plan") or existing_summary.get("title_plan") or {}),
        "visual_blueprint": dict(ctx.get("visual_blueprint") or existing_summary.get("visual_blueprint") or {}),
        "visual_assets": dict(ctx.get("visual_assets") or existing_summary.get("visual_assets") or {}),
        "visual_diagnostics": dict(ctx.get("visual_diagnostics") or existing_summary.get("visual_diagnostics") or {}),
        "article_layout": dict(ctx.get("article_layout") or existing_summary.get("article_layout") or {}),
        "article_render": dict(ctx.get("article_render") or existing_summary.get("article_render") or {}),
        "article_html": str(ctx.get("article_html") or existing_summary.get("article_html") or ""),
        "wechat_result": dict(ctx.get("wechat_result") or existing_summary.get("wechat_result") or {}),
        "runtime_graph": dict(ctx.get("runtime_graph") or existing_summary.get("runtime_graph") or {}),
        "source_maintenance": dict(ctx.get("source_maintenance") or existing_summary.get("source_maintenance") or {}),
        "failed_logs": list(ctx.get("failed_logs") or existing_summary.get("failed_logs") or []),
        "quality_scores": list(ctx.get("quality_scores") or existing_summary.get("quality_scores") or []),
        "target_audience": str(ctx.get("target_audience") or existing_summary.get("target_audience") or ""),
    }
    for carry_key in ("redo_request", "source_run_id"):
        if carry_key in existing_summary:
            payload[carry_key] = existing_summary[carry_key]
    return payload
