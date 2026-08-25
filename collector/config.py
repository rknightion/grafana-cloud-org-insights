"""Runtime configuration.

The credential comes from the **environment** locally and AWS Secrets Manager in deployment  -  never
from a path inside this repo (SPEC §3). `../.env` is a convenience store for interactive work;
reading it automatically would put a `set:cloud-admin` token on the collector's happy path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from collector import identity, observability_score

GCOM = "https://grafana.com/api"

# Per-host concurrency. gcom is ONE shared control plane for all 271 stacks, so it gets a low cap;
# the data plane is 271 separate tenants and tolerates more (SPEC §5.2).
HOST_CONCURRENCY = {"grafana.com": 4}
HOST_CONCURRENCY_DEFAULT = 12

# Proactive pacing for gcom. Measured 2026-08-17: an unpaced 813-call sweep drew 77 HTTP 429s and
# covered 71.6% of the estate; gcom answers 429 with `Retry-After: 8-10`. Requests per second.
HOST_RATE_LIMITS = {"grafana.com": 6.0}

# --- Write target ---------------------------------------------------------------------------------
# There are deliberately NO DEFAULTS for values that identify a deployment. A default org id, stack
# slug or tenant silently sends a correct-looking scan to somebody else's tenant.
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("GCINSIGHT_ORG_ID", "Grafana Cloud organisation id to scan (gcom /orgs/<id>)"),
    ("GCINSIGHT_WRITE_STACK", "slug of the single stack results are published to"),
    ("GCINSIGHT_MIMIR_URL", "Mimir remote_write base URL, no path suffix"),
    ("GCINSIGHT_MIMIR_TENANT", "Mimir tenant id - the write stack's hmInstancePromId"),
    ("GCINSIGHT_LOKI_URL", "Loki push base URL, no path suffix"),
    ("GCINSIGHT_LOKI_TENANT", "Loki tenant id - the write stack's hlInstanceId"),
)


class IncompleteConfig(RuntimeError):
    """Base for every value `load()` refuses to guess."""


class MissingCredential(IncompleteConfig):
    """No usable read credential was supplied."""


class MissingConfig(IncompleteConfig):
    """A required deployment identifier was not supplied."""


def _require(name: str, purpose: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingConfig(f"{name} is not set ({purpose})")
    return value


# --- Credential split (PLAN 0.3) -------------------------------------------------------------------
# TWO policies, not one, because a single credential that can both scan 271 stacks and write to one is
# strictly more dangerous than the pair:
#
#   gcinsight-reader  org realm, region `us`, 9 read-only scopes.
#   gcinsight-writer  STACK realm of the write stack alone, `metrics:write` + `logs:write`.
#
# The writer physically cannot touch the other 270 stacks  -  the realm forbids it, not a scope check.
# `GCINSIGHT_WRITE_TOKEN` falls back to `GCINSIGHT_READ_TOKEN` so an interactive run with one credential still
# works, but deployment must set both.
READER_SCOPES = (
    "stacks:read",                            # GET /instances
    "stack-users:read",                       # GET /instances/<slug>/users
    "stack-plugins:read",                     # GET /instances/<slug>/plugins
    "org-members:read",                       # GET /orgs/<id>/members
    "accesspolicies:read",                    # GET /v1/accesspolicies
    # Per-stack signal databases. ONE org CAP reaches all four in every region; the basic-auth user is
    # the per-signal instance id from `dataplane.AUTH_FIELD`, never the stack id.
    "metrics:read",                           # Mimir: the cardinality API AND the whole query API
    "logs:read",                              # Loki: /loki/api/v1/labels and label/<name>/values
    "traces:read",                            # Tempo: /tempo/api/v2/search/tags and tag/<t>/values
    "profiles:read",                          # Pyroscope: querier.v1.QuerierService/LabelValues
    # Rule and alert inventory. Read the note below before using either.
    "rules:read",                             # {prom}/api/prom/api/v1/{rules,alerts}, Loki ruler
    "alerts:read",                            # {amInstanceUrl}/alertmanager/api/v2/*, user amInstanceId
    # Adaptive Metrics.
    "adaptive-metrics-rules:read",            # /aggregations/rules
    "adaptive-metrics-recommendations:read",  # /aggregations/recommendations
    "adaptive-metrics-config:read",           # /aggregations/recommendations/config
    # adaptive-metrics-exemptions:read is DELIBERATELY ABSENT. Over forty candidate paths 404 across two
    # stacks, including one carrying 316 applied rules, auto_apply enabled and a live segment, so it is
    # not a route that appears once there is data. See CAPABILITIES.md; the exemption data itself is
    # most likely `keep_labels` on the config route, which adaptive-metrics-config:read already reaches.
    "fleet-management:read",                  # Connect-RPC List*  -  a read scope covers the POST verb
)

# `alerts:read` and `rules:read` are the two scopes here that reach beyond inventory, and neither is
# free.
#
# `{amInstanceUrl}/alertmanager/api/v2/status` returns the stack's RAW Alertmanager configuration in
# `config.original`, `http_config` included. On a stack whose contact points live in Alertmanager rather
# than in Grafana, that YAML can carry webhook URLs and tokens. The scope is declared because
# alert-routing inventory needs it; nothing derived from that body may be stored, logged or emitted
# beyond bounded counts. Treat it exactly like `accessToken` on a public dashboard.
#
# `{prom}/api/prom/api/v1/alerts` returns firing instances carrying their full customer label sets.
# Those are unbounded and identity-bearing: count them, never carry them into a metric label.

WRITER_SCOPES = ("metrics:write", "logs:write")

# There is no org-CAP `stack-service-accounts:read` scope  -  only `:write`, which is deliberately absent
# from the collector. The live SA/token inventory instead comes from each stack's basic-role-None reader
# through `collector.sources.serviceaccounts`; do not mistake the missing org scope for a current product
# blind spot or add the write scope to this deployment credential.

# Stacks the organisation has asked us not to provision a reader on. The ONE thing about the estate that is genuine
# policy rather than discoverable, so it is the one thing a config store may hold (CLAUDE.md golden rule).
# Shared with `bin/provision.py` under the same variable name on purpose: two lists would drift, and the
# consequence of drift is the coverage alert firing for ever on a stack we were asked to leave alone.
OPT_OUT_ENV = "GCINSIGHT_OPT_OUT"


@dataclass(frozen=True)
class Config:
    cap: str
    write_token: str
    org_id: str
    tier: str
    dry_run: bool
    limit: int | None
    stack: str | None
    concurrency: int
    deadline_seconds: float
    write_stack: str
    mimir_url: str
    mimir_tenant: str
    loki_url: str
    loki_tenant: str
    opt_out: tuple[str, ...] = ()
    coverage_score_weights: dict[str, float] | None = None

    @property
    def redacted(self) -> dict[str, object]:
        return {
            "org_id": self.org_id,
            "tier": self.tier,
            "dry_run": self.dry_run,
            "limit": self.limit,
            "stack": self.stack,
            "concurrency": self.concurrency,
            "deadline_seconds": self.deadline_seconds,
            "write_stack": self.write_stack,
            "mimir_url": self.mimir_url,
            "mimir_tenant": self.mimir_tenant,
            "loki_url": self.loki_url,
            "loki_tenant": self.loki_tenant,
            "cap": f"…{self.cap[-6:]}" if self.cap else None,
            "write_token": f"…{self.write_token[-6:]}" if self.write_token else None,
            "credentials_split": self.write_token != self.cap,
            "opt_out": list(self.opt_out),
            "coverage_score_weights": self.coverage_score_weights,
        }


def load(
    *,
    tier: str,
    dry_run: bool = False,
    limit: int | None = None,
    stack: str | None = None,
    concurrency: int | None = None,
    deadline_seconds: float | None = None,
) -> Config:
    identity.verify_runtime_projection("scan")
    cap = os.environ.get("GCINSIGHT_READ_TOKEN", "").strip()
    if not cap:
        raise MissingCredential(
            "GCINSIGHT_READ_TOKEN is not set. Export it for local runs "
            "(e.g. `export GCINSIGHT_READ_TOKEN=$(grep ^GCINSIGHT_READ_TOKEN= ../.env | cut -d= -f2-)`); "
            "in deployment it comes from AWS Secrets Manager."
        )
    try:
        score_weights = observability_score.parse_weights(
            os.environ.get("GCINSIGHT_COVERAGE_SCORE_WEIGHTS", "")
        )
    except observability_score.InvalidWeights as exc:
        raise MissingConfig(f"GCINSIGHT_COVERAGE_SCORE_WEIGHTS is invalid ({exc})") from exc
    return Config(
        cap=cap,
        # Falls back to the read credential so a one-token interactive run still works. Deployment sets
        # both, and the runbook says so.
        write_token=os.environ.get("GCINSIGHT_WRITE_TOKEN", "").strip() or cap,
        org_id=_require(*REQUIRED_ENV[0]),
        tier=tier,
        dry_run=dry_run,
        limit=limit,
        stack=stack,
        concurrency=concurrency or HOST_CONCURRENCY_DEFAULT,
        # Deadlines are strictly shorter than the tier interval so a slow scan cannot overlap the next.
        # t3 dropped from 21600 when it moved to a 6-hour cadence (2026-08-19): the deadline must stay
        # strictly shorter than the interval, and 21600 WAS the new interval. Observed runtime is 22s.
        deadline_seconds=deadline_seconds or {"t1": 900, "t2": 3600, "t3": 3600, "t4": 900}.get(tier, 900),
        write_stack=_require(*REQUIRED_ENV[1]),
        mimir_url=_require(*REQUIRED_ENV[2]),
        mimir_tenant=_require(*REQUIRED_ENV[3]),
        loki_url=_require(*REQUIRED_ENV[4]),
        loki_tenant=_require(*REQUIRED_ENV[5]),
        opt_out=tuple(s.strip() for s in os.environ.get(OPT_OUT_ENV, "").split(",") if s.strip()),
        coverage_score_weights=score_weights,
    )
