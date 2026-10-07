# Grafana Cloud org insights - design spec

## Bounded labelling input and policy

`label_inventory` is a default-off T2 input over fresh live inventory, not a configured
estate or an exhaustive inventory. Current base collection reads exact-200 GET
`/api/prom/api/v1/cardinality/label_names` (head-only counts), Loki
`/loki/api/v1/labels` and `/loki/api/v1/label/{name}/values`, Tempo
`/tempo/api/v2/search/tags` and `/tempo/api/v2/search/tag/{scope.name}/values`
(bounded 24-hour samples), and the two exact Pyroscope read RPCs
`/querier.v1.QuerierService/LabelNames` and `LabelValues` through
`label_risk.profile_read`. Those POST exceptions do not change the GET-only shared client.
Metric value shapes, series denominators and cross-signal value-set comparisons remain
missing where not measured. Non-metric below-cap samples do not establish completeness.

Witnessed extensions are separately bounded: exact GET Mimir
`/api/prom/api/v1/cardinality/label_values`, Loki `/loki/api/v1/series`,
`/loki/api/v1/index/stats`, `/loki/api/v1/index/volume`, legacy
`/config/tenant/v1/limits`, and Tempo `/tempo/api/v2/search/tag/name/values`.
A witness is not evidence those extensions are shipping in this base source.
Write-scoped `/loki/api/v1/config/limits/applied` is not approved; unreadable Tempo
overrides remain parked. No log-line route, new permission, YAML feature or scope follows.

Only minimized label/attribute names, distinct counts (`exact` or `at_least`), closed
non-PII shape counts (`uuid`, `hex_id`, `epoch`, `url_with_id`, `long_value`), and
series/stream counts where actually measured may persist in S3 views and the private
hydration input. These register items never reach Loki, finding events, metrics,
stdout, diagnostic `--out` or errors. Raw values remain transient. Email, IP, phone,
JWT and card shapes are not duplicated from `label_risk`; names over 512 UTF-8 bytes
or matching PII become class/count only. Missing, unsupported, parked or incomplete
inputs do not become clean passes, fabricated zeros or a score below coverage 0.8.
Unsatisfied views remain absent, preserving last-good S3 objects.

Evaluator policy, source budget and static allowlist use the existing environment/config
path, not a persisted-schema extension. Shared opt-outs remain genuine policy. The
caller slice is <=900 seconds and <=a quarter of remaining T2 time; tuning cannot
relax transport/body caps or imply bounded daemon-read lifetime or process memory.
See /Users/rob/repos/grafana-cloud-org-insights/RUNBOOK.md for the frozen policy API
and read-only dated stability artifact contract.

## 1. Purpose

Give a platform team and its leadership an estate-wide view of a dynamically discovered Grafana Cloud
organisation. The platform answers operational, governance, adoption and value questions without
installing an agent on every stack or configuring a fixed estate list.

The three user populations are not interchangeable: `currentActiveUsers` is adoption,
`billingActiveUsers` is the only valid money denominator, and `dailyUserCnt` is daily activity.
Every panel and view names the source it uses.

## 2. Scope

The dashboard registry contains eleven surfaces: estate health, consumption and cost, consumer behaviour,
maturity, risk and hygiene, business value, operations, commercial, Assistant/AI, dashboard usage and
observed estate coverage.

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
| Per-stack data plane: Mimir cardinality, Adaptive Metrics, Fleet Management and four-signal observed-name/label-risk inventory | org-realm read token with signal-instance basic auth | collector |
| Each stack's Grafana API and datasource proxy: Assistant, service accounts, usage insights, Adaptive Logs/Traces, optional SLO definitions, public dashboards, dashboard/folder/team/role inventory and alert routing | stack-local reader token | collector |
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
reader alone also receives `datasources:uid:grafanacloud-usage`. The separately selected Synthetic
query token can add only one uniquely discovered, valid Synthetic datasource UID. Query is never
widened to `datasources:*`.
Mutation actions remain absent. The named IRM and ML receipt risks below are explicit exceptions
to a blanket claim that all readable payloads are secret-free. A healthy reconciliation performs
reads only and does not mint a replacement token.

`GCINSIGHT_READER_PRODUCT_READS` defaults to empty. Its selected families, exact pairs, routes and
limits are described in [Configuration](docs/configuration.md#optional-product-readers) and
[CAPABILITIES](CAPABILITIES.md#optional-count-only-product-inputs). SLO and Synthetic retain only
counts and closed enums, not targets, scripts, headers or expressions. Synthetic collection requires
both `synthetic-monitoring` and the independent `synthetic-monitoring-query` token. The latter adds
only the uniquely discovered datasource UID matching `^[A-Za-z0-9_-]{1,40}$` plus unscoped probes read;
ambiguity or invalid discovery adds no query pair. Without it scans make no Synthetic calls. On
reconciliation, a legacy-correct role needs zero discovery; deselection can discover only to remove
an already-held pair matching that exact Synthetic UID. Other extra query pairs remain dangerous.
No product family or customer permission is granted by documentation. IRM count-integrity acceptance
is parked because its source still accepts HTTP 206. ML's job-top-level `grafanaApiKey` is discarded
before the unchanged generic credential guard; nested/other credentials remain rejected.

The collector's HTTP client rejects every method except GET. Some read APIs are implemented as
Connect-RPC POSTs; those calls live outside the collector HTTP client and are authorised by read scopes.
The label-risk source permits exactly the native Pyroscope LabelNames and LabelValues POST reads.
The observed-name source uses `_connect_rpc`, whose exact parsed-path suffix allowlist is Fleet
ListCollectors, Fleet ListPipelines and Pyroscope LabelValues. It requires HTTPS, a nonempty host,
no userinfo, query, fragment or percent-encoded path and refuses redirects. The separate label-risk
two-route exception does not expand this helper or authorise another POST.

## 5. Runtime and scan tiers

The shipped runtime is a stdlib-only multi-architecture image on ECS Fargate, started by EventBridge
Scheduler. The module defaults to ARM64; the image and configured task architecture must match.
Every tier has its own task definition because Scheduler does not support container overrides.

| Tier | Default cadence | Owns |
|---|---|---|
| T1 | hourly at :05 | fresh inventory, access policies, org members and Fleet Management |
| T2 | daily | stack detail, service accounts, Assistant, usage insights, signal inventory, label risk, capability adoption, Adaptive Logs/Traces, optional SLO/Synthetic and configured product counts, Loki retention, public dashboards, alert routing, dashboard inventory and datasource query cost |
| T3 | every 6 hours | Mimir cardinality and Adaptive Metrics |
| T4 | daily | independent one-day and seven-day estate diffs from S3 |
| provisioner | daily, opt-in | per-stack reader reconciliation |

These are module-default cadences in `schedule_timezone` (default `UTC`), not a deployment timetable.
See the [RUNBOOK timetable](RUNBOOK.md#scheduled-jobs) for all five jobs and schedule
controls. Deployment roots may override expressions and timezone. `create_provisioner` defaults false;
when created, its schedule requires both `schedules_enabled` and `provisioner_enabled`.

Every deadline is strictly shorter than its interval. Staleness alerts move with the schedules, and
carry-forward expires after alerts have had time to fire.

T1, T2 and T3 discover the current estate first; T4 compares recorded S3 scan populations without
calling the estate APIs. Per-stack inputs are left-joined onto that inventory;
payload keys never define the estate. A removed stack cannot survive through carry-forward, while an
empty inventory result means unknown and cannot blank all state.

## 6. Hydration, output and cardinality

T1, T2 and T3 compose from the full optional-input set. Inputs a tier does not own are hydrated from
the owning tier's latest envelope. T4 publishes independent historical diff views rather than composing
this optional-input set. `VIEW_INPUTS` is derived by composing subsets of the fixture, not
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

Rules-read coverage travels separately in publication metadata. Partial coverage can publish an
explicitly qualified measured subtotal, never an unqualified estate metric or finding gauge;
carry-forward must not resurrect that incomplete tier's estate claim. Recommendation-count and
pricing coverage are independent and cannot be inferred from readable rules. Current main discovers
segmentation as unsegmented, segmented or unknown. Whole-stack confidence requires known
unsegmented input; segmented, unknown and legacy inputs cannot establish whole-stack savings or
Adaptive maturity from default-only values. Qualified unsegmented subtotals remain useful. Positive
segment marginal counts do not prove disjointness or fallback additivity: no combined segment saving
is emitted and no segment object is mutated.

Adaptive Metrics recommendations are requested with `?verbose=true`. The default response has no
series counts and cannot support a saving. Remediable series are the sum of positive
`current_series_count - recommended_series_count` reductions for `add` and `update`
actions. `keep` and `remove` do not represent an unrealised reduction. An unknown action or
a missing before/after pair on a savings-bearing action makes the aggregate unavailable rather than
zero. Missing, duplicate or invalid metric identities and invalid count fields also withhold savings;
count-less `keep`/`remove` rows do not invalidate otherwise complete savings.

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

Pillar J also groups `data-request` activity by a closed Grafana `source` surface enum; it
measures data requests, not page visits, and the `scenes` bucket is not split per app.

Pillar J publishes per-stack query mix as point-in-time S3 detail with no new metric series. It counts
`data-request` events by non-empty datasource type and panel plugin ID, retaining the top 20 values,
one remainder row and the distinct-value count per dimension. Datasource type is a backend inference,
not Grafana app identity. A failed optional query withholds this view while preserving the older core
insights result. Live dev observations on 2026-09-23 found datasource types on active stacks but no
non-empty `panelPluginId`; the panel dimension remains an evidence gap.

Coverage also presents a producing-signal view from documented usage metrics: a 24-hour peak of
Metrics active series and Traces bytes received per second. A missing series is unknown, a returned
zero is measured zero, and a positive value means backend production during the window. None proves
a human opened a Grafana UI.

Usage events and inventory answer different questions. Pillar J reports public dashboards observed in
use; the Risk dashboard enumerates configured public dashboards whether or not anybody opened them. The
generic build presents both and leaves the policy target to the deploying organisation.

Every published view must have a rendered disposition and every declared metric must be rendered
or alerted, with explicit reasons for exemptions. [View reference](docs/views.md) explains the
publication families and their user meaning. Optional product tables are omitted only for genuinely
missing views; retained older objects remain readable with advancing age. Access, transport and parse
errors are explicit, not silently treated as missing. Table
schemas cover legitimately empty finding views without turning a not-yet-published view into a silent
blank panel.

## 9. Security and privacy

Deployment identifiers have no defaults. Build-time Grafana credentials are separate from runtime
credentials and should be short-lived. New alert rules publish paused and unrouted; ordinary publication
preserves existing rules' pause state and routing. Activation requires an explicit receiver so rules
cannot inherit an unrelated production notification policy.

Identities may be stored in clear only when the deploying organisation has approved that policy and
enforces minimization, access control, encryption and retention for the receiving S3/Loki stores. The
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

Still unresolved: Synthetic Monitoring execution/result inventory and Adaptive Profiles. Optional
Synthetic check/probe configuration counts are implemented, but deployed-reader proof is separate.
Library/playlist visibility controls remain parked and k6 has no admitted collector route. Adaptive Traces
config availability, policy-type counts and pending recommendation counts are collected through the
existing stack reader without permission expansion. Config availability is not enablement, and these
counts cannot measure achieved savings; those remain live `grafanacloud-usage` panels.

## Daily bounded label privacy risk

T2 discovers the estate every run and reads signal label names then a deterministic bounded
subset of values. Risk-context keys take precedence, then scope/key lexical order. Default
bounds: 64 keys per signal/stack, 256 distinct returned values per selected key, 64 retained
full matches per stack/key/class, 2 MiB per response, and 2 MiB aggregate retained JSON-value
bytes per stack. Keys longer than 512 characters and values longer than 8192 characters are
unexamined and explicitly partial, not shortened. Bounds are source tunables, not estate config.
The sample runs immediately after inventory discovery, before other daily gatherers, and reserves
at most a quarter of the tier's remaining budget capped at 15 minutes. Up to eight concurrent
stack workers make sequential requests; each request has a 10-second timeout clamped to the remaining
sample budget, bounded chunk-reading checks, and no retry. `collector.netbound` fences caller waits
including DNS and complete reads. It does not terminate surviving reads: a timed-out operation retains
one of the fixed 32 daemon worker/admission slots until completion, and may retain credentials and
transient bytes in memory. Exhaustion times out new admission rather than creating replacement workers.
The sample is not an exhaustive enumeration or a hard process-termination guarantee.

The separate label-source transport reads at most the byte cap plus one sentinel byte and
refuses redirects. GET reads use the unchanged GET-only client; only the inventory-host native
Pyroscope LabelNames/LabelValues POST exception is added. Errors contain no source body or
exception text. Classification is generic and versioned; confidence expresses format/key
context, never confirmed personal data or a valid secret. No remediation is proposed or performed.

`risk_label_hygiene` is an S3-only finding table with full raw classified matches, separate
confidence/evidence, sampled/matched/retained counts, window and pattern version.
`risk_label_hygiene_coverage` shows per-signal measured/scannable stack denominators, limits
and unavailable/partial coverage. No backend completeness guarantee is proven, so successful
reads remain partial and a no-match sample is not clean. This does not inspect log bodies,
structured metadata, trace/profile contents or the full retention history. Ordinary values and
decoded JWT claims do not persist. The private daily scan input may retain the same bounded
classified matches for cross-tier hydration under existing access/encryption controls.
Current `scans/` objects and the reserved full-key prefix `views/risk_label_hygiene.json`
become eligible for expiry after `scan_retention_days` (positive whole days, default 90)
since last publication. Hydrated republication resets that age; withholding on stale inputs
leaves the last copy subject to expiry. Other last-good views and reader IAM are unchanged.
In the versioned bucket, expiry makes the version noncurrent, then the existing seven-day
noncurrent expiry applies, with asynchronous AWS processing. This is not strict erasure
90 days after observation. For adopted buckets (`create_bucket = false`), the owner must
configure equivalent targeted retention in its existing lifecycle policy before raw publication;
no competing lifecycle resource is created. Deployment validation must prove effective
lifecycle, versioning, encryption and reader access, including a fresh bucket-policy witness denying
non-TLS access, before use. Missing controls block raw publication; these prerequisites do not authorize
adding a bucket policy to an adopted bucket. Diagnostic scan export excludes this input. Generic Loki findings explicitly deny these
views, and no business series are added. One input enum adds at most eight existing input-health
series across four tiers, with no stack multiplier.
