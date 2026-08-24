# Series budget

Everything lands on the configured write stack alone. That stack's own series over the same range is the denominator; the org total never is.

`BUDGET.md` in the repository is generated from `collector/emit/budget.py` and carries the full metric catalogue. This page is the design rule behind it.

## Declared capacity is not measured use

| | Series |
|---|---:|
| Declared, all phases | 7,828 |
| Runaway ceiling | 100,000 |

Declared capacity reserves every bounded enum at its ceiling, so it exceeds the series present at any particular instant. **Do not quote it as live use.** Re-measure with a range query and a matching denominator before reporting a footprint.

The 100,000 ceiling is a runaway backstop, not a target and not a licence for unbounded labels. `guard.ALLOWED_LABELS` and the per-metric shape checks are the real controls.

## By pillar

| Pillar | Mimir series |
|---|---:|
| A — estate | 296 |
| B — cost | 1,101 |
| C — usage | 62 |
| D — maturity | 582 |
| E — risk | 301 |
| F — value | 21 |
| I — AI | 895 |
| J — dashboards | 4,368 |
| scan self-telemetry | 202 |

## The three rules

1. **A per-stack metric carries at most one other label, and that label's enum is at most 4 values.** `stack` × `kind`(10) is 2,710 series. That is a table, not a trend.
2. **A per-stack time series must carry a bounded, actionable trend.** Identity-bearing or wide cross-product detail belongs in a view, even where the total ceiling would allow the series.
3. **Label keys must be in the `collector/emit/guard.py` allow-list.** The guard is the runtime gate; the budget module is the design-time one.

Identities, metric names, dashboard uids, rule names and service-account names never become metric labels. This holds even where the deploying organisation has approved clear identities in S3 and Loki.

## Deliberately views, not metrics

Roughly thirty surfaces are published as S3 tables rather than as series, and each one is a recorded decision rather than an omission. A few that show why:

| View | Series if emitted | Why a view |
|---|---:|---|
| `ai_category_surface` | 5,691 | per-stack human-vs-machine detail; a stack-by-taxonomy metric is a cross product |
| `maturity_dimensions` | 2,439 | a table shows every dimension's contribution; only the composite needs trending |
| `estate` | 271 | wide per-stack inventory: region, cluster, status, users by role, admin share, age, idle, drift |
| `risk_sa_and_token_inventory` | 271 | named service-account and token inventory stays out of metric labels |
| `cost_adaptive_metric_recommendations` | 1 | bounded top-ten-per-stack action queue; metric names stay out of labels |
| `insights_coverage` | 1 | the denominator: why a stack has no figures |

Two of those rows carry a second lesson. `ai_credential_coverage` exists so that paused and opted-out stacks read as **skipped**, not as failures. And `ai_config_disabled` counts only an explicit `false` — `enabled` is absent on skills, and unknown is not disabled.

## Measuring the real footprint

Compare the measured platform footprint with the write stack's own series over the same range. Never copy a measured count back into the generated `BUDGET.md`; it is a declaration, and a measurement pasted into it stops being either.
