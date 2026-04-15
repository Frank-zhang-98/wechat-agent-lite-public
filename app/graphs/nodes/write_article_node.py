from __future__ import annotations

from app.runtime.audit import record_node_audit


def build_write_article_node(agent):
    def _node(state: dict) -> dict:
        bootstrap = dict(state.get("bootstrap_context") or {})
        draft, audit = agent.write(
            run=state["run"],
            topic=dict(bootstrap.get("selected_topic") or {}),
            fact_pack=dict(state.get("fact_pack") or {}),
            fact_compress=dict(state.get("fact_compress") or {}),
            intent=state["article_intent"],
            section_plan=state["section_plan"],
            rewrite_feedback=list(state.get("rewrite_feedback") or []),
        )
        output = dict(state)
        output.update(
            {
                "article_draft": draft,
                "article_attempts": int(state.get("article_attempts", 0) or 0) + 1,
                "node_audits": record_node_audit(state, "WRITE_ARTICLE", audit),
            }
        )
        return output

    return _node
