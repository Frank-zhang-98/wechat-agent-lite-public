from __future__ import annotations

from app.runtime.audit import record_node_audit


def build_validate_plan_node(agent):
    def _node(state: dict) -> dict:
        result, audit = agent.evaluate(section_plan=state["section_plan"])
        output = dict(state)
        output.update(
            {
                "plan_evaluation": result,
                "node_audits": record_node_audit(state, "VALIDATE_PLAN", audit),
            }
        )
        return output

    return _node
