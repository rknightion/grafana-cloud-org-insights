"""Point-in-time configured reports, including disabled objects. No product series."""
from collections.abc import Mapping, Sequence
from typing import Any


def build(stacks: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any] | None):
    rows = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        record = (inventory or {}).get(slug) or {}
        count = record.get("report_count")
        if record.get("available") is not True or type(count) is not int or count < 0:
            continue
        rows.append({"Stack": slug, "Configured reports": count})
    return [], {"reports_inventory": rows} if rows else {}
