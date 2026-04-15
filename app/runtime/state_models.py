from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ArticleIntent:
    pool: str
    subtype: str
    core_angle: str
    audience: str
    subtype_label: str = ""
    must_avoid: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ArticleIntent":
        payload = dict(value or {})
        return cls(
            pool=str(payload.get("pool", "") or ""),
            subtype=str(payload.get("subtype", "") or ""),
            subtype_label=str(payload.get("subtype_label", "") or ""),
            core_angle=str(payload.get("core_angle", "") or ""),
            audience=str(payload.get("audience", "") or ""),
            must_avoid=[str(item) for item in (payload.get("must_avoid") or []) if str(item).strip()],
        )


@dataclass(slots=True)
class SectionSpec:
    role: str
    goal: str
    must_cover: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    heading_hint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SectionSpec":
        payload = dict(value or {})
        return cls(
            role=str(payload.get("role", "") or ""),
            goal=str(payload.get("goal", "") or ""),
            must_cover=[str(item) for item in (payload.get("must_cover") or []) if str(item).strip()],
            must_avoid=[str(item) for item in (payload.get("must_avoid") or []) if str(item).strip()],
            evidence_refs=[str(item) for item in (payload.get("evidence_refs") or []) if str(item).strip()],
            heading_hint=str(payload.get("heading_hint", "") or ""),
        )


@dataclass(slots=True)
class SectionPlan:
    pool: str
    sections: list[SectionSpec]
    strategy_label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "pool": self.pool,
            "strategy_label": self.strategy_label,
            "sections": [item.as_dict() for item in self.sections],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SectionPlan":
        payload = dict(value or {})
        return cls(
            pool=str(payload.get("pool", "") or ""),
            strategy_label=str(payload.get("strategy_label", "") or ""),
            sections=[SectionSpec.from_dict(item) for item in (payload.get("sections") or []) if isinstance(item, dict)],
        )


@dataclass(slots=True)
class ArticleDraft:
    article_markdown: str
    h1_title: str = ""
    section_outputs: list[dict[str, Any]] = field(default_factory=list)
    humanizer: dict[str, Any] = field(default_factory=dict)
    write_output_meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ArticleDraft":
        payload = dict(value or {})
        return cls(
            article_markdown=str(payload.get("article_markdown", "") or ""),
            h1_title=str(payload.get("h1_title", "") or ""),
            section_outputs=[dict(item) for item in (payload.get("section_outputs") or []) if isinstance(item, dict)],
            humanizer=dict(payload.get("humanizer") or {}),
            write_output_meta=dict(payload.get("write_output_meta") or {}),
        )


@dataclass(slots=True)
class RuntimeTitlePlan:
    article_title: str
    wechat_title: str
    title_rationale: str = ""
    source: str = "agent"
    debug: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "RuntimeTitlePlan":
        payload = dict(value or {})
        return cls(
            article_title=str(payload.get("article_title", "") or ""),
            wechat_title=str(payload.get("wechat_title", "") or ""),
            title_rationale=str(payload.get("title_rationale", "") or ""),
            source=str(payload.get("source", "") or "agent"),
            debug=dict(payload.get("debug") or {}),
        )


@dataclass(slots=True)
class VisualBlueprint:
    cover_family: str = ""
    cover_brief: dict[str, Any] = field(default_factory=dict)
    body_policy: dict[str, Any] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "VisualBlueprint":
        payload = dict(value or {})
        return cls(
            cover_family=str(payload.get("cover_family", "") or ""),
            cover_brief=dict(payload.get("cover_brief") or {}),
            body_policy=dict(payload.get("body_policy") or {}),
            items=[dict(item) for item in (payload.get("items") or []) if isinstance(item, dict)],
        )


@dataclass(slots=True)
class VisualAssetSet:
    body_assets: list[dict[str, Any]] = field(default_factory=list)
    cover_5d: dict[str, Any] = field(default_factory=dict)
    cover_asset: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "VisualAssetSet":
        payload = dict(value or {})
        return cls(
            body_assets=[dict(item) for item in (payload.get("body_assets") or []) if isinstance(item, dict)],
            cover_5d=dict(payload.get("cover_5d") or {}),
            cover_asset=dict(payload.get("cover_asset") or {}),
        )


@dataclass(slots=True)
class ArticlePackage:
    intent: ArticleIntent
    fact_pack: dict[str, Any]
    fact_compress: dict[str, Any]
    section_plan: SectionPlan
    article_draft: ArticleDraft
    title_plan: RuntimeTitlePlan
    visual_blueprint: VisualBlueprint
    visual_assets: VisualAssetSet
    visual_diagnostics: dict[str, Any] = field(default_factory=dict)
    article_layout: dict[str, Any] = field(default_factory=dict)
    article_render: dict[str, Any] = field(default_factory=dict)
    article_html: str = ""
    wechat_result: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    draft_status: str = "not_started"
    step_audits: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.as_dict(),
            "fact_pack": self.fact_pack,
            "fact_compress": self.fact_compress,
            "section_plan": self.section_plan.as_dict(),
            "article_draft": self.article_draft.as_dict(),
            "title_plan": self.title_plan.as_dict(),
            "visual_blueprint": self.visual_blueprint.as_dict(),
            "visual_assets": self.visual_assets.as_dict(),
            "visual_diagnostics": self.visual_diagnostics,
            "article_layout": self.article_layout,
            "article_render": self.article_render,
            "article_html": self.article_html,
            "wechat_result": self.wechat_result,
            "quality": self.quality,
            "draft_status": self.draft_status,
            "step_audits": self.step_audits,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ArticlePackage":
        payload = dict(value or {})
        return cls(
            intent=ArticleIntent.from_dict(payload.get("intent") if isinstance(payload.get("intent"), dict) else {}),
            fact_pack=dict(payload.get("fact_pack") or {}),
            fact_compress=dict(payload.get("fact_compress") or {}),
            section_plan=SectionPlan.from_dict(payload.get("section_plan") if isinstance(payload.get("section_plan"), dict) else {}),
            article_draft=ArticleDraft.from_dict(payload.get("article_draft") if isinstance(payload.get("article_draft"), dict) else {}),
            title_plan=RuntimeTitlePlan.from_dict(payload.get("title_plan") if isinstance(payload.get("title_plan"), dict) else {}),
            visual_blueprint=VisualBlueprint.from_dict(
                payload.get("visual_blueprint") if isinstance(payload.get("visual_blueprint"), dict) else {}
            ),
            visual_assets=VisualAssetSet.from_dict(
                payload.get("visual_assets") if isinstance(payload.get("visual_assets"), dict) else {}
            ),
            visual_diagnostics=dict(payload.get("visual_diagnostics") or {}),
            article_layout=dict(payload.get("article_layout") or {}),
            article_render=dict(payload.get("article_render") or {}),
            article_html=str(payload.get("article_html", "") or ""),
            wechat_result=dict(payload.get("wechat_result") or {}),
            quality=dict(payload.get("quality") or {}),
            draft_status=str(payload.get("draft_status", "") or "not_started"),
            step_audits=dict(payload.get("step_audits") or {}),
        )


def build_graph_state(
    *,
    run_id: str,
    trigger: str,
    bootstrap_context: dict[str, Any],
    include_cover_assets: bool,
    publish_enabled: bool,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "trigger": trigger,
        "bootstrap_context": dict(bootstrap_context or {}),
        "include_cover_assets": bool(include_cover_assets),
        "publish_enabled": bool(publish_enabled),
        "plan_attempts": 0,
        "article_attempts": 0,
        "node_audits": {},
        "rewrite_feedback": [],
    }
