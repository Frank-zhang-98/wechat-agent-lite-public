from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext
from app.runtime.state_models import ArticleIntent


class ClassifierAgent:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    def classify(self, *, run_id: str, bootstrap_context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], ArticleIntent, dict[str, Any]]:
        support = self.ctx.support
        forced_pool = self._resolve_target_pool(bootstrap_context)
        default_audience = support.settings.get("writing.default_audience", "ai_product_manager").strip() or "ai_product_manager"
        fact_pack = support.writing_templates.build_fact_pack(bootstrap_context, audience_key=default_audience)
        fact_compress = self._build_fact_compress(
            run_id=run_id,
            bootstrap_context=bootstrap_context,
            fact_pack=fact_pack,
        )
        pool = forced_pool or str(fact_pack.get("primary_pool", "") or "deep_dive").strip() or "deep_dive"
        policy = self.ctx.policy_registry.get(pool)
        topic = dict(bootstrap_context.get("selected_topic") or {})
        subtype = policy.normalize_subtype(policy.subtype(topic=topic, fact_pack=fact_pack))
        subtype_label = policy.subtype_label(subtype)
        target_audience = self._resolve_audience(
            support=support,
            policy=policy,
            subtype=subtype,
            default_audience=default_audience,
        )
        if target_audience != default_audience:
            fact_pack = support.writing_templates.build_fact_pack(bootstrap_context, audience_key=target_audience)
            fact_pack["primary_pool"] = pool
            fact_pack["primary_pool_label"] = support._topic_pool_label(pool)
            fact_pack["subtype"] = subtype
            fact_pack["subtype_label"] = subtype_label
        fact_pack["primary_pool"] = pool
        fact_pack["primary_pool_label"] = support._topic_pool_label(pool)
        fact_pack["subtype"] = subtype
        fact_pack["subtype_label"] = subtype_label
        intent = ArticleIntent(
            pool=pool,
            subtype=subtype,
            core_angle=policy.core_angle(topic=topic, fact_pack=fact_pack, fact_compress=fact_compress),
            audience=target_audience,
            subtype_label=subtype_label,
            must_avoid=list(policy.banned_heading_phrases),
        )
        return fact_pack, fact_compress, intent, {
            "summary": {
                "pool": intent.pool,
                "subtype": intent.subtype,
                "subtype_label": intent.subtype_label,
                "audience": intent.audience,
            },
            "outputs": [
                {"title": "runtime_classifier", "text": str(intent.as_dict()), "language": "json"},
                {"title": "runtime_fact_compress", "text": str(fact_compress), "language": "json"},
            ],
        }

    @staticmethod
    def _resolve_target_pool(bootstrap_context: dict[str, Any]) -> str:
        direct = str(bootstrap_context.get("target_pool", "") or "").strip().lower()
        if direct in {"news", "github", "deep_dive"}:
            return direct
        nested = str(
            (bootstrap_context.get("trigger_request") or {}).get("target_pool", "")
            or ""
        ).strip().lower()
        if nested in {"news", "github", "deep_dive"}:
            return nested
        return ""

    @staticmethod
    def _resolve_audience(*, support, policy, subtype: str, default_audience: str) -> str:
        if not support.settings.get_bool("writing.auto_switch_audience", True):
            return default_audience
        normalized_subtype = str(subtype or "").strip()
        return policy.default_audience_for_subtype(normalized_subtype, fallback=default_audience)

    def _build_fact_compress(
        self,
        *,
        run_id: str,
        bootstrap_context: dict[str, Any],
        fact_pack: dict[str, Any],
    ) -> dict[str, Any]:
        existing = dict(bootstrap_context.get("fact_compress") or {})
        if existing:
            return existing
        support = self.ctx.support
        source_pack = dict(bootstrap_context.get("source_pack") or {})
        fact_grounding = dict(bootstrap_context.get("fact_grounding") or {})
        prompt = (
            "You are a factual analyst. Read the source pack and fact pack, then output strict JSON in simplified Chinese. "
            "Do not write prose outside JSON.\n\n"
            "Return keys: one_sentence_summary, what_it_is, key_mechanisms, concrete_scenarios, numbers, risks, uncertainties, recommended_angle.\n"
            "If article_variant is project_explainer, also return: component_points, evaluation_points, benchmark_points, implementation_chain, repo_assets.\n"
            "Each value must be an array except one_sentence_summary which must be a string.\n"
            "Only keep high-confidence facts grounded in the provided materials. If unsure, put it into uncertainties.\n\n"
            f"Source Pack:\n{support._clip_text(source_pack, 6000)}\n\n"
            f"Fact Pack:\n{support._clip_text(fact_pack, 4000)}\n\n"
            f"Fact Grounding:\n{support._clip_text(fact_grounding, 4000)}"
        )
        result = support.llm.call(run_id, "FACT_COMPRESS", "decision", prompt, temperature=0.1)
        return support._parse_fact_compress_result(result.text, fact_pack)
