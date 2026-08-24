"""Loki push emitter - the home for everything that must not be a metric label (PLAN 5.4).

**Never the OTLP gateway.** Same reason as Mimir: it would inflate the org's gateway request counts and
corrupt the protocol-adoption figures this platform reports.

Mimir carries the bounded, numeric, alertable half. Loki carries the half that is genuinely unbounded
and therefore banned from a metric label by `emit/guard.py`: metric names, label names, dashboard uids,
service-account names, user logins. Those are exactly the fields that make a finding *actionable* - "your
cardinality is high" is useless next to "`stack084`'s worst label is `X` with 88,000 values" - so they
have to live somewhere, and a log line is the right somewhere.

**Stream labels are `job`, `tier`, `pillar`, `event` and nothing else.** Loki streams are as
cardinality-sensitive as Prometheus series, and putting `stack` in a stream label would create 271
streams per event type. `stack` therefore travels **in the line body**, where it is queryable with
`| json | stack="stack084"` at no indexing cost. The test suite pins this, because it is the exact
mistake the metric guard exists to prevent, one layer down.

Timestamps are nanosecond strings - Loki rejects anything else, and the failure is a 400 rather than a
silently misplaced line.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import urllib.error
import urllib.request
from typing import Any, Iterable, Mapping, Sequence

from collector import identity

PUSH_PATH = "/loki/api/v1/push"
JOB = identity.env("GCINSIGHT_LOKI_JOB", "gcinsight")

# The only permitted stream labels. Everything else belongs in the line body.
STREAM_LABELS = frozenset({"job", "tier", "pillar", "event"})

# Closed event vocabulary, so the stream count stays predictable.
EVENTS = ("scan_summary", "stack_detail", "finding", "change")


class UnboundedStream(ValueError):
    """A stream label that would multiply Loki streams the way an unbounded metric label multiplies series."""


class LokiPushRefused(RuntimeError):
    pass


class LokiPushFailed(RuntimeError):
    pass


def check_stream(labels: Mapping[str, str]) -> None:
    for key, value in labels.items():
        if key not in STREAM_LABELS:
            raise UnboundedStream(
                f"stream label {key!r} is not permitted. Streams are as cardinality-sensitive as "
                f"series - put it in the line body, where `| json | {key}=…` still filters on it."
            )
        if not value:
            raise UnboundedStream(f"stream label {key!r} is empty")


def _ns(stamp: dt.datetime) -> str:
    return str(int(stamp.timestamp() * 1_000_000_000))


def build_payload(
    entries: Iterable[tuple[Mapping[str, str], Mapping[str, Any]]],
    *,
    timestamp: dt.datetime | None = None,
) -> dict[str, Any]:
    """Group `(stream_labels, line_dict)` pairs into Loki's stream/values shape."""
    stamp = timestamp or dt.datetime.now(dt.timezone.utc)
    ns = _ns(stamp)
    grouped: dict[tuple[tuple[str, str], ...], list[list[str]]] = {}
    for labels, line in entries:
        stream = {"job": JOB, **dict(labels)}
        check_stream(stream)
        key = tuple(sorted(stream.items()))
        # Set `level` explicitly. Without it Loki's automatic level discovery sniffed the line content
        # and stamped every one of the 271 stack_detail lines `detected_level=error`, which would show
        # a healthy scan as 271 errors in Explore Logs. These are informational records, not events.
        body = {"level": "info", **dict(line)}
        grouped.setdefault(key, []).append([ns, json.dumps(body, default=str, sort_keys=True)])
    return {
        "streams": [
            {"stream": dict(key), "values": values} for key, values in sorted(grouped.items())
        ]
    }


# --- event builders -------------------------------------------------------------------------------

def stack_detail_events(
    tier: str, stacks: Sequence[Mapping[str, Any]], dataplane: Mapping[str, Any] | None = None
) -> list[tuple[dict[str, str], dict[str, Any]]]:
    """One line per stack carrying the detail that cannot be a metric label."""
    dataplane = dataplane or {}
    out = []
    for stack in stacks:
        slug = str(stack["slug"])
        probe = dataplane.get(slug) or {}
        card = probe.get("cardinality") or {}
        adaptive = probe.get("adaptive_metrics") or {}
        fleet = probe.get("fleet") or {}
        line: dict[str, Any] = {
            # `stack` in the BODY, not the stream. Queryable via `| json | stack="stack084"`.
            "stack": slug,
            "region": stack.get("regionSlug"),
            "cluster": stack.get("clusterSlug"),
            "active_series": stack.get("hmInstancePromCurrentActiveSeries") or 0,
            "billed_users": stack.get("billingActiveUsers") or 0,
            "active_users": stack.get("currentActiveUsers") or 0,
            "dashboards": stack.get("dashboardCnt") or 0,
            "alert_rules": stack.get("alertCnt") or 0,
            # Version strings churn on every upgrade - banned from labels, useful here.
            "running_version": stack.get("runningVersion"),
            "datasource_types": sorted(
                k for k, v in (stack.get("datasourceCnts") or {}).items() if v
            ),
        }
        if card.get("available"):
            line["label_names_count"] = card.get("label_names_count")
            line["label_values_count_total"] = card.get("label_values_count_total")
            # Offender NAMES: the actionable half, and unbounded by nature.
            line["top_labels"] = card.get("top_labels") or []
        if adaptive.get("available"):
            line["adaptive_rules_applied"] = adaptive.get("rules_applied")
            line["adaptive_recommendations_pending"] = adaptive.get("recommendations_pending")
            line["adaptive_sample"] = adaptive.get("sample_recommendations") or []
        if fleet.get("available"):
            line["collectors"] = fleet.get("collectors")
            line["pipelines"] = fleet.get("pipelines")
            line["collector_versions"] = fleet.get("collector_versions") or []
        out.append(({"tier": tier, "pillar": "A", "event": "stack_detail"}, line))
    return out


def stack_identity_events(
    tier: str, stack_detail: Mapping[str, Any]
) -> list[tuple[dict[str, str], dict[str, Any]]]:
    """T2's per-stack users, service accounts and plugin drift.

    This is the densest concentration of fields banned from metric labels anywhere in the platform:
    logins (which ARE email addresses on many estates), full names, service-account names, plugin
    versions. PII is in scope and stored in clear by decision, and the cardinality rule is what still
    applies - so it all lives here, in line bodies, and never in a label.
    """
    out = []
    for slug, detail in (stack_detail or {}).items():
        users = (detail or {}).get("users") or []
        accounts = (detail or {}).get("service_accounts") or []
        plugins = (detail or {}).get("plugins") or []
        out.append((
            {"tier": tier, "pillar": "E", "event": "stack_detail"},
            {
                "stack": slug,
                "users": [
                    {"login": u.get("login"), "name": u.get("name"),
                     "email_domain": u.get("email_domain"), "role": u.get("role"),
                     "last_seen_at": u.get("lastSeenAt")}
                    for u in users
                ],
                "user_count": len(users),
                "admin_count": len([u for u in users if u.get("role") == "Admin"]),
                "service_accounts": [
                    {"name": a.get("name"), "kind": a.get("kind"), "role": a.get("role"),
                     "tokens": a.get("tokens"), "disabled": bool(a.get("isDisabled"))}
                    for a in accounts
                ],
                "service_account_tokens": sum(a.get("tokens") or 0 for a in accounts),
                "plugins": [
                    {"slug": p.get("pluginSlug"), "version": p.get("version"),
                     "latest_version": p.get("latestVersion"),
                     "drift": bool(p.get("version") and p.get("latestVersion")
                                   and p["version"] != p["latestVersion"])}
                    for p in plugins
                ],
            },
        ))
    return out


def finding_events(
    tier: str, findings: Sequence[Mapping[str, Any]]
) -> list[tuple[dict[str, str], dict[str, Any]]]:
    """A finding is `{pillar, stack, kind, detail, ...}`; `pillar` becomes the stream label."""
    out = []
    for finding in findings:
        pillar = str(finding.get("pillar") or "A")
        out.append(({"tier": tier, "pillar": pillar, "event": "finding"}, dict(finding)))
    return out


def summary_event(
    tier: str, meta: Mapping[str, Any]
) -> tuple[dict[str, str], dict[str, Any]]:
    line = {**dict(meta), "level": "error" if meta.get("scan_healthy") is False else "info"}
    return ({"tier": tier, "pillar": "scan", "event": "scan_summary"}, line)


# --- the pusher -----------------------------------------------------------------------------------

class LokiWriter:
    """POSTs to exactly one configured Loki push endpoint. Same narrow-write contract as Mimir's."""

    def __init__(self, base_url: str, tenant: str, token: str, *, dry_run: bool = False,
                 timeout: float = 60.0) -> None:
        base = base_url.rstrip("/")
        if not base.startswith("https://"):
            raise LokiPushRefused(f"Loki push must be https, got {base_url!r}")
        if not base.endswith(PUSH_PATH):
            base = base + PUSH_PATH
        self.url = base
        self.tenant = str(tenant)
        self._token = token
        self.dry_run = dry_run
        self.timeout = timeout
        self.lines_written = 0

    def push(
        self,
        entries: Sequence[tuple[Mapping[str, str], Mapping[str, Any]]],
        *,
        timestamp: dt.datetime | None = None,
    ) -> int:
        if not entries:
            return 0
        payload = build_payload(entries, timestamp=timestamp)
        body = json.dumps(payload).encode()
        if self.dry_run:
            self.lines_written += len(entries)
            return len(entries)

        auth = base64.b64encode(f"{self.tenant}:{self._token}".encode()).decode()
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "User-Agent": "gcinsight-collector/1 (+grafana-ps)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status not in (200, 204):
                    raise LokiPushFailed(f"{self.url}: HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read(500).decode("utf-8", "replace")
            raise LokiPushFailed(f"{self.url}: HTTP {exc.code} {detail}") from exc
        self.lines_written += len(entries)
        return len(entries)
