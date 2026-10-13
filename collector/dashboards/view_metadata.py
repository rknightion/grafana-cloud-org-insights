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


# Existing count-only view contracts, not a source roster or a completeness declaration.
CONFIGURED_COUNTS = {
    "library_panels_inventory": "Configured library panels",
    "playlists_inventory": "Configured playlists",
    "reports_inventory": "Configured reports",
    "pdc_networks": "Configured private networks",
    "cloud_accounts": "Configured accounts",
    "ml_jobs": "Configured forecast jobs",
    "faro_apps": "Configured Faro apps",
    "irm_integrations": "Configured IRM integrations",
}
USAGE_OPTIONAL_VIEWS = frozenset(CONFIGURED_COUNTS) | {
    "irm_alert_groups", "loki_volume_top_services", "alerting_rule_inventory",
}

OPTIONAL_HELP = (
    "**Optional view state and coverage**\n\n"
    "Build-read omissions below record no object at dashboard build, with current state unknown. "
    "This is a build observation, not evidence of disabled collection or measured zero. "
    "No publication marker or input age is available for an omitted object, and it is not queried. "
    "Rebuild to discover a subsequently published object. Present or retained last-good objects "
    "keep their exact-object runtime metadata queries below. If such an object is lost after build, "
    "404 remains a visible query error with current state unknown, not measured zero. "
    "401/403, transport failures and invalid JSON remain fatal build errors or runtime query errors, "
    "never absence or empty measurements. A failed runtime query supplies no usable freshness.\n\n"
    "A retained object keeps its original composition/publication marker and input provenance. "
    "Available, disabled, partial and unavailable describe that publication only, not current source health. "
    "Missing state is unknown. Zero configured counts require known usable input and the view's count "
    "contract; an empty row list alone proves neither measured zero nor complete estate coverage. "
    "Scan coverage is shown separately and cannot certify optional-view completeness. Bounded response "
    "states and windows remain in the numeric detail; complete there is not exhaustive inventory."
)


def optional_help(absent_views: frozenset[str]) -> str:
    """Describe only known FileNotFoundError omissions from Usage's optional table builds.

    These names identify presentation contracts, not live stacks or source health. No absent
    object's URL, measurement, marker or age is synthesized; runtime metadata is for present views.
    """
    observations = "\n".join(
        f"- **{view}**: No object at build read; current state unknown."
        for view in sorted(absent_views)) or "No such build-read omissions."
    return OPTIONAL_HELP + "\n\n**Build-read omissions (not current state)**\n\n" + observations


COLUMNS = (
    ("view", "View", "string"),
    ("generated_at", "Snapshot generated at", "string"),
    ("publication_age", "Publication age (s)", "number"),
    ("input", "Input", "string"),
    ("availability", "Availability at publication", "string"),
    ("input_state", "Recorded input state (publication)", "string"),
    ("measurement", "Measurement interpretation", "string"),
    ("scan_coverage", "Publishing scan coverage (not view completeness)", "number"),
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
    count_field = CONFIGURED_COUNTS.get(view)
    zero = (f'$count($filter($rows, function($r) {{ $lookup($r, {json.dumps(count_field)}) = 0 }})) = $count($rows)'
            if count_field else 'false')
    return f'''(
  $stamp := meta.generated_at;
  $elapsed := $type($stamp) = "string" ? ($millis() - $toMillis($stamp)) / 1000 : null;
  $elapsed := $type($elapsed) = "number" and $elapsed >= -{skew:g} ? $max([0, $elapsed]) : null;
  $provenance := $type(meta.inputs) = "object" ? meta.inputs : {{}};
  $rows := $type(rows) = "array" ? rows : [];
  $allUsable := $count($filter({json.dumps(inputs)}, function($n) {{ (
    $v := $lookup($provenance, $n);
    $v.available = true and $v.stale = false and
      $not($v.state in ["disabled", "partial", "unavailable", "incompatible_schema", "future_timestamp"])
  ) }})) = {len(inputs)};
  $measurement := $not($allUsable) ? "Unknown measurement; input not known usable" :
    ($count($rows) = 0 ? "No returned rows; measurement meaning unknown" :
      ($count($rows[`Response state` in ["partial", "unavailable"]]) > 0 ?
        "Partial returned observations; unknown fields are not zero" :
        ({zero} ? "Measured zero in returned configured-count rows; estate completeness unknown" :
          "Returned observations; no generic empty or complete claim")));
  $coverage := meta.coverage_ratio;
  $map({json.dumps(inputs)}, function($name) {{ (
    $p := $lookup($provenance, $name);
    $usable := $p.available = true and $p.stale = false and
      $not($p.state in ["disabled", "partial", "unavailable", "incompatible_schema", "future_timestamp"]);
    $age := $type($p.age_seconds) = "number" and $p.age_seconds >= 0 ? $p.age_seconds : null;
    {{
      "view": {json.dumps(view)},
      "generated_at": $type($stamp) = "string" ? $stamp : null,
      "publication_age": $elapsed,
      "input": $name,
      "availability": $p.state = "disabled" ? "Disabled at publication" :
        ($p.state = "partial" ? "Partial at publication" :
          ($p.available = false ? "Unavailable at publication" :
            ($p.stale = true ? "Stale at publication" :
              ($usable ? "Available at publication" : "Unknown availability")))),
      "input_state": $type($p.state) = "string" ? $p.state : null,
      "measurement": $measurement,
      "scan_coverage": $type($coverage) = "number" and $coverage >= 0 and $coverage <= 1 ? $coverage : null,
      "age_at_publication": $usable ? $age : null,
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
        "Metadata is object-wide and does not narrow with the Stack selector. State at publication is "
        "not current source health. Recorded input state preserves the exact existing provenance "
        "state, including incompatible_schema and future_timestamp; it is blank/Unknown when no state "
        "was recorded, even for available input. It is not a new source-health observation. "
        "Explicit disabled/partial states are displayed only when recorded; "
        "absence of state never infers disabled. Measured zero is limited to returned configured-count "
        "rows with all required inputs known usable; no estate completeness follows. Empty rows alone "
        "remain unknown. HTTP 404 is missing object, not zero; 401/403, transport and parse failures "
        "remain errors, with no usable freshness. Publishing scan coverage is separate from view coverage.",
        [query], build.viz("table", {
            "options": {"showHeader": True, "footer": {"show": False, "fields": []}},
            "fieldConfig": {"defaults": {"noValue": "Unknown"}, "overrides": [
                {"matcher": {"id": "byName", "options": label},
                 "properties": [{"id": "unit", "value": "percentunit" if key == "scan_coverage" else "s"}]}
                for key, label, kind in COLUMNS if kind == "number"
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
    # Known absent optional tables have static guidance, not queries against missing objects.
    # Present tables retain their exact URL and normal failure surface without an empty fallback.
    views: set[str] = set()
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
