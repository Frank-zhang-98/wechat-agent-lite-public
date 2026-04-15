from __future__ import annotations

import html
import ast
import json
import re
from typing import Any

from app.models import Run, RunStep
from app.runtime.state_models import ArticlePackage

RUNTIME_EXPECTED_STEPS = [
    "CLASSIFY",
    "PLAN_SECTIONS",
    "VALIDATE_PLAN",
    "WRITE_ARTICLE",
    "GENERATE_TITLE",
    "EVALUATE_ARTICLE",
    "PLAN_VISUALS",
    "RENDER_ARTICLE",
    "PUBLISH",
]

RUNTIME_REDO_CONFIGS = {
    "WRITE_ARTICLE": {"redo_chain": "to_end"},
    "GENERATE_TITLE": {"redo_chain": "to_end"},
    "PLAN_VISUALS": {"redo_chain": "to_end"},
    "RENDER_ARTICLE": {"redo_chain": "to_end"},
    "PUBLISH": {"redo_chain": "single_step"},
}

TERMINAL_RUN_STATUSES = {"success", "failed", "partial_success", "cancelled"}

STEP_LABELS = {
    "CLASSIFY": "Classify",
    "PLAN_SECTIONS": "Plan Sections",
    "VALIDATE_PLAN": "Validate Plan",
    "WRITE_ARTICLE": "Write Article",
    "GENERATE_TITLE": "Generate Title",
    "EVALUATE_ARTICLE": "Evaluate Article",
    "PLAN_VISUALS": "Plan Visuals",
    "RENDER_ARTICLE": "Render Article",
    "PUBLISH": "Publish",
    "HEALTH_CHECK": "Health Check",
    "SOURCE_MAINTENANCE": "Source Maintenance",
    "FETCH": "Fetch",
    "DEDUP": "Dedup",
    "RULE_SCORE": "Rule Score",
    "RERANK": "Rerank",
    "SELECT": "Select",
    "PRESELECT_NEWS": "Preselect News",
    "PRESELECT_GITHUB": "Preselect GitHub",
    "PRESELECT_DEEP_DIVE": "Preselect Deep Dive",
    "FINAL_SELECT": "Final Select",
    "SOURCE_ENRICH": "Source Enrich",
    "SOURCE_STRUCTURE": "Source Structure",
    "WEB_SEARCH_PLAN": "Web Search Plan",
    "WEB_SEARCH_FETCH": "Web Search Fetch",
    "FACT_GROUNDING": "Fact Grounding",
    "FACT_PACK": "Fact Pack",
    "FACT_COMPRESS": "Fact Compress",
    "WRITE": "Write",
    "HALLUCINATION_CHECK": "Hallucination Check",
    "QUALITY_CHECK": "Quality Check",
}


def get_runtime_snapshot(summary: dict[str, Any]) -> dict[str, Any]:
    value = summary.get("runtime_graph")
    return dict(value) if isinstance(value, dict) else {}


def extract_runtime_package(summary: dict[str, Any]) -> ArticlePackage | None:
    snapshot = get_runtime_snapshot(summary)
    article_package = snapshot.get("article_package")
    if not isinstance(article_package, dict):
        return None
    try:
        return ArticlePackage.from_dict(article_package)
    except Exception:
        return None


def build_step_projection(*, run: Run, step: RunStep) -> dict[str, Any]:
    step_name = str(step.name or "").strip().upper()
    redo_supported = bool(
        str(run.status or "") in TERMINAL_RUN_STATUSES
        and step_name in RUNTIME_REDO_CONFIGS
    )
    redo_cfg = RUNTIME_REDO_CONFIGS.get(step_name, {})
    return {
        "id": step.id,
        "name": step.name,
        "label": format_step_name(step.name),
        "status": step.status,
        "retry_count": step.retry_count,
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "finished_at": step.finished_at.isoformat() if step.finished_at else None,
        "duration_ms": step.duration_ms,
        "error_message": step.error_message,
        "redo_supported": redo_supported,
        "redo_label": "Redo from this step",
        "redo_chain": str(redo_cfg.get("redo_chain") or "unsupported"),
    }


def build_run_projection(
    *,
    run: Run,
    summary: dict[str, Any],
    steps: list[RunStep],
    article_html: str,
    cover_url: str,
) -> dict[str, Any]:
    package = extract_runtime_package(summary)
    snapshot = get_runtime_snapshot(summary)
    runtime_meta = dict(snapshot.get("runtime") or {})
    selected_topic = dict(summary.get("selected_topic") or {})
    trigger_request = dict(summary.get("trigger_request") or {})
    pool_candidates = dict(summary.get("pool_candidates") or {})
    pool_winners = dict(summary.get("pool_winners") or {})
    final_pool_selection = dict(summary.get("final_pool_selection") or {})

    if package:
        selected_pool = str(final_pool_selection.get("selected_pool", "") or package.intent.pool).strip()
        subtype = package.intent.subtype
        subtype_label = package.intent.subtype_label
        article_markdown = package.article_draft.article_markdown
        resolved_article_html = article_html or package.article_html
        target_audience = package.intent.audience
        core_angle = package.intent.core_angle
        summary_sections = [
            _topic_section(selected_topic),
            {
                "title": "Intent",
                "keyvals": [
                    {"label": "Pool", "value": package.intent.pool or "-"},
                    {"label": "Selected Pool", "value": selected_pool or "-"},
                    {"label": "Subtype", "value": subtype_label or subtype or "-"},
                    {"label": "Audience", "value": target_audience or "-"},
                    {"label": "Core Angle", "value": _format_summary_value(core_angle) or "-"},
                    {"label": "Target Pool", "value": trigger_request.get("target_pool_label") or "-"},
                    {"label": "Graph Node", "value": runtime_meta.get("active_graph_node") or "-"},
                ],
            },
            {
                "title": "Pool Winners",
                "entries": [
                    {
                        "title": str(item.get("winner", {}).get("title", "") or item.get("title", "") or pool_name),
                        "subtitle": str(item.get("winner", {}).get("summary", "") or item.get("error", "") or ""),
                        "meta": [
                            f"Pool: {item.get('pool_label', pool_name)}",
                            f"Status: {item.get('status', '-')}",
                            _topk_meta(item),
                        ],
                    }
                    for pool_name, item in sorted(pool_candidates.items())
                ],
            },
            {
                "title": "Section Plan",
                "entries": [
                    {
                        "title": section.heading_hint or section.role or "-",
                        "subtitle": section.goal or "",
                        "meta": [f"Role: {section.role or '-'}"],
                    }
                    for section in package.section_plan.sections
                ],
            },
            {
                "title": "Outputs",
                "keyvals": [
                    {"label": "Article Title", "value": package.title_plan.article_title or "-"},
                    {"label": "WeChat Title", "value": package.title_plan.wechat_title or "-"},
                    {"label": "Draft Status", "value": package.draft_status or "-"},
                    {"label": "Quality Score", "value": package.quality.get("score", 0) or 0},
                    {"label": "Cover", "value": "generated" if cover_url else "missing"},
                    {"label": "Body Illustrations", "value": len(package.visual_assets.body_assets or [])},
                    {"label": "Body Visual Status", "value": package.article_render.get("visual_body_result", "-") or "-"},
                    {"label": "Inserted Illustrations", "value": package.article_render.get("inserted_illustration_count", 0) or 0},
                    {"label": "Qualified Body Assets", "value": package.article_render.get("qualified_body_asset_count", 0) or 0},
                ],
            },
        ]
    else:
        fact_pack = dict(summary.get("fact_pack") or {})
        fact_compress = dict(summary.get("fact_compress") or {})
        selected_pool = str(
            final_pool_selection.get("selected_pool", "")
            or summary.get("selected_pool", "")
            or selected_topic.get("primary_pool", "")
            or fact_pack.get("primary_pool", "")
            or runtime_meta.get("pool", "")
        ).strip()
        subtype = str(summary.get("subtype", "") or fact_pack.get("subtype", "") or runtime_meta.get("subtype", "") or "").strip()
        subtype_label = str(
            summary.get("subtype_label", "")
            or fact_pack.get("subtype_label", "")
            or runtime_meta.get("subtype_label", "")
            or ""
        ).strip()
        article_markdown = str(run.article_markdown or "").strip()
        resolved_article_html = article_html
        summary_sections = [
            _topic_section(selected_topic),
            {
                "title": "Runtime Progress",
                "keyvals": [
                    {"label": "Selected Pool", "value": selected_pool or "-"},
                    {"label": "Subtype", "value": subtype_label or subtype or "-"},
                    {"label": "Target Pool", "value": trigger_request.get("target_pool_label") or "-"},
                    {"label": "Graph Status", "value": runtime_meta.get("graph_status") or "-"},
                    {"label": "Active Graph Node", "value": runtime_meta.get("active_graph_node") or "-"},
                    {"label": "Summary", "value": fact_compress.get("one_sentence_summary", "") or "-"},
                ],
            },
            {
                "title": "Pool Winners",
                "entries": [
                    {
                        "title": str(item.get("winner", {}).get("title", "") or item.get("title", "") or pool_name),
                        "subtitle": str(item.get("winner", {}).get("summary", "") or item.get("error", "") or ""),
                        "meta": [
                            f"Pool: {item.get('pool_label', pool_name)}",
                            f"Status: {item.get('status', '-')}",
                            _topk_meta(item),
                        ],
                    }
                    for pool_name, item in sorted(pool_candidates.items())
                ],
            },
        ]

    return {
        "source": "runtime",
        "expected_steps": list(RUNTIME_EXPECTED_STEPS),
        "selected_pool": selected_pool,
        "subtype": subtype,
        "subtype_label": subtype_label,
        "article_markdown": article_markdown,
        "article_html": resolved_article_html,
        "cover_url": cover_url,
        "summary_sections": summary_sections,
        "pool_candidates": pool_candidates,
        "pool_winners": pool_winners,
        "final_pool_selection": final_pool_selection,
        "active_graph_node": str(runtime_meta.get("active_graph_node", "") or ""),
        "graph_status": str(runtime_meta.get("graph_status", "") or ""),
        "raw_runtime_snapshot": snapshot,
    }


def build_run_list_item(*, run: Run, summary: dict[str, Any], failed_step: str) -> dict[str, Any]:
    package = extract_runtime_package(summary)
    if package:
        subtype = package.intent.subtype
        subtype_label = package.intent.subtype_label
        selected_pool = str((summary.get("final_pool_selection") or {}).get("selected_pool", "") or package.intent.pool).strip()
        selection_reason_preview = (
            str((summary.get("selected_topic") or {}).get("selection_reason", "") or "").strip()
            or str(package.fact_compress.get("one_sentence_summary", "") or "").strip()
        )
    else:
        fact_pack = dict(summary.get("fact_pack") or {})
        subtype = str(summary.get("subtype", "") or fact_pack.get("subtype", "") or "").strip()
        subtype_label = str(summary.get("subtype_label", "") or fact_pack.get("subtype_label", "") or "").strip()
        selected_pool = str(
            (summary.get("final_pool_selection") or {}).get("selected_pool", "")
            or (summary.get("selected_topic") or {}).get("primary_pool", "")
            or fact_pack.get("primary_pool", "")
            or ""
        ).strip()
        selection_reason_preview = _selection_preview(summary)
    return {
        "id": run.id,
        "run_type": run.run_type,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "quality_score": run.quality_score,
        "quality_attempts": run.quality_attempts,
        "quality_fallback_used": run.quality_fallback_used,
        "article_title": run.article_title,
        "draft_status": run.draft_status,
        "selected_pool": selected_pool,
        "subtype": subtype,
        "subtype_label": subtype_label,
        "failed_step": str(failed_step or ""),
        "selection_reason_preview": selection_reason_preview[:160],
    }


def _topic_section(selected_topic: dict[str, Any]) -> dict[str, Any]:
    if not selected_topic:
        return {"title": "Current Topic", "entries": []}
    return {
        "title": "Current Topic",
        "entries": [
            {
                "title": str(selected_topic.get("title", "") or "-"),
                "subtitle": _clean_summary_text(selected_topic.get("summary", "")),
                "meta": [
                    f"Source: {selected_topic.get('source', '-') or '-'}",
                    f"Pool: {selected_topic.get('primary_pool_label', '-') or '-'}",
                ],
                "url": str(selected_topic.get("url", "") or ""),
            }
        ],
    }


def _clean_summary_text(value: Any, *, max_length: int = 320) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}…"


def _format_summary_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, tuple, set)):
        parts = [_clean_summary_text(item, max_length=120) for item in value]
        return "；".join(part for part in parts if part)
    text = _clean_summary_text(value, max_length=600)
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except Exception:
            try:
                parsed = ast.literal_eval(text)
            except Exception:
                parsed = None
        if isinstance(parsed, list):
            return _format_summary_value(parsed)
    return text


def _selection_preview(summary: dict[str, Any]) -> str:
    selected_topic = dict(summary.get("selected_topic") or {})
    top_k = list(summary.get("top_k") or [])
    fact_compress = dict(summary.get("fact_compress") or {})
    selection_arbitration = dict(summary.get("selection_arbitration") or {})
    selected_pool_label = str(selection_arbitration.get("selected_pool_label", "") or "").strip()
    arbitration_reason = str(selection_arbitration.get("reason", "") or "").strip()
    arbitration_preview = f"[{selected_pool_label}] {arbitration_reason}" if selected_pool_label and arbitration_reason else arbitration_reason
    for text in [
        arbitration_preview,
        str(selected_topic.get("selection_reason", "") or "").strip(),
        str(selected_topic.get("rerank_reason", "") or "").strip(),
        str((top_k[0] or {}).get("selection_reason", "") if top_k else "").strip(),
        str((top_k[0] or {}).get("rerank_reason", "") if top_k else "").strip(),
        str(fact_compress.get("one_sentence_summary", "") or "").strip(),
    ]:
        if text:
            return text
    return ""


def _topk_meta(item: dict[str, Any]) -> str:
    requested = item.get("top_k_requested")
    actual = item.get("top_k_actual")
    if requested is None and actual is None:
        actual = len(item.get("top_k") or [])
        requested = actual
    return f"TopK: {actual or 0}/{requested or 0}"


def format_step_name(name: str) -> str:
    return STEP_LABELS.get(str(name or "").strip(), str(name or "-").strip() or "-")
