from __future__ import annotations

from app.runtime.audit import record_node_audit


def build_evaluate_article_node(agent):
    def _node(state: dict) -> dict:
        bootstrap = dict(state.get("bootstrap_context") or {})
        evaluation, audit = agent.evaluate(
            run_id=state["run"].id,
            fact_pack=dict(state.get("fact_pack") or {}),
            fact_grounding=dict(bootstrap.get("fact_grounding") or {}),
            intent=state["article_intent"],
            section_plan=state["section_plan"],
            draft=state["article_draft"],
        )
        output = dict(state)
        output.update(
            {
                "article_evaluation": evaluation,
                "rewrite_feedback": list(evaluation.get("feedback") or []),
                "node_audits": record_node_audit(state, "EVALUATE_ARTICLE", audit),
            }
        )
        return output

    return _node
