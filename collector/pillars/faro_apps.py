"""Point-in-time configured Faro apps by the public bounded AppType enum. Zero series."""
from collections.abc import Mapping, Sequence
from typing import Any


def build(stacks: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any] | None):
    rows = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        record = (inventory or {}).get(slug) or {}
        count, types = record.get("app_count"), record.get("app_types")
        if (record.get("available") is not True or type(count) is not int or count < 0
                or not isinstance(types, dict) or set(types) != {"web", "mobile", "unknown"}
                or any(type(n) is not int or n < 0 for n in types.values())
                or sum(types.values()) != count):
            continue
        rows.append({"Stack": slug, "Configured Faro apps": count, "Web apps": types["web"],
                     "Mobile apps": types["mobile"], "Unknown type apps": types["unknown"]})
    return [], {"faro_apps": rows} if rows else {}
