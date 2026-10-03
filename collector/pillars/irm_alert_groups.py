"""API-default-window IRM alert-group count, relation and population; no product series."""
from collections.abc import Mapping, Sequence
from typing import Any

RELATIONS = frozenset({"exact", "at_least"})
POPULATIONS = frozenset({"api_default_window"})


def build(stacks: Sequence[Mapping[str, Any]], inventory: Mapping[str, Any] | None):
    rows = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        record = (inventory or {}).get(slug) or {}
        count = record.get("alert_group_count")
        relation = record.get("relation")
        population = record.get("population")
        if (record.get("available") is not True or type(count) is not int or count < 0
                or not isinstance(relation, str) or relation not in RELATIONS
                or not isinstance(population, str) or population not in POPULATIONS):
            continue
        rows.append({
            "Stack": slug,
            "IRM alert groups": count,
            "Relation": relation,
            "Population": population,
        })
    return [], {"irm_alert_groups": rows} if rows else {}
