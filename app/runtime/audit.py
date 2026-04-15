from __future__ import annotations

from typing import Any


def record_node_audit(state: dict[str, Any], node_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    audits = dict(state.get("node_audits") or {})
    existing = dict(audits.get(node_name) or {})
    existing.update({key: value for key, value in payload.items() if value not in (None, "", [], {})})
    audits[node_name] = existing
    return audits

