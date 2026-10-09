"""Private S3 producer rows and minimized alerting counts; zero product metrics.

Complete is a valid bounded response, never exhaustive coverage. Raw Loki service
names are allowed only in the private input and this view under D-VOL20.
"""
from __future__ import annotations

VIEW_SCHEMAS = {
    "loki_volume_top_services": (
        ("Stack", "string"), ("Service", "string"), ("Bytes", "number"),
        ("Window seconds", "number"), ("Limit", "number"),
        ("Returned producers", "number"), ("At limit", "boolean"),
        ("Total bytes", "number"), ("Other bytes", "number"),
        ("Response state", "string"),
    ),
    "alerting_rule_inventory": (
        ("Stack", "string"), ("Family", "string"), ("Response state", "string"),
        ("Rule groups", "number"), ("Alerting rules", "number"), ("Recording rules", "number"),
        ("Firing", "number"), ("Pending", "number"), ("Active", "number"),
        ("Suppressed", "number"), ("Unprocessed", "number"),
        ("Active silences", "number"), ("Pending silences", "number"), ("Expired silences", "number"),
    ),
}
RULE_COLUMNS = {
    "rule_groups": "Rule groups", "alerting_rules": "Alerting rules", "recording_rules": "Recording rules",
    "firing": "Firing", "pending": "Pending", "active": "Active", "suppressed": "Suppressed",
    "unprocessed": "Unprocessed", "silences_active": "Active silences",
    "silences_pending": "Pending silences", "silences_expired": "Expired silences",
}


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _volume_producers(record):
    """Hydrated payloads must keep the frozen source's bounded row contract.

    Reject the whole malformed observation: filtering individual items would
    present a corrupt payload as a valid smaller response (or a measured zero).
    """
    rows = record.get("rows")
    if not isinstance(rows, list) or len(rows) > 100:
        return None
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"service_name", "bytes"}:
            return None
        name = row["service_name"]
        if not isinstance(name, str) or not name or name in seen or _count(row["bytes"]) is None:
            return None
        seen.add(name)
    return rows


def build(stacks, loki_volume=None, rule_inventory=None):
    volume_rows, rule_rows = [], []
    volumes = (loki_volume or {}).get("stacks", {})
    rules = (rule_inventory or {}).get("stacks", {})
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or str(stack.get("status", "")).lower() == "paused":
            continue
        volume = volumes.get(slug) or {}
        producers = _volume_producers(volume) if volume.get("state") == "complete" else None
        if producers is not None:
            # An empty selected response measures no returned producers, not zero total bytes.
            for producer in producers or [{"service_name": None, "bytes": None}]:
                volume_rows.append({
                    "Stack": slug, "Service": producer.get("service_name"), "Bytes": _count(producer.get("bytes")),
                    "Window seconds": 86400, "Limit": 100, "Returned producers": len(producers),
                    "At limit": len(producers) == 100, "Total bytes": None, "Other bytes": None,
                    "Response state": "complete",
                })
        for family in ("mimir", "loki", "alertmanager"):
            record = (rules.get(slug) or {}).get(family) or {}
            counts = {column: _count(record.get(key)) for key, column in RULE_COLUMNS.items()}
            if not any(value is not None for value in counts.values()):
                continue
            state = record.get("state")
            rule_rows.append({"Stack": slug, "Family": family,
                              "Response state": state if state in {"complete", "partial"} else "unavailable",
                              **counts})
    views = {}
    if volume_rows:
        views["loki_volume_top_services"] = volume_rows
    if rule_rows:
        views["alerting_rule_inventory"] = rule_rows
    return [], views
