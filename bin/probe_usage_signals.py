#!/usr/bin/env python3
"""Regenerate `testdata/usage-datasource-signals.json` from live `grafanacloud-usage` queries.

    GCINSIGHT_GCX_CONTEXT=<context> python3 bin/probe_usage_signals.py

Needs nothing but a working `gcx` context on a stack in the org - `grafanacloud-usage` is provisioned on
every one of them and carries the whole org's billing/usage series. No service account, no CAP, no token
to tear down afterwards.

The dashboard panels these numbers back read the same datasource LIVE, so this file is not an input to
anything: it is the committed proof that the panel expressions returned what the docs claim, on a date.
Re-run it before quoting any figure from `IDEAS.md`, `PLAN.md` Stage 11 or a panel description.

**Rate-shaped series are windowed, never compared instantaneously.** Every `*_per_second` and `*:rate5m`
series here is momentary, so `> 0` answers "is this happening in the current scrape window" rather than
"does this stack have a problem". The `instant_vs_window` section is the measured justification, and
`tests/test_dashboards.py` enforces the same rule on the panels.
"""

import json
import os
import subprocess
import sys

DS = "grafanacloud-usage"
CTX = os.environ.get("GCINSIGHT_GCX_CONTEXT", "").strip()
if not CTX:
    raise SystemExit("GCINSIGHT_GCX_CONTEXT is required; no deployment context is assumed")
INFO = "grafanacloud_grafana_instance_info"
WINDOW = "24h"
DEFECT = '{reason!="requested-by-configuration"}'


def _decode(raw, want):
    """gcx interleaves a `{"class":"hint"}` object with its payload, so scan every top-level object."""
    dec, i, found = json.JSONDecoder(), 0, None
    while i < len(raw):
        while i < len(raw) and raw[i] in " \n\r\t":
            i += 1
        if i >= len(raw):
            break
        obj, i = dec.raw_decode(raw, i)
        if isinstance(obj, dict) and want(obj):
            found = obj
    return found


def q(expr):
    proc = subprocess.run(
        ["gcx", "metrics", "query", expr, "--context", CTX, "-d", DS,
         "--from", "now-3h", "--to", "now", "--step", "1h", "-o", "json"],
        capture_output=True, text=True)
    obj = _decode(proc.stdout, lambda o: o.get("status") == "success")
    if obj is None:
        raise SystemExit(f"query failed: {expr}\n{proc.stdout[:400]}{proc.stderr[:400]}")
    return obj["data"]["result"]


def scalar(expr):
    res = q(expr)
    return None if not res else float(res[0]["values"][-1][1])


def named(expr, key="slug", *, ascending=False):
    """topk/bottomk-with-join -> [{slug, value}], deduped on the last value each series carries.

    A `topk` evaluated over a RANGE returns the union of the top-k at every step, so more than k series
    come back and the last value of each is what a panel's `lastNotNull` reducer would show. Set
    `ascending` for a `bottomk` so the worst offender is row 0 rather than the best of the worst.
    """
    out = {}
    for r in q(expr):
        slug = r["metric"].get(key)
        if slug:
            out[slug] = float(r["values"][-1][1])
    sign = 1 if ascending else -1
    return [{"slug": s, "value": v} for s, v in sorted(out.items(), key=lambda kv: sign * kv[1])]


def by_label(expr, label):
    return {r["metric"].get(label): float(r["values"][-1][1]) for r in q(expr)}


def join(expr):
    return f"{expr} * on(stack_id) group_left(slug) {INFO}"


def any_in_window(selector):
    """Stacks where a rate-shaped series was non-zero at ANY point in the window."""
    return f"count(count by(stack_id) (max_over_time({selector}[{WINDOW}]) > 0))"


def peak_by_stack(selector, k=10):
    return join(f"topk({k}, sum by(stack_id)(max_over_time({selector}[{WINDOW}])))")


doc = {
    "generated_by": "python3 bin/probe_usage_signals.py",
    "window": WINDOW,
    "source": {
        "datasource": DS,
        "stack_context": CTX,
        "note": (
            "Org-wide billing/usage series, provisioned on every stack. Read DIRECTLY by "
            "dashboard panels - no collector, no service account, no series of ours. 317 metric names "
            "available. Every metric carries a `stack_id` label, and `" + INFO + "` (272 series, one per "
            "stack) carries `stack_id` AND `slug`, so a panel joins to a stack NAME with "
            "`* on(stack_id) group_left(slug) " + INFO + "`. Range queries only, never instant."),
        "cardinality_trap": (
            "`id` is the per-SIGNAL instance id, not the stack. `grafanacloud_instance_queries_per_second` "
            "carries 459 ids against 230 stacks, so `count(<metric> > 0)` counts label combinations and "
            "overstates. Aggregate `sum by(stack_id)` / `count by(stack_id)` first. See "
            "`label_cardinality` for which metrics are genuinely 1:1 per stack."),
        "unit_trap": (
            "`grafanacloud_traces_instance_percentage_complete_traces_flushed` and "
            "`..._percentage_traces_with_root_spans_flushed` are RATIOS 0-1 despite the word percentage "
            "(measured max 1.0). But `..._spans_more_than_5m_in_past_percent` IS percent-scaled and is "
            "not contractually capped at 100 (the current synthetic fixture max is 66.7). Two families, "
            "same word, different units. Thresholding the ratio at "
            "`< 90` matches every stack that reports and reads as a 26-stack outage that is not happening."),
        "window_trap": (
            "Rate-shaped series are momentary. Comparing one to zero asks 'is this happening right now', "
            "not 'does this stack have a problem'. See `instant_vs_window`."),
    },
}

print("data loss...", file=sys.stderr)
DISCARD = "grafanacloud_instance_samples_discarded_per_second"
doc["data_loss"] = {
    "stacks_discarding_metric_samples_defect_reasons": scalar(any_in_window(DISCARD + DEFECT)),
    "stacks_discarding_metric_samples_any_reason": scalar(any_in_window(DISCARD)),
    "stacks_discarding_log_bytes": scalar(
        any_in_window("grafanacloud_logs_instance_discarded_bytes_per_second")),
    "stacks_per_discard_reason": by_label(
        f"count by(reason) (max_over_time({DISCARD}{DEFECT}[{WINDOW}]) > 0)", "reason"),
    "worst_stacks": named(peak_by_stack(DISCARD + DEFECT, 15)),
    "reason_taxonomy": {
        "deliberate": ["requested-by-configuration"],
        "sender_defect": ["sample_duplicate_timestamp", "new-value-for-timestamp",
                          "sample_timestamp_too_old", "too_far_in_future", "otlp_parse_error",
                          "label_invalid", "aggregator-sample-too-old",
                          "sample-too-new-for-aggregation", "aggregator-histogram-too-old"],
        "limit_breach": ["aggregator-too-many-raw-series", "aggregator-too-many-aggregated-series",
                         "aggregator-histogram-unsupported-aggregation"],
    },
    "excluded_on_purpose": (
        "`requested-by-configuration` is Adaptive Metrics dropping what it was told to drop. Counting it "
        "would report a stack as broken for adopting the lever the cost dashboard recommends."),
}

print("trace quality...", file=sys.stderr)
COMPLETE = "grafanacloud_traces_instance_percentage_complete_traces_flushed"
ROOTSPAN = "grafanacloud_traces_instance_percentage_traces_with_root_spans_flushed"
doc["trace_quality"] = {
    "stacks_reporting_completeness": scalar(f"count({COMPLETE})"),
    "max_ratio_observed": scalar(f"max({COMPLETE})"),
    "min_ratio_observed": scalar(f"min({COMPLETE})"),
    "stacks_below_090_complete_24h_low": scalar(f"count(min_over_time({COMPLETE}[{WINDOW}]) < 0.90)"),
    "stacks_below_090_complete_instant": scalar(f"count({COMPLETE} < 0.90)"),
    "stacks_below_090_root_spans_24h_low": scalar(f"count(min_over_time({ROOTSPAN}[{WINDOW}]) < 0.90)"),
    "stacks_over_5pct_spans_late_by_5m": scalar(
        "count(grafanacloud_traces_instance_spans_more_than_5m_in_past_percent > 5)"),
    "worst_stacks": named(join(f"bottomk(10, min_over_time({COMPLETE}[{WINDOW}]))"), ascending=True),
}

print("alerting...", file=sys.stderr)
NOTIF = "grafanacloud_instance_alertmanager_notifications_failed_per_second"
DEADRULE = "grafanacloud_instance_ruler_queries_zero_fetched_series_total:rate5m"
EVALFAIL = "grafanacloud_grafana_instance_alerting_rule_evaluation_failures_total:rate5m"
doc["alerting_health"] = {
    "stacks_with_failing_notifications": scalar(any_in_window(NOTIF)),
    "stacks_with_rules_fetching_zero_series": scalar(any_in_window(DEADRULE)),
    "stacks_with_rule_evaluation_failures": scalar(any_in_window(EVALFAIL)),
    "stacks_with_invalid_alertmanager_config": scalar(
        "count(grafanacloud_instance_alertmanager_invalid_config > 0)"),
    "worst_notification_failures": named(peak_by_stack(NOTIF)),
    "worst_dead_rules": named(peak_by_stack(DEADRULE)),
    "not_a_panel": (
        "`grafanacloud_instance_alertmanager_invalid_config` and both config-reload counters are empty "
        "estate-wide, so a panel would read 0 for ever. Recheck here before assuming it still holds."),
}

print("unread telemetry...", file=sys.stderr)
LOG_IN = (f"max_over_time(sum by(stack_id)"
          f"(grafanacloud_logs_instance_bytes_received_per_second)[{WINDOW}:5m])")
LOG_UNREAD = (f"(max_over_time(sum by(stack_id)"
              f"(grafanacloud_logs_instance_query_bytes:rate5m)[{WINDOW}:5m]) == 0)")
METRICS_IN = f"max_over_time(sum by(stack_id)(grafanacloud_instance_active_series)[{WINDOW}:5m])"
METRICS_UNREAD = (f"(max_over_time(sum by(stack_id)"
                  f"(grafanacloud_instance_queries_per_second)[{WINDOW}:5m]) == 0)")
doc["unread_telemetry"] = {
    "note": (
        "'Ingested and never queried' - IDEAS.md's highest-value and hardest number. Measured over a full "
        "day it splits and only the LOGS half survives. The `and` requiring active ingest is "
        "load-bearing: without it this counts empty stacks and becomes the inventory again."),
    "logs_stacks_ingesting": scalar(f"count({LOG_IN} > 0)"),
    "logs_stacks_ingesting_but_unread": scalar(f"count(({LOG_IN} > 0) and {LOG_UNREAD})"),
    "logs_unread_bytes_per_second": scalar(f"sum({LOG_IN} and {LOG_UNREAD})"),
    "logs_total_bytes_per_second": scalar(f"sum({LOG_IN})"),
    "logs_worst_stacks": named(join(f"topk(15, ({LOG_IN} and {LOG_UNREAD}))")),
    "metrics_stacks_ingesting": scalar(f"count({METRICS_IN} > 0)"),
    "metrics_stacks_ingesting_but_unread": scalar(f"count(({METRICS_IN} > 0) and {METRICS_UNREAD})"),
    "metrics_verdict": (
        "NEGATIVE RESULT - there is no metrics write-only finding and no panel for it. Every stack that "
        "ingests metrics gets queried within 24h bar one, and no stack over 10,000 series went unqueried. "
        "The instantaneous form claimed 60 stacks and 4 large ones; both were artifacts of asking 'was "
        "anyone querying in this 5-minute window'. The metric-quiet stacks hold no series at all, i.e. "
        "the test leftovers `estate_leftovers_idle` already reports. Do not re-add it."),
}

print("adaptive savings...", file=sys.stderr)
SAVINGS = "grafanacloud_instance_recommendations_estimated_savings_series"
doc["adaptive_savings"] = {
    "estimated_savings_series_available": scalar(f"sum({SAVINGS})"),
    "estate_active_series": scalar("sum(grafanacloud_instance_active_series)"),
    "savings_as_fraction_of_estate": scalar(
        f"sum({SAVINGS}) / sum(grafanacloud_instance_active_series)"),
    "stacks_with_savings_available": scalar(f"count(sum by(stack_id)({SAVINGS}) > 0)"),
    "stacks_actually_aggregating": scalar(
        "count(sum by(stack_id)(grafanacloud_instance_aggregation_aggregated_series) > 0)"),
    "raw_series_feeding_aggregation": scalar("sum(grafanacloud_instance_aggregation_raw_series)"),
    "aggregated_series_out": scalar("sum(grafanacloud_instance_aggregation_aggregated_series)"),
    "top_stacks": named(join(f"topk(15, sum by(stack_id)({SAVINGS}))")),
    "closes": (
        "collector/pillars/cost.py states that converting Adaptive Metrics recommendations into a saving "
        "needs a per-recommendation series count it cannot obtain, so it reports rule COUNTS and says "
        "volume is the honest unit. This metric is that missing number. It is still not currency - that "
        "needs the contract."),
}

print("irm...", file=sys.stderr)
ONCALL = "grafanacloud_oncall_instance_alert_groups_total"
doc["irm_in_use"] = {
    "oncall_alert_groups_total": scalar(f"sum({ONCALL})"),
    "oncall_alert_groups_by_state": by_label(f"sum by(state)({ONCALL})", "state"),
    "stacks_with_oncall_provisioned": scalar(f"count(sum by(stack_id)({ONCALL}))"),
    "stacks_with_oncall_alert_groups": scalar(f"count(sum by(stack_id)({ONCALL}) > 0)"),
    "distinct_oncall_teams": scalar(f"count(count by(team)({ONCALL}))"),
    "users_notified_of_alert_groups": scalar(
        "sum(grafanacloud_oncall_instance_user_was_notified_of_alert_groups_total)"),
    "irm_billable_users": scalar("sum(grafanacloud_irm_billable_users)"),
    "stacks_by_oncall_groups": named(join(f"topk(20, sum by(stack_id)({ONCALL}))")),
    "native_labels": (
        "This metric is the exception on this datasource: it already carries `slug`, `team`, "
        "`service_name`, `integration` and `state`, so no join is needed unless an aggregation discards "
        "them. `..._response_time_seconds` and `..._resolution_time_seconds` give real MTTA/MTTR per team "
        "- measured but deliberately not built, see IDEAS.md."),
    "correction": (
        "gcom reports `incident: 0` and `billingOnCallActiveUsers: 0` on EVERY stack listed here. gcom's "
        "`incident` field is the standalone Grafana Incident product, NOT IRM or OnCall. Reading "
        "gcinsight_estate_feature_stacks{kind=\"incident\"} == 0 as 'incident response is unused' is "
        "WRONG and this is the disproof."),
}

print("instant vs window...", file=sys.stderr)
doc["instant_vs_window"] = {
    "note": (
        "Why every rate-shaped expression on these dashboards is wrapped in max_over_time. `instant` is "
        "what a momentary compare returns, `window` the same question over " + WINDOW + ". The instant "
        "form UNDERSTATES intermittent faults and grossly OVERSTATES absence of activity, and it is "
        "unstable: the write-only count read 60 then 33 within 40 minutes on 2026-08-18, which on its own "
        "disqualifies it. tests/test_dashboards.py enforces the windowing."),
    "metric_discards": {
        "instant": scalar(f"count(count by(stack_id) ({DISCARD}{DEFECT} > 0))"),
        "window": doc["data_loss"]["stacks_discarding_metric_samples_defect_reasons"]},
    "log_discards": {
        "instant": scalar(
            "count(count by(stack_id) (grafanacloud_logs_instance_discarded_bytes_per_second > 0))"),
        "window": doc["data_loss"]["stacks_discarding_log_bytes"]},
    "incomplete_traces": {
        "instant": doc["trace_quality"]["stacks_below_090_complete_instant"],
        "window": doc["trace_quality"]["stacks_below_090_complete_24h_low"]},
    "failing_notifications": {
        "instant": scalar(f"count(count by(stack_id)({NOTIF} > 0))"),
        "window": doc["alerting_health"]["stacks_with_failing_notifications"]},
    "rule_evaluation_failures": {
        "instant": scalar(f"count(count by(stack_id)({EVALFAIL} > 0))"),
        "window": doc["alerting_health"]["stacks_with_rule_evaluation_failures"],
        "comment": "The largest gap measured. 9 against 41."},
    "dead_rules": {
        "instant": scalar(f"count(count by(stack_id)({DEADRULE} > 0))"),
        "window": doc["alerting_health"]["stacks_with_rules_fetching_zero_series"],
        "comment": "Identical both ways - a persistent condition, not an event. The control case."},
    "metrics_write_only": {
        "instant": scalar("count(sum by(stack_id)(grafanacloud_instance_queries_per_second) == 0)"),
        "window": doc["unread_telemetry"]["metrics_stacks_ingesting_but_unread"],
        "comment": "The one that dissolved a finding entirely."},
}

print("operations (pillar G)...", file=sys.stderr)
ACK = "grafanacloud_oncall_instance_alert_groups_response_time_seconds"
RESO = "grafanacloud_oncall_instance_alert_groups_resolution_time_seconds"
GRP = "grafanacloud_oncall_instance_alert_groups_total"
TOP = "3600.0"
ENGAGED_DENOM = f"sum({GRP} and on(stack_id) (sum by(stack_id)({ACK}_count) > 0))"
doc["operations"] = {
    "note": (
        "Pillar G - outcomes, not inventory. TWO POPULATIONS: `alert_groups_total` spans 58 stacks, the "
        "response histogram only 8. Any ratio must restrict the denominator with `and on(stack_id)` or it "
        "is a ~15x error. A missing histogram observation means no acknowledgement was RECORDED - the "
        "metric cannot prove intent, so never phrase it as 'nobody looked'."),
    "bucket_note": (
        f"Buckets are 60/300/600/{TOP}/+Inf, so histogram_quantile SATURATES above the median: p90 and "
        f"p99 both return exactly {TOP}, meaning 'at least an hour'. Only p50 is real; the tail must be a "
        f"COUNT above the top finite bucket. And `le` values carry a decimal point - le=\"3600\" matches "
        f"nothing."),
    "alert_groups_estate": scalar(f"sum({GRP})"),
    "alert_groups_by_state": by_label(f"sum by(state)({GRP})", "state"),
    "stacks_with_oncall": scalar(f"count(sum by(stack_id)({GRP}))"),
    "stacks_reporting_timing": scalar(f"count(sum by(stack_id)({ACK}_count))"),
    "acknowledged": scalar(f"sum({ACK}_count)"),
    "raised_on_timing_stacks": scalar(ENGAGED_DENOM),
    "engagement_rate": scalar(f"sum({ACK}_count) / ({ENGAGED_DENOM})"),
    "mtta_median_seconds": scalar(f"histogram_quantile(0.5, sum by(le)({ACK}_bucket))"),
    "mttr_median_seconds": scalar(f"histogram_quantile(0.5, sum by(le)({RESO}_bucket))"),
    "mtta_mean_seconds": scalar(f"sum({ACK}_sum) / sum({ACK}_count)"),
    "ack_cumulative_buckets": by_label(f"sum by(le)({ACK}_bucket)", "le"),
    "acknowledged_after_an_hour": scalar(
        f'sum({ACK}_bucket{{le="+Inf"}}) - sum({ACK}_bucket{{le="{TOP}"}})'),
    "unowned_share_of_all": scalar(f'sum({GRP}{{team="No team"}}) / sum({GRP})'),
    "unowned_share_of_acknowledged": scalar(
        f'sum({ACK}_count{{team="No team"}}) / sum({ACK}_count)'),
    "no_service_share": scalar(f'sum({GRP}{{service_name="No service"}}) / sum({GRP})'),
    "team_engagement_rate": {
        r["metric"].get("team"): float(r["values"][-1][1])
        for r in q(f"(sum by(team)({ACK}_count) / sum by(team)({GRP})) "
                   f"and (sum by(team)({GRP}) >= 50)")},
    "distinct_teams": scalar(f"count(count by(team)({GRP}))"),
    "top_integrations": by_label(f"topk(12, sum by(integration)({GRP}))", "integration"),
    "top_services": by_label(f"topk(8, sum by(service_name)({GRP}))", "service_name"),
}

print("capability + workload...", file=sys.stderr)


def stacks_with(metric):
    """Windowed - an instantaneous count of a bursty series measures one scrape, not adoption."""
    return scalar(f"count(sum by(stack_id)(max_over_time({metric}[{WINDOW}])) > 0)")


doc["capability_adoption"] = {
    "note": (
        "DENOMINATORS DECIDE THE CONCLUSION, and they must be windowed like the numerators. Read "
        "instantaneously the trace population is 39 stacks; over 24h it is 230, because trace ingest is "
        "bursty. Using 39 made span metrics look like 46% adoption - 'a success, not a gap' - when the "
        "honest figure is 10%. That error was made and caught on 2026-08-19."),
    "stacks_ingesting_metrics": stacks_with("grafanacloud_instance_active_series"),
    "stacks_ingesting_traces": stacks_with("grafanacloud_traces_instance_bytes_received_per_second"),
    "stacks_ingesting_traces_INSTANT_do_not_use": scalar(
        "count(sum by(stack_id)(grafanacloud_traces_instance_bytes_received_per_second) > 0)"),
    "native_histograms": stacks_with("grafanacloud_instance_active_native_histogram_series"),
    "exemplars": stacks_with("grafanacloud_instance_exemplars_per_second"),
    "span_metrics": stacks_with("grafanacloud_instance_active_spanmetrics_series"),
    "service_graphs": stacks_with("grafanacloud_instance_active_service_graph_series"),
    "pdc": stacks_with("grafanacloud_grafana_pdc_connected_agents"),
    "adaptive_logs": stacks_with("grafanacloud_logs_instance_adaptivelogs_bytes_dropped_per_second"),
    "adaptive_traces": stacks_with(
        "grafanacloud_traces_instance_adaptivetraces_bytes_received_per_second"),
    "product_activation": by_label(
        "count by(product)(grafanacloud_product_activation_status == 1)", "product"),
    "rejected_unidentifiable_targets": {
        "stacks": stacks_with("grafanacloud_instance_active_unidentifiable_targets_series"),
        "total_series": scalar("sum(grafanacloud_instance_active_unidentifiable_targets_series)"),
        "verdict": ("On ~229 stacks and looks like an un-attributed-junk signal, but the total is ~1,111 "
                    "series - 0.0% of the estate. Noise, not a finding. Deliberately no panel."),
    },
}
doc["workload"] = {
    "pods_monitored": scalar("sum(grafanacloud_instance_active_kube_pod_info_series)"),
    "hosts_monitored": scalar("sum(grafanacloud_instance_active_node_uname_info_series)"),
    "integration_series": scalar("sum(grafanacloud_instance_active_integration_series)"),
    "integration_share_of_estate": scalar(
        "sum(grafanacloud_instance_active_integration_series) / "
        "sum(grafanacloud_instance_active_series)"),
    "stacks_monitoring_k8s": stacks_with("grafanacloud_instance_active_kube_pod_info_series"),
    "stacks_monitoring_hosts": stacks_with("grafanacloud_instance_active_node_uname_info_series"),
    "stacks_using_integrations": stacks_with("grafanacloud_instance_active_integration_series"),
    "assistant_users": scalar("sum(grafanacloud_org_assistant_users)"),
    "ai_tokens_total": scalar("sum(grafanacloud_ai_tokens_total_tokens)"),
    "note": ("`*_info` series are one per object, so their SUM is an object count - the most concrete "
             "'what is in there' figure the platform produces, and it needs no per-stack credential."),
}

print("Assistant and AI usage (pillar I)...", file=sys.stderr)
doc["assistant_ai"] = {
    "window_contract": (
        "grafanacloud_ai_tokens_total_tokens is the CURRENT MONTHLY BILLING-PERIOD aggregate and "
        "resets. grafanacloud_ai_tokens_user_total_tokens is cumulative by identity. Never present "
        "the aggregate as lifetime or the identity ranking as current-period spend."),
    "identity_label_trap": (
        "user_type=service is a billing-series category, NOT proof of a service account. Live rows "
        "include human-shaped emails as well as sa-* identities."),
    "self_managed_attribution": (
        "Grafana docs say self-managed Assistant uses the connected Cloud stack's backend, limits and "
        "billing. The metrics carry only that Cloud stack_id and no originating-instance/source label, "
        "so OSS traffic is folded into the connected Cloud stack and cannot be split here. The live "
        "unmatched_stack_ids checks below are evidence about identifier shape, NOT zero OSS usage."),
    "org_assistant_users": scalar("sum(grafanacloud_org_assistant_users)"),
    "assistant_active_user_memberships": scalar("sum(grafanacloud_assistant_active_users)"),
    "assistant_contract_user_units": scalar("sum(grafanacloud_assistant_users)"),
    "stacks_with_assistant_activity": scalar(
        "count(sum by(stack_id)(grafanacloud_assistant_active_users) > 0)"),
    "org_ai_token_active_users": by_label(
        "sum by(user_type)(grafanacloud_org_ai_tokens_active_users)", "user_type"),
    "ai_token_user_memberships": by_label(
        "sum by(user_type)(grafanacloud_ai_tokens_active_users)", "user_type"),
    "current_billing_period_tokens": scalar("sum(grafanacloud_ai_tokens_total_tokens)"),
    "current_user_token_total": scalar(
        'sum(grafanacloud_ai_tokens_total_tokens{user_type="user"})'),
    "current_service_token_total": scalar(
        'sum(grafanacloud_ai_tokens_total_tokens{user_type="service"})'),
    "current_sum_of_identity_counters": scalar(
        "sum(grafanacloud_ai_tokens_user_total_tokens)"),
    "stacks_with_current_tokens": scalar(
        "count(sum by(stack_id)(grafanacloud_ai_tokens_total_tokens) > 0)"),
    "assistant_run_rate": scalar("sum(grafanacloud_org_assistant_overage)"),
    "assistant_run_rate_stack_sum": scalar("sum(grafanacloud_assistant_overage)"),
    "ai_token_run_rate": scalar("sum(grafanacloud_org_ai_tokens_overage)"),
    "ai_token_run_rate_stack_sum": scalar("sum(grafanacloud_ai_tokens_overage)"),
    "included_assistant_users": scalar("sum(grafanacloud_org_assistant_included_users)"),
    "additional_ai_tokens": scalar("sum(grafanacloud_org_ai_tokens_additional_tokens)"),
    "included_additional_ai_tokens": scalar(
        "sum(grafanacloud_org_ai_tokens_included_additional_tokens)"),
    "unmatched_stack_ids": {
        metric: scalar(
            f"count(count by(stack_id)({metric}) unless on(stack_id) {INFO}) or vector(0)")
        for metric in (
            "grafanacloud_assistant_active_users",
            "grafanacloud_assistant_users",
            "grafanacloud_assistant_overage",
            "grafanacloud_ai_tokens_active_users",
            "grafanacloud_ai_tokens_total_tokens",
            "grafanacloud_ai_tokens_user_total_tokens",
            "grafanacloud_ai_tokens_overage",
        )
    },
    "top_100_stacks_by_assistant_users": named(join(
        "topk(100, sum by(stack_id)(grafanacloud_assistant_active_users))")),
    "top_100_stacks_by_current_tokens": named(join(
        "topk(100, sum by(stack_id)(grafanacloud_ai_tokens_total_tokens))")),
    "top_2_token_share": scalar(
        "sum(topk(2, sum by(stack_id)(grafanacloud_ai_tokens_total_tokens))) / "
        "sum(grafanacloud_ai_tokens_total_tokens)"),
    "top_10_token_share": scalar(
        "sum(topk(10, sum by(stack_id)(grafanacloud_ai_tokens_total_tokens))) / "
        "sum(grafanacloud_ai_tokens_total_tokens)"),
}

print("commercial (pillar H)...", file=sys.stderr)
CREDIT = "sum(grafanacloud_org_spend_commit_credit_total)"
BALANCE = "sum(grafanacloud_org_spend_commit_balance_total)"
RUNRATE = "sum(grafanacloud_org_total_overage)"
doc["commercial"] = {
    "unit_derivation": (
        "NOTHING here declares a currency or a period. The unit is DERIVED from an identity the metrics "
        "satisfy: balance / total_overage vs the independent forecast_months_remaining (below). They agree "
        "to ~0.3%, which only holds if total_overage is a MONTHLY run-rate against the same commitment the "
        "balance draws from. Label the panels with the currency and period, mark the unit DERIVED, and "
        "RE-DERIVE rather than trust it if the two figures ever diverge."),
    "included_volumes_are_zero": (
        "metrics/logs/grafana `_included_*` all read 0 while billable is ~11.95M series / ~12,486 units / "
        "553 users. Pure spend-commit contract with no bundled allowance, so `total_overage` is the WHOLE "
        "charge for the period, NOT an excess over a plan. Never present it as money spent above plan."),
    "commitment_total": scalar(CREDIT),
    "commitment_balance": scalar(BALANCE),
    "commitment_consumed": scalar(f"{CREDIT} - {BALANCE}"),
    "commitment_consumed_share": scalar(f"1 - ({BALANCE} / {CREDIT})"),
    "run_rate_per_month": scalar(RUNRATE),
    "run_rate_by_product": {
        label: scalar(f"sum({metric})") for metric, label in (
            ("grafanacloud_org_metrics_overage", "metrics"),
            ("grafanacloud_org_grafana_overage", "grafana_users"),
            ("grafanacloud_org_logs_overage", "logs"),
            ("grafanacloud_org_assistant_overage", "assistant"),
            ("grafanacloud_org_traces_overage", "traces"),
            ("grafanacloud_org_profiles_overage", "profiles"))},
    "metrics_share_of_run_rate": scalar(f"sum(grafanacloud_org_metrics_overage) / {RUNRATE}"),
    "contract_start_epoch": scalar("max(grafanacloud_org_contract_start_date)"),
    "contract_end_epoch": scalar("max(grafanacloud_org_contract_end_date)"),
    "term_elapsed_share": scalar(
        "(time() - max(grafanacloud_org_contract_start_date)) / "
        "(max(grafanacloud_org_contract_end_date) - max(grafanacloud_org_contract_start_date))"),
    "months_to_contract_end": scalar(
        "(max(grafanacloud_org_contract_end_date) - time()) / (60*60*24*30.44)"),
    "forecast_months_remaining_metric": scalar("sum(grafanacloud_org_forecast_months_remaining)"),
    "balance_over_run_rate_months": scalar(f"{BALANCE} / {RUNRATE}"),
    "not_on_the_dashboard": (
        "This probe can compute whether a commitment will be consumed by term end. DO NOT put that "
        "conclusion in a panel description: whether a commitment is on track is a conversation somebody "
        "has with the contract in front of them, and a dashboard asserting it is both out of scope and "
        "easy to be wrong about. Burn chart only, no conclusion. A test enforces it."),
}

print("label cardinality...", file=sys.stderr)


def cardinality(metric):
    """Series count vs distinct stack_id, for every metric a panel counts without `by(stack_id)`.

    A metric with one series per stack can be counted directly; one with several CANNOT, and the
    difference is invisible in the rendered panel. This section is what lets the dashboard tests decide
    which bare counts are legitimate instead of hardcoding an exemption list that rots.
    """
    proc = subprocess.run(
        ["gcx", "metrics", "series", "--context", CTX, "-d", DS, "--match", metric,
         "--from", "now-1h", "--to", "now", "-o", "json"], capture_output=True, text=True)
    obj = _decode(proc.stdout, lambda o: "data" in o)
    res = (obj or {}).get("data") or []
    return {"series": len(res),
            "distinct_stack_id": len({s.get("stack_id") for s in res}),
            "distinct_id": len({s.get("id") for s in res}),
            "labels": sorted({k for s in res for k in s})}


doc["label_cardinality"] = {
    "note": ("`series` vs `distinct_stack_id`. Equal means one series per stack and a bare `count()` is "
             "honest; greater means several signal instances or label values per stack, so a panel MUST "
             "collapse `sum by(stack_id)`/`count by(stack_id)` first or it counts series and overstates. "
             "tests/test_dashboards.py reads this to decide which bare counts are legitimate."),
    **{m: cardinality(m) for m in (
        COMPLETE, ROOTSPAN, DEADRULE, NOTIF, INFO, SAVINGS, ONCALL, DISCARD,
        "grafanacloud_instance_active_otlp_series",
        "grafanacloud_instance_active_series",
        "grafanacloud_instance_queries_per_second",
        "grafanacloud_logs_instance_discarded_bytes_per_second",
    )},
}

json.dump(doc, open("testdata/usage-datasource-signals.json", "w"), indent=2)
print("written", file=sys.stderr)
