"""v2 dynamic-dashboard authoring harness (PLAN 6.5a).

Dashboards are **`dashboard.grafana.app/v2`** with dynamic constructs - `TabsLayout`, `RowsLayout`,
`AutoGridLayout`. Not classic, and **not `v2alpha1`**: the supported deployment runs a Grafana version where v2 is validated, and
v2alpha1 has a different panel/query shape.

## The two things that make a v2 dashboard silently blank

1. **An orphaned `spec.elements` entry blanks the ENTIRE dashboard**, not just its panel. So
   `assert_layout_complete()` checks `set(elements) == set(placed)` in both directions and is called on
   every build. This is the single highest-value assertion in the file.
2. **Infinity needs `parser:"backend"` + explicit `columns` + `root_selector`, all three.** Measured:
   backend without `columns` returns HTTP 500; omitting `parser`, or using `"simple"`, returns 200 with
   **zero rows** - a panel that looks fine and shows nothing. `columns_for()` generates the spec from the
   real view so a dashboard cannot drift from the data it renders.

## Other traps this harness encodes

- **Datasource uids are parameterised, never hardcoded** so moving the write target is configuration.
- **`format:"table"` value columns are named `Value #<refId>`**, so field overrides use
  `byRegexp:"^Value.*"` with `footer.fields:[]`, never `byName:"Value"`.
- **Never force `query.kind:"prometheus"` on an Infinity-backed variable** - renders a 500.
- **Column order does NOT come from the `columns` array.** Infinity's backend parser returns fields
  ALPHABETISED by display text, and the views' leading-space key convention (`" Stack"`) does not beat
  it, because the parser sorts on the STRIPPED text. Measured live: `risk_admin_sprawl` returned Stack
  as field 13 of 14. Order is pinned by the `organize` transformation in `table_panel`, and that is the
  only thing that works - the leading-space keys are now merely harmless.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
from typing import Any, Iterable, Sequence

SCHEMA = "dashboard.grafana.app/v2"
INFINITY_TYPE = "yesoreyeram-infinity-datasource"

# Local generated views make dashboard builds and tests independent of AWS. A deployed build instead
# requires its bucket explicitly; there is no safe deployment default.
VIEWS_DIR = os.environ.get("GCINSIGHT_VIEWS_DIR", "").strip()
BUCKET = os.environ.get("GCINSIGHT_S3_BUCKET", "").strip()
REGION = os.environ.get("GCINSIGHT_S3_REGION", "eu-west-1").strip() or "eu-west-1"


class ViewSourceNotConfigured(RuntimeError):
    """Neither a local views directory nor a deployment bucket was supplied."""


def bucket_url() -> str:
    """Public HTTPS base baked into Infinity queries in a published dashboard."""
    if not BUCKET:
        raise ViewSourceNotConfigured("GCINSIGHT_S3_BUCKET is not set")
    return f"https://{BUCKET}.s3.{REGION}.amazonaws.com"
# The stack's own Prometheus. Our remote_write series land here, so this is where every trend comes from.
PROM_UID = "grafanacloud-prom"
# The stack's own provisioned billing datasource. Already present on every stack, so a panel can read
# it DIRECTLY - no collector, no credential, no series of ours.
#
# Three label facts govern every expression pointed here:
# * `id` is the per-SIGNAL instance id (hmInstancePromId and friends), NOT the stack. Several ids map
# to one stack, so `count(<metric>)` counts instances and overstates the stack count - always
# `sum by(stack_id)` first. Measured: `grafanacloud_instance_queries_per_second` carries 459 ids
# against 230 stack_ids.
# * `stack_id` IS the numeric stack id. It is still not the slug, so the `$stack` variable (a slug)
# cannot be used against this datasource.
# * `USAGE_INFO` below closes that gap without a collector - see its docstring.
USAGE_UID = "grafanacloud-usage"

# One series per stack carrying BOTH `stack_id` and `slug`, in the same datasource. That makes a
# stack-name lookup a plain PromQL join rather than a pipeline:
#
# topk(15, sum by(stack_id)(<metric>)) * on(stack_id) group_left(slug) <USAGE_INFO>
#
# Verified 272 series on 2026-08-18, exactly matching the estate. Without this every usage-datasource
# panel is stuck at estate-level counts, because a Grafana panel cannot join across datasources.
USAGE_INFO = "grafanacloud_grafana_instance_info"


def usage_by_slug(expr: str) -> str:
    """Wrap a `sum by(stack_id)` expression so it comes back labelled with the stack slug.

    Only valid against `USAGE_UID`. The join is `group_left` on purpose: the metric is the left side and
    keeps its value, `" + "` would add the info series' own value of 1 to every result.
    """
    return f"{expr} * on(stack_id) group_left(slug) {USAGE_INFO}"


def viz(panel_type: str, spec: dict[str, Any]) -> dict[str, Any]:
    """`vizConfig` envelope. `kind` is the literal `VizConfig`; the panel type goes in `group`.

    Writing `{"kind": "table"}` renders **"plugin not found"** for the entire page, not just the panel.
    """
    return {"kind": "VizConfig", "group": panel_type, "version": "", "spec": spec}


class OrphanedElement(AssertionError):
    """An element exists but is not placed, or vice versa. Either blanks the whole dashboard."""


class EmptyView(RuntimeError):
    """The view has no rows, so no column spec exists - and empty `columns` makes Infinity 500."""


class PanelIdCollision(ValueError):
    """Two element keys resolved to the same numeric panel id."""


_MAX_PANEL_ID = 2_147_483_647


def _panel_id(element_key: str) -> int:
    """Return a stable, positive signed-32-bit id derived only from an element key.

    Grafana persists ``spec.id`` as the panel identity used by usage-insights events. Leaving the v2
    field unset made every panel persist as id 0. Sequential ids avoid zero but are not stable when a
    panel is inserted ahead of another one; hashing the stable element key preserves every unaffected
    panel's identity across rebuilds. Collisions are checked across the complete dashboard below rather
    than silently assigning the same identity to two panels.
    """
    digest = hashlib.sha256(element_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % _MAX_PANEL_ID + 1


def _assign_panel_ids(elements: dict[str, Any]) -> None:
    """Assign deterministic, nonzero ids to every Panel in a dashboard's flat element registry."""
    ids: dict[int, str] = {}
    assignments: dict[str, int] = {}
    for key, element in elements.items():
        if element.get("kind") != "Panel":
            continue
        panel_id = _panel_id(key)
        previous = ids.get(panel_id)
        if previous is not None:
            raise PanelIdCollision(
                f"panel id collision: {previous!r} and {key!r} both map to {panel_id}"
            )
        ids[panel_id] = key
        assignments[key] = panel_id

    # Validate the complete mapping before mutating any panel, so a collision cannot leave callers with
    # a partly-normalised element registry after the build fails.
    for key, panel_id in assignments.items():
        elements[key]["spec"]["id"] = panel_id


def assert_layout_complete(elements: dict[str, Any], placed: Iterable[str]) -> None:
    """`set(elements) == set(placed)`, checked both ways.

    An element that nothing references blanks the dashboard; a reference to a missing element does the
    same. Both are easy to introduce by editing one half of a pair.
    """
    declared = set(elements)
    used = set(placed)
    if declared != used:
        raise OrphanedElement(
            f"orphaned elements {sorted(declared - used)}; "
            f"dangling references {sorted(used - declared)} - either blanks the whole dashboard"
        )


def read_view(name: str) -> dict[str, Any]:
    """Fetch a local or published view so column specs are derived, never guessed."""
    if VIEWS_DIR:
        path = pathlib.Path(VIEWS_DIR) / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"{path}: not in GCINSIGHT_VIEWS_DIR")
        return json.loads(path.read_text())
    if not BUCKET:
        raise ViewSourceNotConfigured(
            f"cannot read views/{name}.json: set GCINSIGHT_VIEWS_DIR to a local directory of views, "
            "or GCINSIGHT_S3_BUCKET to the deployed bucket"
        )
    proc = subprocess.run(
        ["aws", "s3", "cp", f"s3://{BUCKET}/views/{name}.json", "-", "--region", REGION],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise FileNotFoundError(f"views/{name}.json: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def _infer_type(values: Sequence[Any]) -> str:
    """Infinity column types: `string`, `number`, `boolean`, `timestamp`.

    A column that is entirely None is typed `string` - `number` would make Grafana render "NaN" where the
    honest answer is blank, and these views use None to mean "not measurable" on purpose.
    """
    seen = [v for v in values if v is not None]
    if not seen:
        return "string"
    if all(isinstance(v, bool) for v in seen):
        return "boolean"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in seen):
        return "number"
    return "string"


def columns_for(view: dict[str, Any],
                fallback: Sequence[tuple[str, str]] | None = None) -> list[dict[str, str]]:
    """Generate Infinity's `columns` from the view's own rows, preserving key order.

    Required: without it the backend parser 500s. Generated rather than written by hand so a pillar
    adding a column cannot leave a dashboard rendering the old set.

    `fallback` is for a view that can legitimately be EMPTY - a condition-matched list where finding
    nothing is the good outcome, like "MCP integrations whose authentication failed". Without it, a
    healthy estate fails the dashboard build: `columns_for` raises, and the raise takes down the whole
    dashboard rather than one panel. With it, the panel renders an empty table, which is the honest
    picture. Only pass a fallback where empty is a real state; leaving it off for a view that should
    always have rows is what keeps "the tier has not run yet" a build failure rather than a blank page.
    """
    rows = view.get("rows") or []
    if not rows and fallback:
        return [{"selector": key, "text": key.strip(), "type": kind} for key, kind in fallback]
    if not rows:
        # An empty `columns` makes Infinity's backend parser return HTTP 500, so a panel built from an
        # empty view is broken rather than merely blank. Fail the build instead: it means the view has not
        # been published yet by the tier that owns it. Run that tier, then rebuild.
        raise EmptyView(
            "view has no rows, so no column spec can be generated. Infinity's backend parser 500s on an "
            "empty `columns`. Run the tier that owns this view before building the dashboard, or pass a "
            "`schema` if an empty result is a legitimate state for it."
        )
    keys = list(rows[0])
    out = []
    for key in keys:
        out.append({
            "selector": key,
            # Strip the leading space that forces order in Infinity's alphabetising parser.
            "text": key.strip(),
            "type": _infer_type([r.get(key) for r in rows]),
        })
    return out


def data_query(
    group: str, ds_uid: str, spec: dict[str, Any], ref_id: str, *, hidden: bool = False,
) -> dict[str, Any]:
    """Wrap a query in the v2 `DataQuery` envelope.

    **This shape is not guessable and getting it wrong renders "plugin not found" on the whole page.**
    `kind` is the literal string `DataQuery`; the plugin id goes in **`group`**; the datasource uid goes in
    **`datasource.name`** (not `uid`, and there is no `type`). Confirmed against a converted dashboard on
    the stack rather than invented - which is exactly what PLAN 6.5a said to do.
    """
    return {
        "kind": "PanelQuery",
        "spec": {
            "refId": ref_id,
            "hidden": hidden,
            "query": {
                "kind": "DataQuery",
                "group": group,
                "version": "v0",
                "datasource": {"name": ds_uid},
                "spec": spec,
            },
        },
    }


# Filters an Infinity table to the dashboard's `stack` selection.
#
# **The anchors and the group are both load-bearing.** Infinity's `=~` is UNANCHORED - measured:
# `Stack =~ "hub.*"` matches both `hub` and `hub-dev` - so an unanchored filter on a slug that
# is a prefix of another slug silently returns extra rows. And the variable is `multi`, so
# `${stack:regex}` expands to `(a|b|c)`; without the outer `(...)` the alternation would escape the
# anchors and match anything ending in the last slug.
#
# `allValue = ".*"` on the variable (see `stack_variable`) is what makes the All case work: it expands
# to `^(.*)$`, which matches every row. Verified live against the datasource, both branches.
STACK_FILTER = 'Stack =~ "^(${stack:regex})$"'


def infinity_query(view_name: str, ds_uid: str, ref_id: str = "A", *,
                   stack_filter: bool = False,
                   schema: Sequence[tuple[str, str]] | None = None) -> dict[str, Any]:
    """One table query against a published S3 view. All three Infinity knobs are set here.

    `schema` is the column spec to use when the view is legitimately empty - see `columns_for`.
    """
    spec: dict[str, Any] = {
        "type": "json",
        "source": "url",
        "format": "table",
        # All three are load-bearing - see the module docstring.
        "parser": "backend",
        "root_selector": "rows",
        "columns": columns_for(read_view(view_name), schema),
        "url": f"{bucket_url()}/views/{view_name}.json",
        "url_options": {"method": "GET"},
    }
    if stack_filter:
        spec["filterExpression"] = STACK_FILTER
    return data_query(INFINITY_TYPE, ds_uid, spec, ref_id)


def prom_query(expr: str, ds_uid: str = PROM_UID, ref_id: str = "A", *,
               legend: str = "__auto", instant: bool = False,
               hidden: bool = False) -> dict[str, Any]:
    """A PromQL query against the stack's own metrics - where our 1,262 published series live.

    `$__interval`, never `$__auto`: the latter is not resolved on this path.
    """
    return data_query("prometheus", ds_uid, {
        "expr": expr,
        "legendFormat": legend,
        "range": not instant,
        "instant": instant,
        "editorMode": "code",
        "interval": "",
    }, ref_id, hidden=hidden)


def expression_query(
    spec: dict[str, Any], ref_id: str, *, hidden: bool = False,
) -> dict[str, Any]:
    """A Grafana server-side expression query in the v2 DataQuery envelope."""
    return data_query("__expr__", "__expr__", {**spec, "refId": ref_id}, ref_id, hidden=hidden)


def _panel(title: str, description: str, queries: list[dict[str, Any]],
           vizconfig: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "Panel",
        "spec": {
            "title": title,
            "description": description,
            "links": [],
            "data": {
                "kind": "QueryGroup",
                "spec": {"queries": queries, "queryOptions": {}, "transformations": []},
            },
            "vizConfig": vizconfig,
        },
    }


def _organize(order: Sequence[str], *, exclude: Sequence[str] = (),
              rename: dict[str, str] | None = None) -> dict[str, Any]:
    """An `organize` transformation that pins field order, and optionally hides or renames fields.

    Required because **Infinity's backend parser returns fields ALPHABETISED by display name**, not in
    the order `columns` declares them. The views therefore carried a `" Stack"` key with a leading
    space, on the theory that a leading space sorts first - it does not, because the parser sorts on the
    stripped display text, so `Stack` sorted under S. Measured on the live datasource:
    `risk_admin_sprawl` returned Stack as field **13 of 14**, off the right-hand edge of the panel. Every
    finding table was reading as anonymous rows of numbers.
    """
    index = {name: i for i, name in enumerate(order)}
    return {"kind": "organize", "spec": {"id": "organize", "options": {
        "indexByName": index,
        "excludeByName": {name: True for name in exclude},
        "renameByName": rename or {},
    }}}


def view_columns(view_name: str,
                 fallback: Sequence[tuple[str, str]] | None = None) -> list[str]:
    """Display names of a view's columns, in the order the pillar declared them."""
    return [c["text"] for c in columns_for(read_view(view_name), fallback)]


# The identity column every per-stack view leads with. Its presence is what decides whether a table can
# honour the dashboard's `stack` selection at all.
STACK_COLUMN = "Stack"

# Units by COLUMN DISPLAY NAME, applied to every table that has the column. Keyed on the name rather than
# per panel because a column name means the same thing in every view that carries it, and a per-call-site
# map would be 30 places to forget.
#
# The ratio/percent split here is measured, not inferred from the name: `Stickiness` is a 0-1 ratio (max
# observed 1.0) so it takes `percentunit`, while every `... %` column is already scaled 0-100 (max observed
# 94.4) so it takes `percent`. Using `percent` on a ratio renders 0.87 as "0.87%" instead of "87%", and
# `percentunit` on a 0-100 column renders 94.4 as "9440%". Both have shipped elsewhere on this project.
COLUMN_UNITS: dict[str, str] = {
    "Stickiness": "percentunit",
    "Admin share %": "percent",
    "Share of org series %": "percent",
    "Share of estate %": "percent",
    "Change %": "percent",
}


def table_panel(title: str, view_name: str, ds_uid: str, *, description: str = "",
                columns: Sequence[str] | None = None, stack_filter: bool | None = None,
                units: dict[str, str] | None = None,
                widths: dict[str, int] | None = None,
                schema: Sequence[tuple[str, str]] | None = None) -> dict[str, Any]:
    """A table bound to one published S3 view.

    `columns` names the fields to show, in order; anything else in the view is hidden. Omit it to show
    every column in the order the pillar declared them - which is still an explicit order, because
    Infinity's own ordering is alphabetical and puts the identity column in the middle (see `_organize`).

    `stack_filter` defaults to **auto**: a view carrying a `Stack` column gets the filter, one without it
    does not. Auto rather than opt-in because the selector silently doing nothing was the defect - a
    viewer picked one stack, every Prometheus panel narrowed, every table kept showing all 273 rows, and
    nothing on the page said the tables were estate-wide. Opting in per call site is 20 chances to forget.
    Pass `False` to keep a table deliberately estate-wide, and say so in its description.

    Filtering does not destroy these tables the way it would a `topk` chart: none of the views are top-N
    - they are full inventories or condition-matched lists, so one stack's row is a meaningful answer to
    "does mine appear here". The top-N rankings on these dashboards are all bar charts, which have no
    `Stack` column and are unaffected.

    `units` maps a column's display name to a Grafana unit, merged over `COLUMN_UNITS`, and `widths` to a
    pixel width - both as field overrides, since a 0-1 ratio rendered bare reads as a broken number.
    """
    declared = view_columns(view_name, schema)
    order = list(columns) if columns else declared
    missing = [c for c in order if c not in declared]
    if missing:
        # Fail the build rather than silently rendering a table with a blank column: a renamed pillar
        # field would otherwise show as an empty strip that reads as "not measurable".
        raise ValueError(
            f"{view_name}: columns {missing} are not in the view, which has {declared}. A pillar "
            f"renamed a field, or this panel names one that never existed."
        )
    exclude = [c for c in declared if c not in order] if columns else []

    if stack_filter is None:
        stack_filter = STACK_COLUMN in declared
    elif stack_filter and STACK_COLUMN not in declared:
        raise ValueError(
            f"{view_name}: stack_filter requested but the view has no {STACK_COLUMN!r} column, so the "
            f"filter would match nothing and the table would render permanently empty."
        )

    resolved_units = {c: u for c, u in COLUMN_UNITS.items() if c in order}
    resolved_units.update(units or {})

    overrides = []
    for column, unit in resolved_units.items():
        overrides.append({"matcher": {"id": "byName", "options": column},
                          "properties": [{"id": "unit", "value": unit}]})
    for column, width in (widths or {}).items():
        overrides.append({"matcher": {"id": "byName", "options": column},
                          "properties": [{"id": "custom.width", "value": width}]})

    panel = _panel(
        title, description,
        [infinity_query(view_name, ds_uid, stack_filter=stack_filter, schema=schema)],
        viz("table", {
            "options": {"showHeader": True, "footer": {"show": False, "fields": []},
                        "cellHeight": "sm"},
            "fieldConfig": {"defaults": {"custom": {"filterable": True, "align": "auto"}},
                            "overrides": overrides},
        }))
    panel["spec"]["data"]["spec"]["transformations"] = [_organize(order, exclude=exclude)]
    return panel


def treemap_panel(title: str, view_name: str, ds_uid: str, *,
                  text_field: str, size_field: str, color_by_field: str,
                  label_fields: Sequence[str] = (), description: str = "") -> dict[str, Any]:
    """A Marcus Olsson Treemap bound to a complete Infinity view.

    The third-party v2 envelope and these option names were round-tripped on obs-hub before this
    builder was added. Keep the native table beside a treemap: area communicates concentration, while
    the table remains the exact ranked and filterable work queue.
    """
    declared = view_columns(view_name)
    mapped = [text_field, size_field, color_by_field, *label_fields]
    missing = [field for field in mapped if field not in declared]
    if missing:
        raise ValueError(
            f"{view_name}: treemap fields {missing} are not in the view, which has {declared}"
        )

    return _panel(
        title, description,
        [infinity_query(
            view_name, ds_uid,
            stack_filter=STACK_COLUMN in declared,
        )],
        viz("marcusolsson-treemap-panel", {
            "fieldConfig": {
                "defaults": {"color": {"mode": "continuous-GrYlRd"}},
                "overrides": [],
            },
            "options": {
                "tiling": "treemapSquarify",
                "textField": text_field,
                "sizeField": size_field,
                "colorByField": color_by_field,
                "labelFields": list(label_fields),
            },
        }),
    )


def stat_panel(title: str, expr: str, *, description: str = "", unit: str = "short",
               decimals: int | None = None, ds_uid: str = PROM_UID) -> dict[str, Any]:
    """A single headline number from PromQL - via a RANGE query reduced to `lastNotNull`.

    **Never `instant`.** Measured: an instant query for `gcinsight_estate_stacks` returns an empty
    frame while the same expression over a range returns 8 points. The collector writes hourly and Mimir's
    lookback-delta is 5 minutes, so an instant query at `now` finds a sample only in the 5 minutes after a
    scan - 8% of the time at best. Same root cause as the carry-forward problem (PLAN 5.3), one layer up:
    a range query plus a reducer is correct at any time of day.
    """
    defaults: dict[str, Any] = {"unit": unit}
    if decimals is not None:
        defaults["decimals"] = decimals
    return _panel(title, description, [prom_query(expr, ds_uid)], viz("stat", {
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "auto", "colorMode": "none", "graphMode": "none",
            "justifyMode": "auto", "orientation": "auto",
        },
        "fieldConfig": {"defaults": defaults, "overrides": []},
    }))


def cross_source_ratio_stat_panel(
    title: str,
    numerator: tuple[str, str],
    denominator: tuple[str, str],
    *,
    description: str = "",
    unit: str = "short",
    decimals: int | None = None,
) -> dict[str, Any]:
    """Divide scalar reductions from two Prometheus datasources without copying either series.

    Both inputs remain range queries. Each is reduced on the Grafana server before the final math so
    daily collector samples and live usage samples do not need identical timestamps.
    """
    defaults: dict[str, Any] = {"unit": unit}
    if decimals is not None:
        defaults["decimals"] = decimals
    queries = [
        prom_query(numerator[0], numerator[1], ref_id="A", hidden=True),
        prom_query(denominator[0], denominator[1], ref_id="B", hidden=True),
        expression_query({
            "type": "reduce", "expression": "$A", "reducer": "last",
            "settings": {"mode": "dropNN"},
        }, "C", hidden=True),
        expression_query({
            "type": "reduce", "expression": "$B", "reducer": "last",
            "settings": {"mode": "dropNN"},
        }, "D", hidden=True),
        expression_query({"type": "math", "expression": "$C / $D"}, "E"),
    ]
    return _panel(title, description, queries, viz("stat", {
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "auto", "colorMode": "none", "graphMode": "none",
            "justifyMode": "auto", "orientation": "auto",
        },
        "fieldConfig": {"defaults": defaults, "overrides": []},
    }))


def timeseries_panel(title: str, exprs: Sequence[tuple[str, str]], *, description: str = "",
                     unit: str = "short", stacked: bool = False,
                     ds_uid: str = PROM_UID) -> dict[str, Any]:
    """A trend from PromQL. `exprs` is a sequence of `(expr, legend)`.

    This is what the whole remote_write path exists for: the S3 views are point-in-time snapshots, so
    without these panels nothing on the dashboards shows a direction of travel.
    """
    queries = [
        prom_query(expr, ds_uid, ref_id=chr(ord("A") + i), legend=legend)
        for i, (expr, legend) in enumerate(exprs)
    ]
    return _panel(title, description, queries, viz("timeseries", {
        "options": {
            "legend": {"calcs": [], "displayMode": "list", "placement": "bottom",
                       "showLegend": len(exprs) > 1},
            "tooltip": {"mode": "single", "sort": "none"},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line", "lineWidth": 2, "fillOpacity": 10 if not stacked else 40,
                    "showPoints": "never", "spanNulls": True,
                    "stacking": {"mode": "normal" if stacked else "none", "group": "A"},
                    "axisPlacement": "auto", "gradientMode": "none",
                },
            },
            "overrides": [],
        },
    }))


# `reduce` in its default "Series to rows" mode names the calculated column after the reducer's DISPLAY
# name, not its id: `lastNotNull` becomes `Last *`. `sortBy` therefore has to match that exact string -
# `"lastNotNull"` matches no field and sorts nothing, silently.
REDUCED_VALUE_FIELD = "Last *"


def barchart_panel(title: str, expr: str, *, description: str = "", legend: str = "__auto",
                   ds_uid: str = PROM_UID, unit: str = "short", sort: str | None = "desc",
                   limit: int | None = None,
                   thresholds: Sequence[tuple[float | None, str]] | None = None) -> dict[str, Any]:
    """A ranked bar chart for topk-style breakdowns. Range query + `lastNotNull`, never instant.

    Same reason as `stat_panel`: an instant query against an hourly-written series is empty most of the
    time. The `reduceValues` transformation turns the reduced series into one bar each.

    `ds_uid` matters here as much as on the stat panels: a bar chart pointed at the wrong datasource
    renders EMPTY, and an empty adoption chart reads as "nobody uses it" rather than "no data".

    **`sort` defaults to descending, and that default is the fix for a whole class of shipped defect.**
    `topk`/`bottomk` bound WHICH series come back; they do not order them, and the `reduce` transformation
    preserves whatever order the datasource returned - in practice alphabetical by label. So every panel
    titled "Worst stacks by ..." or "Biggest ... by stack" was rendering alphabetically, with the actual
    worst offender somewhere in the middle. Pass `sort="asc"` for a `bottomk` chart where small is bad,
    and `sort=None` only where the x-axis is a category whose own order carries meaning.

    `limit` is a DISPLAY limit applied after reduction and sorting. A range `topk(15, ...)` can return
    more than 15 distinct series because membership is recomputed at every step; use `limit=15` only
    where the reader needs an exact-size companion to that union.

    `unit` is not cosmetic either: a 0-1 ratio rendered with the default `short` unit reads as a bare
    decimal, so `0.87` looks like a count rather than 87%.
    """
    defaults: dict[str, Any] = {"unit": unit, "custom": {"axisPlacement": "auto"}}
    if thresholds:
        defaults["thresholds"] = {
            "mode": "absolute",
            "steps": [{"value": value, "color": color} for value, color in thresholds],
        }
        defaults["custom"]["gradientMode"] = "none"
    panel = _panel(title, description, [prom_query(expr, ds_uid, legend=legend)], viz("barchart", {
        "options": {"orientation": "horizontal", "showValue": "auto", "xTickLabelRotation": 0,
                    "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "single", "sort": "none"},
                    **({"colorByField": REDUCED_VALUE_FIELD} if thresholds else {})},
        "fieldConfig": {"defaults": defaults, "overrides": []},
    }))
    # Collapse each series to its last value so the chart shows one bar per label, not a time axis.
    transformations: list[dict[str, Any]] = [
        {"kind": "reduce", "spec": {"id": "reduce",
                                    "options": {"reducers": ["lastNotNull"]}}},
    ]
    if sort:
        transformations.append({"kind": "sortBy", "spec": {"id": "sortBy", "options": {
            "fields": {},
            "sort": [{"field": REDUCED_VALUE_FIELD, "desc": sort == "desc"}],
        }}})
    if limit is not None:
        if limit <= 0:
            raise ValueError("barchart_panel limit must be above zero")
        if not sort:
            raise ValueError("barchart_panel limit requires an explicit sort")
        transformations.append({"kind": "limit", "spec": {
            "id": "limit", "options": {"limitField": limit},
        }})
    panel["spec"]["data"]["spec"]["transformations"] = transformations
    return panel


def barchart_series_panel(title: str, exprs: Sequence[tuple[str, str]], *, description: str = "",
                          ds_uid: str = PROM_UID, unit: str = "short",
                          sort: str | None = None) -> dict[str, Any]:
    """A bar chart of NAMED bars, one query per bar.

    `barchart_panel` labels its bars from a metric label, which is right for "top 15 stacks" but wrong
    wherever the label is an internal value a reader should never see. The response-time histogram is the
    case that forced this: `legend="{{le}}"` rendered bars captioned `300.0`, `3600.0` and `+Inf` - the
    bucket boundaries, decimal point and all. One query per band, each with a caption written for a human,
    is the only way to fix that without a value-mapping table that has to be kept in step with the
    buckets.

    `sort` defaults to `None` here, the opposite of `barchart_panel`: a caller naming its bars explicitly
    has an order in mind, and the case this exists for is an ordered scale.
    """
    queries = [prom_query(expr, ds_uid, ref_id=chr(ord("A") + i), legend=legend)
               for i, (expr, legend) in enumerate(exprs)]
    panel = _panel(title, description, queries, viz("barchart", {
        "options": {"orientation": "horizontal", "showValue": "auto", "xTickLabelRotation": 0,
                    "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "single", "sort": "none"}},
        "fieldConfig": {"defaults": {"unit": unit, "custom": {"axisPlacement": "auto"}},
                        "overrides": []},
    }))
    transformations: list[dict[str, Any]] = [
        {"kind": "reduce", "spec": {"id": "reduce", "options": {"reducers": ["lastNotNull"]}}},
    ]
    if sort:
        transformations.append({"kind": "sortBy", "spec": {"id": "sortBy", "options": {
            "fields": {}, "sort": [{"field": REDUCED_VALUE_FIELD, "desc": sort == "desc"}],
        }}})
    panel["spec"]["data"]["spec"]["transformations"] = transformations
    return panel


def prometheus_table_panel(title: str, expr: str, *, description: str = "",
                           legend: str = "__auto", ds_uid: str = PROM_UID,
                           label_column: str = "Series", value_column: str = "Value",
                           unit: str = "short", sort: str = "desc") -> dict[str, Any]:
    """A scrollable ranked table backed by Prometheus, reduced to one current row per series.

    Use this for long action lists where a bar chart stops being legible. A hundred horizontal bars do
    technically contain the top 100, but only a small fraction fit on screen and the labels collapse;
    the table keeps all 100 available with a compact row height and column filtering.

    The transformation order is load-bearing. `reduce` produces the display fields ``Field`` and
    ``Last *``; `sortBy` must target ``Last *`` before `organize` renames it. Sorting the requested
    output name matches nothing and silently leaves the datasource order in place.
    """
    panel = _panel(title, description, [prom_query(expr, ds_uid, legend=legend)], viz("table", {
        "options": {"showHeader": True, "footer": {"show": False, "fields": []},
                    "cellHeight": "sm"},
        "fieldConfig": {
            "defaults": {"custom": {"filterable": True, "align": "auto"}},
            "overrides": [
                {"matcher": {"id": "byName", "options": value_column},
                 "properties": [{"id": "unit", "value": unit}]},
                {"matcher": {"id": "byName", "options": label_column},
                 "properties": [{"id": "custom.width", "value": 520}]},
            ],
        },
    }))
    panel["spec"]["data"]["spec"]["transformations"] = [
        {"kind": "reduce", "spec": {"id": "reduce",
                                      "options": {"reducers": ["lastNotNull"]}}},
        {"kind": "sortBy", "spec": {"id": "sortBy", "options": {
            "fields": {},
            "sort": [{"field": REDUCED_VALUE_FIELD, "desc": sort == "desc"}],
        }}},
        _organize(["Field", REDUCED_VALUE_FIELD], rename={
            "Field": label_column,
            REDUCED_VALUE_FIELD: value_column,
        }),
    ]
    return panel


def text_panel(title: str, content: str) -> dict[str, Any]:
    """Markdown panel - the coverage/freshness banner (PLAN 6.6)."""
    return _panel(title, "", [], viz("text", {"options": {"mode": "markdown", "content": content}}))


def auto_grid(element_names: Sequence[str], *, max_columns: int = 2,
              row_height: str = "standard") -> dict[str, Any]:
    """`AutoGridLayout` - panels flow and resize themselves, so no manual gridPos arithmetic.

    `row_height` is `"short"`, `"standard"` or `"tall"`. Use `"short"` for a row of stat panels: at
    standard height a single number renders roughly half a screen tall, which is what made several tabs
    look like three enormous digits and nothing else.
    """
    return {
        "kind": "AutoGridLayout",
        "spec": {
            "maxColumnCount": max_columns,
            "columnWidthMode": "standard",
            "rowHeightMode": row_height,
            "fillScreen": False,
            "items": [
                {"kind": "AutoGridLayoutItem", "spec": {"element": {"kind": "ElementReference",
                                                                     "name": name}}}
                for name in element_names
            ],
        },
    }


def tab(title: str, element_names: Sequence[str], *, max_columns: int = 2,
        row_height: str = "standard") -> dict[str, Any]:
    return {
        "kind": "TabItem",
        "spec": {"title": title, "layout": auto_grid(element_names, max_columns=max_columns,
                                                     row_height=row_height)},
    }


def row(title: str, element_names: Sequence[str], *, max_columns: int = 2,
        row_height: str = "standard") -> dict[str, Any]:
    """One `RowsLayoutRow`, wrapping an auto-grid of its own.

    Field names are from the live OpenAPI schema (`...v2.DashboardRowsLayoutRowSpec`), not inferred:
    `title`, `collapse`, `hideHeader`, `fillScreen`, `layout`, of which only `layout` is required.

    Rows always start expanded. Screenshot capture and cold-reader review both need every panel in the
    rendered document without a click-dependent hidden state; long detail remains grouped beneath its
    summary and can still be collapsed interactively after the page loads.
    """
    return {
        "kind": "RowsLayoutRow",
        "spec": {
            "title": title,
            "collapse": False,
            "hideHeader": False,
            "fillScreen": False,
            "layout": auto_grid(element_names, max_columns=max_columns, row_height=row_height),
        },
    }


def rows_tab(title: str, rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """A tab whose panels are grouped into named rows instead of one flat grid.

    Use it where a tab carries a summary AND its detail: an auto-grid gives every panel an equal cell, so
    a headline stat and a 270-row table compete for the same space and the text panels clip. Rows let the
    summary sit at the top at a sensible height with the detail grouped beneath.
    """
    return {
        "kind": "TabItem",
        "spec": {"title": title,
                 "layout": {"kind": "RowsLayout", "spec": {"rows": list(rows)}}},
    }


def dashboard(title: str, description: str, elements: dict[str, Any], tabs: Sequence[dict[str, Any]],
              *, tags: Sequence[str] = (), variables: Sequence[dict[str, Any]] = (),
              links: Sequence[dict[str, Any]] = (), time_from: str = "now-6h") -> dict[str, Any]:
    """Assemble a v2 dashboard and assert the layout is complete before returning it."""
    placed: list[str] = []

    def collect(layout: dict[str, Any]) -> None:
        """Walk a layout of any kind. `RowsLayout` nests an auto-grid per row, so a flat read of
        `spec.items` misses every panel inside a row - and since `assert_layout_complete` treats an
        unplaced element as fatal, that would make any rows-based tab fail the build."""
        spec = layout.get("spec", {})
        for item in spec.get("items", []):
            placed.append(item["spec"]["element"]["name"])
        for nested in spec.get("rows", []):
            collect(nested["spec"]["layout"])
        for nested in spec.get("tabs", []):
            collect(nested["spec"]["layout"])

    for entry in tabs:
        collect(entry["spec"]["layout"])
    assert_layout_complete(elements, placed)
    _assign_panel_ids(elements)

    return {
        "apiVersion": SCHEMA,
        "kind": "Dashboard",
        "spec": {
            "title": title,
            "description": description,
            "tags": list(tags),
            "editable": True,
            "liveNow": False,
            # `weekStart` is deliberately omitted - setting it has crashed renders.
            "timeSettings": {
                "from": time_from, "to": "now", "autoRefresh": "", "autoRefreshIntervals": [],
                "hideTimepicker": False, "timezone": "browser",
            },
            "links": list(links),
            "variables": list(variables),
            "elements": elements,
            "layout": {"kind": "TabsLayout", "spec": {"tabs": list(tabs)}},
        },
    }


# --- PLAN 6.6: shared banner, stack variable, cross-links ----------------------------------------

DASHBOARDS = (
    ("gcinsight-estate", "Estate"),
    ("gcinsight-cost", "Cost"),
    ("gcinsight-usage", "Usage"),
    ("gcinsight-maturity", "Maturity"),
    ("gcinsight-risk", "Risk"),
    ("gcinsight-value", "Value"),
    ("gcinsight-operations", "Operations"),
    ("gcinsight-commercial", "Commercial"),
    ("gcinsight-ai", "AI usage"),
    ("gcinsight-dashboards", "Dashboard usage"),
    ("gcinsight-coverage", "Coverage"),
)

BANNER_MD = """\
**Read the coverage and freshness panels beside this before quoting any number.**

- A **blank cell means not measurable, not zero.** Where that distinction matters the table says so in
  words rather than showing a reassuring `0`. Permission-filtered list endpoints are counted only with
  their measured-stack denominator, because an unreadable list can otherwise look like a clean zero.
- Every summary table **leads with its denominator** (`Stacks measured`, `Stacks scored`). A partial scan
  is reported as partial, never as a smaller estate.
- **Money uses the *billed* user line, never the *active* one.** They differ by double digits, so the
  two answer different questions and are never averaged. The live gap is on the Cost dashboard.
- **Freshness is per INPUT, not per dashboard.** Panels here can mix an hourly inventory sweep with a
  6-hourly data-plane sweep, so the age of each is shown separately. A figure is only as fresh as the
  input it came from.
- **The Stack selector does not filter live `grafanacloud-usage` panels.** That datasource identifies
  stacks by numeric `stack_id`, not by the slug carried by this selector, so those panels remain
  estate-wide even while a stack is selected. Their descriptions state that scope explicitly.
- **An input that goes stale WITHHOLDS its panels rather than zeroing them**, so a table that has
  stopped advancing is the signal - never a table that has dropped to zero.
"""


# Which inputs a dashboard's figures actually depend on, so its freshness panel reports the age of the
# right thing. Keyed by the pillar's dashboard name. Derived from `emit/hydrate.VIEW_INPUTS` via the
# views each dashboard renders - `tests/test_dashboards.py` checks the two agree.
#
# The old behaviour was a single "Data age" reading `tier="t1"` on ALL EIGHT dashboards, because
# `banner_elements()` was called with its default everywhere. So Cost, Maturity, Risk and Value - whose
# figures come from the 6-hourly data-plane sweep - all advertised the hourly tier's timestamp and
# therefore claimed to be minutes old when their contents could be hours old.
DASHBOARD_INPUTS: dict[str, tuple[str, ...]] = {
    "estate": (),
    # The Adaptive Logs recommendation table is T2-owned while Adaptive Metrics/cardinality are T3.
    # Both ages belong on the page: showing only the 6-hourly data-plane age makes the daily named
    # recommendation queue look materially fresher than it is.
    "cost": ("adaptive_logs", "dataplane"),
    "usage": ("stack_detail",),
    "maturity": ("dataplane", "stack_detail"),
    "risk": ("access_policies", "alert_routing", "dataplane", "fleet", "org_members",
             "public_dashboards", "service_accounts", "stack_detail"),
    "value": ("dataplane",),
    # Operations and Commercial read `grafanacloud-usage` DIRECTLY - no collector, no view, no input.
    # Their freshness is the datasource's own, which is why they get no input-age panel at all.
    "operations": (),
    "commercial": (),
    # Pillar J is entirely collector-fed, from T2's per-stack usage-insights sweep. Declaring the input
    # is what gives it a freshness panel: the figures are as current as that sweep, not as the run.
    "dashboards": ("dashboard_inventory", "datasource_query_cost", "insights"),
    # AI was in that group until 2026-08-20 and is NOT any more. Its org-wide tabs are still live from
    # `grafanacloud-usage`, but four tabs now render our own per-stack Assistant series and S3 views from
    # the DAILY `assistant` input. Leaving it declared input-free would have shown a dashboard with no age
    # panel at all beside figures that can be a day old - the same class of error as the old
    # T1-timestamp-everywhere default, and harder to spot because half the page really is live.
    "ai": ("assistant",),
    # Pillar K combines the daily signal-label sweep with the existing dashboard and alert inventories.
    # The live usage panels carry datasource-native freshness and are called out separately in the banner.
    "coverage": ("alert_routing", "dashboard_inventory", "signal_inventory"),
}

# Inputs used by metric panels but not by an S3 view on the same dashboard. Most dashboard input
# dependencies are derived from the views they render; keeping this small explicit seam prevents a
# metric-only capability from appearing current merely because no table has landed yet.
DASHBOARD_METRIC_INPUTS: dict[str, tuple[str, ...]] = {
    "risk": ("alert_routing", "org_members", "public_dashboards"),
}

# Dashboards whose panels come entirely from the live usage datasource rather than from our scans. `ai` is
# deliberately absent: it MIXES the two, and its banner says so rather than claiming either.
LIVE_DATASOURCE_ONLY = ("operations", "commercial")
FRESHNESS_LOOKBACK = "7d"

# Appended to the standard banner for a dashboard that mixes sources, because neither standard text is
# true on its own there and a reader comparing two panels needs to know which is which.
MIXED_BANNER_MD: dict[str, str] = {
    "ai": """
- **This dashboard MIXES two sources and they have different windows.** The Overview, Adoption by stack,
  Token consumption, People and Commercial tabs are live from `grafanacloud-usage` on the **monthly
  billing period**. Assistant use per stack, Human vs machine, Enablement and Collection coverage come
  from our own per-stack collection on a **rolling 30-day plugin window**, refreshed daily. The two
  disagree by design - never quote a figure from one as a check on the other.
- **Every Assistant inventory count is TENANT-scoped.** A user-scoped skill or rule is invisible to any
  credential, including a full Admin, so these are not stack totals and cannot be made into them.
- **Category breakdowns are shares of the CATEGORISED subset**, which is a minority of messages on most
  stacks. The uncategorised share is on the page for exactly that reason.
""",
    "coverage": """
- **The question this surface must answer:** "How can we expand this to show our customers which apps / infra etc are currently observed by us and how can we capture the value that we bring to the table? This could move the conversation from gaps and cost to upside potential and top line revenue growth."
- **This dashboard MIXES collector output, S3 registers and live `grafanacloud-usage`.** Coverage depth,
  technology classification and the named registers follow the input ages shown below. Hosts, pods,
  containers, log streams, integrations and the OnCall ownership catalogue are live datasource panels;
  the Stack selector does not filter them.
- **Canonical service identity is exact after trim and case-folding.** The generic Mimir `service` label
  stays in the legacy register and is never silently promoted into canonical coverage.
""",
}

LIVE_BANNER_MD = """\
**Live from `grafanacloud-usage`: no scan, collector or S3 view; coverage and input age do not apply.**

- **Estate scope:** the Stack selector is carried through links but does not filter these panels because
  this datasource has no stack-slug label.
- **Rate-shaped series use a 24h window**, never an instantaneous comparison.
- A stack missing from a metric is **absent, not zero**.
"""


def banner_elements(dashboard: str = "estate") -> dict[str, Any]:
    """The panels every dashboard carries: how to read it, coverage, and freshness PER INPUT.

    Scan freshness comes from `gcinsight_scan_completed_timestamp_seconds` (PLAN 1.8) - the same
    series the dead-man's switch alerts on, so a stale dashboard and a failed scan are one signal. Input
    freshness comes from `gcinsight_input_age_seconds` (PLAN 16.1), which is the age of the data the
    figures were computed FROM rather than of the run that published them.
    """
    if dashboard in LIVE_DATASOURCE_ONLY:
        return {"_banner": text_panel("How to read this", LIVE_BANNER_MD)}

    out: dict[str, Any] = {
        "_banner": text_panel("How to read this",
                              BANNER_MD + MIXED_BANNER_MD.get(dashboard, "")),
        "_coverage": stat_panel(
            "Scan coverage",
            'gcinsight_scan_coverage_ratio{tier="t1"}',
            unit="percentunit", decimals=1,
            description="Share of the SCANNABLE estate the hourly inventory sweep covered - paused "
                        "stacks are excluded from the denominator, so 100% is achievable. Below 100% "
                        "means stacks failed. This is inventory coverage; the panels below say how old "
                        "each INPUT was."),
        "_freshness": stat_panel(
            "Inventory age",
            "time() - max_over_time("
            f'gcinsight_scan_completed_timestamp_seconds{{tier="t1"}}[{FRESHNESS_LOOKBACK}])',
            unit="s", decimals=0,
            description="Seconds since the last successful hourly inventory sweep. This is the "
                        "dead-man's switch series - alert on this, not on exit code. It covers the "
                        "inventory only; data-plane and per-stack figures have their own age below."),
    }
    for name in DASHBOARD_INPUTS.get(dashboard, ()):
        # `input_age_seconds` is the age AT EMISSION. A range query plus lastNotNull otherwise freezes
        # that value at the last scan and reports an hour-old input as a few seconds old. Advance it by
        # the wall-clock time since the latest T1 sample; T1 is the publication seam whose metric/view
        # values these dashboards render.
        selector = f'gcinsight_input_age_seconds{{tier="t1",input="{name}"}}'
        out[f"_age_{name}"] = stat_panel(
            f"{INPUT_LABELS[name]} age",
            f"time() - max_over_time(timestamp({selector})[{FRESHNESS_LOOKBACK}:]) + "
            f"last_over_time({selector}[{FRESHNESS_LOOKBACK}])",
            unit="s", decimals=0,
            description=INPUT_DESCRIPTIONS[name])
    return out


INPUT_LABELS = {
    "dataplane": "Data plane",
    "stack_detail": "Per-stack detail",
    "access_policies": "Access policies",
    "assistant": "Assistant collection",
    "insights": "Usage-insights sweep",
    "dashboard_inventory": "Dashboard inventory",
    "datasource_query_cost": "Datasource query-cost sweep",
    "fleet": "Fleet Management sweep",
    "adaptive_logs": "Adaptive Logs sweep",
    "public_dashboards": "Public-dashboard inventory",
    "alert_routing": "Alert-routing inventory",
    "service_accounts": "Service-account inventory",
    "org_members": "Organisation membership",
    "signal_inventory": "Signal label inventory",
}

INPUT_DESCRIPTIONS = {
    "dataplane": "Age of the data-plane sweep these figures were computed from - cardinality, Adaptive "
                 "Metrics recommendations and Fleet Management. Gathered every 6 hours, so this reads "
                 "up to 6 hours even when everything is healthy. Past the staleness cap the panels "
                 "that depend on it stop being republished rather than dropping to zero.",
    "stack_detail": "Age of the per-stack identity sweep these figures were computed from - users, "
                    "logins, plugins and service accounts. Gathered daily, so this reads up to 24 "
                    "hours when healthy.",
    "access_policies": "Age of the org access-policy list these figures were computed from. Gathered "
                       "hourly with the inventory, so this should track the inventory age.",
    "assistant": "Age of the per-stack Assistant sweep these figures were computed from - messages, "
                 "tokens, category x surface and tenant inventory, read from each stack's own Assistant "
                 "API. Gathered daily, so this reads up to 24 hours when healthy. It does NOT cover the "
                 "live `grafanacloud-usage` panels on this dashboard, which have no age of ours at all.",
    "fleet": "Age of the Fleet Management sweep behind the collector and pipeline figures. Gathered HOURLY, because a collector fleet changes by the minute - on ephemeral compute a pod reschedule registers a new collector and marks the old one inactive, so a stale reading here describes a fleet that has already moved on. If this climbs past an hour or two, the collector counts are describing the past.",
    "insights": "Age of the per-stack usage-insights sweep these figures were computed from - dashboard opens, viewers, panel queries and the public-dashboard check, read from each stack's own usage-insights datasource. Gathered daily, so this reads up to 24 hours when healthy. The figures themselves cover a rolling window ending at that sweep, so a 24-hour age means the window closed a day ago.",
    "dashboard_inventory": "Age of the complete per-stack dashboard inventory used to distinguish "
                           "opened, unopened and unknown dashboards over the 31-day activity window. "
                           "Gathered daily; read unknown rows as a coverage problem, never as unopened.",
    "datasource_query_cost": "Age of the per-stack datasource query-cost sweep. It resolves query "
                             "activity to datasource identity and preserves unavailable stacks as "
                             "unknown rows, so read the named costs with their coverage state.",
    "adaptive_logs": "Age of the Adaptive Logs recommendation sweep, read through each stack's own app-plugin proxy. Gathered daily, so this reads up to 24 hours when healthy. Note that the recommendation VOLUMES on this page are totals over a window the Adaptive Logs API does not name and cannot be asked to change, so this age tells you how current the recommendation SET is, not what period the bytes cover.",
    "public_dashboards": "Age of the per-stack public-dashboard inventory behind the policy counters. "
                         "The endpoint returns a permission-filtered list, so read this with the "
                         "measured-stack denominator: a stale or missing sweep must not look like "
                         "compliance with the zero-public-dashboard policy.",
    "alert_routing": "Age of the per-stack alert-rule and contact-point inventory behind the routing "
                     "counters. Read it with the input-availability panel and measured-stack denominator: "
                     "an unavailable or partial sweep must not look like fewer inherited or missing "
                     "receivers.",
    "service_accounts": "Age of the per-stack service-account inventory behind the credential counts "
                        "and named table. Read it with coverage: an unavailable stack is excluded rather "
                        "than counted as zero accounts.",
    "org_members": "Age of the Grafana.com organisation membership response behind the Admin, Viewer "
                   "and staff-access counts. This is one org-level population rather than a per-stack "
                   "sample; if it is unavailable the metrics and named table are withheld, never zeroed.",
    "signal_inventory": "Age of the explicitly-windowed Mimir, Loki, Tempo and Pyroscope label sweep "
                        "behind the observed service, technology and cluster registers. Gathered daily; "
                        "a failed stack contributes no row or per-stack metric rather than a zero.",
}


def banner_keys(dashboard: str = "estate") -> tuple[str, ...]:
    """Element keys `banner_elements(dashboard)` produces, for the tab that places them."""
    return tuple(banner_elements(dashboard))


# Retained for the estate default. Prefer `banner_keys(dashboard)`.
BANNER_KEYS = ("_banner", "_coverage", "_freshness")


# --- Findings (pillars/findings.py) ---------------------------------------------------------------
#
# `gcinsight_findings{kind}` is the durable trend for the actionable detail that lives in Loki. Each
# dashboard shows only ITS OWN pillar's kinds, so a reader is not handed another pillar's backlog.
#
# The counts are here; the per-stack detail is NOT, deliberately - it is in the pillar's own tables and in
# Loki, where the fields that make a finding actionable (worst label name, service-account name) are
# permitted. Duplicating it here would be a third copy that could disagree with both.

def findings_elements(pillar: str, kinds: Sequence[str],
                      detail: Sequence[tuple[str, ...]] = (),
                      ds_uid: str | None = None) -> dict[str, Any]:
    """Findings count, trend, help, and the named rows behind them.

    `detail` is `(element_key, panel_title, view_name)` - optionally with a fourth item, the column
    `schema` to fall back on when that view is legitimately empty. These are the tables that name the
    stacks behind the counts. Without them this tab was a bar chart plus an instruction to go and query
    Loki, which is not a drill-down: it tells a reader their estate has 41 of something and then sends
    them elsewhere to find out which. Empty dict when the pillar has no kinds.
    """
    if not kinds:
        return {}
    selector = f'gcinsight_findings{{kind=~"{"|".join(kinds)}"}}'
    out = {
        "_findings_now": barchart_panel(
            "Open findings by kind",
            f"sum by (kind) ({selector})",
            legend="{{kind}}",
            # A finding is a DEFECT, so it must not render in the same green as every healthy metric on
            # these dashboards. Amber from the first one, red once a kind reaches double figures - the
            # boundary is a judgement, but "any" and "lots" are the two states a reader acts on
            # differently, and green for either was actively misleading.
            thresholds=[(None, "yellow"), (10, "red")],
            description="Count of STACKS matching each finding condition, worst first, from the latest "
                        "scan of whichever tier can compute it. Amber and red rather than green because "
                        "every bar here is a defect. A kind that is ABSENT rather than zero means no tier "
                        "that ran could measure it - blank is not the same as none. The tables below name "
                        "the stacks behind these counts.",
        ),
        "_findings_trend": timeseries_panel(
            "Findings over time",
            [(f"sum by (kind) ({selector})", "{{kind}}")],
            description="The durable record. Log retention is shorter than metric retention, so this "
                        "trend outlives the Loki lines carrying the per-stack detail.",
        ),
        "_findings_help": text_panel(
            "About these findings - and where the rest of the detail is",
            "Each bar is a **finding kind** - a condition worth acting on, derived from this pillar's own "
            "tables by `pillars/findings.py`.\n\n"
            "The **detail** is in Loki, not here: query "
            "`{job=\"gcinsight\", event=\"finding\", pillar=\"" + pillar + "\"} | json` to get the "
            "stack, the rank, and the fields that make each one actionable - the worst cardinality label, "
            "the service-account name, the admin count.\n\n"
            "Lines are capped at the worst 25 per kind to keep log volume sane. **The count above is the "
            "true total**, so a capped kind still reports honestly.\n\n"
            "The tables on this tab name the stacks for the kinds that have a published table. Loki is "
            "only needed for the per-finding FIELDS that are banned from a metric label - label names, "
            "service-account names, plugin version strings.",
        ),
    }
    if detail and not ds_uid:
        # A table pointed at the wrong datasource renders EMPTY rather than erroring, and an empty
        # findings table reads as "nothing to report" - the most dangerous wrong answer this tab can give.
        # So a missing uid is a build failure, never a default.
        raise ValueError("findings_elements: detail tables need the Infinity datasource uid")
    for entry in detail:
        key, title, view = entry[0], entry[1], entry[2]
        schema = entry[3] if len(entry) > 3 else None
        out[key] = table_panel(
            title, view, ds_uid, schema=schema,
            description="The named rows behind the counts above - which stacks, and the figures that "
                        "decide whether each one matters. Honours the Stack selector, and every column is "
                        "filterable, so this is where a reader turns a count into a work queue.")
    return out


FINDINGS_KEYS = ("_findings_now", "_findings_trend", "_findings_help")



def stack_variable(ds_uid: str = PROM_UID) -> dict[str, Any]:
    """A `stack` template variable listing all 271 stacks, from Mimir label values.

    Deliberately PromQL-backed rather than Infinity-backed: forcing a prometheus `query.kind` onto an
    Infinity variable renders a 500, and `gcinsight_stack_active_series` carries every stack anyway.
    """
    metric = "gcinsight_stack_active_series"
    return {
        "kind": "QueryVariable",
        "spec": {
            "name": "stack",
            "label": "Stack",
            # Scalar `current` on a single-select var; a list here has crashed renders.
            "current": {"text": "All", "value": "$__all"},
            "hide": "dontHide",
            "refresh": "onDashboardLoad",
            "skipUrlSync": False,
            "query": {
                "kind": "DataQuery",
                "group": "prometheus",
                "version": "v0",
                "datasource": {"name": ds_uid},
                "spec": {
                    "label": "stack",
                    "metric": metric,
                    "qryType": 1,
                    "query": f"label_values({metric},stack)",
                    "refId": "PrometheusVariableQueryEditor-VariableQuery",
                },
            },
            "regex": "",
            "regexApplyTo": "value",
            # **Load-bearing for the Infinity tables.** They filter with
            # `Stack =~ "^(${stack:regex})$"` (see STACK_FILTER), and with no explicit `allValue` the
            # All selection expands to an alternation of all 273 slugs - a working but enormous regex.
            # `.*` keeps the All case to `^(.*)$`. Verified live against the datasource: both the single
            # -stack and the All branch return the expected row counts.
            "allValue": ".*",
            "sort": "alphabeticalAsc",
            "options": [],
            "multi": True,
            "includeAll": True,
            "allowCustomValue": False,
        },
    }


def cross_links(current_uid: str) -> list[dict[str, Any]]:
    """Links to the sibling dashboards, carrying the time range and the `stack` selection across.

    **`DashboardDashboardLink` IS FLAT - no `kind`/`spec` wrapper.** This is the one v2 shape that differs
    from Panel, VizConfig and DataQuery, and wrapping it by analogy with those is a silent failure: the API
    accepts the payload, discards the unknown `kind`/`spec` keys, and stores nine empty strings. The result
    is a row of **blank buttons pointing at `about:blank`** - visible only by clicking one. That failure was
    found only through rendered-dashboard verification.

    Field list is from the live OpenAPI schema (`/openapi/v3/apis/dashboard.grafana.app/v2`,
    `...v2.DashboardDashboardLink`), not inferred:

        required: title, type, icon, tooltip, tags, asDropdown, targetBlank, includeVars, keepTime
        optional: url, origin, placement

    `tags` must be a list - it stored as `null` when omitted. `type` must be `"link"`; `"dashboards"` makes
    Grafana ignore `url` and list by tag instead.
    """
    return [
        {
            "title": title,
            "url": f"/d/{uid}",
            "type": "link",
            "tooltip": f"Grafana Cloud Org Insights - {title}",
            "icon": "external link",
            "tags": [],
            "asDropdown": False,
            "targetBlank": False,
            # Both true so a hop keeps the time range and the `stack` selection. Without them every link
            # resets context, which in a walkthrough is worse than having no links.
            "includeVars": True,
            "keepTime": True,
        }
        for uid, title in DASHBOARDS
        if uid != current_uid
    ]
