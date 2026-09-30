"""Point-in-time Adaptive Traces inventory: counts and bounded states, no business series.

Adaptive Profiles remains uncollected: its inventory is outside the approved family and the
existing task records insufficient adoption to justify a separate collector.
"""
from __future__ import annotations

from typing import Any

from collector.sources.adaptive_traces import POLICY_TYPES

VIEW = "coverage_adaptive_traces_inventory"
VIEW_SCHEMAS = {
    VIEW: (
        ("Stack", "string"), ("region", "string"), ("config_available", "boolean"),
        ("config_state", "string"), ("policies_state", "string"),
        ("recommendations_state", "string"), ("policy_count", "number"),
        ("recommendation_count", "number"), ("pending_recommendation_count", "number"),
        *((f"policies_{kind}", "number") for kind in POLICY_TYPES),
    ),
}


def build(stacks: list[dict[str, Any]], data: dict[str, Any] | None):
    if not stacks or not data:
        return [], {}
    rows = []
    for stack in stacks:
        record = data.get(str(stack.get("slug"))) or {}
        if stack.get("status") == "paused" or not record.get("available"):
            continue
        counts = record.get("policy_type_counts") or {}
        rows.append({
            "Stack": str(stack["slug"]), "region": str(stack.get("regionSlug") or ""),
            "config_available": record.get("config_available"),
            **{f"{resource}_state": record[f"{resource}_state"]
               for resource in ("config", "policies", "recommendations")},
            **{key: record.get(key) for key in (
                "policy_count", "recommendation_count", "pending_recommendation_count")},
            **{f"policies_{kind}": counts.get(kind) for kind in POLICY_TYPES},
        })
    return [], {VIEW: rows} if rows else {}
