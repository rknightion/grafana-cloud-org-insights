# Grafana Cloud org insights - design spec

## 1. Purpose

Give a platform team and its leadership an estate-wide view of a dynamically discovered Grafana Cloud
organisation. The platform answers operational, governance, adoption and value questions without
installing an agent on every stack or configuring a fixed estate list.

The three user populations are not interchangeable: `currentActiveUsers` is adoption,
`billingActiveUsers` is the only valid money denominator, and `dailyUserCnt` is daily activity.
Every panel and view names the source it uses.

## 2. Scope

The dashboard registry contains ten surfaces: estate health, consumption and cost, consumer behaviour,
maturity, risk and hygiene, business value, operations, commercial, Assistant/AI and dashboard usage.

Deliberately out of scope:

- per-tenant self-service and LBAC/RBAC partitioning of the central dashboards;
- rebuilding an existing monthly showback or invoice;
- mutation of customer dashboards, alert rules, service accounts or access policies by the collector;
- Synthetic Monitoring result inventory until a safe unattended read route exists;
- dashboard duplication detection and natural-language querying.

## 3. Data sources

| Source | Credential | Collection shape |
|---|---|---|
| Grafana.com control plane: stack inventory, users, plugins, org members and access policies | org-realm read token | collector |
| Per-stack data plane: Mimir cardinality, Adaptive Metrics and Fleet Management | org-realm read token with signal-instance basic auth | collector |
| Each stack's Grafana API and datasource proxy: Assistant, service accounts, usage insights, Adaptive Logs, public dashboards, dashboard/folder/team/role inventory and alert routing | stack-local reader token | collector |
| `grafanacloud-usage` on the write stack | write-stack reader, exact datasource query scope | live panels plus bounded capability-adoption collector input |
| Optional `config/ratecard.csv` in S3 | task-role read of that single object | collector pricing seam |
| Mimir, Loki and S3 on the nominated write stack/account | stack-realm writer token and AWS task role | emit path |

If data is already present in `grafanacloud-usage`, a panel is preferred unless a durable named view or
trendable bounded series unlocks a separate workflow. Capability adoption is the deliberate exception:
its S3 call list and gap trend support enablement outreach and closure tracking.

The control-plane inventory's `datasourceCnts` map is the adjacent-estate source. Vendor type names and
stack/type/count mappings stay in S3 views; Mimir receives only the scalar distinct-type count. The
auto-provisioned knowledge-graph datasource is excluded from adoption. Coverage presents that
point-in-time provisioned inventory beside Pillar J's separately windowed, separately covered evidence
of datasource types actually queried.

## 4. Credential and permission model

1. `GCINSIGHT_READ_TOKEN` is an org-realm read credential. It discovers the estate and reads the
   control plane and data plane.
2. `GCINSIGHT_WRITE_TOKEN` is a stack-realm Mimir/Loki writer for the nominated write stack alone.
3. The provisioner uses a separate org-realm token carrying only `stacks:read` and
   `stack-service-accounts:write`. The collector never receives it.
4. Each provisionable stack has a standing service account with basic role `None` and the custom
   role `custom:gcinsight.reader`. Its token is stored as an SSM `SecureString` under the
   configured prefix.

The custom role is compared as `(action, scope)` pairs. `datasources:read` may list datasource
metadata. Every reader can query exactly `datasources:uid:grafanacloud-usage-insights`; the write-stack
reader alone also receives `datasources:uid:grafanacloud-usage`. Query is never widened to
`datasources:*`.
Mutation and secret-bearing actions remain absent. A healthy reconciliation performs reads only and
does not mint a replacement token.

The collector's HTTP client rejects every method except GET. Some read APIs are implemented as
Connect-RPC POSTs; those calls live outside the collector HTTP client and are authorised by read scopes.

## 5. Runtime and scan tiers

The shipped runtime is one stdlib-only ARM64 image on ECS Fargate, started by EventBridge Scheduler.
Every tier has its own task definition because Scheduler does not support container overrides.

| Tier | Default cadence | Owns |
|---|---|---|
| T1 | hourly | fresh inventory, access policies, org members and Fleet Management |
| T2 | daily | stack detail, service accounts, Assistant, usage insights, capability adoption, Adaptive Logs, public dashboards, alert routing, dashboard inventory and datasource query cost |
| T3 | every 6 hours | Mimir cardinality and Adaptive Metrics |
| T4 | daily | independent one-day and seven-day estate diffs from S3 |
| provisioner | daily | per-stack reader reconciliation |

Every deadline is strictly shorter than its interval. Staleness alerts move with the schedules, and
carry-forward expires after alerts have had time to fire.

Every scan discovers the current estate first. Per-stack inputs are left-joined onto that inventory;
payload keys never define the estate. A removed stack cannot survive through carry-forward, while an
empty inventory result means unknown and cannot blank all state.

## 6. Hydration, output and cardinality

Every tier composes from the full optional-input set. Inputs it does not own are hydrated from the owning
tier's latest envelope. `VIEW_INPUTS` is derived by composing subsets of the fixture, not
hand-written. A view with unsatisfied inputs is withheld so the last good S3 object remains visible with
its older timestamp. A metric the tier cannot compute is absent, never a structural zero.

Outputs have three homes:

- Mimir for bounded time series and alerts;
- Loki for unbounded finding detail that benefits from retention and querying;
- S3 `views/` for wide current-state tables, plus private `scans/` for hydration, replay and diffs.

Metric labels are limited to bounded keys such as `stack`, `region`, tier and fixed enums.
Identities, metric names, dashboard uids, rule names and service-account names never become metric labels.
`collector/emit/budget.py` is the catalogue authority. Its 100,000-series ceiling is a runaway
backstop; `guard.ALLOWED_LABELS` and per-metric shape checks are the primary controls. A live
footprint is measured against the write stack over the same range, never against the whole org.

## 7. Savings and rate-card semantics

Adaptive Metrics recommendations are requested with `?verbose=true`. The default response has no
series counts and cannot support a saving. Remediable series are the sum of positive
`current_series_count - recommended_series_count` reductions for `add` and `update`
actions. `keep` and `remove` do not represent an unrealised reduction. An unknown action or
a missing before/after pair makes the aggregate unavailable rather than zero.

The optional rate card prices ten supported dimensions. `price()` returns `None`, never
`0.0`, when a dimension is not priced. A partially priced card discloses which components are
omitted and must not present the subtotal as a complete estate total. Currency and billing period come
from the card; mixed currencies are rejected. Metrics-series pricing is per 1,000 series where declared.
Metrics supports two explicit bases: `base_rate_only` excludes DPM, while `dpm_aware` applies
`max(active_series, total_dpm / included_dpm)` per stack. A DPM-aware card uses the live usage inputs and
dedicated dashboard calculation; it never falls back to the two-input base-series saving.

Adaptive Logs recommendation volume is the residual volume still flowing and has no declared window.
It can rank pending work but cannot be converted into a monthly applied saving. Applied drops are read
directly by dashboard panels from `grafanacloud-usage`.

## 8. Dashboard contracts

All dashboards use `dashboard.grafana.app/v2`. Prometheus queries against periodic collector
metrics are range queries reduced with `lastNotNull`; an instant query is empty outside Mimir's
lookback delta. Rate-shaped `grafanacloud-usage` series are compared over a window, and
numerator/denominator populations must match.

Pillar J queries each stack's own `grafanacloud-usage-insights` datasource. That datasource exposes
a whole region, so every LogQL selector includes `instance_type="grafana"` and the current stack's
`instance_id`. For Grafana events, `instance_id` is the stack's `id`. Selectors are
created through one helper and `_query` refuses a template without the regional guard.

Usage events and inventory answer different questions. Pillar J reports public dashboards observed in
use; the Risk dashboard enumerates configured public dashboards whether or not anybody opened them. The
generic build presents both and leaves the policy target to the deploying organisation.

Every published view must be rendered and every declared metric must be rendered or alerted. Table
schemas cover legitimately empty finding views without turning a not-yet-published view into a silent
blank panel.

## 9. Security and privacy

Deployment identifiers have no defaults. Build-time Grafana credentials are separate from runtime
credentials and should be short-lived. Alert rules publish paused and unrouted; activation requires an
explicit receiver so rules cannot inherit an unrelated production notification policy.

Identities may be stored in clear when the deploying organisation has approved that policy. The
cardinality rule remains absolute: no identity reaches a metric label. The Infinity reader is allowed
only on `views/` and denied on `scans/` and `locks/`. Raw scans expire by lifecycle policy.

The generic repository contains synthetic fixtures only. A live compose-input export must be written
outside the committed fixture path and anonymised before use.

## 10. Acceptance and open capabilities

An installation is acceptable when:

1. every stack is either measured, skipped for a named reason, or counted as a failure;
2. every tier advances its scan envelope and dead-man timestamp on schedule;
3. label, metric, view and dashboard coverage gates pass;
4. the write-stack footprint is measured over a range and remains within the declared catalogue;
5. per-stack reader credentials remain basic-role-None, read-only and query-scoped;
6. a missing optional input withholds dependent output instead of publishing zero;
7. one-day and seven-day diffs report their populations and cannot borrow each other's interval bounds;
8. operators can rotate credentials, migrate alert titles, roll back an image and tear down recorded
   objects without name-pattern deletion.

Still unresolved: Synthetic Monitoring result inventory, Adaptive Profiles, and any Adaptive Traces
collection requiring permissions beyond the declared read-only role.
