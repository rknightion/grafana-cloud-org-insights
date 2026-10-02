"""Configured integration counts, not integration activity or usage. Zero series."""
from collections.abc import Mapping, Sequence
from typing import Any


def build(stacks: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any] | None):
    rows = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        record = (inventory or {}).get(slug) or {}
        count = record.get("integration_count")
        if record.get("available") is True and type(count) is int and count >= 0:
            rows.append({"Stack": slug, "Configured IRM integrations": count})
    return [], {"irm_integrations": rows} if rows else {}
