from __future__ import annotations

import json
from typing import Any

from app.runtime.audit import record_node_audit
from app.runtime.state_models import VisualAssetSet, VisualBlueprint
from app.services.article_variant_policy import classify_article_variant
from app.services.news_visual_policy import classify_news_visual_variant


def build_plan_visuals_node(agent, support):
    def _node(state: dict) -> dict:
        bootstrap = dict(state.get("bootstrap_context") or {})
        run = state["run"]
        fact_pack = _enrich_image_candidates(
            support=support,
            bootstrap=bootstrap,
            fact_pack=dict(state.get("fact_pack") or {}),
        )
        decision_blueprint = support.visual_strategy.build_blueprint(
            run_id=run.id,
            topic=dict(bootstrap.get("selected_topic") or {}),
            fact_pack=fact_pack,
            fact_grounding=dict(bootstrap.get("fact_grounding") or {}),
            source_structure=dict(bootstrap.get("source_structure") or {}),
            web_enrich=dict(bootstrap.get("web_enrich") or {}),
            image_candidates=list(fact_pack.get("image_candidates") or []),
            llm=support.llm,
            max_body_illustrations=support.settings.get_int("visual.body_illustration_count", 2),
        )
        compiled_blueprint = support.visual_execution_compiler.compile_blueprint(
            visual_blueprint=decision_blueprint,
            pool=str(fact_pack.get("primary_pool", "") or fact_pack.get("pool", "") or "").strip(),
            subtype=str(fact_pack.get("subtype", "") or "").strip(),
            topic=dict(bootstrap.get("selected_topic") or {}),
            fact_pack=fact_pack,
            web_enrich=dict(bootstrap.get("web_enrich") or {}),
            source_structure=dict(bootstrap.get("source_structure") or {}),
            image_candidates=list(fact_pack.get("image_candidates") or []),
            max_body_illustrations=support.settings.get_int("visual.body_illustration_count", 2),
        )
        prepared_blueprint = support.visual_fit_gate.prepare_blueprint(
            visual_blueprint=compiled_blueprint.as_dict(),
            image_candidates=list(fact_pack.get("image_candidates") or []),
        )
        prepared_blueprint_state = VisualBlueprint.from_dict(prepared_blueprint)
        crawled_assets = support.media_acquisition.acquire(
            run_id=run.id,
            visual_blueprint=prepared_blueprint,
        )
        captured_assets = support.page_capture.capture(
            run_id=run.id,
            visual_blueprint=prepared_blueprint,
        )
        generation_blueprint = _build_generation_blueprint(visual_blueprint=prepared_blueprint_state)
        generated_assets, audit = agent.generate(
            run=run,
            article_title=state["title_plan_state"].article_title,
            visual_blueprint=generation_blueprint,
            include_cover_assets=bool(state.get("include_cover_assets", True)),
            size=support.settings.get("visual.body_size", "1024*1024"),
        )
        successful_crawled_assets = [
            dict(item)
            for item in crawled_assets
            if isinstance(item, dict) and str(item.get("status", "") or "").strip() == "acquired" and str(item.get("path", "") or "").strip()
        ]
        successful_captured_assets = [
            dict(item)
            for item in captured_assets
            if isinstance(item, dict) and str(item.get("status", "") or "").strip() == "captured" and str(item.get("path", "") or "").strip()
        ]
        final_body_assets, fit_failures = support.visual_fit_gate.filter_body_assets(
            visual_blueprint=prepared_blueprint_state.as_dict(),
            body_assets=[*successful_crawled_assets, *successful_captured_assets, *list(generated_assets.body_assets or [])],
        )
        image_search_path = _resolve_image_search_path(body_assets=final_body_assets, fact_pack=fact_pack)
        visual_diagnostics = {
            "planned_item_count": len(list(prepared_blueprint_state.items or [])),
            "qualified_body_asset_count": len(final_body_assets),
            "visual_fit_failures": list(fit_failures or []),
            "omitted_by_policy": len(list(prepared_blueprint_state.items or [])) == 0,
            "image_strategy_variant": str(fact_pack.get("image_strategy_variant", "") or "").strip(),
            "article_variant": str(fact_pack.get("article_variant", "") or "standard").strip() or "standard",
            "variant_match_reasons": list(fact_pack.get("variant_match_reasons") or []),
            "variant_blockers": list(fact_pack.get("variant_blockers") or []),
            "image_search_path": image_search_path,
            "visual_source_strategy": image_search_path,
        }

        audit_payload = dict(audit or {})
        outputs = list(audit_payload.get("outputs") or [])
        outputs.insert(
            1,
            {
                "title": "runtime_image_candidates",
                "text": json.dumps(fact_pack.get("image_candidates") or [], ensure_ascii=False, indent=2),
                "language": "json",
            },
        )
        outputs.insert(
            2,
            {
                "title": "runtime_decision_visual_blueprint",
                "text": json.dumps(decision_blueprint.as_dict(), ensure_ascii=False, indent=2),
                "language": "json",
            },
        )
        outputs.insert(
            3,
            {
                "title": "runtime_compiled_visual_blueprint",
                "text": json.dumps(compiled_blueprint.as_dict(), ensure_ascii=False, indent=2),
                "language": "json",
            },
        )
        outputs.insert(
            4,
            {
                "title": "runtime_prepared_visual_blueprint",
                "text": json.dumps(prepared_blueprint, ensure_ascii=False, indent=2),
                "language": "json",
            },
        )
        outputs.insert(
            5,
            {
                "title": "runtime_crawled_visual_assets",
                "text": json.dumps(crawled_assets, ensure_ascii=False, indent=2),
                "language": "json",
            },
        )
        outputs.insert(
            6,
            {
                "title": "runtime_captured_visual_assets",
                "text": json.dumps(captured_assets, ensure_ascii=False, indent=2),
                "language": "json",
            },
        )
        outputs.insert(
            7,
            {
                "title": "runtime_visual_fit_failures",
                "text": json.dumps(fit_failures, ensure_ascii=False, indent=2),
                "language": "json",
            },
        )
        outputs.insert(
            8,
            {
                "title": "runtime_visual_diagnostics",
                "text": json.dumps(visual_diagnostics, ensure_ascii=False, indent=2),
                "language": "json",
            },
        )
        audit_payload["outputs"] = outputs
        output = dict(state)
        output.update(
            {
                "fact_pack": fact_pack,
                "visual_blueprint_state": prepared_blueprint_state,
                "visual_assets_state": VisualAssetSet(
                    body_assets=final_body_assets,
                    cover_5d=dict(generated_assets.cover_5d or {}),
                    cover_asset=dict(generated_assets.cover_asset or {}),
                ),
                "visual_diagnostics": visual_diagnostics,
                "node_audits": record_node_audit(state, "PLAN_VISUALS", audit_payload),
            }
        )
        return output

    return _node


def _enrich_image_candidates(*, support, bootstrap: dict[str, Any], fact_pack: dict[str, Any]) -> dict[str, Any]:
    topic = dict(bootstrap.get("selected_topic") or {})
    web_enrich = dict(bootstrap.get("web_enrich") or {})
    source_structure = dict(bootstrap.get("source_structure") or {})
    article_variant_info = classify_article_variant(topic=topic, fact_pack=fact_pack)
    article_variant = str(article_variant_info.get("article_variant", "standard") or "standard")
    variant_info = classify_news_visual_variant(topic=topic, fact_pack=fact_pack)
    variant = str(variant_info.get("variant", "standard_news") or "standard_news")
    merged = support.image_research.build_candidates(
        topic=topic,
        fact_pack=fact_pack,
        web_enrich=web_enrich,
        source_structure=source_structure,
    )
    updated = dict(fact_pack)
    updated["article_variant"] = article_variant
    if str(updated.get("primary_pool", "") or updated.get("pool", "") or "").strip() == "news":
        updated["image_strategy_variant"] = variant
        updated["variant_match_reasons"] = list(variant_info.get("matched_features") or [])
        updated["variant_blockers"] = list(variant_info.get("blocked_by") or [])
        updated["variant_reason"] = str(variant_info.get("reason", "") or "").strip()
    else:
        updated["image_strategy_variant"] = article_variant
        updated["variant_match_reasons"] = list(article_variant_info.get("matched_features") or [])
        updated["variant_blockers"] = list(article_variant_info.get("blocked_by") or [])
        updated["variant_reason"] = str(article_variant_info.get("reason", "") or "").strip()
    updated["image_candidates"] = [dict(item) for item in merged]
    updated["news_image_candidates"] = [
        {
            **dict(item),
            "origin": str(item.get("origin_type", "") or "").strip(),
            "context": str(item.get("context_snippet", "") or "").strip(),
            "score": int(item.get("score", 0) or 0),
            "relevance_hits": int(item.get("relevance_hits", 0) or 0),
            "source_article": str(topic.get("title", "") or "").strip(),
        }
        for item in merged
        if isinstance(item, dict)
    ][:6]
    return updated


def _resolve_image_search_path(*, body_assets: list[dict[str, Any]], fact_pack: dict[str, Any]) -> str:
    assets = [dict(item) for item in list(body_assets or []) if isinstance(item, dict)]
    article_variant = str(fact_pack.get("article_variant", "") or "standard").strip() or "standard"
    if not assets:
        return "no_image"
    if article_variant == "project_explainer":
        if any(str(item.get("mode", "") or "").strip() == "capture" for item in assets):
            return "repo_capture"
        if any(str(item.get("source_role", "") or "").strip() == "source_article_tech_visual" for item in assets):
            return "source_article"
        if any(str(item.get("source_role", "") or "").strip() == "repo_readme_or_docs_visual" for item in assets):
            return "repo_assets"
        return "none"
    if any(str(item.get("mode", "") or "").strip() == "capture" for item in assets):
        return "official_capture"
    if any(str(item.get("image_kind", "") or "").strip().lower() == "logo" for item in assets):
        return "logo_fallback"
    if any(str(item.get("source_role", "") or "").strip() == "object_official" for item in assets):
        return "primary_then_official"
    if any(str(item.get("source_role", "") or "").strip() == "primary_source" for item in assets):
        return "primary"
    return "no_image"


def _build_generation_blueprint(*, visual_blueprint: VisualBlueprint) -> VisualBlueprint:
    items = [
        dict(item)
        for item in list(visual_blueprint.items or [])
        if isinstance(item, dict) and str(item.get("mode", "") or "").strip() == "generate"
    ]
    return VisualBlueprint(
        cover_family=visual_blueprint.cover_family,
        cover_brief=dict(visual_blueprint.cover_brief or {}),
        body_policy=dict(getattr(visual_blueprint, "body_policy", {}) or {}),
        items=items,
    )
