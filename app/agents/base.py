from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.policies import PolicyRegistry
from app.rubrics import RubricRegistry


class RuntimeSupport(Protocol):
    settings: Any
    llm: Any
    writing_templates: Any
    title_generator: Any
    visual_strategy: Any
    visual_execution_compiler: Any
    visual_renderer: Any
    image_research: Any
    visual_fit_gate: Any
    media_acquisition: Any
    page_capture: Any
    article_renderer: Any
    wechat: Any
    hallucination_checker: Any
    humanizer: Any

    def _prepare_generated_article_markdown(self, article: str, ctx: dict[str, Any]) -> str: ...
    def _writer_output_is_acceptable(self, article: str) -> bool: ...
    def _humanize_article_if_needed(
        self,
        *,
        run: Any,
        ctx: dict[str, Any],
        article: str,
        topic: dict[str, Any],
        fact_pack: dict[str, Any],
        audience_key: str,
        pool: str,
        subtype: str,
        skip_rewrite: bool,
    ) -> dict[str, Any]: ...
    def _sync_titles_from_article_markdown(self, ctx: dict[str, Any]) -> None: ...
    def _quality_hard_checks(self, article: str, fact_pack: dict[str, Any], humanizer_analysis: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def _fallback_article(self, topic: dict[str, Any]) -> str: ...


@dataclass(slots=True)
class AgentContext:
    support: RuntimeSupport
    policy_registry: PolicyRegistry
    rubric_registry: RubricRegistry
