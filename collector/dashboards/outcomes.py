"""Opt-in presentation of the observer's bounded, private outcome evidence."""
from __future__ import annotations

import json

from collector.dashboards import build

RECEIPT_VIEWS = (
    "cost_summary", "usage_summary", "risk_summary", "value_summary", "coverage_summary",
)
COLUMNS = (
    ("tier", "Tier", "string"),
    ("evidence", "Evidence", "string"),
    ("observation", "Observer query state", "string"),
    ("freshness", "Observer status freshness", "string"),
    ("age", "Observer age (s)", "number"),
    ("state", "Latest observed outcome", "string"),
    ("reason", "Recorded reason", "string"),
    ("observed_at", "Recorded outcome at", "string"),
    ("count", "Observed inventory count", "number"),
    ("last_success_at", "Historical successful evidence at", "string"),
    ("last_success_count", "Historical inventory count", "number"),
    ("membership", "Current membership", "string"),
)
HELP = (
    "This separate observer reads bounded task-log evidence, not the live Grafana estate. "
    "Latest observed outcome is not the actual latest outcome. Observer status expires after one hour; "
    "dated successful evidence is retained for at most three days with its original timestamp. "
    "An older successful observation does not clear a newer failure, gap or conflict. "
    "Inventory counts describe a recorded discovery only; current membership and visibility stay unknown. "
    "The five summary receipts are collector acknowledgements for recorded digests, not proof of the "
    "current remote object or a storage-service receipt. Other views have no receipt coverage here. "
    "Missing objects, access failures and malformed timestamps remain query errors or Unknown, never zero. "
    "This section is deployment-wide and does not follow the Stack selector."
)


def selector(tier: str) -> str:
    """Return JSONata over one exact observer projection, excluding private replay material."""
    # Infinity's backend evaluates both sides of logical and; nullable comparisons
    # must be selected by a conditional rather than preceded by a type guard.
    # Its ISO parser truncates +00:00 timestamps to midnight; canonical UTC Z
    # retains the time and fractional seconds without changing the instant.
    if tier not in ("t1", "t2", "t3", "t4"):
        raise ValueError("unsupported outcome tier")
    return f'''(
  $age := function($stamp) {{ (
    $n := $type($stamp) = "string" ? ($millis() - $toMillis($replace($stamp, /\\+00:00$/, "Z"))) / 1000 : null;
    $type($n) = "number" ? ($n >= -300 ? $max([0, $n]) : null) : null
  ) }};
  $valid := meta.version = 1 and meta.tier = {json.dumps(tier)};
  $elapsed := $valid ? $age(meta.observation_completed_at) : null;
  $fresh := $type($elapsed) = "number" ? $elapsed <= 3600 : false;
  $rows := $valid and $type(rows) = "array" ? rows : [];
  $items := {json.dumps([{"kind": "attempt", "view": None}, {"kind": "inventory", "view": None}] + [{"kind": "view", "view": name} for name in RECEIPT_VIEWS])};
  $map($items, function($item) {{ (
    $matches := $filter($rows, function($r) {{ $r.kind = $item.kind and
      ($item.kind != "view" or $r.view = $item.view) }});
    $r := $count($matches) = 1 ? $matches[0] : $item;
    $observedAge := $age($r.observed_at);
    $successAge := $age($r.last_success_at);
    $dated := $type($observedAge) = "number" ? $observedAge <= 259200 : false;
    $historical := $type($successAge) = "number" ? $successAge <= 259200 : false;
    {{
      "tier": {json.dumps(tier.upper())},
      "evidence": $r.kind = "attempt" ? "Latest observed attempt" :
        ($r.kind = "inventory" ? "Recorded inventory" : $r.view),
      "observation": meta.observation_state in ["complete", "partial", "unavailable"] ?
        meta.observation_state : "unknown",
      "freshness": $fresh ? "Within 1h" :
        ($type($elapsed) = "number" ? "Stale observer status" : "Unknown observer freshness"),
      "age": $elapsed,
      "state": $dated and $r.state in ["unknown", "running", "incomplete", "ambiguous", "success", "failed", "acknowledged"] ?
        ($r.state = "acknowledged" ? "Collector acknowledgement" : $r.state) : "unknown",
      "reason": $r.reason in ["none", "not_observed", "expired", "gap", "conflict", "read_failed", "empty", "scan_failed", "exception", "cap"] ?
        $r.reason : "unknown",
      "observed_at": $dated ? $r.observed_at : null,
      "count": $dated and $r.kind = "inventory" ? ($type($r.count) = "number" ? ($r.count > 0 ? $r.count : null) : null) : null,
      "last_success_at": $historical ? $r.last_success_at : null,
      "last_success_count": $historical and $r.kind = "inventory" ? ($type($r.last_success_count) = "number" ? ($r.last_success_count > 0 ? $r.last_success_count : null) : null) : null,
      "membership": "Unknown"
    }}
  ) }})[]
)'''


def elements(ds: str) -> dict:
    panels = {"_outcome_help": build.text_panel("Collector outcome evidence", HELP)}
    for tier in ("t1", "t2", "t3", "t4"):
        query = build.data_query(build.INFINITY_TYPE, ds, {
            "type": "json", "source": "url", "format": "table", "parser": "backend",
            "root_selector": selector(tier),
            "columns": [{"selector": key, "text": label, "type": kind}
                        for key, label, kind in COLUMNS],
            "url": f"{build.bucket_url()}/views/outcomes/{tier}.json",
            "url_options": {"method": "GET"},
        }, "A")
        panels[f"_outcome_{tier}"] = build._panel(
            f"{tier.upper()} | Latest observed outcomes and dated successes", HELP, [query],
            build.viz("table", {
                "options": {"showHeader": True, "footer": {"show": False, "fields": []}},
                "fieldConfig": {"defaults": {"noValue": "Unknown"}, "overrides": [
                    {"matcher": {"id": "byName", "options": "Observer age (s)"},
                     "properties": [{"id": "unit", "value": "s"}]},
                ]},
            }),
        )
    return panels


def tab() -> dict:
    return build.rows_tab("Collector outcomes", [
        build.row("How to read outcome evidence", ["_outcome_help"], max_columns=1),
        *[build.row(f"{tier.upper()} observed evidence", [f"_outcome_{tier}"], max_columns=1)
          for tier in ("t1", "t2", "t3", "t4")],
    ])
