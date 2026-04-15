from __future__ import annotations

from app.runtime.audit import record_node_audit


def build_plan_sections_node(agent):
    def _node(state: dict) -> dict:
        bootstrap = dict(state.get("bootstrap_context") or {})
        fact_compress = dict(state.get("fact_compress") or bootstrap.get("fact_compress") or {})
        section_plan, audit = agent.plan(
            topic=dict(bootstrap.get("selected_topic") or {}),
            fact_pack=dict(state.get("fact_pack") or {}),
            fact_compress=fact_compress,
            intent=state["article_intent"],
        )
        output = dict(state)
        output.update(
            {
                "fact_compress": fact_compress,
                "section_plan": section_plan,
                "plan_attempts": int(state.get("plan_attempts", 0) or 0) + 1,
                "node_audits": record_node_audit(state, "PLAN_SECTIONS", audit),
            }
        )
        return output

    return _node
