"""Read-only presentation of each displayed view's existing publication provenance.

Never use another object's snapshot or Mimir's retained labels as a current membership fence.
The published envelope has no fresh inventory identity set or generic per-view completeness bit.
"""

from __future__ import annotations

import json
import re
from typing import Any

from collector.dashboards import build
from collector.emit import carry, hydrate


SNAPSHOT_HELP = (
    "This is a published historical snapshot: row membership is historical/unknown, not proven "
    "current. The Stack selector narrows retained rows only; All and historical label values are "
    "not fresh discovery. Failed inventory leaves current membership unknown, never an estate of "
    "zero. No row is excluded as departed without reliable current-inventory evidence. "
    "An empty result is not measured zero unless the relevant input was known available and the "
    "view's own measurement contract establishes that interpretation. Missing input is unavailable. "
    "See this view's publication/input metadata on How to read this, not another scan's timestamp."
)


COLUMNS = (
    ("view", "View", "string"),
    ("generated_at", "Snapshot generated at", "string"),
    ("publication_age", "Publication age (s)", "number"),
    ("input", "Input", "string"),
    ("availability", "Availability at publication", "string"),
    ("age_at_publication", "Input age at publication (s)", "number"),
    ("age_now", "Input age now (s)", "number"),
    ("membership", "Current membership", "string"),
    ("completeness", "View completeness", "string"),
)


def _selector(view: str) -> str:
    """JSONata runs when Infinity reads the object, not when we build the dashboard.

    generated_at is the envelope publication marker, not exact S3 upload or source event time.
    Retained input ages are provenance estimates anchored to that marker. Missing availability
    cannot be repaired from a recorded age or coverage_ratio. Parser errors remain explicit.
    """
    names = sorted(hydrate.VIEW_INPUTS.get(view, ()))
    inputs = names or ["Inventory (no per-input provenance)"]
    skew = carry.MAX_FUTURE_SKEW.total_seconds()
    return f'''(
  $stamp := meta.generated_at;
  $elapsed := $type($stamp) = "string" ? ($millis() - $toMillis($stamp)) / 1000 : null;
  $elapsed := $type($elapsed) = "number" and $elapsed >= -{skew:g} ? $max([0, $elapsed]) : null;
  $provenance := $type(meta.inputs) = "object" ? meta.inputs : {{}};
  $map({json.dumps(inputs)}, function($name) {{ (
    $p := $lookup($provenance, $name);
    $usable := $p.available = true and $p.stale = false;
    $age := $type($p.age_seconds) = "number" and $p.age_seconds >= 0 ? $p.age_seconds : null;
    {{
      "view": {json.dumps(view)},
      "generated_at": $type($stamp) = "string" ? $stamp : null,
      "publication_age": $elapsed,
      "input": $name,
      "availability": $p.available = false ? "Unavailable at publication" :
        ($usable ? "Available at publication" : "Unknown availability"),
      "age_at_publication": $age,
      "age_now": $usable and $type($age) = "number" and $type($elapsed) = "number" ? $age + $elapsed : null,
      "membership": "Historical snapshot; current membership unknown",
      "completeness": "Unknown; scan coverage is not per-view completeness"
    }}
  ) }})[]
)'''


def metadata_panel(view: str, ds: str) -> dict[str, Any]:
    query = build.data_query(build.INFINITY_TYPE, ds, {
        "type": "json", "source": "url", "format": "table", "parser": "backend",
        "root_selector": _selector(view),
        "columns": [{"selector": key, "text": label, "type": kind}
                    for key, label, kind in COLUMNS],
        "url": f"{build.bucket_url()}/views/{view}.json",
        "url_options": {"method": "GET"},
    }, "A")
    panel = build._panel(
        f"{view} | Publication and input provenance",
        "Metadata from this exact last-good object, read at dashboard query time. Snapshot generated "
        "at is its publication marker, not exact S3 upload time. Publication age advances at each "
        "query, independently of the latest scan. Input age now adds elapsed publication age only "
        "for known available, non-stale input provenance; these are estimates, not exact observation "
        "timestamps. Input age at publication is the recorded age, not a live freshness claim. "
        "Missing metadata yields Unknown, never zero or an age borrowed from another scan. "
        "Coverage_ratio qualifies the publishing scan, not per-view completeness or today's "
        "membership. Current membership remains unknown, including during failed inventory. "
        "No generic complete/empty claim is inferred from row count. Unavailable input ages are "
        "withheld; malformed timestamps and HTTP/access errors remain explicit query errors. "
        "Metadata is object-wide and does not narrow with the Stack selector.",
        [query], build.viz("table", {
            "options": {"showHeader": True, "footer": {"show": False, "fields": []}},
            "fieldConfig": {"defaults": {"noValue": "Unknown"}, "overrides": [
                {"matcher": {"id": "byName", "options": label},
                 "properties": [{"id": "unit", "value": "s"}]}
                for _, label, kind in COLUMNS if kind == "number"
            ]},
        }))
    panel["spec"]["data"]["spec"]["transformations"] = [
        build._organize([label for _, label, _ in COLUMNS])]
    return panel


def elements_for(elements: dict[str, Any], ds: str) -> dict[str, Any]:
    """One companion per actual referenced view, even when multiple tables use it.

    Do not read source inputs or infer membership from other view objects. This also works with
    optional/empty views and legacy objects: columns are fixed presentation, not a new schema.
    """
    views = set()
    for element in elements.values():
        panel = element["spec"]
        for wrapped in panel["data"]["spec"]["queries"]:
            query = wrapped["spec"]["query"]
            if query["group"] != build.INFINITY_TYPE:
                continue
            match = re.search(r"/views/([A-Za-z0-9_-]+)\.json$", query["spec"].get("url", ""))
            if match:
                views.add(match.group(1))
                if SNAPSHOT_HELP not in panel["description"]:
                    panel["description"] += "\n\n" + SNAPSHOT_HELP
    return {f"_meta_{view}": metadata_panel(view, ds) for view in sorted(views)}
