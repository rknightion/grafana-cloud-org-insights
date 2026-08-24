"""Pillar D - the observability-maturity rubric, composite score and leaderboard (PLAN 4.4).

The composite score AND the leaderboard, knowing a leaderboard invites argument. That
argument is won or lost on fairness, so three obligations are built in rather than documented:

1. **Weights are published** - the `maturity_rubric` view is rendered on the dashboard beside the score.
2. **Every score is explainable per stack** - `maturity_dimensions` carries each dimension's raw value,
   its 0-100 score and its weighted contribution. A stack owner can reconstruct the number by hand.
3. **The metric is versioned** - `gcinsight_maturity_score{version}`. Changing the rubric starts a
   new series instead of silently rewriting history, so a score that moved because the *rubric* moved is
   visible as such.

**Fairness traps that would have made the leaderboard indefensible, and what is done about them:**

- **Ratios punish small stacks.** A 2-user stack with 1 admin is 50% admins, structurally, and no
  governance change can fix that. Admin share is therefore only scored where `users >= ADMIN_MIN_USERS`;
  below that the test is the absolute count.
- **Cardinality ratios punish small stacks the other way.** `label_values / series` is *best* on
  `stack094` (0.0115 at 3.0M series) and worst on stacks with a few thousand series, because volume
  amortises label values. Measured p50 is 0.14 and the worst is `stack030` at 1.02 on 5,960 series.
  Scoring it estate-wide would rank the biggest stack the most disciplined. So the dimension applies
  **only above `CARDINALITY_MIN_SERIES`** and is `None` below it.
- **Missing data must not flatter.** T3 dimensions are absent on a T1/T2 run. The composite renormalises
  over the weight actually available, and every score carries `dimensions_scored` and `weight_covered`
  so a stack judged on four dimensions is never silently ranked against one judged on nine.
- **Both alerting extremes are failures.** 116 of 230 real stacks have zero alert rules; at the other end
  `stack158` runs 708 rules for 12 users and `stack029` 700 for 3. A "more is better" score would
  call the second group excellent.

**Ownership never comes from `createdBy`/`updatedBy`** - measured, 99.6% of those resolve to an org-level
token or empty, and
where they do resolve they usually name VENDOR staff rather than anyone in the org. Owners
are the stack's own Admin users, with Grafana staff filtered out of anything customer-facing.
"""

from __future__ import annotations

import os

from dataclasses import dataclass
from typing import Any, Callable

from collector.coverage import Coverage
from collector.pillars.usage import EXCLUDED_DATASOURCES, SIGNAL_FIELDS, USAGE_FLOOR

# Bump when any weight or scorer changes. The metric carries it, so history stays honest.
RUBRIC_VERSION = "1"

# Eligibility. A stack has to be doing real work before "how mature is it" is a meaningful question.
# Without this the leaderboard is won by near-empty stacks: `stack030` (1 user, scored on 7 of 9
# dimensions) came first and `stack031` (3 users, 2 series) placed sixth, because renormalising over the
# available weight rewards having little enough data that the hard dimensions do not apply.
# Measured: at 1 user the gate lets `stack030` (1 user, 5,960 series) place second, because engagement is
# daily/active and a single user logging in daily scores a trivial 100. Three is where the ratio
# dimensions stop being noise - the same small-N problem as admin share.
MIN_ELIGIBLE_USERS = 3
# And a stack judged on a thin slice of the rubric is not comparable to one judged on all of it.
MIN_WEIGHT_COVERED = 0.8

# Below this many users, admin *share* is structural noise; score the absolute count instead.
ADMIN_MIN_USERS = 5
ADMIN_MAX_ABSOLUTE = 2
# Below this many series, label-value counts say nothing about discipline. 5,000 rather than 10,000 so
# the dimension actually reaches the mid-sized stacks - `stack030` at 5,960 series carries a ratio of
# 1.02, the worst in the estate, and a 10,000 floor excused it.
CARDINALITY_MIN_SERIES = 5_000

# Alert rules per dashboard. Measured estate: p75 = 0.53, p90 = 4.14, max = 10.61.
ALERT_BAND = (0.2, 3.0)
# Dashboards per active user. Measured: p25 = 5.3, median 8.5, p90 = 21.
DASHBOARD_BAND = (2.0, 25.0)

TIERS = (("leading", 75.0), ("solid", 50.0), ("lagging", 25.0), ("dormant", 0.0))

# Closed vocabulary, so it can be a metric label and a dashboard breakdown.
UNSCORED_REASONS = ("paused", "too_few_users", "no_signal_above_floor", "insufficient_rubric_coverage")

# Grafana staff must never appear as an owner in customer-facing output.
STAFF_DOMAINS = ("@grafana.com",)
# Logins to exclude from ownership: vendor or partner staff who created a stack on the org's behalf.
# Counting them as owners attributes the customer's estate to whoever set it up. Populate for your own
# deployment - empty is the honest default, because this cannot be guessed.
STAFF_LOGINS: frozenset[str] = frozenset(
    s.strip() for s in os.environ.get("GCINSIGHT_STAFF_LOGINS", "").split(",") if s.strip()
)


def is_staff(identity: str | None) -> bool:
    if not identity:
        return False
    low = identity.strip().lower()
    return low in STAFF_LOGINS or any(d in low for d in STAFF_DOMAINS)


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def _band(value: float, lo: float, hi: float) -> float:
    """100 inside [lo, hi], decaying linearly to 0 at 0 and at 3x hi. Both extremes are failures."""
    if lo <= value <= hi:
        return 100.0
    if value < lo:
        return _clamp(100.0 * value / lo) if lo else 0.0
    return _clamp(100.0 * (1 - (value - hi) / (2 * hi))) if hi else 0.0


def _lower_better(value: float, good: float, bad: float) -> float:
    if value <= good:
        return 100.0
    if value >= bad:
        return 0.0
    return _clamp(100.0 * (bad - value) / (bad - good))


def _higher_better(value: float, bad: float, good: float) -> float:
    if value >= good:
        return 100.0
    if value <= bad:
        return 0.0
    return _clamp(100.0 * (value - bad) / (good - bad))


@dataclass(frozen=True)
class Dimension:
    key: str
    weight: float
    what: str
    how: str
    # Returns (score 0-100, raw value shown to the owner) or None when not applicable.
    score: Callable[[dict[str, Any], dict[str, Any] | None], tuple[float, Any] | None]


# --- Scorers. Each returns None rather than 0 when the dimension cannot be judged. ---

def signals_in_use(stack: dict[str, Any]) -> list[str]:
    return [k for k, f in SIGNAL_FIELDS.items() if (stack.get(f) or 0) > USAGE_FLOOR]


def _signal_breadth(s, _dp):
    """Three signals is mature; five is exceptional, not the bar.

    Scoring `used / 5` gave ~90% of the estate an identical 20.0 - a 15%-weight dimension with almost no
    variance, which only compresses the range and puts "leading" out of reach. Using metrics well is a
    legitimate position, so the curve tops out at 3.
    """
    used = signals_in_use(s)
    return _higher_better(len(used), 0, 3), f"{len(used)} of {len(SIGNAL_FIELDS)} signals above floor"


def _alerting(s, _dp):
    dashboards = s.get("dashboardCnt") or 0
    alerts = s.get("alertCnt") or 0
    if not dashboards:
        return None
    ratio = alerts / dashboards
    return _band(ratio, *ALERT_BAND), f"{alerts} rules / {dashboards} dashboards = {ratio:.2f}"


def _engagement(s, _dp):
    active = s.get("currentActiveUsers") or 0
    if not active:
        return None
    ratio = (s.get("dailyUserCnt") or 0) / active
    return _higher_better(ratio, 0.0, 0.75), f"{s.get('dailyUserCnt') or 0}/{active} daily = {ratio:.2f}"


def _access_hygiene(s, _dp):
    """Share above ADMIN_MIN_USERS; absolute count below it, where share is structural."""
    users = s.get("currentActiveUsers") or 0
    admins = s.get("currentActiveAdminUsers") or 0
    if not users:
        return None
    if users < ADMIN_MIN_USERS:
        return (100.0 if admins <= ADMIN_MAX_ABSOLUTE else 0.0), f"{admins} admins of {users} users"
    share = 100.0 * admins / users
    return _lower_better(share, 20.0, 75.0), f"{admins}/{users} admins = {share:.0f}%"


def _dashboard_utilisation(s, _dp):
    users = s.get("currentActiveUsers") or 0
    if not users:
        return None
    ratio = (s.get("dashboardCnt") or 0) / users
    return _band(ratio, *DASHBOARD_BAND), f"{s.get('dashboardCnt') or 0}/{users} = {ratio:.1f} per user"


def _datasource_breadth(s, _dp):
    types = len([1 for k, v in (s.get("datasourceCnts") or {}).items()
                 if v and k not in EXCLUDED_DATASOURCES])
    return _higher_better(types, 0, 5), f"{types} datasource types"


def _adaptive_adoption(_s, dp):
    am = (dp or {}).get("adaptive_metrics") or {}
    if not am.get("available"):
        return None
    applied, pending = am["rules_applied"], am["recommendations_pending"]
    if not applied and not pending:
        # Nothing applied and nothing on offer: no headroom, so not a failure.
        return None
    total = applied + pending
    return 100.0 * applied / total, f"{applied} applied / {pending} pending"


def _cardinality_discipline(s, dp):
    """Only above CARDINALITY_MIN_SERIES - the ratio is size-biased and meaningless below it."""
    card = (dp or {}).get("cardinality") or {}
    series = s.get("hmInstancePromCurrentActiveSeries") or 0
    if not card.get("available") or series < CARDINALITY_MIN_SERIES:
        return None
    values = card.get("label_values_count_total") or 0
    ratio = values / series
    return _lower_better(ratio, 0.05, 0.5), f"{values:,} values / {series:,} series = {ratio:.3f}"


def _collector_health(_s, dp):
    fm = (dp or {}).get("fleet") or {}
    if not fm.get("available"):
        return None
    collectors, pipelines = fm.get("collectors") or 0, fm.get("pipelines") or 0
    if not collectors and not pipelines:
        return None  # Fleet Management simply not in use; not a maturity failure.
    if pipelines and not collectors:
        return 0.0, f"{pipelines} pipelines, 0 collectors registered"
    return 100.0, f"{collectors} collectors, {pipelines} pipelines"


RUBRIC: tuple[Dimension, ...] = (
    Dimension("signal_breadth", 0.15, "Signals genuinely in use",
              f"share of {len(SIGNAL_FIELDS)} signals above the {USAGE_FLOOR}-unit floor", _signal_breadth),
    Dimension("alerting_proportionality", 0.15, "Alerting neither absent nor sprawling",
              f"alert rules per dashboard, ideal {ALERT_BAND[0]}-{ALERT_BAND[1]}; both extremes score 0",
              _alerting),
    Dimension("adaptive_adoption", 0.15, "Adaptive Metrics recommendations acted on",
              "applied rules as a share of applied + pending; not scored where there is no headroom",
              _adaptive_adoption),
    Dimension("engagement", 0.15, "People actually log in",
              "daily users / active users, 100 at 0.75", _engagement),
    Dimension("access_hygiene", 0.10, "Admin rights not handed to everyone",
              f"admin share, 100 at <=20% and 0 at >=75%; under {ADMIN_MIN_USERS} users scored on "
              f"absolute count (<={ADMIN_MAX_ABSOLUTE})", _access_hygiene),
    Dimension("cardinality_discipline", 0.10, "Label values proportionate to volume",
              f"label values / series, 100 at <=0.05; only scored above {CARDINALITY_MIN_SERIES:,} series",
              _cardinality_discipline),
    Dimension("dashboard_utilisation", 0.10, "Dashboards proportionate to the audience",
              f"dashboards per active user, ideal {DASHBOARD_BAND[0]}-{DASHBOARD_BAND[1]}",
              _dashboard_utilisation),
    Dimension("datasource_breadth", 0.05, "More than one thing plugged in",
              "distinct datasource types, 100 at 5+, excluding the auto-provisioned one",
              _datasource_breadth),
    Dimension("collector_health", 0.05, "Fleet Management collectors actually connected",
              "0 where pipelines exist with no collectors; not scored where FM is unused",
              _collector_health),
)


def tier_for(score: float | None) -> str:
    if score is None:
        return "unscored"
    for name, floor in TIERS:
        if score >= floor:
            return name
    return "dormant"


def eligibility(stack: dict[str, Any]) -> str | None:
    """Why this stack cannot be scored, or None if it can.

    Returns a closed vocabulary so the reason is a bounded metric label and shows on the dashboard -
    "unscored" with no reason is the kind of blank that gets read as a bug.
    """
    if stack.get("status") == "paused":
        return "paused"
    users = stack.get("currentActiveUsers") or 0
    if users < MIN_ELIGIBLE_USERS:
        return "too_few_users"
    if not signals_in_use(stack):
        return "no_signal_above_floor"
    return None


def score_stack(stack: dict[str, Any], dp: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score one stack. Returns the composite plus every dimension's contribution.

    An ineligible stack scores `None`, not 0 - "we cannot judge this" and "this is bad" are different
    statements and a 0 on a leaderboard is an accusation.
    """
    ineligible = eligibility(stack)
    dimensions: list[dict[str, Any]] = []
    weighted = 0.0
    weight_covered = 0.0
    for dim in RUBRIC:
        result = dim.score(stack, dp)
        if result is None:
            dimensions.append({"dimension": dim.key, "weight": dim.weight, "score": None,
                               "raw": None, "contribution": None, "applicable": False})
            continue
        score, raw = result
        score = _clamp(score)
        weighted += score * dim.weight
        weight_covered += dim.weight
        dimensions.append({"dimension": dim.key, "weight": dim.weight, "score": round(score, 1),
                           "raw": raw, "contribution": round(score * dim.weight, 2),
                           "applicable": True})

    # Renormalise over the weight actually available - but only rank a stack judged on enough of the
    # rubric to be comparable. Thin coverage plus renormalisation is what put a 1-user stack first.
    thin = weight_covered < MIN_WEIGHT_COVERED
    reason = ineligible or ("insufficient_rubric_coverage" if thin else None)
    composite = (
        None if reason or not weight_covered else round(weighted / weight_covered, 1)
    )
    return {
        "slug": str(stack["slug"]),
        "score": composite,
        "tier": tier_for(composite),
        "unscored_reason": reason,
        "dimensions_scored": sum(1 for d in dimensions if d["applicable"]),
        "dimensions_total": len(RUBRIC),
        "weight_covered": round(weight_covered, 2),
        "partial": weight_covered < 0.999,
        "dimensions": dimensions,
    }


def dimension_means(scored: list[dict[str, Any]]) -> dict[str, float]:
    """Estate mean per rubric dimension - the aggregate the per-stack view cannot trend (PLAN 9.1).

    Two exclusions, and both matter more than they look:

    * **Only dimensions that were actually scored count.** A scorer returns `None` rather than 0 when it
      cannot judge, and the T3 dimensions are absent entirely on a T1/T2 run. Treating `None` as 0 would
      make every dimension look worse on the hourly tier than on the weekly one - a trend that tracks
      which tier ran last instead of the estate.
    * **Stacks carrying any `unscored_reason` are dropped whole.** A dormant or 1-user stack can still
      have scoreable dimensions, and including them measures stack creation rather than maturity. This is
      the same small-N effect that once put `stack030` (1 user) top of the leaderboard.

    Each dimension therefore gets its OWN denominator. Returns `{}` when nothing was scored, so the
    caller emits an absent series rather than a zero.
    """
    buckets: dict[str, list[float]] = {}
    for entry in scored:
        if entry.get("unscored_reason") is not None:
            continue
        for d in entry.get("dimensions", []):
            if not d.get("applicable") or d.get("score") is None:
                continue
            buckets.setdefault(str(d["dimension"]), []).append(float(d["score"]))
    return {key: round(sum(vals) / len(vals), 1) for key, vals in buckets.items() if vals}


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def build(
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    dataplane: dict[str, Any] | None = None,
    stack_detail: dict[str, Any] | None = None,
) -> tuple[list[tuple[str, dict[str, str], float]], dict[str, list[dict[str, Any]]]]:
    dataplane = dataplane or {}
    stack_detail = stack_detail or {}
    metrics: list[tuple[str, dict[str, str], float]] = []

    scored = [score_stack(s, dataplane.get(str(s["slug"]))) for s in stacks]
    for entry in scored:
        if entry["score"] is not None:
            metrics.append((
                "gcinsight_maturity_score",
                {"stack": entry["slug"], "version": RUBRIC_VERSION},
                float(entry["score"]),
            ))

    values = [e["score"] for e in scored if e["score"] is not None]
    for kind, p in (("median", 0.5), ("p90", 0.9)):
        v = _percentile(values, p)
        if v is not None:
            metrics.append(("gcinsight_maturity_percentile",
                            {"kind": kind, "version": RUBRIC_VERSION}, float(v)))
    if values:
        metrics.append(("gcinsight_maturity_percentile",
                        {"kind": "worst", "version": RUBRIC_VERSION},
                        float(min(values))))

    # The whole rubric is a T3 product: without the data plane no stack clears the coverage bar, so every
    # tier count is structurally 0. Emitting those zeros from an hourly T1 would overwrite the real
    # weekly values at a later timestamp and flatten the leaderboard to nothing (PLAN 5.3). Emit only
    # when something was actually scored; the carry-forward republishes these between T3 runs.
    if values:
        for name, _floor in TIERS:
            metrics.append((
                "gcinsight_maturity_stacks_by_tier",
                {"kind": name, "version": RUBRIC_VERSION},
                float(len([e for e in scored if e["tier"] == name])),
            ))
        # Estate mean per dimension (PLAN 9.1). Inside this guard deliberately: on a tier with no data
        # plane nothing clears the coverage bar, and a structural 0 here would overwrite the real weekly
        # value at a later timestamp exactly as the tier counts once did.
        for dim_key, mean in dimension_means(scored).items():
            metrics.append((
                "gcinsight_maturity_dimension_mean",
                {"dimension": dim_key, "version": RUBRIC_VERSION},
                float(mean),
            ))
        # Why stacks fell out, as a bounded enum. An unexplained "unscored" reads as a collector bug.
        for reason in UNSCORED_REASONS:
            metrics.append((
                "gcinsight_maturity_unscored",
                {"reason": reason, "version": RUBRIC_VERSION},
                float(len([e for e in scored if e["unscored_reason"] == reason])),
            ))

    # --- Ownership directory, T2. Admins of the stack itself, never createdBy/updatedBy. ---
    owners: list[dict[str, Any]] = []
    for slug, detail in stack_detail.items():
        admins = [u for u in (detail or {}).get("users", []) or [] if u.get("role") == "Admin"]
        external = [u for u in admins if not is_staff(u.get("login")) and not is_staff(u.get("email"))]
        owners.append({
            " Stack": slug,
            "Admins": len(admins),
            # Grafana staff are filtered out of the customer-facing owner list, always.
            "Owner candidates": ", ".join(
                sorted({u.get("name") or u.get("login") or "?" for u in external})
            ) or None,
            "Owner emails": ", ".join(sorted({u["email"] for u in external if u.get("email")})) or None,
            "Staff admins excluded": len(admins) - len(external),
        })

    by_slug = {str(s["slug"]): s for s in stacks}
    leaderboard = sorted(
        [
            {
                " Stack": e["slug"],
                "Score": e["score"],
                "Tier": e["tier"],
                "Unscored reason": e["unscored_reason"],
                "Dimensions scored": f"{e['dimensions_scored']} of {e['dimensions_total']}",
                "Partial": e["partial"],
                "Active series": by_slug[e["slug"]].get("hmInstancePromCurrentActiveSeries") or 0,
                "Users (active)": by_slug[e["slug"]].get("currentActiveUsers") or 0,
                **{d["dimension"]: d["score"] for d in e["dimensions"]},
            }
            for e in scored
        ],
        key=lambda r: (r["Score"] is None, -(r["Score"] or 0)),
    )

    # The rubric is a T3 product end to end: without the data plane nothing clears the coverage bar, so
    # every one of these tables would be all-nulls and would overwrite the real weekly ones.
    if not values:
        return metrics, {}

    views: dict[str, list[dict[str, Any]]] = {
        "maturity": leaderboard,
        # Published beside the score. Without this the leaderboard is unarguable-with, which is worse.
        "maturity_rubric": [
            {" Dimension": d.key, "Weight": d.weight, "What it measures": d.what,
             "How it is scored": d.how}
            for d in RUBRIC
        ] + [{" Dimension": "RUBRIC VERSION", "Weight": None,
              "What it measures": RUBRIC_VERSION,
              "How it is scored": "emitted as gcinsight_maturity_score{version} so a rubric change "
                                  "starts a new series rather than rewriting history"}],
        # The "explainable per stack" obligation: one row per stack per dimension.
        "maturity_dimensions": [
            {" Stack": e["slug"], "Dimension": d["dimension"], "Weight": d["weight"],
             "Score": d["score"], "Raw": d["raw"], "Contribution": d["contribution"],
             "Applicable": d["applicable"]}
            for e in scored for d in e["dimensions"]
        ],
        "maturity_summary": [{
            " Metric": "Stacks scored",
            "Value": f"{len(values)} of {coverage.scannable} scannable ({coverage.total} total)",
        }, {
            " Metric": "Not scored, and why",
            "Value": ", ".join(
                f"{r}: {len([e for e in scored if e['unscored_reason'] == r])}"
                for r in UNSCORED_REASONS
                if any(e["unscored_reason"] == r for e in scored)
            ) or "none",
        }, {
            " Metric": f"Eligibility bar",
            "Value": f">= {MIN_ELIGIBLE_USERS} active users, at least one signal above "
                     f"{USAGE_FLOOR} units, and >= {int(100*MIN_WEIGHT_COVERED)}% of the rubric "
                     f"applicable. Near-empty stacks would otherwise top the leaderboard.",
        }, {
            " Metric": "Median score",
            "Value": _percentile(values, 0.5),
        }, {
            " Metric": "p90 score",
            "Value": _percentile(values, 0.9),
        }, {
            " Metric": "Worst score",
            "Value": min(values) if values else None,
        }, {
            " Metric": "Scored on all dimensions",
            "Value": len([e for e in scored if not e["partial"]]),
        }, {
            " Metric": "Rubric version",
            "Value": RUBRIC_VERSION,
        }],
    }
    if stack_detail:
        views["maturity_owners"] = sorted(owners, key=lambda r: r[" Stack"])
    return metrics, views
