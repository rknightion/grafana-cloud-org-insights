"""Actionable findings, derived from the pillar views and streamed to Loki.

`emit/loki.py` has always declared a `finding` event and a `finding_events()` builder, and nothing ever
called it - so the most actionable half of the Loki story was empty. This module is the missing producer.

WHY DERIVE FROM VIEWS RATHER THAN CHANGE THE PILLARS
----------------------------------------------------
The pillars already compute exactly these rows: `risk_admin_sprawl` IS the admin-sprawl finding,
`cost_cardinality_outliers` IS the cardinality finding. Re-deriving the conditions inside six pillars
would give two definitions of every finding that could disagree. So the mapping below is declarative:
one row of a named view becomes one finding, and the pillar that produced the view owns the logic.

WHAT MAKES A FINDING USEFUL IS THE FIELDS METRICS CANNOT CARRY
-------------------------------------------------------------
"Cardinality is high" is useless next to "`stack084`'s worst label is `X` with 88,000 values". Those
fields - label names, service-account names, stack slugs - are precisely what the cardinality guard bans
from a metric label, which is why they belong in a log line.

THE COUNTS ARE A METRIC; THE DETAIL IS NOT
------------------------------------------
`gcinsight_findings{kind}` is a bounded gauge - one series per finding kind - so a finding TREND
survives log retention, which is shorter than metric retention on every Grafana Cloud plan. That gauge is
the durable record; the Loki lines are the current detail.

**An absent view means an absent series, never a zero.** T1 cannot compute `cost_cardinality_outliers`,
and emitting `0` for it would overwrite the real weekly value every hour - the exact defect that already
cost this project a debugging session, one layer up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

# Views carry the stack under a LEADING-SPACE key. That is deliberate upstream: Infinity's backend parser
# orders columns alphabetically, and the space forces the stack column to sort first. It also means a
# naive `row["Stack"]` silently finds nothing.
STACK_KEYS = (" Stack", "Stack", "stack")

# Loki lines per finding kind. `cost_cardinality_outliers` alone has 230 rows, and several kinds at that
# size would multiply the platform's log volume several-fold for detail nobody reads past the worst
# offenders. The METRIC still carries the true total, so the cap costs visibility of the tail, not of the
# number - and `derive()` marks every capped kind rather than truncating silently.
MAX_LINES_PER_KIND = 25


@dataclass(frozen=True)
class FindingSpec:
    view: str
    pillar: str
    kind: str
    severity: str
    summary: str
    # Row columns worth carrying into the line. Empty means "the whole row".
    fields: tuple[str, ...] = field(default_factory=tuple)

    # --- Row filters, for views that are a TABLE rather than a finding set --------------------------
    #
    # Most of these views are already filtered by the pillar that owns them: every row of
    # `risk_fleet_dead` has `FM dead = True`, every row of `risk_admin_sprawl` is genuinely admin-heavy.
    # Two are not, and treating their rows as findings produced nonsense - 4,964 "service account risks"
    # when the estate has 2, and 230 "cardinality outliers" including a stack with 2 active series.
    #
    # A filter here is therefore an admission that the view is unfiltered upstream. The better fix is for
    # the pillar to publish a filtered view; until it does, the threshold lives here and says why.
    require: tuple[str, ...] = field(default_factory=tuple)          # field must be truthy
    at_least: tuple[tuple[str, float], ...] = field(default_factory=tuple)  # field >= value

    def matches(self, row: Mapping[str, Any]) -> bool:
        for key in self.require:
            if not row.get(key):
                return False
        for key, floor in self.at_least:
            value = row.get(key)
            if not isinstance(value, (int, float)) or value < floor:
                return False
        return True


# Ordered by how likely a reader is to act on it, which is also the order the dashboards present.
SPECS: tuple[FindingSpec, ...] = (
    FindingSpec(
        "cost_cardinality_outliers", "B", "cardinality_outlier", "high",
        "Stack has a label driving a material share of its series; the worst label is named so it can be "
        "dropped or aggregated. Threshold: a single label with 5,000+ values.",
        ("Active series", "Label values", "Label names", "Worst label", "Worst label values"),
        # The view is the FULL cardinality table, 230 rows, sorted descending - not an outlier set. Its
        # own distribution, measured 2026-08-18: worst-label values p50=33, p75=638, p90=1,972,
        # p95=7,756, max=80,345. So 5,000 sits just below p95 and yields 14 stacks that each have a label
        # genuinely worth dropping. Unfiltered, this kind reported 230 findings including a stack with
        # 2 active series, which is how a findings list loses its reader.
        at_least=(("Worst label values", 5_000.0),),
    ),
    FindingSpec(
        "cost_adaptive_headroom", "B", "adaptive_headroom", "high",
        "Adaptive Metrics recommendations are pending and unapplied - series being paid for that a "
        "single action would remove.",
        ("Active series", "Recs pending", "Rules applied", "Share of org series %"),
    ),
    FindingSpec(
        "risk_admin_sprawl", "E", "admin_sprawl", "high",
        "Admin share is far above what the user count justifies. Every Admin can delete the stack.",
        ("Users (active)", "Admins", "Admin share %", "Delete protection", "Active series"),
    ),
    FindingSpec(
        "risk_service_accounts", "E", "service_account_risk", "high",
        "Service account hoarding live tokens, or a person-named account holding automation credentials.",
        ("Service account", "Kind", "Role", "Tokens", "Disabled", "Flag"),
        # The view is the WHOLE service-account inventory - 4,964 rows across 271 stacks, of which 4,458
        # are Grafana's own auto-provisioned `extsvc-*` accounts. `Flag` is the column the pillar sets on
        # the ones that matter, and exactly 2 carry it. Reporting all 4,964 as findings was the single
        # worst signal-to-noise defect in this module's first version.
        require=("Flag",),
    ),
    FindingSpec(
        "risk_delete_protection", "E", "no_delete_protection", "high",
        "Stack holds production load and can be deleted without a guard. Compounding risk where the "
        "stack is also admin-heavy - every Admin can delete it, and there is nothing to stop them. "
        "Threshold: unprotected and 50,000+ active series (see risk.DELETE_PROTECTION_SERIES_FLOOR).",
        ("Active series", "Users (active)", "Admins", "Admin share %", "Delete protection"),
        # No row filter: `risk.py` publishes this view already filtered, which is the module's stated
        # preference over a threshold here.
    ),
    FindingSpec(
        "risk_fleet_dead", "E", "fleet_dead_collector", "medium",
        "Fleet Management collectors registered but not reporting - a pipeline believed to be running "
        "that is not.",
        ("Collectors", "Pipelines", "FM dead", "Active series"),
    ),
    FindingSpec(
        "risk_plugin_drift", "E", "plugin_drift", "medium",
        "Installed plugin is behind its latest version.",
    ),
    FindingSpec(
        "estate_leftovers_billing", "A", "leftover_stack_billing", "medium",
        "Automated-test leftover that is nonetheless billing - users or series attached.",
        ("Users (billed)", "Active series", "Age (days)", "Idle (days)", "Created by"),
    ),
    FindingSpec(
        "estate_leftovers_idle", "A", "leftover_stack_idle", "info",
        "Automated-test leftover with no users and no series. A GOVERNANCE finding worth £0 - stack "
        "creation is leaking. Never present it as a saving.",
        ("Users (billed)", "Active series", "Age (days)", "Idle (days)", "Created by"),
    ),
    FindingSpec(
        "estate_drift", "A", "version_drift", "info",
        "Stack is behind the current Grafana version.",
        ("Version drift", "Users (active)", "Active series"),
    ),
    FindingSpec(
        "usage_dormant_stacks", "C", "dormant_stack", "medium",
        "Stack is provisioned and paid for but effectively unused.",
        ("Users (active)", "Users (daily)", "Stickiness", "Dashboards", "Age (days)"),
    ),
    # --- Pillar I. All four views are pre-filtered by pillars/ai.py, which is this module's stated
    # preference over a threshold living here. Two of them are legitimately EMPTY today and that is the
    # point: `gcinsight_findings{kind}` still carries a measured 0, because every stack's MCP
    # integrations and enabled flags were read successfully. That is different from an absent series.
    FindingSpec(
        "ai_mcp_auth_failed", "I", "mcp_auth_failed", "high",
        "Tenant MCP integration's last authentication FAILED, so Assistant is configured to reach a "
        "system it cannot reach. Silent: the integration still shows as enabled.",
        ("kind", "name", "type", "enabled", "authenticationFailed", "createdBy"),
    ),
    FindingSpec(
        "ai_enablement_gap", "I", "assistant_no_tenant_config", "medium",
        "Stack uses Assistant heavily and has NO tenant skills, rules, automations or MCP integrations - "
        "people are driving it raw. The cheapest enablement intervention in the estate. Threshold: 100+ "
        "messages in 30 days (pillars/ai.py ENABLEMENT_MESSAGE_FLOOR, just above the active-stack p75).",
        ("Messages", "Assistant users", "Tokens", "Tokens per Assistant user", "Tenant objects"),
    ),
    FindingSpec(
        "ai_token_outliers", "I", "assistant_token_outlier", "medium",
        "Tokens per Assistant user far above the estate median. Usually machine-driven rather than a "
        "heavy human - read it beside the machine share, which is what explains it. Threshold: 25M "
        "tokens per user (pillars/ai.py TOKENS_PER_USER_OUTLIER, the estate p90).",
        ("Tokens per Assistant user", "Assistant users", "Tokens", "Messages",
         "Machine share of categorised"),
    ),
    FindingSpec(
        "ai_config_disabled", "I", "assistant_config_disabled", "info",
        "Tenant Assistant object exists but is switched off - configured effort producing nothing. "
        "`enabled` is absent on skills, so only an explicit false counts here.",
        ("kind", "name", "enabled", "scope", "createdBy"),
    ),
)

SEVERITIES = ("high", "medium", "info")
KINDS = tuple(s.kind for s in SPECS)


def _stack_of(row: Mapping[str, Any]) -> str | None:
    for key in STACK_KEYS:
        if key in row and row[key]:
            return str(row[key])
    return None


def derive(views: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return `(findings, totals)`.

    `totals` is keyed by kind and holds the TRUE row count even where the lines were capped. Only kinds
    whose source view was actually present appear in either - that is what keeps a gap absent rather
    than zero.
    """
    findings: list[dict[str, Any]] = []
    totals: dict[str, int] = {}

    for spec in SPECS:
        if spec.view not in views:
            # The tier that ran cannot compute this. Say nothing at all about it.
            continue
        rows = views[spec.view]
        if not isinstance(rows, list):
            continue

        matching = [r for r in rows if isinstance(r, dict) and spec.matches(r)]
        totals[spec.kind] = len(matching)
        for rank, row in enumerate(matching[:MAX_LINES_PER_KIND], start=1):
            detail = (
                {k: row.get(k) for k in spec.fields if k in row}
                if spec.fields
                else {k: v for k, v in row.items() if k not in STACK_KEYS}
            )
            findings.append(
                {
                    "pillar": spec.pillar,
                    "kind": spec.kind,
                    "severity": spec.severity,
                    "summary": spec.summary,
                    "stack": _stack_of(row),
                    "rank": rank,
                    "of_total": len(matching),
                    "truncated": len(matching) > MAX_LINES_PER_KIND,
                    "source_view": spec.view,
                    "detail": detail,
                }
            )
    return findings, totals


def metrics(totals: Mapping[str, int]) -> list[tuple[str, dict[str, str], float]]:
    """One bounded gauge per finding kind that was actually computable.

    Deliberately NOT `sum by (severity)` as well: severity is a property of the kind, so a second
    breakdown would be derivable from this one and would only add series.
    """
    return [
        ("gcinsight_findings", {"kind": kind}, float(count))
        for kind, count in sorted(totals.items())
    ]


def summarise(findings: Sequence[Mapping[str, Any]], totals: Mapping[str, int]) -> str:
    """One stderr line. Names the capped kinds explicitly - a silent truncation reads as full coverage."""
    if not totals:
        return "findings: none computable by this tier"
    capped = [k for k, n in sorted(totals.items()) if n > MAX_LINES_PER_KIND]
    total = sum(totals.values())
    msg = f"findings: {total} across {len(totals)} kinds, {len(findings)} lines to Loki"
    if capped:
        msg += f" (capped at {MAX_LINES_PER_KIND} for: {', '.join(capped)})"
    return msg
