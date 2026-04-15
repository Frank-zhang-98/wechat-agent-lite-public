from __future__ import annotations

import json
import math
from datetime import datetime, timezone
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.security import allow_insecure_secret_storage, has_external_encryption_key
from app.db import get_read_session, get_session
from app.core.config import CONFIG
from app.models import ConfigEntry, Run, RunStep, SourceHealthState
from app.schemas import ConfigUpdatePayload, TriggerRunPayload
from app import state
from app.runtime.facade import RuntimeFacade
from app.runtime.projections import build_run_list_item, build_run_projection, build_step_projection, extract_runtime_package
from app.services.fetch_service import FetchService
from app.services.metrics_service import get_step_timing_metrics, get_storage_metrics, get_token_metrics, get_token_overview
from app.services.model_pricing_service import get_pricing_catalog, sync_pricing_catalog
from app.services.proxy_link_service import ProxyLinkService
from app.services.article_render_service import ArticleRenderService
from app.services.settings_service import SettingsService
from app.services.source_maintenance_service import SourceMaintenanceService

router = APIRouter(prefix="/api")
RUN_LIST_SORT_ORDERS = {
    "time_desc",
    "time_asc",
    "score_desc",
    "score_asc",
    "title_asc",
    "title_desc",
    "status_priority",
    "status_reverse",
}
RUN_QUICK_FILTERS = {"all", "issues", "success", "health"}
RUN_STATUS_PRIORITY = {"failed": 0, "partial_success": 1, "running": 2, "pending": 3, "success": 4, "cancelled": 5}
_ARTICLE_RENDERER: ArticleRenderService | None = None


def _parse_json_field(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {"value": value}
    except Exception:
        return {}


def _load_run_hotspots(run_id: str) -> list[dict]:
    path = CONFIG.data_dir / "runs" / run_id / "hotspots.json"
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def _get_article_renderer() -> ArticleRenderService:
    global _ARTICLE_RENDERER
    if _ARTICLE_RENDERER is None:
        _ARTICLE_RENDERER = ArticleRenderService()
    return _ARTICLE_RENDERER


def _load_run_article_html(run: Run, summary: dict | None = None) -> str:
    summary = dict(summary or {})
    package = extract_runtime_package(summary)
    if package and str(package.article_html or "").strip():
        return str(package.article_html or "")
    article_render = summary.get("article_render") if isinstance(summary, dict) else {}
    html_path = ""
    if isinstance(article_render, dict):
        html_path = str(article_render.get("html_path", "") or "").strip()
    if html_path:
        candidate = Path(html_path)
        if candidate.exists() and candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except Exception:
                pass

    run_dir = CONFIG.data_dir / "runs" / run.id
    candidate = run_dir / "article.html"
    if candidate.exists() and candidate.is_file():
        try:
            return candidate.read_text(encoding="utf-8")
        except Exception:
            pass

    article_markdown = str(run.article_markdown or "").strip()
    if not article_markdown:
        return ""

    pool, subtype = _extract_run_semantics(summary if isinstance(summary, dict) else {})
    article_layout = summary.get("article_layout") if isinstance(summary, dict) else {}
    explicit_layout = str(article_layout.get("name", "") if isinstance(article_layout, dict) else "").strip()
    visual_assets = summary.get("visual_assets") if isinstance(summary, dict) else {}
    illustrations = (
        list(visual_assets.get("body_assets") or [])
        if isinstance(visual_assets, dict)
        else []
    )
    try:
        rendered = _get_article_renderer().render(
            article_markdown,
            article_title=str(run.article_title or "").strip(),
            pool=pool,
            subtype=subtype,
            target_audience="",
            layout_name=explicit_layout,
            illustrations=illustrations,
            run_id=run.id,
        )
    except Exception:
        return ""
    return rendered.html


def _resolve_run_asset_path(*, run_id: str, asset_path: str) -> Path:
    run_dir = (CONFIG.data_dir / "runs" / run_id).resolve()
    candidate = (run_dir / asset_path).resolve()
    try:
        candidate.relative_to(run_dir)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="asset not found") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return candidate


def _find_run_cover_path(run: Run, summary: dict | None = None) -> Path | None:
    summary = dict(summary or {})
    package = extract_runtime_package(summary)
    if package:
        cover_path = str((package.visual_assets.cover_asset or {}).get("path", "") or "").strip()
        if cover_path:
            candidate = Path(cover_path)
            if candidate.exists() and candidate.is_file():
                return candidate
    visual_assets = summary.get("visual_assets") if isinstance(summary, dict) else {}
    cover_asset = visual_assets.get("cover_asset") if isinstance(visual_assets, dict) else {}
    cover_path = ""
    if isinstance(cover_asset, dict):
        cover_path = str(cover_asset.get("path", "") or "").strip()
    if cover_path:
        candidate = Path(cover_path)
        if candidate.exists() and candidate.is_file():
            return candidate

    run_dir = CONFIG.data_dir / "runs" / run.id
    if not run_dir.exists():
        return None
    for pattern in ("cover.png", "cover.jpg", "cover.jpeg", "cover.webp"):
        candidate = run_dir / pattern
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _extract_run_semantics(summary: dict) -> tuple[str, str]:
    if not isinstance(summary, dict):
        return "", ""
    pool = str(summary.get("selected_pool", "") or summary.get("pool", "") or "").strip()
    subtype = str(summary.get("subtype", "") or "").strip()
    fact_pack = summary.get("fact_pack") if isinstance(summary.get("fact_pack"), dict) else {}
    article_layout = summary.get("article_layout") if isinstance(summary.get("article_layout"), dict) else {}
    if isinstance(fact_pack, dict):
        pool = pool or str(fact_pack.get("primary_pool", "") or fact_pack.get("pool", "") or "").strip()
        subtype = subtype or str(fact_pack.get("subtype", "") or "").strip()
    if isinstance(article_layout, dict):
        pool = pool or str(article_layout.get("pool", "") or "").strip()
        subtype = subtype or str(article_layout.get("subtype", "") or "").strip()
    return pool, subtype


def _compact_topic_preview(item: dict | None) -> dict:
    topic = dict(item or {})
    return {
        "title": str(topic.get("title", "") or "").strip(),
        "source": str(topic.get("source", "") or "").strip(),
        "url": str(topic.get("url", "") or "").strip(),
        "summary": str(topic.get("summary", "") or "").strip()[:240],
        "primary_pool": str(topic.get("primary_pool", "") or "").strip(),
        "primary_pool_label": str(topic.get("primary_pool_label", "") or "").strip(),
        "rule_score": topic.get("rule_score"),
        "final_score": topic.get("final_score"),
        "published": str(topic.get("published", "") or "").strip(),
    }


def _compact_topic_list(items: list | None) -> dict:
    topics = list(items or [])
    return {
        "count": len(topics),
        "items": [_compact_topic_preview(item) for item in topics[:5] if isinstance(item, dict)],
    }


def _compact_pool_bucket(bucket: dict | None) -> dict:
    data = dict(bucket or {})
    winner = data.get("winner")
    return {
        "pool": str(data.get("pool", "") or "").strip(),
        "pool_label": str(data.get("pool_label", "") or "").strip(),
        "status": str(data.get("status", "") or "").strip(),
        "error": str(data.get("error", "") or "").strip(),
        "fetched_count": int(data.get("fetched_count") or 0),
        "deduped_count": int(data.get("deduped_count") or 0),
        "top_n": _compact_topic_list(data.get("top_n") or []),
        "top_k": _compact_topic_list(data.get("top_k") or []),
        "top_k_requested": data.get("top_k_requested"),
        "top_k_actual": data.get("top_k_actual"),
        "winner": _compact_topic_preview(winner) if isinstance(winner, dict) else {},
    }


def _compact_source_entry(entry: dict | None) -> dict:
    item = dict(entry or {})
    content_text = str(item.get("content_text", "") or "")
    paragraphs = list(item.get("paragraphs") or [])
    images = list(item.get("images") or [])
    return {
        "url": str(item.get("url", "") or "").strip(),
        "title": str(item.get("title", "") or "").strip(),
        "summary": str(item.get("summary", "") or "").strip()[:240],
        "status": str(item.get("status", "") or "").strip(),
        "fetch_mode": str(item.get("fetch_mode", "") or "").strip(),
        "content_text_length": len(content_text),
        "paragraph_count": len(paragraphs),
        "images_count": len(images),
    }


def _compact_source_pack(pack: dict | None) -> dict:
    value = dict(pack or {})
    return {
        "primary": _compact_source_entry(value.get("primary") or {}),
        "related_count": len(value.get("related") or []),
        "related": [_compact_source_entry(item) for item in list(value.get("related") or [])[:3] if isinstance(item, dict)],
    }


def _compact_fact_grounding(payload: dict | None) -> dict:
    value = dict(payload or {})
    return {
        "hard_facts_count": len(value.get("hard_facts") or []),
        "official_facts_count": len(value.get("official_facts") or []),
        "context_facts_count": len(value.get("context_facts") or []),
        "unknowns_count": len(value.get("unknowns") or []),
        "hard_facts": list(value.get("hard_facts") or [])[:5],
        "official_facts": list(value.get("official_facts") or [])[:5],
    }


def _compact_fact_pack(payload: dict | None) -> dict:
    value = dict(payload or {})
    return {
        "primary_pool": str(value.get("primary_pool", "") or "").strip(),
        "subtype": str(value.get("subtype", "") or "").strip(),
        "subtype_label": str(value.get("subtype_label", "") or "").strip(),
        "key_points_count": len(value.get("key_points") or []),
        "implementation_steps_count": len(value.get("implementation_steps") or []),
        "code_artifacts_count": len(value.get("code_artifacts") or []),
        "coverage_checklist_count": len(value.get("coverage_checklist") or []),
        "key_points": list(value.get("key_points") or [])[:5],
    }


def _compact_fact_compress(payload: dict | None) -> dict:
    value = dict(payload or {})
    return {
        "one_sentence_summary": str(value.get("one_sentence_summary", "") or "").strip(),
        "key_mechanisms": list(value.get("key_mechanisms") or [])[:5],
        "concrete_scenarios": list(value.get("concrete_scenarios") or [])[:5],
        "risks": list(value.get("risks") or [])[:5],
        "uncertainties": list(value.get("uncertainties") or [])[:5],
    }


def _compact_visual_blueprint(payload: dict | None) -> dict:
    value = dict(payload or {})
    items = [dict(item) for item in list(value.get("items") or [])[:5] if isinstance(item, dict)]
    return {
        "cover_family": str(value.get("cover_family", "") or "").strip(),
        "cover_brief": dict(value.get("cover_brief") or {}),
        "item_count": len(value.get("items") or []),
        "items": items,
    }


def _compact_visual_assets(payload: dict | None) -> dict:
    value = dict(payload or {})
    body_assets = [dict(item) for item in list(value.get("body_assets") or [])[:5] if isinstance(item, dict)]
    return {
        "body_asset_count": len(value.get("body_assets") or []),
        "body_assets": body_assets,
        "cover_5d": dict(value.get("cover_5d") or {}),
        "cover_asset": dict(value.get("cover_asset") or {}),
    }


def _compact_visual_diagnostics(payload: dict | None) -> dict:
    value = dict(payload or {})
    return {
        "planned_item_count": int(value.get("planned_item_count") or 0),
        "qualified_body_asset_count": int(value.get("qualified_body_asset_count") or 0),
        "omitted_by_policy": bool(value.get("omitted_by_policy", False)),
        "visual_fit_failures": [dict(item) for item in list(value.get("visual_fit_failures") or [])[:5] if isinstance(item, dict)],
    }


def _compact_runtime_graph(payload: dict | None) -> dict:
    value = dict(payload or {})
    runtime_meta = dict(value.get("runtime") or {})
    article_package = dict(value.get("article_package") or {})
    intent = dict(article_package.get("intent") or {})
    fact_pack = dict(article_package.get("fact_pack") or {})
    fact_compress = dict(article_package.get("fact_compress") or {})
    section_plan = dict(article_package.get("section_plan") or {})
    article_draft = dict(article_package.get("article_draft") or {})
    title_plan = dict(article_package.get("title_plan") or {})
    visual_blueprint = dict(article_package.get("visual_blueprint") or {})
    visual_assets = dict(article_package.get("visual_assets") or {})
    return {
        "runtime": runtime_meta,
        "article_package": {
            "intent": {
                "pool": str(intent.get("pool", "") or "").strip(),
                "subtype": str(intent.get("subtype", "") or "").strip(),
                "subtype_label": str(intent.get("subtype_label", "") or "").strip(),
                "audience": str(intent.get("audience", "") or "").strip(),
                "core_angle": str(intent.get("core_angle", "") or "").strip(),
            },
            "fact_pack": {
                "primary_pool": str(fact_pack.get("primary_pool", "") or "").strip(),
                "subtype": str(fact_pack.get("subtype", "") or "").strip(),
            },
            "fact_compress": {
                "one_sentence_summary": str(fact_compress.get("one_sentence_summary", "") or "").strip(),
            },
            "section_plan": {
                "pool": str(section_plan.get("pool", "") or "").strip(),
                "section_count": len(section_plan.get("sections") or []),
            },
            "article_draft": {
                "article_markdown_length": len(str(article_draft.get("article_markdown", "") or "")),
                "h1_title": str(article_draft.get("h1_title", "") or "").strip(),
            },
            "title_plan": {
                "article_title": str(title_plan.get("article_title", "") or "").strip(),
                "wechat_title": str(title_plan.get("wechat_title", "") or "").strip(),
                "source": str(title_plan.get("source", "") or "").strip(),
            },
            "visual_blueprint": {
                "cover_family": str(visual_blueprint.get("cover_family", "") or "").strip(),
                "item_count": len(visual_blueprint.get("items") or []),
            },
            "visual_assets": {
                "body_asset_count": len(visual_assets.get("body_assets") or []),
                "has_cover_asset": bool(visual_assets.get("cover_asset")),
            },
            "visual_diagnostics": dict(article_package.get("visual_diagnostics") or {}),
            "article_layout": dict(article_package.get("article_layout") or {}),
            "article_render": dict(article_package.get("article_render") or {}),
            "article_html_length": len(str(article_package.get("article_html", "") or "")),
            "wechat_result": dict(article_package.get("wechat_result") or {}),
            "quality": dict(article_package.get("quality") or {}),
            "draft_status": str(article_package.get("draft_status", "") or "").strip(),
        },
    }


def _build_run_detail_summary(summary: dict | None) -> dict:
    value = dict(summary or {})
    compact: dict[str, object] = {}
    for key, item in value.items():
        if key == "selected_topic":
            compact[key] = _compact_topic_preview(item if isinstance(item, dict) else {})
        elif key in {"top_n", "top_k", "fetched_items"}:
            compact[key] = _compact_topic_list(item if isinstance(item, list) else [])
        elif key == "pool_candidates":
            compact[key] = {
                str(pool): _compact_pool_bucket(bucket if isinstance(bucket, dict) else {})
                for pool, bucket in dict(item or {}).items()
            }
        elif key == "pool_winners":
            compact[key] = {
                str(pool): _compact_topic_preview(bucket.get("winner") if isinstance(bucket, dict) and isinstance(bucket.get("winner"), dict) else bucket if isinstance(bucket, dict) else {})
                for pool, bucket in dict(item or {}).items()
            }
        elif key == "selection_arbitration":
            arbitration = dict(item or {})
            compact[key] = {
                "selected_pool": arbitration.get("selected_pool"),
                "selected_pool_label": arbitration.get("selected_pool_label"),
                "reason": str(arbitration.get("reason", "") or "").strip(),
                "candidate_count": len(arbitration.get("candidates") or []),
                "candidates": [_compact_topic_preview(candidate) for candidate in list(arbitration.get("candidates") or [])[:5] if isinstance(candidate, dict)],
            }
        elif key == "source_pack":
            compact[key] = _compact_source_pack(item if isinstance(item, dict) else {})
        elif key == "fact_grounding":
            compact[key] = _compact_fact_grounding(item if isinstance(item, dict) else {})
        elif key == "fact_pack":
            compact[key] = _compact_fact_pack(item if isinstance(item, dict) else {})
        elif key == "fact_compress":
            compact[key] = _compact_fact_compress(item if isinstance(item, dict) else {})
        elif key == "visual_blueprint":
            compact[key] = _compact_visual_blueprint(item if isinstance(item, dict) else {})
        elif key == "visual_assets":
            compact[key] = _compact_visual_assets(item if isinstance(item, dict) else {})
        elif key == "visual_diagnostics":
            compact[key] = _compact_visual_diagnostics(item if isinstance(item, dict) else {})
        elif key == "runtime_graph":
            compact[key] = _compact_runtime_graph(item if isinstance(item, dict) else {})
        elif key == "article_draft":
            draft = dict(item or {})
            compact[key] = {
                "article_markdown_length": len(str(draft.get("article_markdown", "") or "")),
                "h1_title": str(draft.get("h1_title", "") or "").strip(),
            }
        elif key == "article_html":
            compact[key] = {"length": len(str(item or ""))}
        else:
            compact[key] = item
    return compact


def _failed_step_name_subquery():
    return (
        select(RunStep.name)
        .where(RunStep.run_id == Run.id, RunStep.status == "failed")
        .order_by(RunStep.id.asc())
        .limit(1)
        .scalar_subquery()
    )


def _query_runs_page(
    session: Session,
    *,
    page: int,
    page_size: int,
    keyword: str = "",
    status: str = "",
    run_type: str = "",
    sort_order: str = "time_desc",
    quick_filter: str = "all",
) -> dict:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    failed_step_name = _failed_step_name_subquery()

    stmt = select(Run, failed_step_name.label("failed_step")).select_from(Run)
    keyword = str(keyword or "").strip()
    if status:
        stmt = stmt.where(Run.status == status)
    if run_type:
        stmt = stmt.where(Run.run_type == run_type)

    quick_filter = str(quick_filter or "all").strip().lower()
    if quick_filter == "issues":
        stmt = stmt.where(Run.status.in_(["failed", "partial_success"]))
    elif quick_filter == "success":
        stmt = stmt.where(Run.status == "success")
    elif quick_filter == "health":
        stmt = stmt.where(Run.run_type == "health")

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Run.id.ilike(pattern),
                Run.article_title.ilike(pattern),
                failed_step_name.ilike(pattern),
            )
        )

    total = session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()

    status_rank = case(
        *[(Run.status == key, value) for key, value in RUN_STATUS_PRIORITY.items()],
        else_=99,
    )
    sort_order = sort_order if sort_order in RUN_LIST_SORT_ORDERS else "time_desc"
    if sort_order == "time_asc":
        stmt = stmt.order_by(Run.started_at.asc(), Run.id.asc())
    elif sort_order == "score_desc":
        stmt = stmt.order_by(Run.quality_score.desc(), Run.started_at.desc(), Run.id.desc())
    elif sort_order == "score_asc":
        stmt = stmt.order_by(Run.quality_score.asc(), Run.started_at.desc(), Run.id.desc())
    elif sort_order == "title_asc":
        stmt = stmt.order_by(func.lower(func.coalesce(Run.article_title, "")).asc(), Run.started_at.desc(), Run.id.desc())
    elif sort_order == "title_desc":
        stmt = stmt.order_by(func.lower(func.coalesce(Run.article_title, "")).desc(), Run.started_at.desc(), Run.id.desc())
    elif sort_order == "status_priority":
        stmt = stmt.order_by(status_rank.asc(), Run.started_at.desc(), Run.id.desc())
    elif sort_order == "status_reverse":
        stmt = stmt.order_by(status_rank.desc(), Run.started_at.desc(), Run.id.desc())
    else:
        stmt = stmt.order_by(Run.started_at.desc(), Run.id.desc())

    offset = (page - 1) * page_size
    rows = session.execute(stmt.offset(offset).limit(page_size)).all()
    output = []
    for run, failed_step in rows:
        summary = _parse_json_field(run.summary_json)
        output.append(build_run_list_item(run=run, summary=summary, failed_step=str(failed_step or "")))

    active_run = session.execute(
        select(Run.id, Run.run_type, Run.status, Run.article_title)
        .where(Run.status.in_(["pending", "running"]))
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(1)
    ).first()
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    return {
        "runs": output,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        },
        "active_run": (
            {
                "id": active_run.id,
                "run_type": active_run.run_type,
                "status": active_run.status,
                "article_title": active_run.article_title,
            }
            if active_run
            else None
        ),
    }


def _execute_run_background(run_id: str) -> None:
    with get_session() as session:
        RuntimeFacade(session).execute_existing(run_id)


def _build_source_health_snapshot(session) -> dict:
    fetch = FetchService()
    cfg = fetch.load_sources() or {}
    try:
        states = {
            state.source_key: state
            for state in session.execute(
                select(SourceHealthState).order_by(SourceHealthState.category.asc(), SourceHealthState.source_name.asc())
            ).scalars().all()
        }
    except Exception:
        states = {}
    sources: list[dict] = []
    for category, source in SourceMaintenanceService.iter_source_definitions(cfg=cfg, target_pool=""):
        if not isinstance(source, dict):
            continue
        source_key = SourceMaintenanceService._source_key(
            category=category,
            name=str(source.get("name", "") or ""),
        )
        state = states.get(source_key)
        current_url = str(source.get("probe_url", "") or source.get("url", "") or "")
        sources.append(
            {
                "source_key": source_key,
                "category": category,
                "name": str(source.get("name", "") or ""),
                "enabled": bool(source.get("enabled", True)),
                "mode": str(source.get("mode", "rss") or "rss"),
                "weight": float(source.get("weight", 0.7) or 0.7),
                "current_url": current_url,
                "last_status": state.last_status if state else "unknown",
                "last_http_status": state.last_http_status if state else None,
                "last_error": state.last_error if state else "",
                "last_action": state.last_action if state else "",
                "last_action_reason": state.last_action_reason if state else "",
                "last_candidate_url": state.last_candidate_url if state else "",
                "consecutive_failures": int(state.consecutive_failures or 0) if state else 0,
                "total_successes": int(state.total_successes or 0) if state else 0,
                "total_failures": int(state.total_failures or 0) if state else 0,
                "last_checked_at": state.last_checked_at.isoformat() if state and state.last_checked_at else None,
                "last_success_at": state.last_success_at.isoformat() if state and state.last_success_at else None,
                "last_failure_at": state.last_failure_at.isoformat() if state and state.last_failure_at else None,
            }
        )

    active_step = session.execute(
        select(RunStep).where(RunStep.name == "SOURCE_MAINTENANCE", RunStep.status == "running").order_by(RunStep.started_at.desc())
    ).scalars().first()
    active_maintenance = None
    if active_step:
        run = session.get(Run, active_step.run_id)
        active_maintenance = {
            "run_id": active_step.run_id,
            "run_type": run.run_type if run else "",
            "started_at": active_step.started_at.isoformat() if active_step.started_at else None,
            "details": _parse_json_field(active_step.details_json),
        }

    summary = {
        "total_sources": len(sources),
        "enabled_sources": sum(1 for item in sources if item["enabled"]),
        "healthy_sources": sum(1 for item in sources if item["last_status"] == "ok"),
        "attention_sources": sum(
            1 for item in sources if item["last_status"] not in {"ok", "unknown"} or item["consecutive_failures"] > 0
        ),
    }
    return {"summary": summary, "sources": sources, "active_maintenance": active_maintenance}


@router.get("/health")
def health() -> dict:
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


@router.get("/source-health")
def source_health() -> dict:
    try:
        with get_read_session() as session:
            snapshot = _build_source_health_snapshot(session)
    except OperationalError:
        snapshot = state.source_health_snapshot or {"summary": {}, "sources": [], "active_maintenance": None}
    else:
        state.source_health_snapshot = snapshot
    return snapshot


@router.get("/settings")
def get_settings() -> dict:
    with get_session() as session:
        service = SettingsService(session)
        service.ensure_defaults()
        session.flush()
        stored_secret_count = session.execute(
            select(func.count()).select_from(ConfigEntry).where(ConfigEntry.is_secret.is_(True), ConfigEntry.value != "")
        ).scalar_one()
        return {
            "values": service.as_dict(include_secrets=False),
            "security": {
                "secrets_masked": True,
                "has_external_encryption_key": has_external_encryption_key(),
                "allow_insecure_secret_storage": allow_insecure_secret_storage(),
                "stored_secret_count": int(stored_secret_count or 0),
            },
        }


@router.put("/settings")
def update_settings(payload: ConfigUpdatePayload) -> dict:
    auto_proxy: dict[str, str] = {}
    if "proxy.share_link" in payload.values:
        share_link = (payload.values.get("proxy.share_link", "") or "").strip()
        if share_link:
            current_all_proxy = (payload.values.get("proxy.all_proxy", "") or "").strip()
            try:
                auto_proxy = ProxyLinkService.derive_settings(share_link=share_link, current_all_proxy=current_all_proxy)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"invalid proxy share link: {exc}") from exc
    with get_session() as session:
        service = SettingsService(session)
        service.ensure_defaults()
        session.flush()
        try:
            service.update_many(payload.values)
            if auto_proxy:
                service.update_many(auto_proxy)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if state.scheduler:
        state.scheduler.reload_jobs()
    return {"ok": True, "updated": len(payload.values) + len(auto_proxy), "auto_proxy": auto_proxy}


@router.post("/proxy/parse")
def parse_proxy_share_link(payload: ConfigUpdatePayload) -> dict:
    share_link = (payload.values.get("proxy.share_link", "") or "").strip()
    if not share_link:
        raise HTTPException(status_code=400, detail="proxy.share_link is required")
    current_all_proxy = (payload.values.get("proxy.all_proxy", "") or "").strip()
    try:
        auto_proxy = ProxyLinkService.derive_settings(share_link=share_link, current_all_proxy=current_all_proxy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid proxy share link: {exc}") from exc
    return {"ok": True, "auto_proxy": auto_proxy}


@router.post("/runs/trigger")
def trigger_run(payload: TriggerRunPayload, background_tasks: BackgroundTasks) -> dict:
    source_url = (payload.source_url or "").strip()
    target_pool = str(payload.target_pool or "").strip().lower()
    run_type = payload.run_type if payload.run_type in {"main", "health"} else "main"
    if target_pool and target_pool not in RuntimeFacade.TOPIC_POOLS:
        raise HTTPException(status_code=400, detail="target_pool must be one of news/github/deep_dive")
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="source_url must be a valid http(s) URL")
        if target_pool:
            raise HTTPException(status_code=400, detail="target_pool is not supported when source_url is provided")
        run_type = "manual_url"
    elif run_type == "health" and target_pool:
        raise HTTPException(status_code=400, detail="target_pool is only supported for main runs")
    with get_session() as session:
        runtime = RuntimeFacade(session)
        run = runtime.create_run(run_type=run_type, trigger_source=payload.trigger_source, status="pending")
        summary_payload: dict[str, object] = {}
        if source_url:
            summary_payload["manual_input"] = {
                "source_url": source_url,
            }
        if target_pool:
            summary_payload["trigger_request"] = {
                "target_pool": target_pool,
                "target_pool_label": runtime._topic_pool_label(target_pool),
            }
        if summary_payload:
            run.summary_json = json.dumps(summary_payload, ensure_ascii=False)
            session.flush()
        run_id = run.id
    background_tasks.add_task(_execute_run_background, run_id)
    return {"ok": True, "run_id": run_id, "status": "pending"}


@router.post("/runs/{run_id}/steps/{step_name}/redo")
def redo_run_step(run_id: str, step_name: str, background_tasks: BackgroundTasks) -> dict:
    with get_session() as session:
        try:
            run = RuntimeFacade(session).create_step_redo_run(source_run_id=run_id, step_name=step_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        run_id_new = run.id
    background_tasks.add_task(_execute_run_background, run_id_new)
    return {"ok": True, "new_run_id": run_id_new, "status": "pending"}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    with get_session() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status in {"success", "failed", "partial_success", "cancelled"}:
            return {"ok": True, "run_id": run.id, "status": run.status, "message": "run already finished"}
    state.request_run_cancel(run_id)
    return {"ok": True, "run_id": run_id, "status": "cancelling", "message": "cancel requested"}


@router.get("/runs")
def list_runs(
    limit: int | None = Query(default=None, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    run_type: str = Query(default=""),
    sort_order: str = Query(default="time_desc"),
    quick_filter: str = Query(default="all"),
) -> dict:
    with get_session() as session:
        if limit is not None and page == 1 and page_size == 20:
            page_size = limit
        normalized_quick_filter = quick_filter if quick_filter in RUN_QUICK_FILTERS else "all"
        return _query_runs_page(
            session,
            page=page,
            page_size=page_size,
            keyword=keyword,
            status=status,
            run_type=run_type,
            sort_order=sort_order,
            quick_filter=normalized_quick_filter,
        )


@router.get("/runs/{run_id}")
def get_run_detail(run_id: str) -> dict:
    with get_session() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        steps = (
            session.execute(select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.id.asc())).scalars().all()
        )
        raw_summary = _parse_json_field(run.summary_json)
        summary = raw_summary
        if isinstance(summary, dict) and not summary.get("fetched_items"):
            summary["fetched_items"] = _load_run_hotspots(run.id)
        cover_path = _find_run_cover_path(run, summary)
        article_html = _load_run_article_html(run, summary)
        projection = build_run_projection(
            run=run,
            summary=summary,
            steps=steps,
            article_html=article_html,
            cover_url=f"/api/runs/{run.id}/cover" if cover_path else "",
        )
        compact_summary = _build_run_detail_summary(summary)
        projection = dict(projection)
        projection["raw_runtime_snapshot"] = _compact_runtime_graph(projection.get("raw_runtime_snapshot") or {})
        return {
            "run": {
                "id": run.id,
                "run_type": run.run_type,
                "status": run.status,
                "trigger_source": run.trigger_source,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "error_message": run.error_message,
                "quality_score": run.quality_score,
                "quality_threshold": run.quality_threshold,
                "quality_attempts": run.quality_attempts,
                "quality_fallback_used": run.quality_fallback_used,
                "article_title": run.article_title,
                "article_markdown": run.article_markdown,
                "article_html": article_html,
                "cover_url": f"/api/runs/{run.id}/cover" if cover_path else "",
                "draft_status": run.draft_status,
                "summary": compact_summary,
                "projection": projection,
            },
            "steps": [
                {
                    **build_step_projection(run=run, step=step),
                    "details": _parse_json_field(step.details_json),
                }
                for step in steps
            ],
        }


@router.get("/runs/{run_id}/article")
def get_run_article(run_id: str) -> dict:
    with get_session() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        summary = _parse_json_field(run.summary_json)
        return {
            "run_id": run.id,
            "article_title": run.article_title,
            "article_markdown": run.article_markdown or "",
            "article_html": _load_run_article_html(run, summary),
        }


@router.get("/runs/{run_id}/assets/{asset_path:path}")
def get_run_asset(run_id: str, asset_path: str):
    with get_session() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        candidate = _resolve_run_asset_path(run_id=run.id, asset_path=asset_path)
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        return FileResponse(candidate, media_type=media_type)


@router.get("/runs/{run_id}/summary")
def get_run_summary(run_id: str) -> dict:
    with get_session() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        summary = _parse_json_field(run.summary_json)
        if isinstance(summary, dict) and not summary.get("fetched_items"):
            summary["fetched_items"] = _load_run_hotspots(run.id)
        return {
            "run_id": run.id,
            "summary": summary,
            "projection": build_run_projection(
                run=run,
                summary=summary,
                steps=session.execute(select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.id.asc())).scalars().all(),
                article_html=_load_run_article_html(run, summary),
                cover_url=f"/api/runs/{run.id}/cover" if _find_run_cover_path(run, summary) else "",
            ),
        }


@router.get("/runs/{run_id}/steps/{step_id}")
def get_run_step_detail(run_id: str, step_id: int) -> dict:
    with get_session() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        step = session.get(RunStep, step_id)
        if not step or step.run_id != run.id:
            raise HTTPException(status_code=404, detail="step not found")
        summary = _parse_json_field(run.summary_json)
        return {
            "run_id": run.id,
            "step": {
                **build_step_projection(run=run, step=step),
                "details": _parse_json_field(step.details_json),
            },
        }


@router.get("/runs/{run_id}/cover")
def get_run_cover(run_id: str):
    with get_session() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        summary = _parse_json_field(run.summary_json)
        cover_path = _find_run_cover_path(run, summary)
        if not cover_path:
            raise HTTPException(status_code=404, detail="cover not found")
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(cover_path.suffix.lower(), "application/octet-stream")
        return FileResponse(cover_path, media_type=media_type)


@router.get("/metrics/storage")
def storage_metrics() -> dict:
    return get_storage_metrics()


@router.get("/metrics/tokens")
def token_metrics(days: int = Query(default=7, ge=1, le=365)) -> dict:
    with get_session() as session:
        return get_token_metrics(session, days=days)


@router.get("/metrics/tokens/overview")
def token_overview() -> dict:
    with get_session() as session:
        return get_token_overview(session)


@router.get("/metrics/steps")
def step_metrics(days: int = Query(default=7, ge=1, le=365)) -> dict:
    with get_session() as session:
        return get_step_timing_metrics(session, days=days)


@router.get("/pricing")
def pricing_status() -> dict:
    catalog = get_pricing_catalog(auto_sync=True)
    return {"meta": catalog.get("meta", {}), "rules": catalog.get("rules", {})}


@router.post("/pricing/sync")
def pricing_sync() -> dict:
    catalog = sync_pricing_catalog()
    active = catalog or get_pricing_catalog(auto_sync=False)
    return {"ok": catalog is not None, "meta": active.get("meta", {})}


@router.post("/mail/test")
def mail_test() -> dict:
    with get_session() as session:
        service = SettingsService(session)
        service.ensure_defaults()
        mail = RuntimeFacade(session).mail
        subject_prefix = service.get("mail.subject_prefix", "[wechat-agent-lite]")
        subject = f"{subject_prefix} SMTP 测试邮件"
        html_body = (
            "<html><body style='font-family:Arial,\"Microsoft YaHei\",sans-serif;'>"
            "<h3>SMTP 测试成功</h3>"
            "<p>这是一封来自 wechat-agent-lite 控制台的测试邮件。</p>"
            "<p>如果你看到这封邮件，说明当前 SMTP 配置至少可以完成一次发送。</p>"
            "</body></html>"
        )
        try:
            result = mail.send_test(subject=subject, html_body=html_body)
        except Exception as exc:
            result = {"sent": False, "reason": str(exc)}
        return {"ok": bool(result.get("sent")), "result": result}
