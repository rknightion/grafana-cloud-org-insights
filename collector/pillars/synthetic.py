"""Point-in-time minimized Synthetic check/probe inventory. No new series."""
from collector.sources.synthetic import CHECK_TYPES

VIEW = "coverage_synthetic_inventory"
SCHEMA = (("Stack", "string"), ("Checks", "number"), ("Enabled checks", "number"),
          *((f"{kind} checks", "number") for kind in CHECK_TYPES),
          ("Public probes", "number"), ("Private probes", "number"))


def build(stacks, inventory):
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
        rows.append({"Stack": slug, "Checks": record["check_count"],
                     "Enabled checks": record["enabled_count"],
                     **{f"{kind} checks": record["check_type_counts"][kind] for kind in CHECK_TYPES},
                     "Public probes": record["probe_counts"]["public"],
                     "Private probes": record["probe_counts"]["private"]})
    return [], {VIEW: rows} if rows else {}
