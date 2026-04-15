from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.runtime.state_models import VisualBlueprint
from app.services.article_variant_policy import detect_article_variant
from app.services.localization_service import LocalizationService
from app.services.news_visual_policy import (
    NEWS_PRODUCT_RELEASE_SOURCE_ORDER,
    classify_news_visual_variant,
    collect_official_hosts,
    is_official_host,
)


class VisualExecutionCompiler:
    SUBJECT_KEYS = (
        "person_subject",
        "company_subject",
        "product_subject",
        "project_subject",
        "event_subject",
        "page_subject",
        "mechanism_subject",
    )
    PRIORITY_VALUE = {"disabled": 0, "low": 1, "medium": 2, "high": 3}
    TASK_KEYS = ("reference", "evidence", "explanatory", "none")

    BASE_PROFILES: dict[str, dict[str, Any]] = {
        "news": {
            "intent_order": ["reference", "evidence", "none", "explanatory"],
            "first_item_allowed_intents": {"reference", "evidence", "none"},
            "mode_order": ["acquire", "none"],
            "allow_capture": False,
            "allow_explanatory_generate": False,
            "reference_subject_order": ["person_subject", "company_subject", "product_subject", "event_subject"],
            "default_subject_priorities": {
                "person_subject": "high",
                "company_subject": "high",
                "product_subject": "medium",
                "event_subject": "medium",
                "page_subject": "disabled",
                "project_subject": "disabled",
                "mechanism_subject": "low",
            },
            "default_task_priorities": {
                "reference": "high",
                "evidence": "medium",
                "explanatory": "disabled",
                "none": "medium",
            },
            "explanatory_families": ["comparison_card", "process_explainer_infographic"],
        },
        "github": {
            "intent_order": ["reference", "none", "explanatory"],
            "first_item_allowed_intents": {"reference", "none"},
            "mode_order": ["acquire", "capture", "generate", "none"],
            "allow_capture": True,
            "allow_explanatory_generate": True,
            "reference_subject_order": ["page_subject", "project_subject", "product_subject", "company_subject"],
            "default_subject_priorities": {
                "person_subject": "disabled",
                "company_subject": "low",
                "product_subject": "medium",
                "project_subject": "high",
                "event_subject": "disabled",
                "page_subject": "high",
                "mechanism_subject": "medium",
            },
            "default_task_priorities": {
                "reference": "high",
                "evidence": "low",
                "explanatory": "low",
                "none": "medium",
            },
            "explanatory_families": ["process_explainer_infographic", "system_layers_infographic"],
        },
        "deep_dive": {
            "intent_order": ["reference", "evidence", "none", "explanatory"],
            "first_item_allowed_intents": {"reference", "evidence", "none"},
            "mode_order": ["acquire", "generate", "none"],
            "allow_capture": False,
            "allow_explanatory_generate": True,
            "reference_subject_order": ["product_subject", "company_subject", "page_subject", "project_subject"],
            "default_subject_priorities": {
                "person_subject": "low",
                "company_subject": "medium",
                "product_subject": "high",
                "project_subject": "medium",
                "event_subject": "disabled",
                "page_subject": "medium",
                "mechanism_subject": "medium",
            },
            "default_task_priorities": {
                "reference": "high",
                "evidence": "medium",
                "explanatory": "low",
                "none": "medium",
            },
            "explanatory_families": ["system_layers_infographic", "process_explainer_infographic"],
        },
    }

    SUBTYPE_OVERRIDES: dict[str, dict[str, Any]] = {
        "capital_signal": {"explanatory_families": ["comparison_infographic", "comparison_card"]},
        "stack_analysis": {"explanatory_families": ["system_layers_infographic", "comparison_infographic"]},
        "tutorial": {"explanatory_families": ["process_explainer_infographic", "system_layers_infographic"]},
        "code_explainer": {"explanatory_families": ["process_explainer_infographic", "system_layers_infographic"]},
    }

    def compile_blueprint(
        self,
        *,
        visual_blueprint: VisualBlueprint | dict[str, Any],
        pool: str,
        subtype: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        web_enrich: dict[str, Any],
        source_structure: dict[str, Any] | None = None,
        image_candidates: list[dict[str, Any]],
        max_body_illustrations: int,
    ) -> VisualBlueprint:
        if isinstance(visual_blueprint, VisualBlueprint):
            blueprint = visual_blueprint
        elif hasattr(visual_blueprint, "as_dict") and callable(getattr(visual_blueprint, "as_dict")):
            blueprint = VisualBlueprint.from_dict(visual_blueprint.as_dict())
        elif hasattr(visual_blueprint, "__dict__"):
            blueprint = VisualBlueprint.from_dict(dict(getattr(visual_blueprint, "__dict__", {}) or {}))
        else:
            blueprint = VisualBlueprint.from_dict(visual_blueprint)
        news_variant = str(classify_news_visual_variant(topic=topic, fact_pack=fact_pack).get("variant", "standard_news"))
        article_variant = str(fact_pack.get("article_variant", "") or "").strip() or str(
            detect_article_variant(topic=topic, fact_pack=fact_pack) or "standard"
        )
        strategy_variant = news_variant if str(pool or "").strip() == "news" else article_variant
        profile = self.resolve_profile(pool=pool, subtype=subtype, variant=strategy_variant, article_variant=article_variant)
        capture_targets = self._build_capture_targets(
            topic=topic,
            web_enrich=web_enrich,
            image_candidates=image_candidates,
            pool=pool,
            variant=news_variant,
            article_variant=article_variant,
            profile=profile,
            fact_pack=fact_pack,
            source_structure=source_structure or {},
        )
        compiled_items: list[dict[str, Any]] = []
        normalized_items = [dict(item) for item in list(blueprint.items or []) if isinstance(item, dict)]
        for index, item in enumerate(normalized_items[: max(0, int(max_body_illustrations or 0))]):
            compiled = self._compile_item(
                item=item,
                index=index,
                pool=pool,
                subtype=subtype,
                topic=topic,
                fact_pack=fact_pack,
                image_candidates=image_candidates,
                capture_targets=capture_targets,
                profile=profile,
                variant=news_variant,
                article_variant=article_variant,
            )
            if compiled:
                compiled_items.append(compiled)
        body_policy = dict(blueprint.body_policy or {})
        body_policy.pop("min_required", None)
        body_policy["max_allowed"] = min(max(0, int(max_body_illustrations or 0)), 2)
        body_policy["prefer_mode"] = str(profile["mode_order"][0] if profile.get("mode_order") else "acquire")
        body_policy["reason"] = f"{pool or 'unknown'}:{subtype or 'default'}:{strategy_variant}"
        return VisualBlueprint(
            cover_family=blueprint.cover_family,
            cover_brief=dict(blueprint.cover_brief or {}),
            body_policy=body_policy,
            items=compiled_items,
        )

    def resolve_profile(self, *, pool: str, subtype: str, variant: str = "", article_variant: str = "standard") -> dict[str, Any]:
        normalized_pool = str(pool or "").strip() or "deep_dive"
        base = dict(self.BASE_PROFILES.get(normalized_pool) or self.BASE_PROFILES["deep_dive"])
        override = dict(self.SUBTYPE_OVERRIDES.get(str(subtype or "").strip()) or {})
        if override.get("default_subject_priorities"):
            merged_subjects = {**dict(base.get("default_subject_priorities") or {}), **dict(override.get("default_subject_priorities") or {})}
            base["default_subject_priorities"] = merged_subjects
        for key, value in override.items():
            if key == "default_subject_priorities":
                continue
            base[key] = value
        if normalized_pool == "news" and str(variant or "").strip() == "product_release_news":
            base["mode_order"] = ["acquire", "capture", "none"]
            base["allow_capture"] = True
            base["reference_subject_order"] = ["company_subject", "product_subject", "page_subject", "event_subject", "person_subject"]
        if normalized_pool == "deep_dive" and str(article_variant or "").strip() == "project_explainer":
            base["mode_order"] = ["acquire", "capture", "none"]
            base["allow_capture"] = True
            base["allow_explanatory_generate"] = False
            base["reference_subject_order"] = [
                "project_subject",
                "page_subject",
                "mechanism_subject",
                "product_subject",
                "company_subject",
            ]
            base["default_subject_priorities"] = {
                **dict(base.get("default_subject_priorities") or {}),
                "project_subject": "high",
                "page_subject": "high",
                "mechanism_subject": "medium",
                "product_subject": "medium",
                "company_subject": "low",
            }
            base["default_task_priorities"] = {
                **dict(base.get("default_task_priorities") or {}),
                "reference": "high",
                "evidence": "medium",
                "explanatory": "disabled",
                "none": "medium",
            }
        return base

    def _compile_item(
        self,
        *,
        item: dict[str, Any],
        index: int,
        pool: str,
        subtype: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        image_candidates: list[dict[str, Any]],
        capture_targets: list[dict[str, Any]],
        profile: dict[str, Any],
        variant: str,
        article_variant: str,
    ) -> dict[str, Any] | None:
        normalized = self._normalize_decision_item(item=item, profile=profile, subtype=subtype)
        intent_kind = self._resolve_intent_kind(item=normalized, profile=profile, first_item=index == 0)
        preferred_mode = self._resolve_preferred_mode(
            item=normalized,
            intent_kind=intent_kind,
            profile=profile,
            pool=pool,
            variant=variant,
            article_variant=article_variant,
            image_candidates=image_candidates,
            capture_targets=capture_targets,
        )
        if intent_kind == "none" or preferred_mode == "none":
            return None
        subject_ref = dict(normalized.get("subject_ref") or {})
        brief = self._build_execution_brief(
            item=normalized,
            intent_kind=intent_kind,
            preferred_mode=preferred_mode,
            pool=pool,
            subtype=subtype,
            profile=profile,
            topic=topic,
            fact_pack=fact_pack,
            subject_ref=subject_ref,
        )
        execution_type = str(brief.get("type", "") or "").strip()
        constraints = dict(normalized.get("constraints") or {})
        if preferred_mode == "capture" and capture_targets:
            constraints = {**constraints, "capture_targets": [dict(entry) for entry in capture_targets]}
        else:
            constraints.pop("capture_targets", None)
        if preferred_mode != "acquire":
            constraints.pop("candidate_image_urls", None)
            constraints.pop("candidate_metadata", None)
        allowed_families = []
        if intent_kind == "explanatory" and execution_type:
            allowed_families = [execution_type]
        if str(pool or "").strip() == "news" and str(variant or "").strip() == "product_release_news":
            constraints["source_role_order"] = list(NEWS_PRODUCT_RELEASE_SOURCE_ORDER[:2])
            constraints["allow_logo_fallback"] = bool(
                preferred_mode == "acquire"
                and self._has_release_acquire_candidate(
                    image_candidates=image_candidates,
                    include_logo=True,
                )
            )
        if str(pool or "").strip() == "deep_dive" and str(article_variant or "").strip() == "project_explainer":
            constraints["source_role_order"] = ["source_article_tech_visual", "repo_readme_or_docs_visual"]
            constraints["allow_logo_fallback"] = False
        return {
            **normalized,
            "intent_kind": intent_kind,
            "preferred_mode": preferred_mode,
            "mode": self._preferred_mode_to_mode(preferred_mode),
            "purpose": execution_type,
            "brief": brief,
            "allowed_families": allowed_families,
            "constraints": constraints,
            "fallback_generate_brief": {},
            "required": index == 0,
        }

    def _normalize_decision_item(self, *, item: dict[str, Any], profile: dict[str, Any], subtype: str) -> dict[str, Any]:
        raw_slots = dict(item.get("subject_slots") or {})
        subject_slots: dict[str, dict[str, Any]] = {}
        for key in self.SUBJECT_KEYS:
            raw_entry = raw_slots.get(key)
            if isinstance(raw_entry, dict):
                name = LocalizationService.localize_visual_text(str(raw_entry.get("name", "") or "").strip())
                priority = self._normalize_priority(raw_entry.get("priority", "disabled"))
            else:
                name = LocalizationService.localize_visual_text(str(item.get(key, "") or "").strip())
                priority = self._normalize_priority((item.get(f"{key}_priority") or "").strip() if isinstance(item.get(f"{key}_priority"), str) else "")
            if not priority:
                priority = self._normalize_priority(dict(profile.get("default_subject_priorities") or {}).get(key, "disabled"))
            subject_slots[key] = {"name": name, "priority": priority}

        raw_task_priorities = dict(item.get("task_priorities") or {})
        task_priorities: dict[str, str] = {}
        for key in self.TASK_KEYS:
            raw_value = raw_task_priorities.get(key)
            if not isinstance(raw_value, str):
                raw_value = item.get(f"{key}_priority", "")
            normalized_priority = self._normalize_priority(raw_value)
            if not normalized_priority:
                normalized_priority = self._normalize_priority(dict(profile.get("default_task_priorities") or {}).get(key, "disabled"))
            task_priorities[key] = normalized_priority

        intent_kind = self._normalize_intent_kind(item.get("intent_kind", ""))
        if not intent_kind:
            intent_kind = self._best_priority(task_priorities, self.TASK_KEYS)
        preferred_mode = self._normalize_preferred_mode(item.get("preferred_mode", "") or item.get("mode", ""))
        subject_ref = dict(item.get("subject_ref") or {})
        if not subject_ref:
            subject_ref = self._best_subject_ref(subject_slots=subject_slots)

        anchor_heading = LocalizationService.localize_visual_text(
            str(item.get("anchor_heading", "") or (item.get("brief") or {}).get("section", "") or "").strip()
        )
        section_role = str(item.get("section_role", "") or "").strip() or self._section_role_from_heading(anchor_heading)
        visual_goal = LocalizationService.localize_visual_text(str(item.get("visual_goal", "") or "").strip())
        visual_claim = LocalizationService.localize_visual_text(str(item.get("visual_claim", "") or "").strip())
        evidence_refs = [str(entry).strip() for entry in (item.get("evidence_refs") or []) if str(entry).strip()]
        facts_to_visualize = [str(entry).strip() for entry in (item.get("facts_to_visualize") or []) if str(entry).strip()]
        return {
            "placement_key": str(item.get("placement_key", "") or "section_1").strip() or "section_1",
            "anchor_heading": anchor_heading,
            "section_role": section_role or "overview",
            "placement": str(item.get("placement", "") or "after_section").strip() or "after_section",
            "intent_kind": intent_kind or "none",
            "preferred_mode": preferred_mode or "none",
            "subject_ref": subject_ref,
            "subject_slots": subject_slots,
            "task_priorities": task_priorities,
            "visual_goal": visual_goal,
            "visual_claim": visual_claim,
            "evidence_refs": evidence_refs,
            "facts_to_visualize": facts_to_visualize,
            "constraints": dict(item.get("constraints") or {}),
            "required": bool(item.get("required", False)),
            "purpose": str(item.get("purpose", "") or "").strip(),
            "brief": dict(item.get("brief") or {}),
            "allowed_families": [str(entry).strip() for entry in (item.get("allowed_families") or []) if str(entry).strip()],
            "fallback_generate_brief": dict(item.get("fallback_generate_brief") or {}),
        }

    def _resolve_intent_kind(self, *, item: dict[str, Any], profile: dict[str, Any], first_item: bool) -> str:
        intent_kind = self._normalize_intent_kind(item.get("intent_kind", ""))
        task_priorities = dict(item.get("task_priorities") or {})
        if not intent_kind or intent_kind == "none":
            intent_kind = self._best_priority(task_priorities, profile.get("intent_order") or self.TASK_KEYS)
        if first_item and intent_kind not in set(profile.get("first_item_allowed_intents") or {}):
            intent_kind = self._best_priority(task_priorities, profile.get("intent_order") or self.TASK_KEYS, allowed=set(profile.get("first_item_allowed_intents") or {}))
        return intent_kind or "none"

    def _resolve_preferred_mode(
        self,
        *,
        item: dict[str, Any],
        intent_kind: str,
        profile: dict[str, Any],
        pool: str,
        variant: str,
        article_variant: str,
        image_candidates: list[dict[str, Any]],
        capture_targets: list[dict[str, Any]],
    ) -> str:
        if intent_kind == "none":
            return "none"
        requested = self._normalize_preferred_mode(item.get("preferred_mode", ""))
        mode_order = list(profile.get("mode_order") or [])
        subject_ref = dict(item.get("subject_ref") or {})
        has_subject = bool(str(subject_ref.get("name", "") or "").strip())
        if intent_kind == "explanatory":
            if not profile.get("allow_explanatory_generate"):
                return "none"
            return "generate" if requested == "generate" and "generate" in mode_order else "none"
        if str(pool or "").strip() == "news" and str(variant or "").strip() == "product_release_news":
            if self._has_release_acquire_candidate(image_candidates=image_candidates, include_logo=False):
                return "acquire" if "acquire" in mode_order else "none"
            if capture_targets and profile.get("allow_capture"):
                return "capture"
            if self._has_release_acquire_candidate(image_candidates=image_candidates, include_logo=True):
                return "acquire" if "acquire" in mode_order else "none"
            return "none"
        if str(pool or "").strip() == "deep_dive" and str(article_variant or "").strip() == "project_explainer":
            if self._has_project_explainer_acquire_candidate(image_candidates=image_candidates):
                return "acquire" if "acquire" in mode_order else "none"
            if capture_targets and profile.get("allow_capture"):
                return "capture"
            return "none"
        if requested in {"acquire", "capture"}:
            if requested == "capture" and capture_targets and profile.get("allow_capture"):
                return "capture"
            if requested == "acquire":
                return "acquire"
        if image_candidates:
            return "acquire" if "acquire" in mode_order else "none"
        if capture_targets and profile.get("allow_capture") and subject_ref.get("kind") in {"page", "product", "project"}:
            return "capture"
        if has_subject and "acquire" in mode_order:
            return "acquire"
        return "none"

    def _build_execution_brief(
        self,
        *,
        item: dict[str, Any],
        intent_kind: str,
        preferred_mode: str,
        pool: str,
        subtype: str,
        profile: dict[str, Any],
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        subject_ref: dict[str, Any],
    ) -> dict[str, Any]:
        anchor_heading = str(item.get("anchor_heading", "") or "").strip()
        visual_goal = str(item.get("visual_goal", "") or "").strip()
        title_seed = str(topic.get("title", "") or fact_pack.get("topic_title", "") or "").strip()
        subject_name = LocalizationService.localize_visual_text(str(subject_ref.get("name", "") or "").strip())
        section_text = LocalizationService.localize_visual_text(anchor_heading or str(item.get("section_role", "") or "").strip())
        if intent_kind == "explanatory":
            visual_type = self._resolve_explanatory_type(pool=pool, subtype=subtype, anchor_heading=anchor_heading, profile=profile)
            return {
                "type": visual_type,
                "section": section_text,
                "title": LocalizationService.localize_visual_text(subject_name or title_seed[:48] or section_text),
                "caption": LocalizationService.localize_visual_text(str(item.get("visual_claim", "") or "").strip()),
                "must_show": [entry for entry in list(item.get("facts_to_visualize") or []) if str(entry).strip()][:4],
                "must_avoid": ["photorealistic fake photo", "robot face", "watermark"],
            }
        if preferred_mode == "capture":
            visual_type = "product_screenshot" if subject_ref.get("kind") in {"page", "product", "project"} else "reference_image"
            caption = section_text or subject_name or "页面截图"
            return {
                "type": visual_type,
                "section": section_text,
                "title": LocalizationService.localize_visual_text(subject_name or title_seed[:48] or section_text),
                "caption": LocalizationService.localize_visual_text(caption),
                "must_show": [subject_name] if subject_name else [],
                "must_avoid": ["cropped blank page", "login wall", "watermark"],
            }
        visual_type = "news_photo" if str(pool or "").strip() == "news" else "reference_image"
        caption = subject_name or LocalizationService.localize_visual_text(str(item.get("visual_claim", "") or "").strip())
        return {
            "type": visual_type,
            "section": section_text,
            "title": LocalizationService.localize_visual_text(subject_name or title_seed[:48] or section_text),
            "caption": caption,
            "must_show": [subject_name] if subject_name else [],
            "must_avoid": ["watermark", "robot face"],
        }

    def _resolve_explanatory_type(self, *, pool: str, subtype: str, anchor_heading: str, profile: dict[str, Any]) -> str:
        families = [str(entry).strip() for entry in (profile.get("explanatory_families") or []) if str(entry).strip()]
        heading = str(anchor_heading or "").strip().lower()
        if "comparison_infographic" in families and any(token in heading for token in ("compare", "comparison", "difference", "trade-off", "vs", "对比", "差异")):
            return "comparison_infographic"
        if "process_explainer_infographic" in families and any(token in heading for token in ("workflow", "pipeline", "process", "step", "流程", "步骤")):
            return "process_explainer_infographic"
        if "system_layers_infographic" in families and any(token in heading for token in ("architecture", "layer", "module", "structure", "架构", "分层", "模块")):
            return "system_layers_infographic"
        if str(subtype or "").strip() == "capital_signal" and "comparison_infographic" in families:
            return "comparison_infographic"
        return families[0] if families else "system_layers_infographic"

    def _build_capture_targets_legacy(
        self,
        *,
        topic: dict[str, Any],
        web_enrich: dict[str, Any],
        pool: str,
        profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if str(pool or "").strip() != "github" or not profile.get("allow_capture"):
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
            add(topic_url, origin_type="primary", query_source="repo_readme", title="README 首屏", caption="仓库首页或 README 首屏截图")

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

    def _build_capture_targets(
        self,
        *,
        topic: dict[str, Any],
        web_enrich: dict[str, Any],
        image_candidates: list[dict[str, Any]],
        pool: str,
        variant: str,
        article_variant: str,
        profile: dict[str, Any],
        fact_pack: dict[str, Any],
        source_structure: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not profile.get("allow_capture"):
            return []
        normalized_pool = str(pool or "").strip()
        targets: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(
            url: str,
            *,
            origin_type: str,
            query_source: str,
            title: str = "",
            caption: str = "",
            source_role: str = "",
            page_host: str = "",
            is_official_host_value: bool = False,
        ) -> None:
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
                    "source_role": str(source_role or "").strip(),
                    "page_host": str(page_host or urlparse(normalized).netloc.lower()).strip(),
                    "is_official_host": bool(is_official_host_value),
                }
            )

        if normalized_pool == "github":
            topic_url = str(topic.get("url", "") or "").strip()
            if topic_url:
                add(
                    topic_url,
                    origin_type="primary",
                    query_source="repo_readme",
                    title="README 棣栧睆",
                    caption="浠撳簱棣栭〉鎴?README 棣栧睆鎴浘",
                    source_role="primary_source",
                )
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
                        caption="瀹樻柟椤甸潰棣栧睆鎴浘",
                        source_role="object_official",
                        is_official_host_value=True,
                    )
                elif "github.com" not in lowered:
                    add(
                        entry_url,
                        origin_type="official",
                        query_source=str(entry.get("query", "") or entry.get("title", "") or "official").strip() or "official",
                        title=str(entry.get("title", "") or "").strip(),
                        caption="瀹樼綉鎴栦骇鍝侀〉鎴浘",
                        source_role="object_official",
                        is_official_host_value=True,
                    )
            return targets[:4]

        if normalized_pool == "deep_dive" and str(article_variant or "").strip() == "project_explainer":
            repo_url = str(fact_pack.get("github_repo_url", "") or "").strip()
            if repo_url:
                add(
                    repo_url,
                    origin_type="official",
                    query_source="repo_readme",
                    title=str(fact_pack.get("project_subject", "") or topic.get("title", "") or "").strip(),
                    caption="Repo README / docs 椤甸潰鎴浘",
                    source_role="repo_readme_or_docs_visual",
                    page_host=urlparse(repo_url).netloc.lower(),
                    is_official_host_value=True,
                )
            for candidate in list(image_candidates or [])[:12]:
                if not isinstance(candidate, dict):
                    continue
                if str(candidate.get("source_role", "") or "").strip() != "repo_readme_or_docs_visual":
                    continue
                candidate_page = str(candidate.get("source_page", "") or "").strip()
                if not candidate_page:
                    continue
                add(
                    candidate_page,
                    origin_type=str(candidate.get("origin_type", "") or "").strip() or "search",
                    query_source=str(candidate.get("query_source", "") or "").strip() or "repo_visual_page",
                    title=str(candidate.get("caption", "") or "").strip(),
                    caption="Repo / docs 椤甸潰鎴浘",
                    source_role="repo_readme_or_docs_visual",
                    page_host=str(candidate.get("page_host", "") or "").strip(),
                    is_official_host_value=True,
                )
            for entry in list((web_enrich or {}).get("official_sources") or [])[:4]:
                if not isinstance(entry, dict):
                    continue
                entry_url = str(entry.get("url", "") or "").strip()
                if not entry_url:
                    continue
                lowered = entry_url.lower()
                if "github.com/" in lowered or any(token in lowered for token in ("/docs", "docs.", "/demo", "/examples", "/playground")):
                    add(
                        entry_url,
                        origin_type="official",
                        query_source=str(entry.get("query", "") or entry.get("title", "") or "repo_official").strip() or "repo_official",
                        title=str(entry.get("title", "") or "").strip(),
                        caption="Repo / docs / demo 椤甸潰鎴浘",
                        source_role="repo_readme_or_docs_visual",
                        page_host=urlparse(entry_url).netloc.lower(),
                        is_official_host_value=True,
                    )
            return targets[:4]

        if normalized_pool != "news" or str(variant or "").strip() != "product_release_news":
            return []

        official_hosts = collect_official_hosts(web_enrich=web_enrich)
        topic_url = str(topic.get("url", "") or "").strip()
        topic_host = urlparse(topic_url).netloc.lower() if topic_url else ""
        if topic_url and topic_host and topic_host in official_hosts:
            add(
                topic_url,
                origin_type="primary",
                query_source="primary_official_page",
                title=str(topic.get("title", "") or "").strip(),
                caption="瀹樻柟涓婚〉棣栧睆鎴浘",
                source_role="object_official",
                page_host=topic_host,
                is_official_host_value=True,
            )

        for entry in list((web_enrich or {}).get("official_sources") or [])[:6]:
            if not isinstance(entry, dict):
                continue
            entry_url = str(entry.get("url", "") or "").strip()
            if not entry_url:
                continue
            add(
                entry_url,
                origin_type="official",
                query_source=str(entry.get("query", "") or entry.get("title", "") or "official").strip() or "official",
                title=str(entry.get("title", "") or "").strip(),
                caption="瀹樻柟浜у搧椤垫垨鏂囨。鎴浘",
                source_role="object_official",
                page_host=urlparse(entry_url).netloc.lower(),
                is_official_host_value=True,
            )

        for candidate in list(image_candidates or [])[:10]:
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("source_role", "") or "").strip() != "object_official":
                continue
            candidate_page = str(candidate.get("source_page", "") or "").strip()
            if not candidate_page:
                continue
            add(
                candidate_page,
                origin_type=str(candidate.get("origin_type", "") or "").strip(),
                query_source=str(candidate.get("query_source", "") or "").strip() or "official_candidate_page",
                title=str(candidate.get("caption", "") or "").strip(),
                caption="瀹樻柟椤甸潰鎴浘",
                source_role="object_official",
                page_host=str(candidate.get("page_host", "") or "").strip(),
                is_official_host_value=bool(candidate.get("is_official_host", False)),
            )
        return targets[:4]

    def _has_release_acquire_candidate(self, *, image_candidates: list[dict[str, Any]], include_logo: bool) -> bool:
        for candidate in list(image_candidates or []):
            if not isinstance(candidate, dict):
                continue
            source_role = str(candidate.get("source_role", "") or "").strip()
            if source_role not in {"primary_source", "object_official"}:
                continue
            image_kind = str(candidate.get("image_kind", "") or "").strip().lower()
            if image_kind == "logo" and not (include_logo and source_role == "object_official"):
                continue
            return True
        return False

    def _has_project_explainer_acquire_candidate(self, *, image_candidates: list[dict[str, Any]]) -> bool:
        for candidate in list(image_candidates or []):
            if not isinstance(candidate, dict):
                continue
            source_role = str(candidate.get("source_role", "") or "").strip()
            if source_role not in {"source_article_tech_visual", "repo_readme_or_docs_visual"}:
                continue
            image_kind = str(candidate.get("image_kind", "") or "").strip().lower()
            if image_kind in {"logo", "portrait", "photo"}:
                continue
            return True
        return False

    def _best_subject_ref(self, *, subject_slots: dict[str, dict[str, Any]]) -> dict[str, Any]:
        best_key = ""
        best_value = -1
        for key, payload in subject_slots.items():
            priority = self.PRIORITY_VALUE.get(str(payload.get("priority", "disabled") or "disabled"), 0)
            name = str(payload.get("name", "") or "").strip()
            if not name or priority <= best_value:
                continue
            best_key = key
            best_value = priority
        if not best_key:
            return {}
        return {"kind": best_key.replace("_subject", ""), "name": str(subject_slots.get(best_key, {}).get("name", "") or "").strip()}

    def _best_priority(self, priorities: dict[str, str], keys: tuple[str, ...] | list[str], allowed: set[str] | None = None) -> str:
        best_key = "none"
        best_value = -1
        allowed_set = set(allowed or keys)
        for key in keys:
            if key not in allowed_set:
                continue
            value = self.PRIORITY_VALUE.get(str(priorities.get(key, "disabled") or "disabled"), 0)
            if value > best_value:
                best_key = key
                best_value = value
        return best_key if best_value > 0 else ("none" if "none" in allowed_set else "")

    @staticmethod
    def _normalize_priority(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {"high", "medium", "low", "disabled"} else ""

    @staticmethod
    def _normalize_intent_kind(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {"reference", "evidence", "explanatory", "none"} else ""

    @staticmethod
    def _normalize_preferred_mode(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {"acquire", "capture", "generate", "none"} else ""

    @staticmethod
    def _preferred_mode_to_mode(preferred_mode: str) -> str:
        if preferred_mode == "acquire":
            return "crawl"
        return preferred_mode

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
        if any(token in value for token in ("architecture", "架构", "模块", "分层")):
            return "architecture"
        if any(token in value for token in ("workflow", "pipeline", "process", "流程", "步骤")):
            return "workflow"
        return "overview"
