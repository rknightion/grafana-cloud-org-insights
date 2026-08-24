# Architecture

One stdlib-only ARM64 image runs on ECS Fargate, started by EventBridge Scheduler. Every tier has its own task definition, because Scheduler does not support container overrides.

## Scan tiers

| Tier | Default cadence | Owns |
|---|---|---|
| T1 | hourly | fresh inventory, access policies, org members and Fleet Management |
| T2 | daily | stack detail, service accounts, Assistant, usage insights, Adaptive Logs, public dashboards, alert routing, dashboard inventory and datasource query cost |
| T3 | every 6 hours | Mimir cardinality and Adaptive Metrics |
| T4 | daily | independent one-day and seven-day estate diffs, computed from S3 |
| provisioner | daily | per-stack reader reconciliation |

Every deadline is strictly shorter than its interval. Staleness alerts move with the schedules, and carry-forward expires after alerts have had time to fire.

## The estate is discovered, never declared

Every scan discovers the current estate first, then left-joins per-stack inputs onto that inventory. Payload keys never define the estate.

Two failure modes fall out of that ordering. A removed stack cannot survive through carry-forward, because it is absent from the inventory the join runs against. And an empty inventory result means *unknown*, not *empty* - it cannot blank all state.

Paused stacks answer the control plane with a conflict response and are **skipped, not failed**. Coverage is therefore a ratio against scannable stacks, never against the total. Against the total, a handful of paused stacks caps coverage below 100% for ever and trains everyone to ignore the warning.

## Hydration

Every tier composes the full view set from the full input set. Inputs a tier does not own are hydrated from the owning tier's latest envelope, so an hourly T1 run publishes views built from the newest T2 and T3 data as well as its own.

`VIEW_INPUTS` is derived by composing subsets of the fixture rather than being hand-written, so a view cannot quietly disagree with the inputs it actually reads.

A view whose inputs are unsatisfied is **withheld**, leaving the last good S3 object visible with its older timestamp. A metric a tier cannot compute is **absent**, never a structural zero. A table that stops advancing is therefore the signal that something upstream has stopped - which is only true if nothing in the pipeline is willing to write a confident zero.

## Three landing zones

Each is chosen for what it is good at.

- **Mimir** takes bounded time series, for trends and alerting. Labels carry `stack`, `region`, tier and fixed enums only.
- **Loki** takes unbounded finding detail that benefits from retention and querying - including the offender names a metric label must never carry: metric names, dashboard uids, user logins, rule names.
- **S3** takes wide current-state tables under `views/`, which the dashboards render directly, plus a private `scans/` archive used for hydration, replay and diffs. Long-term history lives in Mimir, not in the archive.

## The cardinality rule

Identities, metric names, dashboard uids, rule names and service-account names never become metric labels. This is absolute, and it survives the deploying organisation's decision to allow clear identities elsewhere - S3 and Loki may carry them; a metric label may not.

`collector/emit/budget.py` is the catalogue authority and the design-time gate; `guard.ALLOWED_LABELS` and per-metric shape checks are the runtime gate. The declared 100,000-series ceiling is a runaway backstop, not a target.

Two rules decide whether something is a metric or a view:

- A per-stack metric carries **at most one** other label, and that label's enum is **at most 4** values. `stack` × `kind`(10) is 2,710 series - that is a table, not a trend.
- A per-stack time series must carry a bounded, actionable trend. Identity-bearing or wide cross-product detail belongs in a view even where the total ceiling would allow it.

[Series budget](series-budget.md) has the declared catalogue and the views that were deliberately not emitted.

## Savings arithmetic

Adaptive Metrics recommendations are requested with `?verbose=true`. The default response has no series counts and cannot support a saving - it is structurally complete-looking and insufficient.

Remediable series are the sum of positive `current_series_count - recommended_series_count` reductions for `add` and `update` actions. `keep` and `remove` do not represent an unrealised reduction. An unknown action, or a missing before/after pair, makes the aggregate **unavailable** rather than zero.

Adaptive Logs recommendation volume is the residual volume still flowing, and has no declared window. It can rank pending work; it cannot be converted into a monthly applied saving. Applied drops are read directly by dashboard panels from `grafanacloud-usage`.

## Dashboard contracts

All dashboards use `dashboard.grafana.app/v2`.

Prometheus queries against periodic collector metrics are **range queries reduced with `lastNotNull`**. An instant query is empty outside Mimir's lookback delta, so a periodic metric read instantly renders an empty panel that looks like missing data.

Rate-shaped `grafanacloud-usage` series are compared over a window, and numerator and denominator populations must match. The three user populations are not interchangeable: `currentActiveUsers` is adoption, `billingActiveUsers` is the only valid money denominator, and `dailyUserCnt` is daily activity. Every panel and view names the source it uses.

Pillar J - the `dashboards` surface - queries each stack's own `grafanacloud-usage-insights` datasource. That datasource exposes a whole region, so every LogQL selector includes `instance_type="grafana"` and the current stack's `instance_id`. Selectors are created through one helper, and `_query` refuses a template without the regional guard. Without it, one stack's figures are silently repeated across every stack in its region.

Usage events and inventory answer different questions, and both are published. Pillar J reports public dashboards **observed in use**; the Risk dashboard enumerates **configured** public dashboards whether or not anybody opened them. A share nobody opens is invisible to usage events and is exactly the one worth finding.

## Out of scope

Deliberately not built:

- per-tenant self-service, and LBAC/RBAC partitioning of the central dashboards;
- rebuilding an existing monthly showback or invoice;
- mutation of customer dashboards, alert rules, service accounts or access policies by the collector;
- Synthetic Monitoring result inventory, until a safe unattended read route exists;
- dashboard duplication detection and natural-language querying.
