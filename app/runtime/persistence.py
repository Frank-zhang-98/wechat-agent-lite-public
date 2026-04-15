from __future__ import annotations

from app.runtime.state_models import ArticlePackage


def build_graph_snapshot(package: ArticlePackage, *, trigger: str) -> dict:
    return {
        "runtime": {
            "engine": "langgraph",
            "trigger": trigger,
            "pool": package.intent.pool,
            "subtype": package.intent.subtype,
            "subtype_label": package.intent.subtype_label,
            "graph_status": "completed",
            "active_graph_node": "",
            "graph_started_at": "",
            "graph_updated_at": "",
        },
        "article_package": package.as_dict(),
    }
