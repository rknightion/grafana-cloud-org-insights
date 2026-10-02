"""Point-in-time configured AWS accounts only, not an all-provider total. No product series."""
from collections.abc import Mapping, Sequence
from typing import Any


def build(stacks: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any] | None):
    rows = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        record = (inventory or {}).get(slug) or {}
        count = record.get("account_count")
        if record.get("available") is not True or type(count) is not int or count < 0:
            continue
        rows.append({"Stack": slug, "Provider": "aws", "Configured accounts": count})
    return [], {"cloud_accounts": rows} if rows else {}
