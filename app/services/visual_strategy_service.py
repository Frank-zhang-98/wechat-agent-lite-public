from __future__ import annotations

import json
import re
from typing import Any

from app.runtime.state_models import VisualBlueprint
from app.services.article_variant_policy import detect_article_variant
from app.services.llm_gateway import LLMGateway
from app.services.localization_service import LocalizationService
from app.services.news_visual_policy import classify_news_visual_variant


class VisualStrategyService:
    SUBJECT_KEYS = (
        "person_subject",
        "company_subject",
        "product_subject",
        "project_subject",
        "event_subject",
        "page_subject",
        "mechanism_subject",
    )
    PRIORITY_KEYS = ("high", "medium", "low", "disabled")
    PRIORITY_VALUE = {"disabled": 0, "low": 1, "medium": 2, "high": 3}
    INTENT_KEYS = ("reference", "evidence", "explanatory", "none")
    MODE_KEYS = ("acquire", "capture", "generate", "none")

    def build_blueprint(
        self,
        *,
        run_id: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_grounding: dict[str, Any],
        source_structure: dict[str, Any],
        web_enrich: dict[str, Any] | None = None,
        image_candidates: list[dict[str, Any]] | None,
        llm: LLMGateway,
        max_body_illustrations: int = 2,
    ) -> VisualBlueprint:
        pool, subtype = self._resolve_article_semantics(fact_pack)
        news_variant = str(classify_news_visual_variant(topic=topic, fact_pack=fact_pack).get("variant", "standard_news"))
        article_variant = str(fact_pack.get("article_variant", "") or "").strip() or str(
            detect_article_variant(topic=topic, fact_pack=fact_pack) or "standard"
        )
        strategy_variant = news_variant if pool == "news" else article_variant
        resolved_max = self._resolve_max_body_illustrations(
            pool=pool,
            subtype=subtype,
            requested=max_body_illustrations,
        )
        body_policy = self._build_body_policy(
            pool=pool,
            subtype=subtype,
            variant=strategy_variant,
            article_variant=article_variant,
            max_body_illustrations=resolved_max,
        )
        prompt = self._build_blueprint_prompt(
            topic=topic,
            fact_pack=fact_pack,
            fact_grounding=fact_grounding,
            source_structure=source_structure,
            image_candidates=list(image_candidates or []),
            body_policy=body_policy,
            max_body_illustrations=resolved_max,
            variant=strategy_variant,
            article_variant=article_variant,
        )
        result = llm.call(run_id, "VISUAL_STRATEGY", "decision", prompt, temperature=0.2)
        blueprint = self._parse_blueprint(
            result.text,
            pool=pool,
            subtype=subtype,
            body_policy=body_policy,
            max_body_illustrations=resolved_max,
        ) or self._fallback_blueprint(
            topic=topic,
            fact_pack=fact_pack,
            pool=pool,
            subtype=subtype,
            body_policy=body_policy,
            max_body_illustrations=resolved_max,
        )
        return self._apply_pool_blueprint_policy(
            blueprint=blueprint,
            topic=topic,
            fact_pack=fact_pack,
            web_enrich=dict(web_enrich or {}),
            pool=pool,
            subtype=subtype,
            image_candidates=list(image_candidates or []),
            max_body_illustrations=resolved_max,
        )

    def build_cover_prompt_request(
        self,
        *,
        article_title: str,
        strategy: dict[str, Any],
        cover_5d: dict[str, Any],
    ) -> str:
        brief = dict(strategy.get("cover_brief") or {})
        must_show = LocalizationService.localize_visual_items(brief.get("must_show") or [])
        must_avoid = LocalizationService.localize_visual_items(brief.get("must_avoid") or [])
        subject_hint = LocalizationService.localize_visual_text(str(brief.get("subject_hint", "") or "").strip())
        scene_hint = LocalizationService.localize_visual_text(str(brief.get("scene_hint", "") or "").strip())
        mood_hint = LocalizationService.localize_visual_text(str(brief.get("mood_hint", "") or "").strip())
        title_safe_zone = str(brief.get("title_safe_zone", "left_bottom") or "left_bottom").strip()
        return (
            "Generate a concise Chinese image prompt for a WeChat article cover. "
            "Do not place readable text, logo, or watermark inside the image. "
            "Leave clean negative space for a later title overlay.\n"
            f"Cover family: {strategy.get('cover_family', 'structure')}\n"
            f"Article title: {LocalizationService.localize_visual_text(article_title)}\n"
            f"Cover scores: {json.dumps(cover_5d, ensure_ascii=False)}\n"
            f"Main claim: {LocalizationService.localize_visual_text(str(brief.get('main_claim', '') or ''))}\n"
            f"Subject hint: {subject_hint or 'clean technical focal subject'}\n"
            f"Scene hint: {scene_hint or 'clean technology-themed environment'}\n"
            f"Mood hint: {mood_hint or 'professional, calm, credible'}\n"
            f"Title safe zone: {title_safe_zone}\n"
            f"Must show: {json.dumps(must_show, ensure_ascii=False)}\n"
            f"Must avoid: {json.dumps(must_avoid, ensure_ascii=False)}"
        )

    def build_body_prompt_request(self, *, article_title: str, item: dict[str, Any]) -> str:
        brief = dict(item.get("brief") or {})
        must_show = LocalizationService.localize_visual_items(brief.get("must_show") or item.get("must_show") or [])
        must_avoid = LocalizationService.localize_visual_items(brief.get("must_avoid") or item.get("must_avoid") or [])
        return (
            "Generate a concise Chinese image prompt for an inline article illustration. "
            "This is an information-focused inline visual, not a cover. "
            "Do not include readable text, logos, or UI screenshots unless explicitly required.\n"
            f"Article title: {LocalizationService.localize_visual_text(article_title)}\n"
            f"Purpose: {item.get('purpose', '')}\n"
            f"Section: {LocalizationService.localize_visual_text(str(item.get('section_role', '') or brief.get('section', '') or '').strip())}\n"
            f"Brief: {json.dumps(brief, ensure_ascii=False)}\n"
            f"Must show: {json.dumps(must_show, ensure_ascii=False)}\n"
            f"Must avoid: {json.dumps(must_avoid, ensure_ascii=False)}"
        )

    @staticmethod
    def _resolve_max_body_illustrations(*, pool: str = "", subtype: str = "", requested: int = 0) -> int:
        return min(max(0, int(requested or 0)), 2)

    @staticmethod
    def _resolve_article_semantics(fact_pack: dict[str, Any]) -> tuple[str, str]:
        pool = str(fact_pack.get("primary_pool", "") or fact_pack.get("pool", "") or "").strip()
        subtype = str(fact_pack.get("subtype", "") or "").strip()
        if not subtype and pool == "news":
            subtype = "industry_news"
        elif not subtype and pool == "github":
            subtype = "repo_recommendation"
        elif not subtype:
            subtype = "technical_walkthrough"
        return pool, subtype

    @classmethod
    def _build_body_policy(
        cls,
        *,
        pool: str,
        subtype: str,
        variant: str = "",
        article_variant: str = "standard",
        max_body_illustrations: int,
    ) -> dict[str, Any]:
        normalized_pool = str(pool or "").strip()
        prefer_mode = "acquire"
        if normalized_pool == "github":
            prefer_mode = "acquire"
        elif normalized_pool == "news" and str(variant or "").strip() == "product_release_news":
            prefer_mode = "acquire"
        elif normalized_pool == "deep_dive" and str(article_variant or "").strip() == "project_explainer":
            prefer_mode = "acquire"
        return {
            "max_allowed": min(max(0, int(max_body_illustrations or 0)), 2),
            "prefer_mode": prefer_mode,
            "fallback_mode": "none"
            if normalized_pool == "deep_dive" and str(article_variant or "").strip() == "project_explainer"
            else "generate",
            "reason": f"{pool or 'unknown'}:{subtype or 'default'}:{variant or 'default'}",
        }

    def _build_blueprint_prompt(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        fact_grounding: dict[str, Any],
        source_structure: dict[str, Any],
        image_candidates: list[dict[str, Any]],
        body_policy: dict[str, Any],
        max_body_illustrations: int,
        variant: str,
        article_variant: str,
    ) -> str:
        pool, subtype = self._resolve_article_semantics(fact_pack)
        profile = self._strategy_profile(pool=pool, subtype=subtype, variant=variant, article_variant=article_variant)
        compact_candidates = [
            {
                "origin_type": str(item.get("origin_type", "") or "").strip(),
                "source_role": str(item.get("source_role", "") or "").strip(),
                "image_kind": str(item.get("image_kind", "") or "").strip(),
                "caption": str(item.get("caption", "") or "").strip()[:90],
                "source_page": str(item.get("source_page", "") or "").strip()[:160],
            }
            for item in list(image_candidates or [])[:6]
            if isinstance(item, dict)
        ]
        return (
            "You are the decision model for article visual planning. "
            "Return strict JSON only, with no markdown fences and no explanation.\n"
            "Think in this order: article type profile -> which subject is worth visualizing -> which intent is best -> whether the right answer is no body image.\n"
            "Output schema:\n"
            "{\n"
            '  "cover_family": "structure|comparison|thesis|command",\n'
            '  "cover_brief": {"main_claim": "", "subject_hint": "", "scene_hint": "", "mood_hint": "", "title_safe_zone": "left_top|left_center|left_bottom", "must_show": [], "must_avoid": []},\n'
            '  "items": [\n'
            '    {"placement_key": "section_1", "anchor_heading": "", "section_role": "overview", "intent_kind": "reference|evidence|explanatory|none", "preferred_mode": "acquire|capture|generate|none", "visual_goal": "", "visual_claim": "", "subject_ref": {"kind": "person|company|product|project|event|page|mechanism", "name": ""}, "subject_slots": {"person_subject": {"name": "", "priority": "high|medium|low|disabled"}, "company_subject": {"name": "", "priority": "high|medium|low|disabled"}, "product_subject": {"name": "", "priority": "high|medium|low|disabled"}, "project_subject": {"name": "", "priority": "high|medium|low|disabled"}, "event_subject": {"name": "", "priority": "high|medium|low|disabled"}, "page_subject": {"name": "", "priority": "high|medium|low|disabled"}, "mechanism_subject": {"name": "", "priority": "high|medium|low|disabled"}}, "task_priorities": {"reference": "high|medium|low|disabled", "evidence": "high|medium|low|disabled", "explanatory": "high|medium|low|disabled", "none": "high|medium|low|disabled"}, "evidence_refs": [], "facts_to_visualize": []}\n'
            "  ]\n"
            "}\n"
            "Rules:\n"
            f"- Maximum body items: {max_body_illustrations}\n"
            f"- Body policy: {json.dumps(body_policy, ensure_ascii=False)}\n"
            f"- Strategy profile: {json.dumps(profile, ensure_ascii=False)}\n"
            "- Use Chinese text values for human-facing fields.\n"
            "- News body illustrations must never use generated explanatory visuals; prefer no body image over a generated one.\n"
            "- News and GitHub first body item should not default to explanatory generate.\n"
            "- Across all article types, explanatory generate should be rare and only used when it is explicitly needed.\n"
            "- For product/API release news, prefer existing images from the main source first, then object-official images, then official-page screenshot, then logo, else none.\n"
            "- For deep_dive project explainers, preserve source/repo technical visuals first. Prefer source article diagrams or screenshots, then repo README/docs visuals, then repo/docs capture, else none.\n"
            "- For deep_dive project explainers, do not fall back to generated explanatory visuals or generic OG hero images.\n"
            "- If the article should not force a body image, return no items.\n"
            "- Do not output execution-only fields such as purpose, allowed_families, fallback_generate_brief, constraints, mode, or brief.\n"
            "- Decide intent and preferred_mode only.\n\n"
            f"Topic:\n{json.dumps(topic, ensure_ascii=False)}\n\n"
            f"Fact Pack:\n{json.dumps(fact_pack, ensure_ascii=False)[:5000]}\n\n"
            f"Fact Grounding:\n{json.dumps(fact_grounding, ensure_ascii=False)[:5000]}\n\n"
            f"Source Structure:\n{json.dumps(source_structure, ensure_ascii=False)[:5000]}\n\n"
            f"Image Candidates:\n{json.dumps(compact_candidates, ensure_ascii=False)}"
        )

    def _parse_blueprint(
        self,
        text: str,
        *,
        pool: str,
        subtype: str,
        body_policy: dict[str, Any],
        max_body_illustrations: int,
    ) -> VisualBlueprint | None:
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return None
            data = json.loads(text[start : end + 1])
        except Exception:
            return None
        if not isinstance(data, dict):
            return None

        cover_family = self._normalize_cover_family(data.get("cover_family"))
        cover_brief = self._normalize_cover_brief(data.get("cover_brief") or {})
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            # v5.8 stops accepting legacy body_illustrations as a decision source.
            # Falling back to empty items is safer than re-introducing old
            # explanatory/generate defaults through compatibility translation.
            raw_items = []
        items = [
            self._normalize_blueprint_item(item=item, subtype=subtype)
            for item in list(raw_items or [])[:max_body_illustrations]
            if isinstance(item, dict)
        ]
        items = [item for item in items if item]
        return VisualBlueprint(
            cover_family=cover_family,
            cover_brief=cover_brief,
            body_policy=dict(body_policy or {}),
            items=items,
        )

    def _fallback_blueprint(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        pool: str,
        subtype: str,
        body_policy: dict[str, Any],
        max_body_illustrations: int,
    ) -> VisualBlueprint:
        title = LocalizationService.localize_visual_text(str(topic.get("title", "") or "").strip())
        cover_family = "thesis" if pool == "news" else "comparison" if pool == "github" else "structure"
        cover_brief = {
            "main_claim": title,
            "subject_hint": title[:32] or "technical focal subject",
            "scene_hint": "clean technical scene with clear hierarchy",
            "mood_hint": "professional, calm, credible",
            "title_safe_zone": "left_bottom",
            "must_show": [title] if title else [],
            "must_avoid": ["robot face", "cheap ai glow", "watermark"],
        }
        return VisualBlueprint(
            cover_family=cover_family,
            cover_brief=self._normalize_cover_brief(cover_brief),
            body_policy=dict(body_policy or {}),
            items=[],
        )

    def _apply_pool_blueprint_policy(
        self,
        *,
        blueprint: VisualBlueprint,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        web_enrich: dict[str, Any],
        pool: str,
        subtype: str,
        image_candidates: list[dict[str, Any]],
        max_body_illustrations: int,
    ) -> VisualBlueprint:
        normalized_items = [
            self._normalize_blueprint_item(item=dict(item), subtype=subtype)
            for item in list(blueprint.items or [])[:max_body_illustrations]
            if isinstance(item, dict)
        ]
        normalized_items = [item for item in normalized_items if item]
        return VisualBlueprint(
            cover_family=blueprint.cover_family or ("thesis" if pool == "news" else "comparison"),
            cover_brief=dict(blueprint.cover_brief or {}),
            body_policy=dict(blueprint.body_policy or {}),
            items=normalized_items,
        )

    def _translate_legacy_body_illustrations(
        self,
        *,
        body_illustrations: list[Any],
        pool: str,
        subtype: str,
    ) -> list[dict[str, Any]]:
        translated: list[dict[str, Any]] = []
        for index, item in enumerate(body_illustrations):
            if not isinstance(item, dict):
                continue
            body_type = str(item.get("type", "") or "").strip() or self._fallback_body_type(
                section_heading=str(item.get("section", "") or ""),
                pool=pool,
                subtype=subtype,
            )
            candidate_urls = [
                str(url).strip()
                for url in (
                    item.get("candidate_image_urls")
                    or ([item.get("image_url")] if str(item.get("image_url", "") or "").strip() else [])
                )
                if str(url).strip()
            ]
            intent_kind = "explanatory" if body_type in {
                "comparison_card",
                "comparison_infographic",
                "process_explainer_infographic",
                "system_layers_infographic",
                "workflow_diagram",
                "architecture_diagram",
            } else "reference"
            preferred_mode = "generate" if intent_kind == "explanatory" else ("acquire" if candidate_urls else "none")
            section = LocalizationService.localize_visual_text(str(item.get("section", "") or "").strip())
            subject_name = LocalizationService.localize_visual_text(str(item.get("title", "") or item.get("caption", "") or "").strip())
            subject_kind = "event" if pool == "news" else "page" if pool == "github" else "product"
            task_priorities = {
                "reference": "high" if intent_kind == "reference" else "low",
                "evidence": "medium" if pool in {"news", "deep_dive"} and intent_kind == "reference" else "low",
                "explanatory": "high" if intent_kind == "explanatory" else "low",
                "none": "low",
            }
            translated.append(
                {
                    "placement_key": f"section_{index + 1}",
                    "anchor_heading": section,
                    "section_role": self._section_role_from_heading(str(item.get("section", "") or "")),
                    "placement": "after_section",
                    "intent_kind": intent_kind,
                    "preferred_mode": preferred_mode,
                    "required": index == 0,
                    "visual_goal": self._default_visual_goal(
                        pool=pool,
                        subtype=subtype,
                        section_heading=str(item.get("section", "") or ""),
                        body_type=body_type,
                    ),
                    "visual_claim": LocalizationService.localize_visual_text(
                        str(item.get("caption", "") or item.get("title", "") or "").strip()[:120]
                    ),
                    "subject_ref": {"kind": subject_kind, "name": subject_name} if subject_name else {},
                    "subject_slots": {
                        "person_subject": {"name": "", "priority": "disabled"},
                        "company_subject": {"name": "", "priority": "disabled"},
                        "product_subject": {"name": subject_name if subject_kind == "product" else "", "priority": "medium" if subject_kind == "product" and subject_name else "disabled"},
                        "project_subject": {"name": subject_name if subject_kind == "project" else "", "priority": "medium" if subject_kind == "project" and subject_name else "disabled"},
                        "event_subject": {"name": subject_name if subject_kind == "event" else "", "priority": "medium" if subject_kind == "event" and subject_name else "disabled"},
                        "page_subject": {"name": subject_name if subject_kind == "page" else "", "priority": "medium" if subject_kind == "page" and subject_name else "disabled"},
                        "mechanism_subject": {"name": section if intent_kind == "explanatory" else "", "priority": "medium" if intent_kind == "explanatory" and section else "disabled"},
                    },
                    "task_priorities": task_priorities,
                    "evidence_refs": [str(item.get("section", "") or "").strip()] if str(item.get("section", "") or "").strip() else [],
                    "facts_to_visualize": [str(x).strip() for x in (item.get("must_show") or []) if str(x).strip()],
                }
            )
        return translated

    def _strategy_profile(self, *, pool: str, subtype: str, variant: str = "", article_variant: str = "standard") -> dict[str, Any]:
        normalized_pool = str(pool or "").strip() or "deep_dive"
        base_profiles = {
            "news": {
                "first_item_allowed_intents": ["reference", "evidence", "none"],
                "mode_order": ["acquire", "none"],
                "reference_subject_order": ["person_subject", "company_subject", "product_subject", "event_subject"],
                "allow_capture": False,
                "allow_explanatory_generate": False,
            },
            "github": {
                "first_item_allowed_intents": ["reference", "none"],
                "mode_order": ["acquire", "capture", "generate", "none"],
                "reference_subject_order": ["page_subject", "project_subject", "product_subject", "company_subject"],
                "allow_capture": True,
                "allow_explanatory_generate": True,
            },
            "deep_dive": {
                "first_item_allowed_intents": ["reference", "evidence", "none"],
                "mode_order": ["acquire", "generate", "none"],
                "reference_subject_order": ["product_subject", "company_subject", "page_subject", "project_subject"],
                "allow_capture": False,
                "allow_explanatory_generate": True,
            },
        }
        profile = dict(base_profiles.get(normalized_pool) or base_profiles["deep_dive"])
        subtype_value = str(subtype or "").strip()
        if subtype_value == "capital_signal" and normalized_pool == "news":
            profile["reference_subject_order"] = ["company_subject", "product_subject", "event_subject", "person_subject"]
        if subtype_value in {"tutorial", "code_explainer"} and normalized_pool == "github":
            profile["reference_subject_order"] = ["page_subject", "product_subject", "project_subject", "company_subject"]
        if normalized_pool == "news" and str(variant or "").strip() == "product_release_news":
            profile["mode_order"] = ["acquire", "capture", "none"]
            profile["allow_capture"] = True
            profile["reference_subject_order"] = ["company_subject", "product_subject", "page_subject", "event_subject", "person_subject"]
        if normalized_pool == "deep_dive" and str(article_variant or "").strip() == "project_explainer":
            profile["mode_order"] = ["acquire", "capture", "none"]
            profile["allow_capture"] = True
            profile["allow_explanatory_generate"] = False
            profile["reference_subject_order"] = [
                "project_subject",
                "page_subject",
                "mechanism_subject",
                "product_subject",
                "company_subject",
            ]
            profile["default_subject_priorities"] = {
                **dict(profile.get("default_subject_priorities") or {}),
                "project_subject": "high",
                "page_subject": "high",
                "mechanism_subject": "medium",
                "product_subject": "medium",
                "company_subject": "low",
            }
            profile["default_task_priorities"] = {
                **dict(profile.get("default_task_priorities") or {}),
                "reference": "high",
                "evidence": "medium",
                "explanatory": "disabled",
                "none": "medium",
            }
        return profile

    def _normalize_subject_slots(self, item: dict[str, Any]) -> dict[str, dict[str, str]]:
        payload = dict(item.get("subject_slots") or {})
        slots: dict[str, dict[str, str]] = {}
        for key in self.SUBJECT_KEYS:
            entry = payload.get(key) if isinstance(payload.get(key), dict) else {}
            name = LocalizationService.localize_visual_text(
                str(
                    (entry or {}).get("name", "")
                    or item.get(key, "")
                    or item.get(key.replace("_subject", "_name"), "")
                    or ""
                ).strip()
            )
            priority = self._normalize_priority((entry or {}).get("priority", "") or item.get(f"{key}_priority", ""))
            slots[key] = {"name": name, "priority": priority or "disabled"}
        return slots

    def _normalize_task_priorities(self, item: dict[str, Any]) -> dict[str, str]:
        payload = dict(item.get("task_priorities") or {})
        priorities: dict[str, str] = {}
        for key in self.INTENT_KEYS:
            raw = payload.get(key, "") if isinstance(payload, dict) else ""
            priorities[key] = self._normalize_priority(raw or item.get(f"{key}_priority", "")) or "disabled"
        return priorities

    def _normalize_subject_ref(self, value: dict[str, Any], *, subject_slots: dict[str, dict[str, str]]) -> dict[str, str]:
        payload = dict(value or {})
        kind = str(payload.get("kind", "") or "").strip().lower()
        name = LocalizationService.localize_visual_text(str(payload.get("name", "") or "").strip())
        if kind and name:
            return {"kind": kind, "name": name}
        best_key = ""
        best_priority = -1
        for key, entry in subject_slots.items():
            entry_name = str(entry.get("name", "") or "").strip()
            entry_priority = self.PRIORITY_VALUE.get(str(entry.get("priority", "disabled") or "disabled"), 0)
            if entry_name and entry_priority > best_priority:
                best_key = key
                best_priority = entry_priority
        if not best_key:
            return {}
        return {"kind": best_key.replace("_subject", ""), "name": str(subject_slots.get(best_key, {}).get("name", "") or "").strip()}

    @classmethod
    def _normalize_priority(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in cls.PRIORITY_KEYS else ""

    @classmethod
    def _normalize_intent_kind(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in cls.INTENT_KEYS else ""

    @classmethod
    def _normalize_preferred_mode(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in cls.MODE_KEYS else ""

    def _normalize_blueprint_item(self, *, item: dict[str, Any], subtype: str) -> dict[str, Any]:
        brief = dict(item.get("brief") or {})
        anchor_heading = LocalizationService.localize_visual_text(str(item.get("anchor_heading", "") or brief.get("section", "") or "").strip())
        section_role = str(item.get("section_role", "") or "").strip() or self._section_role_from_heading(anchor_heading)
        intent_kind = self._normalize_intent_kind(item.get("intent_kind", ""))
        preferred_mode = self._normalize_preferred_mode(item.get("preferred_mode", ""))
        subject_slots = self._normalize_subject_slots(item)
        task_priorities = self._normalize_task_priorities(item)
        subject_ref = self._normalize_subject_ref(item.get("subject_ref") or {}, subject_slots=subject_slots)
        normalized = {
            "placement_key": str(item.get("placement_key", "") or "section_1").strip() or "section_1",
            "anchor_heading": anchor_heading,
            "section_role": section_role or "overview",
            "placement": str(item.get("placement", "") or "after_section").strip() or "after_section",
            "intent_kind": intent_kind or "none",
            "preferred_mode": preferred_mode or "none",
            "required": bool(item.get("required", False)),
            "subject_ref": subject_ref,
            "subject_slots": subject_slots,
            "task_priorities": task_priorities,
            "visual_goal": LocalizationService.localize_visual_text(str(item.get("visual_goal", "") or "").strip()),
            "visual_claim": LocalizationService.localize_visual_text(str(item.get("visual_claim", "") or "").strip()),
            "evidence_refs": [str(entry).strip() for entry in (item.get("evidence_refs") or []) if str(entry).strip()],
            "facts_to_visualize": [str(entry).strip() for entry in (item.get("facts_to_visualize") or []) if str(entry).strip()],
        }
        if normalized["intent_kind"] == "none" or normalized["preferred_mode"] == "none":
            normalized["preferred_mode"] = "none"
        return normalized

    def _build_capture_item(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        pool: str,
        subtype: str,
        index: int,
        capture_targets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sections = self._generic_sections(fact_pack)
        section = sections[min(index, len(sections) - 1)]
        title = LocalizationService.localize_visual_text(str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip())
        purpose = "product_screenshot"
        return self._normalize_blueprint_item(
            item={
                "placement_key": f"section_{index + 1}",
                "anchor_heading": section,
                "section_role": self._section_role_from_heading(section),
                "purpose": purpose,
                "placement": "after_section",
                "mode": "capture",
                "preferred_mode": "capture",
                "required": index == 0,
                "visual_goal": self._default_visual_goal(pool=pool, subtype=subtype, section_heading=section, body_type=purpose),
                "visual_claim": title[:64] or section,
                "evidence_refs": [section],
                "facts_to_visualize": [section],
                "allowed_families": self._allowed_generate_families(pool=pool, subtype=subtype, section_heading=section),
                "brief": {
                    "type": purpose,
                    "section": section,
                    "title": title[:48] or section,
                    "caption": LocalizationService.localize_visual_text(f"{section} 对应的真实页面截图"),
                    "must_show": [section] if section else [],
                    "must_avoid": ["cropped blank page", "login wall", "watermark"],
                },
                "constraints": {"capture_targets": [dict(item) for item in capture_targets]},
                "fallback_generate_brief": self._build_generate_fallback_brief(
                    item={"section": section, "title": title, "caption": ""},
                    pool=pool,
                    subtype=subtype,
                ),
            },
            subtype=subtype,
        )

    def _prefer_capture_for_github(
        self,
        *,
        item: dict[str, Any],
        subtype: str,
        capture_targets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        current = dict(item)
        if str(current.get("preferred_mode", "") or "").strip() != "acquire":
            return current
        constraints = dict(current.get("constraints") or {})
        if list(constraints.get("candidate_image_urls") or []):
            return current
        if list(constraints.get("capture_targets") or []):
            return current
        current["mode"] = "capture"
        current["preferred_mode"] = "capture"
        current["constraints"] = {**constraints, "capture_targets": [dict(entry) for entry in capture_targets]}
        return self._normalize_blueprint_item(item=current, subtype=subtype)

    @staticmethod
    def _build_capture_targets(*, topic: dict[str, Any], web_enrich: dict[str, Any], pool: str) -> list[dict[str, Any]]:
        if str(pool or "").strip() != "github":
            return []
        targets: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(url: str, *, origin_type: str, query_source: str, title: str = "", caption: str = "") -> None:
            normalized = str(url or "").strip()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            targets.append(
                {
                    "url": normalized,
                    "origin_type": origin_type,
                    "query_source": query_source,
                    "title": title.strip(),
                    "caption": caption.strip(),
                }
            )

        topic_url = str(topic.get("url", "") or "").strip()
        if topic_url:
            add(topic_url, origin_type="primary", query_source="repo_readme", title="README 首屏", caption="仓库首页与 README 首屏截图")

        for entry in list((web_enrich or {}).get("official_sources") or [])[:4]:
            if not isinstance(entry, dict):
                continue
            entry_url = str(entry.get("url", "") or "").strip()
            if not entry_url:
                continue
            lowered = entry_url.lower()
            if any(token in lowered for token in ("/docs", "docs.", "/demo", "demo.", "/playground", "/app", "/product")):
                add(
                    entry_url,
                    origin_type="official",
                    query_source=str(entry.get("query", "") or entry.get("title", "") or "official").strip() or "official",
                    title=str(entry.get("title", "") or "").strip(),
                    caption="官方页面首屏截图",
                )
            elif "github.com" not in lowered:
                add(
                    entry_url,
                    origin_type="official",
                    query_source=str(entry.get("query", "") or entry.get("title", "") or "official").strip() or "official",
                    title=str(entry.get("title", "") or "").strip(),
                    caption="官网或产品页截图",
                )
        return targets[:4]

    def _build_news_crawl_item(
        self,
        *,
        candidate: dict[str, Any],
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        subtype: str,
        index: int,
    ) -> dict[str, Any]:
        sections = self._news_sections(fact_pack)
        section = sections[min(index, len(sections) - 1)]
        title = self._pick_news_photo_title(
            topic_title=str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip(),
            section=section,
            source_article=str(candidate.get("source_article", "") or ""),
            alt=str(candidate.get("alt", "") or ""),
            caption=str(candidate.get("caption", "") or ""),
            context=str(candidate.get("context", "") or ""),
        )
        caption = self._pick_news_photo_caption(
            topic_title=str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip(),
            section=section,
            source_article=str(candidate.get("source_article", "") or ""),
            title=title,
            caption=str(candidate.get("caption", "") or ""),
            context=str(candidate.get("context", "") or ""),
        )
        urls = [str(candidate.get("url", "") or "").strip()]
        return self._normalize_blueprint_item(
            item={
                "placement_key": f"section_{index + 1}",
                "anchor_heading": section,
                "section_role": self._section_role_from_heading(section),
                "purpose": "news_photo",
                "placement": "after_section",
                "mode": "crawl",
                "preferred_mode": "acquire",
                "required": True,
                "visual_goal": self._default_visual_goal(pool="news", subtype=subtype, section_heading=section, body_type="news_photo"),
                "visual_claim": caption or title,
                "evidence_refs": [section],
                "facts_to_visualize": [caption or title],
                "allowed_families": [],
                "brief": {
                    "type": "news_photo",
                    "section": section,
                    "title": title,
                    "caption": caption,
                    "must_show": [],
                    "must_avoid": ["generated fake news photo", "robot face", "cheap ai glow"],
                },
                "constraints": {"candidate_image_urls": urls, "candidate_metadata": [dict(candidate)]},
                "fallback_generate_brief": self._build_news_fallback_generate_brief(
                    item={"section": section, "title": title, "caption": caption},
                    subtype=subtype,
                ),
            },
            subtype=subtype,
        )

    def _build_news_generate_item(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        subtype: str,
        index: int,
    ) -> dict[str, Any]:
        sections = self._news_sections(fact_pack)
        section = sections[min(index, len(sections) - 1)]
        fallback_type = self._fallback_body_type(section_heading=section, pool="news", subtype=subtype)
        title = LocalizationService.localize_visual_text(str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip())
        summary = ""
        for item in (fact_pack.get("section_blueprint") or []):
            if isinstance(item, dict) and str(item.get("heading", "") or "").strip() == section:
                summary = LocalizationService.localize_visual_text(str(item.get("summary", "") or "").strip()[:120])
                break
        return self._normalize_blueprint_item(
            item={
                "placement_key": f"section_{index + 1}",
                "anchor_heading": section,
                "section_role": self._section_role_from_heading(section),
                "purpose": fallback_type,
                "placement": "after_section",
                "mode": "generate",
                "preferred_mode": "generate",
                "required": True,
                "visual_goal": self._default_visual_goal(pool="news", subtype=subtype, section_heading=section, body_type=fallback_type),
                "visual_claim": summary or title[:48] or section,
                "evidence_refs": [section],
                "facts_to_visualize": [summary] if summary else [section],
                "allowed_families": self._allowed_generate_families(pool="news", subtype=subtype, section_heading=section),
                "brief": {
                    "type": fallback_type,
                    "section": section,
                    "title": title[:48] or section,
                    "caption": summary,
                    "must_show": [section] if section else [],
                    "must_avoid": ["photorealistic fake news photo", "robot face", "watermark"],
                },
            },
            subtype=subtype,
        )

    def _build_acquire_item(
        self,
        *,
        candidate: dict[str, Any],
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        pool: str,
        subtype: str,
        index: int,
    ) -> dict[str, Any]:
        sections = self._generic_sections(fact_pack)
        section = sections[min(index, len(sections) - 1)]
        image_kind = str(candidate.get("image_kind", "") or "").strip()
        purpose = "product_screenshot" if image_kind == "screenshot" else "reference_image"
        title = LocalizationService.localize_visual_text(str(candidate.get("alt", "") or topic.get("title", "") or "").strip()[:64])
        caption = LocalizationService.localize_visual_text(
            str(candidate.get("caption", "") or candidate.get("context_snippet", "") or "").strip()[:140]
        )
        return self._normalize_blueprint_item(
            item={
                "placement_key": f"section_{index + 1}",
                "anchor_heading": section,
                "section_role": self._section_role_from_heading(section),
                "purpose": purpose,
                "placement": "after_section",
                "mode": "crawl",
                "preferred_mode": "acquire",
                "required": index == 0,
                "visual_goal": self._default_visual_goal(pool=pool, subtype=subtype, section_heading=section, body_type=purpose),
                "visual_claim": caption or title or section,
                "evidence_refs": [section],
                "facts_to_visualize": [caption] if caption else [section],
                "allowed_families": self._allowed_generate_families(pool=pool, subtype=subtype, section_heading=section),
                "brief": {
                    "type": purpose,
                    "section": section,
                    "title": title or section,
                    "caption": caption,
                    "must_show": [section] if section else [],
                    "must_avoid": ["watermark", "robot face"],
                },
                "constraints": {"candidate_image_urls": [str(candidate.get("url", "") or "").strip()], "candidate_metadata": [dict(candidate)]},
                "fallback_generate_brief": self._build_generate_fallback_brief(
                    item={"section": section, "title": title, "caption": caption},
                    pool=pool,
                    subtype=subtype,
                ),
            },
            subtype=subtype,
        )

    def _build_generate_item(
        self,
        *,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        pool: str,
        subtype: str,
        index: int,
    ) -> dict[str, Any]:
        sections = self._news_sections(fact_pack) if pool == "news" else self._generic_sections(fact_pack)
        section = sections[min(index, len(sections) - 1)]
        fallback_type = self._fallback_body_type(section_heading=section, pool=pool, subtype=subtype)
        summary = ""
        for item in (fact_pack.get("section_blueprint") or []):
            if isinstance(item, dict) and str(item.get("heading", "") or "").strip() == section:
                summary = LocalizationService.localize_visual_text(str(item.get("summary", "") or "").strip()[:120])
                break
        title = LocalizationService.localize_visual_text(str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip())
        return self._normalize_blueprint_item(
            item={
                "placement_key": f"section_{index + 1}",
                "anchor_heading": section,
                "section_role": self._section_role_from_heading(section),
                "purpose": fallback_type,
                "placement": "after_section",
                "mode": "generate",
                "preferred_mode": "generate",
                "required": index == 0,
                "visual_goal": self._default_visual_goal(pool=pool, subtype=subtype, section_heading=section, body_type=fallback_type),
                "visual_claim": summary or title[:48] or section,
                "evidence_refs": [section],
                "facts_to_visualize": [summary] if summary else [section],
                "allowed_families": self._allowed_generate_families(pool=pool, subtype=subtype, section_heading=section),
                "brief": {
                    "type": fallback_type,
                    "section": section,
                    "title": title[:48] or section,
                    "caption": summary,
                    "must_show": [section] if section else [],
                    "must_avoid": ["photorealistic fake photo", "robot face", "watermark"],
                },
            },
            subtype=subtype,
        )

    @classmethod
    def _build_news_fallback_generate_brief(cls, *, item: dict[str, Any], subtype: str) -> dict[str, Any]:
        section = LocalizationService.localize_visual_text(str(item.get("section", "") or "").strip())
        fallback_type = cls._fallback_body_type(section_heading=section, pool="news", subtype=subtype)
        return {
            "type": fallback_type,
            "section": section,
            "title": LocalizationService.localize_visual_text(str(item.get("title", "") or "").strip()),
            "caption": LocalizationService.localize_visual_text(str(item.get("caption", "") or "").strip()),
            "must_show": [section] if section else [],
            "must_avoid": ["photorealistic fake news photo", "robot face", "watermark"],
        }

    @classmethod
    def _build_generate_fallback_brief(cls, *, item: dict[str, Any], pool: str, subtype: str) -> dict[str, Any]:
        section = LocalizationService.localize_visual_text(str(item.get("section", "") or item.get("anchor_heading", "") or "").strip())
        fallback_type = cls._fallback_body_type(section_heading=section, pool=pool, subtype=subtype)
        return {
            "type": fallback_type,
            "section": section,
            "title": LocalizationService.localize_visual_text(str(item.get("title", "") or "").strip()),
            "caption": LocalizationService.localize_visual_text(str(item.get("caption", "") or "").strip()),
            "must_show": [section] if section else [],
            "must_avoid": ["photorealistic fake photo", "robot face", "watermark"],
        }

    def _pick_viable_news_candidates(self, fact_pack: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [
            dict(item)
            for item in (fact_pack.get("news_image_candidates") or [])
            if isinstance(item, dict) and not self._is_placeholder_news_image(item)
        ]
        filtered = [
            item
            for item in candidates
            if not self._should_reject_news_image_candidate(item=item, fact_pack=fact_pack)
        ]
        viable = [
            item
            for item in filtered
            if int(item.get("relevance_hits", 0) or 0) > 0
            or int(item.get("score", 0) or 0) >= 85
            or (str(item.get("origin", "") or "").strip() == "primary" and not self._is_low_signal_news_image(item))
        ]
        if viable:
            return viable
        primary_only = [item for item in filtered if str(item.get("origin", "") or "").strip() == "primary"]
        return primary_only[:1] or filtered[:1]

    def _pick_viable_image_candidates(
        self,
        *,
        pool: str,
        fact_pack: dict[str, Any],
        image_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized_pool = str(pool or "").strip()
        if normalized_pool == "news":
            curated = self._pick_viable_news_candidates(
                {
                    **dict(fact_pack or {}),
                    "news_image_candidates": [
                        {
                            **dict(item),
                            "origin": str(item.get("origin", "") or item.get("origin_type", "") or "").strip(),
                            "context": str(item.get("context", "") or item.get("context_snippet", "") or "").strip(),
                            "score": int(item.get("score", 0) or 0),
                            "relevance_hits": int(item.get("relevance_hits", 0) or 0),
                        }
                        for item in list(image_candidates or [])
                        if isinstance(item, dict)
                    ],
                }
            )
            if curated:
                return curated
        curated: list[dict[str, Any]] = []
        for item in list(image_candidates or []):
            if not isinstance(item, dict):
                continue
            image_kind = str(item.get("image_kind", "") or "").strip().lower()
            if image_kind in {"logo", "avatar"}:
                continue
            if int(item.get("provenance_score", 0) or 0) < 30:
                continue
            curated.append(dict(item))
        ranked = sorted(
            curated,
            key=lambda item: (
                int(item.get("score", 0) or 0),
                int(item.get("relevance_hits", 0) or 0),
                int(item.get("provenance_score", 0) or 0),
            ),
            reverse=True,
        )
        return ranked[:6]

    @staticmethod
    def _fallback_body_type(*, section_heading: str, pool: str = "", subtype: str = "") -> str:
        heading = str(section_heading or "").strip()
        normalized_pool = str(pool or "").strip()
        normalized_subtype = str(subtype or "").strip()
        if normalized_pool == "news":
            if normalized_subtype == "capital_signal":
                return "comparison_infographic"
            return "comparison_card"
        if normalized_pool == "github":
            if normalized_subtype in {"repo_recommendation", "collection_repo"}:
                return "comparison_card"
            if normalized_subtype == "stack_analysis":
                return "system_layers_infographic"
            return "process_explainer_infographic"
        if any(token in heading for token in ["compare", "comparison", "difference", "trade-off", "vs", "对比", "差异"]):
            return "comparison_infographic"
        if any(token in heading.lower() for token in ["workflow", "pipeline", "process", "step"]):
            return "process_explainer_infographic"
        if normalized_subtype == "tutorial":
            return "process_explainer_infographic"
        return "system_layers_infographic"

    @classmethod
    def _default_visual_goal(cls, *, pool: str, subtype: str, section_heading: str, body_type: str) -> str:
        heading = LocalizationService.localize_visual_text(str(section_heading or "").strip())
        if body_type == "news_photo":
            return f"为“{heading or '当前小节'}”提供可信现场或人物纪实参考"
        if body_type == "product_screenshot":
            return f"展示“{heading or '当前小节'}”对应的真实界面或产品形态"
        if body_type == "reference_image":
            return f"为“{heading or '当前小节'}”补充真实参考图"
        if body_type == "comparison_infographic":
            return f"帮助读者理解“{heading or '当前小节'}”中的关键对比关系"
        if body_type == "process_explainer_infographic":
            return f"帮助读者看清“{heading or '当前小节'}”的流程与步骤"
        return f"帮助读者理解“{heading or '当前小节'}”的结构与重点"

    @classmethod
    def _allowed_generate_families(cls, *, pool: str, subtype: str, section_heading: str) -> list[str]:
        normalized_pool = str(pool or "").strip()
        normalized_subtype = str(subtype or "").strip()
        body_type = cls._fallback_body_type(section_heading=section_heading, pool=pool, subtype=subtype)
        if normalized_pool == "news":
            if normalized_subtype == "capital_signal":
                return ["comparison_infographic", "comparison_card"]
            return ["comparison_card", "process_explainer_infographic"]
        if normalized_pool == "github":
            if normalized_subtype in {"code_explainer", "tutorial"}:
                return ["process_explainer_infographic", "system_layers_infographic"]
            if normalized_subtype == "stack_analysis":
                return ["system_layers_infographic", "comparison_infographic"]
            return ["comparison_card", body_type]
        return [body_type, "process_explainer_infographic", "system_layers_infographic"]

    @staticmethod
    def _generic_sections(fact_pack: dict[str, Any]) -> list[str]:
        headings = [
            LocalizationService.localize_visual_text(str(item.get("heading", "") or "").strip())
            for item in (fact_pack.get("section_blueprint") or [])
            if isinstance(item, dict) and str(item.get("heading", "") or "").strip()
        ]
        cleaned = [item for item in headings if item and len(item) <= 72]
        return cleaned or ["核心结论", "实现细节"]

    @staticmethod
    def _normalize_cover_family(value: Any) -> str:
        family = str(value or "structure").strip().lower() or "structure"
        return family if family in {"structure", "comparison", "thesis", "command"} else "structure"

    @staticmethod
    def _normalize_cover_brief(value: dict[str, Any]) -> dict[str, Any]:
        brief = dict(value or {})
        return {
            "main_claim": LocalizationService.localize_visual_text(str(brief.get("main_claim", "") or "").strip()),
            "subject_hint": LocalizationService.localize_visual_text(str(brief.get("subject_hint", "") or "").strip()),
            "scene_hint": LocalizationService.localize_visual_text(str(brief.get("scene_hint", "") or "").strip()),
            "mood_hint": LocalizationService.localize_visual_text(str(brief.get("mood_hint", "") or "").strip()),
            "title_safe_zone": VisualStrategyService._normalize_title_safe_zone(brief.get("title_safe_zone", "left_bottom")),
            "must_show": LocalizationService.localize_visual_items(brief.get("must_show") or []),
            "must_avoid": LocalizationService.localize_visual_items(brief.get("must_avoid") or []),
        }

    @staticmethod
    def _normalize_title_safe_zone(value: Any) -> str:
        zone = str(value or "left_bottom").strip().lower() or "left_bottom"
        return zone if zone in {"left_top", "left_center", "left_bottom"} else "left_bottom"

    @staticmethod
    def _section_role_from_heading(heading: str) -> str:
        value = str(heading or "").strip().lower()
        if not value:
            return "overview"
        if any(token in value for token in ("event", "what changed", "事件", "脉络")):
            return "event_frame"
        if any(token in value for token in ("impact", "meaning", "影响", "意义")):
            return "impact"
        if any(token in value for token in ("risk", "watch", "观察", "风险")):
            return "watch_signals"
        if any(token in value for token in ("capital", "融资", "估值")):
            return "capital_signal"
        return "overview"

    @staticmethod
    def _news_sections(fact_pack: dict[str, Any]) -> list[str]:
        headings = [
            LocalizationService.localize_visual_text(str(item.get("heading", "") or "").strip())
            for item in (fact_pack.get("section_blueprint") or [])
            if isinstance(item, dict) and str(item.get("heading", "") or "").strip()
        ]
        cleaned = [item for item in headings if item and not VisualStrategyService._looks_like_noisy_news_section(item)]
        return cleaned or ["事件脉络", "影响判断"]

    @staticmethod
    def _looks_like_noisy_news_section(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return True
        if len(re.findall(r"[A-Za-z]{4,}", value)) >= 6 and not re.search(r"[\u4e00-\u9fff]", value):
            return True
        return len(value) > 72

    @staticmethod
    def _is_placeholder_news_image(item: dict[str, Any]) -> bool:
        haystack = " ".join(
            [
                str(item.get("url", "") or "").lower(),
                str(item.get("alt", "") or "").lower(),
                str(item.get("caption", "") or "").lower(),
                str(item.get("context", "") or "").lower(),
            ]
        )
        if not haystack.strip():
            return True
        return any(
            marker in haystack
            for marker in ("miss-main-pic", "missing", "placeholder", "default-image", "no-image", "fallback")
        )

    @staticmethod
    def _is_low_signal_news_image(item: dict[str, Any]) -> bool:
        text_signals = [
            VisualStrategyService._clean_news_photo_text(item.get("alt", "")),
            VisualStrategyService._clean_news_photo_text(item.get("caption", "")),
            VisualStrategyService._clean_news_photo_text(item.get("context", "")),
            VisualStrategyService._clean_news_photo_text(item.get("source_article", "")),
        ]
        return not any(text_signals)

    @staticmethod
    def _should_reject_news_image_candidate(*, item: dict[str, Any], fact_pack: dict[str, Any]) -> bool:
        raw_haystack = " ".join(
            [
                str(item.get("url", "") or ""),
                str(item.get("alt", "") or ""),
                str(item.get("caption", "") or ""),
                str(item.get("context", "") or ""),
                str(item.get("source_article", "") or ""),
            ]
        ).lower()
        if re.search(r"\b(?:author|editor|reporter|headshot|portrait|avatar|staff)\b", raw_haystack):
            return True
        if not VisualStrategyService._is_low_signal_news_image(item):
            return False
        score = int(item.get("score", 0) or 0)
        relevance_hits = int(item.get("relevance_hits", 0) or 0)
        if score >= 85 or relevance_hits > 0:
            return False
        candidate_date = VisualStrategyService._extract_date_key(str(item.get("url", "") or ""))
        published_date = VisualStrategyService._extract_date_key(str(fact_pack.get("published", "") or ""))
        if candidate_date and published_date and abs(candidate_date - published_date) >= 120:
            return True
        return score < 60 and relevance_hits == 0

    @staticmethod
    def _extract_date_key(value: str) -> int | None:
        match = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", str(value or "").strip())
        if not match:
            return None
        year, month, day = (int(part) for part in match.groups())
        return year * 10000 + month * 100 + day

    @staticmethod
    def _clean_news_photo_text(value: Any) -> str:
        text = str(value or "").strip()
        text = re.sub(r"<[^>]*>", " ", text)
        text = re.sub(r"&[A-Za-z#0-9]+;", " ", text)
        text = re.sub(r"https?://\S+", " ", text, flags=re.IGNORECASE)
        text = LocalizationService.localize_visual_text(text)
        return re.sub(r"\s+", " ", text).strip(" >\"'.,;:!?，。；：！？")

    @classmethod
    def _pick_news_photo_title(
        cls,
        *,
        topic_title: str,
        section: str,
        source_article: str,
        alt: str,
        caption: str,
        context: str,
    ) -> str:
        for candidate in (
            cls._clean_news_photo_text(alt),
            cls._clean_news_photo_text(caption),
            cls._clean_news_photo_text(source_article),
            cls._clean_news_photo_text(topic_title),
            cls._clean_news_photo_text(section),
            cls._clean_news_photo_text(context),
        ):
            if candidate:
                return candidate[:64]
        return "新闻现场"

    @classmethod
    def _pick_news_photo_caption(
        cls,
        *,
        topic_title: str,
        section: str,
        source_article: str,
        title: str,
        caption: str,
        context: str,
    ) -> str:
        for candidate in (
            cls._clean_news_photo_text(caption),
            cls._clean_news_photo_text(context),
            cls._clean_news_photo_text(source_article),
            cls._clean_news_photo_text(topic_title),
            cls._clean_news_photo_text(section),
        ):
            if candidate and candidate != title:
                return candidate[:120]
        return cls._clean_news_photo_text(section)[:120]
