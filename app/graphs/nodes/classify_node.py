from __future__ import annotations

from app.runtime.audit import record_node_audit


def build_classify_node(agent):
    def _node(state: dict) -> dict:
        fact_pack, fact_compress, intent, audit = agent.classify(
            run_id=str(state.get("run_id") or ""),
            bootstrap_context=state.get("bootstrap_context") or {},
        )
        output = dict(state)
        output.update(
            {
                "fact_pack": fact_pack,
                "fact_compress": fact_compress,
                "article_intent": intent,
                "node_audits": record_node_audit(state, "CLASSIFY", audit),
            }
        )
        return output

    return _node
