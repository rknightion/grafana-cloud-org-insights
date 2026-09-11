"""Live `grafanacloud-usage` panels for Logs retention divergence candidates.

The billing datasource reports numeric `stack_id`, not the dashboard's slug selector, so every panel
here is deliberately estate-wide. The collector is responsible for confirming an individual stack.
"""

from __future__ import annotations

from collector.dashboards import build


_LIMITS = "grafanacloud_logs_instance_limits"
_RETENTION = f'{_LIMITS}{{limit_name="retention_period"}}'
_LOOKBACK = f'{_LIMITS}{{limit_name="max_query_lookback"}}'
_DAYS = " / 1e9 / 86400"

# Keep the comparison form visibly identical wherever it is used. The billing metric has one value per
# stack and limit name, so `on(stack_id)` is its only join key. A mismatch is a candidate, not proof of
# a per-stream setting: the collector performs that confirmation stack by stack.
_DIVERGENCE = f"count({_LOOKBACK} != on(stack_id) group_left() {_RETENTION})"

_SCOPE = (
    "Estate-wide: grafanacloud-usage identifies numeric stack_id and does not follow the dashboard "
    "$stack slug selector. The collector tier confirms an individual stack."
)


def _stat(title: str, queries: list[tuple[str, str]], description: str) -> dict:
    """Return a multi-value stat panel from range queries against the live usage datasource."""
    return build._panel(  # noqa: SLF001 - the public stat helper accepts one expression only.
        title,
        description,
        [
            build.prom_query(
                expression, build.USAGE_UID, ref_id=chr(ord("A") + index), legend=legend
            )
            for index, (expression, legend) in enumerate(queries)
        ],
        build.viz(
            "stat",
            {
                "options": {
                    "reduceOptions": {
                        "calcs": ["lastNotNull"],
                        "fields": "",
                        "values": False,
                    },
                    "textMode": "auto",
                    "colorMode": "none",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "orientation": "auto",
                },
                "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []},
            },
        ),
    )


def _table_query(expression: str, ref_id: str) -> dict:
    """A range Prometheus table query exposing numeric `stack_id` for a table join."""
    return build.data_query(
        "prometheus",
        build.USAGE_UID,
        {
            "expr": expression,
            "legendFormat": "__auto",
            "range": True,
            "instant": False,
            "editorMode": "code",
            "interval": "",
            "format": "table",
        },
        ref_id,
    )


def _candidate_table() -> dict:
    """Build the divergent-stack table with retention and lookback as separate numeric columns."""
    retention = f"({_RETENTION} != on(stack_id) group_left() {_LOOKBACK}){_DAYS}"
    lookback = f"({_LOOKBACK} != on(stack_id) group_left() {_RETENTION}){_DAYS}"
    panel = build._panel(  # noqa: SLF001 - this table needs two Prometheus result frames.
        "Candidate stacks: retention and lookback days",
        "Only stacks whose reported lookback differs from reported retention appear. This is a candidate "
        "signal of a likely per-stream retention override, not confirmation. " + _SCOPE,
        [_table_query(retention, "A"), _table_query(lookback, "B")],
        build.viz(
            "table",
            {
                "options": {
                    "showHeader": True,
                    "footer": {"show": False, "fields": []},
                    "cellHeight": "sm",
                },
                "fieldConfig": {
                    "defaults": {"custom": {"filterable": True, "align": "auto"}},
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "Retention days"},
                            "properties": [{"id": "unit", "value": "d"}],
                        },
                        {
                            "matcher": {"id": "byName", "options": "Lookback days"},
                            "properties": [{"id": "unit", "value": "d"}],
                        },
                    ],
                },
            },
        ),
    )
    panel["spec"]["data"]["spec"]["transformations"] = [
        {
            "kind": "joinByField",
            "spec": {
                "id": "joinByField",
                "options": {
                    "byField": "stack_id",
                    "mode": "outerTabular",
                },
            },
        },
        {
            "kind": "organize",
            "spec": {
                "id": "organize",
                "options": {
                    "indexByName": {"stack_id": 0, "Value #A": 1, "Value #B": 2},
                    "excludeByName": {"Time": True},
                    "renameByName": {
                        "stack_id": "Stack ID",
                        "Value #A": "Retention days",
                        "Value #B": "Lookback days",
                    },
                },
            },
        },
    ]
    return panel


def _global_retention_stat(retention_days: str) -> dict:
    """Show the modal duration itself, not the number of stacks carrying it.

    PromQL's ``count_values`` keeps the grouped sample value in a label and uses the sample value for
    the group count.  Promote that label to a field before the stat reduction; otherwise the headline
    would display the winning group's population while calling it a duration.
    """
    panel = _stat(
        "Modal global retention days and distinct values",
        [
            (
                f'topk(1, count_values("retention_days", {retention_days}))',
                "{{retention_days}}",
            ),
            (
                f'count(count_values("retention_days", {retention_days}))',
                "distinct retention values",
            ),
        ],
        "Shows the reported retention-day value distribution: the modal value is the most common "
        "retention_days result and the companion value counts distinct reported values. "
        + _SCOPE,
    )
    panel["spec"]["data"]["spec"]["transformations"] = [
        {
            "kind": "labelsToFields",
            "spec": {"id": "labelsToFields", "options": {"mode": "columns"}},
        },
        {
            "kind": "merge",
            "spec": {"id": "merge", "options": {}},
        },
        {
            "kind": "organize",
            "spec": {
                "id": "organize",
                "options": {
                    "excludeByName": {"Time": True, "Value #A": True},
                    "indexByName": {"retention_days": 0, "Value #B": 1},
                    "renameByName": {
                        "retention_days": "Modal retention days",
                        "Value #B": "Distinct retention values",
                    },
                },
            },
        },
    ]
    return panel


def retention_panels() -> dict[str, dict]:
    """Return the five frozen Operations elements for live Logs retention reporting.

    The caller owns dashboard placement and registry wiring; this function has no credentials, network
    access, collector output, or side effects.
    """
    retention_days = f"{_RETENTION}{_DAYS}"
    return {
        "_ret_denom": _stat(
            "Stacks reporting retention and any Logs limit",
            [
                (f"count(count by(stack_id) ({_RETENTION}))", "retention period"),
                (f"count(count by(stack_id) ({_LIMITS}))", "any Logs limit"),
            ],
            "Compares the stacks reporting a retention period with stacks reporting any Logs limit, so "
            "the other retention panels have a visible reporting denominator. "
            + _SCOPE,
        ),
        "_ret_global": _global_retention_stat(retention_days),
        "_ret_candidates": build.stat_panel(
            "Candidate stacks with divergent lookback",
            _DIVERGENCE,
            ds_uid=build.USAGE_UID,
            description="Counts stacks whose reported query lookback differs from reported retention. "
            "It is a candidate signal of a likely per-stream retention override, not "
            "confirmation. " + _SCOPE,
        ),
        "_ret_candidate_table": _candidate_table(),
        "_ret_trend": build.timeseries_panel(
            "Candidate stacks with divergent lookback over time",
            [(_DIVERGENCE, "candidate stacks")],
            ds_uid=build.USAGE_UID,
            description="Trend of stacks whose reported query lookback differs from reported retention. "
            "It is a candidate signal of a likely per-stream retention override, not "
            "confirmation. " + _SCOPE,
        ),
    }
