#!/usr/bin/env python3
"""Build and publish the v2 dashboards (PLAN 6.5b).

    python3 bin/dashboards.py --list # what would be built
    python3 bin/dashboards.py --out /tmp/dash --ds-uid <uid> # write JSON, publish nothing
    python3 bin/dashboards.py --publish estate # publish one
    python3 bin/dashboards.py --publish all # publish all

A publish needs a build-time Grafana token in `GCINSIGHT_GRAFANA_TOKEN` (an Admin service account on the
stack). That is **not** a runtime credential: the scheduled scan writes only to Mimir/Loki/S3 via the
two CAPs and never touches the Grafana API. Local JSON output is offline when `--ds-uid` is supplied.

Datasource uid comes from `--ds-uid` or is resolved by name, never hardcoded (PLAN 0.6).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from collector import identity, observability_score
from collector import ratecard as ratecard_model
from collector.dashboards import build
from collector.pillars import (
    ai as ai_pillar,
    coverage as coverage_pillar,
    cost as cost_pillar,
    estate as estate_pillar,
    findings,
    insights as insights_pillar,
    insights_inventory as insights_inventory_pillar,
    risk as risk_pillar,
    usage as usage_pillar,
)
from collector.sources import assistant as assistant_src

STACK_ID = os.environ.get("GCINSIGHT_WRITE_STACK_ID", "").strip()
BASE = os.environ.get("GCINSIGHT_WRITE_STACK_URL", "").strip()
DS_NAME = identity.env("GCINSIGHT_DASHBOARD_DS_NAME", "Grafana Cloud Org Insights (S3)")
FOLDER_TITLE = identity.env("GCINSIGHT_DASHBOARD_FOLDER_TITLE", "Grafana Cloud Org Insights")
DASHBOARD_UID_PREFIX = identity.env("GCINSIGHT_DASHBOARD_UID_PREFIX", "gcinsight")
DASHBOARD_TITLE_PREFIX = identity.env(
    "GCINSIGHT_DASHBOARD_TITLE_PREFIX", "Grafana Cloud Org Insights"
)
DASHBOARD_TAG = identity.env("GCINSIGHT_DASHBOARD_TAG", "gcinsight")

# --- Shared `grafanacloud-usage` expressions -------------------------------------------------------
# Each of these appears on a stat panel AND on a trend panel. Written once so the headline number and
# the line above it cannot drift apart - the failure mode is a stat saying 44 next to a graph plotting
# something subtly different, which destroys trust in the whole page and is invisible in review.
#
# Two shapes matter, and getting either wrong produces a plausible wrong number rather than an error.
#
# 1. `count(count by(stack_id) (...))`. The inner `count by` collapses a stack's several signal instances
# and its `reason`/`integration` label values to one entry; the outer `count` counts stacks. A bare
# `count(<metric> > 0)` counts LABEL COMBINATIONS - measured, that reported 223 zero-query stacks
# against a real 60.
#
# 2. **`max_over_time(...[24h])` on anything rate-shaped, never a bare instantaneous compare.** Every
# `*_per_second` and `*:rate5m` series here is momentary: comparing it to zero answers "is this
# happening in the current scrape window", not "does this stack have a problem". Measured 2026-08-18,
# within one 40-minute span, the difference:
#
# instant vs 24h discards 20/29 log drops 7/22 notifications 14/20 eval failures 9/41
# write-only stacks 33 instant -> 9 over 24h, and 4 "big write-only stacks" -> ZERO
#
# So the instant form UNDERSTATES intermittent faults and wildly OVERSTATES absence-of-activity. It
# also made the same panel read 60 then 33 forty minutes apart, which on its own disqualifies it.
WINDOW = "24h"

# Adaptive Metrics dropping samples it was told to drop is not data loss. Excluded so the panel does not
# report a stack for adopting the cost lever we recommend two dashboards over.
DEFECT_ONLY = '{reason!="requested-by-configuration"}'


def _any_in_window(selector: str) -> str:
    """Stacks where a rate-shaped series was non-zero at ANY point in the window."""
    return f"count(count by(stack_id) (max_over_time({selector}[{WINDOW}]) > 0))"


DISCARD_STACKS = _any_in_window(
    f"grafanacloud_instance_samples_discarded_per_second{DEFECT_ONLY}")
LOGDROP_STACKS = _any_in_window("grafanacloud_logs_instance_discarded_bytes_per_second")
NOTIF_STACKS = _any_in_window(
    "grafanacloud_instance_alertmanager_notifications_failed_per_second")
# The PER-INTEGRATION variant of the same failure. The stack-level metric says a stack could not deliver;
# this one says through which channel, which is the difference between "20 stacks have a problem" and
# "one webhook is dead". Six integrations exist in this estate. Rate-shaped, so always windowed.
NOTIF_METRIC = "grafanacloud_instance_alertmanager_notifications_failed_per_integration_per_second"
DEADRULE_STACKS = _any_in_window(
    "grafanacloud_instance_ruler_queries_zero_fetched_series_total:rate5m")
EVALFAIL_STACKS = _any_in_window(
    "grafanacloud_grafana_instance_alerting_rule_evaluation_failures_total:rate5m")
TRACE_DISCARD_STACKS = _any_in_window(
    "grafanacloud_traces_instance_discarded_spans_total:rate5m")
METADATA_DISCARD_STACKS = _any_in_window(
    "grafanacloud_instance_metadata_discarded_per_second")
STATE_HISTORY_FAILURES = (
    "max by(stack_id)(max_over_time("
    "grafanacloud_grafana_instance_alerting_state_history_writes_failed_total:rate5m[24h]))"
)
STATE_HISTORY_FAILURE_STACKS = f"count(({STATE_HISTORY_FAILURES}) > 0)"

# --- Ingested and never queried --------------------------------------------------------------------
# IDEAS.md calls this the highest-value and hardest number in the platform. Measured honestly over 24h it
# splits cleanly, and only one half survives:
#
# METRICS - the finding DOES NOT EXIST. 234 stacks ingest metrics and exactly ONE went a full day
# without a query; not one stack over 10,000 series did. The instant form claimed 60 stacks and 4 big
# ones, and both were artifacts of asking "was anyone querying in this five-minute window". Do not
# re-add a metrics write-only panel: it is a negative result, not a missing feature.
#
# LOGS - this can be a real cost conversation. The live expressions identify stacks that ingest logs
# without any query activity in the same 24-hour window and quantify their combined ingest rate.
#
# The `and` is load-bearing in both directions: it requires the stack to be INGESTING, so an empty stack
# with no queries is excluded. That is what dissolved the metrics half - the 9 metric-quiet stacks turned
# out to have no series at all, i.e. the test leftovers `estate_leftovers_idle` already reports.
# Average each stack over the same 24-hour population used to decide whether it had a reader. Summing
# independent per-stack maxima creates an estate rate that never existed at any instant; live it was
# 3.9x the time-aligned average. Peaks remain useful for fault detection elsewhere, not for a spend rate.
_LOG_IN = f"avg_over_time(sum by(stack_id)(grafanacloud_logs_instance_bytes_received_per_second)[{WINDOW}:5m])"
_LOG_UNREAD = f"(max_over_time(sum by(stack_id)(grafanacloud_logs_instance_query_bytes:rate5m)[{WINDOW}:5m]) == 0)"
LOGS_UNREAD_STACKS = f"count(({_LOG_IN} > 0) and {_LOG_UNREAD})"
LOGS_UNREAD_BYTES = f"sum({_LOG_IN} and {_LOG_UNREAD})"
LOGS_IN_BYTES = f"sum({_LOG_IN})"

# A ratio 0-1, NOT a percent - see the panel description. `min_over_time` because completeness dips and a
# dip is the defect: momentary read 4 stacks, 24h low 14.
TRACE_INCOMPLETE_STACKS = ("count(min_over_time("
                           f"grafanacloud_traces_instance_percentage_complete_traces_flushed[{WINDOW}]) < 0.90)")

# --- Adaptive Metrics savings, the number cost.py says it cannot compute ---------------------------
# collector/pillars/cost.py reports recommendation COUNTS and states outright that converting them to a
# saving needs a per-recommendation series figure it cannot obtain. This metric IS that figure, and it
# was sitting in a datasource already provisioned on every stack.
SAVINGS_SERIES = "sum(grafanacloud_instance_recommendations_estimated_savings_series)"
SAVINGS_FRACTION = f"{SAVINGS_SERIES} / sum(grafanacloud_instance_active_series)"
SAVINGS_STACKS = ("count(sum by(stack_id)"
                  "(grafanacloud_instance_recommendations_estimated_savings_series) > 0)")
AGGREGATING_STACKS = ("count(sum by(stack_id)"
                      "(grafanacloud_instance_aggregation_aggregated_series) > 0)")

# The disproof of `gcinsight_estate_feature_stacks{kind="incident"} == 0`. See d_value's `n_oncall`.
ONCALL_STACKS = ("count(sum by(stack_id)"
                 "(grafanacloud_oncall_instance_alert_groups_total) > 0)")

# Product inventory and actual use answer different questions. Keep each pair on the same tab so a
# provisioned flag cannot be mistaken for adoption. k6 usage is a current billing-period quantity;
# Synthetic Monitoring executions are a momentary rate and therefore use the standard 24h window.
K6_ACTIVE_STACKS = (
    "count(sum by(stack_id)(grafanacloud_k6_stack_virtual_user_hours_usage) > 0)"
)
SM_ACTIVE_STACKS = _any_in_window("grafanacloud_sm_billable_check_executions_per_second")

# --- Pillar G: are they actually OPERATING? ---------------------------------------------------------
# Every other dashboard counts what EXISTS. These count what somebody DID. The source is the OnCall
# metrics, which uniquely carry `slug`, `team`, `service_name`, `integration` and `state` natively - no
# stack_id join needed.
#
# THREE measurement traps here, all found by cross-checking two metrics that disagreed.
#
# 1. **The two OnCall metrics cover DIFFERENT populations, and comparing them naively is a 15x error.**
# `alert_groups_total` spans **58 stacks / 11,692 groups**; the response-time histogram spans only
# **8 stacks / 1,069 observations**. A first draft of this dashboard put "368 unowned alerts" next to
# "5,738 unowned alerts" from the two sources on the same tab. Any ratio MUST restrict
# `alert_groups_total` to the stacks that report timing - the `and on(stack_id)` in ENGAGED_DENOM.
#
# 2. **A missing histogram observation is a missing ACKNOWLEDGEMENT, and that is the headline finding.**
# On the 8 timing stacks there were **8,700 alert groups but only 1,069 response-time observations**:
# OnCall records a response time when a human engages, so ~88% of alert groups show no human
# engagement at all. Say "no acknowledgement was recorded", never "nobody looked" - the metric cannot
# prove intent, only that no acknowledgement was logged.
#
# 3. **The histogram buckets top out at 3600s** (60 / 300 / 600 / 3600 / +Inf), so `histogram_quantile`
# SATURATES: p90 and p99 both return exactly 3600, meaning "at least an hour", not "an hour". Only p50
# is a real number. Express the tail as a COUNT above the top finite bucket, never as a high quantile.
# And the `le` values carry a decimal point - `le="3600"` matches NOTHING and renders empty.
ACK = "grafanacloud_oncall_instance_alert_groups_response_time_seconds"
RES = "grafanacloud_oncall_instance_alert_groups_resolution_time_seconds"
GROUPS = "grafanacloud_oncall_instance_alert_groups_total"
TOP_BUCKET = "3600.0"

# Alert groups belonging ONLY to stacks that report response timing - the honest denominator for any
# engagement ratio. Without the `and on(stack_id)` this divides 8 stacks' numerator by 58 stacks' total.
ENGAGED = f"sum({ACK}_count)"
ENGAGED_DENOM = (f"sum({GROUPS} and on(stack_id) "
                 f"(sum by(stack_id)({ACK}_count) > 0))")
ENGAGEMENT_RATE = f"{ENGAGED} / {ENGAGED_DENOM}"

MTTA_MEDIAN = f"histogram_quantile(0.5, sum by(le)({ACK}_bucket))"
MTTR_MEDIAN = f"histogram_quantile(0.5, sum by(le)({RES}_bucket))"
MTTA_MEAN = f"sum({ACK}_sum) / sum({ACK}_count)"
ACK_TOTAL = f'sum({ACK}_bucket{{le="+Inf"}})'
ACK_WITHIN_HOUR = f'sum({ACK}_bucket{{le="{TOP_BUCKET}"}})'
ACK_TAIL = f"{ACK_TOTAL} - {ACK_WITHIN_HOUR}"
ACK_TAIL_SHARE = f"1 - ({ACK_WITHIN_HOUR} / {ACK_TOTAL})"

# Per-team floors are the same signal-to-noise discipline as the delete-protection threshold: a team with
# 2 alert groups scores 0% or 100% and neither means anything.
TEAM_MIN_GROUPS = 50

# **The denominator restriction is the same defect as ENGAGED_DENOM, one aggregation down, and it was
# missed when that one was fixed.** `alert_groups_total` exists on 58 stacks; the response-time histogram
# exists on 8. So dividing a team's ACKNOWLEDGEMENT count by its TOTAL groups mixes a numerator drawn from
# 8 stacks with a denominator drawn from 58, and understates the team.
#
# Measured 2026-08-19, current form vs restricted form: `dpps-aem-admins` 75.9% both ways and
# `app_observability` 11.8% both ways - their groups happen to live only on timing stacks - but
# `No team` moves from **6.65% to 11.73%**, a 1.76x understatement. Two of three teams unaffected is not
# a reason to leave it: which teams are affected changes as soon as OnCall spreads to another stack.
TIMING_STACKS = f"(sum by(stack_id)({ACK}_count) > 0)"
GROUPS_ON_TIMING_STACKS = f"({GROUPS} and on(stack_id) {TIMING_STACKS})"
TEAM_ENGAGEMENT = (f"topk(12, (sum by(team)({ACK}_count) / sum by(team){GROUPS_ON_TIMING_STACKS}) "
                   f"and (sum by(team){GROUPS_ON_TIMING_STACKS} >= {TEAM_MIN_GROUPS}))")
TEAM_TAIL_SHARE = (
    f'topk(12, (1 - (sum by(team)({ACK}_bucket{{le="{TOP_BUCKET}"}}) '
    f'/ sum by(team)({ACK}_bucket{{le="+Inf"}}))) '
    f'and (sum by(team)({ACK}_bucket{{le="+Inf"}}) >= 10))')
TEAM_VOLUME = f"topk(12, sum by(team)({GROUPS}))"

# Both shares are over the SAME population - the stacks that report response timing - because they sit
# side by side and are meant to be read against each other. Before this, the first was over all 58 OnCall
# stacks and the second over the 8 timing stacks, so the comparison the layout invites was invalid: a
# difference between them could have been a real ownership effect or purely the change of denominator.
UNOWNED_SHARE_ALL = (f'sum({GROUPS}{{team="No team"}} and on(stack_id) {TIMING_STACKS}) '
                     f'/ sum{GROUPS_ON_TIMING_STACKS}')
UNOWNED_SHARE_ACKED = f'sum({ACK}_count{{team="No team"}}) / sum({ACK}_count)'
UNOWNED_SERVICE_SHARE = (
    f'sum({GROUPS}{{service_name="No service"}} and on(stack_id) {TIMING_STACKS}) '
    f'/ sum{GROUPS_ON_TIMING_STACKS}'
)
ALL_GROUPS = f"sum({GROUPS})"

# --- Capability adoption (Tier 2) -------------------------------------------------------------------
# **The denominator decides whether each of these is a gap or a success, and TWO different mistakes here
# each invert the conclusion. Both were made and caught on 2026-08-19.**
#
# 1. Use the right signal's denominator. Span metrics are derived from traces, so the population is
# stacks that SEND traces, not all 272 stacks.
# 2. **Measure the denominator over the same 24h window as everything else.** Read instantaneously,
# "stacks ingesting traces" is **39**; over 24h it is **230**. Trace ingest is bursty, so an
# instantaneous count catches only whoever happened to be shipping in that scrape. Using 39 made span
# metrics look like 46% adoption - "a success, not a gap" - when the honest figure is 23/230 = **10%**,
# which is a real and significant gap.
#
# So: every count here is windowed, and every panel states its own denominator.
def _stacks_with(metric: str) -> str:
    """Stacks where a metric was present and non-zero at ANY point in the window.

    Windowed for the same reason as the data-loss panels: an instantaneous count of a bursty series
    measures who was mid-flight in one scrape, not who uses the feature.
    """
    return f"count(sum by(stack_id)(max_over_time({metric}[{WINDOW}])) > 0)"


METRICS_STACKS = _stacks_with("grafanacloud_instance_active_series")
TRACES_STACKS = _stacks_with("grafanacloud_traces_instance_bytes_received_per_second")


NATIVE_HIST_STACKS = _stacks_with("grafanacloud_instance_active_native_histogram_series")
EXEMPLAR_STACKS = _stacks_with("grafanacloud_instance_exemplars_per_second")
SPANMETRIC_STACKS = _stacks_with("grafanacloud_instance_active_spanmetrics_series")
SERVICEGRAPH_STACKS = _stacks_with("grafanacloud_instance_active_service_graph_series")
PDC_STACKS = _stacks_with("grafanacloud_grafana_pdc_connected_agents")
ADAPTIVE_LOGS_STACKS = _stacks_with("grafanacloud_logs_instance_adaptivelogs_bytes_dropped_per_second")
ADAPTIVE_TRACES_STACKS = _stacks_with("grafanacloud_traces_instance_adaptivetraces_bytes_received_per_second")

# --- Workload composition (Tier 2) ------------------------------------------------------------------
# `*_info` series are one-per-object, so their SUM is an object count: how many pods and hosts the organisation
# actually monitor. The most concrete "what is in there" number the platform can produce.
PODS_MONITORED = "sum(grafanacloud_instance_active_kube_pod_info_series)"
HOSTS_MONITORED = "sum(grafanacloud_instance_active_node_uname_info_series)"
INTEGRATION_SERIES = "sum(grafanacloud_instance_active_integration_series)"
INTEGRATION_SHARE = f"{INTEGRATION_SERIES} / sum(grafanacloud_instance_active_series)"
K8S_STACKS = _stacks_with("grafanacloud_instance_active_kube_pod_info_series")
HOST_STACKS = _stacks_with("grafanacloud_instance_active_node_uname_info_series")
INTEGRATION_STACKS = _stacks_with("grafanacloud_instance_active_integration_series")

# Phase 1 of Pillar K remains panel-only: these object counts need no durable named workflow. GCI-0019
# deliberately copies only the bounded capability-adoption projection because its S3 call list and
# trendable gap series unlock outreach and closure tracking that a live panel cannot provide.
# Keep different metric generations separate rather than summing overlapping populations.
OBSERVED_OBJECT_COUNTS = (
    ("sum(grafanacloud_app_observability_service_entity_count)", "App O11y services"),
    ("sum(grafanacloud_app_observability_hostless_service_entity_count)",
     "App O11y hostless services"),
    ("sum(grafanacloud_asserts_instance_active_entities)", "active entity-graph entities"),
    ("sum(grafanacloud_asserts_instance_total_entities)", "entity-graph entities"),
    ("sum(grafanacloud_instance_active_target_info_series)", "OTel service instances"),
    ("sum(grafanacloud_instance_active_kube_node_info_series)", "Kubernetes nodes"),
    ("sum(grafanacloud_instance_active_kube_pod_container_info_series)", "containers"),
    ("sum(grafanacloud_logs_instance_active_streams)", "log streams"),
    ("sum(grafanacloud_instance_active_caas_targets_series)", "CaaS targets"),
    ("sum(grafanacloud_instance_active_faas_targets_series)", "serverless targets"),
)
APP_HOST_COUNTS = (
    ("sum(grafanacloud_instance_app_o11y_host_count)", "App O11y host count"),
    ("sum(grafanacloud_instance_app_o11y_host_count_v2)", "App O11y host count v2"),
    ("sum(grafanacloud_instance_app_o11y_host_count_v3)", "App O11y host count v3"),
)
APP_SERVICES_BY_STACK = build.usage_by_slug(
    "topk(15, sum by(stack_id)(grafanacloud_app_observability_service_entity_count))"
)
INTEGRATIONS_BY_SERIES = (
    "topk(20, sum by(integration)(grafanacloud_instance_active_integration_series))"
)
INTEGRATIONS_BY_HOST_SERIES = (
    "topk(20, sum by(integration)(grafanacloud_instance_active_integration_host_series))"
)
PROFILE_USAGE_GROUPS = (
    "topk(15, sum by(usage_group)(max_over_time("
    f"grafanacloud_profiles_instance_usage_group_bytes_received_per_second[{WINDOW}])))"
)
FE_SESSION_RATE = (
    "max_over_time(sum(grafanacloud_frontend_observability_instance_sessions_per_second)"
    f"[{WINDOW}:5m])"
)

# --- Pillar H: commercial (Tier 3) ------------------------------------------------------------------
# Commercial presentation constraints, enforced by tests:
# * Money is labelled **USD per month, marked as DERIVED** - the datasource states no currency.
# * The burn chart shows the two lines and **states no conclusion**. Do not add a projection, a
# forecast of underspend, or a "you will leave N unconsumed" note to any panel description here.
# Any deployment-specific commercial analysis belongs in presentation notes, not in an always-on dashboard.
# * Its own dashboard, so commercial data is one link that can stay closed in a room.
#
# **Why the unit is knowable at all.** Nothing here declares a currency or a period, so it was derived
# from an identity the metrics themselves satisfy: `spend_commit_balance_total / total_overage` = 36.55,
# and the independent `forecast_months_remaining` = 36.64 - agreeing to 0.3%. That only holds if
# `total_overage` is a MONTHLY run-rate against the same commitment the balance is drawn from. Verified
# 2026-08-19. Re-derive rather than trust this if the two ever diverge.
#
# **`_included_*` are all ZERO and that is not a bug.** metrics/logs/grafana included volumes read 0 while
# billable is 11.95M series / 12,486 units / 553 users. This is a pure spend-commit contract: there is no
# bundled allowance, so "overage" is the WHOLE charge for the period and not an excess over an allowance.
# Presenting `total_overage` as "money spent above plan" would be wrong.
COMMIT_TOTAL = "sum(grafanacloud_org_spend_commit_credit_total)"
COMMIT_BALANCE = "sum(grafanacloud_org_spend_commit_balance_total)"
COMMIT_CONSUMED = f"{COMMIT_TOTAL} - {COMMIT_BALANCE}"
COMMIT_CONSUMED_SHARE = f"1 - ({COMMIT_BALANCE} / {COMMIT_TOTAL})"
RUN_RATE = "sum(grafanacloud_org_total_overage)"
FORECAST_MONTHS = "sum(grafanacloud_org_forecast_months_remaining)"
CONTRACT_START = "max(grafanacloud_org_contract_start_date)"
CONTRACT_END = "max(grafanacloud_org_contract_end_date)"
TERM_ELAPSED_SHARE = f"(time() - {CONTRACT_START}) / ({CONTRACT_END} - {CONTRACT_START})"
MONTHS_TO_END = f"({CONTRACT_END} - time()) / (60*60*24*30.44)"
# **The COMPLETE decomposition of `grafanacloud_org_total_overage`, and completeness is the point.**
#
# This was six components, chosen because they were the obvious ones. Measured 2026-08-19, those six sum
# to 58,235.43 against a total of 76,521.76 - the chart was missing **18,286.33/month, 24% of the run
# rate**, and it was missing it silently: six bars beside a total that nothing on the page reconciled to.
# The absent lines were not rounding. Infrastructure Observability alone (containers + hosts) is
# 11,242.33 and Synthetic Monitoring (core + browser checks) is 5,180.75.
#
# All 24 components verified to sum EXACTLY to `grafanacloud_org_total_overage`:
# 58,235.43 + 18,286.33 = 76,521.76. So the set is complete and nothing is double-counted.
#
# **`logs`/`traces`/`profiles` and their `_process_`/`_retention_` siblings are INDEPENDENT billing
# dimensions, not a rollup and its parts.** Summing only the three top-level names undercounts; summing
# all three per product is what reconciles. Do not "simplify" this by dropping the sub-splits.
#
# A component reading exactly 0 has a real reporting series and genuinely means "no charge on this line",
# not "not measured" - verified per component, 1,442 samples over 24h each.
PRODUCT_OVERAGES = (
    ("grafanacloud_org_metrics_overage", "metrics"),
    ("grafanacloud_org_grafana_overage", "Grafana users"),
    ("grafanacloud_org_infra_o11y_container_overage", "Infra o11y - containers"),
    ("grafanacloud_org_sm_overage", "Synthetic Monitoring"),
    ("grafanacloud_org_logs_overage", "logs - ingest"),
    ("grafanacloud_org_infra_o11y_host_overage", "Infra o11y - hosts"),
    ("grafanacloud_org_assistant_overage", "Assistant"),
    ("grafanacloud_org_logs_retention_overage", "logs - retention"),
    ("grafanacloud_org_sm_browser_overage", "Synthetic Monitoring - browser"),
    ("grafanacloud_org_app_o11y_overage", "Application Observability"),
    ("grafanacloud_org_irm_users_overage", "IRM users"),
    ("grafanacloud_org_traces_overage", "traces - ingest"),
    ("grafanacloud_org_k6_virtual_user_hours_overage", "k6 - virtual-user hours"),
    ("grafanacloud_org_fe_o11y_overage", "Frontend Observability"),
    ("grafanacloud_org_k6_ip_overage", "k6 - static IPs"),
    ("grafanacloud_org_profiles_overage", "profiles - ingest"),
    ("grafanacloud_org_ai_tokens_overage", "AI tokens"),
    ("grafanacloud_org_db_o11y_overage", "Database Observability"),
    ("grafanacloud_org_grafana_plugin_users_overage", "Grafana plugin users"),
    ("grafanacloud_org_logs_process_overage", "logs - process"),
    ("grafanacloud_org_profiles_process_overage", "profiles - process"),
    ("grafanacloud_org_profiles_retention_overage", "profiles - retention"),
    ("grafanacloud_org_traces_process_overage", "traces - process"),
    ("grafanacloud_org_traces_retention_overage", "traces - retention"),
)

# The sum of the components, for the reconciliation panel. If this and `RUN_RATE` ever diverge, Grafana
# Cloud has added a billing line and `PRODUCT_OVERAGES` is no longer complete - which is exactly the
# condition that made the six-component chart wrong, so it is now a panel rather than an assumption.
COMPONENT_SUM = " + ".join(f"sum({metric})" for metric, _ in PRODUCT_OVERAGES)
RECONCILIATION_GAP = f"{RUN_RATE} - ({COMPONENT_SUM})"



def _api(method: str, path: str, token: str, body=None, base: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{base or BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(900).decode("utf-8", "replace")


def resolve_ds_uid(token: str) -> str:
    code, body = _api("GET", f"/api/datasources/name/{DS_NAME.replace(' ', '%20')}", token)
    if code != 200 or not isinstance(body, dict):
        raise SystemExit(f"cannot resolve datasource {DS_NAME!r}: {code} {body}")
    return body["uid"]


def resolve_folder_uid(token: str) -> str:
    """`/api/folders` lists ROOT level only - a nested folder needs its parent named explicitly.

    A deployment may place the configured insights folder below any root folder, so a flat listing can
    report that it does not exist when it is merely nested.
    """
    code, roots = _api("GET", "/api/folders?limit=500", token)
    if code != 200 or not isinstance(roots, list):
        raise SystemExit(f"cannot list folders: {code} {roots}")
    for folder in roots:
        if folder.get("title") == FOLDER_TITLE:
            return folder["uid"]
    # Descend one level into each root folder.
    for parent in roots:
        code, children = _api("GET", f"/api/folders?limit=500&parentUid={parent['uid']}", token)
        if code == 200 and isinstance(children, list):
            for child in children:
                if child.get("title") == FOLDER_TITLE:
                    return child["uid"]
    raise SystemExit(f"folder {FOLDER_TITLE!r} not found at root or one level down")


# --- dashboard definitions ------------------------------------------------------------------------
# Each returns (uid, title, description, elements, tabs). Views are named exactly as the pillars emit
# them; a typo fails at build time because read_view() 404s.

def d_estate(ds: str):
    el = {
        "n_stacks": build.stat_panel(
            "Stacks", 'gcinsight_estate_stacks{status="total"}',
            description="Every stack in the configured Grafana Cloud organisation, paused ones "
                        "included. This is the "
                        "denominator for most percentages on these dashboards - but NOT for signal "
                        "adoption, which divides by the stacks that ingest that signal. The estate moves, "
                        "so use the displayed denominator rather than copying it into prose."),
        "n_active": build.stat_panel(
            "Active", 'gcinsight_estate_stacks{status="active"}',
            description="Stacks not paused. A PAUSED stack answers HTTP 409 to the control plane, so it is "
                        "SKIPPED by a scan rather than counted as a failure - coverage is measured against "
                        "scannable stacks, never the total, or paused stacks would permanently cap the "
                        "ratio and train everyone to ignore the warning."),
        "n_dash": build.stat_panel(
            "Dashboards", "gcinsight_estate_dashboards",
            description="Dashboards that EXIST across the estate, summed from each stack's `dashboardCnt`. "
                        "It says nothing about whether any of them are opened. The Dashboard usage "
                        "dashboard measures opens separately through each stack's own usage-insights "
                        "datasource; read the two together as a consolidation question."),
        "n_users": build.stat_panel(
            "Users (billed)", "gcinsight_cost_billed_users",
            description="`billingActiveUsers` - **the only user count valid for money.** Deliberately not "
                        "`currentActiveUsers`, which is an ADOPTION figure. Never quote one as the other; "
                        "the spread moves with the estate, so `bin/trace.py` "
                        "recomputes it on every run instead of hardcoding it."),
        "t_stacks": build.timeseries_panel(
            "Estate size over time",
            [('gcinsight_estate_stacks{status="total"}', "total"),
             ('gcinsight_estate_stacks{status="active"}', "active"),
             ('gcinsight_estate_stacks{status="paused"}', "paused")],
            description="Provisioning velocity. A step change with no matching users is stack leakage."),
        "t_content": build.timeseries_panel(
            "Dashboards and alert rules",
            [("gcinsight_estate_dashboards", "dashboards"),
             ("gcinsight_estate_alert_rules", "alert rules")],
            description="Content growth. Both lines only ever rising is the normal and slightly worrying "
                        "case: growth is visible while deletion is not. Cross-read with the Operations "
                        "dashboard's live engagement ratio before treating rule growth as maturity."),
        "t_users": build.timeseries_panel(
            "Users - adoption vs billed",
            [("gcinsight_estate_active_users", "active (adoption)"),
             ("gcinsight_cost_billed_users", "billed (money)"),
             ("gcinsight_estate_daily_users", "daily")],
            description="Only the billed line is valid in a cost calculation."),
        "t_roles": build.timeseries_panel(
            "Users by role",
            [('gcinsight_estate_users_by_role{role="admin"}', "admin"),
             ('gcinsight_estate_users_by_role{role="editor"}', "editor"),
             ('gcinsight_estate_users_by_role{role="viewer"}', "viewer")], stacked=True,
            description="Role mix across the estate, stacked so the top edge is total assignments. A "
                        "healthy estate is viewer-heavy; the admin share here is the governance signal, "
                        "and the Risk dashboard's Admin sprawl view names the stacks where admins are the "
                        "majority. Counts ROLE ASSIGNMENTS per stack, so one person on ten stacks counts "
                        "ten times - this is a permissions measure, not a headcount."),
        "n_us_region": build.stat_panel(
            "Stacks in US regions", "max_over_time(gcinsight_estate_us_region_stacks[24h])",
            description="Stacks whose data is stored in a US region. For a Swiss pharma this is a data-"
                        "residency question rather than a technical one, which is why it gets its own "
                        "number instead of being read off the region chart. It counts where the STACK "
                        "lives, not where the monitored workload runs - an EU stack can still be "
                        "collecting from US infrastructure, and that is not visible from here."),
        "n_drift": build.stat_panel(
            "Stacks off the standard Grafana build",
            "max_over_time(gcinsight_estate_version_drift_stacks[24h])",
            description="Stacks not on the version the rest of the estate runs. The table on this tab "
                        "names them. Drift is not automatically a fault - a stack can be deliberately "
                        "pinned - but an unexplained one usually means an upgrade that silently did not "
                        "complete."),
        "b_leftover": build.barchart_panel(
            "Test leftovers by class", "max_over_time(gcinsight_estate_test_leftover_stacks[24h])",
            legend="{{kind}}",
            description="Stacks that look like abandoned tests, split by whether they COST anything. "
                        "`idle` ones are clutter and carry no charge; `billing` ones are being paid for "
                        "and nobody is using them, which makes them the only actionable half. The two "
                        "tables on the Leakage tab name the stacks in each class."),
        "b_region": build.barchart_panel(
            "Stacks by region", "gcinsight_estate_stacks_by_region", legend="{{region}}",
            description="Where each stack's data is stored, biggest region first. Data residency is the "
                        "reason this matters for a pharma customer - the US-region count beside this is "
                        "the number worth asking about. Counts STACKS, not workloads: a stack in an EU "
                        "region can still be collecting from US infrastructure."),
        "estate": build.table_panel(
            "Every stack, by active series", "estate", ds,
            description="Admin share is blank where a stack has no users - 0% would read as healthy."),
        "drift": build.table_panel(
            "Stacks off the standard Grafana build", "estate_drift", ds,
            columns=['Stack', 'Region', 'Cluster', 'Version drift', 'Active series', 'Users (active)', 'Age (days)'],
            description="Stacks not on the version the rest of the estate runs. Being behind is not automatically "
                        "wrong - the question each row asks is whether that pin was deliberate and is "
                        "still needed, because a forgotten pin misses security fixes silently."),
        "idle": build.table_panel(
            "Test leftovers - idle, cost nothing", "estate_leftovers_idle", ds,
            columns=['Stack', 'Region', 'Idle (days)', 'Age (days)', 'Active series', 'Users (active)', 'Dashboards', 'Delete protection'],
            description="Governance and attack surface, NEVER automatically a saving. These rows meet "
                        "the live idle-test criteria shown in the table; verify current volume before "
                        "acting."),
        "billing": build.table_panel(
            "Test leftovers that DO bill", "estate_leftovers_billing", ds,
            columns=['Stack', 'Region', 'Idle (days)', 'Active series', 'Users (billed)', 'Users (active)', 'Dashboards', 'Delete protection'],
            schema=estate_pillar.VIEW_SCHEMAS["estate_leftovers_billing"],
            description="Rows that still carry billed use. This is the cost conversation; the idle "
                        "table beside it is governance rather than a saving."),
        # --- T4 estate diff, BOTH windows (PLAN 13.2) -------------------------------------------------
        # These views existed from deployment and nothing rendered them - T4 published a diff nobody could
        # see. Measured and fixed 2026-08-19. Daily first: it is the one that answers "what changed since
        # yesterday", which is what somebody opening this tab in the morning wants.
        #
        # Each table's FIRST ROW is a `COMPARISON WINDOW` row naming the window and the interval actually
        # achieved. Two diff tables are otherwise indistinguishable, and reading the daily one as weekly
        # overstates every change sevenfold.
        "diff_daily": build.table_panel(
            "What changed since yesterday", "estate_diff_daily", ds,
            description="Day-over-day. Read the COMPARISON WINDOW row first - the baseline is the scan "
                        "NEAREST 1 day back, not exactly a day, and the row states the real interval. "
                        "Refuses a baseline under 12h or over 3 days rather than mislabelling one; the "
                        "table is simply absent if neither bound could be met, which is honest rather "
                        "than a broken panel. Rows reading 'not measured in both scans' mean one side was "
                        "a T1 inventory scan with no data plane - never that the value was zero."),
        "diff_weekly": build.table_panel(
            "What changed over the last week (read the actual interval)", "estate_diff", ds,
            description="Week-over-week, the same table over a 7-day target. Read the COMPARISON WINDOW "
                        "row before interpreting any delta: the achieved interval and measured "
                        "populations are part of the result. Prefers a T3 scan as the baseline because "
                        "that carries the data plane; "
                        "with T3 now running every 6 hours the four Adaptive/Fleet/cardinality rows "
                        "should populate rather than reading 'not measured in both scans'."),
        "t_coverage": build.timeseries_panel(
            "Scan coverage by tier",
            [('gcinsight_scan_coverage_ratio{tier="t1"}', "t1"),
             ('gcinsight_scan_coverage_ratio{tier="t2"}', "t2"),
             ('gcinsight_scan_coverage_ratio{tier="t3"}', "t3")], unit="percentunit",
            description="Below 1.0 means stacks failed. A partial scan is reported as partial, never as "
                        "a smaller estate."),
        "t_carry": build.timeseries_panel(
            "Carry-forward age", [('gcinsight_carry_forward_age_seconds{tier="t1"}', "t1 state age")],
            unit="s", description="Age of the data-plane state the hourly tier is republishing. ALERT ON "
                                  "THIS. Past the staleness cap the hourly tier stops republishing and "
                                  "the dependent panels go empty rather than presenting old figures as "
                                  "current - the emptiness is the honest signal. The cap is set in "
                                  "`collector/emit/carry.py`; it is deliberately not repeated here, "
                                  "because a number written into a description drifts from the constant "
                                  "it describes and this one already did."),

        # --- Scan accounting and runtime. Both were declared metrics with no panel anywhere. ----------
        #
        # `tier=~"t1|t2|t3"` is NOT cosmetic: T4 reads prior scans from S3 and never touches a stack, so
        # it emits no stacks_* series at all. Without the filter T4 renders as a permanent gap that reads
        # exactly like a failing tier.
        "t_accounting": build.timeseries_panel(
            "Stacks scanned vs scannable, by tier",
            [('max_over_time(gcinsight_scan_stacks_total{tier=~"t1|t2|t3"}[24h])', "{{tier}} total"),
             ('max_over_time(gcinsight_scan_stacks_scannable{tier=~"t1|t2|t3"}[24h])', "{{tier}} scannable"),
             ('max_over_time(gcinsight_scan_stacks_scanned{tier=~"t1|t2|t3"}[24h])', "{{tier}} scanned")],
            description="The accounting behind the coverage ratio: total estate, the part a healthy scan "
                        "is expected to reach, and what it actually reached. `scannable` is below `total` "
                        "by the number of PAUSED stacks, which are excluded by design - counting them as "
                        "failures would cap coverage below 100% for ever and train everyone to ignore it. "
                        "T4 is excluded because it makes no API calls and scans nothing, so it has no "
                        "coverage to report; including it would render a permanent gap that looks like a "
                        "dead tier."),
        "b_skipped": build.barchart_panel(
            "Stacks skipped, by reason",
            'max_over_time(gcinsight_scan_stacks_skipped{tier="t1"}[24h])', legend="{{reason}}",
            description="Stacks a healthy scan deliberately does not reach, by reason. `paused` stacks "
                        "have no running Grafana to query. These are excluded from the coverage "
                        "denominator rather than counted as failures."),
        "b_failed": build.barchart_panel(
            "Stacks that FAILED, by reason",
            'max_over_time(gcinsight_scan_stacks_failed{tier=~"t1|t2|t3"}[24h]) or on() vector(0)',
            legend="{{reason}}",
            description="Real scan failures, by cause. **An empty result here means zero failures, which "
                        "is the one place on these dashboards where absence does NOT mean 'not "
                        "measurable'** - the collector emits a series only for a failure reason it "
                        "actually recorded, so nothing recorded means nothing failed. `or vector(0)` "
                        "makes that read as 0 rather than as 'No data', which would suggest an outage."),
        "t_duration": build.timeseries_panel(
            "Scan runtime by tier",
            [('max_over_time(gcinsight_scan_duration_seconds[24h])', "{{tier}}")],
            unit="s",
            description="How long each tier takes. The question it answers is whether a tier is "
                        "approaching its own schedule interval, because a run that overruns its interval "
                        "overlaps the next one and both write `latest.json`. Every tier currently sits far "
                        "below its interval - the closest is well under 1% of it - so there is real "
                        "headroom. Watch for a trend rather than a value: steady growth here is the early "
                        "warning, and the deadline in `terraform/variables.tf` is the backstop."),
        "t_carry_series": build.timeseries_panel(
            "Series carried forward vs computed live",
            [('max_over_time(gcinsight_carry_forward_series{tier="t1"}[24h])', "carried from state")],
            description="How much of what the hourly tier publishes is REPUBLISHED from the data-plane "
                        "tier's saved state rather than freshly measured. It is not a fault - it is the "
                        "mechanism that stops 6-hourly figures rendering empty between runs - but it is "
                        "worth seeing, because everything counted here is as old as the carry-forward age "
                        "beside it."),

        "t_carry_dropped": build.timeseries_panel(
            "Carried series DROPPED because their stack has left the estate",
            [('max_over_time(gcinsight_carry_forward_dropped_absent[24h])', "{{tier}}")],
            description="The golden rule made visible. Republishing saved state would keep a "
                        "decommissioned stack alive on every panel for as long as the state is carried, "
                        "so carry-forward re-checks the LIVE inventory and drops any series whose stack "
                        "is gone. A spike here is a decommission, and it should be followed by that "
                        "stack disappearing from the per-stack tables. A spike with no known "
                        "decommission is the one to investigate: it can also mean an inventory call "
                        "returned a short list."),

        # --- Input freshness, the other half of the same story ----------------------------------------
        "t_inputs": build.timeseries_panel(
            "Age of each input, by consuming tier",
            [('gcinsight_input_age_seconds', "{{tier}} <- {{input}}")],
            unit="s",
            description="Since every tier now composes from the full input set - pulling what it did not "
                        "gather from the tier that did - this is the age of the DATA each published figure "
                        "was computed from, as opposed to the age of the run that published it. The two "
                        "differ by hours and it is the input age that governs how current a number is. A "
                        "line that climbs without resetting means the tier that gathers that input has "
                        "stopped; past the cap its dependent views stop being republished."),
        "t_input_avail": build.timeseries_panel(
            "Inputs available, by consuming tier",
            [('gcinsight_input_available', "{{tier}} <- {{input}}")],
            description="1 means the input was available and fresh enough to use; 0 means the views "
                        "depending on it were WITHHELD rather than published with zeros in place of the "
                        "figures it feeds. A drop to 0 here is the signal that a table elsewhere has "
                        "stopped advancing - which is deliberately what happens instead of that table "
                        "quietly falling to zero."),
    }
    tabs = [
        build.tab("Overview", ["n_stacks", "n_active", "n_dash", "n_users", "t_stacks",
                               "t_content", "t_users"]),
        build.tab("Composition", ["t_roles", "b_region", "n_us_region", "n_drift", "drift"]),
        build.tab("All stacks", ["estate"]),
        build.tab("Leakage", ["b_leftover", "idle", "billing"]),
        build.tab("Change", ["diff_daily", "diff_weekly"]),
        build.tab("Scan health", ["t_coverage", "t_accounting", "b_skipped", "b_failed",
                                  "t_duration", "t_carry", "t_carry_series", "t_carry_dropped"]),
        build.tab("Data freshness", ["t_inputs", "t_input_avail"]),
    ]
    return "gcinsight-estate", "Grafana Cloud Org Insights - Estate", \
        "Pillar A: estate and tenant health across the live stack population.", el, tabs


def _prom_number(value: float) -> str:
    """Stable PromQL literal for a validated rate-card number."""
    return f"{float(value):.15g}"


def _dpm_pricing(card: ratecard_model.RateCard | None) -> dict[str, str] | None:
    """Build the DPM-aware per-stack pricing expressions from the deployed card, or stay absent.

    The card is the authority for every constant. The calculation deliberately remains in
    `grafanacloud-usage`: active series and total DPM are billing-side inputs, and piping them through
    the collector would spend series merely to reproduce a datasource already on the target stack.
    """
    if card is None:
        return None
    metrics_rate = card.rates.get("metrics_series")
    if (metrics_rate is None or metrics_rate.billing_basis != "dpm_aware"
            or metrics_rate.included_dpm is None):
        return None

    rate = _prom_number(metrics_rate.rate)
    per = _prom_number(metrics_rate.per)
    included_dpm = _prom_number(metrics_rate.included_dpm)
    active = (
        "quantile_over_time(0.95, "
        "(sum by(stack_id)(grafanacloud_instance_active_series < Inf))[30d:])"
    )
    total_dpm = (
        "(quantile_over_time(0.95, "
        "(sum by(stack_id)(grafanacloud_instance_samples_per_second < Inf))[30d:]) * 60)"
    )
    dpm_floor = f"(({total_dpm}) / {included_dpm})"
    # `or` fills stacks where the recommendation gauge is absent with a real zero. Without it the
    # after-vector drops healthy/no-recommendation stacks and an estate after-total becomes partial.
    reduction = (
        "(sum by(stack_id)(grafanacloud_instance_recommendations_estimated_savings_series) "
        f"or on(stack_id) (0 * ({active})))"
    )
    after_active = f"clamp_min(({active}) - ({reduction}), 0)"
    # PromQL has no scalar max for two vectors. `floor + clamp_min(value-floor, 0)` is element-wise max
    # and, critically, is applied while `stack_id` still exists. Summing first would let a low-DPM stack
    # subsidise a DPM-dominated one and overstate the saving.
    before_usage = f"(({dpm_floor}) + clamp_min(({active}) - ({dpm_floor}), 0))"
    after_usage = f"(({dpm_floor}) + clamp_min(({after_active}) - ({dpm_floor}), 0))"
    before_cost = f"(({before_usage}) / {per} * {rate})"
    after_cost = f"(({after_usage}) / {per} * {rate})"
    saving = f"(clamp_min(({before_usage}) - ({after_usage}), 0) / {per} * {rate})"
    return {
        "currency": card.currency,
        "period": metrics_rate.period,
        "included_dpm": included_dpm,
        "rate": rate,
        "per": per,
        "active": active,
        "dpm_floor": dpm_floor,
        "after_active": after_active,
        "before": before_cost,
        "after": after_cost,
        "saving": saving,
    }


def _dpm_regime_savings(dpm: dict[str, str]) -> str:
    """Top per-stack savings with the before->after billing regime attached as a bounded label."""
    top = f"topk(15, {dpm['saving']})"
    active = dpm["active"]
    after = dpm["after_active"]
    floor = dpm["dpm_floor"]
    transitions = (
        ("active-series -> active-series", f"({active}) > ({floor})", f"({after}) > ({floor})"),
        ("active-series -> balanced", f"({active}) > ({floor})", f"({after}) == ({floor})"),
        ("active-series -> DPM", f"({active}) > ({floor})", f"({after}) < ({floor})"),
        ("balanced -> balanced", f"({active}) == ({floor})", f"({after}) == ({floor})"),
        ("balanced -> DPM", f"({active}) == ({floor})", f"({after}) < ({floor})"),
        ("DPM -> DPM", f"({active}) < ({floor})", f"({after}) < ({floor})"),
    )
    labelled = []
    for regime, before_predicate, after_predicate in transitions:
        selected = (
            f"(({top}) and on(stack_id) ({before_predicate}) "
            f"and on(stack_id) ({after_predicate}))"
        )
        labelled.append(f'label_replace({selected}, "regime", "{regime}", "", "")')
    return "(" + " or ".join(labelled) + ")"


def d_cost(ds: str, *, rate_card: ratecard_model.RateCard | None = None):
    recommendation_view_live = _published_views_exist("cost_adaptive_metric_recommendations")
    adaptive_logs_view_live = _published_views_exist("cost_adaptive_logs")
    dpm = _dpm_pricing(rate_card)
    el = {
        "n_series": build.stat_panel(
            "Active series (org)", 'sum(gcinsight_stack_active_series{stack=~"$stack"})',
            description="The metrics cost driver: Grafana Cloud bills on ACTIVE SERIES, not on queries or "
                        "samples. Respects the `$stack` selector, so it is the estate total only when "
                        "`$stack` is All. Sourced from each stack's own reported active series - NOT the "
                        "same instrument as the billing-side average on the Commercial dashboard, and the "
                        "two legitimately differ. Never quote one as the other."),
        "n_ratio": build.stat_panel(
            "Series per billed user", "gcinsight_cost_series_per_billed_user", decimals=0,
            description="Active series divided by BILLED users - the estate's unit economics in one "
                        "number, and the line to watch over time. Falling means the platform is getting "
                        "more efficient per person; rising means series growth is outpacing adoption. "
                        "Uses the billed figure, not active users, because this is a money ratio."),
        "n_pending": build.stat_panel(
            "Adaptive recs pending",
            'sum(gcinsight_adaptive_recommendations{status="pending",stack=~"$stack"})',
            description="Adaptive Metrics aggregation RULES that Grafana Cloud has recommended and nobody "
                        "has applied. A count of recommendations, not of series - for the volume they "
                        "would actually remove see the live Savings available tab."),
        "n_unadopted": build.stat_panel(
            "Stacks with 0 rules applied", "gcinsight_cost_stacks_without_adaptive",
            description="Stacks that HAVE pending Adaptive Metrics recommendations and have applied none "
                        "of them - so the saving has been calculated for them and ignored. Cross-read "
                        "the headroom table for the named stacks and the Maturity dashboard for the "
                        "independent `adaptive_adoption` score."),
        "n_rules_applied": build.stat_panel(
            "Adaptive rules applied", "gcinsight_cost_adaptive_rules_applied_total",
            description="Aggregation rules already in force across the estate - the numerator to the "
                        "pending count beside it. Without it a rising pending figure is unreadable: it "
                        "can mean nobody is acting, or that Grafana Cloud is recommending faster than "
                        "the organisation can apply."),
        "t_billed_top": build.timeseries_panel(
            "Top 10 stacks by billed users",
            [('topk(10, gcinsight_stack_billed_users{stack=~"$stack"})', "{{stack}}")],
            description="`billingActiveUsers` per stack - the only user count valid for money, and the "
                        "per-stack detail behind the estate figure on the Overview tab. Deliberately not "
                        "`currentActiveUsers`, which measures adoption and runs higher; the spread "
                        "between them moves, so read both rather than converting one into the other."),
        "t_series": build.timeseries_panel(
            "Org active series", [('sum(gcinsight_stack_active_series{stack=~"$stack"})', "total")],
            description="The metrics cost driver. Growth here is the bill growing."),
        "t_top": build.timeseries_panel(
            "Top 10 stacks by active series",
            [('topk(10, gcinsight_stack_active_series{stack=~"$stack"})', "{{stack}}")],
            description="The stacks driving the metrics bill, largest first. Concentration is the point: "
                        "estate-wide averages hide a dominant stack. Use the live ranking to choose the "
                        "owners whose changes can materially move the total; do not preserve a dated share "
                        "in the tooltip."),
        "t_adaptive": build.timeseries_panel(
            "Adaptive Metrics - applied vs pending",
            [('sum(gcinsight_adaptive_recommendations{status="applied",stack=~"$stack"})', "applied"),
             ('sum(gcinsight_adaptive_recommendations{status="pending",stack=~"$stack"})', "pending")],
            description="The gap is the unrealised saving. Watch `applied` rise as remediation lands."),
        "t_unadopted": build.timeseries_panel(
            "Stacks with recommendations and zero rules applied",
            [("gcinsight_cost_stacks_without_adaptive", "stacks")],
            description="The trend behind the headline finding. Falling is improvement only when "
                        "recommendations are being applied rather than disappearing with missing data."),
        # A warning in a tooltip does not make an incomparable chart honest. This was one bar chart
        # with metrics SERIES (millions) beside log and trace VOLUME (single digits) on one axis: the
        # volume bars were invisible and the chart said nothing except "metrics is denominated in a bigger
        # unit". Split by unit, so within each panel the bars really are comparable.
        "b_signal_series": build.barchart_panel(
            "Current usage - signals billed by SERIES",
            'gcinsight_cost_usage_by_signal{signal=~"metrics|graphite"}', legend="{{signal}}",
            description="Series-denominated signals only, so these bars are directly comparable. Metrics "
                        "dominates the estate and dominates the bill; Graphite is two stacks. For what "
                        "each signal actually COSTS rather than how much of it there is, the Commercial "
                        "dashboard's run-rate breakdown is the money view."),
        "b_signal_volume": build.barchart_panel(
            "Current usage - signals billed by VOLUME",
            'gcinsight_cost_usage_by_signal{signal=~"logs|traces|profiles"}', legend="{{signal}}",
            description="Volume-denominated signals only. Kept apart from the series-denominated ones "
                        "because putting them on one axis made these bars invisible next to a metrics bar "
                        "several million units tall - the chart looked like logs and traces were unused, "
                        "which is the opposite of the truth. Read against their own history."),
        "summary": build.table_panel(
            "Cost summary", "cost_summary", ds,
            description="Leads with the denominator. 'Savings in currency' states why it is unavailable "
                        "rather than rendering blank."),
        "headroom": build.table_panel(
            "Adaptive headroom - sorted by remediable volume", "cost_adaptive_headroom", ds,
            description="Pending recommendations, zero rules applied. Sorted by what you can remove, "
                        "not by spend."),
        "cardinality": build.table_panel(
            "Cardinality outliers", "cost_cardinality_outliers", ds,
            description="The exact ranked and filterable work queue behind the treemap. Worst label NAME "
                        "per stack is unbounded, so it lives here and never in a metric label."),
        "cardinality_treemap": build.treemap_panel(
            "Cardinality concentration across stacks", "cost_cardinality_outliers", ds,
            text_field="Stack", size_field="Label values",
            color_by_field="Worst label values",
            label_fields=("Active series", "Worst label", "Worst label values"),
            description="Each rectangle's AREA is the stack's total label values, so this view answers "
                        "whether cardinality is concentrated in a few stacks or spread across the estate. "
                        "Hover for active series and the worst-label detail; use the native table beside "
                        "it for exact ranking and filtering. Colour is retained as context but was not "
                        "visually strong enough in the live spike to carry a decision."),
        "cost": build.table_panel(
            "Per-stack cost drivers", "cost", ds,
            description="Every stack's usage per signal, largest first - the chargeback table, with no "
                        "queries behind it. A blank cell means NOT MEASURED rather than zero; the tier "
                        "that owns that column had no data for that stack."),
        "signals": build.table_panel(
            "Usage by signal - Current vs Billing", "cost_signal_usage", ds,
            description="Current activity and the billing population answer different questions. Compare "
                        "the two live columns rather than treating a dated gap as a constant."),

        # --- Adaptive Metrics savings in SERIES, live from `grafanacloud-usage` ------------------------
        # The rest of this dashboard counts recommendations because that is all the aggregations API
        # gives; the summary view says so in a row titled "Savings in currency". This tab is the volume
        # the recommendations would actually remove, which the billing datasource reports per stack.
        # Still not currency - converting series to pounds needs the organisation's contract, not another metric.
        "n_savings": build.stat_panel(
            "Series Adaptive Metrics would remove", SAVINGS_SERIES, ds_uid=build.USAGE_UID,
            description="Series that existing Adaptive Metrics recommendations estimate they would "
                        "remove. Nothing needs to be discovered, only reviewed and applied. This is a "
                        "live gauge over a moving estate, so use the displayed value rather than a "
                        "number copied from a tooltip."),
        "n_savings_pct": build.stat_panel(
            "Share of the estate that is removable", SAVINGS_FRACTION, unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="Estimated removable series divided by the estate's active series. Read it as "
                        "the share aggregatable without losing a query, not as the share of the bill "
                        "that disappears "
                        " - the pricing conversion is not in this datasource."),
        "n_savings_stacks": build.stat_panel(
            "Stacks with savings on the table", SAVINGS_STACKS, ds_uid=build.USAGE_UID,
            description="How many stacks have at least one Adaptive Metrics recommendation waiting. "
                        "Read it "
                        "against 'Stacks actually aggregating' beside it; the gap between the two is the "
                        "finding, not either number alone."),
        "n_aggregating": build.stat_panel(
            "Stacks actually aggregating", AGGREGATING_STACKS, ds_uid=build.USAGE_UID,
            description="Stacks reporting non-zero aggregated series. The gap against the panel to its left is the whole "
                        "finding - recommendations are being generated estate-wide and acted on almost "
                        "nowhere."),
        "b_savings": build.barchart_panel(
            "Stacks that entered the top 15 during this window",
            build.usage_by_slug("topk(15, sum by(stack_id)("
                                "grafanacloud_instance_recommendations_estimated_savings_series))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID,
            description="A range `topk(15)` returns the UNION of every stack that entered the top 15 at "
                        "any step, so it can show more than 15 bars. Those extra entries are recovered "
                        "spikes, not a broken limit. Compare with the exact-size endpoint companion: "
                        "union-minus-endpoint names the stacks whose removable volume spiked and then fell."),
        "b_savings_endpoint": build.barchart_panel(
            "Top 15 at the window endpoint",
            build.usage_by_slug(
                "sum by(stack_id)(grafanacloud_instance_recommendations_estimated_savings_series) "
                "and on(stack_id) topk(15, sum by(stack_id)("
                "grafanacloud_instance_recommendations_estimated_savings_series @ end()))"
            ),
            legend="{{slug}}", ds_uid=build.USAGE_UID, limit=15,
            description="Membership is frozen to the top 15 at the range endpoint, then the range-safe "
                        "values are reduced, sorted and display-limited. Compare it with the union panel: "
                        "union-minus-endpoint names stacks that spiked during the window and recovered "
                        "before its endpoint."),
        # --- Adaptive LOGS (Pillar B, PLAN 18.16) -----------------------------------------------------
        # This block reads TWO sources on purpose, because neither one can answer both halves:
        #
        #   PENDING  -> our own collector series, from each stack's app-plugin proxy.
        #   APPLIED  -> `grafanacloud-usage`, live, no credential, zero series of ours.
        #
        # The split is forced by the API, not chosen: the Adaptive Logs payload reports each pattern's
        # RESIDUAL volume, so a pattern already dropped at a high rate reports almost no bytes and no
        # arithmetic on the payload can recover what it used to be. Computing an applied saving from it
        # would therefore understate the saving silently.
        "n_al_stacks": build.stat_panel(
            "Stacks with Adaptive Logs recommendations",
            "gcinsight_cost_adaptivelogs_stacks_with_recommendations",
            description="Stacks holding at least one Adaptive Logs recommendation. Read it against the "
                        "panel beside it: the gap between having recommendations and having applied any "
                        "of them is the finding, not either number alone. The denominator is the stacks "
                        "whose plugin proxy answered, which is its own panel on the coverage row."),
        "n_al_none": build.stat_panel(
            "...that have applied NONE of them",
            "gcinsight_cost_adaptivelogs_stacks_none_applied",
            description="Stacks carrying recommendations where not one pattern has a drop rate "
                        "configured. This is the Adaptive Metrics story repeating in logs: the "
                        "recommendations are generated automatically and acted on almost nowhere, which "
                        "is why the maturity dimension for adaptive adoption is the estate's weakest. "
                        "Each of these is one owner conversation."),
        "n_al_pending": build.stat_panel(
            "Log volume the recommendations would drop",
            "gcinsight_cost_adaptivelogs_pending_bytes_total", unit="bytes", decimals=1,
            description="Bytes existing recommendations would additionally drop, summed across the "
                        "estate. **This is a total over a window the Adaptive Logs API does not name** - "
                        "the endpoint states no period and ignores every window parameter it is given - "
                        "so do NOT divide it into a daily or per-second figure. For a real rate, use the "
                        "'currently being dropped' panel below, which comes from the billing datasource. "
                        "Already-dropped patterns report their residual volume, so this figure is the "
                        "pending half only and never double-counts a saving already taken."),
        "n_al_unqueried": build.stat_panel(
            "...with zero queried lines in the API window",
            "gcinsight_cost_adaptivelogs_pending_bytes_unqueried", unit="bytes", decimals=1,
            description="The subset with zero queried lines in the recommendation API's own unnamed "
                        "window. It is the lower-risk review queue, not proof that nobody has ever queried "
                        "these logs over their lifetime. Confirm the owning workload before applying a "
                        "recommendation."),
        "n_al_measured": build.stat_panel(
            "Stacks measured for Adaptive Logs",
            "gcinsight_cost_adaptivelogs_stacks_measured",
            description="The denominator. Every figure on this tab is a sum over these stacks, so a "
                        "drop here moves the totals without anything changing on the estate. It reads "
                        "the full provisionable estate when healthy, because the recommendation "
                        "endpoint answers on every stack whether or not Adaptive Logs is in use."),
        "n_al_recs": build.stat_panel(
            "Recommendations outstanding",
            "gcinsight_cost_adaptivelogs_pending_total",
            description="Individual log patterns with a recommended drop rate above what is configured. "
                        "A count of patterns, not of stacks - one stack can hold hundreds, so this "
                        "number is dominated by whichever stacks have the most fragmented logging."),
        "t_al_progress": build.timeseries_panel(
            "Adaptive Logs recommendations: outstanding vs total",
            [("gcinsight_cost_adaptivelogs_recommendations_total", "recommendations held"),
             ("gcinsight_cost_adaptivelogs_pending_total", "still outstanding")],
            description="The GAP between these two lines is how many patterns have actually been given "
                        "a drop rate, and the success condition is that gap widening. Two lines rather "
                        "than one derived 'applied' series on purpose: the count of applied patterns is "
                        "real, but the BYTES they save are not recoverable from this API, and a single "
                        "line labelled 'applied' invites reading a saving off it. For the saving, the "
                        "billing datasource panel below is the honest source."),
        "b_al_top": build.barchart_panel(
            "Biggest pending log savings, by stack",
            "topk(15, gcinsight_cost_adaptivelogs_pending_bytes)",
            legend="{{stack}}", unit="bytes",
            description="A work queue, largest first. Concentration is the point: start at the top "
                        "because a handful of owner conversations move the estate total more than the "
                        "long tail combined. Bytes are over the API's own unstated window - use them to "
                        "RANK stacks, not as a monthly figure."),
        "t_al_dropping": build.timeseries_panel(
            "Log volume currently being dropped by Adaptive Logs",
            [("sum(grafanacloud_logs_instance_adaptivelogs_bytes_dropped_per_second)",
              "estate bytes/sec dropped"),
             ("sum(grafanacloud_logs_instance_adaptivelogs_policy_bytes_dropped_per_second)",
              "of which policy-driven")],
            unit="Bps", ds_uid=build.USAGE_UID,
            description="The REALISED saving, and the only place on this tab with an honest rate. It "
                        "comes from the billing datasource rather than our collector, so it is live "
                        "rather than on the daily sweep and will not agree to the second with the "
                        "pending figures above. The success condition is this line rising while the "
                        "pending total falls."),
        "n_al_dropping_stacks": build.stat_panel(
            "Stacks actually dropping log volume",
            _any_in_window("grafanacloud_logs_instance_adaptivelogs_bytes_dropped_per_second"),
            ds_uid=build.USAGE_UID,
            description="Measured over a window, never instantaneously - a per-second series compared "
                        "to zero answers 'is a drop happening in this scrape' rather than 'does this "
                        "stack use Adaptive Logs'. Corroborates the collector independently: the stacks "
                        "appearing here are the ones whose recommendation payload reports patterns "
                        "already configured, from a completely different source."),
        "t_savings": build.timeseries_panel(
            "Available vs realised aggregation",
            [(SAVINGS_SERIES, "series still removable"),
             ("sum(grafanacloud_instance_aggregation_aggregated_series)", "series aggregated today"),
             ("sum(grafanacloud_instance_aggregation_raw_series)", "raw series feeding aggregation")],
            ds_uid=build.USAGE_UID,
            description="The success condition is the first line falling while aggregated series rise. "
                        "Raw and aggregated are shown together so the reduction where aggregation is "
                        "enabled can be read from the live data rather than a frozen example."),
    }
    dpm_rows: list[dict[str, Any]] = []
    if dpm is not None:
        scope = (
            f"{dpm['currency']}/{dpm['period']}; {dpm['included_dpm']} included DPM; "
            f"rate {dpm['rate']} per {dpm['per']} series-equivalent. "
            "Before regime = max(30-day p95 active series, 30-day p95 total "
            "DPM / included DPM). After regime = the same max after subtracting the current "
            "per-stack Adaptive Metrics removable-series estimate."
        )
        currency_unit = f"currency{dpm['currency'].upper()}"
        el.update({
            "dpm_before": build.stat_panel(
                f"Metrics charge before recommendations ({dpm['currency']}/{dpm['period']})",
                f"sum({dpm['before']})", ds_uid=build.USAGE_UID,
                unit=currency_unit, decimals=2,
                description=f"{scope} The max is applied per stack before this estate sum; this is the "
                            "before figure, and the after figure beside it uses the identical population."),
            "dpm_after": build.stat_panel(
                f"Metrics charge after recommendations ({dpm['currency']}/{dpm['period']})",
                f"sum({dpm['after']})", ds_uid=build.USAGE_UID,
                unit=currency_unit, decimals=2,
                description=f"{scope} This is the modelled after figure, not a forecast that every "
                            "recommendation will be approved. Read the before panel for the same stack "
                            "population and billing regime."),
            "dpm_saving": build.stat_panel(
                f"DPM-aware removable metrics charge ({dpm['currency']}/{dpm['period']})",
                f"sum({dpm['saving']})", ds_uid=build.USAGE_UID,
                unit=currency_unit, decimals=2,
                description=f"{scope} This is before minus after per stack and then summed, never an "
                            "estate-wide series reduction priced as though every stack were active-series "
                            "dominated."),
            "dpm_by_stack": build.barchart_panel(
                f"DPM-aware saving by stack ({dpm['currency']}/{dpm['period']})",
                build.usage_by_slug(_dpm_regime_savings(dpm)),
                legend="{{slug}}  -  {{regime}}", ds_uid=build.USAGE_UID,
                unit=currency_unit, limit=15,
                description=f"{scope} The ranking shows where the before-to-after billing regime really "
                            "moves; a DPM-dominated stack can have many removable series and little or no "
                            "currency saving."),
        })
        dpm_rows = [
            build.row("Contract-aware result", ["dpm_before", "dpm_after", "dpm_saving"],
                      max_columns=3, row_height="short"),
            build.row("Where the bill moves", ["dpm_by_stack"], max_columns=1),
        ]
    if recommendation_view_live:
        el["adaptive_metric_recommendations"] = build.table_panel(
            "Metrics to review, ranked by removable series",
            "cost_adaptive_metric_recommendations", ds,
            schema=cost_pillar.VIEW_SCHEMAS["cost_adaptive_metric_recommendations"],
            description="A bounded action queue retained from each stack's largest recommendations. "
                        "`Dependencies` is the combined count of rule, query and dashboard references; "
                        "zero is the lower-risk queue, not permission to apply without the owner. The "
                        "table retains at most ten metrics per stack, so it is not a complete inventory.",
        )
    if adaptive_logs_view_live:
        el["adaptive_logs_recommendations"] = build.table_panel(
            "Adaptive Logs recommendations by stack",
            "cost_adaptive_logs", ds,
            schema=cost_pillar.VIEW_SCHEMAS["cost_adaptive_logs"],
            description="The named work queue behind the pending-volume panels. `Pending GB` is over "
                        "the recommendation API's unnamed window and is valid for ranking, not for a "
                        "monthly or per-second claim. `Pending GB (unqueried)` is the lower-risk review "
                        "subset, not permission to apply without the workload owner.",
        )
    savings_rows = [
        build.row("Headline", ["n_savings", "n_savings_pct", "n_savings_stacks", "n_aggregating"],
                  max_columns=3, row_height="short"),
        build.row("Where to act", ["b_savings", "b_savings_endpoint"], max_columns=2),
    ]
    if recommendation_view_live:
        savings_rows.append(build.row(
            "Which metrics", ["adaptive_metric_recommendations"],
            max_columns=1, row_height="tall",
        ))
    savings_rows.append(build.row("Progress", ["t_savings"], max_columns=1))
    adaptive_logs_rows = [
        build.row("Pending", ["n_al_stacks", "n_al_none", "n_al_recs"],
                  max_columns=3, row_height="short"),
        build.row("Volume on the table", ["n_al_pending", "n_al_unqueried"],
                  max_columns=2, row_height="short"),
        build.row("Progress", ["t_al_progress"], max_columns=1),
        build.row("Where to act", ["b_al_top"], max_columns=1),
    ]
    if adaptive_logs_view_live:
        adaptive_logs_rows.append(build.row(
            "Named recommendation queue", ["adaptive_logs_recommendations"],
            max_columns=1, row_height="tall",
        ))
    adaptive_logs_rows.extend([
        build.row("Already realised (live, billing datasource)",
                  ["t_al_dropping", "n_al_dropping_stacks"], max_columns=2),
        build.row("Coverage", ["n_al_measured"], max_columns=1, row_height="short"),
    ])
    tabs = [
        build.tab("Overview", ["n_series", "n_ratio", "n_pending", "n_rules_applied", "n_unadopted",
                               "t_series", "t_adaptive", "summary"]),
        build.tab("Levers", ["t_unadopted", "headroom", "cardinality_treemap", "cardinality"]),
        build.rows_tab("Savings available", savings_rows),
        build.rows_tab("Adaptive Logs", adaptive_logs_rows),
        build.tab("Biggest stacks", ["t_top", "t_billed_top", "cost"]),
        build.tab("Signals", ["b_signal_series", "b_signal_volume", "signals"]),
    ]
    if dpm_rows:
        tabs.insert(4, build.rows_tab("DPM-aware savings", dpm_rows))
    return "gcinsight-cost", "Grafana Cloud Org Insights - Cost", \
        "Pillar B: cost as diagnosis. The organisation's showback email already gives owners the number; this " \
        "says why it is that size and which lever moves it.", el, tabs


def d_usage(ds: str):
    el = {
        "n_stick": build.stat_panel(
            "Stickiness (daily/active)", "gcinsight_usage_stickiness_ratio",
            unit="percentunit", decimals=1,
            description="STICKINESS = daily active users / monthly active users. Of the people who used "
                        "Grafana at all this month, the share who used it TODAY - the standard DAU/MAU "
                        "ratio. High means the platform is part of the daily routine; low means people "
                        "log in only when something breaks. "
                        "**Deliberately not a money figure** - it uses active users, not billed, because "
                        "it measures behaviour rather than cost. It is a ratio of two estate-wide sums, so "
                        "one very large stack dominates it; the per-stack column in Per-stack engagement "
                        "is where you see who is actually sticky."),
        "n_types": build.stat_panel(
            "Datasource types in use", "gcinsight_usage_datasource_types_distinct",
            description="Distinct datasource plugin types provisioned anywhere in the estate - a breadth "
                        "measure of what the organisation connects Grafana to. Excludes "
                        "`grafana-knowledgegraph-datasource`, which is auto-provisioned on every stack and "
                        "would otherwise look like universal adoption of something nobody chose."),
        "t_stick": build.timeseries_panel(
            "Stickiness over time", [("gcinsight_usage_stickiness_ratio", "daily / active")],
            unit="percentunit",
            description="Of the people with access, how many showed up. Deliberately not a money figure."),
        "t_signals": build.timeseries_panel(
            "Stacks using each signal", [("gcinsight_usage_stacks_by_signal", "{{signal}}")],
            description="Thresholded above the synthetic floor of 2 series, never at >0."),
        "b_recency": build.barchart_panel(
            "Users by last-seen bucket", "gcinsight_usage_users_last_seen_bucket",
            # `sort=None` on purpose: these buckets are an ORDERED CATEGORY (recent -> never), so ranking
            # them by size destroys the one reading that matters - the shape of the decay. Every other
            # bar chart here sorts by value; this is the deliberate exception.
            legend="{{kind}}", sort=None,
            description="Every user who has ever logged in, grouped by how recently. Read it left to "
                        "right as a decay curve rather than as a ranking - the bars are in recency order, "
                        "not size order. `never` is the actionable bucket: an account that has never "
                        "logged in is a licence being paid for and a credential nobody is watching. The "
                        "per-user table beneath names them."),
        # --- Protocol adoption (SPEC 7.2 item 10, PLAN 3.3). ------------------------------------------
        # Reads the stack's OWN provisioned `grafanacloud-usage` datasource DIRECTLY. No collector, no
        # credential, no series of ours - the datasource is already on every stack, so there was never a
        # service account needed here. Consequences worth knowing:
        # * it is LIVE, not on our hourly write cadence, so it is fresher than every other panel here;
        # * the `id` label is the metrics instance id, NOT the stack slug, so `$stack` does not apply and
        # these panels are deliberately estate-level counts rather than per-stack breakdowns.
        "n_otlp": build.stat_panel(
            "Stacks above the OTLP floor", "count(grafanacloud_instance_active_otlp_series > 1000)",
            ds_uid=build.USAGE_UID,
            description="Stacks carrying more than 1,000 active OTLP series. The threshold is a "
                        "JUDGEMENT, not a protocol fact - it separates real OTLP traffic from the "
                        "synthetic floor described in the panel beside this one. Read it as 'stacks above "
                        "1,000 OTLP series', which is what it measures; it does not prove those stacks "
                        "have adopted OTLP as a standard, nor that the ones below it have not started."),
        "n_otlp_floor": build.stat_panel(
            "Stacks on the synthetic floor",
            "count(grafanacloud_instance_active_otlp_series <= 1000)",
            ds_uid=build.USAGE_UID,
            description="A small synthetic series floor exists even without meaningful OTLP traffic, "
                        "which is why the adoption threshold is above 1,000 rather than above zero. This "
                        "panel keeps that excluded population visible; refresh evidence/otlp-floor.json "
                        "before changing the threshold."),
        "t_otlp": build.timeseries_panel(
            "OTLP adoption over time",
            [("count(grafanacloud_instance_active_otlp_series > 1000)", "stacks above the floor"),
             ("count(grafanacloud_instance_active_otlp_series)", "stacks reporting any value")],
            ds_uid=build.USAGE_UID,
            description="The protocol-migration line. The gap between the two series is the synthetic "
                        "floor, and it is why the lower line is the only honest one."),
        "summary": build.table_panel(
            "Usage summary", "usage_summary", ds,
            description="The headline engagement figures with their denominators stated, so each number "
                        "can be checked rather than taken. Rows reading NOT MEASURABLE say why, rather "
                        "than rendering a zero that would look like a finding."),
        "usage": build.table_panel(
            "Per-stack engagement", "usage", ds,
            description="Per-stack users, daily actives and stickiness - this is where the estate-wide "
                        "stickiness number breaks down into who is actually using their stack. A stack "
                        "with users but zero daily actives is provisioned and unused; a blank cell is not "
                        "measured, never zero."),
        "plugins": build.table_panel(
            "Plugin adoption", "usage_plugin_adoption", ds,
            description="Which datasource types are provisioned and on how many STACKS (not how many "
                        "instances). Worth scanning for competitor datasources, which indicate another "
                        "monitoring platform may still be live somewhere. "
                        "Excludes the auto-provisioned knowledge-graph datasource."),
        "dormant": build.table_panel(
            "Provisioned, populated, nobody logs in", "usage_dormant_stacks", ds,
            columns=['Stack', 'Region', 'Users (active)', 'Users (daily)', 'Stickiness', 'Dashboards', 'Alert rules', 'Age (days)'],
            schema=usage_pillar.VIEW_SCHEMAS["usage_dormant_stacks"],
            description="The DRILL-DOWN behind the dormancy figures: the named stacks that have users but "
                        "zero daily activity, so somebody was onboarded and nobody came back. Distinct "
                        "from the zero-user test leftovers on the Estate dashboard, which cost nothing and "
                        "are a governance point rather than an adoption one."),
        "recency": build.table_panel(
            "Every user, by how recently they logged in", "usage_user_recency", ds,
            description="The DRILL-DOWN behind the last-seen buckets above - the individual users, so "
                        "`never` stops being a number and becomes a list somebody can act on. Contains "
                        "real names and email addresses BY DESIGN: this is an internal "
                        "platform-team view, Grafana already holds these identities, and an ownership "
                        "directory needs a name rather than a hash. Identifying fields live here and in "
                        "Loki only - never in a metric label."),

        # --- Ingested and never queried, live from `grafanacloud-usage` -------------------------------
        # IDEAS.md calls this the highest-value and hardest number in the platform. Measured honestly over
        # a 24h window it splits, and only the LOGS half survives - see the module-level comment on
        # LOGS_UNREAD_STACKS. There is deliberately no metrics equivalent here: 234 stacks ingest metrics
        # and exactly ONE went a day without a query. Do not add one back; it is a negative result.
        "n_logs_unread": build.stat_panel(
            "Stacks ingesting logs nobody reads (24h)", LOGS_UNREAD_STACKS, ds_uid=build.USAGE_UID,
            description="Ingesting log bytes AND zero log-query bytes across a full day. The `and` "
                        "requires active ingest, so an empty stack is "
                        "excluded - this is spend with no reader, not an idle tenant. Read it next to "
                        "log retention: paying to keep 13 months of logs nobody queries is the same "
                        "finding twice."),
        "n_logs_unread_bytes": build.stat_panel(
            "Log ingest with no reader (24h)", LOGS_UNREAD_BYTES, unit="Bps", decimals=2,
            ds_uid=build.USAGE_UID,
            description="Bytes per second being ingested by stacks with no log queries over the full "
                        "window. This is a rate, not a daily volume; multiply by 86,400 for bytes/day. "
                        "Use the ranked stack chart below to see whether one owner dominates the total."),
        "b_logs_unread": build.barchart_panel(
            "Unread log ingest by stack (24h)",
            build.usage_by_slug(f"topk(15, ({_LOG_IN} and {_LOG_UNREAD}))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="Bps",
            description="Bytes per second ingested by stacks that ran NO log queries at all over the "
                        "window, named via the stack_id->slug join and biggest first. Expect one bar to "
                        "dwarf the rest - that concentration is the finding, not a rendering fault, and "
                        "it means the remediation is a single conversation rather than an estate "
                        "programme. Unit is bytes/sec: multiply by 86,400 for a per-day figure."),
        # --- Workload composition (Tier 2), live from `grafanacloud-usage` ----------------------------
        # The only place the platform says what is actually being MONITORED rather than how much of it
        # there is. `*_info` series are one per object, so their sum is an object count.
        "n_pods": build.stat_panel(
            "Kubernetes pods monitored", PODS_MONITORED, ds_uid=build.USAGE_UID,
            description="Derived from `kube_pod_info`, which emits one series per pod. The most concrete 'what is in "
                        "there' figure the platform can produce, and it needs no per-stack credential."),
        "n_hosts": build.stat_panel(
            "Hosts monitored", HOSTS_MONITORED, ds_uid=build.USAGE_UID,
            description="Derived from `node_uname_info`, one series per host. Compare the live value with "
                        "pods to understand whether the monitored estate is container-first."),
        "n_intseries": build.stat_panel(
            "Series from Grafana Cloud Integrations", INTEGRATION_SERIES, ds_uid=build.USAGE_UID,
            description="Active series attributed to Grafana Cloud Integrations. This is an identifiable "
                        "source of the metrics footprint, not a count of integrations or stacks."),
        "n_intshare": build.stat_panel(
            "Integrations' share of all series", INTEGRATION_SHARE, unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="Integration-attributed active series divided by all active series. It is a "
                        "live ratio over a moving estate. Worth both readings: a real "
                        "adoption success, and also where a quarter of the metrics bill sits, which makes "
                        "it the first place to point Adaptive Metrics."),
        "b_asset_counts": build.barchart_series_panel(
            "Observed objects across the estate", OBSERVED_OBJECT_COUNTS,
            ds_uid=build.USAGE_UID, sort="desc",
            description="Affirmative inventory from counters already present on the write stack. Each "
                        "bar keeps its source metric's population intact; service, entity and target "
                        "counts are not added together into a synthetic total."),
        "b_observed_objects": build.barchart_panel(
            "App Observability services by stack", APP_SERVICES_BY_STACK,
            legend="{{slug}}", ds_uid=build.USAGE_UID, limit=15,
            description="Named with the datasource's stack_id-to-slug lookup. The join multiplies by "
                        "the one-series-per-stack info metric so the observed-service count is unchanged."),
        "b_integrations": build.barchart_panel(
            "Observed technologies from Grafana Integrations", INTEGRATIONS_BY_SERIES,
            legend="{{integration}}", ds_uid=build.USAGE_UID, limit=20,
            description="Active series grouped by Grafana Cloud's live `integration` label. There is no "
                        "maintained technology list: a newly observed integration appears on its own."),
        "b_integration_hosts": build.barchart_panel(
            "Integration host series by technology", INTEGRATIONS_BY_HOST_SERIES,
            legend="{{integration}}", ds_uid=build.USAGE_UID, limit=20,
            description="The host-shaped half of the same discovered integration catalogue, kept "
                        "separate from all active integration series so the two meanings stay legible."),
        "b_profiles": build.barchart_panel(
            "Profile ingestion by usage group (24h peak)", PROFILE_USAGE_GROUPS,
            legend="{{usage_group}}", ds_uid=build.USAGE_UID, unit="Bps", limit=15,
            description="Profile bytes received per second, grouped by the live usage_group label and "
                        "windowed over the dashboard's operational day. An empty chart is measured "
                        "absence in this datasource, not a configured list with no matches."),
        "b_app_hosts": build.barchart_series_panel(
            "App Observability hosts by reporting metric", APP_HOST_COUNTS,
            ds_uid=build.USAGE_UID, sort="desc",
            description="The three reporting generations stay separate because their populations may "
                        "overlap. Adding them would manufacture a host total the datasource does not "
                        "declare."),
        "n_infra_host_hours": build.stat_panel(
            "Infrastructure host-hours observed",
            "sum(grafanacloud_org_infra_o11y_billable_host_hours)",
            ds_uid=build.USAGE_UID, unit="h",
            description="Billing-side host-hours attributed to Infrastructure Observability in the "
                        "datasource's current accounting period."),
        "n_infra_container_hours": build.stat_panel(
            "Infrastructure container-hours observed",
            "sum(grafanacloud_org_infra_o11y_billable_container_hours)",
            ds_uid=build.USAGE_UID, unit="h",
            description="Billing-side container-hours attributed to Infrastructure Observability in "
                        "the datasource's current accounting period."),
        "n_db_host_hours": build.stat_panel(
            "Database host-hours observed", "sum(grafanacloud_org_db_o11y_billable_host_hours)",
            ds_uid=build.USAGE_UID, unit="h",
            description="Billing-side database host-hours observed in the datasource's current "
                        "accounting period."),
        "n_fe_sessions": build.stat_panel(
            "Frontend sessions observed", "sum(grafanacloud_org_fe_o11y_billable_sessions)",
            ds_uid=build.USAGE_UID,
            description="Billing-side frontend sessions observed in the datasource's current "
                        "accounting period."),
        "n_fe_session_rate": build.stat_panel(
            "Frontend session rate (24h peak)", FE_SESSION_RATE,
            ds_uid=build.USAGE_UID, unit="ops",
            description="The time-aligned estate session rate at its highest point in the operational "
                        "window. The aggregate is windowed before comparison; it is not an instantaneous "
                        "sample or a sum of unrelated per-stack peaks."),
        "t_workload": build.timeseries_panel(
            "How many stacks monitor what",
            [(K8S_STACKS, "Kubernetes"), (HOST_STACKS, "hosts"),
             (INTEGRATION_STACKS, "Grafana Cloud Integrations"),
             (METRICS_STACKS, "-- stacks ingesting metrics at all")],
            ds_uid=build.USAGE_UID,
            description="Each line counts stacks over the same 24-hour window; the metrics-ingesting "
                        "line is the denominator for the other three. Deliberately NOT on this dashboard: "
                        "`..._active_unidentifiable_targets_series`. "
                        "It was measured separately and rejected as negligible estate noise, not a "
                        "customer finding; see IDEAS.md for the evidence."),
        "n_assistant": build.stat_panel(
            "Grafana Assistant users", "sum(grafanacloud_org_assistant_users)",
            ds_uid=build.USAGE_UID,
            description="Org-wide Assistant users. Per `reference_ai_token_billing_metrics` these are "
                        "per-user, not pooled; compare with the live active-user population when quoting "
                        "an adoption share."),
        "n_aitokens": build.stat_panel(
            "AI tokens this billing period", "sum(grafanacloud_ai_tokens_total_tokens)",
            ds_uid=build.USAGE_UID,
            description="AI tokens consumed across the org in the CURRENT billing period. This "
                        "aggregate resets monthly; it is not a lifetime counter. The dedicated AI "
                        "dashboard separates this period total from the per-identity lifetime metric."),
        "t_logs_unread": build.timeseries_panel(
            "Log ingest: total vs unread",
            [(LOGS_IN_BYTES, "ingested estate-wide"),
             (LOGS_UNREAD_BYTES, "ingested with no reader")],
            unit="Bps", ds_uid=build.USAGE_UID,
            description="The gap is the point. If the lower line drops to zero somebody started querying "
                        "those logs, or stopped shipping them - both are wins, and the per-stack chart "
                        "above says which."),
    }
    tabs = [
        build.tab("Overview", ["n_stick", "n_types", "t_stick", "summary"]),
        build.tab("Adoption", ["t_signals", "plugins"]),
        build.tab("Engagement", ["b_recency", "dormant", "recency", "usage"]),
        build.tab("Protocol adoption", ["n_otlp", "n_otlp_floor", "t_otlp"]),
        build.tab("Unread telemetry", ["n_logs_unread", "n_logs_unread_bytes",
                                       "b_logs_unread", "t_logs_unread"]),
        build.rows_tab("Workload", [
            build.row("Headline", ["n_pods", "n_hosts", "n_intseries", "n_intshare"],
                      max_columns=4, row_height="short"),
            build.row("Observed objects", ["b_asset_counts", "b_observed_objects"], max_columns=2),
            build.row("Technologies and profiles",
                      ["b_integrations", "b_integration_hosts", "b_profiles"], max_columns=3),
            build.row("App Observability hosts", ["b_app_hosts"], max_columns=1),
            build.row("Billing-side observed activity",
                      ["n_infra_host_hours", "n_infra_container_hours", "n_db_host_hours",
                       "n_fe_sessions", "n_fe_session_rate"], max_columns=5, row_height="short"),
            build.row("Estate reach", ["t_workload"], max_columns=1),
            build.row("Adjacent product use", ["n_assistant", "n_aitokens"],
                      max_columns=2, row_height="short"),
        ]),
    ]
    return "gcinsight-usage", "Grafana Cloud Org Insights - Consumer behaviour", \
        ("Pillar C: what stack consumers actually do. Per-dashboard view analytics now lives on the "
         "Dashboard usage dashboard."), el, tabs


def d_maturity(ds: str):
    el = {
        "n_median": build.stat_panel(
            "Median score", 'gcinsight_maturity_percentile{kind="median",version="1"}', decimals=1,
            description="The MIDDLE stack's overall maturity score out of 100 - half the scored estate is "
                        "below this. Median rather than mean on purpose: a handful of very mature or very "
                        "empty stacks would drag an average and misrepresent the typical stack. Only "
                        "SCORED stacks count; dormant and test-leftover stacks are excluded and the Not "
                        "scored tab says why."),
        "n_p90": build.stat_panel(
            "p90 score", 'gcinsight_maturity_percentile{kind="p90",version="1"}', decimals=1,
            description="The score 90% of scored stacks fall below - what GOOD looks like inside the organisation's "
                        "own estate rather than against an industry benchmark. The gap between this and "
                        "the median is the realistic improvement available: it is already being achieved "
                        "by their own teams, so it is an argument that needs no external evidence."),
        "n_worst": build.stat_panel(
            "Worst ranked", 'gcinsight_maturity_percentile{kind="worst",version="1"}', decimals=1,
            description="The lowest score among stacks that COULD be scored - so it is a real stack with "
                        "real users, not an empty one. Genuinely dormant and test stacks are excluded "
                        "rather than filling this with noise; the Leaderboard tab names it."),
        "n_ranked": build.stat_panel(
            "Stacks ranked", 'count(gcinsight_maturity_score{stack=~"$stack",version="1"})',
            description="How many stacks got a score at all - **the denominator for every other number on "
                        "this dashboard, and it is not the estate total.** A stack is unscored when it is "
                        "paused, has too few users, or the weekly data-plane tier could not reach it; the "
                        "Not scored tab breaks it down by reason. If this drops sharply the scores above "
                        "describe a different population, not an improving estate."),
        "t_pct": build.timeseries_panel(
            "Score distribution over time",
            [('gcinsight_maturity_percentile{kind="median",version="1"}', "median"),
             ('gcinsight_maturity_percentile{kind="p90",version="1"}', "p90"),
             ('gcinsight_maturity_percentile{kind="worst",version="1"}', "worst")],
            description="Is the estate getting better? This is the line to watch quarter on quarter."),
        "t_tiers": build.timeseries_panel(
            "Stacks per tier", [('gcinsight_maturity_stacks_by_tier{version="1"}', "{{kind}}")], stacked=True,
            description="leading >=75, solid >=50, lagging >=25, dormant below."),
        "b_top": build.barchart_panel(
            "Top 15 by score", 'topk(15, gcinsight_maturity_score{stack=~"$stack",version="1"})',
            legend="{{stack}}",
            description="The most mature stacks - the internal reference implementations, and the most "
                        "useful thing to point another team at. A small stack can score well on breadth "
                        "with very little in it, so check a leader's size on the Estate dashboard before "
                        "holding it up as an example."),
        "b_bottom": build.barchart_panel("Bottom 15 by score",
                                          'bottomk(15, gcinsight_maturity_score{stack=~"$stack",version="1"})',
                                          legend="{{stack}}", sort="asc",
                                          # Amber below 25 (the `lagging` tier boundary), red below 10, so
                                          # the bottom chart cannot be mistaken for the top chart at a
                                          # glance - they rendered in identical green.
                                          thresholds=[(None, "orange"), (10, "red"), (25, "yellow")],
                                          description="The lowest-scoring stacks, WORST FIRST, and where enablement effort pays back most - each is a "
                        "real stack with real users, since dormant and test-leftover stacks are excluded "
                        "from scoring entirely. Cross-read with the Estate dashboard for size: a low score "
                        "on a stack carrying 3M series is a different conversation from a low score on one "
                        "carrying 500."),
        # PLAN 9.1. Before this there was NO trend for "which dimension is the estate weakest on": the
        # per-stack view is 271 x 9 = 2,439 rows, which as series would exceed the whole budget. Sorted
        # ascending so the weakest dimension is the first bar a reader's eye lands on.
        "b_dims": build.barchart_panel(
            "Estate mean by dimension - weakest first",
            # `sort()` is applied by the DATASOURCE and then discarded: the `reduce` transformation
            # rebuilds the frame in series order, so the PromQL sort never reached the chart and the bars
            # rendered alphabetically. `sort="asc"` on the panel is what actually orders them.
            'gcinsight_maturity_dimension_mean{version="1"}', sort="asc", legend="{{dimension}}",
            description="The mean is over the stacks that SCORED each dimension, excluding the four "
                        "unscored reasons - so a dormant estate cannot drag it down and each dimension "
                        "carries its own denominator."),
        "t_dims": build.timeseries_panel(
            "Dimension means over time",
            [('gcinsight_maturity_dimension_mean{version="1"}', "{{dimension}}")],
            description="Which dimension is enablement actually moving? A flat line here next to a "
                        "rising composite means the score improved by stacks dropping out, not improving."),
        "b_unscored": build.barchart_panel(
            "Not scored, and why", 'gcinsight_maturity_unscored{version="1"}', legend="{{reason}}",
            description="Why each excluded stack was excluded, biggest reason first. An unexplained "
                        "'unscored' would read as a collector bug, so the reason is a metric rather than "
                        "a footnote. The table beneath names the individual stacks behind each reason - "
                        "the aggregate alone cannot be actioned."),
        # The named rows behind `b_unscored`. A count of stacks excluded for a reason cannot be acted
        # on; the list of which stacks, and how much is in each, can. Filterable by reason, and it
        # honours the Stack selector like every other per-stack table.
        "unscored_detail": build.table_panel(
            "Which stacks were not scored, and why", "maturity", ds,
            columns=["Stack", "Unscored reason", "Users (active)", "Active series",
                     "Dimensions scored", "Score"],
            description="Every stack the rubric excluded, with the reason beside it - the named rows "
                        "behind the reason counts above. Filter the `Unscored reason` column to work one "
                        "reason at a time. A scored stack shows a blank reason and a Score, so the two "
                        "populations are distinguishable in one table. `Users (active)` and `Active "
                        "series` are here because they decide whether an exclusion matters: a stack "
                        "excluded for too few users while carrying millions of series is worth a "
                        "conversation, one excluded while carrying nothing is correctly ignored."),
        "owners": build.table_panel(
            "Who owns each stack", "maturity_owners", ds,
            description="The best available ownership directory, inferred from each stack's Grafana "
                        "Admin users after Grafana staff accounts are excluded. An admin is a remediation "
                        "contact, not proof of business ownership, so treat each row as a lead rather than "
                        "an authority. Use the Stack selector to narrow the directory before contacting "
                        "anyone."),
        "summary": build.table_panel(
            "Maturity summary", "maturity_summary", ds,
            description="The score's inputs and weights, so a stack owner can see exactly why they scored "
                        "what they did. The rubric is versioned - the metric carries a `version` label, so "
                        "changing the weights starts a new series rather than silently rewriting history."),
        "rubric": build.table_panel(
            "The rubric - published weights", "maturity_rubric", ds,
            description="A leaderboard nobody can argue with is worse than one they can."),
        "board": build.table_panel(
            "Leaderboard", "maturity", ds,
            description="Unscored stacks carry a reason. Ratio dimensions are noise below 3 users."),
        "dims": build.table_panel(
            "Every dimension's contribution, per stack", "maturity_dimensions", ds,
            description="Recompute any score by hand from these rows."),
    }
    tabs = [
        build.tab("Overview", ["n_median", "n_p90", "n_worst", "n_ranked", "t_pct", "t_tiers"]),
        build.tab("By dimension", ["b_dims", "t_dims"]),
        build.tab("Leaderboard", ["b_top", "b_bottom", "board"]),
        build.tab("How it is scored", ["rubric", "summary"]),
        build.tab("Who owns what", ["owners"]),
        build.tab("Explain a score", ["dims"]),
        build.tab("Not scored", ["b_unscored", "unscored_detail"]),
    ]
    return "gcinsight-maturity", "Grafana Cloud Org Insights - Maturity", \
        "Pillar D: nine-dimension rubric, composite score and leaderboard.", el, tabs


def _published_views_exist(*names: str) -> bool:
    """Whether every view has reached S3, without weakening the normal missing-view build gate."""
    try:
        for name in names:
            build.read_view(name)
    except FileNotFoundError:
        return False
    return True


def d_risk(ds: str):
    fleet_detail_views_live = _published_views_exist(
        "risk_fleet_attributes", "risk_fleet_pipelines",
    )
    public_dashboard_view_live = _published_views_exist("risk_public_dashboards")
    alert_routing_views_live = _published_views_exist(
        "risk_alert_routing", "risk_alert_routing_findings",
    )
    org_members_view_live = _published_views_exist("risk_org_members")
    el = {
        "n_org_admins": build.stat_panel(
            "Organisation members with Admin role",
            "gcinsight_risk_org_members_admins",
            description="Current count from the complete Grafana.com organisation membership response. "
                        "If the org-members input is unavailable this panel is absent rather than zero. "
                        "Use the named table to review ownership rather than inferring intent from role."),
        "n_org_viewers": build.stat_panel(
            "Organisation members with Viewer role",
            "gcinsight_risk_org_members_viewers",
            description="Current Viewer-role count from the same org-level response as the Admin count. "
                        "The named membership table is the review surface when role ownership needs "
                        "checking."),
        "b_org_staff_access": build.barchart_panel(
            "Organisation members by staff-access state",
            "sum by(status)(gcinsight_risk_org_members_staff_access)",
            legend="{{status}}", sort="desc",
            description="Counts active, expired, none and unknown staff-access states from one org-level "
                        "response. Unknown remains its own state rather than becoming no access. The named "
                        "table carries expiry, reason and ticket detail for review."),
        "n_admin": build.stat_panel(
            "Stacks over 50% admins", "gcinsight_risk_admin_heavy_stacks",
            description="Stacks where more than half the active users hold Admin. Read the named table "
                        "with delete protection and active series: the decision is which materially used, "
                        "unprotected stacks have an unusually broad destructive role, not whether one "
                        "dated estate-wide median is high."),
        "n_noprot": build.stat_panel(
            "Stacks with no delete protection", "gcinsight_risk_stacks_without_delete_protection",
            description="Stacks that can be deleted without a confirmation guard. This is the "
                        "governance count; the table on this tab is the ACTIONABLE subset, filtered to "
                        "stacks carrying 50,000+ series, because an empty unprotected stack is a deletion "
                        "candidate rather than a deletion risk."),
        "n_fmdead": build.stat_panel(
            "FM configured, no active collectors", "gcinsight_risk_stacks_pipelines_no_collectors",
            description="Stacks with Fleet Management pipelines defined and no active collectors. Old "
                        "inactive registrations can still exist, so this measures whether configuration "
                        "currently reaches a live fleet rather than whether a collector connected at some "
                        "point in the past."),
        "n_coll": build.stat_panel(
            "Collector registrations", "gcinsight_risk_collectors_total",
            description="Every collector registration Fleet Management returns across the estate. "
                        "**MOST OF THIS CAN BE DEAD, so read the two panels beside it before quoting "
                        "this one.** A collector id embeds its hostname, so on ephemeral compute every "
                        "pod reschedule creates a new registration and the old one is marked inactive "
                        "until Fleet Management prunes it. Kept unchanged so the trend line stays "
                        "continuous rather than stepping when the split was introduced."),
        "n_coll_active": build.stat_panel(
            "Collectors ACTIVE", "gcinsight_risk_collectors_active",
            description="Registrations NOT marked inactive: the fleet that actually exists. **This is "
                        "the number to quote.** Absent rather than zero if the collector scan has not "
                        "run since the split was introduced, because a zero here would say the estate "
                        "runs no collectors at all."),
        "n_coll_inactive": build.stat_panel(
            "Collectors inactive", "gcinsight_risk_collectors_inactive",
            description="Registrations for collectors that are gone. Compare the share and per-stack "
                        "table before treating this as a fault: ephemeral compute can legitimately "
                        "re-register hosts, while a falling active count is a different signal."),
        "n_coll_inactive_share": build.stat_panel(
            "Collector registrations inactive",
            "gcinsight_risk_collectors_inactive / clamp_min("
            "gcinsight_risk_collectors_active + gcinsight_risk_collectors_inactive, 1)",
            unit="percentunit", decimals=1,
            description="Inactive registrations divided by the active-plus-inactive population from the "
                        "same Fleet sweep. This makes churn comparable as the estate grows; use the named "
                        "table to distinguish concentrated ephemeral-host churn from a broad fleet issue."),
        "n_coll_unconfigured": build.stat_panel(
            "Collectors no enabled pipeline targets",
            "gcinsight_risk_collectors_unconfigured",
            description="Alive, registered, and matched by no ENABLED pipeline, so receiving no "
                        "configuration at all. **DERIVED, not reported** - Fleet Management has no API "
                        "for pipeline-to-collector targeting, so this platform evaluates the matchers "
                        "itself using Prometheus label semantics. It doubles as the evaluator's sanity "
                        "check: most stacks carry a catch-all pipeline, so a large number here is more "
                        "likely a parsing problem than a fleet problem. Read it with the unparsed "
                        "matcher count."),
        "n_pipe_total": build.stat_panel(
            "Pipelines configured", "gcinsight_risk_pipelines_total",
            description="Fleet Management pipelines defined across the estate, enabled or not. The "
                        "denominator for the two panels beside it: on its own it says configuration "
                        "exists, not that any of it is reaching a collector."),
        "n_pipe_enabled": build.stat_panel(
            "Pipelines enabled", "gcinsight_risk_pipelines_enabled",
            description="Of the pipelines configured, how many are switched ON. A disabled pipeline "
                        "still describes a target set and configures nothing, so counting the two "
                        "together reports a switched-off pipeline as covering collectors it never "
                        "reaches. The gap to the total is the deliberately-off set."),
        "n_pipe_generated": build.stat_panel(
            "Pipelines Grafana generated", "gcinsight_risk_pipelines_generated",
            description="`SOURCE_TYPE_GRAFANA`: created by onboarding rather than written by somebody. "
                        "The gap to the total is hand-authored configuration, which is the half that "
                        "has an owner worth finding."),
        "n_matchers_unparsed": build.stat_panel(
            "Pipeline matchers not understood",
            "gcinsight_risk_fleet_matchers_unparsed",
            description="Matchers this platform cannot parse. **Any value above zero means at least one "
                        "'collectors targeted' figure is UNKNOWN rather than small**, and the affected "
                        "pipeline reports no count rather than a wrong one. It should be zero; if it is "
                        "not, Fleet Management has grown a matcher shape the evaluator needs teaching."),
        "t_collectors": build.timeseries_panel(
            "Collector registrations: active vs inactive",
            [("gcinsight_risk_collectors_active", "active"),
             ("gcinsight_risk_collectors_inactive", "inactive")],
            stacked=True,
            description="The two lines together are the raw registration count. Watch the RATIO rather "
                        "than either line: inactive rising while active is flat is ordinary churn on "
                        "ephemeral compute, whereas active falling is a fleet going away."),
        "t_coll_top": build.timeseries_panel(
            "Top 10 stacks by ACTIVE collectors",
            [("topk(10, gcinsight_stack_collectors_active)", "{{stack}}")],
            description="Where the real fleet is. Deliberately the active count, not the registration "
                        "count: ranked by registrations, a stack churning pods dominates the chart "
                        "while running a modest fleet."),
        "t_admin": build.timeseries_panel(
            "Admin-heavy stacks over time", [("gcinsight_risk_admin_heavy_stacks", "stacks")],
            description="Direction of travel for stacks where more than half of active users are Admin. "
                        "The named table provides the current population and load behind the line."),
        # This tab rendered as an empty "No data" panel, and the cause was NOT missing data - the
        # metric carries 506 custom and 4,458 extsvc service accounts. It was a bare selector on a
        # metric derived from the DAILY per-stack sweep, read on a dashboard whose default window is 6
        # hours: at most one sample in range, usually none. Every expression here is now windowed, and
        # since T1 hydrates the per-stack detail it recomputes these hourly anyway.
        "n_sa_custom": build.stat_panel(
            "Custom service accounts", 'max_over_time(gcinsight_risk_service_accounts_total{kind="custom"}[24h])',
            description="Service accounts somebody at the organisation created, across the estate - the ones worth "
                        "governing. Excludes the `extsvc-*` accounts Grafana provisions for its own "
                        "plugins; the split keeps customer-managed identities visible even when the "
                        "Grafana-managed population is larger."),
        "n_sa_extsvc": build.stat_panel(
            "Grafana-managed service accounts", 'max_over_time(gcinsight_risk_service_accounts_total{kind="extsvc"}[24h])',
            description="`extsvc-*` accounts Grafana creates for its own plugins and apps. Shown only so "
                        "the custom count beside it is credible - these are not a governance concern and "
                        "nobody should act on this number."),
        "t_sa": build.timeseries_panel(
            "Service accounts by kind",
            [('max_over_time(gcinsight_risk_service_accounts_total[24h])', "{{kind}}")],
            stacked=True,
            description="Windowed over 24h, NOT a bare selector: this comes from the daily per-stack "
                        "sweep, and on the default 6-hour dashboard window a bare selector shows nothing "
                        "at all - which reads as 'no service accounts' rather than 'no sample in range'. "
                        "`extsvc-*` are Grafana's own and dominate the total; the split matters more than "
                        "the sum."),
        "t_sa_scope": build.text_panel(
            "How service-account detail is collected",
            "The named inventory below comes from each stack's **stack-local read-only** reader, not from "
            "the org access-policy proxy. The stack-local `serviceaccounts:read` action can list account "
            "names, roles, disabled state and token counts without granting create or delete access.\n\n"
            "The table is intentionally an inventory, not a finding count. Use the Stack selector to "
            "narrow it, and start with rows carrying a `Flag`. Token secret values are never collected. "
            "A blank table is credible only when the per-stack-detail age and scan coverage are current."),
        "sa_inventory": build.table_panel(
            "Service-account inventory", "risk_service_accounts", ds,
            schema=risk_pillar.VIEW_SCHEMAS["risk_service_accounts"],
            columns=["Stack", "Service account", "Kind", "Role", "Assigned roles", "Role read",
                     "Tokens", "Expired tokens", "Non-expiring tokens", "Never-used tokens",
                     "Stale live tokens (90d)", "Nearest token expiry", "Token read",
                     "Token hygiene", "Disabled", "Flag"],
            description="The named accounts behind the two totals, filterable by stack. `extsvc` rows are "
                        "Grafana-managed; custom rows are customer-managed. Permanent, never-used and "
                        "stale live credentials are shown only where token metadata was completely read; "
                        "unknown remains blank rather than becoming a clean zero. `Flag` is a review hint, "
                        "not an automatic remediation instruction. An empty result means no readable rows "
                        "only when service-account freshness and coverage are current."),
        # Public dashboards are now ENUMERATED, not inferred (PLAN 18.17). The old description here said
        # this pillar's credential "gets 401 on every stack Grafana API path" - true of the org access
        # policy, and false since the per-stack reader role gained `dashboards.public:read`.
        "n_public": build.stat_panel(
            "Public dashboards that EXIST",
            "gcinsight_risk_public_dashboards_enumerated",
            description="Enumerated per stack through each stack's own API, so it counts public "
                        "dashboards that exist whether or not "
                        "anybody has ever opened one. Read it with the coverage panel beside it: the "
                        "endpoint answers 200 with a permission-filtered list rather than 403, so a "
                        "count taken without the role would read zero. Compare the result with your "
                        "organisation's public-sharing policy. The named list is in the expanded "
                        "`Which dashboards` row on this tab."),
        "n_public_enabled": build.stat_panel(
            "...of which are live now",
            "gcinsight_risk_public_dashboards_enabled",
            description="The subset currently serving. A DISABLED public dashboard remains configured "
                        "and one click from live; this panel is what is exposed at this moment. If these two "
                        "disagree, the difference is the set somebody has already turned off but not "
                        "removed."),
        "n_public_stacks": build.stat_panel(
            "Stacks carrying at least one",
            "gcinsight_risk_public_dashboards_stacks",
            description="The number of owner conversations, which is a better measure of the work than "
                        "the dashboard count. Use the named inventory once published to see whether the "
                        "inventory is concentrated rather than preserving a dated share here."),
        "n_public_measured": build.stat_panel(
            "Stacks measured for public dashboards",
            "gcinsight_risk_public_dashboards_measured",
            description="The denominator, and it is load-bearing rather than decorative. Stacks that "
                        "could not be read contribute to NEITHER side of the count, so a drop here "
                        "shrinks the breach total without anything improving on the estate. If this is "
                        "well below the estate size, treat the count as a floor."),
        "n_public_events": build.stat_panel(
            "Public dashboards anyone has OPENED",
            'sum(gcinsight_dashboards_estate_public{version="2"})',
            description="Pillar J's independent count, derived from usage-insights EVENTS rather than "
                        "from enumeration - so it sees only the ones somebody has actually opened. "
                        "**The two answer different questions and a disagreement is expected:** "
                        "enumeration is the inventory question and events are the exposure question. It "
                        "also reads a different input on a different cadence, so they will not agree to "
                        "the minute."),
        "n_routing_available": build.stat_panel(
            "Alert-routing input available",
            'max(gcinsight_input_available{input="alert_routing"})',
            description="One means at least one current scan carries the alert-routing input. Read this "
                        "with the alert-routing input age in the dashboard header and the measured-stack "
                        "denominator below; availability alone does not prove estate coverage."),
        "n_routing_measured": build.stat_panel(
            "Stacks measured for alert routing",
            "gcinsight_risk_alert_routing_stacks_measured",
            description="The denominator for every routing count on this tab. A stack contributes only "
                        "when both its alert-rule and contact-point provisioning endpoints answered; the "
                        "APIs return bare arrays with no server total, so response completeness is not "
                        "claimed."),
        "n_routing_rules": build.stat_panel(
            "Alert rules in measured stacks",
            "gcinsight_risk_alert_rules_total",
            description="All alert rules returned by the measured stacks. This is the population behind "
                        "the routing findings, not the org's independent inventory total; compare coverage "
                        "before using it as an estate count."),
        "n_routing_inherited": build.stat_panel(
            "Active rules inheriting notification policy",
            "gcinsight_risk_alert_rules_active_inherited",
            description="Active rules with no direct receiver, so Grafana routes them through the stack's "
                        "notification policy. Inheritance is not automatically broken, but it is the "
                        "blast-radius seam: a policy change can reroute many rules at once."),
        "n_routing_missing": build.stat_panel(
            "Active rules naming a missing receiver",
            "gcinsight_risk_alert_rules_active_missing_receiver",
            description="Active rules whose explicit receiver is absent from the provisioning contact-point "
                        "list. The built-in default receiver is excluded from this count because its absence "
                        "from that API is ambiguous rather than proof of a broken route."),
        "n_routing_builtin": build.stat_panel(
            "Rules with unverified built-in receiver",
            "gcinsight_risk_alert_rules_unverified_builtin",
            description="Rules naming `grafana-default-email` when that built-in does not appear in the "
                        "provisioning response. These are UNVERIFIED, not called broken; confirm delivery "
                        "before changing the rule or contact points."),
        "routing_scope": build.text_panel(
            "How to read alert routing",
            "A direct receiver can be checked against the stack's contact-point list. An inherited rule "
            "has no direct receiver and follows notification policy instead; that is a governance surface, "
            "not proof of failure. The provisioning APIs expose arrays without a total-count envelope, so "
            "the measured-stack count and input age are part of every conclusion."),
        "summary": build.table_panel(
            "Risk summary", "risk_summary", ds,
            description="The public-dashboard row carries a count only where the enumeration actually "
                        "ran, and words rather than a zero otherwise - this pillar cannot tell an "
                        "unreadable stack from a compliant one, and on a zero-tolerance policy that "
                        "difference is the whole check."),
        "admins": build.table_panel(
            "Admin sprawl", "risk_admin_sprawl", ds,
            columns=['Stack', 'Region', 'Users (active)', 'Admins', 'Admin share %', 'Delete protection'],
            description="Sorted by active series: biggest stacks first, where it matters most."),
        "fleet": build.table_panel(
            "Fleet Management configured and dead", "risk_fleet_dead", ds,
            # `Collectors` is every REGISTRATION FM returns and most of it estate-wide is dead, so the
            # active/inactive split sits beside it rather than replacing it - the raw column stays because
            # it is what the FM UI shows, and a reader comparing the two is the point.
            columns=['Stack', 'Region', 'Collectors', 'Collectors (active)', 'Collectors (inactive)',
                     'Inactive %', 'Pipelines', 'Pipelines (enabled)', 'FM dead', 'Alert rules'],
            description="The named stacks behind the FM counter: pipelines defined, no LIVE collectors "
                        "connected. Start with the ones that also carry real series - an empty stack with "
                        "a dead pipeline costs nothing and misleads nobody. `Collectors` counts every "
                        "registration including dead ones; `Collectors (active)` is the number to act on, "
                        "and a high `Inactive %` usually means ephemeral compute re-registering rather "
                        "than a broken fleet. `Pipelines (enabled)` excludes switched-off pipelines, "
                        "which still describe a target set but configure nothing."),
        "policies": build.table_panel(
            "Access policies, org-wide-write first", "risk_access_policies", ds,
            description="A REPORT, not a remediation list. Policies are region-scoped, so the region "
                        "column is how you find one again. Confirm the owner before touching any."),
        "t_noprot": build.timeseries_panel(
            "Stacks without delete protection",
            [("gcinsight_risk_stacks_without_delete_protection", "unprotected")],
            description="This line should fall as protection is enabled. The detail table filters to "
                        "material stacks, because an empty unprotected stack is a deletion candidate "
                        "rather than a deletion risk."),
        "noprot": build.table_panel(
            "Production load with no delete protection", "risk_delete_protection", ds,
            columns=['Stack', 'Region', 'Active series', 'Users (active)', 'Alert rules', 'Delete protection'],
            description="Unprotected AND 50,000+ active series, largest first. Cross-read with Admin "
                        "sprawl: a stack that is admin-heavy AND unprotected can be deleted by any of "
                        "those admins, with nothing to stop them. Empty stacks are excluded - those are "
                        "deletion candidates, not deletion risks."),
        "n_plugindrift": build.stat_panel(
            "Stacks with unusual datasource plugins",
            'max_over_time(gcinsight_risk_plugin_drift_stacks[24h])',
            description="The counter the table below drills into. Windowed over 24h, NOT a bare "
                        "selector: this comes from the daily per-stack sweep and the default dashboard "
                        "window is 6 hours, so unwindowed it renders empty - which reads as zero drift "
                        "rather than no sample in range."),
        "plugindrift": build.table_panel(
            "Stacks with unusual datasource plugins", "risk_plugin_drift", ds,
            description="The DRILL-DOWN behind the plugin-drift counter: the named stacks running "
                        "datasource types the rest of the estate does not. Read as a question rather than "
                        "a fault - a one-off plugin may be entirely legitimate, but it is unsupported "
                        "surface nobody else is watching, and competitor datasources show up here too."),
        "risk": build.table_panel(
            "Per-stack governance", "risk", ds,
            description="Every stack's governance posture in one row - admin share, delete protection, "
                        "alert rules, series and collection state. A blank cell means NOT MEASURABLE, never "
                        "zero; use the input-age panels to distinguish a missing read from a measured zero."),

        # --- Data loss + alerting health, read LIVE from `grafanacloud-usage` --------------------------
        # Everything below this line reads the stack's own provisioned billing datasource directly: no
        # collector, no service account, no series of ours. Consequences that apply to every one of them:
        # * LIVE, not on our hourly write cadence, so these panels are fresher than the rest of the page
        # and will disagree with an S3 view captured an hour ago. That is correct, not a bug.
        # * `$stack` does NOT apply - the datasource has no slug label. Names come from the PromQL join
        # in `build.usage_by_slug`, which is why the named panels are bar charts rather than tables.
        # * Aggregate `sum by(stack_id)` before counting, or you count signal instances not stacks.
        # Evidence for every figure quoted in these descriptions: evidence/usage-datasource-signals.json,
        # regenerated by `python3 bin/probe_usage_signals.py`.
        "n_discard": build.stat_panel(
            "Stacks that lost metric samples (24h)", DISCARD_STACKS, ds_uid=build.USAGE_UID,
            description="Samples rejected at ingest at any point in the last 24h for a reason OTHER than "
                        "a deliberate drop rule, so these stacks believe they are monitored and are not. "
                        "`requested-by-configuration` is excluded on purpose - that is Adaptive Metrics "
                        "working correctly, and counting it would "
                        "report a stack as broken for adopting the lever the cost dashboard recommends. "
                        "WINDOWED DELIBERATELY: the instantaneous "
                        "form of this question read 20, because a discard rate is momentary and 'is it "
                        "happening right now' is not the question."),
        "n_logdrop": build.stat_panel(
            "Stacks that lost log bytes (24h)", LOGDROP_STACKS, ds_uid=build.USAGE_UID,
            description="Same failure mode as metric discards and the "
                        "same invisibility - nothing in the stack's own UI says it is happening. The "
                        "instantaneous form read 7, which is why this is windowed."),
        "b_reason": build.barchart_panel(
            "Stacks per discard reason (24h)",
            # `count by(reason)` over the raw selector counts SERIES, and this metric carries
            # reason + id + stack_id - so a stack with two metrics instances failing the same way was
            # counted twice. Collapsing to (reason, stack_id) first makes each stack count once.
            f"count by(reason) (max by(reason, stack_id) "
            f"(max_over_time(grafanacloud_instance_samples_discarded_per_second"
            f"{DEFECT_ONLY}[{WINDOW}])) > 0)",
            legend="{{reason}}", ds_uid=build.USAGE_UID,
            description="The taxonomy is what makes this actionable, because the reasons have different "
                        "owners. SENDER DEFECTS (fix the collector or the app): sample_duplicate_timestamp, "
                        "new-value-for-timestamp, sample_timestamp_too_old, too_far_in_future, "
                        "otlp_parse_error, label_invalid. LIMIT BREACHES (fix the config): "
                        "aggregator-too-many-*-series. `requested-by-configuration` is excluded because "
                        "it is Adaptive Metrics deliberately dropping configured data, not data loss."),
        "b_discard": build.barchart_panel(
            "Worst stacks by samples discarded/sec (24h peak)",
            build.usage_by_slug(
                f"topk(15, sum by(stack_id)(max_over_time("
                f"grafanacloud_instance_samples_discarded_per_second{DEFECT_ONLY}[{WINDOW}])))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="ops",
            description="Named via the stack_id->slug join. Peak rate over the window, so a stack that "
                        "fixed itself drops off within a day rather than carrying its history forever, "
                        "and one that failed at 03:00 is still visible at 09:00."),
        "t_dataloss": build.timeseries_panel(
            "Data loss over time",
            [(DISCARD_STACKS, "stacks discarding metrics"),
             (LOGDROP_STACKS, "stacks discarding logs"),
             (TRACE_DISCARD_STACKS, "stacks discarding trace spans"),
             (METADATA_DISCARD_STACKS, "stacks discarding metric metadata")],
            ds_uid=build.USAGE_UID,
            description="Both lines should be zero. Neither has been. Each point is a 24h look-back, so "
                        "the lines are smooth by construction and a single bad hour stays visible for a "
                        "day - that is the intent, not lag."),
        "n_traceincomplete": build.stat_panel(
            "Stacks flushing incomplete traces (24h)", TRACE_INCOMPLETE_STACKS, ds_uid=build.USAGE_UID,
            description="Dropped below 90% of traces arriving complete at some point in the last 24h. "
                        "Only stacks reporting this trace-quality metric are in the denominator; absence "
                        "is unmeasured, not clean. A trace "
                        "that arrives in pieces cannot be read, so this is instrumentation that is "
                        "running and useless. `min_over_time` because a momentary read caught only 4: "
                        "trace completeness dips, and a dip is the defect. "
                        "UNIT TRAP: despite the metric name this series is a RATIO 0-1, so the threshold "
                        "is 0.90 and NOT 90. Thresholding at 90 matches every stack that reports and "
                        "invents a 26-stack outage - that error was made and caught here on 2026-08-18."),
        "n_trace_discard": build.stat_panel(
            "Stacks discarding trace spans (24h)", TRACE_DISCARD_STACKS,
            ds_uid=build.USAGE_UID,
            description="Stacks where the hosted traces backend discarded spans at any point in the "
                        "window. This is direct data loss, distinct from incomplete traces: the latter "
                        "arrived in pieces, while these spans were refused after arrival. Windowed because "
                        "the rate is momentary; an instant zero would erase an intermittent loss event."),
        "n_metadata_discard": build.stat_panel(
            "Stacks discarding metric metadata (24h)", METADATA_DISCARD_STACKS,
            ds_uid=build.USAGE_UID,
            description="Stacks whose hosted Metrics tenant discarded metadata. Samples may still ingest, "
                        "so this is not the same population as sample discards; lost HELP/TYPE metadata "
                        "reduces discoverability and can break tooling that depends on metric metadata."),
        "b_spans_late": build.barchart_panel(
            "Worst stacks by spans arriving over 5 minutes late (24h peak)",
            build.usage_by_slug(
                f"topk(15, max_over_time("
                f"grafanacloud_traces_instance_spans_more_than_5m_in_past_percent[{WINDOW}]))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="percent",
            thresholds=[(None, "green"), (5, "yellow"), (25, "red")],
            description="Spans arriving more than 5 minutes after the fact, as a PERCENTAGE of that "
                        "stack's spans. A late span cannot be joined to its trace, so this is the same "
                        "class of loss as incomplete flushing beside it, from a different cause - usually "
                        "a collector buffering or a clock problem. "
                        "UNIT: genuinely percent-scaled here, unlike the completeness metric next to it "
                        "which is a 0-1 ratio. It is nominally 0-100 but the observed estate maximum "
                        "exceeds 100, so do not clamp it or use 100 as a validation bound. "
                        "COVERAGE: this metric is reported by only a small subset of stacks and was never "
                        "observed at exactly zero - it appears to be emitted only while lateness is "
                        "actually happening. So read this as 'worst among the stacks reporting a problem', "
                        "NOT as a compliance percentage over the estate. Absent stacks are unmeasured, "
                        "not certified clean."),
        "b_trace": build.barchart_panel(
            "Worst stacks by trace completeness (24h low)",
            build.usage_by_slug(
                f"bottomk(15, min_over_time("
                f"grafanacloud_traces_instance_percentage_complete_traces_flushed[{WINDOW}]))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="percentunit", sort="asc",
            # A 0-1 ratio with the default `short` unit renders as a bare decimal, so 0.87 reads as a
            # count rather than 87%. `percentunit` is the 0-1 unit; `percent` would multiply by 100 twice.
            thresholds=[(None, "red"), (0.9, "green")],
            description="Share of traces flushed complete, as a percentage, over the 24h LOW - lowest "
                        "first, so short bars are the broken ones. That is the opposite of every other "
                        "chart on this dashboard, which is why it is stated here. Below 90% is amber by "
                        "threshold: a trace arriving in pieces cannot be read, so a stack here is running "
                        "instrumentation that produces nothing usable. Values can go SLIGHTLY NEGATIVE "
                        "(the source can report a small negative): the series is a computed "
                        "difference, so a small negative means a stack flushing essentially nothing, not "
                        "a broken panel."),
        "b_trace_discard": build.barchart_panel(
            "Worst stacks by discarded trace-span rate (24h peak)",
            build.usage_by_slug(
                f"topk(15, sum by(stack_id)(max_over_time("
                f"grafanacloud_traces_instance_discarded_spans_total:rate5m[{WINDOW}])))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="ops",
            description="Named trace-loss work queue, ranked by each stack's peak discarded-span rate in "
                        "the window. Fix the highest-volume sender first; the count above says how broad "
                        "the issue is, while this chart says where the loss is concentrated."),
        "b_metadata_discard": build.barchart_panel(
            "Worst stacks by discarded metric-metadata rate (24h peak)",
            build.usage_by_slug(
                f"topk(15, sum by(stack_id)(max_over_time("
                f"grafanacloud_instance_metadata_discarded_per_second[{WINDOW}])))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="ops",
            description="Named metadata-loss work queue. Kept separate from sample discards because a "
                        "stack can retain samples while losing metadata; combining them would hide which "
                        "limit or payload shape needs remediation."),
        "b_integration_fail": build.barchart_panel(
            "Notification failure rate by integration (24h peak)",
            f"sum by(integration)(max_over_time({NOTIF_METRIC}[{WINDOW}]))",
            legend="{{integration}}", ds_uid=build.USAGE_UID, unit="ops",
            description="WHICH delivery channel is failing, estate-wide. The stack-level panels say who "
                        "is affected; this says what to go and fix, which is usually one dead contact "
                        "point rather than many broken rules. Six integrations exist in this estate "
                        "(email, webhook, Slack, Google Chat, PagerDuty, OnCall) and an integration with "
                        "no failures is absent rather than zero. Values are failures per SECOND at the "
                        "24h peak, so they are small numbers - the ranking is what matters, not the "
                        "magnitude."),
        "b_notif_by_stack_integration": build.barchart_panel(
            "Worst stack + integration pairs by notification failure rate (24h peak)",
            build.usage_by_slug(
                f"topk(15, sum by(stack_id, integration)(max_over_time({NOTIF_METRIC}[{WINDOW}])))"),
            legend="{{slug}} / {{integration}}", ds_uid=build.USAGE_UID, unit="ops",
            description="The work queue: each bar is one stack's one broken channel, which is the unit a "
                        "fix actually happens in. Named via the stack_id->slug join. Failures per second "
                        "at the 24h peak."),
        "n_notiffail": build.stat_panel(
            "Stacks with failing notifications (24h)", NOTIF_STACKS, ds_uid=build.USAGE_UID,
            description="Alertmanager accepted the alert and could not deliver it. This is the worst "
                        "failure on the page - the alert fired, somebody "
                        "believes they were told, and nobody was. Check the contact point before the "
                        "rule: a dead webhook fails every notification routed through it. The "
                        "instantaneous form read 14."),
        "n_deadrules": build.stat_panel(
            "Stacks with rules that fetch nothing (24h)", DEADRULE_STACKS, ds_uid=build.USAGE_UID,
            description="Rule queries returning zero series, so the rule can never fire. Usually a rule "
                        "outliving the "
                        "metric it watched, which is invisible in the UI: a rule matching nothing shows "
                        "as Normal, not as broken. Remediation is deleting rules, so this is the only "
                        "finding on these dashboards with no cost attached to fixing it."),
        "n_evalfail": build.stat_panel(
            "Stacks with rule evaluation failures (24h)", EVALFAIL_STACKS, ds_uid=build.USAGE_UID,
            description="Windowed because a momentary failure rate answers only whether an evaluation "
                        "is failing in the current scrape. Distinct from Error-state blips that come from "
                        "shared-fleet noise: these are evaluations that failed outright."),
        "b_deadrules": build.barchart_panel(
            "Worst stacks by zero-series rule-query rate (24h peak)",
            build.usage_by_slug(
                f"topk(15, sum by(stack_id)(max_over_time("
                f"grafanacloud_instance_ruler_queries_zero_fetched_series_total:rate5m[{WINDOW}])))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="ops",
            description="Peak rate of no-op rule evaluations. Start at the top: these are rules to "
                        "delete, not rules to fix."),
        "b_notif": build.barchart_panel(
            "Worst stacks by notification failure rate (24h peak)",
            build.usage_by_slug(
                f"topk(15, sum by(stack_id)(max_over_time("
                f"grafanacloud_instance_alertmanager_notifications_failed_per_second[{WINDOW}])))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="ops",
            description="Check the contact point before the rule - a dead webhook fails every "
                        "notification routed through it."),
        "t_alerting": build.timeseries_panel(
            "Alerting health over time",
            [(DEADRULE_STACKS, "stacks with rules fetching nothing"),
             (NOTIF_STACKS, "stacks with failing notifications"),
             (EVALFAIL_STACKS, "stacks with evaluation failures")],
            ds_uid=build.USAGE_UID,
            description="Alertmanager CONFIG validity is deliberately not on this page: "
                        "grafanacloud_instance_alertmanager_invalid_config and the reload-failure "
                        "counters were empty in the evidence sweep, so a panel would read 0 for ever. "
                        "Recheck with bin/probe_usage_signals.py before assuming that negative result holds."),
    }
    if fleet_detail_views_live:
        el.update({
            "fleet_attributes": build.table_panel(
                "Active collector attributes", "risk_fleet_attributes", ds,
                schema=risk_pillar.VIEW_SCHEMAS["risk_fleet_attributes"],
                columns=["Stack", "Attribute", "Value", "Active collectors",
                         "Distinct values", "Truncated"],
                description="Bounded attribute inventory over ACTIVE collectors only. Use "
                            "collector.version and platform splits to find upgrade drift or unexpected "
                            "fleet shapes. `Distinct values` is uncapped while displayed values are "
                            "bounded; `Truncated` prevents a partial taxonomy looking complete."),
            "fleet_pipelines": build.table_panel(
                "Fleet Management pipeline reach", "risk_fleet_pipelines", ds,
                schema=risk_pillar.VIEW_SCHEMAS["risk_fleet_pipelines"],
                columns=["Stack", "Pipeline", "Enabled", "Source",
                         "Enabled collectors targeted", "Collectors targeted", "Config type",
                         "Matchers", "Updated at"],
                description="The named inventory behind the configuration counters. A disabled "
                            "pipeline targets no active configuration even when its matcher describes "
                            "a fleet; a user-owned pipeline with zero enabled targets is the ownership "
                            "review queue. Target counts are DERIVED by evaluating matchers against "
                            "active collectors."),
        })
    if public_dashboard_view_live:
        el["public_dashboards"] = build.table_panel(
            "Public dashboards that exist", "risk_public_dashboards", ds,
            schema=risk_pillar.VIEW_SCHEMAS["risk_public_dashboards"],
            description="The exact dashboards behind the configured inventory count. A disabled row "
                        "is still configured and remains in scope; `Enabled` identifies what is "
                        "serving now. The measured-stack counter above is the coverage denominator.",
        )
    if alert_routing_views_live:
        el.update({
            "alert_routing_inventory": build.table_panel(
                "Alert-routing inventory by stack", "risk_alert_routing", ds,
                schema=risk_pillar.VIEW_SCHEMAS["risk_alert_routing"],
                description="The per-stack population behind the routing counters. `Completeness` and "
                            "truncation fields are part of the finding: a short response must not look "
                            "like a stack with fewer exposed rules.",
            ),
            "alert_routing_findings": build.table_panel(
                "Rules needing routing review", "risk_alert_routing_findings", ds,
                schema=risk_pillar.VIEW_SCHEMAS["risk_alert_routing_findings"],
                description="The named rules behind missing, inherited and unverified receiver counts. "
                            "Inheritance is a governance surface rather than automatic failure; a missing "
                            "explicit receiver is the broken case to fix first.",
            ),
        })
    if org_members_view_live:
        el["org_members"] = build.table_panel(
            "Organisation membership and staff access", "risk_org_members", ds,
            schema=risk_pillar.VIEW_SCHEMAS["risk_org_members"],
            description="The named rows behind the Admin, Viewer and staff-access counts. Identity is "
                        "deliberately retained for internal governance; unknown access remains explicit. "
                        "The inventory stays below the summary because it supports review rather than "
                        "being the headline.",
        )

    collector_rows = [
        build.row("The fleet that exists",
                  ["n_coll_active", "n_coll_inactive", "n_coll_inactive_share", "n_coll"],
                  max_columns=4, row_height="short"),
        build.row("Configuration reaching it",
                  ["n_pipe_total", "n_pipe_enabled", "n_pipe_generated", "n_coll_unconfigured",
                   "n_matchers_unparsed"],
                  max_columns=5, row_height="short"),
        build.row("Trend", ["t_collectors", "t_coll_top"], max_columns=1),
        build.row("Configured and dead", ["fleet"], max_columns=1),
    ]
    if fleet_detail_views_live:
        collector_rows.extend([
            build.row("Active collector attributes", ["fleet_attributes"],
                      max_columns=1, row_height="tall"),
            build.row("Pipeline reach and ownership", ["fleet_pipelines"],
                      max_columns=1, row_height="tall"),
        ])

    public_dashboard_rows = [
        build.row("Configured inventory",
                  ["n_public", "n_public_enabled", "n_public_stacks"],
                  max_columns=3, row_height="short"),
        build.row("The two independent counts", ["n_public_events", "n_public_measured"],
                  max_columns=2, row_height="short"),
    ]
    if public_dashboard_view_live:
        public_dashboard_rows.append(build.row(
            "Which dashboards", ["public_dashboards"],
            max_columns=1, row_height="tall",
        ))

    alert_routing_rows = [
        build.row("Coverage", ["n_routing_available", "n_routing_measured", "n_routing_rules"],
                  max_columns=3, row_height="short"),
        build.row("Routing exposure", ["n_routing_inherited", "n_routing_missing",
                                        "n_routing_builtin"],
                  max_columns=3, row_height="short"),
        build.row("Interpretation", ["routing_scope"], max_columns=1),
    ]
    if alert_routing_views_live:
        alert_routing_rows.extend([
            build.row("Which rules", ["alert_routing_findings"],
                      max_columns=1, row_height="tall"),
            build.row("Per-stack population", ["alert_routing_inventory"],
                      max_columns=1, row_height="tall"),
        ])

    access_rows = [
        build.row("Organisation roles", ["n_org_admins", "n_org_viewers"],
                  max_columns=2, row_height="short"),
        build.row("Staff access state", ["b_org_staff_access"], max_columns=1),
        build.row("Stack access posture", ["n_plugindrift", "admins", "policies", "plugindrift"],
                  max_columns=1),
    ]
    if org_members_view_live:
        access_rows.append(build.row(
            "Named organisation members", ["org_members"],
            max_columns=1, row_height="tall",
        ))

    tabs = [
        build.tab("Overview", ["n_public", "n_admin", "n_noprot", "n_fmdead", "n_coll_active", "summary",
                               "t_admin"]),
        build.rows_tab("Public dashboards", public_dashboard_rows),
        build.tab("Delete protection", ["t_noprot", "noprot"]),
        build.rows_tab("Data loss", [
            build.row("Headline", ["n_discard", "n_logdrop", "n_traceincomplete",
                                       "n_trace_discard", "n_metadata_discard"],
                      max_columns=5, row_height="short"),
            build.row("Trace quality and loss", ["b_spans_late", "b_trace", "b_trace_discard"],
                      max_columns=3),
            build.row("Metric discards", ["b_reason", "b_discard"], max_columns=2),
            build.row("Metric metadata", ["b_metadata_discard"], max_columns=1),
            build.row("Trend", ["t_dataloss"], max_columns=1),
        ]),
        build.rows_tab("Alerting health", [
            build.row("Headline", ["n_notiffail", "n_deadrules", "n_evalfail"],
                      max_columns=3, row_height="short"),
            build.row("Notification delivery", ["b_integration_fail", "b_notif_by_stack_integration",
                                                 "b_notif"], max_columns=3),
            build.row("Rule queries", ["b_deadrules"], max_columns=1),
            build.row("Trend", ["t_alerting"], max_columns=1),
        ]),
        build.rows_tab("Alert routing", alert_routing_rows),
        build.rows_tab("Access", access_rows),
        build.rows_tab("Credentials", [
            build.row("Headline", ["n_sa_custom", "n_sa_extsvc"],
                      max_columns=2, row_height="short"),
            build.row("Trend and collection contract", ["t_sa", "t_sa_scope"], max_columns=2),
            build.row("Named inventory", ["sa_inventory"], max_columns=1,
                      row_height="tall"),
        ]),
        build.rows_tab("Collectors", collector_rows),
        build.tab("Per stack", ["risk"]),
    ]
    return "gcinsight-risk", "Grafana Cloud Org Insights - Risk & hygiene", \
        "Pillar E: governance and attack surface.", el, tabs


def d_value(ds: str):
    el = {
        "n_unit": build.stat_panel(
            "Series per billed user", "gcinsight_value_unit_cost_per_billed_user", decimals=0,
            description="The estate's unit economics: active series per BILLED user. **Trending down is "
                        "the whole ROI argument** - more people served per unit of spend. Uses billed "
                        "rather than active users because this is a money ratio; the two populations "
                        "differ and their spread moves with the estate."),
        "n_billed": build.stat_panel(
            "Billed users", "gcinsight_cost_billed_users",
            description="`billingActiveUsers` - the only user count valid for money, and the denominator "
                        "of every unit-economics figure on this dashboard. Deliberately NOT "
                        "`currentActiveUsers`, which measures ADOPTION rather than "
                        "cost. The spread between them moves with the estate, so it is recomputed on every "
                        "run rather than hardcoded."),
        "n_remediable": build.stat_panel(
            "Remediable series", "gcinsight_value_savings_identified_series",
            description="Series that identified Adaptive Metrics recommendations would remove if applied, "
                        "summed from the per-metric reduction each recommendation reports. NOT the active "
                        "series of unadopted stacks, which is what this read before the verbose "
                        "recommendation payload was parsed and which claimed whole stacks were "
                        "remediable."),
        "n_remediable_unused": build.stat_panel(
            "Of that, observed unused in the API window",
            "gcinsight_value_savings_unused_series",
            description="The subset whose metrics appear in no alert rule, no query and no dashboard, so "
                        "the API observed no dependency in its own window. That makes these the first "
                        "candidates to review, not safe automatic deletions: an owner must still check "
                        "longer-lived and external dependencies before applying a recommendation."),
        "n_savings_money": build.stat_panel(
            "Remediable, priced", "gcinsight_value_savings_identified_currency",
            description="The same reduction priced with the rate card at `config/ratecard.csv` in the "
                        "deployment bucket. **ABSENT, never zero, when no rate card is supplied** - rates "
                        "are never inferred, so an empty panel here means no card, not no saving. The "
                        "series figures beside it are the honest unit until one is uploaded. Period and "
                        "currency come from the card."),
        "n_savings_money_unused": build.stat_panel(
            "Priced, observed unused in the API window",
            "gcinsight_value_savings_unused_currency",
            description="The observed-unused subset, priced. Same absence rule: no rate card means no "
                        "panel, not a zero. This is a prioritisation figure for owner review, not a "
                        "promise that the reduction can be applied without sign-off."),
        "t_unit": build.timeseries_panel(
            "Unit economics - series per billed user",
            [("gcinsight_value_unit_cost_per_billed_user", "series / billed user")],
            description="Efficiency. Falling is good even while absolute volume rises."),
        "t_remediable": build.timeseries_panel(
            "Remediable volume", [("gcinsight_value_savings_identified_series", "series"),
                                  ("gcinsight_value_savings_unused_series", "unused in API window")],
            description="The reduction pending Adaptive recommendations would deliver, and the subset "
                        "with no observed dependency in the API window. Both require owner review before "
                        "application. This line should fall as reviewed recommendations are applied."),
        "b_adoption": build.barchart_panel(
            "Signal adoption, % of estate", "gcinsight_value_adoption_ratio", legend="{{signal}}",
            unit="percent",
            description="Share of the estate ingesting each signal. Compare signal adoption here before "
                        "deciding whether the opportunity is basic ingestion or a derived capability such "
                        "as span metrics. "
                        "COUNTS ANY REPORTED USAGE, not a volume threshold: the inventory fields behind "
                        "this are in different units per signal - series for metrics, volume for logs and "
                        "traces - so a single numeric floor is meaningless across them. This panel "
                        "previously applied a 1,000-SERIES floor to a log field whose estate-wide maximum "
                        "is under 20, and therefore reported 0% log and 0% trace adoption while the "
                        "sentence above it said the opposite. The counts are calibrated against the "
                        "`grafanacloud-usage` datasource and agree with it to the stack on metrics, traces "
                        "and profiles."),
        # This was one bar chart over every benchmark at once. The bars were series counts, ratios,
        # percentages, user counts, dashboard counts and a 0-100 score sharing ONE axis - so their heights
        # were arithmetically incomparable and the tallest bar was whichever benchmark happened to be
        # denominated in the largest unit. Split by unit; the table beside them carries every figure.
        "b_bench_pct": build.barchart_panel(
            "Benchmarks measured as a percentage (median)",
            'gcinsight_value_benchmark{kind=~"admin_share|adaptive_adoption"}', legend="{{kind}}",
            unit="percent",
            description="The two benchmarks that are genuinely percentages, so their bars ARE comparable "
                        "with each other. Median, never a mean - a single 3M-series stack would define a "
                        "mean and describe nothing."),
        "b_bench_ratio": build.barchart_panel(
            "Benchmarks measured as a ratio (median)",
            'gcinsight_value_benchmark{kind=~"stickiness"}', legend="{{kind}}",
            unit="percentunit",
            description="Ratios on a 0-1 scale, rendered as percentages. Kept apart from the 0-100 "
                        "benchmarks because mixing the two scales on one axis makes a 0.6 ratio render as "
                        "a bar 1/100th the height of an equivalent 60%."),
        "b_features": build.barchart_panel(
            "gcom provisioning flags - stacks with the flag set",
            "gcinsight_estate_feature_stacks", legend="{{kind}}",
            description="Three booleans from the gcom inventory, NOT a statement about what the organisation uses. "
                        "A ZERO here is a measured zero, not a gap - unlike "
                        "the rest of this platform, where an absent series means 'could not measure'. "
                        "READ `kind=\"incident\"` WITH THE PANEL TO ITS RIGHT: it is the legacy "
                        "standalone Grafana Incident flag, while the live IRM/OnCall panel measures "
                        "actual alert-group activity independently. It "
                        "proves a flag is unset; it does not prove a capability is unused, and it never "
                        "proves the organisation pays for it - enablement backlog at most, never wasted spend."),
        # The disproof, parked beside the claim on purpose. `incident: 0` was read as "incident response
        # is unused across the estate" and that is WRONG - measured 2026-08-18, 20 stacks carry 11,549
        # OnCall alert groups while gcom reports incident=0 AND billingOnCallActiveUsers=0 on every one of
        # them. Two fields, two products. Anyone deciding from the bar chart alone reaches a false
        # conclusion, so the counter-evidence sits in the same tab rather than in a doc nobody opens.
        "n_oncall": build.stat_panel(
            "Stacks actually running IRM/OnCall", ONCALL_STACKS, ds_uid=build.USAGE_UID,
            description="Live from grafanacloud-usage, and the direct contradiction of `incident 0` to "
                        "its left. This panel counts stacks with alert-group activity, not merely a "
                        "provisioned entitlement. gcom's `incident` field is the legacy standalone "
                        "Grafana Incident product; IRM and OnCall do not set it. Evidence: "
                        "evidence/usage-datasource-signals.json, key `irm_in_use`."),
        "b_oncall": build.barchart_panel(
            "OnCall alert groups by stack",
            build.usage_by_slug("topk(15, sum by(stack_id)(grafanacloud_oncall_instance_alert_groups_total))"),
            legend="{{slug}}", ds_uid=build.USAGE_UID,
            description="Who is actually on the end of a pager. The first real operating signal in this "
                        "platform - everything else here counts what EXISTS, this counts what HAPPENED. "
                        "Note this metric is the exception on this datasource: it already carries `slug`, "
                        "`team`, `service_name`, `integration` and `state` natively, so the stack_id join "
                        "is only needed because the sum discards them. Those labels are a far richer "
                        "seam than this bar chart uses - team and MTTA/MTTR dimensions are "
                        "available and deliberately out of scope here. See IDEAS.md."),
        "n_k6_provisioned": build.stat_panel(
            "Stacks with a k6 org id", 'gcinsight_estate_feature_stacks{kind="k6"}',
            description="gcom provisioning flag only: a stack can carry a k6 org id without running a "
                        "test. Read it against current-period virtual-user-hour activity beside it; the "
                        "gap is provisioned-but-inactive, not proof of paid waste."),
        "n_k6_active": build.stat_panel(
            "Stacks using k6 this billing period", K6_ACTIVE_STACKS,
            ds_uid=build.USAGE_UID,
            description="Stacks with positive browser or protocol virtual-user-hour usage in the current "
                        "billing period, collapsed by stack before counting. This is actual test activity, "
                        "not the k6OrgId provisioning flag."),
        "b_k6_active": build.barchart_panel(
            "k6 virtual-user hours by stack this billing period",
            build.usage_by_slug(
                "topk(15, sum by(stack_id)(grafanacloud_k6_stack_virtual_user_hours_usage))"
            ),
            legend="{{slug}}", ds_uid=build.USAGE_UID,
            description="Current billing-period browser and protocol virtual-user hours, summed per "
                        "stack and named through the stack-id join. This is a usage ranking, not a "
                        "lifetime test inventory."),
        "n_sm_provisioned": build.stat_panel(
            "Stacks with the Synthetic Monitoring datasource",
            "gcinsight_usage_synthetic_monitoring_datasource_stacks",
            description="Stacks where the Synthetic Monitoring datasource is provisioned. Presence alone "
                        "does not prove a check is executing; compare with the 24-hour activity count."),
        "n_sm_active": build.stat_panel(
            "Stacks executing Synthetic Monitoring checks (24h)", SM_ACTIVE_STACKS,
            ds_uid=build.USAGE_UID,
            description="Stacks with positive billable check-execution rate at any point in the last day, "
                        "collapsed across browser, protocol and scripted check classes before counting."),
        "b_sm_active": build.barchart_panel(
            "Synthetic Monitoring execution rate by stack (24h peak)",
            build.usage_by_slug(
                f"topk(15, sum by(stack_id)(max_over_time("
                f"grafanacloud_sm_billable_check_executions_per_second[{WINDOW}])))"
            ),
            legend="{{slug}}", ds_uid=build.USAGE_UID, unit="ops",
            description="Named activity ranking behind the executing-stack count. A provisioned stack "
                        "absent here ran no billable checks in the window; a high bar identifies where the "
                        "actual synthetic workload and cost are concentrated."),
        "t_features": build.timeseries_panel(
            "gcom provisioning flags over time",
            [("gcinsight_estate_feature_stacks", "{{kind}}")],
            description="The line that should move when enablement lands. Whether k6 is USED needs a "
                        "separate k6 activity signal; the gcom inventory flag alone cannot establish it. "
                        "For genuine product activation prefer grafanacloud_product_activation_status "
                        "on the usage datasource; these three gcom booleans cannot see those products."),
        "summary": build.table_panel(
            "Value summary", "value_summary", ds,
            description="Billed users is the only figure valid for money; active users is adoption."),
        "savings": build.table_panel(
            "Savings", "value_savings", ds,
            description="Measured Adaptive recommendation reductions and their coverage. Currency is "
                        "present only when a valid rate card prices the relevant dimension; absence is "
                        "unknown, never zero."),
        "adoption": build.table_panel(
            "Signal adoption", "value_adoption", ds,
            description="One row per signal with the stack count behind each estate percentage. This "
                        "view treats a positive inventory usage value as adoption; it does not reuse the "
                        "1,000-series OTLP floor because log and trace inventory fields are volume units."),

        # --- Capability gaps (Tier 2), live from `grafanacloud-usage` ---------------------------------
        # The honest version of the entitlement question. The three gcom booleans on the tab before this
        # cannot see any of these products, which is why that tab is named for what it measures.
        "n_activated": build.stat_panel(
            "Products activated somewhere in the estate",
            "count(count by(product)(grafanacloud_product_activation_status == 1))",
            ds_uid=build.USAGE_UID,
            description="Count of products this metric reports as switched on somewhere. Real activation "
                        "state, not a provisioning flag - prefer this over "
                        "`gcinsight_estate_feature_stacks` for any entitlement claim."),
        "b_activation": build.barchart_panel(
            "Product activation - stacks per product",
            "count by(product)(grafanacloud_product_activation_status == 1)", legend="{{product}}",
            ds_uid=build.USAGE_UID,
            description="Stacks with each product's activation status set. This is the product-adoption "
                        "view the gcom provisioning flags cannot provide; absent products are unreported, "
                        "not necessarily disabled."),
        "n_nativehist": build.stat_panel(
            "Stacks using native histograms", NATIVE_HIST_STACKS, ds_uid=build.USAGE_UID,
            description="Stacks emitting native histograms at any point in the last 24h. Read against "
                        "the metrics-ingesting denominator below. Native histograms replace a fan of "
                        "`_bucket` series with a single series, and this estate carries 11.4M active "
                        "series. It is also the standing recommendation from the DPM-cost prompt review, "
                        "so the two pieces of work corroborate each other."),
        "n_exemplars": build.stat_panel(
            "Stacks emitting exemplars", EXEMPLAR_STACKS, ds_uid=build.USAGE_UID,
            description="Stacks emitting exemplars at any point in the last 24h. Exemplars are what lets "
                        "a metrics panel click through to a trace; compare against the metrics and traces "
                        "denominators below to see the addressable gap."),
        # CURRENT STATE, as named bars. Nine lines on one time axis, most of them flat and close
        # together, made the present position unreadable - a reader had to trace a line to its right edge
        # to answer "how many stacks use span metrics", which is the whole question of this tab. The two
        # denominator bars are included so every derived count can be read against its own population
        # without leaving the panel.
        "b_capability": build.barchart_series_panel(
            "Capability adoption today - derived features vs their own denominators",
            [(METRICS_STACKS, "stacks ingesting metrics (DENOMINATOR)"),
             (TRACES_STACKS, "stacks ingesting traces (DENOMINATOR)"),
             (NATIVE_HIST_STACKS, "native histograms"),
             (EXEMPLAR_STACKS, "exemplars"),
             (SPANMETRIC_STACKS, "span metrics"),
             (SERVICEGRAPH_STACKS, "service graphs"),
             (PDC_STACKS, "private datasource connect"),
             (ADAPTIVE_LOGS_STACKS, "adaptive logs"),
             (ADAPTIVE_TRACES_STACKS, "adaptive traces")],
            ds_uid=build.USAGE_UID, sort="desc",
            description="Where the estate stands NOW, biggest first. **The two bars marked DENOMINATOR "
                        "are populations, not achievements** - every other bar is a subset of one of them, "
                        "and a derived feature can only ever reach its own denominator. Span metrics and "
                        "service graphs are derived from traces, so read them against the traces bar; the "
                        "rest are metrics features. The gap between a derived bar and its denominator is "
                        "the addressable opportunity, and it is the largest structured expand story in "
                        "this estate. Counts are windowed over 24h - a stack ingesting at any point in the "
                        "window counts, because trace ingest is bursty and an instantaneous count "
                        "understated the trace population nearly sixfold."),
        "t_capability": build.timeseries_panel(
            "Capability adoption - stacks using each feature",
            [(NATIVE_HIST_STACKS, "native histograms"),
             (EXEMPLAR_STACKS, "exemplars"),
             (SPANMETRIC_STACKS, "span metrics"),
             (SERVICEGRAPH_STACKS, "service graphs"),
             (PDC_STACKS, "private datasource connect"),
             (ADAPTIVE_LOGS_STACKS, "adaptive logs"),
             (ADAPTIVE_TRACES_STACKS, "adaptive traces"),
             (TRACES_STACKS, "-- stacks ingesting traces at all"),
             (METRICS_STACKS, "-- stacks ingesting metrics at all")],
            ds_uid=build.USAGE_UID,
            description="THE TWO `--` LINES ARE THE DENOMINATORS - read every other line against them. "
                        "Span metrics, service graphs and Adaptive Traces divide by trace-ingesting "
                        "stacks; the other features divide by metrics-ingesting stacks. "
                        "WINDOW MATTERS: trace ingest is bursty, so an instantaneous denominator can be "
                        "many times smaller and reverse the conclusion. Every line here uses the same "
                        "windowed population."),
        "bench": build.table_panel(
            "Internal benchmarks", "value_benchmarks", ds,
            description="Median, p90 and worst per dimension across the organisation's own live stack population. We cannot show "
                        "another customer's data, and we do not need to: the stacks benchmark against each "
                        "other, and 'your own p90 team already does this' is a stronger argument than any "
                        "industry average because nobody can dispute the comparison."),
    }
    tabs = [
        build.tab("Overview", ["n_unit", "n_billed", "n_remediable", "t_unit", "summary"]),
        build.rows_tab("Savings", [
            build.row("Reduction available", ["n_remediable", "n_remediable_unused",
                                              "n_savings_money", "n_savings_money_unused"],
                      max_columns=4, row_height="short"),
            build.row("Progress", ["t_remediable"], max_columns=1),
            build.row("Per stack", ["savings"], max_columns=1),
        ]),
        build.tab("Adoption", ["b_adoption", "adoption"]),
        build.tab("Capability flags", ["b_features", "n_oncall", "b_oncall", "t_features"]),
        build.rows_tab("Test and probe adoption", [
            build.row("Provisioned versus active",
                      ["n_k6_provisioned", "n_k6_active", "n_sm_provisioned", "n_sm_active"],
                      max_columns=4, row_height="short"),
            build.row("Where the workload runs", ["b_k6_active", "b_sm_active"], max_columns=2),
        ]),
        build.rows_tab("Capability gaps", [
            build.row("Headline", ["n_activated", "n_nativehist", "n_exemplars"],
                      max_columns=3, row_height="short"),
            build.row("Current adoption", ["b_activation", "b_capability"], max_columns=2),
            build.row("Trend", ["t_capability"], max_columns=1),
        ]),
        build.tab("Benchmarks", ["b_bench_pct", "b_bench_ratio", "bench"]),
    ]
    return "gcinsight-value", "Grafana Cloud Org Insights - Business value", \
        "Pillar F: unit economics and internal benchmarking, for weekly reading.", el, tabs


def d_operations(ds: str):
    """Pillar G - are they actually operating? Reads `grafanacloud-usage` only: no collector, no series.

    Every other dashboard here counts what EXISTS: stacks, dashboards, rules, users, series. This one
    counts what somebody DID - acknowledged an alert, resolved it, or never touched it. It is the only
    behavioural signal the platform has, and the only one that measures outcomes rather than inventory.

    Scope is stated on the page, not just here: the response-timing metrics cover **8 stacks**, so the
    engagement figures describe **8,700 alert groups on those 8**, not the estate's 11,692 across 58.
    """
    el = {
        # --- Engagement: the headline -----------------------------------------------------------------
        "n_engagement": build.stat_panel(
            "Alerts that anyone acknowledged", ENGAGEMENT_RATE, unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="THE HEADLINE. Alert groups with a recorded acknowledgement divided by all alert "
                        "groups on the stacks that report response timing. OnCall logs a response time "
                        "when somebody engages; groups outside the numerator were resolved, silenced or "
                        "left without an acknowledgement. "
                        "Say 'no acknowledgement was recorded' rather than 'nobody looked': the metric "
                        "proves an absent acknowledgement, not intent. "
                        "The denominator is restricted to those same timing stacks on purpose; using the "
                        "broader OnCall population would mix coverage."),
        "n_engaged": build.stat_panel(
            "Alert groups acknowledged", ENGAGED, ds_uid=build.USAGE_UID,
            description="Alert groups with a response-time observation. This is the population every "
                        "response-time number on this page is calculated over."),
        "n_engaged_denom": build.stat_panel(
            "Alert groups raised (timing stacks)", ENGAGED_DENOM, ds_uid=build.USAGE_UID,
            description="All alert groups on stacks that report timing. The broader OnCall estate is "
                        "deliberately NOT used because the acknowledgement numerator does not exist over "
                        "that full population."),
        "b_teamengage": build.barchart_panel(
            "Share of each team's alerts that anyone acknowledged", TEAM_ENGAGEMENT,
            legend="{{team}}", ds_uid=build.USAGE_UID, unit="percentunit",
            description="Acknowledged share per team over the timing-stack population. The spread shows "
                        "whether routing and ownership correlate with response rather than hiding them "
                        "inside an estate average. "
                        f"Teams under {TEAM_MIN_GROUPS} alert groups are excluded - too few to mean "
                        "anything, the same discipline as the delete-protection threshold."),
        "t_engagement": build.timeseries_panel(
            "Engagement rate over time", [(ENGAGEMENT_RATE, "acknowledged share")],
            unit="percentunit", ds_uid=build.USAGE_UID,
            description="Both sides are cumulative counters, so this is a lifetime running average and "
                        "moves slowly by construction. A step up means a burst of alerts actually being "
                        "worked; a slow decline means alert volume growing faster than anyone answers it."),

        # --- Response time, for the 12% that were engaged ---------------------------------------------
        "n_mtta": build.stat_panel(
            "Median time to acknowledge", MTTA_MEDIAN, unit="s", decimals=0, ds_uid=build.USAGE_UID,
            description="Read it as the answer to a narrow question: of the alerts somebody engaged with, "
                        "how fast? The on-call works when an alert is pointed at a person. Combined with "
                        "the engagement panel, that is the whole diagnosis - a routing problem, not a "
                        "responsiveness problem."),
        "n_mttr": build.stat_panel(
            "Median time to resolve", MTTR_MEDIAN, unit="s", decimals=0, ds_uid=build.USAGE_UID,
            description="Median elapsed time from alert-group creation to resolution, only for groups "
                        "with a recorded timing observation. Compare with acknowledgement time to split "
                        "time-to-notice from time-to-fix."),
        "n_mtta_mean": build.stat_panel(
            "Mean time to acknowledge", MTTA_MEAN, unit="s", decimals=0, ds_uid=build.USAGE_UID,
            description="Arithmetic mean over acknowledged groups. A large gap from the median is not a "
                        "contradiction: a long tail can drag the mean sharply upward. Quoting the "
                        "mean alone makes a working on-call look broken; quoting the median alone hides "
                        "the tail. Both are on this page for that reason."),
        "n_tail": build.stat_panel(
            "Acknowledged only after an hour", ACK_TAIL, ds_uid=build.USAGE_UID,
            description="A COUNT above the "
                        "top bucket, never a high percentile: the histogram's largest finite bucket is "
                        "3600s, so p90 and p99 both saturate at exactly 3600 and would be read as "
                        "'an hour' when the truth is 'at least an hour, and the data cannot say more'."),
        "n_tail_share": build.stat_panel(
            "Share acknowledged only after an hour", ACK_TAIL_SHARE, unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="Share of ACKNOWLEDGED alerts whose recorded acknowledgement exceeded one hour, "
                        "not a share of all alerts. Groups without an acknowledgement have no duration to "
                        "place in this ratio."),
        "b_ackdist": build.barchart_series_panel(
            "Acknowledgements by response-time band",
            # Prometheus histogram buckets are cumulative. Subtract adjacent buckets so every alert is
            # represented exactly once and the chart can be read directly rather than asking readers to
            # perform five subtractions. The order is the scale's order, deliberately not by size.
            [(f'sum({ACK}_bucket{{le="60.0"}})', "within 1 min"),
             (f'sum({ACK}_bucket{{le="300.0"}}) - sum({ACK}_bucket{{le="60.0"}})',
              "1 to 5 min"),
             (f'sum({ACK}_bucket{{le="600.0"}}) - sum({ACK}_bucket{{le="300.0"}})',
              "5 to 10 min"),
             (f'sum({ACK}_bucket{{le="3600.0"}}) - sum({ACK}_bucket{{le="600.0"}})',
              "10 min to 1 hour"),
             (f'sum({ACK}_bucket{{le="+Inf"}}) - sum({ACK}_bucket{{le="3600.0"}})',
              "over 1 hour")],
            ds_uid=build.USAGE_UID,
            description="Disjoint bands derived by subtracting adjacent cumulative histogram buckets, "
                        "so every acknowledgement appears in exactly one bar. Boundaries are fixed "
                        "by Grafana Cloud at 1m/5m/10m/1h, so this is the full resolution available - "
                        "there is no finer breakdown to build, and it is also why no p90 or p99 is shown "
                        "anywhere on this dashboard: both saturate at the top bucket and would report "
                        "exactly one hour regardless of the real figure."),
        "t_response": build.timeseries_panel(
            "Acknowledge and resolve medians over time",
            [(MTTA_MEDIAN, "median acknowledge (s)"), (MTTR_MEDIAN, "median resolve (s)")],
            unit="s", ds_uid=build.USAGE_UID,
            description="Medians only. The means make a poor trend line: `_sum`/`_count` are cumulative "
                        "counters, so one very stale alert steps the series permanently."),

        # --- Ownership --------------------------------------------------------------------------------
        "n_unowned_all": build.stat_panel(
            "Unowned share - timing-stack alerts", UNOWNED_SHARE_ALL, unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="Share of alert groups labelled `team=\"No team\"`, restricted to the stacks "
                        "that report acknowledgement timing. This is the same population as the "
                        "acknowledged-alert share beside it, so the two ratios can be compared."),
        "n_unowned_acked": build.stat_panel(
            "Unowned share of ACKNOWLEDGED alerts", UNOWNED_SHARE_ACKED, unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="Share of acknowledged alert groups labelled `team=\"No team\"`. "
                        "Acknowledgement timing exists on a restricted set of stacks; the panel beside "
                        "it deliberately restricts its denominator to that same timing-stack population, "
                        "so their difference reflects engagement rather than coverage."),
        "n_unowned_svc": build.stat_panel(
            "Timing-stack alerts with no service attribution", UNOWNED_SERVICE_SHARE,
            unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="Share of OnCall alert groups on timing-reporting stacks labelled "
                        "`service_name=\"No service\"`. The same population restriction as the team "
                        "share prevents ownership differences being confused with measurement coverage. The "
                        "same governance gap as the "
                        "team field but wider, and it is what stops anyone answering 'which service "
                        "pages us most' - the by-service chart on the Alert flow tab is mostly a picture "
                        "of how much attribution is missing."),
        "b_teamtail": build.barchart_panel(
            "Teams by share of acknowledged alerts that took over an hour", TEAM_TAIL_SHARE,
            legend="{{team}}", ds_uid=build.USAGE_UID, unit="percentunit",
            description="For each team, the share of acknowledged alerts whose recorded response took "
                        "over an hour. Use the live spread to test whether ownership affects "
                        "not just WHETHER an alert is answered but how fast. Teams "
                        "under 10 acknowledged groups are excluded."),
        "b_teamvol": build.barchart_panel(
            "Alert volume by team", TEAM_VOLUME, legend="{{team}}", ds_uid=build.USAGE_UID,
            description="Lifetime alert-group volume by team across every OnCall stack reporting the "
                        "counter. This has broader coverage than the timing-based engagement panels, so "
                        "use it to rank workload, not as their denominator."),
        "b_service_owner": build.barchart_panel(
            "Observed services and their owning teams",
            f"topk(20, sum by(service_name, team)({GROUPS}))",
            legend="{{service_name}} · {{team}}", ds_uid=build.USAGE_UID, limit=20,
            description="A named service-and-owner catalogue read directly from OnCall's live labels. "
                        "The volume ranks the register; `No service` and `No team` remain visible rather "
                        "than being filtered away, because they state the unmatched share."),

        # --- Alert flow -------------------------------------------------------------------------------
        "n_groups": build.stat_panel(
            "Alert groups, estate-wide", ALL_GROUPS, ds_uid=build.USAGE_UID,
            description="All OnCall alert groups by state across stacks reporting the counter. A cumulative counter, so "
                        "this is lifetime volume and not a rate."),
        "n_notified": build.stat_panel(
            "User notifications sent",
            "sum(grafanacloud_oncall_instance_user_was_notified_of_alert_groups_total)",
            ds_uid=build.USAGE_UID,
            description="Cumulative user-notification events across OnCall. This is lifetime volume, not "
                        "a current rate or a count of distinct people."),
        "n_state_history_failures": build.stat_panel(
            "Stacks failing to write alert state history (24h)",
            STATE_HISTORY_FAILURE_STACKS, ds_uid=build.USAGE_UID,
            description="Stacks where the state-history write-failure rate was above zero at any point "
                        "in the window. A point-in-time zero misses intermittent failures, so this uses "
                        "the 24-hour maximum and collapses signal instances to one stack."),
        "b_state_history_failures": build.barchart_panel(
            "Alert state-history write failures by stack (24h)",
            build.usage_by_slug(f"topk(15, {STATE_HISTORY_FAILURES})"),
            legend="{{slug}}", ds_uid=build.USAGE_UID,
            description="The named stacks behind the counter, ranked by their maximum failure rate in "
                        "the window. State-history write failure hides alert transitions from later "
                        "analysis, so any bar is an observability integrity defect, not merely alert "
                        "volume."),
        # DEDUPED BY (stack_id, slug) DELIBERATELY. The raw metric carries a per-Alertmanager-instance
        # `id` label which is not always the stack, so several stacks emit two series and a naive topk
        # lists the same stack twice with its load split across the rows.
        "b_am_active": build.barchart_panel(
            "Active Grafana Alertmanager alerts by stack",
            "topk(15, sum by(stack_id, slug)("
            'grafanacloud_instance_alertmanager_alerts{state="active"} '
            "* on(stack_id) group_left(slug) " + build.USAGE_INFO + "))",
            legend="{{slug}}", ds_uid=build.USAGE_UID,
            description="**GRAFANA ALERTMANAGER alerts, which are NOT the OnCall alert groups the rest of "
                        "this dashboard counts.** Every other panel here measures OnCall - what paged a "
                        "human and whether anyone answered. This measures what Grafana's own Alertmanager "
                        "is currently holding in the `active` state, which is a much larger number and "
                        "includes everything that never routes to a person. Read the two together: a "
                        "stack high here and absent from the OnCall panels is firing constantly with "
                        "nobody on the other end. Summed per stack because some stacks run more than one "
                        "Alertmanager instance and would otherwise appear twice."),
        "b_integration": build.barchart_panel(
            "What pages them, by integration",
            f"topk(12, sum by(integration)({GROUPS}))", legend="{{integration}}",
            ds_uid=build.USAGE_UID,
            description="Lifetime OnCall alert-group volume by integration, largest first. Differently "
                        "named integrations that serve the same destination expose a consolidation and "
                        "ownership problem; this chart counts names exactly as OnCall reports them."),
        "b_service": build.barchart_panel(
            "What pages them, by service",
            f"topk(8, sum by(service_name)({GROUPS}))", legend="{{service_name}}",
            ds_uid=build.USAGE_UID,
            description="Lifetime OnCall alert-group volume by service. The `No service` bar is the "
                        "finding - most alerts cannot be attributed to a service, so treat this chart as "
                        "a measure of missing attribution first and a ranking second."),
        "t_state": build.timeseries_panel(
            "Alert groups by state",
            [(f"sum by(state)({GROUPS})", "{{state}}")], ds_uid=build.USAGE_UID,
            description="Cumulative counters, so these lines only ever rise and the SLOPE is the signal. "
                        "A `firing` line climbing while `resolved` stays flat means alerts arriving and "
                        "not being closed."),
    }
    tabs = [
        build.rows_tab("Engagement", [
            build.row("Headline", ["n_engagement", "n_engaged", "n_engaged_denom"],
                      max_columns=3, row_height="short"),
            build.row("By team", ["b_teamengage"], max_columns=1),
            build.row("Trend", ["t_engagement"], max_columns=1),
        ]),
        build.rows_tab("Response time", [
            build.row("Typical response", ["n_mtta", "n_mttr", "n_mtta_mean"],
                      max_columns=3, row_height="short"),
            build.row("Long tail", ["n_tail", "n_tail_share"], max_columns=2, row_height="short"),
            build.row("Distribution and trend", ["b_ackdist", "t_response"], max_columns=2),
        ]),
        build.rows_tab("Ownership", [
            build.row("Headline", ["n_unowned_all", "n_unowned_acked", "n_unowned_svc"],
                      max_columns=3, row_height="short"),
            build.row("Team detail", ["b_teamtail", "b_teamvol"], max_columns=2),
            build.row("Named service register", ["b_service_owner"], max_columns=1),
        ]),
        build.tab("Alert flow", ["n_groups", "n_notified", "n_state_history_failures",
                                 "b_state_history_failures", "b_integration", "b_service", "t_state",
                                 "b_am_active"]),
    ]
    return "gcinsight-operations", "Grafana Cloud Org Insights - Operations", \
        ("Pillar G: what the estate actually DOES - acknowledged, resolved, or never touched. The only "
         "behavioural signal in this platform. Live from the stack's own grafanacloud-usage datasource, "
         "no collector and no series. SCOPE: response timing covers only stacks that emit timing; "
         "volume and ownership cover the broader OnCall population. Ratios restrict their denominator "
         "to the timing population and each panel says which."), el, tabs



def d_dashboards(ds: str):
    """Pillar J - what people actually OPEN, including observed public-dashboard activity.

    Every other pillar measures what EXISTS. This one measures what is USED, from each stack's own
    `grafanacloud-usage-insights` datasource, read with that stack's own read-only credential. A stack
    with 400 dashboards and 3 that anyone opens looks healthy everywhere else in this platform.

    `publicDashboardUid` on a dashboard-open event proves exposure through a public share, and
    `userId=-1` identifies an unauthenticated reader. It does not enumerate configured shares or identify
    when sharing was enabled. The complete configured inventory lives on Risk; this tab measures which
    public dashboards were actually used.

    Every figure covers the same rolling window, stated on the tab rather than assumed.
    """
    opening_inventory_live = _published_views_exist(insights_inventory_pillar.DASHBOARD_VIEW)
    query_cost_live = _published_views_exist(insights_inventory_pillar.QUERY_COST_VIEW)
    el = {
        # --- Adoption ---------------------------------------------------------------------------------
        "n_views": build.stat_panel(
            "Dashboard opens", 'sum(gcinsight_dashboards_estate_views{version="2"})',
            description="`dashboard-view` events across every measured stack. This is the only "
                        "engagement signal in the platform: dashboard COUNT says what exists, this says "
                        "what anyone looked at. Read it against the coverage tab - it is a sum over the "
                        "stacks that could be measured, not over the estate."),
        "n_viewed": build.stat_panel(
            "Distinct dashboards opened",
            'sum(gcinsight_dashboards_estate_dashboards_viewed{version="2"})',
            description="Dashboards opened at least once in the window, summed per stack. Against the "
                        "provisioned count in the per-stack table this is the "
                        "provisioned-but-never-opened figure, which is the governance point."),
        "n_viewers": build.stat_panel(
            "Distinct authenticated viewers", 'sum(gcinsight_dashboards_estate_viewers{version="2"})',
            description="Distinct authenticated `userId`s per stack, SUMMED; the anonymous `-1` "
                        "sentinel is excluded and reported separately. **Not an org-wide distinct count** - "
                        "somebody using four stacks counts four times. Treat it as reach per stack "
                        "aggregated, never as headcount."),
        "n_provisioned": build.stat_panel(
            "Dashboards provisioned (measured stacks)",
            'sum(gcinsight_dashboards_estate_provisioned{version="2"})',
            description="Dashboards that EXIST on the stacks this pillar could measure, from inventory. "
                        "The denominator for the share beside it. Deliberately not the estate's whole "
                        "dashboard count, which would divide by stacks with no usage figures and "
                        "understate adoption."),
        "n_viewed_share": build.stat_panel(
            "Share of provisioned dashboards opened",
            'sum(gcinsight_dashboards_estate_dashboards_viewed{version="2"}) / '
            'sum(gcinsight_dashboards_estate_provisioned{version="2"})',
            unit="percentunit", decimals=1,
            description="**The headline governance figure of this pillar.** Numerator and denominator "
                        "both cover the measured stacks only, so it is a real share rather than two "
                        "populations divided. Read it beside the coverage tab: a low share means most "
                        "of what has been built is never opened, which is a maintenance and a licence "
                        "conversation rather than a fault."),
        "n_measured": build.stat_panel(
            "Stacks measured",
            'sum(gcinsight_dashboards_estate_stacks{kind="measured",version="2"})',
            description="Stacks whose usage-insights datasource answered. The denominator for every "
                        "figure on this dashboard; the coverage tab says why the rest did not."),
        "n_with_views": build.stat_panel(
            "Stacks with any dashboard opened",
            'sum(gcinsight_dashboards_estate_stacks{kind="with_views",version="2"})',
            description="Measured stacks where at least one dashboard was opened. The gap to the "
                        "measured count is stacks nobody visited at all in the window."),
        "n_with_public": build.stat_panel(
            "Stacks with public-dashboard activity",
            'sum(gcinsight_dashboards_estate_stacks{kind="with_public_dashboards",version="2"})',
            description="Measured stacks carrying at least one distinct `publicDashboardUid` in the "
                        "window. This is the number of owner conversations behind the public-dashboard "
                        "count, not an inventory of every configured public share."),
        "tbl_usage": build.table_panel(
            "Per stack: what exists, what gets opened, what it costs to serve",
            "insights_dashboard_usage", ds,
            schema=insights_pillar.VIEW_SCHEMAS["insights_dashboard_usage"],
            description="Ordered by opens. `Viewed share %` is dashboards opened against dashboards "
                        "provisioned - the lower it is, the more of that stack nobody uses. "
                        "`Cache hit %` is blank where the stack ran too few queries for a ratio to mean "
                        "anything, rather than showing a swing between 0 and 100."),
        "t_viewers": build.timeseries_panel(
            "Distinct authenticated viewers over time, by stack",
            [('topk(10, gcinsight_dashboards_viewers{version="2",stack=~"$stack"})', "{{stack}}")],
            description="Distinct authenticated `userId`s per stack; anonymous `-1` is excluded. Opens "
                        "and viewers move independently and the "
                        "gap is the point: rising opens on flat viewers is the same few people "
                        "refreshing, which is a different story from the platform reaching more of "
                        "the organisation."),
        "t_viewed": build.timeseries_panel(
            "Distinct dashboards opened over time, by stack",
            [('topk(10, gcinsight_dashboards_viewed{version="2",stack=~"$stack"})', "{{stack}}")],
            description="How much of each stack's dashboard estate gets touched, rather than how "
                        "often. A stack whose opens climb while this line stays flat has one popular "
                        "dashboard, not broad adoption."),
        "t_views": build.timeseries_panel(
            "Dashboard opens over time, by stack",
            [('topk(10, gcinsight_dashboards_views{version="2",stack=~"$stack"})', "{{stack}}")],
            description="Top 10 stacks by opens. The direction of travel is the point: a stack whose "
                        "line falls after an onboarding push is the conversation this platform exists "
                        "to start."),

        # --- Public-dashboard exposure activity --------------------------------------------------------
        "n_public": build.stat_panel(
            "Public dashboards observed in use",
            'sum(gcinsight_dashboards_estate_public{version="2"})',
            description="Distinct public dashboards carrying at least one `dashboard-view` event in "
                        "the measurement window. This proves exposure activity but is not the configured "
                        "inventory: a public dashboard nobody opened is absent here and remains visible "
                        "on the Risk dashboard."),
        "n_public_events": build.stat_panel(
            "Public dashboard opens",
            'sum(gcinsight_dashboards_estate_public_events{version="2"})',
            description="`dashboard-view` events carrying a non-empty `publicDashboardUid`. A high "
                        "open count against a low observed-dashboard count means one heavily-read public "
                        "page; neither figure says when the share was configured."),
        "n_anon": build.stat_panel(
            "Anonymous dashboard opens",
            'sum(gcinsight_dashboards_estate_anonymous_views{version="2"})',
            description="Opens with `userId=-1`: a reader who never authenticated. Corroborates the "
                        "public exposure signal from a different field on the same open events."),
        "tbl_public": build.table_panel(
            "Top public dashboards by opens (up to 10 per stack)",
            "insights_public_dashboards", ds,
            schema=insights_pillar.VIEW_SCHEMAS["insights_public_dashboards"],
            description="A BOUNDED SAMPLE OF ACTIVITY: usage insights retains the ten most-opened public "
                        "dashboards per stack, with stack, dashboard name, dashboard uid and public uid. "
                        "It names the busiest objects to investigate first and is not a complete configured "
                        "inventory; Risk holds that inventory. An empty table means no public-dashboard "
                        "activity was observed, not that no public dashboards exist."),
        "t_public": build.timeseries_panel(
            "Public dashboard opens over time, by stack",
            [('topk(10, gcinsight_dashboards_public_events{version="2",stack=~"$stack"})', "{{stack}}")],
            description="Observed opens of already-public dashboards. A new line can mean first use of "
                        "an old share or a newly shared dashboard; usage insights cannot identify when "
                        "sharing was configured. The trend shows continuing exposure activity."),

        "t_anon": build.timeseries_panel(
            "Anonymous dashboard opens over time, by stack",
            [('topk(10, gcinsight_dashboards_anonymous_views{version="2",stack=~"$stack"})', "{{stack}}")],
            description="Opens with `userId=-1`. Tracked separately from the public-dashboard events "
                        "because the two fields can disagree: an unauthenticated reader is the "
                        "corroborating signal, and a stack showing anonymous opens with no public "
                        "dashboard is worth a look on its own."),

        # --- Query behaviour --------------------------------------------------------------------------
        "n_queries": build.stat_panel(
            "Panel data requests", 'sum(gcinsight_dashboards_estate_requests{version="2"})',
            description="`data-request` events emitted by panels. One request can carry several inner "
                        "queries, whose separate total is shown beside it. Distinct from dashboard opens."),
        "n_cache": build.stat_panel(
            "Cache hit rate",
            'sum(gcinsight_dashboards_estate_queries_cached{version="2"}) / '
            'sum(gcinsight_dashboards_estate_queries_total{version="2"})',
            unit="percentunit", decimals=1,
            description="Cached queries as a share of all queries, across measured stacks. A low rate "
                        "with high query volume is a cost lever: it means dashboards are re-querying "
                        "rather than being served from cache."),
        "n_errors": build.stat_panel(
            "Panel data-request errors", 'sum(gcinsight_dashboards_estate_request_errors{version="2"})',
            description="`data-request` events carrying a non-empty error - what readers actually hit "
                        "when they open a dashboard. Nothing else in this platform sees a broken panel "
                        "from the reader's side."),
        "n_panels": build.stat_panel(
            "Panels that ran a query",
            'sum(gcinsight_dashboards_estate_panels_queried{version="2"})',
            description="Distinct panels per stack that ran at least one query, summed."),
        "n_ds": build.stat_panel(
            "Datasource types queried",
            'sum(gcinsight_dashboards_estate_datasources_queried{version="2"})',
            description="Distinct datasource types queried per stack, SUMMED - so a type used on 40 "
                        "stacks counts 40 times. It is a breadth-of-integration measure per stack "
                        "aggregated, never a count of distinct types across the estate; the table "
                        "below is that count."),
        "n_qtotal": build.stat_panel(
            "Queries issued", 'sum(gcinsight_dashboards_estate_queries_total{version="2"})',
            description="`totalQueries` summed over `data-request` events - the queries inside those "
                        "requests, which is a larger number than the request count above because one "
                        "request can carry several. The denominator of the cache rate."),
        "n_qcached": build.stat_panel(
            "Queries served from cache",
            'sum(gcinsight_dashboards_estate_queries_cached{version="2"})',
            description="`cachedQueries` summed. Shown as an absolute beside the rate because the rate "
                        "alone hides scale: a low percentage of a very large number is a bigger cost "
                        "lever than a low percentage of a small one."),
        "tbl_ds": build.table_panel(
            "Datasource types actually QUERIED",
            "insights_datasource_types", ds,
            schema=insights_pillar.VIEW_SCHEMAS["insights_datasource_types"],
            description="Which datasource types panels really query, and on how many stacks. Distinct "
                        "from plugin adoption on the Consumer behaviour dashboard, which counts what is "
                        "PROVISIONED - a datasource can be provisioned everywhere and queried nowhere. "
                        "Worth scanning for competitor datasources still carrying real query volume."),
        "t_panel_queries": build.timeseries_panel(
            "Panel data requests over time, by stack",
            [('topk(10, gcinsight_dashboards_panel_queries{version="2",stack=~"$stack"})', "{{stack}}")],
            description="Data-request event load from dashboards, per stack. This is the read-side cost driver: "
                        "everything else in this platform measures what is written."),
        "t_cache": build.timeseries_panel(
            "Cache hit rate over time, worst stacks",
            [('bottomk(10, gcinsight_dashboards_cache_hit_ratio{version="2",stack=~"$stack"})', "{{stack}}")],
            unit="percentunit",
            description="`bottomk` deliberately - a LOW rate is the cost lever, so worst-first is the "
                        "actionable direction. Normally bottomk on a ratio surfaces whichever stack ran "
                        "three queries; here the collector WITHHOLDS the ratio below its query floor, so "
                        "every stack on this chart ran enough queries for the figure to mean something."),
        "t_errors": build.timeseries_panel(
            "Panel data-request errors over time, by stack",
            [('topk(10, gcinsight_dashboards_query_errors{version="2",stack=~"$stack"})', "{{stack}}")],
            description="A rising line is readers hitting panel data requests that returned an error. "
                        "One request can contain several queries, so this is not a query count. Read with "
                        "the per-stack error rate in the adoption table, which normalises for request volume."),

        # --- What people open -------------------------------------------------------------------------
        "tbl_top": build.table_panel(
            "Most-opened candidates (up to 10 retained per stack)",
            "insights_top_dashboards", ds,
            schema=insights_pillar.VIEW_SCHEMAS["insights_top_dashboards"],
            description="A bounded candidate set: each stack's own ten most-opened dashboards, then "
                        "merged and re-ranked. It is not a provable estate-wide top 50 because one stack "
                        "could own more than ten of the true leaders. Folder included "
                        "because the same dashboard name recurs across stacks and the folder is often "
                        "the only thing distinguishing them."),

        "tbl_summary": build.table_panel(
            "Every figure on this dashboard, with its caveat in the row name",
            "insights_summary", ds,
            description="The same numbers as the stat panels, with the caveats written into the metric "
                        "names rather than left in a panel description nobody opens - which population "
                        "each figure covers, that viewers are summed per stack and not deduplicated "
                        "across the org, and that the public-dashboard target is zero. Read this first "
                        "if you are about to quote a figure from this page to somebody else."),

        # --- Coverage ---------------------------------------------------------------------------------
        "tbl_coverage": build.table_panel(
            "Stacks with no figures, and why",
            "insights_coverage", ds,
            schema=insights_pillar.VIEW_SCHEMAS["insights_coverage"],
            description="The denominator. A stack awaiting its credential, one whose usage-insights "
                        "datasource is not provisioned, and one whose token is refused are three "
                        "different problems with three different fixes, so they are never collapsed "
                        "into a single 'not measured'. An empty table means full coverage."),
    }
    if opening_inventory_live:
        el["tbl_opening_inventory"] = build.table_panel(
            "Complete 31-day dashboard opening inventory",
            insights_inventory_pillar.DASHBOARD_VIEW, ds,
            schema=insights_inventory_pillar.VIEW_SCHEMAS[
                insights_inventory_pillar.DASHBOARD_VIEW
            ],
            description="The complete ownership queue: one row per configured dashboard, classified as "
                        "opened, unopened or unknown over 31 days. Unknown rows remain visible with their "
                        "coverage detail and must not be counted as unopened. Use Stack, Folder and "
                        "Dashboard uid to find the owner before retiring anything.",
        )
    if query_cost_live:
        el["tbl_datasource_query_cost"] = build.table_panel(
            "Datasource query cost and cache share",
            insights_inventory_pillar.QUERY_COST_VIEW, ds,
            schema=insights_inventory_pillar.VIEW_SCHEMAS[
                insights_inventory_pillar.QUERY_COST_VIEW
            ],
            description="Resolved datasource name, uid and type ranked by cumulative query duration, with "
                        "cache share beside it. Unavailable stacks remain as explicit unknown rows with "
                        "coverage detail rather than disappearing and making the measured total look "
                        "complete. Start with high duration and low cache share.",
        )

    query_rows = [
        build.row("Headline", ["n_queries", "n_qtotal", "n_qcached", "n_cache"],
                  max_columns=4, row_height="short"),
        build.row("Breadth and errors", ["n_panels", "n_ds", "n_errors"],
                  max_columns=3, row_height="short"),
        build.row("Datasource types", ["tbl_ds"], max_columns=1),
    ]
    if query_cost_live:
        query_rows.append(build.row(
            "Named datasource cost queue", ["tbl_datasource_query_cost"],
            max_columns=1, row_height="tall",
        ))
    query_rows.append(build.row("Trend", ["t_panel_queries", "t_cache", "t_errors"],
                                max_columns=1))

    opening_rows = []
    if opening_inventory_live:
        opening_rows.append(build.row(
            "Complete 31-day ownership queue", ["tbl_opening_inventory"],
            max_columns=1, row_height="tall",
        ))
    opening_rows.append(build.row(
        "Bounded activity leaders", ["tbl_top"],
        max_columns=1, row_height="tall",
    ))
    tabs = [
        build.rows_tab("Adoption", [
            build.row("Headline", ["n_viewed_share", "n_viewed", "n_provisioned", "n_views",
                                   "n_viewers"],
                      max_columns=5, row_height="short"),
            build.row("Coverage", ["n_measured", "n_with_views"], max_columns=2, row_height="short"),
            build.row("Trend", ["t_views", "t_viewers", "t_viewed"], max_columns=1),
            build.row("Per stack", ["tbl_usage"], max_columns=1),
            build.row("Summary, with the caveats", ["tbl_summary"], max_columns=1),
        ]),
        build.rows_tab("Public dashboards", [
            build.row("Observed exposure", ["n_public", "n_with_public", "n_public_events", "n_anon"],
                      max_columns=4, row_height="short"),
            build.row("Which ones", ["tbl_public"], max_columns=1),
            build.row("Trend", ["t_public", "t_anon"], max_columns=1),
        ]),
        build.rows_tab("Query behaviour", query_rows),
        build.rows_tab("What people open", opening_rows),
        build.tab("Coverage", ["tbl_coverage"], max_columns=1),
    ]
    return "gcinsight-dashboards", "Grafana Cloud Org Insights - Dashboard usage", \
        ("Pillar J: what people actually OPEN, from each stack's own usage-insights datasource. Every "
         "other pillar measures what exists; this measures what is used. Public-dashboard figures are "
         "observed activity, not configured inventory; the complete inventory is on Risk. "
         "Figures cover a rolling window and are summed over the stacks that could be measured - the "
         "Coverage tab is the denominator."), el, tabs


def d_coverage(ds: str):
    """Pillar K - the observed-estate asset register and the coverage depth it carries."""
    stack = '{stack=~"$stack"}'
    service_signal = "gcinsight_coverage_services_by_signal"
    el = {
        # The first screen deliberately mixes the best existing live object counters with the bounded
        # collector counts that do not exist in grafanacloud-usage. Panel descriptions state which is
        # which; neither source is copied into the other merely to make the layout uniform.
        "n_measured": build.stat_panel(
            "Stacks measured atomically", "gcinsight_coverage_stacks_measured",
            description="Stacks whose explicitly-windowed reads succeeded across every signal. A failed "
                        "stack is absent from every register and count rather than written as zero."),
        "n_services": build.stat_panel(
            "Application service assets", f"sum(gcinsight_coverage_stack_services{stack})",
            description="The application population from canonical service identities discovered "
                        "across metrics, logs, traces and profiles. Platform probes and infrastructure "
                        "units remain counted separately rather than inflating this headline."),
        "n_technologies": build.stat_panel(
            "Observed technology deployments", f"sum(gcinsight_coverage_stack_technologies{stack})",
            description="Versioned registry matches summed across the selected stacks. This is an "
                        "affirmative deployment count; the named technology register is below."),
        "n_clusters": build.stat_panel(
            "Observed clusters", f"sum(gcinsight_coverage_stack_clusters{stack})",
            description="Distinct, explicitly-windowed Mimir cluster identities across the selected "
                        "stacks. Cluster names stay in S3 and never become metric labels."),
        "n_hosts": build.stat_panel(
            "Hosts monitored", HOSTS_MONITORED, ds_uid=build.USAGE_UID,
            description="Live from the usage datasource and derived from the one-series-per-host "
                        "inventory metric. This panel remains estate-wide when Stack is selected."),
        "n_pods": build.stat_panel(
            "Kubernetes pods monitored", PODS_MONITORED, ds_uid=build.USAGE_UID,
            description="Live from the usage datasource and derived from the one-series-per-pod "
                        "inventory metric. This panel remains estate-wide when Stack is selected."),
        "n_containers": build.stat_panel(
            "Containers monitored",
            "sum(grafanacloud_instance_active_kube_pod_container_info_series)",
            ds_uid=build.USAGE_UID,
            description="Live container inventory already present in grafanacloud-usage. It is not "
                        "copied through the collector and remains estate-wide under Stack selection."),
        "n_log_streams": build.stat_panel(
            "Active log streams", "sum(grafanacloud_logs_instance_active_streams)",
            ds_uid=build.USAGE_UID,
            description="Live active-stream inventory from grafanacloud-usage. It is a current object "
                        "count, not the number of named services discovered from Loki labels."),
        "n_traced_services": build.stat_panel(
            "Services observed in traces", f'{service_signal}{{kind="traces"}}',
            description="Canonical resource.service.name identities returned by the explicitly-windowed "
                        "Tempo inventory. Names remain in the S3 register."),
        "n_profiled_services": build.stat_panel(
            "Services observed in profiles", f'{service_signal}{{kind="profiles"}}',
            description="Canonical service_name identities returned by the explicitly-windowed "
                        "Pyroscope inventory. A successful empty result remains a measured absence."),
        "n_integrations": build.stat_panel(
            "Grafana Integrations observed",
            "count(sum by(integration)(grafanacloud_instance_active_integration_series) > 0)",
            ds_uid=build.USAGE_UID,
            description="Distinct live integration label values with active series. The vocabulary is "
                        "discovered from the datasource rather than maintained in this dashboard."),
        "t_live_assets": build.timeseries_panel(
            "Live infrastructure footprint over time",
            [(HOSTS_MONITORED, "hosts"), (PODS_MONITORED, "pods"),
             ("sum(grafanacloud_instance_active_kube_pod_container_info_series)", "containers"),
             ("sum(grafanacloud_logs_instance_active_streams)", "log streams")],
            ds_uid=build.USAGE_UID,
            description="Live datasource-native infrastructure counters. Populations stay separate; "
                        "the lines are not added into a synthetic estate total."),

        # Coverage depth is the reframe: the same distribution reads as both protected surface and room
        # to deepen observation. Keep it full-width and ahead of every classification detail.
        "b_depth": build.barchart_panel(
            "Telemetry depth per named service - observed strength and room to deepen",
            "gcinsight_coverage_services_by_depth", legend="{{kind}} signals", sort=None,
            description="Application services grouped by how many canonical signals carry the exact "
                        "identity. Greater depth means more ways to investigate the service; shallower "
                        "depth is the adjacent upside without recasting the asset itself as a gap."),
        "n_completeness_mean": build.stat_panel(
            "Mean service observability completeness",
            f'gcinsight_coverage_service_completeness_mean{{version="{observability_score.VERSION}"}}',
            unit="percent", decimals=1,
            description="Mean over non-ephemeral service rows with at least four applicable components. "
                        "Read it only with the mean denominator beside it: a smaller applicable rubric "
                        "can raise this number without any new coverage."),
        "n_applicable_mean": build.stat_panel(
            "Mean applicable components per scored service",
            f'gcinsight_coverage_service_applicable_components_mean'
            f'{{version="{observability_score.VERSION}"}}',
            decimals=2,
            description="The population-matched denominator for mean completeness. Profiles, SLO, "
                        "alerting or dashboard evidence is excluded only for the explicit bounded "
                        "reasons in the panel below."),
        "b_unscored": build.barchart_panel(
            "Services unscored where a component cannot be evaluated",
            "gcinsight_coverage_unscored > 0", legend="{{component}} · {{reason}}", sort="desc",
            description="Counts the service-component decisions behind the score denominator. The row "
                        "entry counts visible machine-generated identities excluded from aggregates; "
                        "the other entries state which product or evidence absence made a component "
                        "inapplicable instead of failed."),
        "b_signal": build.barchart_panel(
            "Application services observed by signal", service_signal, legend="{{kind}}", sort=None,
            description="Application service identities present in each explicitly-windowed signal "
                        "inventory. A service may appear in several bars, which is the coverage depth."),
        "b_population": build.barchart_panel(
            "Discovered identity populations",
            "gcinsight_coverage_service_population", legend="{{kind}}", sort="desc",
            description="Every canonical identity is counted once as application, platform or "
                        "infrastructure_unit. Non-application identities remain visible so a classifier "
                        "or probe-naming change cannot silently shrink the coverage denominator."),
        "b_adoption_gap": build.barchart_panel(
            "Stacks with no measured capability use",
            "gcinsight_coverage_capability_gap", legend="{{kind}}", sort="desc",
            description="Each bar states how many stacks in that capability's explicit population "
                        "show no use. A measured zero is deliberately published here because closing "
                        "the opportunity is the finding; the table beside it states every denominator."),
        "b_technology": build.barchart_panel(
            "Observed technologies ranked by measured stacks",
            "topk(20, gcinsight_coverage_technology_stacks > 0)", legend="{{kind}}", limit=20,
            description="Bounded technology-registry entries ranked by the stacks where a sentinel "
                        "metric was observed. This is registry reach; the named evidence remains in S3."),
        "b_technology_presence": build.barchart_panel(
            "Stacks by technologies detected",
            "gcinsight_coverage_stacks_by_technology_count", legend="{{kind}} technologies", sort=None,
            description="A bounded distribution over the measured-stack population. The registry is a "
                        "presence detector, so its denominator is stacks rather than every metric name."),
        "n_no_technology": build.stat_panel(
            "Stacks with no technology detected",
            'gcinsight_coverage_stacks_by_technology_count{kind="0"}',
            description="The actionable registry gap: measured stacks where no versioned sentinel was "
                        "observed in the explicit signal-inventory window."),
        "n_legacy": build.stat_panel(
            "Service identities present only in legacy Mimir service",
            'gcinsight_coverage_service_identity{kind="legacy_only"} / '
            'scalar(sum(gcinsight_coverage_service_identity'
            '{kind=~"canonical|legacy_only"}))',
            unit="percentunit", decimals=1,
            description="Legacy-only identities divided by canonical plus legacy-only identities. The "
                        "generic service label is reported separately and never promoted silently."),
        "n_metric_backlog": build.stat_panel(
            "Unmatched metric names in the registry backlog",
            'gcinsight_coverage_metric_names{kind="unmatched"}',
            description="A development work-queue count, not a coverage share or confidence score. "
                        "The table below names the evidence that needs registry review."),
        "b_identity": build.barchart_panel(
            "Canonical and legacy service identity populations",
            "gcinsight_coverage_service_identity", legend="{{kind}}", sort="desc",
            description="Canonical, legacy-only and overlapping identity counts. Showing every enum "
                        "keeps both the classified population and its unmatched legacy share visible."),
        "b_stack_services": build.barchart_panel(
            "Named service assets by stack",
            f"topk(20, gcinsight_coverage_stack_services{stack})", legend="{{stack}}", limit=20,
            description="Selected stacks ranked by their full canonical service count. The S3 register "
                        "is bounded for legibility; this metric is calculated before that table bound."),
        "b_stack_technologies": build.barchart_panel(
            "Technology deployments by stack",
            f"topk(20, gcinsight_coverage_stack_technologies{stack})", legend="{{stack}}", limit=20,
            description="Selected stacks ranked by the number of versioned registry technologies "
                        "present. Technology names remain in the register below."),
        "b_stack_clusters": build.barchart_panel(
            "Observed clusters by stack",
            f"topk(20, gcinsight_coverage_stack_clusters{stack})", legend="{{stack}}", limit=20,
            description="Selected stacks ranked by distinct explicitly-windowed cluster identities. "
                        "The named cluster register is the exact drill-down."),
        "b_oncall": build.barchart_panel(
            "Live OnCall service and owning-team catalogue",
            f"topk(20, sum by(service_name, team)({GROUPS}))",
            legend="{{service_name}} · {{team}}", ds_uid=build.USAGE_UID, limit=20,
            description="A separate live catalogue from grafanacloud-usage. Identity-bearing label "
                        "values stay live and are never copied into collector output. Unattributed "
                        "service and team values remain visible as the unmatched share."),

        "tbl_adoption": build.table_panel(
            "Capability populations, current use and opportunity",
            coverage_pillar.ADOPTION_VIEW, ds,
            schema=coverage_pillar.VIEW_SCHEMAS[coverage_pillar.ADOPTION_VIEW],
            description="One row per capability with its population basis, measured use, opportunity "
                        "count and a specific next step. Provisioned and population-eligible do not "
                        "mean entitled, paid for or wasted."),
        "tbl_adoption_targets": build.table_panel(
            "Named capability enablement call list",
            coverage_pillar.ADOPTION_TARGET_VIEW, ds,
            schema=coverage_pillar.VIEW_SCHEMAS[coverage_pillar.ADOPTION_TARGET_VIEW],
            description="Stacks showing no use inside the stated capability population, ranked by "
                        "active series so the largest existing telemetry footprints lead the queue."),

        "tbl_datasource_provisioned": build.table_panel(
            "Third-party datasource types PROVISIONED",
            "usage_plugin_adoption", ds,
            schema=usage_pillar.VIEW_SCHEMAS["usage_plugin_adoption"],
            description="Point-in-time control-plane inventory, ranked by stacks carrying each type. "
                        "The auto-provisioned grafana-knowledgegraph-datasource is excluded because it "
                        "is not an adoption decision. This states configuration, not use."),
        "tbl_datasource_queried": build.table_panel(
            "Datasource types actually QUERIED in 24 hours",
            "insights_datasource_types", ds,
            schema=insights_pillar.VIEW_SCHEMAS["insights_datasource_types"],
            description="Pillar J usage-insights evidence from measured stacks only. This states real "
                        "panel demand in its explicit 24-hour window, not what is merely provisioned; "
                        "its freshness and coverage denominator are shown above."),
        "tbl_datasource_inventory": build.table_panel(
            "Named stack-to-datasource inventory",
            "usage_datasource_inventory", ds,
            schema=usage_pillar.VIEW_SCHEMAS["usage_datasource_inventory"],
            description="The call list behind the provisioned ranking: one row per live stack and "
                        "third-party datasource type, with its instance count. Fundable next step: "
                        "commission a datasource consolidation assessment for the highest-reach vendor "
                        "type, then use this register to scope the stack owners and Pillar J to confirm "
                        "current demand."),

        "tbl_services": build.table_panel(
            "Named service observability completeness register", coverage_pillar.SERVICE_VIEW, ds,
            schema=coverage_pillar.VIEW_SCHEMAS[coverage_pillar.SERVICE_VIEW],
            description="The primary asset register: seven configurable weighted components plus the "
                        "named population, applicable denominator and explicit unscored reasons. "
                        "Metrics, logs and traces "
                        "always remain applicable; unused products and unavailable evidence do not "
                        "become failed coverage. Active direct routing stays separate because it must "
                        "not double-weight alerting. Rows are bounded per stack for legibility."),

        # What observation has done. Every ratio over the alert-group counter is restricted to stacks
        # that report the response-time histogram; otherwise its numerator and denominator are different
        # populations. A missing timing observation means no acknowledgement was recorded, not that no
        # human looked.
        "n_value_groups": build.stat_panel(
            "Alert groups on timing-reporting stacks", f"sum{GROUPS_ON_TIMING_STACKS}",
            ds_uid=build.USAGE_UID,
            description="OnCall alert groups restricted to stacks that also report acknowledgement "
                        "timing. This is the denominator for every response ratio on this tab."),
        "n_value_acknowledged": build.stat_panel(
            "Acknowledgements recorded", ENGAGED, ds_uid=build.USAGE_UID,
            description="Response-time observations recorded by OnCall. A missing observation means no "
                        "acknowledgement was recorded; it does not prove nobody looked."),
        "n_value_engagement": build.stat_panel(
            "Alert groups with a recorded acknowledgement", ENGAGEMENT_RATE,
            unit="percentunit", decimals=1, ds_uid=build.USAGE_UID,
            description="Acknowledgement observations divided only by alert groups on timing-reporting "
                        "stacks. The explicit population restriction prevents a cross-estate ratio."),
        "n_value_mtta": build.stat_panel(
            "Median time to acknowledge", MTTA_MEDIAN, unit="s", decimals=1,
            ds_uid=build.USAGE_UID,
            description="p50 only. Higher quantiles saturate at the histogram's top finite bucket and "
                        "would turn 'at least an hour' into a false exact duration."),
        "n_value_mttr": build.stat_panel(
            "Median time to resolve", MTTR_MEDIAN, unit="s", decimals=1,
            ds_uid=build.USAGE_UID,
            description="p50 only, for the same finite-bucket reason as acknowledgement time."),
        "n_value_tail": build.stat_panel(
            "Acknowledgements recorded after the top finite bucket", ACK_TAIL,
            ds_uid=build.USAGE_UID,
            description=f"Count above the histogram's `{TOP_BUCKET}` second finite bucket. A count is "
                        "honest here; p90 and p99 would both saturate at the bucket boundary."),
        "n_value_unowned_team": build.stat_panel(
            "Timing-stack alert groups with no owning team", UNOWNED_SHARE_ALL,
            unit="percentunit", decimals=1, ds_uid=build.USAGE_UID,
            description="Share labelled `team=\"No team\"` within the timing-reporting stack population."),
        "n_value_unowned_service": build.stat_panel(
            "Timing-stack alert groups with no service attribution", UNOWNED_SERVICE_SHARE,
            unit="percentunit", decimals=1, ds_uid=build.USAGE_UID,
            description="Share labelled `service_name=\"No service\"` within the same timing-reporting "
                        "stack population as the team share."),

        # Unit economics use Grafana's own published currency series. No custom rate card participates
        # in these panels; the card remains only for currency derived from a non-currency quantity.
        "n_spend_app_service": build.stat_panel(
            "Application Observability run rate per observed App O11y service",
            "sum(grafanacloud_org_app_o11y_overage) / "
            "sum(grafanacloud_app_observability_service_entity_count)",
            unit="currencyUSD", decimals=2, ds_uid=build.USAGE_UID,
            description="Application Observability's published monthly overage divided by its own "
                        "published observed-service population. This is product-specific, not total spend."),
        "n_spend_infra_host_hour": build.stat_panel(
            "Infrastructure Observability run rate per billable host-hour",
            "sum(grafanacloud_org_infra_o11y_host_overage) / "
            "sum(grafanacloud_org_infra_o11y_billable_host_hours)",
            unit="currencyUSD", decimals=4, ds_uid=build.USAGE_UID,
            description="Infrastructure host overage divided by the matching published billable "
                        "host-hours. Both numerator and denominator are Grafana billing metrics."),
        "n_spend_infra_container_hour": build.stat_panel(
            "Infrastructure Observability run rate per billable container-hour",
            "sum(grafanacloud_org_infra_o11y_container_overage) / "
            "sum(grafanacloud_org_infra_o11y_billable_container_hours)",
            unit="currencyUSD", decimals=4, ds_uid=build.USAGE_UID,
            description="Infrastructure container overage divided by the matching published billable "
                        "container-hours. This is not a recomputed rate card."),
        "n_spend_ack": build.stat_panel(
            "Current monthly run rate per acknowledgement recorded", f"{RUN_RATE} / {ENGAGED}",
            unit="currencyUSD", decimals=2, ds_uid=build.USAGE_UID,
            description="Grafana-published total monthly run rate divided by response-time observations "
                        "from the timing-reporting population. It is a flipped denominator, not a claim "
                        "that every charge exists to handle OnCall pages."),
        "n_spend_service": build.cross_source_ratio_stat_panel(
            "Current monthly run rate per named observed service",
            (RUN_RATE, build.USAGE_UID),
            ("sum(gcinsight_coverage_stack_services)", build.PROM_UID),
            unit="currencyUSD", decimals=2,
            description="Grafana-published total monthly run rate divided by the atomic four-signal "
                        "canonical service population. Grafana server-side expressions combine the two "
                        "datasources; neither series is copied. No value is shown when the denominator "
                        "is unavailable."),
        "n_spend_billed_user": build.cross_source_ratio_stat_panel(
            "Current monthly run rate per billed user",
            (RUN_RATE, build.USAGE_UID), ("gcinsight_cost_billed_users", build.PROM_UID),
            unit="currencyUSD", decimals=2,
            description="Total published monthly run rate divided by billingActiveUsers. Active users "
                        "are an adoption figure and are deliberately excluded from this money panel."),
        "n_spend_viewer": build.cross_source_ratio_stat_panel(
            "Current monthly run rate per distinct dashboard viewer observed in 24h",
            (RUN_RATE, build.USAGE_UID),
            ("sum(gcinsight_dashboards_viewers)", build.PROM_UID),
            unit="currencyUSD", decimals=2,
            description="Total published monthly run rate divided by Pillar J's distinct-viewer counts "
                        "summed per stack over its explicit 24-hour window. A person using several stacks "
                        "can appear several times, so this is not an org-wide unique-human count."),
        "tbl_technologies": build.table_panel(
            "Observed technology register", coverage_pillar.TECHNOLOGY_VIEW, ds,
            schema=coverage_pillar.VIEW_SCHEMAS[coverage_pillar.TECHNOLOGY_VIEW],
            description="Named versioned-registry matches and their sentinel evidence count by stack."),
        "tbl_clusters": build.table_panel(
            "Observed cluster register", coverage_pillar.CLUSTER_VIEW, ds,
            schema=coverage_pillar.VIEW_SCHEMAS[coverage_pillar.CLUSTER_VIEW],
            description="Named clusters from explicitly-windowed Mimir label inventory. Names are "
                        "available here for action and excluded from metric labels."),
        "tbl_metrics": build.table_panel(
            "Metric-name classification register", coverage_pillar.METRIC_VIEW, ds,
            schema=coverage_pillar.VIEW_SCHEMAS[coverage_pillar.METRIC_VIEW],
            description="The metric-name evidence behind the technology registry, including every "
                        "unmatched name and its count. Unmatched names are the registry-development "
                        "backlog, not a share of technology coverage."),
        "tbl_legacy": build.table_panel(
            "Legacy Mimir service register", coverage_pillar.LEGACY_SERVICE_VIEW, ds,
            schema=coverage_pillar.VIEW_SCHEMAS[coverage_pillar.LEGACY_SERVICE_VIEW],
            description="Generic Mimir service values reported without silently treating them as "
                        "canonical service_name identities."),
        "tbl_summary": build.table_panel(
            "Coverage summary and registry version", coverage_pillar.SUMMARY_VIEW, ds,
            schema=coverage_pillar.VIEW_SCHEMAS[coverage_pillar.SUMMARY_VIEW],
            description="Per-stack denominators, retained-row count, unmatched-name backlog and the "
                        "exact technology registry version used for this publication."),
    }
    tabs = [
        build.rows_tab("Observed estate", [
            build.row("Measured register", ["n_measured", "n_services", "n_technologies", "n_clusters"],
                      max_columns=4, row_height="short"),
            build.row("Infrastructure already observed", ["n_hosts", "n_pods", "n_containers",
                                                         "n_log_streams"],
                      max_columns=4, row_height="short"),
            build.row("Signals and integrations", ["n_traced_services", "n_profiled_services",
                                                     "n_integrations"],
                      max_columns=3, row_height="short"),
            build.row("Direction of travel", ["t_live_assets"], max_columns=1),
        ]),
        build.rows_tab("Coverage depth", [
            build.row("Score and its denominator", ["n_completeness_mean", "n_applicable_mean"],
                      max_columns=2, row_height="short"),
            build.row("Why components are not scored", ["b_unscored"], max_columns=1),
            build.row("Identity populations", ["b_population"], max_columns=1),
            build.row("Coverage depth per service", ["b_depth"], max_columns=1, row_height="tall"),
            build.row("Services by signal", ["b_signal"], max_columns=1),
            build.row("Technology presence", ["b_technology_presence", "n_no_technology",
                                                "b_technology"], max_columns=3),
            build.row("Identity evidence", ["n_legacy", "b_identity"], max_columns=2),
            build.row("Where the assets sit", ["b_stack_services", "b_stack_technologies",
                                                "b_stack_clusters"], max_columns=3),
        ]),
        build.rows_tab("Adoption opportunities", [
            build.row("Opportunity counts", ["b_adoption_gap"], max_columns=1),
            build.row("Population and fundable next step", ["tbl_adoption"], max_columns=1),
            build.row("Named call list, largest telemetry footprint first",
                      ["tbl_adoption_targets"], max_columns=1, row_height="tall"),
        ]),
        build.rows_tab("Adjacent datasource estate", [
            build.row("Provisioned configuration versus measured use",
                      ["tbl_datasource_provisioned", "tbl_datasource_queried"], max_columns=2),
            build.row("Named consolidation call list", ["tbl_datasource_inventory"],
                      max_columns=1, row_height="tall"),
        ]),
        build.rows_tab("Outcome value", [
            build.row("Recorded response", ["n_value_groups", "n_value_acknowledged",
                                              "n_value_engagement"],
                      max_columns=3, row_height="short"),
            build.row("Time returned to people", ["n_value_mtta", "n_value_mttr", "n_value_tail"],
                      max_columns=3, row_height="short"),
            build.row("Ownership completeness", ["n_value_unowned_team",
                                                   "n_value_unowned_service"],
                      max_columns=2, row_height="short"),
        ]),
        build.rows_tab("Unit economics", [
            build.row("Observation products", ["n_spend_app_service", "n_spend_infra_host_hour",
                                                 "n_spend_infra_container_hour"],
                      max_columns=3, row_height="short"),
            build.row("Value denominators", ["n_spend_service", "n_spend_ack",
                                               "n_spend_billed_user", "n_spend_viewer"],
                      max_columns=4, row_height="short"),
        ]),
        build.rows_tab("Named service register", [
            build.row("Coverage register", ["tbl_services"], max_columns=1, row_height="tall"),
            build.row("Live OnCall ownership", ["b_oncall"], max_columns=1),
        ]),
        build.rows_tab("Technology and cluster registers", [
            build.row("Technologies", ["tbl_technologies"], max_columns=1),
            build.row("Clusters", ["tbl_clusters"], max_columns=1),
        ]),
        build.rows_tab("Classification evidence", [
            build.row("Registry-development backlog", ["n_metric_backlog"], max_columns=1,
                      row_height="short"),
            build.row("Metric names", ["tbl_metrics"], max_columns=1, row_height="tall"),
            build.row("Legacy service identity", ["tbl_legacy"], max_columns=1),
        ]),
        build.tab("Summary", ["tbl_summary"], max_columns=1, row_height="tall"),
    ]
    return "gcinsight-coverage", "Grafana Cloud Org Insights - Coverage", \
        ("Pillar K: the affirmative observed-estate asset register, how deeply each named service is "
         "covered, the explicit ownership and response relationships attached to it, and the adjacent "
         "surface where observation can carry more value."), el, tabs


def d_commercial(ds: str):
    """Pillar H - the commitment and the run rate. Live from `grafanacloud-usage`, no collector.

    Separate dashboard on purpose: commercial figures are one link that can stay closed.

    **Every money panel is labelled USD/month and says the unit is DERIVED**, because the datasource
    declares no currency. The derivation is an identity the metrics satisfy: balance / total_overage =
    36.55 against an independent forecast_months_remaining of 36.64. If those two ever disagree, the unit
    assumption has broken and every figure here needs re-deriving before it is quoted.

    **The burn tab states no conclusion, deliberately.** Do not add a projection or an underspend note to
    a panel description - that analysis belongs in a deployment-specific review, not in the dashboard.
    """
    el = {
        # --- Commitment -------------------------------------------------------------------------------
        "n_commit": build.stat_panel(
            "Spend commitment (USD, total term)", COMMIT_TOTAL, unit="currencyUSD", decimals=2,
            ds_uid=build.USAGE_UID,
            description="`grafanacloud_org_spend_commit_credit_total` - the whole 36-month commitment, "
                        "not a monthly figure. TWO DECIMALS ON PURPOSE: at zero decimals Grafana "
                        "abbreviates this to $3M and abbreviates the remaining balance to $3M as well, so "
                        "the two most consequential numbers on the page rendered identically and the "
                        "several-hundred-thousand difference between them was invisible. "
                        "CURRENCY IS DERIVED, NOT DECLARED - the datasource states no unit; USD is "
                        "inferred from the balance-over-run-rate identity matching the platform's own "
                        "forecast to 0.3%. Confirm against the contract before quoting externally."),
        "n_consumed": build.stat_panel(
            "Commitment consumed (USD)", COMMIT_CONSUMED, unit="currencyUSD", decimals=2,
            ds_uid=build.USAGE_UID,
            description="Credit minus balance - drawn down since the term began, not a monthly figure. "
                        "Same derived-currency caveat as the panel beside it."),
        "n_consumed_share": build.stat_panel(
            "Share of commitment consumed", COMMIT_CONSUMED_SHARE, unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="Credit drawn down as a share of the total commitment. Currency-independent, so "
                        "this is the safest figure on the dashboard to quote - a ratio needs no unit, and "
                        "so needs none of the derived-currency caveat the money panels carry."),
        "n_balance": build.stat_panel(
            "Commitment remaining (USD)", COMMIT_BALANCE, unit="currencyUSD", decimals=2,
            ds_uid=build.USAGE_UID,
            description="Credit not yet drawn down, over the whole term. Two decimals for the same reason "
                        "as the commitment panel: abbreviated to $3M it was indistinguishable from the "
                        "total. Derived currency, as above."),
        "n_term_elapsed": build.stat_panel(
            "Share of contract term elapsed", TERM_ELAPSED_SHARE, unit="percentunit", decimals=1,
            ds_uid=build.USAGE_UID,
            description="Computed from `grafanacloud_org_contract_start_date` and `..._end_date`: "
                        "2026-02-01 to 2029-01-31, a 36-month term. Also currency-independent. Read "
                        "against the consumed share beside it - the two together are the burn picture, "
                        "and the chart on the Consumption vs term tab plots both over time."),
        "n_months_metric": build.stat_panel(
            "Months the commitment lasts at current run rate", FORECAST_MONTHS, decimals=1,
            ds_uid=build.USAGE_UID,
            description="`grafanacloud_org_forecast_months_remaining`, read straight from the platform "
                        "rather than computed here. This is NOT months left "
                        "on the contract - that is the panel beside it - it is how long the remaining "
                        "balance lasts at the present rate of spend. The two answer different questions "
                        "and confusing them is the easiest mistake on this page."),
        "n_months_contract": build.stat_panel(
            "Months remaining on the contract", MONTHS_TO_END, decimals=1, ds_uid=build.USAGE_UID,
            description="Computed live from the contract end date, 2029-01-31 - how long the TERM runs. "
                        "The panel beside it measures the commitment rather than the term: how long the "
                        "remaining balance lasts at the present rate of spend. The two answer different "
                        "questions and confusing them is the easiest mistake on this page."),

        # --- Run rate ---------------------------------------------------------------------------------
        "n_runrate": build.stat_panel(
            "Current run rate (USD/month)", RUN_RATE, unit="currencyUSD", decimals=2,
            ds_uid=build.USAGE_UID,
            description="`grafanacloud_org_total_overage`, per MONTH. BOTH THE CURRENCY AND THE PERIOD "
                        "ARE DERIVED, not declared by the datasource - the period is in the title because a "
                        "bare currency figure with no period is unquotable. "
                        "Note the metric name is misleading here - `_included_*` volumes are all ZERO on "
                        "this contract, so there is no bundled allowance and 'overage' is the WHOLE "
                        "charge for the period, not spend above a plan. Do not present it as excess."),
        "b_runrate": build.barchart_panel(
            "Run rate by product",
            f"sort_desc(label_replace(sum({PRODUCT_OVERAGES[0][0]}), \"product\", \"metrics\", \"\", \"\"))",
            legend="{{product}}", ds_uid=build.USAGE_UID,
            description="placeholder - replaced below"),
        # The guard that keeps the breakdown honest. A component chart the reader cannot reconcile to the
        # total is an invitation to trust it, and the six-component version was wrong by 24% for exactly
        # that reason: nothing on the page would have shown the discrepancy.
        "n_reconcile": build.stat_panel(
            "Unaccounted run rate (USD/month)", RECONCILIATION_GAP, unit="currencyUSD", decimals=2,
            ds_uid=build.USAGE_UID,
            description="`total_overage` minus the sum of every component in the breakdown beside this. "
                        "Same DERIVED currency and period as every money panel here. "
                        f"MUST BE ZERO across all {len(PRODUCT_OVERAGES)} enumerated components. "
                        "Anything else means Grafana Cloud has introduced a billing line the "
                        "breakdown does not carry, so the product chart is understating the run rate and "
                        "the new metric needs adding to PRODUCT_OVERAGES. This panel exists because a "
                        "plausible component chart has previously omitted live billing lines."),
        "t_runrate": build.timeseries_panel(
            "Run rate by product over time",
            [(f"sum({metric})", label) for metric, label in PRODUCT_OVERAGES],
            unit="currencyUSD", stacked=True, ds_uid=build.USAGE_UID,
            description="Stacked over every billing line, so the top edge IS the total run rate and "
                        "the reconciliation panel above proves it. Metrics is the largest single line by "
                        "a wide margin, which is the whole reason the Cost dashboard's Adaptive Metrics "
                        "tab matters: the biggest cost line is the one with millions of series of "
                        "identified, unapplied savings sitting against it. The current split is on the bar "
                        "chart above rather than repeated here, so it cannot go stale in two places. "
                        "USD/month, DERIVED unit."),
        "t_metrics_share": build.timeseries_panel(
            "Metrics share of run rate",
            [(f"sum(grafanacloud_org_metrics_overage) / {RUN_RATE}", "metrics share")],
            unit="percentunit", ds_uid=build.USAGE_UID,
            description="Metrics overage as a share of total overage. Currency-independent, so this is "
                        "safe to quote without the derived-unit caveat. If Adaptive Metrics adoption "
                        "moves, this is the line it shows up on - and it is the single most direct measure "
                        "of whether the cost work is landing."),

        # --- Consumption vs term ----------------------------------------------------------------------
        "t_burn": build.timeseries_panel(
            "Commitment consumed vs contract term elapsed",
            [(COMMIT_CONSUMED_SHARE, "commitment consumed"),
             (TERM_ELAPSED_SHARE, "contract term elapsed")],
            unit="percentunit", ds_uid=build.USAGE_UID,
            description="Two ratios on one axis, both currency-independent. `commitment consumed` is "
                        "1 - balance/credit; `contract term elapsed` is derived from the contract start "
                        "and end dates. "
                        "The two lines are the data. Reading a trajectory off them is a commercial "
                        "conversation and is deliberately left to the person in the room, not asserted "
                        "here."),
        "t_balance": build.timeseries_panel(
            "Commitment remaining", [(COMMIT_BALANCE, "balance")],
            unit="currencyUSD", ds_uid=build.USAGE_UID,
            description="The absolute drawdown against the commitment. Derived currency, as above."),
    }
    # The bar chart needs one series per product with a readable label, which `sum()` alone cannot carry -
    # each overage metric is a separate name, so relabel each and union them.
    el["b_runrate"] = build.barchart_panel(
        "Run rate by product (USD/month)",
        " or ".join(
            f'label_replace(sum({metric}), "product", "{label}", "", "")'
            for metric, label in PRODUCT_OVERAGES),
        legend="{{product}}", ds_uid=build.USAGE_UID, unit="currencyUSD",
        description="The COMPLETE decomposition of the run rate - all "
                    f"{len(PRODUCT_OVERAGES)} billing lines, biggest first, verified to sum exactly to "
                    "`grafanacloud_org_total_overage` with a remainder of zero. The panel beside this one "
                    "shows that remainder live, so if Grafana Cloud adds a billing line the gap appears "
                    "here rather than being absorbed silently. "
                    "The chart previously omitted billing lines while still looking complete; the live "
                    "reconciliation remainder is what prevents that recurring. Lines reading zero are "
                    "real zeros, not gaps: each "
                    "has a reporting series and simply carries no charge. "
                    "USD/month, DERIVED unit. Each product is a separately-named metric rather than one "
                    "metric with a `product` label, so each is relabelled and unioned with `or` - that is "
                    "why this expression is shaped the way it is.")
    tabs = [
        build.tab("Commitment", ["n_commit", "n_consumed", "n_consumed_share", "n_balance",
                                 "n_term_elapsed", "n_months_metric", "n_months_contract"]),
        build.tab("Run rate", ["n_runrate", "n_reconcile", "b_runrate", "t_runrate",
                               "t_metrics_share"]),
        build.tab("Consumption vs term", ["t_burn", "t_balance"]),
    ]
    return "gcinsight-commercial", "Grafana Cloud Org Insights - Commercial", \
        ("Pillar H: the spend commitment and the run rate behind it. Live from grafanacloud-usage. "
         "CURRENCY AND PERIOD ARE DERIVED, not declared by the datasource - every money panel says so, "
         "and the ratio panels are unit-free and safer to quote. Contract 2026-02-01 to 2029-01-31."), \
        el, tabs


def d_ai(ds: str):
    """Pillar I - Assistant adoption, AI-token consumption and commercial exposure.

    The org-wide panels here come from `grafanacloud-usage`, which needs no credential. Since 2026-08-20
    that is no longer the ONLY source: a per-stack read-only reader exists on 269 stacks (PLAN 17D) and
    unlocks tenant Assistant inventory and a category x surface breakdown that the billing metrics do not
    carry at all. The two must never be presented as one measure - their windows differ (obs-hub, same
    day: plugin 30-day 14,677,233 tokens vs billing current-period 8,610,789).

    Two superficially similar token metrics have different windows and are kept apart throughout:

    * `ai_tokens_total_tokens` is the current billing-period aggregate and resets monthly.
    * `ai_tokens_user_total_tokens` is cumulative by identity and does not share that reset contract.
    """
    assistant_users = "sum(grafanacloud_org_assistant_users)"
    active_stacks = "count(sum by(stack_id)(grafanacloud_assistant_active_users) > 0)"
    token_users = 'sum(grafanacloud_org_ai_tokens_active_users{user_type="user"})'
    tokens = "sum(grafanacloud_ai_tokens_total_tokens)"
    token_stacks = "count(sum by(stack_id)(grafanacloud_ai_tokens_total_tokens) > 0)"
    assistant_cost = "sum(grafanacloud_org_assistant_overage)"
    token_cost = "sum(grafanacloud_org_ai_tokens_overage)"

    stack_users = build.usage_by_slug(
        "topk(100, sum by(stack_id)(grafanacloud_assistant_active_users))")
    stack_tokens = build.usage_by_slug(
        "topk(100, sum by(stack_id)(grafanacloud_ai_tokens_total_tokens))")
    stack_assistant_cost = build.usage_by_slug(
        "topk(100, sum by(stack_id)(grafanacloud_assistant_overage))")
    people = ('topk(100, sum by(email)(max_over_time('
              'grafanacloud_ai_tokens_user_total_tokens{user_type="user"}[120d])))')
    services = ('topk(100, sum by(email)(max_over_time('
                'grafanacloud_ai_tokens_user_total_tokens{user_type="service"}[120d])))')

    # Collector-sourced expressions - OUR series on the stack's own Prometheus, so no slug join.
    ai_measured = 'gcinsight_ai_estate_stacks{kind="measured"}'
    ai_with_usage = 'gcinsight_ai_estate_stacks{kind="with_usage"}'
    ai_with_config = 'gcinsight_ai_estate_stacks{kind="with_tenant_config"}'
    ai_messages = "gcinsight_ai_estate_messages_total"
    ai_uncategorised_share = ("gcinsight_ai_estate_messages_uncategorised / "
                              "gcinsight_ai_estate_messages_total")
    ai_est_users = "gcinsight_ai_estate_users"
    ai_est_tokens = "gcinsight_ai_estate_tokens"
    ai_combos = "gcinsight_ai_estate_category_combos"
    ai_combo_series = "gcinsight_ai_estate_messages"
    ai_by_category = "sum by(category) (gcinsight_ai_estate_messages)"
    ai_by_surface = "sum by(surface) (gcinsight_ai_estate_messages)"
    # The estate machine share, from the same series both ways round so numerator and denominator cover
    # one population. `surface!="web"` rather than a list of machine surfaces: a surface Assistant adds
    # later is machine-driven until somebody says otherwise, and the combo count makes it visible.
    ai_machine_share_estate = ('sum(gcinsight_ai_estate_messages{surface!="web"}) / '
                               "sum(gcinsight_ai_estate_messages)")
    ai_tenant_objects = "gcinsight_ai_estate_tenant_objects"
    ai_investigations = "gcinsight_ai_estate_investigations"
    ai_top_messages = "topk(50, gcinsight_ai_messages)"
    ai_top_tpu = "topk(50, gcinsight_ai_tokens_per_active_user)"
    ai_top_machine = "topk(50, gcinsight_ai_machine_share)"
    ai_provisioned = "gcinsight_stacks_provisioned"
    ai_missing = "gcinsight_stacks_missing_credential"
    ai_gap_age = "gcinsight_missing_credential_age_seconds"

    el = {
        # --- Overview -------------------------------------------------------------------------------
        "n_assistant_users": build.stat_panel(
            "Assistant users this billing month", assistant_users, ds_uid=build.USAGE_UID,
            description="The ORG-LEVEL Assistant user gauge for the current monthly billing period. "
                        "Use this for the headline rather than summing per-stack active users, which can "
                        "double-count somebody who works in more than one stack. It is not the same as "
                        "the fractional per-stack contract user-unit gauge."),
        "n_active_stacks": build.stat_panel(
            "Stacks with Assistant activity", active_stacks, ds_uid=build.USAGE_UID,
            description="Stacks whose Assistant active-user gauge is above zero in the current billing "
                        "period, after collapsing by stack_id. This is reach across the estate, not a "
                        "unique-person count; the table on Adoption by stack names the stacks."),
        "n_token_users": build.stat_panel(
            "People consuming AI tokens", token_users, ds_uid=build.USAGE_UID,
            description="Unique org-level user identities with AI-token activity in the current billing "
                        "period. Explicitly selects user_type=user, so a service identity cannot inflate "
                        "the people count."),
        "n_tokens": build.stat_panel(
            "AI tokens this billing period", tokens, ds_uid=build.USAGE_UID,
            description="Current billing-period AI tokens across every stack. The aggregate RESETS "
                        "monthly, so a drop at the billing boundary is expected and is not lost usage. "
                        "Do not compare this with the lifetime identity ranking as if their windows match."),
        "n_token_stacks": build.stat_panel(
            "Stacks consuming AI tokens", token_stacks, ds_uid=build.USAGE_UID,
            description="Stacks with a positive current-period AI-token total, after summing all "
                        "user_type series by stack_id. The Adoption by stack table names up to the top "
                        "hundred rather than hiding the long tail behind a headline."),
        "n_assistant_overage": build.stat_panel(
            "Assistant run rate (USD/month)", assistant_cost, unit="currencyUSD", decimals=2,
            ds_uid=build.USAGE_UID,
            description="`grafanacloud_org_assistant_overage`. USD/month is DERIVED, not declared by "
                        "the datasource, using the same commitment reconciliation as the Commercial "
                        "dashboard. On this spend-commit contract, overage is the whole charge for the "
                        "period - not spend above a bundled plan."),
        "n_token_overage": build.stat_panel(
            "AI-token run rate (USD/month)", token_cost, unit="currencyUSD", decimals=2,
            ds_uid=build.USAGE_UID,
            description="`grafanacloud_org_ai_tokens_overage`. USD/month is DERIVED under the same "
                        "contract identity as the Commercial dashboard. A reported zero is a real gauge "
                        "sample, not a missing series; it does not make token consumption free or prove "
                        "what entitlement the organisation bought."),

        # --- Adoption by stack ----------------------------------------------------------------------
        "tbl_stack_users": build.prometheus_table_panel(
            "Top 100 stacks by Assistant active users", stack_users, legend="{{slug}}",
            ds_uid=build.USAGE_UID, label_column="Stack", value_column="Active users",
            description="The hundred stacks with the largest current-period Assistant active-user "
                        "counts, named through the stack_id-to-slug join and sorted largest first. These "
                        "are stack memberships, not unique org users: one person can appear in several "
                        "stacks. The table scrolls and filters so the long tail remains actionable."),
        "tbl_stack_tokens": build.prometheus_table_panel(
            "Top 100 stacks by current-period AI tokens", stack_tokens, legend="{{slug}}",
            ds_uid=build.USAGE_UID, label_column="Stack", value_column="AI tokens",
            description="The hundred largest stack totals in the CURRENT billing period, largest first. "
                        "This uses the monthly-reset aggregate, not the lifetime identity counter. The "
                        "stack selector cannot filter it because grafanacloud-usage has no slug label; "
                        "slug is added only for display by joining on stack_id."),

        # --- Token consumption ----------------------------------------------------------------------
        "t_users": build.timeseries_panel(
            "Assistant and AI-token users over time",
            [(assistant_users, "Assistant user gauge - org"),
             ("sum(grafanacloud_assistant_active_users)",
              "Assistant stack-user memberships"),
             ("sum(grafanacloud_assistant_users)",
              "Assistant contract user units - stack sum"),
             ('sum(grafanacloud_ai_tokens_active_users{user_type="user"})',
              "AI-token stack-user memberships")],
            ds_uid=build.USAGE_UID,
            description="The org line is the headline. The active-user lines sum stack memberships and "
                        "can be higher because the same person may use several stacks. The contract "
                        "user-unit series is separate because its per-stack values may be fractional; "
                        "it is not a distinct-person count. All lines cover the monthly billing period."),
        "t_tokens": build.timeseries_panel(
            "Current billing-period AI tokens", [(tokens, "tokens")], ds_uid=build.USAGE_UID,
            description="Monthly-reset aggregate token consumption. The slope shows consumption within "
                        "the period; the step down at a billing boundary is an expected reset. This "
                        "dashboard defaults to thirty days so the billing-period shape is visible."),
        "n_top2_share": build.stat_panel(
            "Share of tokens from top 2 stacks",
            "sum(topk(2, sum by(stack_id)(grafanacloud_ai_tokens_total_tokens))) / " + tokens,
            unit="percentunit", decimals=1, ds_uid=build.USAGE_UID,
            description="Current-period tokens from the two largest stack totals divided by the estate "
                        "total. Numerator and denominator use the same monthly-reset population, so this "
                        "is an honest concentration ratio rather than a lifetime/current-period mix."),
        "n_top10_share": build.stat_panel(
            "Share of tokens from top 10 stacks",
            "sum(topk(10, sum by(stack_id)(grafanacloud_ai_tokens_total_tokens))) / " + tokens,
            unit="percentunit", decimals=1, ds_uid=build.USAGE_UID,
            description="Current-period tokens from the ten largest stack totals divided by the same "
                        "estate total. Read it with the top-two share to distinguish a concentrated "
                        "programme from broad adoption; the top-hundred table names the contributors."),

        # --- People and identities ------------------------------------------------------------------
        "tbl_people": build.prometheus_table_panel(
            "Top 100 people by lifetime cumulative AI tokens", people, legend="{{email}}",
            ds_uid=build.USAGE_UID, label_column="User", value_column="Lifetime AI tokens",
            description="Per-user LIFETIME CUMULATIVE token totals, deduplicated by email across stacks "
                        "and ranked by the most recent value seen within the look-back window. This is "
                        "deliberately not labelled current spend: its counter does not share the monthly "
                        "reset contract of the aggregate token panels."),
        "tbl_services": build.prometheus_table_panel(
            "Top 100 identities on service-token series - lifetime cumulative", services,
            legend="{{email}}", ds_uid=build.USAGE_UID,
            label_column="Identity on service-token series",
            value_column="Lifetime AI tokens",
            description="Identities on series labelled user_type=service, ranked by their LIFETIME "
                        "CUMULATIVE AI-token counter. This is a billing-series category, NOT proof that "
                        "the email belongs to a bot or service account: live rows include human-shaped "
                        "addresses alongside sa-* identities. Never quote it as service-account usage."),

        # --- Commercial -----------------------------------------------------------------------------
        "tbl_stack_assistant_cost": build.prometheus_table_panel(
            "Top 100 stacks by Assistant run rate (USD/month)", stack_assistant_cost,
            legend="{{slug}}", ds_uid=build.USAGE_UID, label_column="Stack",
            value_column="USD/month", unit="currencyUSD",
            description="Per-stack Assistant charge, largest first. USD/month is DERIVED and `overage` "
                        "is the whole charge under this spend-commit contract, not an amount above a "
                        "bundled allowance. This is the drill-down behind the Assistant run-rate stat."),
        "n_included_users": build.stat_panel(
            "Contract-reported included Assistant users",
            "sum(grafanacloud_org_assistant_included_users)", ds_uid=build.USAGE_UID,
            description="The included-user gauge reported by this contract. It currently has a real "
                        "series, but included gauges are not a usable adoption denominator here: this "
                        "spend-commit contract reports no bundled allowance. Zero does not mean nobody "
                        "is licensed or using Assistant."),
        "n_additional_tokens": build.stat_panel(
            "Contract-reported additional AI tokens",
            "sum(grafanacloud_org_ai_tokens_additional_tokens)", ds_uid=build.USAGE_UID,
            description="The contract-level additional-token gauge. It is shown only as a raw contract "
                        "field; do not use it as the consumption total or entitlement denominator. "
                        "Current consumption comes from the monthly token aggregate on Overview."),
        "n_included_additional_tokens": build.stat_panel(
            "Contract-reported included additional AI tokens",
            "sum(grafanacloud_org_ai_tokens_included_additional_tokens)", ds_uid=build.USAGE_UID,
            description="The contract-level included-additional-token gauge. A reported zero is not "
                        "evidence that the organisation has no AI entitlement; included gauges are unpopulated for "
                        "this spend-commit contract. It is isolated here to prevent it becoming a false "
                        "denominator elsewhere."),

        # --- Collector-sourced: per-stack Assistant reads (PLAN 17E) ---------------------------------
        #
        # These read OUR OWN metrics on `grafanacloud-prom`, not `grafanacloud-usage`, and that is the
        # performance argument for the collector path as well as the data one: `grafanacloud-usage` has no
        # `slug` label, so every panel above it pays for a 273-series `group_left` join on a shared,
        # org-wide tenant. Our series carry `stack` directly, so a ranking is a bare `topk`.
        "n_ai_measured": build.stat_panel(
            "Stacks with Assistant data collected", ai_measured,
            description="Stacks whose Assistant API answered this scan. Read it beside the two stats to "
                        "its right: this is the DENOMINATOR for both, and it is smaller than the estate "
                        "whenever a stack is paused or is still waiting for its nightly credential. The "
                        "Collection coverage tab names every stack that is missing."),
        "n_ai_with_usage": build.stat_panel(
            "Stacks with any Assistant activity", ai_with_usage,
            description="Of the stacks collected, how many had at least one Assistant message in the "
                        "30-day window. A measured zero is a real answer here - it means Assistant is "
                        "provisioned and nobody has used it - so this is reach, not licensing."),
        "n_ai_with_config": build.stat_panel(
            "Stacks with any tenant Assistant configuration", ai_with_config,
            description="Stacks carrying at least one TENANT-scoped skill, rule, automation or MCP "
                        "integration. Compare it with the activity count beside it: the gap between the "
                        "two is the enablement opportunity, and it is the largest single finding on this "
                        "dashboard. User-scoped objects are invisible to any credential and are not "
                        "counted here - see the Feature activity tab."),
        "n_ai_messages": build.stat_panel(
            "Assistant messages (30d, collected stacks)", ai_messages,
            description="User messages across every stack collected, over the plugin's rolling 30-day "
                        "window. This is NOT the billing window used by the Overview tab's token stats, "
                        "and the two must never be presented as one measure."),
        "n_ai_est_users": build.stat_panel(
            "Assistant active users (30d, collected stacks)", ai_est_users,
            description="Per-stack active-user figures from each stack's own Assistant API, SUMMED - so "
                        "somebody using Assistant on four stacks counts four times. Deliberately not "
                        "comparable with the Overview tab's org-level user gauge, which covers the "
                        "monthly BILLING period and is deduplicated by identity. Two windows and two "
                        "populations; use each for what it measures."),
        "n_ai_est_tokens": build.stat_panel(
            "Assistant tokens (30d, collected stacks)", ai_est_tokens,
            description="Tokens reported by each stack's own Assistant API over the plugin's rolling "
                        "30-day window, summed. **Never read this against the Overview tab's token "
                        "gauge** - that one is the monthly billing period, and on one stack measured the "
                        "same day they differed materially. The plugin figure is what the feature reports; "
                        "the billing figure is what is charged."),
        "n_ai_uncategorised": build.stat_panel(
            "Share of messages carrying no category", ai_uncategorised_share,
            unit="percentunit", decimals=1,
            description="Assistant classifies only some traffic. Measured across the estate this is the "
                        "MAJORITY of messages, and the per-stack median is higher still, so every "
                        "category breakdown on the Human vs machine tab is a share of the CATEGORISED "
                        "subset and never of total messages. This stat is what makes that honest."),
        "n_ai_combos": build.stat_panel(
            "Category x surface combinations in use", ai_combos,
            description="How many distinct category-and-surface pairs the estate actually produced. It is "
                        "a drift detector rather than an insight: this number rising means Assistant "
                        "added to its own taxonomy, which explains a step in our series count before "
                        "somebody has to go looking for the cause."),
        "b_ai_investigations": build.barchart_panel(
            "Investigations created, by originator", ai_investigations, legend="{{kind}}",
            description="Investigations created in the window, split by whether Assistant or a person "
                        "started them. The investigation INVENTORY is not collectable - a service "
                        "account owns none and belongs to no Grafana team - so these counts come from the "
                        "usage endpoint and there is deliberately no drill-down list."),
        "tbl_ai_stack_messages": build.prometheus_table_panel(
            "Top 50 stacks by Assistant messages (30d)", ai_top_messages, legend="{{stack}}",
            label_column="Stack", value_column="Messages",
            description="Ranked from our own per-stack series, so no stack_id-to-slug join is involved "
                        "and the Stack selector works. A stack absent from this table was not collected; "
                        "a stack present with zero really did have no Assistant traffic."),
        "tbl_ai_per_stack": build.table_panel(
            "Assistant use per stack - the full table", "ai_assistant", ds,
            columns=[" Stack".strip(), "Region", "Measured", "Users (active)", "Assistant users",
                     f"Days active of {assistant_src.WINDOW_DAYS}", "Messages",
                     "Messages categorised", "Messages uncategorised",
                     "Machine share of categorised", "Tokens", "Tokens per Assistant user",
                     "Investigations created", "Tenant objects", "Why not"],
            units={"Machine share of categorised": "percentunit"},
            description="Every stack in the estate, collected or not. `Users (active)` is the stack "
                        "population beside the Assistant-user subset, so low feature reach is visible "
                        "without another join. `Measured` false with a reason in "
                        "`Why not` is a stack the platform could not read - usually one created since "
                        "the last nightly provisioning run. Every tenant figure is TENANT-SCOPED: it is "
                        "not the total number of skills or rules on the stack and cannot be made into one."),
        "tbl_ai_reconciliation": build.table_panel(
            "Assistant source reconciliation and token split", "ai_assistant", ds,
            columns=["Stack", "Region", "Messages", "Messages categorised",
                     "Messages uncategorised", "Categorised exceeds total", "Chat tokens",
                     "Investigation tokens", "Investigations created",
                     "Investigations by Assistant", "Investigations by user", "Tenant skills",
                     "Tenant rules", "Tenant automations", "Tenant MCP integrations", "Detail"],
            description="The fields that explain disagreements hidden by the headline rollups. "
                        "`Categorised exceeds total` marks a source-frame mismatch rather than normalising "
                        "it away; chat and investigation tokens show which workflow drove consumption; "
                        "the two investigation-origin columns reconcile the total. `Detail` carries the "
                        "collection reason for unreadable rows. Tenant object counts remain tenant-scoped."),

        # --- Human vs machine ------------------------------------------------------------------------
        "b_ai_category": build.barchart_panel(
            "Categorised messages by task category", ai_by_category, legend="{{category}}",
            description="What people and pipelines ask Assistant to do, across the estate. "
                        "Investigate-dominated is incident work, Learn-dominated is onboarding, "
                        "Dashboard-dominated is authoring. Shares of the CATEGORISED subset only - see "
                        "the uncategorised stat on the previous tab before quoting a percentage."),
        "b_ai_surface": build.barchart_panel(
            "Categorised messages by surface", ai_by_surface, legend="{{surface}}",
            description="Where the traffic came from. `web` is a person in the UI; `cli`, `a2a`, "
                        "`automation`, `lodestone` and `slack` are machine-driven. This split exists in "
                        "no billing metric, and it is the one that changes the enablement conversation: "
                        "a stack driven by automation needs different help from one driven by people."),
        "t_ai_machine": build.timeseries_panel(
            "Machine-driven share of categorised messages - estate",
            [(ai_machine_share_estate, "non-web share")], unit="percentunit",
            description="Non-`web` surfaces as a share of categorised messages, estate-wide. Denominator "
                        "is the categorised subset, not all messages. A rising line means Assistant is "
                        "moving from an interactive tool to a pipeline component, which changes what "
                        "growth in token spend means."),
        "tbl_ai_combo": build.prometheus_table_panel(
            "Categorised messages by category and surface - estate", ai_combo_series,
            legend="{{category}} ({{surface}})", label_column="Category (surface)",
            value_column="Messages",
            description="The full cross-tabulation, estate-wide. Deliberately not broken down by stack "
                        "as a metric - that would be 273 x 21 series for a table. The per-stack version "
                        "is the next panel, from S3."),
        "tbl_ai_combo_stack": build.table_panel(
            "Category and surface per stack", "ai_category_surface", ds,
            schema=ai_pillar.VIEW_SCHEMAS["ai_category_surface"],
            description="One row per stack, category and surface. `Human driven` marks the `web` rows. "
                        "This is where a single stack's mix is read; the metric version above is "
                        "estate-wide because the per-stack cross product is a table, not a time series."),
        "tbl_ai_stack_machine": build.prometheus_table_panel(
            "Top 50 stacks by machine-driven share", ai_top_machine, legend="{{stack}}",
            label_column="Stack", value_column="Machine share", unit="percentunit",
            description="Stacks whose Assistant traffic is most machine-driven. ABSENT rather than zero "
                        "where nothing was categorised at all: a stack with no classified messages has "
                        "no share, and calling that 0% would assert it is entirely human-driven."),

        # --- Enablement and configuration ------------------------------------------------------------
        "b_ai_tenant_objects": build.barchart_panel(
            "Tenant Assistant objects across the estate", ai_tenant_objects, legend="{{kind}}",
            description="Every TENANT-scoped skill, rule, automation and MCP integration in the org. The "
                        "headline is how small these numbers are against the number of stacks using "
                        "Assistant. A zero bar is measured, not missing. User-scoped objects cannot be "
                        "counted by any credential, so this is not the total configured effort."),
        "tbl_ai_tenant": build.table_panel(
            "Tenant Assistant configuration - every object", "ai_tenant_config", ds,
            schema=ai_pillar.VIEW_SCHEMAS["ai_tenant_config"],
            description="Names and metadata only. Skill bodies, rule content, MCP URLs and MCP headers "
                        "are NOT collected, by design. `enabled` is blank for skills because the API does "
                        "not report it for them - blank is unknown, not disabled. "
                        "`authenticationFailed` true on an MCP row means Assistant is configured to reach "
                        "a system it currently cannot."),
        "tbl_ai_gap": build.table_panel(
            "Stacks using Assistant with no tenant configuration", "ai_enablement_gap", ds,
            schema=ai_pillar.VIEW_SCHEMAS["ai_enablement_gap"],
            columns=["Stack", "Messages", "Assistant users",
                     f"Days active of {assistant_src.WINDOW_DAYS}", "Tokens",
                     "Tokens per Assistant user", "Machine share of categorised"],
            units={"Machine share of categorised": "percentunit"},
            description="Real usage, no skills, no rules, no MCP integrations, no automations - people "
                        "driving Assistant raw. The cheapest intervention available on this estate. "
                        "Threshold is 100+ messages in the window, just above the active-stack upper "
                        "quartile, so this is a work queue rather than an inventory."),
        "tbl_ai_stack_tpu": build.prometheus_table_panel(
            "Top 50 stacks by tokens per Assistant user", ai_top_tpu, legend="{{stack}}",
            label_column="Stack", value_column="Tokens per user",
            description="The outlier detector. Read it with the machine-driven share: a very high "
                        "per-user figure is usually a pipeline attributed to a service identity, not a "
                        "person burning tokens. ABSENT where a stack has no active Assistant user, "
                        "because the ratio is undefined and a zero would rank a dormant stack first."),
        "tbl_ai_outliers": build.table_panel(
            "Token outliers - the stacks and their context", "ai_token_outliers", ds,
            schema=ai_pillar.VIEW_SCHEMAS["ai_token_outliers"],
            columns=["Stack", "Tokens per Assistant user", "Assistant users", "Tokens", "Messages",
                     "Machine share of categorised", "Tenant objects"],
            units={"Machine share of categorised": "percentunit"},
            description="Stacks above the estate's 90th percentile for tokens per Assistant user, with "
                        "the columns that explain them. An empty table is the healthy state and means no "
                        "stack currently clears the threshold."),
        "tbl_ai_mcp_failed": build.table_panel(
            "MCP integrations whose authentication is failing", "ai_mcp_auth_failed", ds,
            schema=ai_pillar.VIEW_SCHEMAS["ai_mcp_auth_failed"],
            description="An MCP integration still shows as enabled when its credentials stop working, so "
                        "this fails silently: Assistant is told to consult a system it cannot reach. An "
                        "empty table is a MEASURED zero - every stack's integrations were read."),
        "tbl_ai_disabled": build.table_panel(
            "Tenant objects that exist but are switched off", "ai_config_disabled", ds,
            schema=ai_pillar.VIEW_SCHEMAS["ai_config_disabled"],
            description="Configured effort producing nothing. Only an explicit `enabled: false` appears "
                        "here - skills carry no `enabled` field at all, and treating absent as false "
                        "would invent findings on every skill in the estate."),

        # --- Collection coverage ---------------------------------------------------------------------
        "n_ai_provisioned": build.stat_panel(
            "Stacks holding a working reader credential", ai_provisioned,
            description="Stacks whose per-stack read-only Assistant credential answered this scan. The "
                        "credential is a basic-role-None service account holding a custom read-only role: "
                        "the dashboard's input coverage is granted without write or chat access."),
        "n_ai_missing": build.stat_panel(
            "Stacks awaiting a credential", ai_missing,
            description="Provisionable stacks with no working credential. **A number above zero is "
                        "NORMAL** - a stack created today gets one at the next nightly reconciliation. "
                        "This count is deliberately NOT what the alert watches; the age beside it is. "
                        "Paused and opted-out stacks are excluded and can never appear here."),
        "n_ai_gap_age": build.stat_panel(
            "Oldest credential gap", ai_gap_age, unit="s",
            description="How long the longest-standing gap has been open, and the quantity the alert "
                        "fires on at 48 hours - two missed reconciliations. BLANK is the healthy state: "
                        "no gap has no age, and a zero would be indistinguishable from a gap that opened "
                        "this instant, which is exactly the moment not to page anybody."),
        "tbl_ai_coverage": build.table_panel(
            "Which stacks lack a credential, and since when", "ai_credential_coverage", ds,
            schema=ai_pillar.VIEW_SCHEMAS["ai_credential_coverage"],
            description="`Actionable` false means the platform is deliberately not provisioning that "
                        "stack: paused, so its Grafana is not running and even listing service accounts "
                        "is refused, or on the opt-out list the organisation asked for. Only actionable rows can "
                        "raise the alert. An empty table means every stack in the estate is covered."),
        "tbl_ai_summary": build.table_panel(
            "What is collected, what is not, and why", "ai_summary", ds,
            description="The headline figures with their denominators, followed by the four things this "
                        "platform deliberately does not or cannot collect. Read the NOT MEASURABLE rows "
                        "as product boundaries: no wider credential changes any of them."),

        # REPLACED, not deleted, on 2026-08-20. This tab used to say feature-level activity was "not
        # measurable estate-wide in Phase 1". That became FALSE the moment the per-stack reader credential
        # went live on 269 stacks (PLAN 17D), and a stale disclaimer is worse than none: it tells a reader
        # a number is unavailable while the platform is collecting it. What remains genuinely unavailable
        # is narrower and sharper, so it is stated as a boundary rather than a blanket.
        "feature_scope": build.text_panel(
            "What feature-level Assistant data can and cannot be collected",
            """Every stack now carries a read-only reader credential, so tenant-scoped Assistant
inventory and usage ARE collectable. Three limits are permanent and are **product boundaries, not
permission gaps** - a wider role cannot fix any of them, so a blank here is never a zero:

| | collectable |
|---|---|
| Usage aggregates - users, messages, tokens, investigations created, category x surface | **yes** |
| Tenant-scoped skills, rules, automations, MCP integrations | **yes, for tenant scope only** |
| User-scoped ("Just me") skills and rules | **no, and not even countable.** Invisible to a full Admin too; the API reports a total of 0 rather than hiding a count |
| Investigation **inventory** | **no.** A service account owns none and is in no Grafana team, so the list returns empty even holding `investigations.all:read` |
| Investigation **counts** | **yes**, split assistant-created vs user-created |
| Watchers | **no.** The endpoint rejects service-account identities outright - verified against a full Admin |

So every inventory figure on this dashboard is **tenant-scoped**. It is not the total number of skills
or rules on a stack, and cannot be made into one."""),
        "oss_scope": build.text_panel(
            "Self-managed Grafana Assistant usage is not distinguishable in billing metrics",
            """Assistant on a self-managed Grafana installation uses a connected Grafana Cloud stack's
backend, usage limits and billing. The usage metrics expose that Cloud `stack_id`, but no external-instance
or source label, so self-managed traffic is folded into the connected Cloud stack's users and token total.
This is **not zero self-managed usage**; it is a split the current datasource cannot make. An honest panel
needs a new product dimension or a tenant-wide Assistant API that identifies the originating instance."""),
    }

    tabs = [
        build.tab("Overview", ["n_assistant_users", "n_active_stacks", "n_token_users", "n_tokens",
                               "n_token_stacks", "n_assistant_overage", "n_token_overage"],
                  max_columns=3, row_height="short"),
        build.tab("Adoption by stack", ["tbl_stack_users", "tbl_stack_tokens"],
                  max_columns=2, row_height="tall"),
        build.rows_tab("Assistant use per stack", [
            build.row("Estate", ["n_ai_measured", "n_ai_with_usage", "n_ai_with_config",
                                 "n_ai_messages", "n_ai_est_users", "n_ai_est_tokens",
                                 "n_ai_uncategorised", "n_ai_combos"],
                      max_columns=4, row_height="short"),
            build.row("Ranking and investigations",
                      ["tbl_ai_stack_messages", "b_ai_investigations"],
                      max_columns=2, row_height="tall"),
            build.row("Every stack", ["tbl_ai_per_stack"], max_columns=1, row_height="tall"),
            build.row("Source reconciliation and workflow split", ["tbl_ai_reconciliation"],
                      max_columns=1, row_height="tall"),
        ]),
        build.rows_tab("Human vs machine", [
            build.row("Estate mix", ["b_ai_category", "b_ai_surface"], max_columns=2,
                      row_height="standard"),
            build.row("Trend and cross-tabulation", ["t_ai_machine", "tbl_ai_combo"],
                      max_columns=2, row_height="tall"),
            build.row("Per stack", ["tbl_ai_stack_machine", "tbl_ai_combo_stack"],
                      max_columns=2, row_height="tall"),
        ]),
        build.rows_tab("Enablement and configuration", [
            build.row("Tenant configuration across the estate",
                      ["b_ai_tenant_objects", "tbl_ai_tenant"], max_columns=2, row_height="tall"),
            build.row("Where enablement would pay", ["tbl_ai_gap"], max_columns=1,
                      row_height="tall"),
            build.row("Token outliers", ["tbl_ai_stack_tpu", "tbl_ai_outliers"], max_columns=2,
                      row_height="tall"),
            build.row("Configuration that is broken or switched off",
                      ["tbl_ai_mcp_failed", "tbl_ai_disabled"], max_columns=2,
                      row_height="standard"),
        ]),
        build.rows_tab("Collection coverage", [
            build.row("Credential coverage",
                      ["n_ai_provisioned", "n_ai_missing", "n_ai_gap_age"],
                      max_columns=3, row_height="short"),
            build.row("Stacks awaiting a credential", ["tbl_ai_coverage"], max_columns=1,
                      row_height="standard"),
            build.row("What is collected and what is not", ["tbl_ai_summary"], max_columns=1,
                      row_height="tall"),
        ]),
        build.rows_tab("Token consumption", [
            build.row("Concentration", ["n_top2_share", "n_top10_share"],
                      max_columns=2, row_height="short"),
            build.row("History", ["t_users", "t_tokens"], max_columns=2, row_height="tall"),
        ]),
        build.tab("People and identities", ["tbl_people", "tbl_services"],
                  max_columns=2, row_height="tall"),
        build.rows_tab("Commercial", [
            build.row("Assistant run rate by stack", ["tbl_stack_assistant_cost"],
                      max_columns=1, row_height="tall"),
            build.row("Raw contract gauges - do not use as denominators",
                      ["n_included_users", "n_additional_tokens", "n_included_additional_tokens"],
                      max_columns=3, row_height="short"),
        ]),
        build.tab("Feature activity", ["feature_scope", "oss_scope"],
                  max_columns=1, row_height="short"),
    ]

    return "gcinsight-ai", "Grafana Cloud Org Insights - Grafana Assistant & AI usage", \
        ("Pillar I: org-wide Assistant adoption, current billing-period token consumption, lifetime "
         "identity totals and AI-related run rate. Org-wide panels are live from grafanacloud-usage. "
         "Feature-level Assistant inventory is collectable per stack and is TENANT-SCOPED - see the "
         "Feature activity tab for the three boundaries that no credential can widen."), el, tabs


# Dashboard name -> pillar letter, so each dashboard shows only its OWN finding kinds. Derived from
# pillars/findings.py rather than restated, so adding a finding kind reaches the right dashboard with no
# edit here.
PILLAR_OF = {"estate": "A", "cost": "B", "usage": "C", "maturity": "D", "risk": "E", "value": "F",
             "operations": "G", "commercial": "H", "ai": "I", "dashboards": "J",
             "coverage": "K"}


# The named rows behind each pillar's finding counts, as (element key, panel title, view name).
#
# The Findings tab used to be a bar chart, a trend and a paragraph telling the reader to go and query
# Loki. That is not a drill-down: it says the estate has 41 of something and then sends the reader to a
# different tool to find out which 41. Every view named here is already published - the tables simply were
# not placed on the tab where the counts appear.
#
# Views are reused rather than duplicated, so a stack appearing in two lists is the same row in both.
FINDING_DETAIL: dict[str, tuple[tuple[str, str, str], ...]] = {
    "estate": (("_fd_idle", "Idle test leftovers - which stacks", "estate_leftovers_idle"),
               ("_fd_billing", "Test leftovers that DO bill - which stacks", "estate_leftovers_billing",
                estate_pillar.VIEW_SCHEMAS["estate_leftovers_billing"]),
               ("_fd_drift", "Off the standard build - which stacks", "estate_drift")),
    "cost": (("_fd_headroom", "Adaptive headroom - which stacks", "cost_adaptive_headroom"),
             ("_fd_cardinality", "Cardinality outliers - which stacks", "cost_cardinality_outliers")),
    "usage": (("_fd_dormant", "Dormant stacks - which stacks", "usage_dormant_stacks",
               usage_pillar.VIEW_SCHEMAS["usage_dormant_stacks"]),),
    "risk": (("_fd_admins", "Admin sprawl - which stacks", "risk_admin_sprawl"),
             ("_fd_noprot", "No delete protection - which stacks", "risk_delete_protection"),
             ("_fd_fleet", "Fleet Management dead - which stacks", "risk_fleet_dead"),
             ("_fd_plugins", "Plugin drift - which stacks", "risk_plugin_drift")),
    # Pillar I. These four carry a SCHEMA as a fourth item, because all four are condition-matched lists
    # where finding nothing is the good outcome - and `build.columns_for` derives a table's column spec
    # from the view's first row, so an empty view would fail the dashboard BUILD on a healthy estate and
    # take the whole page with it rather than one panel.
    "ai": (("_fd_ai_gap", "Assistant used with no tenant configuration - which stacks",
            "ai_enablement_gap", ai_pillar.VIEW_SCHEMAS["ai_enablement_gap"]),
           ("_fd_ai_tokens", "Tokens-per-user outliers - which stacks", "ai_token_outliers",
            ai_pillar.VIEW_SCHEMAS["ai_token_outliers"]),
           ("_fd_ai_mcp", "MCP integrations failing authentication - which stacks",
            "ai_mcp_auth_failed", ai_pillar.VIEW_SCHEMAS["ai_mcp_auth_failed"]),
           ("_fd_ai_off", "Tenant objects switched off - which stacks", "ai_config_disabled",
            ai_pillar.VIEW_SCHEMAS["ai_config_disabled"])),
}


def findings_for(name: str) -> tuple[str, list[str]]:
    pillar = PILLAR_OF.get(name, "")
    return pillar, [s.kind for s in findings.SPECS if s.pillar == pillar]


BUILDERS = {
    "estate": d_estate, "cost": d_cost, "usage": d_usage,
    "maturity": d_maturity, "risk": d_risk, "value": d_value,
    "operations": d_operations, "commercial": d_commercial, "ai": d_ai,
    "dashboards": d_dashboards, "coverage": d_coverage,
}


def assemble(
    name: str, ds: str, *, rate_card: ratecard_model.RateCard | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build one dashboard's full spec: the pillar's own panels plus the shared furniture.

    **This is the ONE place the shared furniture is applied**, and it is a function rather than inline
    code in `main()` because the layout test used to reproduce this assembly by hand. That copy drifted
    the moment the banner became per-dashboard and the Findings tab gained detail tables, so the test
    passed on an assembly nobody publishes while the real one was unverified. A single function means the
    test exercises exactly what ships.

    Raises `OrphanedElement` if any element is unplaced or any placement dangles - either blanks the
    entire dashboard, so it is a build failure rather than a warning.
    """
    if name == "cost":
        uid, title, desc, elements, tabs = d_cost(ds, rate_card=rate_card)
    else:
        uid, title, desc, elements, tabs = BUILDERS[name](ds)
    uid = uid.replace("gcinsight-", f"{DASHBOARD_UID_PREFIX}-", 1)
    title = title.replace("Grafana Cloud Org Insights", DASHBOARD_TITLE_PREFIX, 1)

    # Per-DASHBOARD, not a default: a dashboard whose figures come from the 6-hourly data-plane sweep
    # must show that input's age, not the hourly inventory's (PLAN 16.2).
    elements = {**build.banner_elements(name), **elements}
    # Rows, not a flat grid. In an auto-grid every panel gets an equal cell, so the guidance text was
    # squeezed into the same box as a stat and CLIPPED its last bullet, while "3 mins" rendered a
    # half-screen high. The text gets its own full-width row; the freshness stats share a 3-column row
    # beneath it, which is also what stops them dominating the page.
    banner_keys = list(build.banner_keys(name))
    freshness = [k for k in banner_keys if k != "_banner"]
    banner_rows = [build.row(
        "How to read this", ["_banner"], max_columns=1,
        # The live dashboards have no freshness row below this. Their banner is deliberately compact
        # enough for short height at 1700px; standard height leaves half a screen of blank space.
        row_height="short" if name in build.LIVE_DATASOURCE_ONLY else "standard",
    )]
    if freshness:
        banner_rows.append(build.row("Coverage and freshness", freshness, max_columns=3,
                                     row_height="short"))
    banner_tab = build.rows_tab("How to read this", banner_rows)
    # The headline tab is the default landing page. Guidance remains always available, but making it the
    # first tab buried the actual decision on all ten dashboards and forced every reader through method
    # prose before seeing whether anything needed attention.
    tabs = list(tabs)

    # Findings tab, only where this pillar actually has finding kinds. Two pillars have none of their
    # own, and an empty tab reads as a broken dashboard rather than as "nothing to report".
    pillar, kinds = findings_for(name)
    detail = FINDING_DETAIL.get(name, ())
    found_el = build.findings_elements(pillar, kinds, detail=detail, ds_uid=ds)
    if found_el:
        elements = {**elements, **found_el}
        # Summary above, named detail beneath. The detail is on the same tab - which is the whole point,
        # since the previous version sent the reader to Loki - while the row ordering keeps the counts
        # that tell readers where to look first ahead of the large tables.
        finding_rows = [build.row("Open findings", list(build.FINDINGS_KEYS), max_columns=2)]
        finding_rows += [build.row(entry[1], [entry[0]], max_columns=1)
                         for entry in detail]
        tabs = list(tabs) + [build.rows_tab("Findings", finding_rows)]

    # Method and freshness are always available but never steal the default landing page. Append after
    # the optional Findings tab so guidance has one stable location on every dashboard.
    tabs = list(tabs) + [banner_tab]

    spec = build.dashboard(
        title, desc, elements, tabs,
        tags=[DASHBOARD_TAG, f"pillar-{name}"],
        variables=[build.stack_variable()],
        links=build.cross_links(uid),
        # Assistant and token measures are monthly billing-period gauges. Six hours makes their history
        # look flat and hides the reset boundary; thirty days shows the period shape by default while the
        # time picker remains available.
        time_from=("now-30d" if name == "ai" else
                   "now-7d" if name == "dashboards" else "now-6h"),
    )
    return uid, identity.map_tree(spec)


def publish(uid: str, spec: dict, folder_uid: str, token: str) -> tuple[int, object]:
    """Create or update via the v2 resource API, then verify what Grafana actually persisted."""
    ns = f"stacks-{STACK_ID}"
    root = f"/apis/{build.SCHEMA}/namespaces/{ns}/dashboards"
    resource = {
        "apiVersion": build.SCHEMA,
        "kind": "Dashboard",
        "metadata": {
            "name": uid,
            "annotations": {"grafana.app/folder": folder_uid},
        },
        "spec": spec["spec"],
    }
    code, existing = _api("GET", f"{root}/{uid}", token)
    if code == 200 and isinstance(existing, dict):
        resource["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
        code, response = _api("PUT", f"{root}/{uid}", token, resource)
    else:
        code, response = _api("POST", root, token, resource)
    if code not in (200, 201):
        return code, response

    read_code, persisted = _api("GET", f"{root}/{uid}", token)
    if read_code != 200 or not isinstance(persisted, dict):
        return 502, f"write accepted but persisted dashboard could not be read back: {read_code} {persisted}"
    try:
        verify_persisted(uid, spec, persisted)
    except ValueError as exc:
        return 502, f"write accepted but persisted dashboard failed contract verification: {exc}"
    return code, persisted


LINK_REQUIRED = (
    "title", "type", "icon", "tooltip", "tags", "asDropdown", "targetBlank", "includeVars",
    "keepTime",
)

THIRD_PARTY_VIZ_GROUPS = frozenset({
    "volkovlabs-echarts-panel",
    "volkovlabs-table-panel",
    "volkovlabs-variable-panel",
    "marcusolsson-treemap-panel",
})


def _require_persisted_subset(expected: Any, actual: Any, path: str) -> None:
    """Require every authored plugin option to survive read-back, while allowing server defaults."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise ValueError(f"{path} changed from an object while being persisted")
        for key, value in expected.items():
            if key not in actual:
                raise ValueError(f"{path}.{key} was dropped while being persisted")
            _require_persisted_subset(value, actual[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"{path} list length changed while being persisted")
        for index, (wanted, saved) in enumerate(zip(expected, actual)):
            _require_persisted_subset(wanted, saved, f"{path}[{index}]")
        return
    if actual != expected:
        raise ValueError(f"{path} changed from {expected!r} to {actual!r} while being persisted")


def verify_persisted(uid: str, expected: dict, resource: dict) -> None:
    """Refuse a write that Grafana accepted but normalised into a broken dashboard.

    The API has silently discarded structurally-wrong link fields before. Source-side tests then
    asserted the same wrong builder and passed. This checker reads the saved resource and validates the
    external contracts at their customer-visible seam.
    """
    metadata = resource.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("name") != uid:
        raise ValueError(f"read-back identity is not {uid!r}")
    persisted = resource.get("spec")
    wanted = expected.get("spec")
    if not isinstance(persisted, dict) or not isinstance(wanted, dict):
        raise ValueError("read-back has no dashboard spec")

    elements = persisted.get("elements")
    expected_elements = wanted.get("elements")
    if not isinstance(elements, dict) or not isinstance(expected_elements, dict):
        raise ValueError("read-back has no elements mapping")
    if set(elements) != set(expected_elements):
        raise ValueError(
            f"element keys changed: missing={sorted(set(expected_elements) - set(elements))} "
            f"extra={sorted(set(elements) - set(expected_elements))}"
        )

    for name, element in elements.items():
        if not isinstance(element, dict) or element.get("kind") != "Panel":
            raise ValueError(f"element {name!r} is not a Panel envelope")
        panel = element.get("spec")
        if not isinstance(panel, dict):
            raise ValueError(f"element {name!r} has no panel spec")
        expected_panel = ((expected_elements.get(name) or {}).get("spec")
                          if isinstance(expected_elements.get(name), dict) else None)
        if not isinstance(expected_panel, dict):
            raise ValueError(f"expected element {name!r} has no panel spec")
        if panel.get("id") != expected_panel.get("id"):
            raise ValueError(
                f"element {name!r} panel id changed from {expected_panel.get('id')!r} "
                f"to {panel.get('id')!r}"
            )
        viz = panel.get("vizConfig")
        if not (
            isinstance(viz, dict) and viz.get("kind") == "VizConfig"
            and isinstance(viz.get("group"), str) and bool(viz["group"])
            and isinstance(viz.get("spec"), dict)
        ):
            raise ValueError(f"element {name!r} has a malformed VizConfig envelope")
        expected_viz = expected_panel.get("vizConfig")
        if not isinstance(expected_viz, dict):
            raise ValueError(f"expected element {name!r} has no VizConfig envelope")
        for field in ("kind", "group", "version"):
            if viz.get(field) != expected_viz.get(field):
                raise ValueError(f"element {name!r} changed VizConfig {field!r} while being persisted")
        if viz["group"] in THIRD_PARTY_VIZ_GROUPS:
            wanted_spec = expected_viz.get("spec")
            saved_spec = viz.get("spec")
            if not isinstance(wanted_spec, dict) or not isinstance(saved_spec, dict):
                raise ValueError(f"third-party element {name!r} has no options spec")
            _require_persisted_subset(
                wanted_spec.get("options", {}), saved_spec.get("options"),
                f"element {name!r} options",
            )
            _require_persisted_subset(
                wanted_spec.get("fieldConfig", {}), saved_spec.get("fieldConfig"),
                f"element {name!r} fieldConfig",
            )
            if viz["group"] == "volkovlabs-echarts-panel":
                get_option = (wanted_spec.get("options") or {}).get("getOption")
                if not isinstance(get_option, str) or not get_option.strip():
                    raise ValueError(f"element {name!r} has blank Business Charts getOption")
                saved_option = (saved_spec.get("options") or {}).get("getOption")
                if saved_option != get_option:
                    raise ValueError(f"element {name!r} Business Charts getOption changed on read-back")
        data = panel.get("data")
        queries = (((data or {}).get("spec") or {}).get("queries")) if isinstance(data, dict) else None
        if not isinstance(queries, list):
            raise ValueError(f"element {name!r} has no query list")
        expected_data = expected_panel.get("data")
        expected_queries = (((expected_data or {}).get("spec") or {}).get("queries")
                            if isinstance(expected_data, dict) else None)
        if not isinstance(expected_queries, list):
            raise ValueError(f"expected element {name!r} has no query list")
        if len(queries) != len(expected_queries):
            raise ValueError(
                f"element {name!r} query count changed from {len(expected_queries)} to {len(queries)}"
            )
        for index, (query, expected_query) in enumerate(zip(queries, expected_queries)):
            if not isinstance(query, dict) or query.get("kind") != "PanelQuery":
                raise ValueError(f"element {name!r} has a malformed PanelQuery envelope")
            inner = (query.get("spec") or {}).get("query")
            if not (
                isinstance(inner, dict) and inner.get("kind") == "DataQuery"
                and isinstance(inner.get("group"), str) and bool(inner["group"])
                and isinstance(inner.get("datasource"), dict)
                and isinstance(inner["datasource"].get("name"), str)
                and bool(inner["datasource"]["name"])
                and isinstance(inner.get("spec"), dict)
            ):
                raise ValueError(f"element {name!r} has a malformed DataQuery envelope")
            if inner["group"] == build.INFINITY_TYPE:
                query_spec = inner["spec"]
                if query_spec.get("parser") != "backend":
                    raise ValueError(f"Infinity query in {name!r} is not using the backend parser")
                if query_spec.get("root_selector") != "rows":
                    raise ValueError(f"Infinity query in {name!r} has no rows root_selector")
                columns = query_spec.get("columns")
                if not isinstance(columns, list) or not columns:
                    raise ValueError(f"Infinity query in {name!r} has no explicit columns")
            _require_persisted_subset(
                expected_query, query, f"element {name!r} query {index}",
            )

    _require_persisted_subset(wanted.get("layout"), persisted.get("layout"), "layout")

    links = persisted.get("links")
    expected_links = wanted.get("links")
    if not isinstance(links, list) or not isinstance(expected_links, list):
        raise ValueError("read-back has no links list")
    if len(links) != len(expected_links):
        raise ValueError(f"link count changed from {len(expected_links)} to {len(links)}")
    for index, (link, expected_link) in enumerate(zip(links, expected_links)):
        if not isinstance(link, dict) or "kind" in link or "spec" in link:
            raise ValueError(f"link {index} is not the flat DashboardDashboardLink shape")
        missing = [field for field in LINK_REQUIRED if field not in link]
        if missing:
            raise ValueError(f"link {index} is missing required fields {missing}")
        if not link.get("title") or not link.get("url") or link.get("type") != "link":
            raise ValueError(f"link {index} has no usable title/url/type")
        if not isinstance(link.get("tags"), list):
            raise ValueError(f"link {index} tags is not a list")
        for field in ("title", "url", "type", "includeVars", "keepTime"):
            if link.get(field) != expected_link.get(field):
                raise ValueError(f"link {index} changed {field!r} while being persisted")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--publish", help="dashboard name, or `all`")
    ap.add_argument("--out", help="write built JSON to this directory")
    ap.add_argument("--ds-uid", help="datasource uid; resolved by name if omitted")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    try:
        identity.verify_runtime_projection("dashboards")
    except identity.InvalidIdentity as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list:
        for name in BUILDERS:
            print(f" {name}")
        return 0

    token = os.environ.get("GCINSIGHT_GRAFANA_TOKEN", "").strip()
    if args.publish:
        if not token:
            print(
                "error: GCINSIGHT_GRAFANA_TOKEN is not set (build-time Grafana admin token)",
                file=sys.stderr,
            )
            return 2
        # Both values identify the write target. A defaulted stack id can publish successfully into a
        # different customer's namespace, so refuse before the first Grafana API call.
        for var, value, purpose in (
            ("GCINSIGHT_WRITE_STACK_URL", BASE, "e.g. https://<slug>.grafana.net"),
            ("GCINSIGHT_WRITE_STACK_ID", STACK_ID, "the stack's numeric id"),
        ):
            if not value:
                print(f"error: {var} is not set ({purpose})", file=sys.stderr)
                return 2
        ds = args.ds_uid or resolve_ds_uid(token)
        folder = resolve_folder_uid(token)
        print(f"datasource uid={ds} folder uid={folder}", file=sys.stderr)
    else:
        if not args.out:
            print("error: choose --list, --out, or --publish", file=sys.stderr)
            return 2
        if not args.ds_uid:
            print("error: --out requires --ds-uid for an offline build", file=sys.stderr)
            return 2
        ds = args.ds_uid
        print(f"datasource uid={ds}", file=sys.stderr)

    names = list(BUILDERS) if args.publish == "all" else (
        [args.publish] if args.publish else list(BUILDERS))
    deployed_rate_card = None
    if args.publish and "cost" in names:
        # The rate card is optional, but unreadable/malformed is never treated as absent. Import lazily
        # so local JSON generation and unit-test assembly do not touch deployment S3 state.
        from scan import RateCardReadFailed, load_ratecard
        try:
            deployed_rate_card = load_ratecard()
        except (RateCardReadFailed, ratecard_model.InvalidRateCard) as exc:
            print(f"error: rate card configuration is invalid: {exc}", file=sys.stderr)
            return 2
    rc = 0
    for name in names:
        # PLAN 6.6 - shared banner, coverage, freshness, variable, cross-links and Findings tab, all
        # applied inside `assemble` so the layout test can exercise the same code path.
        uid, spec = assemble(
            name, ds, rate_card=deployed_rate_card if name == "cost" else None,
        )
        if args.out:
            path = pathlib.Path(args.out)
            path.mkdir(parents=True, exist_ok=True)
            (path / f"{uid}.json").write_text(json.dumps(spec, indent=2))
            print(f" wrote {path / f'{uid}.json'}", file=sys.stderr)
        if args.publish:
            code, resp = publish(uid, spec, folder, token)
            ok = code in (200, 201)
            print(f" {'OK ' if ok else 'FAIL'} {name:9} {uid:28} HTTP {code}"
                  f"{'' if ok else ' ' + str(resp)[:300]}", file=sys.stderr)
            if not ok:
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
