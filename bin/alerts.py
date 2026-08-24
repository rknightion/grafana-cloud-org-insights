#!/usr/bin/env python3
"""Build and publish the platform's own health alerts (PLAN 7.3).

    python3 bin/alerts.py --list                # what would be built
    python3 bin/alerts.py --out /tmp/alerts     # write JSON, publish nothing
    python3 bin/alerts.py --publish             # create or update all rules

Needs a Grafana token with alerting write on the target stack, in `GCINSIGHT_GRAFANA_TOKEN`. Like
`bin/dashboards.py` this is a BUILD-time credential - the scheduled scan never touches the Grafana API.

WHY THESE ALERT ON AGE AND NOT ON EXIT CODE
-------------------------------------------
A scan that fails loudly is the easy case and needs no alert: it exits non-zero, and its own metrics
still arrive. The failure that actually loses the platform is silent - the task cannot pull its image,
cannot reach Secrets Manager, or was never scheduled at all. Nothing runs, so there is no exit code, no
log line and no metric to compare. The only observable is that the timestamp stopped moving.

So the primary signal is the AGE of `gcinsight_scan_completed_timestamp_seconds`, and NoData is
itself the alarm rather than something to suppress.

THE QUERY SHAPE IS NOT INCIDENTAL - `max_over_time` IS LOAD-BEARING
------------------------------------------------------------------
The collector writes hourly at best and weekly at worst, and Mimir's lookback-delta is 5 minutes. A
plain instant query on one of these series therefore returns an EMPTY result at almost any evaluation
time, which the same trap already cost this project once on the dashboards. Every rule below wraps the
selector in `max_over_time(...[window])`, so the series has a value at every evaluation regardless of
how sparsely it is written. **Each window must be longer than that rule's own threshold**, or the series
disappears exactly when it goes stale and the rule silently degrades to NoData instead of firing on age.

ROUTING IS NEVER LEFT TO THE DEFAULT POLICY
------------------------------------------
The write stack can have notification policies that create tickets or page an on-call rota. A Grafana
rule with `notification_settings` unset inherits that policy, so an unpaused rule could notify an
unrelated customer receiver on the strength of our scanner being late.

Two independent guards, because either alone can be undone by a single mistake:

  1. Rules publish PAUSED. A paused rule evaluates nothing and notifies nothing.
  2. `--activate` REFUSES without an explicit `--receiver`. There is no code path that unpauses a rule
     while leaving routing to be inherited. The deployment owner nominates the receiver; we do not guess it.

WHAT IS DELIBERATELY NOT ALERTED
--------------------------------
Scan duration. A scan getting slower while still completing inside its deadline is not an incident, and
a rule for it would fire on ordinary estate growth. It is on the dashboard, where a human reading a
trend is the right consumer. Over-alerting is a defect, not thoroughness.

Mimir/Loki push failure has no rule either, and does not need one: if the push fails, the timestamp
series never arrives, so the staleness rule already covers it. That is the second reason to alert on age.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from collector import identity

BASE = os.environ.get("GCINSIGHT_WRITE_STACK_URL", "").strip()
FOLDER_UID = os.environ.get("GCINSIGHT_INSIGHTS_FOLDER_UID", "").strip()
PROM_UID = os.environ.get("GCINSIGHT_PROM_DS_UID", "grafanacloud-prom")
RULE_GROUP = identity.env("GCINSIGHT_ALERT_RULE_GROUP", "gcinsight-health")
TITLE_PREFIX = identity.env("GCINSIGHT_ALERT_TITLE_PREFIX", "Estate insights")
TITLE_SEPARATOR = identity.env("GCINSIGHT_ALERT_TITLE_SEPARATOR", ":")
SERVICE_LABEL = identity.env("GCINSIGHT_ALERT_SERVICE_LABEL", "gcinsight")

# Alert-rule identity is the uid, never the title. A fresh installation POSTs these generic stable
# values, so later title edits remain ordinary in-place PUTs.
# Keep the registry keyed by the rule's logical purpose rather than by its current display title: doing
# the latter would quietly turn a title rename back into an identity migration.
RULE_UIDS: dict[str, str] = identity.json_mapping("GCINSIGHT_ALERT_RULE_UIDS_JSON", {
    "coverage": "gcinsight-coverage",
    "staleness_t1": "gcinsight-stale-t1",
    "staleness_t2": "gcinsight-stale-t2",
    "staleness_t3": "gcinsight-stale-t3",
    "staleness_t4": "gcinsight-stale-t4",
    "input": "gcinsight-input",
    "credential_gap": "gcinsight-credential-gap",
})

# How often the group is evaluated. One minute would be waste: the fastest tier writes hourly, so
# nothing these rules watch can change more than once an hour.
GROUP_INTERVAL_SECONDS = 300

# tier -> (max_over_time window, staleness threshold in seconds, human interval)
#
# Each threshold allows roughly two consecutive missed runs: long enough that a single late or slow run
# never pages, short enough that nobody reads a stale dashboard believing it is current.
#
# **These MUST move whenever a cadence moves.** t3 went weekly -> every 6 hours and t4 weekly -> daily on
# 2026-08-19; leaving t3 at 9 days would have let 36 consecutive missed runs pass in silence, which is a
# worse failure than the one the rule exists to catch.
#
# Two relationships, both asserted in tests/test_alerts.py because each produces a rule that looks correct
# in the UI and cannot fire:
#   * the window must be LONGER than the threshold, or the series stops existing at exactly the moment the
#     rule should fire and it degrades to NoData;
#   * the threshold must be SHORTER than carry.MAX_CARRY_AGE, so the alert always precedes the panels
#     going blank rather than following it.
TIERS: dict[str, tuple[str, int, str]] = {
    "t1": ("24h", 3 * 3600, "hourly"),
    "t2": ("7d", 36 * 3600, "daily"),
    "t3": ("48h", 18 * 3600, "6-hourly"),
    "t4": ("7d", 36 * 3600, "daily"),
}

COVERAGE_FLOOR = 0.90
COVERAGE_WINDOW = "36h"

# Two missed provisioner runs (it is daily, at 03:35 UTC). Deliberately not a count threshold - see
# `credential_gap_rule`.
CREDENTIAL_GAP_SECONDS = 48 * 3600


def alert_title(suffix: str) -> str:
    separator = TITLE_SEPARATOR if TITLE_SEPARATOR in {":", ";", "."} else f" {TITLE_SEPARATOR}"
    return f"{TITLE_PREFIX}{separator} {suffix}"


def _expr_node(expr: str, ref: str = "query") -> dict:
    """A prometheus instant query, shaped as the stack's own converted rules shape it."""
    return {
        "refId": ref,
        "queryType": "prometheus",
        "datasourceUid": PROM_UID,
        # `from` only has to cover the instant query's own evaluation; the lookback that matters is
        # inside the PromQL, in max_over_time.
        "relativeTimeRange": {"from": 600, "to": 0},
        "model": {
            "refId": ref,
            "datasource": {"type": "prometheus", "uid": PROM_UID},
            "expr": expr,
            "instant": True,
            "range": False,
            "intervalMs": 1000,
            "maxDataPoints": 43200,
        },
    }


def _threshold_node(on: str, gt: float | None = None, lt: float | None = None, ref: str = "threshold") -> dict:
    evaluator = {"type": "gt", "params": [gt]} if gt is not None else {"type": "lt", "params": [lt]}
    return {
        "refId": ref,
        "queryType": "threshold",
        "datasourceUid": "__expr__",
        "relativeTimeRange": {"from": 0, "to": 0},
        "model": {
            "refId": ref,
            "type": "threshold",
            "datasource": {"type": "__expr__", "uid": "__expr__", "name": "__expr__"},
            "expression": on,
            "conditions": [{"evaluator": evaluator}],
            "intervalMs": 1000,
            "maxDataPoints": 43200,
        },
    }


def staleness_rule(tier: str, *, paused: bool = True, receiver: str | None = None) -> dict:
    window, threshold, cadence = TIERS[tier]
    hours = threshold / 3600
    return {
        "uid": RULE_UIDS[f"staleness_{tier}"],
        "title": alert_title(f"{tier} scan is stale"),
        "ruleGroup": RULE_GROUP,
        "folderUID": FOLDER_UID,
        "condition": "threshold",
        "for": "10m",
        # NoData IS the alarm here. If the series is absent entirely, the platform has never run or has
        # been dead longer than the window - the exact silent failure this rule exists for. Suppressing
        # it would leave the dead-man's switch unable to detect the deadest case.
        "noDataState": "Alerting",
        # A query error means we do not know the age, which is not the same as being stale. Escalating
        # on it would turn Mimir's own blips into false pages; the next successful evaluation resolves.
        "execErrState": "OK",
        "isPaused": paused,
        # None means "inherit the notification policy", which can reach ticketing or on-call receivers.
        # Only ever set from an explicitly named receiver.
        "notification_settings": {"receiver": receiver} if receiver else None,
        "labels": {
            "service": SERVICE_LABEL,
            "tier": tier,
            "severity": "critical" if tier in ("t1", "t2") else "warning",
        },
        "annotations": {
            "summary": f"The {cadence} {tier} estate scan has not completed for over {hours:.0f}h.",
            "description": (
                f"`gcinsight_scan_completed_timestamp_seconds{{tier=\"{tier}\"}}` has not advanced "
                f"in more than {hours:.0f}h, so the {tier} tier is not running. Nothing on the "
                "dashboards for this tier is current, and the panels will keep showing the last good "
                "values rather than going blank.\n\n"
                "This fires on the AGE of the timestamp, not on a task exit code, because the failures "
                "that matter here produce no exit code at all - an image that cannot be pulled, a "
                "secret that cannot be read, or a schedule that was never created.\n\n"
                "Check, in order: the EventBridge schedule exists and is ENABLED; the last ECS task's "
                "stopped reason; the task's CloudWatch logs; and whether a stale S3 lock under "
                f"`locks/{tier}.lock` is causing every run to refuse to start."
            ),
            "runbook_url": "See RUNBOOK.md in the insights platform repository.",
        },
        "data": [
            # The subtraction is done in PromQL rather than a math node so the alert's own value is the
            # age in seconds - which is what someone reading the alert wants to see.
            _expr_node(
                f'time() - max_over_time(gcinsight_scan_completed_timestamp_seconds{{tier="{tier}"}}[{window}])'
            ),
            _threshold_node("query", gt=float(threshold)),
        ],
    }


def coverage_rule(*, paused: bool = True, receiver: str | None = None) -> dict:
    """One rule for every tier, because the floor is the same for all of them.

    `last_over_time` rather than `min_over_time`: the question is whether the MOST RECENT scan was thin,
    not whether any scan in the window was. `min_over_time` would keep a recovered tier alerting for the
    whole window after one bad run.
    """
    return {
        "uid": RULE_UIDS["coverage"],
        "title": alert_title("scan coverage below floor"),
        "ruleGroup": RULE_GROUP,
        "folderUID": FOLDER_UID,
        "condition": "threshold",
        "for": "10m",
        # OK, NOT Alerting - deliberately different from the staleness rules. A tier that is not running
        # produces no coverage series either, and it already has its own rule; firing both would page
        # twice for one fault.
        "noDataState": "OK",
        "execErrState": "OK",
        "isPaused": paused,
        "notification_settings": {"receiver": receiver} if receiver else None,
        "labels": {"service": SERVICE_LABEL, "severity": "warning"},
        "annotations": {
            "summary": f"A scan tier covered less than {COVERAGE_FLOOR:.0%} of the scannable estate.",
            "description": (
                "`gcinsight_scan_coverage_ratio` is below "
                f"{COVERAGE_FLOOR:.0%} for the tier in this alert's labels. The estate did not shrink - "
                "coverage is the denominator-aware measure, so this means stacks FAILED to be scanned "
                "and the aggregate numbers are computed over fewer stacks than usual.\n\n"
                "The overwhelmingly likely cause is `grafana.com` rate-limiting: it meters per "
                "credential and answers 429 with `Retry-After: 8-10`. An unpaced sweep once lost 77 of "
                "271 stacks this way. Check whether two tiers ran concurrently, or whether anything "
                "else is using the same access policy token.\n\n"
                "Coverage is measured against `stacks_scannable`, not `stacks_total`: paused stacks "
                "answer HTTP 409 and are skipped rather than failed, so they must not count against it."
            ),
        },
        "data": [
            _expr_node(f"last_over_time(gcinsight_scan_coverage_ratio[{COVERAGE_WINDOW}])"),
            _threshold_node("query", lt=COVERAGE_FLOOR),
        ],
    }


def input_rule(*, paused: bool = True, receiver: str | None = None) -> dict:
    """A composable input has gone unavailable, so the views depending on it are being WITHHELD.

    This is the alert for the failure mode that motivated `collector/emit/hydrate.py` (PLAN 16.1). Every
    tier now composes from the full input set, pulling what it did not gather from the tier that did, and
    withholds any view whose inputs are missing or past the staleness cap. **The symptom on the dashboard
    is therefore a table that stops advancing, not a table that goes to zero** - which is the honest
    behaviour, and also a silent one. Nobody notices a figure that is merely no longer moving.

    `noDataState: OK`, deliberately. The metric only exists once a tier has run, and a tier that is not
    running already has its own staleness rule; alerting here as well would page twice for one fault.

    Alerts on `_available` rather than on `_age_seconds` because the age is emitted only while the input
    IS available - an unavailable input has no age at all, on purpose, since a zero would read as
    "gathered just now". So availability is the signal and age is the diagnosis.
    """
    return {
        "uid": RULE_UIDS["input"],
        "title": alert_title("an input is unavailable and views are being withheld"),
        "ruleGroup": RULE_GROUP,
        "folderUID": FOLDER_UID,
        "condition": "threshold",
        # Longer than the others: T2's input is gathered daily, so a single missed run is normal-ish and
        # the staleness cap allows several. This should fire on a persistent gap, not on one late tier.
        "for": "30m",
        "noDataState": "OK",
        "execErrState": "OK",
        "isPaused": paused,
        "notification_settings": {"receiver": receiver} if receiver else None,
        "labels": {"service": SERVICE_LABEL, "severity": "warning"},
        "annotations": {
            "summary": "A tier could not obtain one of its composable inputs, so the views that depend "
                       "on it were not republished.",
            "description": (
                "`gcinsight_input_available` is 0 for the tier and input in this alert's labels.\n\n"
                "Each tier composes from the FULL input set: `access_policies` from the hourly tier, "
                "`stack_detail` from the daily tier, `dataplane` from the 6-hourly tier, hydrated from "
                "`scans/<tier>/latest.json` when the running tier did not gather it. A 0 here means that "
                "object was missing, carried no such input, or was older than the staleness cap.\n\n"
                "**The affected views were WITHHELD, not zeroed.** The previous copies are still on the "
                "bucket with their own older `generated_at`, so the dashboards are stale rather than "
                "wrong - check the per-input freshness panels on the affected dashboard's first tab to "
                "see how stale.\n\n"
                "Diagnose the tier that OWNS the input, not the one that raised this. If that tier is "
                "failing it has its own staleness alert; if it is running but its scan carries no such "
                "input, the gatherer is broken while the scan still exits 0.\n\n"
                "One benign cause: a fresh deployment where the owning tier has not run yet."
            ),
        },
        "data": [
            _expr_node("min_over_time(gcinsight_input_available[6h])"),
            _threshold_node("query", lt=1),
        ],
    }


def credential_gap_rule(*, paused: bool = True, receiver: str | None = None) -> dict:
    """A stack has been without its Assistant reader credential for too long (PLAN 17D).

    **Alerts on the AGE of the oldest individual gap, never on the count**, and that distinction is the
    whole rule. A count above zero is the NORMAL state for hours after the organisation creates a stack: the daily
    provisioner at 03:35 UTC fixes it on its next pass. Worse, `count > 0 FOR 48h` never resets while
    stacks keep appearing, so it would eventually fire having never seen one gap last two days.
    `collector/emit/gapstate.py` stamps when each gap was first observed and the collector emits the
    maximum, so this rule watches exactly the thing that matters.

    48 hours is two missed provisioner runs. `noDataState: OK` because the series is ABSENT when there is
    no gap at all - that is the healthy state and it must not page.

    `max_over_time` over a window longer than the threshold, for the same reason as every other rule
    here: the collector writes hourly and Mimir's lookback-delta is 5 minutes, so a bare instant selector
    evaluates empty most of the time.
    """
    return {
        "uid": RULE_UIDS["credential_gap"],
        "title": alert_title("a stack has been without its Assistant credential for 48h"),
        "ruleGroup": RULE_GROUP,
        "folderUID": FOLDER_UID,
        "condition": "threshold",
        "for": "30m",
        "noDataState": "OK",
        "execErrState": "OK",
        "isPaused": paused,
        "notification_settings": {"receiver": receiver} if receiver else None,
        "labels": {"service": SERVICE_LABEL, "severity": "warning"},
        "annotations": {
            "summary": "The longest-standing per-stack Assistant credential gap has passed two days, "
                       "so the nightly provisioner is not fixing it on its own.",
            "description": (
                "`gcinsight_missing_credential_age_seconds` is the age of the OLDEST individual gap, "
                "not a count. A count above zero is normal and clears at the next 03:35 UTC provisioner "
                "run; a gap that survives two runs will not clear by itself.\n\n"
                "Read `views/ai_credential_coverage.json` (Assistant dashboard, coverage table) for "
                "which stacks, since when, and whether the state is actionable. Paused and opted-out "
                "stacks are excluded from the gap set by design and can never raise this.\n\n"
                "Then run the provisioner by hand and read its per-stack action:\n"
                "`GCINSIGHT_PROVISION_TOKEN=… python3 bin/provision.py --dry-run --stack <slug>`\n\n"
                "The actions map to different faults. `create_sa` on a stack that already has one means "
                "the listing failed - usually a transient 5xx, which self-heals. `unexplained_403` means "
                "the credential authenticates and the role carries every declared action and the API "
                "still refuses: that needs a human and **must not** be re-minted, it would loop. A stack "
                "that has just left the estate should have been pruned, so check the inventory too.\n\n"
                "This is the insights platform's health, not the organisation's. It must route only to "
                "the receiver explicitly nominated at activation and must never inherit the stack's "
                "notification policy."
            ),
        },
        "data": [
            _expr_node("max_over_time(gcinsight_missing_credential_age_seconds[6h])"),
            _threshold_node("query", gt=float(CREDENTIAL_GAP_SECONDS)),
        ],
    }


def build_all(*, paused: bool = True, receiver: str | None = None) -> list[dict]:
    """Paused by DEFAULT, and that default is a safety property rather than timidity.

    Until the schedules are enabled, every one of these rules is legitimately in breach: no tier has run
    recently, so each staleness rule either measures a large age or sees no series at all. Publishing
    them live would put four firing alerts straight into the organisation's notification policy - 662 other rules
    already route through it and this tool does not own where they go.

    So the rules land paused, and `--activate` is the deliberate go-live step, taken once the schedules
    are on and one run of each tier has landed.
    """
    rules = (
        [staleness_rule(t, paused=paused, receiver=receiver) for t in TIERS]
        + [coverage_rule(paused=paused, receiver=receiver)]
        + [input_rule(paused=paused, receiver=receiver)]
        + [credential_gap_rule(paused=paused, receiver=receiver)]
    )
    return identity.map_tree(rules)


# --- publishing -------------------------------------------------------------------------------------


def _api(method: str, path: str, token: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # Without this the provisioning API stamps provenance=api and the rules become READ-ONLY in
            # the UI. the organisation's platform team must be able to tune a threshold without a code change, and
            # a rule they cannot edit is a rule they will delete.
            "X-Disable-Provenance": "true",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(900).decode("utf-8", "replace")


def contact_points(token: str) -> list[str]:
    code, body = _api("GET", "/api/v1/provisioning/contact-points", token)
    if code != 200 or not isinstance(body, list):
        raise SystemExit(f"cannot list contact points: {code} {str(body)[:300]}")
    return sorted({c["name"] for c in body if c.get("name")})


def _rule_indexes(token: str) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """Return all rules by uid, then OUR rules by uid and by title.

    UID uniqueness is a Grafana contract, but verify the payload before using a uid in a PUT path.
    Titles only need to be unique inside our folder/group; duplicate titles elsewhere are normal on this
    stack. Building all three indexes from one response also makes the publish preflight atomic: every
    collision is found before the first write.
    """
    code, body = _api("GET", "/api/v1/provisioning/alert-rules", token)
    if code != 200 or not isinstance(body, list):
        raise SystemExit(f"cannot list alert rules: {code} {str(body)[:300]}")

    def unique(rows: list[dict], field: str, scope: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for rule in rows:
            value = rule.get(field)
            if not isinstance(value, str) or not value:
                raise SystemExit(f"REFUSED: {scope} rule has no usable {field}: {str(rule)[:300]}")
            if value in out:
                raise SystemExit(f"REFUSED: duplicate {field} {value!r} in {scope} alert-rule state")
            out[value] = rule
        return out

    all_by_uid = unique(body, "uid", "live")
    ours = [
        rule for rule in body
        if rule.get("folderUID") == FOLDER_UID and rule.get("ruleGroup") == RULE_GROUP
    ]
    # Pause and routing are customer-blast-radius state. Treat an incomplete live payload as unknown,
    # never as the falsy defaults Python would otherwise supply: bool(None) is False (active), while a
    # missing notification_settings becomes None (inherit the organisation's default policy). That combination can
    # create ServiceNow/Jira/OnCall traffic from a malformed GET response before any alert expression is
    # even considered.
    for rule in ours:
        uid = rule.get("uid") or "<unknown>"
        if not isinstance(rule.get("isPaused"), bool):
            raise SystemExit(
                f"REFUSED: our live rule {uid!r} has no boolean isPaused; pause state is unknown"
            )
        if "notification_settings" not in rule:
            raise SystemExit(
                f"REFUSED: our live rule {uid!r} has no notification_settings; routing is unknown"
            )
        routing = rule["notification_settings"]
        if routing is not None and not (
            isinstance(routing, dict)
            and isinstance(routing.get("receiver"), str)
            and bool(routing["receiver"].strip())
        ):
            raise SystemExit(
                f"REFUSED: our live rule {uid!r} has malformed notification_settings: "
                f"{str(routing)[:200]}"
            )
    return all_by_uid, unique(ours, "uid", "our"), unique(ours, "title", "our")


def existing_rules(token: str) -> dict[str, dict]:
    """uid -> the live rule, for rules in OUR folder and group only.

    Scoped deliberately. The stack carries hundreds of rules belonging to the organisation's own teams; this tool
    must be incapable of updating one of them even if a uid collision appears in malformed live state.
    """
    _all_by_uid, ours_by_uid, _ours_by_title = _rule_indexes(token)
    return ours_by_uid


# --- Title migration (PLAN 18.8) ------------------------------------------------------------------
#
# Historical migration for rules created before `RULE_UIDS` made uid the normal update identity. The
# old publisher keyed on title, so changing a title in the source and running `--publish` created a new
# paused, unrouted rule and left the old one live and routed.
#
# So a rename is a uid-keyed migration, and it PUTs the LIVE rule body back with only `title` changed -
# not a rebuilt rule. That is deliberate: rebuilding would also re-apply whatever the source now says
# about pausing and routing, which is exactly the regression `preserve_live_state` exists to prevent.
#
# Entries are removed once the migration has run everywhere it needs to. A stale entry is harmless -
# the old title simply is not there - but it is dead weight, and `--migrate-titles` reports what it
# could not find so the difference is visible rather than assumed.
RENAMED_TITLES: dict[str, str] = {
    "Estate insights - t1 scan is stale": "Estate insights: t1 scan is stale",
    "Estate insights - t2 scan is stale": "Estate insights: t2 scan is stale",
    "Estate insights - t3 scan is stale": "Estate insights: t3 scan is stale",
    "Estate insights - t4 scan is stale": "Estate insights: t4 scan is stale",
    "Estate insights - scan coverage below floor": "Estate insights: scan coverage below floor",
    "Estate insights - an input is unavailable and views are being withheld":
        "Estate insights: an input is unavailable and views are being withheld",
    "Estate insights - a stack has been without its Assistant credential for 48h":
        "Estate insights: a stack has been without its Assistant credential for 48h",
}


def migrate_titles(token: str, *, dry_run: bool = False) -> int:
    """Rename in place, keyed on uid. Preserves pause, routing and every other field verbatim."""
    _all_by_uid, _ours_by_uid, have = _rule_indexes(token)
    failures = 0
    for old, new in RENAMED_TITLES.items():
        if old not in have:
            print(f"  skipped (not present): {old}")
            continue
        if new in have:
            # Both titles live means a --publish already created the new one. Renaming now would collide,
            # and silently deleting either is not this tool's call.
            print(f"  REFUSED: both {old!r} and {new!r} exist. A --publish has already created the new "
                  f"rule; delete whichever is wrong by hand and re-run.", file=sys.stderr)
            failures += 1
            continue
        live = have[old]
        uid = live["uid"]
        if dry_run:
            print(f"  would rename {uid}: {old!r} -> {new!r} "
                  f"(isPaused={live.get('isPaused')}, routing="
                  f"{(live.get('notification_settings') or {}).get('receiver')})")
            continue
        code, body = _api("PUT", f"/api/v1/provisioning/alert-rules/{uid}", token,
                          {**live, "title": new})
        if code in (200, 201, 202):
            print(f"  renamed {uid}: {old!r} -> {new!r}")
        else:
            failures += 1
            print(f"  FAILED ({code}): {old}\n    {str(body)[:400]}", file=sys.stderr)
    return failures


def publish(token: str, *, paused: bool = True, receiver: str | None = None,
            preserve_live_state: bool = False) -> int:
    """Create or update every rule. `preserve_live_state` keeps an EXISTING rule's pause and routing.

    That flag exists because of a real regression, caused on 2026-08-20 by this tool. A plain
    `--publish` - the thing you run after adding a rule - rebuilds every rule with `paused=True` and
    `notification_settings=None` and PUTs them, so the five rules that had been live and routed since
    2026-08-18 were silently paused and unrouted. Nothing failed and nothing said so: the output read
    `updated: ...` seven times and the platform simply stopped alerting.

    The two defaults have to differ, and this is why: for a NEW rule, paused-and-unrouted is the safety
    property (every staleness rule is legitimately in breach before its tier has run, and an unrouted
    unpaused rule inherits the stack's notification policy). For an EXISTING rule, changing
    its live state is not this command's job - `--activate` and `--deactivate` are, and they say so.
    """
    all_by_uid, have, have_by_title = _rule_indexes(token)
    rules = build_all(paused=paused, receiver=receiver)

    # `--migrate-titles` preserves the original live uid by design. A later normal publish must adopt
    # exactly those explicit migrations or it will reject the healthy migrated rule as an orphan. This
    # is deliberately narrower than title identity: arbitrary matching titles remain untrusted.
    migrated_titles = set(RENAMED_TITLES.values())
    adopted: list[dict] = []
    for rule in rules:
        canonical_uid = rule["uid"]
        live = have_by_title.get(rule["title"])
        if (
            live is not None
            and live["uid"] != canonical_uid
            and rule["title"] in migrated_titles
            and canonical_uid not in all_by_uid
        ):
            rule = {**rule, "uid": live["uid"]}
        adopted.append(rule)
    rules = adopted
    expected_by_uid = {rule["uid"]: rule for rule in rules}
    if len(expected_by_uid) != len(rules):
        raise SystemExit("REFUSED: build_all produced duplicate alert-rule uids")

    # Finish the complete identity/blast-radius preflight before the first PUT or POST. A partial update
    # followed by discovering an orphan would be worse than refusing the run: some rules would have new
    # source while another still evaluated the old definition.
    foreign = sorted(uid for uid in expected_by_uid if uid in all_by_uid and uid not in have)
    if foreign:
        raise SystemExit(
            "REFUSED: expected alert-rule uid(s) exist outside our folder/group: " + ", ".join(foreign)
        )
    unexpected = sorted(set(have) - set(expected_by_uid))
    if unexpected:
        details = ", ".join(f"{uid} ({have[uid].get('title')!r})" for uid in unexpected)
        raise SystemExit(
            "REFUSED: unrecognised rule(s) exist in our folder/group, possibly title-publish orphans: "
            + details
        )
    wrong_uid = [
        (rule["title"], have_by_title[rule["title"]]["uid"], uid)
        for uid, rule in expected_by_uid.items()
        if rule["title"] in have_by_title and have_by_title[rule["title"]]["uid"] != uid
    ]
    if wrong_uid:
        details = ", ".join(f"{title!r}: live {live_uid}, expected {expected_uid}"
                            for title, live_uid, expected_uid in wrong_uid)
        raise SystemExit("REFUSED: rule title exists at the wrong uid; explicit adoption required: " + details)

    failures = 0
    kept: list[str] = []
    for rule in rules:
        uid = rule["uid"]
        title = rule["title"]
        if uid in have:
            live = have[uid]
            if preserve_live_state:
                # _rule_indexes has already proved these fields are present and correctly typed.
                # Indexing rather than `.get()` keeps that invariant visible at the use site.
                was_paused = live["isPaused"]
                was_routing = live["notification_settings"]
                if was_paused != rule["isPaused"] or was_routing != rule.get("notification_settings"):
                    kept.append(title)
                rule = {**rule, "isPaused": was_paused, "notification_settings": was_routing}
            code, body = _api("PUT", f"/api/v1/provisioning/alert-rules/{uid}", token, {**rule, "uid": uid})
            verb = "updated"
        else:
            code, body = _api("POST", "/api/v1/provisioning/alert-rules", token, rule)
            verb = "created"
        if code in (200, 201, 202):
            print(f"  {verb}: {title}")
        else:
            failures += 1
            print(f"  FAILED ({code}): {title}\n    {str(body)[:400]}", file=sys.stderr)

    if kept:
        print(f"  kept the live pause/routing state of {len(kept)} existing rule(s): "
              f"{', '.join(sorted(kept))}")
    if not failures:
        # The evaluation interval belongs to the GROUP, not the rule, so it needs its own call. Left at
        # Grafana's default the group evaluates every minute, which is 60x more often than the fastest
        # thing it watches can change.
        code, body = _api(
            "PUT",
            f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/{RULE_GROUP}",
            token,
            {"title": RULE_GROUP, "folderUid": FOLDER_UID, "interval": GROUP_INTERVAL_SECONDS},
        )
        if code in (200, 202):
            print(f"  group interval: {GROUP_INTERVAL_SECONDS}s")
        else:
            print(f"  WARNING: could not set group interval ({code}): {str(body)[:200]}", file=sys.stderr)
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print titles and expressions, publish nothing")
    ap.add_argument("--contact-points", action="store_true", help="list the stack's contact points and exit")
    ap.add_argument("--out", help="write the rule JSON to this directory, publish nothing")
    ap.add_argument("--publish", action="store_true", help="create or update the rules on the stack (PAUSED)")
    ap.add_argument(
        "--activate",
        action="store_true",
        help="publish the rules UNPAUSED. Requires --receiver. Only after the schedules are enabled and "
             "one run of each tier has landed - before that every rule is legitimately in breach.",
    )
    ap.add_argument(
        "--migrate-titles",
        action="store_true",
        help="run the historical pre-RULE_UIDS title migration, keyed on uid and preserving pause and "
             "routing. New title changes are handled safely by an ordinary uid-keyed --publish.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="with --migrate-titles, print what would be renamed and change nothing",
    )
    ap.add_argument(
        "--deactivate",
        action="store_true",
        help="publish the rules PAUSED and UNROUTED, including ones that are currently live. The "
             "deliberate opposite of --activate; a plain --publish leaves an existing rule's live state "
             "alone.",
    )
    ap.add_argument(
        "--receiver",
        help="contact point these rules notify. Mandatory with --activate: leaving it unset makes the "
             "rules inherit the stack's notification policy, which may reach unrelated ticketing or "
             "on-call receivers.",
    )
    args = ap.parse_args(argv)

    try:
        identity.verify_runtime_projection("alerts")
    except identity.InvalidIdentity as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.activate and args.deactivate:
        print("error: --activate and --deactivate cannot be combined", file=sys.stderr)
        return 2
    if args.deactivate and args.receiver:
        print("error: --deactivate cannot be combined with --receiver", file=sys.stderr)
        return 2
    if args.dry_run and (args.publish or args.activate or args.deactivate):
        print(
            "error: --dry-run is implemented only for --migrate-titles; "
            "it cannot be combined with --publish, --activate, or --deactivate",
            file=sys.stderr,
        )
        return 2

    paused = not args.activate
    # State-changing modes imply --publish. Without this they fall through to the read-only listing and
    # print a routing line that looks like it was applied.
    if args.activate or args.deactivate:
        args.publish = True
    if args.activate and not args.receiver:
        print(
            "error: --activate requires --receiver.\n"
            "  An unpaused rule with no notification_settings inherits the stack's notification policy.\n"
            "  On a live customer stack that can raise a real ticket or page a real rota because our\n"
            "  scanner was late. Name the contact point the deployment owner nominated for this platform.\n"
            "  List the options with: python3 bin/alerts.py --contact-points",
            file=sys.stderr,
        )
        return 2

    # Every network mode names a live write target. Refuse before building or calling Grafana when
    # either half is absent; a guessed folder uid can place rules beside somebody else's alerting.
    if args.publish or args.migrate_titles or args.contact_points:
        required = [
            ("GCINSIGHT_WRITE_STACK_URL", BASE, "e.g. https://<slug>.grafana.net"),
        ]
        if args.publish or args.migrate_titles:
            required.append((
                "GCINSIGHT_INSIGHTS_FOLDER_UID", FOLDER_UID,
                "uid of the folder these rules live in",
            ))
        for var, value, purpose in required:
            if not value:
                print(f"error: {var} is not set ({purpose})", file=sys.stderr)
                return 2
    rules = build_all(paused=paused, receiver=args.receiver)

    if args.migrate_titles:
        token = os.environ.get("GCINSIGHT_GRAFANA_TOKEN", "").strip()
        if not token:
            print("error: GCINSIGHT_GRAFANA_TOKEN is not set", file=sys.stderr)
            return 2
        return 1 if migrate_titles(token, dry_run=args.dry_run) else 0

    if args.contact_points:
        token = os.environ.get("GCINSIGHT_GRAFANA_TOKEN", "").strip()
        if not token:
            print("error: GCINSIGHT_GRAFANA_TOKEN is not set", file=sys.stderr)
            return 2
        for name in contact_points(token):
            print(f"  {name}")
        return 0

    if args.list or not (args.out or args.publish):
        for r in rules:
            print(f"\n{r['title']}")
            print(f"  labels    {r['labels']}")
            print(f"  noData    {r['noDataState']}   for {r['for']}")
            ns = r.get("notification_settings")
            print(f"  routing   {ns['receiver'] if ns else 'NONE (rule stays paused; would inherit the stack policy if unpaused)'}")
            print(f"  expr      {r['data'][0]['model']['expr']}")
            cond = r["data"][1]["model"]["conditions"][0]["evaluator"]
            print(f"  condition {cond['type']} {cond['params'][0]}")
        print(f"\n{len(rules)} rules, folder {FOLDER_UID}, group {RULE_GROUP}")
        print(f"paused: {paused}" + ("" if paused else "  <-- these will fire immediately if stale"))
        return 0

    if args.out:
        d = pathlib.Path(args.out)
        d.mkdir(parents=True, exist_ok=True)
        for r in rules:
            # Drop title separators BEFORE collapsing spaces. Doing it afterwards leaves punctuation
            # embedded in filenames because there are no spaces left to match on.
            slug = (r["title"].lower().replace(" - ", " ").replace(": ", " ")
                    .replace(" ", "-"))
            (d / f"{slug}.json").write_text(json.dumps(r, indent=2))
        print(f"wrote {len(rules)} rules to {d}")
        return 0

    token = os.environ.get("GCINSIGHT_GRAFANA_TOKEN", "").strip()
    if not token:
        print("error: GCINSIGHT_GRAFANA_TOKEN is not set (build-time Grafana token, alerting write)", file=sys.stderr)
        return 2
    if args.receiver:
        available = contact_points(token)
        if args.receiver not in available:
            print(
                f"error: contact point {args.receiver!r} does not exist on this stack.\n"
                "  Available: " + ", ".join(available),
                file=sys.stderr,
            )
            return 2
    # A plain `--publish` must not change the live state of a rule that already exists - it silently
    # paused and unrouted five live rules once. `--activate` and `--deactivate` are the commands that
    # change live state, and they pass through here with the flag off.
    rc = publish(token, paused=paused, receiver=args.receiver,
                 preserve_live_state=paused and not args.deactivate)
    if paused:
        print(
            "\nNEW rules published PAUSED and UNROUTED; existing rules kept whatever pause and routing "
            "they already had. Unpause with `--activate --receiver <contact point>` once the schedules "
            "are enabled and one run of each tier has landed - until then the staleness rules are "
            "correctly in breach.",
            file=sys.stderr,
        )
    return 1 if rc else 0


if __name__ == "__main__":
    raise SystemExit(main())
