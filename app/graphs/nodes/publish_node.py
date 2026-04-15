from __future__ import annotations

from app.runtime.audit import record_node_audit


def build_publish_node(agent):
    def _node(state: dict) -> dict:
        bootstrap = dict(state.get("bootstrap_context") or {})
        result, draft_status, audit = agent.publish(
            topic=dict(bootstrap.get("selected_topic") or {}),
            draft=state["article_draft"],
            title_plan=state["title_plan_state"],
            visual_assets=state["visual_assets_state"],
            article_html=str(state.get("article_html") or ""),
        )
        output = dict(state)
        output.update(
            {
                "wechat_result": result,
                "draft_status": draft_status,
                "node_audits": record_node_audit(state, "PUBLISH", audit),
            }
        )
        return output

    return _node
