"""Point-in-time SLO inventory. No new time series and no identity-bearing detail."""
from collections.abc import Mapping, Sequence
from typing import Any

VIEW = "coverage_slo_inventory"
SCHEMA = (
    ("Stack", "string"), ("SLO definitions", "number"),
    ("Configured alerting", "number"), ("Metrics source", "number"),
    ("Knowledge graph source", "number"), ("Unknown source", "number"),
    ("Created status", "number"), ("Updated status", "number"),
    ("Unknown status", "number"),
)


def build(stacks: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any] | None):
    if not inventory:
        return [], {}
    rows = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        record = inventory.get(slug) or {}
        if not record.get("available"):
            continue
        sources = record["source_counts"]
        statuses = record["status_counts"]
        rows.append({
            "Stack": slug,
            "SLO definitions": record["count"],
            "Configured alerting": record["configured_alerting_count"],
            "Metrics source": sources["metrics"],
            "Knowledge graph source": sources["knowledge_graph"],
            "Unknown source": sources["unknown"],
            "Created status": statuses["created"],
            "Updated status": statuses["updated"],
            "Unknown status": statuses["unknown"],
        })
    return [], {VIEW: rows} if rows else {}
