from __future__ import annotations

from typing import Any


def build_visual_asset(*, item: dict[str, Any], mode: str, payload: dict[str, Any]) -> dict[str, Any]:
    brief = dict(item.get("brief") or {})
    anchor_heading = str(item.get("anchor_heading", "") or brief.get("section", "") or "").strip()
    section_role = str(item.get("section_role", "") or "").strip()
    return {
        "placement_key": str(item.get("placement_key", "") or "").strip(),
        "anchor_heading": anchor_heading,
        "section_role": section_role,
        "type": str(brief.get("type", "") or item.get("purpose", "") or "").strip(),
        "title": str(brief.get("title", "") or "").strip(),
        "caption": str(brief.get("caption", "") or "").strip(),
        "visual_goal": str(item.get("visual_goal", "") or "").strip(),
        "visual_claim": str(item.get("visual_claim", "") or "").strip(),
        "purpose": str(item.get("purpose", "") or "").strip(),
        "placement": str(item.get("placement", "") or "").strip(),
        "mode": str(mode or item.get("mode", "") or "").strip(),
        "source_page": "",
        "origin_type": "",
        "query_source": "",
        "source_role": "",
        "page_host": "",
        "is_official_host": False,
        "brief": brief,
        "evidence_refs": [str(entry).strip() for entry in (item.get("evidence_refs") or []) if str(entry).strip()],
        "facts_to_visualize": [str(entry).strip() for entry in (item.get("facts_to_visualize") or []) if str(entry).strip()],
        **dict(payload or {}),
    }
