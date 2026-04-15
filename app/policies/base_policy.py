from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SectionRoleTemplate:
    role: str
    goal: str
    default_heading: str
    must_cover: tuple[str, ...] = ()
    must_avoid: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SubtypeProfile:
    subtype: str
    label: str
    default_audience: str = "ai_product_manager"
    title_mode: str = ""
    visual_mode: str = ""
    layout_name: str = ""
    is_news: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class BasePolicy:
    pool: str = "deep_dive"
    label: str = ""
    title_preferences: tuple[str, ...] = ()
    visual_preferences: tuple[str, ...] = ()
    banned_heading_phrases: tuple[str, ...] = ()
    subtype_profiles: dict[str, SubtypeProfile] = {}
    default_subtype: str = "general"

    def section_templates(self, fact_pack: dict[str, Any]) -> list[SectionRoleTemplate]:
        raise NotImplementedError

    def core_angle(self, *, topic: dict[str, Any], fact_pack: dict[str, Any], fact_compress: dict[str, Any]) -> str:
        candidates = [
            str(fact_compress.get("recommended_angle", "") or "").strip(),
            str(fact_compress.get("one_sentence_summary", "") or "").strip(),
            str(topic.get("summary", "") or "").strip(),
            str(topic.get("title", "") or "").strip(),
        ]
        for item in candidates:
            if item:
                return item
        return str(topic.get("title", "") or "核心角度").strip() or "核心角度"

    def subtype(self, *, topic: dict[str, Any], fact_pack: dict[str, Any]) -> str:
        return self.default_subtype

    def allowed_subtypes(self) -> tuple[str, ...]:
        values = tuple(str(item or "").strip() for item in self.subtype_profiles.keys())
        return tuple(item for item in values if item) or (self.default_subtype,)

    def normalize_subtype(self, subtype: str) -> str:
        token = str(subtype or "").strip()
        if token in self.allowed_subtypes():
            return token
        return self.default_subtype

    def subtype_label(self, subtype: str) -> str:
        return self.profile(subtype).label

    def profile(self, subtype: str) -> SubtypeProfile:
        normalized = self.normalize_subtype(subtype)
        profile = self.subtype_profiles.get(normalized)
        if profile:
            return profile
        return SubtypeProfile(subtype=normalized, label=normalized)

    def default_audience_for_subtype(self, subtype: str, *, fallback: str = "ai_product_manager") -> str:
        return str(self.profile(subtype).default_audience or fallback).strip() or fallback

    def title_mode_for_subtype(self, subtype: str, *, fallback: str = "") -> str:
        return str(self.profile(subtype).title_mode or fallback).strip()

    def visual_mode_for_subtype(self, subtype: str, *, fallback: str = "") -> str:
        return str(self.profile(subtype).visual_mode or fallback).strip()

    def layout_name_for_subtype(self, subtype: str, *, fallback: str = "") -> str:
        return str(self.profile(subtype).layout_name or fallback).strip()

    def is_news_subtype(self, subtype: str) -> bool:
        return bool(self.profile(subtype).is_news)

    def default_audience(self, *, fact_pack: dict[str, Any], bootstrap_context: dict[str, Any]) -> str:
        return str(
            fact_pack.get("audience_key")
            or bootstrap_context.get("target_audience")
            or "ai_product_manager"
        ).strip()


class PolicyRegistry:
    def __init__(self, policies: list[BasePolicy]):
        self._policies = {policy.pool: policy for policy in policies}

    def get(self, pool: str) -> BasePolicy:
        return self._policies.get(str(pool or "").strip(), self._policies["deep_dive"])
