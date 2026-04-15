from __future__ import annotations

import re
from typing import Any

from app.runtime.state_models import VisualBlueprint


class VisualFitGate:
    GENERATE_ALLOWED_TYPES = {
        "comparison_card",
        "comparison_infographic",
        "process_explainer_infographic",
        "system_layers_infographic",
        "workflow_diagram",
        "architecture_diagram",
    }

    def prepare_blueprint(self, *, visual_blueprint: VisualBlueprint | dict[str, Any], image_candidates: list[dict[str, Any]]) -> dict[str, Any]:
        blueprint = self._as_blueprint(visual_blueprint)
        prepared_items: list[dict[str, Any]] = []
        for item in list(blueprint.items or []):
            if not isinstance(item, dict):
                continue
            current = dict(item)
            preferred_mode = str(current.get("preferred_mode", "") or current.get("mode", "") or "none").strip().lower()
            if preferred_mode in {"", "none"}:
                continue
            if preferred_mode == "acquire":
                ranked = self._rank_candidates(item=current, image_candidates=image_candidates)
                constraints = dict(current.get("constraints") or {})
                if ranked:
                    constraints["candidate_image_urls"] = [str(candidate.get("url", "") or "").strip() for candidate in ranked]
                    constraints["candidate_metadata"] = [dict(candidate) for candidate in ranked]
                else:
                    constraints.pop("candidate_image_urls", None)
                    constraints.pop("candidate_metadata", None)
                current["constraints"] = constraints
                current["mode"] = "crawl"
            elif preferred_mode == "capture":
                capture_targets = [dict(entry) for entry in (dict(current.get("constraints") or {}).get("capture_targets") or []) if isinstance(entry, dict)]
                current["constraints"] = {**dict(current.get("constraints") or {}), "capture_targets": capture_targets} if capture_targets else {}
                current["mode"] = "capture"
            elif preferred_mode == "generate":
                if not self._can_generate(item=current):
                    continue
                current["mode"] = "generate"
            else:
                continue
            prepared_items.append(current)
        return VisualBlueprint(
            cover_family=blueprint.cover_family,
            cover_brief=dict(blueprint.cover_brief or {}),
            body_policy=dict(blueprint.body_policy or {}),
            items=prepared_items,
        ).as_dict()

    def filter_body_assets(
        self,
        *,
        visual_blueprint: VisualBlueprint | dict[str, Any],
        body_assets: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        blueprint = self._as_blueprint(visual_blueprint)
        item_map = {
            str(item.get("placement_key", "") or "").strip(): dict(item)
            for item in list(blueprint.items or [])
            if isinstance(item, dict)
        }
        accepted: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for asset in list(body_assets or []):
            if not isinstance(asset, dict):
                continue
            placement_key = str(asset.get("placement_key", "") or "").strip()
            item = item_map.get(placement_key, {})
            if not self._asset_has_layout_anchor(asset=asset):
                failures.append({"placement_key": placement_key, "reason": "layout_fit_failed"})
                continue
            mode = str(asset.get("mode", "") or "").strip().lower()
            if mode == "generate" and not self._can_generate(item=item):
                failures.append({"placement_key": placement_key, "reason": "generate_not_allowed"})
                continue
            if mode == "generate" and not str(asset.get("visual_goal", "") or "").strip():
                failures.append({"placement_key": placement_key, "reason": "missing_visual_goal"})
                continue
            if mode in {"crawl", "capture"}:
                provenance_score = int(asset.get("provenance_score", item.get("provenance_score", 0)) or 0)
                if provenance_score and provenance_score < 45:
                    failures.append({"placement_key": placement_key, "reason": "low_provenance"})
                    continue
            accepted.append(asset)
        return accepted, failures

    @staticmethod
    def _as_blueprint(value: VisualBlueprint | dict[str, Any]) -> VisualBlueprint:
        if isinstance(value, VisualBlueprint):
            return value
        return VisualBlueprint.from_dict(value if isinstance(value, dict) else {})

    def _rank_candidates(self, *, item: dict[str, Any], image_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked: list[tuple[int, dict[str, Any]]] = []
        anchor = str(item.get("anchor_heading", "") or item.get("section_role", "") or "").strip()
        query_text = " ".join(
            [
                anchor,
                str(item.get("visual_goal", "") or "").strip(),
                str(item.get("visual_claim", "") or "").strip(),
                " ".join(str(entry).strip() for entry in (item.get("facts_to_visualize") or []) if str(entry).strip()),
                str((item.get("subject_ref") or {}).get("name", "") or "").strip(),
            ]
        ).strip()
        allowed_families = {str(entry).strip() for entry in (item.get("allowed_families") or []) if str(entry).strip()}
        constraints = dict(item.get("constraints") or {})
        source_role_order = [str(entry).strip() for entry in (constraints.get("source_role_order") or []) if str(entry).strip()]
        source_role_rank = {role: len(source_role_order) - index for index, role in enumerate(source_role_order)}
        allow_logo_fallback = bool(constraints.get("allow_logo_fallback", False))
        for candidate in image_candidates:
            if not isinstance(candidate, dict):
                continue
            if self._reject_candidate_for_item(item=item, candidate=candidate):
                continue
            source_role = str(candidate.get("source_role", "") or "").strip()
            image_kind = str(candidate.get("image_kind", "") or "").strip().lower()
            if source_role_order and source_role not in source_role_order:
                continue
            if image_kind == "logo" and source_role_order and source_role != "object_official":
                continue
            if image_kind == "logo" and source_role_order and not allow_logo_fallback:
                continue
            semantic_fit = self._semantic_score(query_text=query_text, candidate=candidate)
            evidence_fit = int(candidate.get("provenance_score", 0) or 0)
            layout_fit = 80 if anchor else 20
            total = semantic_fit + evidence_fit + layout_fit + source_role_rank.get(source_role, 0) * 12
            if evidence_fit < 45:
                continue
            if allowed_families and "news_photo" not in allowed_families and image_kind == "photo":
                total += 4
            if image_kind == "logo":
                total -= 18
            if source_role in {"source_article_tech_visual", "repo_readme_or_docs_visual"}:
                if image_kind in {"diagram", "screenshot"}:
                    total += 24
                if image_kind == "photo":
                    total -= 24
            ranked.append((total, dict(candidate)))
        ranked.sort(key=lambda entry: (-entry[0], entry[1].get("url", "")))
        return [entry[1] for entry in ranked[:3]]

    def _semantic_score(self, *, query_text: str, candidate: dict[str, Any]) -> int:
        query_tokens = self._tokens(query_text)
        candidate_tokens = self._tokens(
            " ".join(
                [
                    str(candidate.get("alt", "") or ""),
                    str(candidate.get("caption", "") or ""),
                    str(candidate.get("context_snippet", "") or ""),
                    str(candidate.get("source_page", "") or ""),
                ]
            )
        )
        exact_overlap = len(query_tokens & candidate_tokens)
        partial_overlap = 0
        for query_token in query_tokens:
            for candidate_token in candidate_tokens:
                if query_token == candidate_token:
                    continue
                if query_token in candidate_token or candidate_token in query_token:
                    partial_overlap += 1
                    break
        return min(100, exact_overlap * 18 + partial_overlap * 10 + int(candidate.get("score", 0) or 0))

    def _reject_candidate_for_item(self, *, item: dict[str, Any], candidate: dict[str, Any]) -> bool:
        image_kind = str(candidate.get("image_kind", "") or "").strip().lower()
        intent_kind = str(item.get("intent_kind", "") or "").strip().lower()
        subject_ref = dict(item.get("subject_ref") or {})
        subject_kind = str(subject_ref.get("kind", "") or "").strip().lower()
        preferred_mode = str(item.get("preferred_mode", "") or item.get("mode", "") or "").strip().lower()
        if preferred_mode == "generate":
            return True
        if image_kind == "logo":
            return not (intent_kind == "reference" and subject_kind in {"company", "product", "project"})
        if image_kind == "portrait":
            return not (intent_kind == "reference" and subject_kind == "person")
        return False

    def _can_generate(self, *, item: dict[str, Any]) -> bool:
        if str(item.get("intent_kind", "") or "").strip().lower() != "explanatory":
            return False
        families = {str(entry).strip() for entry in (item.get("allowed_families") or []) if str(entry).strip()}
        visual_type = str((item.get("brief") or {}).get("type", "") or item.get("purpose", "") or "").strip()
        if visual_type == "news_photo":
            return False
        if families and visual_type and visual_type not in families:
            return False
        return visual_type in self.GENERATE_ALLOWED_TYPES

    @staticmethod
    def _asset_has_layout_anchor(*, asset: dict[str, Any]) -> bool:
        return bool(
            str(asset.get("anchor_heading", "") or "").strip()
            or str(asset.get("section_role", "") or "").strip()
        )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9@._/-]{2,}|[\u4e00-\u9fff]{2,8}", str(text or ""))
            if token.strip()
        }
