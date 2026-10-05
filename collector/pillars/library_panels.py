"""Configured library panel counts only, never panel models, usage or rendered instances."""
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = (("Stack", "string"), ("Configured library panels", "number"))


def build(stacks: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any] | None):
    rows = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        record = (inventory or {}).get(slug) or {}
        count = record.get("library_panel_count")
        if record.get("available") is not True or type(count) is not int or count < 0:
            continue
        rows.append({"Stack": slug, "Configured library panels": count})
    return [], {"library_panels_inventory": rows} if rows else {}
