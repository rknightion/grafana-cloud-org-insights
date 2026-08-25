#!/usr/bin/env python3
"""the organisation estate insight scan.

    ./scan.py --tier t1 --dry-run                       # inventory only, writes nothing
    ./scan.py --tier t2 --dry-run --limit 5             # bounded local diagnostic
    ./scan.py --tier t2 --dry-run --stack obs-hub     # one-stack local diagnostic

Production/manual publishing runs happen only through the deployed ECS task definitions; see RUNBOOK.md.

Credential comes from `GCINSIGHT_ORG_CAP` in the environment. See SPEC.md for the tier model.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Any

from collector import config, ratecard
from collector.coverage import FAILURE_ABORT_RATIO, Coverage
from collector.emit import (carry, diff, gapstate, guard, hydrate, lock as scanlock, loki, mimir,
                            s3 as s3emit)
from collector.httpclient import ReadOnlyClient
from collector.resolver import InstanceResolver
from collector.pillars import ai as ai_pillar, compose, findings as findings_mod
from collector import credentials
from collector.sources import adaptive_logs as adaptive_logs_src
from collector.sources import alert_routing as alert_routing_src
from collector.sources import public_dashboards as public_dashboards_src
from collector.sources import stack_catalog
from collector.sources import assistant as assistant_src
from collector.sources import fleet as fleet_src
from collector.sources import serviceaccounts as sa_src
from collector.sources import signal_inventory as signal_inventory_src
from collector.sources import capability_adoption as capability_adoption_src
from collector.sources import usage_insights, dataplane, gcom

TIERS = ("t1", "t2", "t3", "t4")
RATECARD_KEY = "config/ratecard.csv"
LOG_LEVELS = frozenset({"info", "warn", "error"})
SUMMARY_KEYS = (
    "tier", "generated_at", "org_id", "scan_healthy", "sources_healthy",
    "stacks_total", "stacks_scannable", "stacks_scanned", "stacks_failed",
    "stacks_skipped", "coverage_ratio", "requests", "retries", "series_emitted",
    "duration_seconds", "mimir_push_failed", "loki_push_failed",
)


class RateCardReadFailed(RuntimeError):
    """The optional card was not absent; its configured object could not be read."""


def console_log(level: str, message: str, **fields: Any) -> None:
    """Write one structured record to the ECS console stream."""
    if level not in LOG_LEVELS:
        raise ValueError(f"invalid console log level {level!r}")
    print(
        json.dumps({"level": level, "message": message, **fields}, separators=(",", ":"), default=str),
        file=sys.stderr,
    )


class StructuredArgumentParser(argparse.ArgumentParser):
    """Keep malformed ECS invocations inside the one-record console-log contract."""

    def error(self, message: str) -> None:
        console_log("error", f"argument error: {message}")
        raise SystemExit(2)


def scan_completion_level(meta: dict[str, Any]) -> str:
    """Classify a completed scan without treating T4's intentional 0/0 coverage as partial."""
    if meta.get("scan_healthy") is False:
        return "error"
    scannable = int(meta.get("stacks_scannable") or 0)
    if scannable and float(meta.get("coverage_ratio") or 0) < 1.0:
        return "warn"
    return "info"


def scan_completion_record(meta: dict[str, Any]) -> dict[str, Any]:
    record = {"event": "scan_complete", "level": scan_completion_level(meta)}
    record.update({key: meta.get(key) for key in SUMMARY_KEYS})
    return record


def _verified_ecs_runtime() -> bool:
    """Prove this process can read its link-local ECS container metadata.

    An environment variable name alone is trivial to copy into a local shell and therefore cannot be
    the boundary protecting customer-facing publication. Fargate injects a link-local URI whose JSON
    names the running ECS container; require both the authoritative host and that live response.
    """
    uri = (os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
           or os.environ.get("ECS_CONTAINER_METADATA_URI") or "")
    try:
        parsed = urllib.parse.urlsplit(uri)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"169.254.170.2", "fd00:ec2::23"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or not parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return False
        with urllib.request.urlopen(uri, timeout=1.0) as response:  # noqa: S310 - fixed link-local host
            payload = json.load(response)
    except Exception:  # noqa: BLE001 - any metadata ambiguity must fail closed
        return False
    if not isinstance(payload, dict):
        return False
    arn = payload.get("ContainerARN")
    parts = arn.split(":", 5) if isinstance(arn, str) else []
    return len(parts) == 6 and parts[0] == "arn" and parts[2] == "ecs" \
        and parts[5].startswith("container/")


def load_ratecard(
    *, bucket: str = s3emit.BUCKET, runner: Any = subprocess.run
) -> ratecard.RateCard | None:
    """Load the deployment's optional card, distinguishing absence from an unreadable object."""
    uri = f"s3://{bucket}/{RATECARD_KEY}"
    try:
        head = runner(
            ["aws", "s3api", "head-object", "--bucket", bucket, "--key", RATECARD_KEY,
             "--region", s3emit.REGION],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise RateCardReadFailed(
            f"{uri}: head-object timed out after {exc.timeout}s"
        ) from exc
    except OSError as exc:
        raise RateCardReadFailed(f"{uri}: could not run head-object: {exc}") from exc
    if head.returncode != 0:
        error = (head.stderr or "").strip()
        if any(marker in error for marker in ("(404)", "NoSuchKey", "Not Found")):
            return None
        raise RateCardReadFailed(
            f"{uri}: could not determine whether the rate card exists: {error}"
        )

    try:
        fetched = runner(
            ["aws", "s3", "cp", uri, "-", "--region", s3emit.REGION, "--only-show-errors"],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise RateCardReadFailed(f"{uri}: read timed out after {exc.timeout}s") from exc
    except OSError as exc:
        raise RateCardReadFailed(f"{uri}: could not run read: {exc}") from exc
    if fetched.returncode != 0:
        raise RateCardReadFailed(f"{uri}: {(fetched.stderr or '').strip()}")
    try:
        return ratecard.loads(fetched.stdout)
    except ratecard.InvalidRateCard as exc:
        raise ratecard.InvalidRateCard(f"{uri}: {exc}") from exc


def envelope(cfg: config.Config, coverage: Coverage, data: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "tier": cfg.tier,
            "org_id": cfg.org_id,
            **coverage.as_meta(),
            **(extra or {}),
        },
        "data": data,
    }


def source_report(
    expected: int,
    data: dict[str, Any],
    *,
    available: Any,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Coverage for one independently-failing source inside a tier.

    T2 is not one read: gcom detail can cover the whole estate while every stack-local source is
    unavailable.  Keeping those populations separate avoids corrupting `Coverage` while still making
    a source-wide failure part of the scan's health and exit status.
    """
    measured = min(expected, sum(1 for record in data.values() if available(record)))
    missing = max(0, expected - measured)
    ratio = (measured / expected) if expected else 1.0
    return {
        "expected": expected,
        "available": measured,
        "unavailable": missing,
        "coverage_ratio": round(ratio, 4),
        "healthy": not expected or (missing / expected) <= FAILURE_ABORT_RATIO,
        "error_count": len(errors or []),
        "error_samples": list(errors or [])[:10],
    }


def publication_inputs(
    gathered: dict[str, dict[str, Any]],
    sources: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    """Split independently gathered inputs at the publication floor.

    A non-empty mapping proves only that *something* answered. It does not make an estate input safe:
    one success and 268 refusals would otherwise be composed, saved as the owner's latest input, and
    hydrated by T1 as a fresh estate total. Inputs below the source-health floor are therefore omitted
    both from composition and from the scan envelope. Their current failure remains explicit in
    provenance and `meta.sources`, while the previous good S3 views are left untouched.
    """
    accepted: dict[str, dict[str, Any]] = {}
    unavailable: dict[str, dict[str, str]] = {}
    for name, payload in gathered.items():
        report = sources.get(name)
        if report is None or report.get("healthy"):
            accepted[name] = payload
            continue
        measured = int(report.get("available") or 0)
        expected = int(report.get("expected") or 0)
        state = "partial" if measured else "unavailable"
        unavailable[name] = {
            "state": state,
            "reason": (
                f"{state}: {measured} of {expected} {report.get('unit') or 'stacks'} available "
                f"({float(report.get('coverage_ratio') or 0):.1%}), below the publication floor"
            ),
        }
    return accepted, unavailable


def gather_assistant(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """Per-stack Assistant reads (PLAN 17E). T2 only  -  it is T2's second gatherer.

    Runs against `<slug>.grafana.net`, one host per tenant, so it never touches gcom's 6 req/s cap.
    Measured on the full estate 2026-08-20: 2,153 requests, every one HTTP 200, zero retries, 54s.

    **Deliberately does NOT write to the tier's `Coverage`.** T2's coverage means "did we get this
    stack's gcom detail", and `gcom.fetch_all_stack_detail` has already recorded ok/failure for the same
    slugs against the same object  -  a second source recording against it would push `scanned + skipped`
    past `total` and make `coverage_ratio` mean two things at once. A stack awaiting its credential is a
    PROVISIONING state, and it has its own gauge, its own view and its own alert.
    """
    errors: list[str] = []
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        # NOT "the whole estate is missing its credential". That would fire the coverage alert on 273
        # stacks and publish an estate of zeros, from what is really one IAM or network failure.
        console_log(
            "error",
            f"assistant: credential store unreadable  -  {exc}. Skipping the Assistant sweep; the "
            f"views it feeds are WITHHELD rather than published empty.",
        )
        return {}, [f"credential store: {exc}"]
    console_log("info", f"assistant: {len(creds)} stored credential(s) for {len(stacks)} stacks")
    data = assistant_src.probe_all(
        client, stacks, creds, concurrency=cfg.concurrency,
        on_error=lambda slug, msg: errors.append(f"{slug}: {msg}"),
    )
    reasons: dict[str, int] = {}
    for record in data.values():
        if not record.get("available"):
            reasons[record["reason"]] = reasons.get(record["reason"], 0) + 1
    console_log(
        "warn" if reasons or errors else "info",
        f"assistant: {len([r for r in data.values() if r.get('available')])} of {len(data)} stacks "
        f"returned data" + (f", not available: {reasons}" if reasons else ""),
    )
    return data, errors


def gather_adaptive_logs(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """T2's fourth gatherer: Adaptive Logs recommendations (PLAN 18.16).

    One GET per stack against that stack's OWN app-plugin proxy, so 269 requests hit 269 different hosts
    and gcom's 6 req/s cap does not apply. Measured on the full estate: 269 of 269 available, zero
    failures, 185s.

    Same `Coverage` abstention as `gather_assistant`, and for the same reason - T2's coverage already
    means "did gcom give us this stack's detail", and a second writer would make `coverage_ratio` mean
    two things at once.
    """
    errors: list[str] = []
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        console_log(
            "error",
            f"adaptive_logs: credential store unreadable  -  {exc}. Skipping the sweep; the views it "
            f"feeds are WITHHELD rather than published empty.",
        )
        return {}, [f"credential store: {exc}"]
    data = adaptive_logs_src.probe_all(
        client, stacks, creds,
        on_error=lambda slug, msg: errors.append(f"{slug}: {msg}"),
    )
    ok = [r for r in data.values() if r.get("available")]
    reasons: dict[str, int] = {}
    for record in data.values():
        if not record.get("available"):
            reasons[record["reason"]] = reasons.get(record["reason"], 0) + 1
    console_log(
        "warn" if reasons or errors else "info",
        f"adaptive_logs: {len(ok)} of {len(data)} stacks returned data, "
        f"{len([r for r in ok if r.get('recommendations')])} carry recommendations"
        + (f", not available: {reasons}" if reasons else ""),
    )
    return data, errors


def gather_public_dashboards(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """T2's fifth gatherer: public-dashboard ENUMERATION (PLAN 18.17).

    One GET per stack against that stack's own API. Measured on the full estate: 269 stacks in 94s,
    zero failures, 34 public dashboards found across 15 stacks against the organisation policy of zero.

    **The endpoint answers 200 with a permission-filtered list rather than 403**, so an unreadable stack
    must never be folded in as a compliant zero. `pillars/risk.py` adds up only the stacks whose state
    is `ok` and publishes the denominator beside the count.
    """
    errors: list[str] = []
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        console_log(
            "error",
            f"public_dashboards: credential store unreadable  -  {exc}. Skipping the enumeration; "
            f"Pillar E reports it as NOT MEASURED rather than as zero.",
        )
        return {}, [f"credential store: {exc}"]
    data = public_dashboards_src.probe_all(
        client, stacks, creds,
        on_error=lambda slug, msg: errors.append(f"{slug}: {msg}"),
    )
    ok = [r for r in data.values() if r.get("available")]
    found = sum(r.get("total") or 0 for r in ok)
    console_log(
        "warn" if errors or len(ok) < len(data) else "info",
        f"public_dashboards: {len(ok)} of {len(data)} stacks read, {found} public dashboard(s) "
        f"across {len([r for r in ok if r.get('total')])} stack(s)",
    )
    return data, errors


def gather_alert_routing(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """T2 stack-local alert-rule to contact-point routing inventory.

    Two read-only GETs per readable stack. A source-wide credential-store failure withholds the views
    and fails T2 source health; it is never converted into an estate of inherited or missing routes.
    """
    errors: list[str] = []
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        console_log(
            "error",
            f"alert routing: credential store unreadable  -  {exc}. Skipping the sweep; the routing "
            f"views are WITHHELD rather than published empty.",
        )
        return {}, [f"credential store: {exc}"]
    data = alert_routing_src.probe_all(
        client, stacks, creds,
        on_error=lambda slug, msg: errors.append(f"{slug}: {msg}"),
    )
    ok = [record for record in data.values() if record.get("available")]
    console_log(
        "warn" if errors or len(ok) < len(data) else "info",
        f"alert routing: {len(ok)}/{len(data)} stacks readable, "
        f"{sum(r.get('rules_total') or 0 for r in ok)} rules, "
        f"{sum(r.get('rules_active_missing_receiver') or 0 for r in ok)} active missing receivers",
    )
    return data, errors


def gather_fleet(
    cfg: config.Config, stacks: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """T1's second gatherer: Fleet Management collectors and pipelines (PLAN 18.15).

    Hourly rather than 6-hourly because a collector fleet changes by the minute. It runs against
    per-stack Fleet Management hosts, so it shares no rate limit with gcom, and each stack costs exactly
    two Connect-RPC `List*` calls.

    **Deliberately does NOT write to the tier's `Coverage`.** T1's coverage means "did we get the
    inventory", which is one call for the whole estate. A per-stack source recording against the same
    object would make `coverage_ratio` mean two things at once. A stack with no Fleet Management URL is
    not a failure; it is a stack not using Fleet Management.
    """
    errors: list[str] = []
    data = fleet_src.probe_all(
        stacks, cfg.cap, on_error=lambda slug, msg: errors.append(f"{slug}: {msg}"))
    live = [d for d in data.values() if d.get("available")]
    collectors = sum(d.get("collectors") or 0 for d in live)
    active = sum(d.get("collectors_active") or 0 for d in live)
    unparsed = sum(d.get("matchers_unparsed") or 0 for d in live)
    console_log(
        "warn" if errors or unparsed else "info",
        f"fleet: {len(live)}/{len(data)} stacks answered, {collectors} registrations "
        f"({active} active, {collectors - active} inactive), {unparsed} unparsed matcher(s)",
    )
    return data, errors


def gather_service_accounts(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """T2's service-account input, kept separate from `stack_detail` (PLAN 18.13).

    Service accounts come from a different host, credential and RBAC action than gcom detail.  Merging
    the result into `stack_detail` let a fresh identity sweep mask a failed service-account sweep during
    hydration.  The scan envelope therefore preserves the source's native per-stack result separately.

    Same coverage rule as the Assistant sweep: this does NOT write to the tier's `Coverage`. T2's
    coverage means "did we get this stack's gcom detail", and a second source recording against the
    same slugs would push `scanned + skipped` past `total`.
    """
    errors: list[str] = []
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        # One IAM or network failure is not "the estate has no service accounts". Leave every record at
        # `not_gathered` so Pillar E says so, rather than publishing an inventory of zero.
        console_log(
            "error",
            f"service accounts: credential store unreadable  -  {exc}. Leaving the inventory "
            f"ungathered; Pillar E reports it as not measured rather than as empty.",
        )
        return {}, [f"credential store: {exc}"]
    data = sa_src.probe_all(
        client, stacks, creds, on_error=lambda slug, msg: errors.append(f"{slug}: {msg}")
    )
    ok = sum(1 for r in data.values() if r["state"] == sa_src.OK)
    total = sum(len(r["accounts"]) for r in data.values())
    console_log(
        "warn" if errors or ok < len(data) else "info",
        f"service accounts: {ok}/{len(data)} stacks readable, {total} accounts",
    )
    return data, errors


def gather_insights(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """Per-stack usage-insights reads (Pillar J). T2 only  -  T2's third gatherer.

    Queries each stack's own `grafanacloud-usage-insights` datasource through that stack's datasource
    proxy, with that stack's read-only credential. One host per tenant, so gcom's 6 req/s ceiling does
    not apply. Every query is a LogQL metric expression, so the response is a handful of numbers however
    much a stack ingests.

    **Does NOT write to the tier's `Coverage`**, for the same reason the Assistant sweep does not: T2's
    coverage means "did we get this stack's gcom detail", and a second source recording against the same
    object would push `scanned + skipped` past `total`. Insight coverage is its own view.
    """
    errors: list[str] = []
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        # One IAM or network failure, not an estate with no credentials. Publishing the latter would
        # blank every Pillar J panel and read as "nobody looks at any dashboard".
        console_log(
            "error",
            f"insights: credential store unreadable  -  {exc}. Skipping the usage-insights sweep; the "
            f"views it feeds are WITHHELD rather than published empty.",
        )
        return {}, [f"credential store: {exc}"]
    console_log("info", f"insights: {len(creds)} stored credential(s) for {len(stacks)} stacks")
    data = usage_insights.probe_all(
        stacks, creds, concurrency=cfg.concurrency, client=client,
        on_error=lambda slug, msg: errors.append(f"{slug}: {msg}"),
    )
    reasons: dict[str, int] = {}
    for record in data.values():
        if not record.get("available"):
            reasons[record["reason"]] = reasons.get(record["reason"], 0) + 1
    console_log(
        "warn" if reasons or errors else "info",
        f"insights: {len([r for r in data.values() if r.get('available')])} of {len(data)} stacks "
        f"returned data" + (f", not available: {reasons}" if reasons else ""),
    )
    return data, errors


def gather_signal_inventory(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Daily atomic label inventory across all four signal databases using the org CAP."""
    errors: list[str] = []
    data = signal_inventory_src.probe_all(
        client, stacks, cfg.cap, concurrency=cfg.concurrency,
        on_error=lambda slug, msg: errors.append(f"{slug}: {msg}"),
    )
    available = [record for record in data.values() if record.get("available")]
    reasons: dict[str, int] = {}
    for record in data.values():
        if not record.get("available"):
            reason = str(record.get("reason") or "unknown")
            reasons[reason] = reasons.get(reason, 0) + 1
    console_log(
        "warn" if errors or len(available) < len(data) else "info",
        f"signal inventory: {len(available)}/{len(data)} stacks measured"
        + (f", not available: {reasons}" if reasons else ""),
    )
    return data, errors


def gather_capability_adoption(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """One bounded org-usage read through the write stack's narrowly scoped reader."""
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        console_log(
            "error",
            f"capability adoption: credential store unreadable - {exc}. The opportunity views are "
            f"WITHHELD rather than published as an estate of zero.",
        )
        return {}, [f"credential store: {exc}"]
    record = capability_adoption_src.probe(
        client, stacks, creds, write_stack=cfg.write_stack,
    )
    errors = [] if record.get("available") else [
        f"{record.get('reason')}: {record.get('detail', '')}".strip()
    ]
    console_log(
        "info" if record.get("available") else "error",
        "capability adoption: org usage input available"
        if record.get("available") else f"capability adoption: unavailable - {errors[0]}",
    )
    return record, errors


def gather_dashboard_inventory(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Complete dashboard catalogue joined to the independently measured 31-day opening set."""
    errors: list[str] = []
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        return {}, [f"credential store: {exc}"]
    catalog = stack_catalog.probe_dashboards_all(
        client, stacks, creds, concurrency=cfg.concurrency,
        on_error=lambda slug, msg: errors.append(f"{slug}: dashboard inventory: {msg}"),
    )
    activity = usage_insights.probe_dashboard_activity_all(
        stacks, creds, concurrency=cfg.concurrency, client=client,
        on_error=lambda slug, msg: errors.append(f"{slug}: dashboard activity: {msg}"),
    )
    merged: dict[str, Any] = {}
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        inventory = catalog.get(slug) or {}
        observed = activity.get(slug) or {}
        if not inventory.get("available"):
            merged[slug] = inventory or {
                "slug": slug, "available": False, "reason": "not_measured",
                "detail": "dashboard catalogue returned no record",
            }
            continue
        merged[slug] = {
            "slug": slug,
            "available": True,
            "window": usage_insights.ACTIVITY_WINDOW,
            "dashboards": inventory.get("dashboards") or [],
            "activity_available": bool(observed.get("available")),
            "activity_reason": "" if observed.get("available") else observed.get("reason", "not_measured"),
            "activity_detail": "" if observed.get("available") else observed.get("detail", ""),
            "opened": observed.get("opened") or [],
        }
    known = sum(len(record.get("dashboards") or []) for record in merged.values()
                if record.get("available"))
    measured = sum(1 for record in merged.values() if record.get("activity_available"))
    console_log(
        "warn" if errors or measured < len(merged) else "info",
        f"dashboard inventory: {known} dashboards; 31-day activity measured on "
        f"{measured}/{len(merged)} stacks",
    )
    return merged, errors


def gather_datasource_query_cost(
    client: ReadOnlyClient, cfg: config.Config, stacks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Bounded per-stack query cost joined to the read-only datasource catalogue."""
    errors: list[str] = []
    try:
        creds = credentials.load_all()
    except credentials.StoreUnavailable as exc:
        return {}, [f"credential store: {exc}"]
    catalog = stack_catalog.probe_datasources_all(
        client, stacks, creds, concurrency=cfg.concurrency,
        on_error=lambda slug, msg: errors.append(f"{slug}: datasource inventory: {msg}"),
    )
    costs = usage_insights.probe_datasource_cost_all(
        stacks, creds, concurrency=cfg.concurrency, client=client,
        on_error=lambda slug, msg: errors.append(f"{slug}: datasource query cost: {msg}"),
    )
    merged: dict[str, Any] = {}
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            continue
        measured = costs.get(slug) or {}
        inventory = catalog.get(slug) or {}
        if not measured.get("available"):
            merged[slug] = measured or {
                "slug": slug, "available": False, "reason": "not_measured",
                "detail": "query-cost source returned no record",
            }
            continue
        # A cost-bearing UID without its datasource name is not the approved product. A catalogue
        # failure must therefore make this stack UNKNOWN, not publish an opaque identifier as though
        # it were an actionable measured finding. A UID missing from an otherwise successful catalogue
        # is retained below because it can legitimately name a datasource deleted after the query event.
        if not inventory.get("available"):
            inventory_reason = str(inventory.get("reason") or "datasource_inventory_unavailable")
            inventory_detail = str(inventory.get("detail") or "datasource inventory returned no record")
            merged[slug] = {
                "slug": slug,
                "available": False,
                "reason": inventory_reason,
                "detail": f"datasource inventory: {inventory_detail}",
            }
            continue
        merged[slug] = {
            "slug": slug,
            "available": True,
            "window": usage_insights.WINDOW,
            "costs": measured.get("costs") or [],
            "inventory_available": bool(inventory.get("available")),
            "inventory_reason": "" if inventory.get("available") else inventory.get("reason", "not_measured"),
            "inventory_detail": "" if inventory.get("available") else inventory.get("detail", ""),
            "datasources": inventory.get("datasources") or [],
        }
    retained = sum(len(record.get("costs") or []) for record in merged.values()
                   if record.get("available"))
    available = sum(1 for record in merged.values() if record.get("available"))
    console_log(
        "warn" if errors or available < len(merged) else "info",
        f"datasource query cost: {retained} bounded rows across {available}/{len(merged)} stacks",
    )
    return merged, errors


def assistant_gaps(
    cfg: config.Config, stacks: list[dict[str, Any]], assistant: dict[str, Any] | None, *, gathered: bool
) -> dict[str, str]:
    """First-seen stamps for the credential gaps, so the coverage alert can watch an AGE (PLAN 17D).

    `gathered` is the whole point. Only the tier that actually MEASURED the estate may stamp a new gap or
    clear a healed one; a tier working from a hydrated payload up to three days old would resurrect a gap
    the provisioner has already fixed, and the alert would never clear.
    """
    if not assistant:
        return {}
    if not gathered:
        return gapstate.load(bucket=s3emit.BUCKET)
    missing = ai_pillar.missing_slugs(stacks, assistant, cfg.opt_out)
    state = gapstate.update(missing, bucket=s3emit.BUCKET, dry_run=cfg.dry_run)
    if missing:
        console_log(
            "warn",
            f"assistant: {len(missing)} stack(s) awaiting a credential: "
            f"{', '.join(missing[:8])}{' …' if len(missing) > 8 else ''}",
        )
    return state


def run_t1(client: ReadOnlyClient, cfg: config.Config) -> dict[str, Any]:
    stacks = gcom.fetch_inventory(client, cfg)
    coverage = Coverage(tier=cfg.tier, total=len(stacks))
    for s in stacks:
        if s.get("status") == "paused":
            coverage.record_skipped(str(s["slug"]), "paused")
        else:
            coverage.record_ok(str(s["slug"]))

    resolver = InstanceResolver(stacks)
    collisions = resolver.cross_stack_collisions()
    policies = gcom.fetch_access_policies(client, cfg, stacks)
    org_members: dict[str, Any] = {}
    org_member_errors: list[str] = []
    try:
        org_members = gcom.fetch_org_members(client, cfg)
    except Exception as exc:  # noqa: BLE001 - source health carries the bounded reason
        reason = f"{type(exc).__name__}: {exc}"
        org_member_errors.append(reason)
        console_log(
            "error",
            f"org members: unavailable  -  {reason}. Membership metrics and view are WITHHELD.",
        )
    fleet_data, fleet_errors = gather_fleet(cfg, stacks)

    # Fleet is an independently failing per-stack source, not part of the one-shot inventory read.
    # Its honest population is active stacks that advertise a Fleet endpoint: a stack with no endpoint
    # is not a failed Fleet read. One responding endpoint out of hundreds must not become a tiny but
    # confidently-current estate total, so apply the same publication floor as T2's stack-local inputs.
    fleet_expected = sum(
        1 for stack in stacks
        if stack.get("status") != "paused" and stack.get("agentManagementInstanceUrl")
    )
    sources = {
        "org_members": {
            **source_report(
                1,
                {"org": org_members} if org_members else {},
                available=lambda record: record.get("state") == "ok",
                errors=org_member_errors,
            ),
            "unit": "org response",
        },
        "fleet": source_report(
            fleet_expected,
            fleet_data,
            available=lambda record: bool(record.get("available")),
            errors=fleet_errors,
        )
    }
    source_failures = sorted(name for name, report in sources.items() if not report["healthy"])
    publishable, unavailable_inputs = publication_inputs(
        {"org_members": org_members, "fleet": fleet_data}, sources,
    )

    # Hydrate T2's per-stack detail and T3's data plane from their latest scans, so the hourly tier
    # publishes a COMPLETE view set rather than flattening nine views it cannot compute (PLAN 16.1).
    # Leaving them as None here was not a safe default: the pillars' honest `None` was overwritten onto
    # the bucket on top of T3's real figures every hour.
    inputs, prov = hydrate.hydrate(
        cfg.tier,
        {"access_policies": policies, **publishable},
        unavailable=unavailable_inputs,
        bucket=s3emit.BUCKET,
    )
    rate_card = load_ratecard(bucket=s3emit.BUCKET)
    metrics, views = compose.build_all(
        stacks, coverage,
        gap_first_seen=assistant_gaps(cfg, stacks, inputs.get("assistant"), gathered=False),
        ratecard=rate_card,
        score_weights=getattr(cfg, "coverage_score_weights", None),
        **inputs,
    )
    scan_inputs = prov

    # Republish the weekly T3 series so they resolve between T3 runs (PLAN 5.3). Without this every
    # Pillar B/D/F panel is empty for 99.95% of the week.
    carried: list[tuple[str, dict[str, str], float]] = []
    report: dict[str, Any] = {"available": False, "carried": 0, "age_seconds": None}
    try:
        state = carry.load_state("t3", bucket=s3emit.BUCKET)
    except carry.StateUnavailable as exc:
        console_log("warn", f"carry-forward: no t3 state ({exc})  -  run `./scan.py --tier t3`")
    else:
        # The live slug set is the authority on what exists (golden rule: the estate is
        # discovered, never configured). Without it a decommissioned stack's T3 series would be
        # re-stamped as current for up to MAX_CARRY_AGE.
        carried, report = carry.carry_forward(
            metrics, state, live_stacks={str(s['slug']) for s in stacks})
        if report["too_old"]:
            console_log(
                "warn",
                f"carry-forward: t3 state is {report['age_seconds']}s old  -  REFUSING to republish. "
                f"Panels go empty, which is the honest signal.",
            )
        else:
            console_log(
                "info",
                f"carry-forward: +{report['carried']} series from t3 "
                f"({report['age_seconds']}s old, {report['skipped_live']} already live)",
            )
    metrics = metrics + carried + carry.report_metrics(report, cfg.tier)

    scan = envelope(
        cfg,
        coverage,
        # `fleet` too. An input a tier OWNS but does not persist is invisible to every other tier -
        # `hydrate` reads inputs out of `scans/<tier>/latest.json`, and the symptom is not an error but
        # panels carrying at most one sample in the dashboards' default window.
        {"stacks": stacks, "access_policies": policies, **publishable},
        extra={
            "cross_stack_id_collisions": len(collisions),
            "requests": client.attempts.requests,
            "retries": client.attempts.retries,
            "series_emitted": len(metrics),
            "error_samples": (org_member_errors + fleet_errors)[:10],
            "sources": sources,
            "source_failures": source_failures,
            "sources_healthy": not source_failures,
            "scan_healthy": not coverage.should_abort and not source_failures,
        },
    )
    scan["meta"]["inputs"] = scan_inputs
    scan["_emit"] = {"metrics": metrics, "views": views}
    return scan


def run_t2(client: ReadOnlyClient, cfg: config.Config) -> dict[str, Any]:
    stacks = gcom.fetch_inventory(client, cfg)
    slugs = [str(s["slug"]) for s in stacks]
    if cfg.stack:
        slugs = [s for s in slugs if s == cfg.stack] or [cfg.stack]
    elif cfg.limit:
        slugs = slugs[: cfg.limit]

    selected = [s for s in stacks if str(s["slug"]) in set(slugs)]
    coverage = Coverage(tier=cfg.tier, total=len(selected))
    errors: list[str] = []
    detail = gcom.fetch_all_stack_detail(
        client, cfg, selected, coverage, on_error=lambda slug, msg: errors.append(f"{slug}: {msg}")
    )
    service_accounts, service_account_errors = gather_service_accounts(client, cfg, selected)
    errors += service_account_errors
    assistant, assistant_errors = gather_assistant(client, cfg, selected)
    errors += assistant_errors
    insights_data, insights_errors = gather_insights(client, cfg, selected)
    errors += insights_errors
    dashboard_inventory, dashboard_inventory_errors = gather_dashboard_inventory(client, cfg, selected)
    errors += dashboard_inventory_errors
    datasource_query_cost, datasource_query_cost_errors = gather_datasource_query_cost(
        client, cfg, selected,
    )
    errors += datasource_query_cost_errors
    adaptive_logs, adaptive_logs_errors = gather_adaptive_logs(client, cfg, selected)
    errors += adaptive_logs_errors
    pubdash, pubdash_errors = gather_public_dashboards(client, cfg, selected)
    errors += pubdash_errors
    alert_routing, alert_routing_errors = gather_alert_routing(client, cfg, selected)
    errors += alert_routing_errors
    signal_inventory, signal_inventory_errors = gather_signal_inventory(client, cfg, selected)
    errors += signal_inventory_errors
    capability_adoption, capability_adoption_errors = gather_capability_adoption(
        # The datasource exists on the write stack even when a diagnostic --stack/--limit selects a
        # different target. The source still discovers that host from the full live inventory; compose
        # then left-joins the result only to the selected diagnostic population.
        client, cfg, stacks,
    )
    errors += capability_adoption_errors

    # Decide publication eligibility BEFORE hydration or composition. A non-empty per-stack mapping is
    # not an available estate input: 1 success plus 268 failures is partial, not a tiny but valid total.
    expected = coverage.scannable
    gathered_inputs = {
        "stack_detail": detail,
        "service_accounts": service_accounts,
        "assistant": assistant,
        "insights": insights_data,
        "dashboard_inventory": dashboard_inventory,
        "datasource_query_cost": datasource_query_cost,
        "adaptive_logs": adaptive_logs,
        "public_dashboards": pubdash,
        "alert_routing": alert_routing,
        "signal_inventory": signal_inventory,
        "capability_adoption": capability_adoption,
    }
    sources = {
        "stack_detail": source_report(expected, detail, available=lambda _r: True),
        "service_accounts": source_report(
            expected, service_accounts, available=lambda r: r.get("state") == sa_src.OK,
            errors=service_account_errors,
        ),
        "assistant": source_report(
            expected, assistant, available=lambda r: bool(r.get("available")),
            errors=assistant_errors,
        ),
        "insights": source_report(
            expected, insights_data, available=lambda r: bool(r.get("available")),
            errors=insights_errors,
        ),
        # Dashboard inventory availability is the publication floor. Activity gaps remain as explicit
        # UNKNOWN rows rather than causing known dashboard identities to disappear.
        "dashboard_inventory": source_report(
            expected, dashboard_inventory, available=lambda r: bool(r.get("available")),
            errors=dashboard_inventory_errors,
        ),
        # Cost measurement is required; datasource-name resolution may fail independently and then
        # retains the UID with an explicit unresolved name rather than dropping the cost row.
        "datasource_query_cost": source_report(
            expected, datasource_query_cost, available=lambda r: bool(r.get("available")),
            errors=datasource_query_cost_errors,
        ),
        "adaptive_logs": source_report(
            expected, adaptive_logs, available=lambda r: bool(r.get("available")),
            errors=adaptive_logs_errors,
        ),
        "public_dashboards": source_report(
            expected, pubdash, available=lambda r: bool(r.get("available")),
            errors=pubdash_errors,
        ),
        "alert_routing": source_report(
            expected, alert_routing, available=lambda r: bool(r.get("available")),
            errors=alert_routing_errors,
        ),
        "signal_inventory": source_report(
            expected, signal_inventory, available=lambda r: bool(r.get("available")),
            errors=signal_inventory_errors,
        ),
        "capability_adoption": {
            **source_report(
                1, {"org": capability_adoption},
                available=lambda r: bool(r.get("available")),
                errors=capability_adoption_errors,
            ),
            "unit": "org usage response",
        },
    }
    source_failures = sorted(name for name, report in sources.items() if not report["healthy"])
    publishable_inputs, unavailable_inputs = publication_inputs(gathered_inputs, sources)

    # Pillar C's user recency, Pillar E's service-account and plugin-drift halves, all of Pillar I, and
    # all of Pillar J.
    inputs, prov = hydrate.hydrate(
        cfg.tier,
        publishable_inputs,
        unavailable=unavailable_inputs,
        bucket=s3emit.BUCKET,
    )
    rate_card = load_ratecard(bucket=s3emit.BUCKET)
    metrics, views = compose.build_all(
        selected, coverage,
        gap_first_seen=assistant_gaps(
            cfg, selected, inputs.get("assistant"),
            # `gathered=True` updates the first-seen gap state in S3. If ANY source failed this run is
            # going to stop before publication, so that side write must stop too even when Assistant
            # itself was healthy.
            gathered=not source_failures and "assistant" in publishable_inputs,
        ),
        ratecard=rate_card,
        score_weights=getattr(cfg, "coverage_score_weights", None),
        **inputs,
    )
    scan_inputs = prov

    scan = envelope(
        cfg,
        coverage,
        # `insights` too. Without it in the envelope the sweep runs, composes, and is then invisible to
        # every other tier: `hydrate` reads inputs out of `scans/<tier>/latest.json`, so an input that is
        # gathered but not persisted cannot be hydrated and every Pillar J panel would carry at most one
        # sample in the dashboards' default window.
        publishable_inputs,
        extra={
            "requests": client.attempts.requests,
            "retries": client.attempts.retries,
            "error_samples": errors[:10],
            "series_emitted": len(metrics),
            "sources": sources,
            "source_failures": source_failures,
            "sources_healthy": not source_failures,
            "scan_healthy": not coverage.should_abort and not source_failures,
        },
    )
    scan["meta"]["inputs"] = scan_inputs
    scan["_emit"] = {"metrics": metrics, "views": views}
    return scan


def run_t3(client: ReadOnlyClient, cfg: config.Config) -> dict[str, Any]:
    """Six-hourly: cardinality, Adaptive Metrics recommendations, Fleet Management inventory."""
    stacks = gcom.fetch_inventory(client, cfg)
    if cfg.stack:
        stacks = [s for s in stacks if str(s["slug"]) == cfg.stack]
    elif cfg.limit:
        stacks = stacks[: cfg.limit]

    coverage = Coverage(tier=cfg.tier, total=len(stacks))
    errors: list[str] = []
    data = dataplane.probe_all(
        client, cfg.cap, stacks, coverage, concurrency=cfg.concurrency,
        on_error=lambda slug, msg: errors.append(f"{slug}: {msg}"),
    )
    # The richest tier: Pillars B, D and F only become real here, and Pillar E gains Fleet Management.
    inputs, prov = hydrate.hydrate(cfg.tier, {"dataplane": data}, bucket=s3emit.BUCKET)
    rate_card = load_ratecard(bucket=s3emit.BUCKET)
    metrics, views = compose.build_all(
        stacks, coverage,
        gap_first_seen=assistant_gaps(cfg, stacks, inputs.get("assistant"), gathered=False),
        ratecard=rate_card,
        score_weights=getattr(cfg, "coverage_score_weights", None),
        **inputs,
    )
    scan_inputs = prov

    scan = envelope(
        # `stacks` too, so the Loki detail events can pair inventory with the cardinality and Adaptive
        # findings  -  which is the whole point of the T3 sweep.
        cfg, coverage, {"dataplane": data, "stacks": stacks},
        extra={"requests": client.attempts.requests, "retries": client.attempts.retries,
               "by_status": client.attempts.by_status, "error_samples": errors[:10],
               "series_emitted": len(metrics)},
    )
    scan["meta"]["inputs"] = scan_inputs
    scan["_emit"] = {"metrics": metrics, "views": views}
    return scan


def run_t4(client: ReadOnlyClient, cfg: config.Config) -> dict[str, Any]:
    """Estate diff over every window in `diff.WINDOWS`. Reads prior scans from S3, no API calls.

    Compares the latest scan against the one nearest each window's target, NOT the two most recent
    (PLAN 5.6). Since 2026-08-19 T4 runs daily and publishes BOTH a week-over-week and a day-over-day
    diff (PLAN 13.2), each to its own view key.

    **Each window succeeds or fails independently.** A young deployment, or one where T3 has been down,
    can legitimately support one window and not the other  -  the daily diff needs a 12-hour baseline and
    refuses anything past 3 days, while the weekly needs a full day and allows up to 21. Failing one must
    not suppress the other, and neither is an error.
    """
    coverage = Coverage(tier=cfg.tier, total=0)
    views: dict[str, list[dict[str, Any]]] = {}
    payload: dict[str, Any] = {}
    for window in diff.WINDOWS:
        # Prefer t3  -  it carries the data plane, so the diff can cover Adaptive and cardinality too.
        # With T3 on a 6-hour cadence this now usually succeeds, where a weekly T3 often fell through
        # to t1 and left the four data-plane rows reading "not measured in both scans".
        for source_tier in ("t3", "t1"):
            try:
                scans = diff.list_scans(source_tier, bucket=s3emit.BUCKET)
                latest, baseline = diff.select_baseline(scans, window=window)
                report = diff.diff(
                    diff.load_scan(latest[0], bucket=s3emit.BUCKET),
                    diff.load_scan(baseline[0], bucket=s3emit.BUCKET),
                    latest[1], baseline[1], window=window,
                )
            except diff.NoBaseline as exc:
                console_log("info", f"t4: no {window.name} baseline in {source_tier} ({exc})")
                continue
            payload[window.name] = {"source_tier": source_tier, **report}
            views[window.view] = diff.as_view(report)
            console_log(
                "info" if report["on_target"] else "warn",
                f"t4: {window.name} {source_tier} diff over {report['interval_days']} days "
                f"({'on target' if report['on_target'] else 'OFF TARGET  -  interval is stated in the view'})",
            )
            break

    if not payload:
        console_log("info", "t4: no window could be diffed  -  not an error on a young deployment")

    scan = envelope(cfg, coverage, {"diff": payload})
    if views:
        scan["_emit"] = {"metrics": [], "views": views}
    return scan


def run(client: ReadOnlyClient, cfg: config.Config, args: argparse.Namespace) -> int:
    """Everything that touches the estate or publishes. Called with the tier's lock already held."""
    if not cfg.dry_run and getattr(args, "out", None):
        console_log(
            "error",
            "error: --out is diagnostic and requires --dry-run; production stores the full "
            "envelope in S3 and emits only a bounded completion record to stdout.",
        )
        return 2
    if not cfg.dry_run and not _verified_ecs_runtime():
        console_log(
            "error",
            "error: refusing to publish outside a verified deployed ECS task definition; "
            "local runs must use --dry-run.",
        )
        return 2
    runners = {"t1": run_t1, "t2": run_t2, "t3": run_t3, "t4": run_t4}
    if cfg.tier not in runners:
        console_log("error", f"error: tier {cfg.tier} not implemented yet")
        return 2

    started = dt.datetime.now(dt.timezone.utc)
    try:
        scan = runners[cfg.tier](client, cfg)
    except ratecard.InvalidRateCard as exc:
        console_log("error", f"error: invalid rate card  -  {exc}")
        return 2
    except RateCardReadFailed as exc:
        console_log("error", f"error: rate card could not be read  -  {exc}")
        return 2
    finished = dt.datetime.now(dt.timezone.utc)
    coverage_ratio = scan["meta"]["coverage_ratio"]
    source_failures = scan["meta"].get("source_failures") or []
    failed_stacks = int(scan["meta"].get("stacks_failed") or 0)
    scannable_stacks = int(scan["meta"].get("stacks_scannable") or 0)
    primary_unhealthy = bool(
        scannable_stacks and (failed_stacks / scannable_stacks) > FAILURE_ABORT_RATIO
    )
    # T2 reports source health while gathering because it has several independently degradable
    # stack-local sources. Persist the same common contract on every tier: acceptance tooling should
    # never have to infer health from a missing field on T1/T3/T4.
    scan["meta"].setdefault("sources_healthy", not source_failures)
    scan["meta"].setdefault("scan_healthy", not primary_unhealthy and not source_failures)
    if primary_unhealthy or source_failures:
        # Stop before EVERY publication seam. Advancing the completion timestamp or latest scan after
        # an independently gathered owner input fell below its floor would make the failed run look
        # fresh, and saving the partial payload would let T1 hydrate it as the new estate truth. The
        # last-good views and owner envelope therefore remain untouched; the non-zero ECS task and its
        # CloudWatch error are the failure evidence, while the existing staleness alert watches the
        # completion timestamp that deliberately did not advance.
        reasons: list[str] = []
        if primary_unhealthy:
            reasons.append(
                f"primary stack coverage {failed_stacks} failures across {scannable_stacks} "
                f"scannable stacks ({coverage_ratio:.1%} covered)"
            )
        if source_failures:
            reasons.append("unhealthy owner inputs: " + ", ".join(source_failures))
        console_log(
            "error",
            "error: scan coverage is below the publication floor; "
            "REFUSING all S3, Mimir and Loki writes: " + "; ".join(reasons),
        )
        for name in source_failures:
            report = (scan["meta"].get("sources") or {}).get(name) or {}
            console_log(
                "error",
                f"  {name}: {report.get('available', 0)} of {report.get('expected', 0)} available "
                f"({float(report.get('coverage_ratio') or 0):.1%}); "
                f"errors={report.get('error_count', 0)} "
                f"samples={report.get('error_samples') or []}",
            )
        if cfg.dry_run:
            print(json.dumps(scan_completion_record(scan["meta"]), separators=(",", ":"), default=str))
            console_log("info", "dry-run: no S3, Mimir or Loki writes")
        return 1

    # UNCONDITIONAL, and that is the point of PLAN 1.8. A tier that produced no views and no metrics has
    # still RUN, and must still record that it ran  -  `run_t4` legitimately produces nothing when there is
    # no baseline to diff (scans less than a day apart, or a freshly deployed platform), and without this
    # it emitted no completion timestamp at all. Its staleness rule then sat on NoData for ever, which is
    # indistinguishable from the tier being dead. A switch that cannot tell "ran, nothing to do" from
    # "never ran" is not a switch.
    emit = scan.pop("_emit", None) or {"metrics": [], "views": {}}

    # A partial run composes every estate rollup over a SUBSET. Refuse before every publication seam:
    # carry state, views, Mimir, Loki and the latest scan envelope must all remain at their last-good
    # full-estate value. Dry-runs are diagnostic and write nothing, so they remain permitted.
    if (cfg.limit or cfg.stack) and not cfg.dry_run:
        console_log(
            "error",
            f"REFUSING all S3, Mimir and Loki writes: this run is limited to "
            f"{cfg.stack or str(cfg.limit) + ' stacks'}, so every estate rollup would be computed "
            f"over a subset. Re-run without --limit/--stack to publish, or add --dry-run for a "
            f"diagnostic run.",
        )
        return 2

    # Persist the accepted T3 batch so T1 can republish it hourly (PLAN 5.3). This MUST live after the
    # common publication-floor decision above. Saving inside `run_t3` let a rejected partial scan replace
    # the carry state before `run()` returned 1; the next healthy T1 then republished the poisoned batch
    # every hour even though the rejection log claimed every write was refused. Keep the state payload at
    # the pre-health-metric shape used historically; scan completion/duration belong to their live tier.
    if cfg.tier == "t3" and not cfg.dry_run:
        console_log("info", f"  {carry.save_state(emit['metrics'], 't3', bucket=s3emit.BUCKET)}")

    # PLAN 1.8  -  the dead-man's switch. Alerting is on the AGE of this timestamp, never on exit code:
    # a tier that cannot pull its image or reach Secrets Manager exits nothing at all, so there is no
    # code to alert on. Emitted by every tier, and it is what the dashboards' freshness banner reads.
    emit["metrics"] = list(emit["metrics"]) + [
        ("gcinsight_scan_completed_timestamp_seconds", {"tier": cfg.tier},
         float(int(finished.timestamp()))),
        ("gcinsight_scan_duration_seconds", {"tier": cfg.tier},
         round((finished - started).total_seconds(), 2)),
    ]
    scan["meta"]["duration_seconds"] = round((finished - started).total_seconds(), 2)
    # Findings: the actionable half, derived from the views the pillars already produced. Must happen
    # BEFORE the guard and the Mimir push  -  appending after either means the counts are neither
    # cardinality-checked nor written, and the only symptom is a metric that is quietly always absent.
    # The COUNTS go to Mimir as a bounded gauge so the trend outlives log retention; the DETAIL goes
    # to Loki, because the fields that make a finding actionable are the ones banned from a label.
    derived, finding_totals = findings_mod.derive(emit["views"])
    if finding_totals:
        emit["metrics"] = list(emit["metrics"]) + findings_mod.metrics(finding_totals)
    console_log("info", findings_mod.summarise(derived, finding_totals))

    # Input provenance -> metrics, and views whose inputs are unsatisfied are WITHHELD rather than
    # published as zeros (PLAN 16.1). Withholding leaves the last good copy on the bucket with its own
    # older timestamp: visibly stale beats silently wrong.
    prov = hydrate.Provenance(scan["meta"].get("inputs") or {})
    if prov:
        emit["metrics"] = list(emit["metrics"]) + hydrate.report_metrics(prov, cfg.tier)
        emit["views"], withheld = hydrate.filter_views(emit["views"], prov)
        console_log("warn" if withheld else "info", hydrate.summarise(prov, withheld))
        for name, why in sorted(withheld.items()):
            console_log("warn", f"  WITHHELD {name}: {why}")

    n = guard.check_all(emit["metrics"])
    # The runners' provisional count predates completion, findings and provenance metrics, and T4 has
    # no runner-owned metrics at all. Publish the final guarded count as the common contract.
    scan["meta"]["series_emitted"] = n
    console_log("info", f"label guard: {n} series pass")

    for uri in s3emit.write_views(emit["views"], scan["meta"], dry_run=cfg.dry_run):
        console_log("info", f"  {uri}")

    # Native remote_write to the target stack. Never the OTLP gateway (SPEC §5.3).
    # The WRITE credential, not the scanning one (PLAN 0.3). Scoped to obs-hub's stack realm.
    writer = mimir.RemoteWriter(
        cfg.mimir_url, cfg.mimir_tenant, cfg.write_token, dry_run=cfg.dry_run
    )
    try:
        written = writer.push(emit["metrics"])
        console_log(
            "info",
            f"mimir: {written} samples → {cfg.write_stack} "
            f"({'DRY-RUN' if cfg.dry_run else writer.url})",
        )
    except (mimir.RemoteWriteFailed, mimir.InvalidSeries) as exc:
        # A failed push must not look like a successful scan, but the S3 views are already
        # written and remain valid, so this degrades rather than discarding the run.
        console_log("error", f"mimir: PUSH FAILED  -  {exc}")
        scan["meta"]["mimir_push_failed"] = str(exc)
        scan["meta"]["scan_healthy"] = False

    # Loki carries the detail the cardinality guard bans from a metric label  -  label NAMES,
    # version strings, datasource ids, SA names. `stack` rides in the line body, never a stream.
    events = [loki.summary_event(cfg.tier, scan["meta"])]
    if derived:
        events += loki.finding_events(cfg.tier, derived)
    stacks_for_events = scan["data"].get("stacks") or []
    if stacks_for_events:
        events += loki.stack_detail_events(
            cfg.tier, stacks_for_events, scan["data"].get("dataplane")
        )
    # T2 carries no `stacks`; its payload is the identity detail, which is the densest concentration
    # of label-banned fields in the platform (logins, SA names, plugin versions).
    if scan["data"].get("stack_detail"):
        events += loki.stack_identity_events(cfg.tier, scan["data"]["stack_detail"])
    lokiw = loki.LokiWriter(cfg.loki_url, cfg.loki_tenant, cfg.write_token, dry_run=cfg.dry_run)
    try:
        lines = lokiw.push(events)
        console_log(
            "info",
            f"loki: {lines} lines → {cfg.write_stack} "
            f"({'DRY-RUN' if cfg.dry_run else lokiw.url})",
        )
    except (loki.LokiPushFailed, loki.UnboundedStream) as exc:
        console_log("error", f"loki: PUSH FAILED  -  {exc}")
        scan["meta"]["loki_push_failed"] = str(exc)
        scan["meta"]["scan_healthy"] = False
    for uri in s3emit.write_scan(scan, dry_run=cfg.dry_run):
        console_log("info", f"  {uri}")

    if args.out:
        payload = json.dumps(scan, indent=2, default=str)
        with open(args.out, "w") as fh:
            fh.write(payload)
        console_log("info", f"wrote {args.out} ({len(payload):,} bytes)")
    elif cfg.dry_run:
        # Don't spew the whole estate to a terminal on a dry run; the summary is the useful part.
        print(json.dumps(scan_completion_record(scan["meta"]), separators=(",", ":"), default=str))
    else:
        # CloudWatch Logs forwards stdout through Firehose. The complete scan can be many megabytes;
        # printing it here turned one successful T3 into 40,056 Loki lines / 7.6 MB and exhausted the
        # write stack's ingestion rate. S3 already holds the canonical envelope. Keep stdout as one
        # bounded, non-PII completion record so startup failures and tracebacks remain useful in Loki.
        print(json.dumps(scan_completion_record(scan["meta"]), separators=(",", ":"), default=str))

    if cfg.dry_run:
        console_log("info", "dry-run: no S3, Mimir or Loki writes")

    # >10% of stacks failing means the scan is too thin to publish (SPEC §5.2).
    if scannable_stacks and coverage_ratio < 1.0:
        console_log(
            "warn",
            f"warning: coverage {coverage_ratio:.1%}  -  "
            f"{scan['meta']['stacks_failed']} of {scan['meta']['stacks_total']} stacks failed",
        )
    failed = scan["meta"]["stacks_failed"]
    total = scan["meta"]["stacks_total"]
    if total and (failed / total) > 0.10:
        return 1
    # A scan that gathered everything and then could not publish it is not a success. Distinct exit
    # code so alerting can tell "the estate is unreachable" from "we cannot write to obs-hub".
    if scan["meta"].get("mimir_push_failed") or scan["meta"].get("loki_push_failed"):
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = StructuredArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--tier", required=True, choices=TIERS)
    ap.add_argument("--dry-run", action="store_true", help="write nothing to S3, Mimir or Loki")
    ap.add_argument("--limit", type=int, help="only scan the first N stacks")
    ap.add_argument("--stack", help="only scan this stack slug")
    ap.add_argument("--concurrency", type=int, help="per-host concurrency for the data plane")
    ap.add_argument(
        "--deadline-seconds",
        type=float,
        help="override the tier's default deadline. ECS has no max-runtime setting, so this is the "
             "only thing bounding a run; it must stay shorter than the tier's schedule interval.",
    )
    ap.add_argument("--out", help="write the dry-run scan envelope to this path (requires --dry-run)")
    ap.add_argument(
        "--ignore-lock",
        action="store_true",
        help="run even if another scan of this tier holds the lock (debugging only  -  two concurrent "
             "scans share the per-credential gcom rate-limit quota and race on latest.json)",
    )
    args = ap.parse_args(argv)

    if args.out and not args.dry_run:
        console_log(
            "error",
            "error: --out requires --dry-run; production publishes the full envelope to S3.",
        )
        return 2

    if not args.dry_run and not _verified_ecs_runtime():
        console_log(
            "error",
            "error: refusing to publish from a local process; production and manual publishing "
            "must use a deployed ECS task definition. Use --dry-run for local diagnostics.",
        )
        return 2

    try:
        cfg = config.load(
            tier=args.tier,
            dry_run=args.dry_run,
            limit=args.limit,
            stack=args.stack,
            concurrency=args.concurrency,
            deadline_seconds=args.deadline_seconds,
        )
    except config.MissingCredential as exc:
        console_log("error", f"error: {exc}")
        return 2

    client = ReadOnlyClient(
        host_concurrency=cfg.concurrency,
        host_concurrency_overrides=config.HOST_CONCURRENCY,
        host_rate_limits=config.HOST_RATE_LIMITS,
        deadline=cfg.deadline_seconds,
    )

    # PLAN 1.7  -  one scan of a tier at a time. Acquired here rather than inside a runner so that
    # nothing which reads the estate or writes to S3 can run twice concurrently.
    lock = scanlock.ScanLock(
        tier=cfg.tier,
        ttl_seconds=scanlock.ttl_for(cfg.deadline_seconds),
        backend=scanlock.S3Backend(s3emit.BUCKET, s3emit.REGION),
        # `dry_run` on the lock means "take no lock and be blocked by none". Two different reasons reach
        # it: a dry run writes nothing so it can neither collide nor be collided with, and --ignore-lock
        # is the deliberate debugging override.
        dry_run=cfg.dry_run or args.ignore_lock,
    )
    try:
        lock.acquire()
    except scanlock.LockHeld as exc:
        # Not a crash and not a coverage problem: the previous run of this tier is still going. Its own
        # dead-man's-switch age is what escalates if this keeps happening, so this exits quietly with a
        # code of its own rather than paging.
        console_log("info", f"lock: {exc}")
        return 4
    except scanlock.LockBackendFailed as exc:
        # An S3 or IAM problem, NOT "someone else is running". Conflating the two would let a broken
        # bucket policy look like a busy schedule forever.
        console_log("error", f"lock: backend failure  -  {exc}")
        return 2
    if lock.broke_stale_lock:
        console_log(
            "warn",
            f"lock: broke a stale {cfg.tier} lock  -  the previous run was killed without releasing it "
            f"(OOM, spot reclaim or StopTask). Check the previous task's exit reason.",
        )
    try:
        return run(client, cfg, args)
    finally:
        lock.release()


def entrypoint() -> int:
    """Emit one structured failure record before Python renders an unexpected traceback."""
    try:
        return main()
    except Exception as exc:
        console_log(
            "error",
            f"unexpected top-level exception: {type(exc).__name__}: {exc}",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(entrypoint())
