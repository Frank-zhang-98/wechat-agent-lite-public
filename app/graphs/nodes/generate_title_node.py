from __future__ import annotations

from app.runtime.audit import record_node_audit


def build_generate_title_node(agent):
    def _node(state: dict) -> dict:
        bootstrap = dict(state.get("bootstrap_context") or {})
        title_plan, audit = agent.generate(
            run_id=state["run"].id,
            topic=dict(bootstrap.get("selected_topic") or {}),
            fact_pack=dict(state.get("fact_pack") or {}),
            fact_compress=dict(state.get("fact_compress") or {}),
            intent=state["article_intent"],
            section_plan=state["section_plan"],
            draft=state["article_draft"],
        )
        output = dict(state)
        output.update(
            {
                "title_plan_state": title_plan,
                "node_audits": record_node_audit(state, "GENERATE_TITLE", audit),
            }
        )
        return output

    return _node
