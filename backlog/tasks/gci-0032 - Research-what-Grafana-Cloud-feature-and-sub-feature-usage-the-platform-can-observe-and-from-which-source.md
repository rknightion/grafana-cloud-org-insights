---
id: GCI-0032
title: >-
  Research what Grafana Cloud feature and sub-feature usage the platform can
  observe, and from which source
status: To Do
assignee: []
created_date: '2026-09-23 17:50'
updated_date: '2026-09-23 17:51'
labels:
  - research
  - adoption
  - pillar-j
dependencies: []
references:
  - collector/sources/usage_insights.py
  - collector/sources/capability_adoption.py
  - collector/provision.py
  - collector/technology_registry.py
  - CAPABILITIES.md
  - docs/traps.md
priority: high
type: task
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

Field question (2026-09-23): "Does anyone have a customer who is successfully tracking overall Grafana feature usage? Usage Insights shows dashboards, but what about the other UI experiences?" Other SEs have customers asking for the same thing. Nobody has a good answer today, and this platform already holds most of the credentials that could produce one.

The frozen question for this research: **for each Grafana Cloud product and its main sub-features, what adoption and usage signal can this project obtain, from which source, at what fidelity, with which credential, and at what cost or risk?** The deliverable is an evidence-backed matrix and a ranked set of follow-on implementation tasks. It is not an implementation.

The first concrete strand is already scoped as subtask GCI-0032.01: the `source` field on usage-insights `data-request` events, which splits queries by Grafana surface (dashboard, Explore, alerting, Scenes apps, Assistant). That subtask's upstream contract notes and traps are the model for the rest of this work. In particular, every Scenes-based app plugin appears to report `source="scenes"` rather than its own id, so per-app attribution needs a different signal. Finding that signal is one of the questions here.

## Fidelity ladder (every matrix cell names its level)

1. **Available** - entitled or provisioned on the stack (instance exists, plugin installed).
2. **Configured** - objects exist: N checks, N SLOs, N integrations, N Faro apps, N clusters. A count of config, not of use.
3. **Producing** - the feature is generating or ingesting data: billing or usage metrics above zero, sentinel metrics present in the stack's own Mimir.
4. **Used by people** - humans query or open it: usage-insights events, distinct users, Assistant usage APIs.

"Installed" must never be presented as "used". Most products will only reach levels 1 to 3; say so plainly rather than stretching a level-2 figure into an adoption claim.

## Sources to probe (all of them, for every product)

1. **Grafana.com control plane, org-realm reader** (`collector/sources/gcom.py`): stack inventory and detail fields, installed plugins per stack, `datasourceCnts`, product instance ids and URLs (SM, k6, IRM, profiles, etc.), anything that marks a product as enabled.
2. **`grafanacloud-usage` billing and usage metrics on the write stack** (`collector/sources/capability_adoption.py` already reads ten). Enumerate every `grafanacloud_*` metric name live, for example `group by (__name__) ({__name__=~"grafanacloud_.+"})` over a 24h range. Map each to product and sub-feature, and note whether it carries `stack_id`. Record which are cumulative counters, which are rates and which are billing-period totals, following the windowing rules already in `capability_adoption.py`.
3. **Per-stack usage-insights datasource** (`collector/sources/usage_insights.py`): beyond `source` (GCI-0032.01), check whether `datasourceType`, `panelPluginId`, `panelName` or any other logfmt field identifies a product. Product-specific datasource types include Synthetic Monitoring, Asserts/Knowledge Graph, k6, SLO and Infinity. Is a dashboard owned by a product app, like the SM or K8s dashboards, identifiable from its uid or folder?
4. **Per-stack Grafana API with the existing reader role** (`collector/provision.py`; `CAPABILITIES.md` "Stack-local reader"): what each product's app plugin exposes through `/api/plugins/<id>/resources/...` or its own API that a read-only action could reach. That covers `/api/plugins` list and settings (`enabled`, pinned, `jsonData` present), SLO, Synthetic Monitoring, Knowledge Graph (Asserts), Application Observability, Kubernetes Monitoring, Frontend Observability, IRM (OnCall and Incident), k6, Fleet Management, Cloud Provider, Database Observability, Machine Learning, Drilldown app settings, Investigations, Reporting, Recorded queries, Library panels, Playlists and Git sync / provisioning.
5. **Per-stack data plane, org-realm reader**: inference from telemetry the product writes into the stack itself. For example: SM `sm_check_info` and `probe_*`; Knowledge Graph `asserts:*` recording rules or entity series; App O11y span metrics and `traces_target_info`; Kubernetes Monitoring build-info and `kube_*`; Faro/Frontend series; Beyla; Fleet-managed collector series. The technology registry (`collector/technology_registry.py`, `technology-registry.json`, GCI-0008.03/0015/0031) already does sentinel matching; extend it rather than building a second matcher.
6. **Existing collectors**: Pillar I Assistant, Adaptive Metrics/Logs/Traces, Fleet, alert routing and rules, public dashboards, service accounts. Record what they already answer so the matrix does not propose rebuilding them.

## Products and sub-features in scope (extend as live discovery finds more)

- **Drilldown apps**: Metrics, Logs, Traces, Profiles. Per-app, not just the `scenes` bucket.
- **Application Observability**: services onboarded, service map, span-metrics source (Tempo metrics-generator vs Alloy/Beyla), OTel vs Beyla instrumentation.
- **Knowledge Graph (Asserts)**: entity graph populated, assertions, RCA workbench use, KG-backed SLOs, integrations enabled.
- **Synthetic Monitoring**: checks by type (HTTP, ping, DNS, TCP, traceroute, MultiHTTP, scripted, browser), public vs private probes, check alerts. SPEC.md lists SM result inventory as out of scope until a safe unattended read route exists; this research should establish whether one exists now.
- **k6 / Performance testing**: projects, tests, runs, VUh (already partly read), browser tests, cloud vs local execution.
- **Frontend Observability**: apps, sessions (already partly read), sourcemaps uploaded.
- **Kubernetes Monitoring**: clusters, Helm chart and Alloy versions, cost features.
- **SLO**: SLO count, SLOs with alerting, SLO source (metrics vs KG).
- **IRM**: OnCall integrations, escalation chains, schedules, alert groups (already partly read); Incident declared incidents.
- **Alerting**: Grafana-managed vs datasource-managed rules, recording rules, contact point types. Much of this already exists; place it in the matrix.
- **Assistant and Investigations**: Pillar I already covers much of it; add Assistant-driven querying from `source="grafana-assistant-app"`.
- **Adaptive Telemetry**: Metrics, Logs, Traces, Profiles; rules applied vs recommendations pending.
- **Fleet Management / Alloy**: collectors, pipelines, remote config in use.
- **Cloud Provider Observability** (AWS, Azure, GCP), **Integrations / Connections**, **Database Observability**, **Private Data source Connect**.
- **Machine Learning**: forecasts, outlier detection, Sift.
- **Profiles (Pyroscope)**: continuous profiling in use (GCI-0019 already measures it).
- **Core UI surfaces**: Explore, correlations, notebooks, public dashboards, reporting, snapshots, library panels, playlists, dashboards-as-code / Git sync. The `source` strand covers the query-driven ones.

## Rules that must hold

- **Read-only research.** Use existing credentials and existing scopes. Do not widen `custom:gcinsight.reader`, mint anything, or change any access policy to test a hypothesis. When a route needs a new action or scope, record the exact `(action, scope)` pair, what it would read, whether it touches secrets or production data, and the blast radius. Put it in the matrix as a **decision for Rob**, not a grant. The reader stays basic-role None and query-scoped; `datasources:query` is never widened beyond the two pinned uids.
- The collector HTTP client is GET-only by construction. Record any route that is a POST (Connect-RPC or similar) as such. It needs the same scrutiny the existing Connect-RPC read routes got.
- Every usage-insights query keeps the `instance_id` guard (see `docs/traps.md` and the `usage_insights.py` docstring).
- Probe several stacks of different size and product mix. One stack is an anecdote.
- **Record negative results.** A route that 401s, 403s for a service-account identity by product design (like Assistant `watcher-agents`), returns zero for an SA (like `/api/v2/investigations`) or returns 200 with wrong data is as valuable as a working one. These go into `CAPABILITIES.md` "Known unavailable or rejected routes".
- No customer identifiers, stack slugs, user names or tokens in anything committed. Use anonymised or synthetic examples.
- Cardinality: every proposed metric states its series cost (live stacks x enum size) and why it needs a time series rather than a view, per AGENTS.md.

## Deliverable

1. A backlog doc, "Feature usage observability matrix" (create it with `backlog doc create`, never by hand). Rows are product/sub-feature. Columns: best fidelity level reachable, source, exact route/query/metric, credential and scope (existing or needed), live-verified yes/no plus on how many stacks, per-stack or estate, cardinality cost if emitted, known traps, and a recommendation (build now / build after scope decision / not obtainable / out of scope).
2. Verified routes and negative results added to `CAPABILITIES.md`, and new traps to `docs/traps.md`.
3. One follow-on Backlog task per "build now" row or coherent group, created via the CLI, ranked by value to the field question vs cost. Reference this task and the matrix doc. Group the scope-widening rows into a single decision task for Rob.
4. A short answer to the original field question, written into the matrix doc's summary: what a customer can track about Grafana feature usage today with this platform, what it could track after the follow-ons, and what no available source can see.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Live enumeration of every grafanacloud_* metric on the write stack, each mapped to a product and sub-feature with its windowing semantics
- [ ] #2 Every product and sub-feature listed in the description has a matrix row naming the best reachable fidelity level (available, configured, producing, used by people), source, exact route or query, credential and scope
- [ ] #3 Each row states live-verified or not, and on how many stacks; negative results (401, 403-by-design, 200-with-wrong-data) are recorded in CAPABILITIES.md
- [ ] #4 No reader role, scope or access policy was changed; every route that would need a new (action, scope) pair is listed with what it reads and its risk, grouped into one decision task for Rob
- [ ] #5 Per-app attribution inside the Scenes 'scenes' source bucket is resolved or recorded as not obtainable, with the evidence
- [ ] #6 Matrix exists as a backlog doc and its summary answers the field question: trackable today, trackable after follow-ons, not visible to any available source
- [ ] #7 One follow-on task per build-now row or coherent group, created via the backlog CLI and ranked by value vs cost, each stating proposed series cost
- [ ] #8 No customer identifiers, stack slugs, user names or tokens appear in any committed artifact
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Upstream evidence for the source-field strand (Grafana surface attribution, Scenes 'scenes' bucket, Assistant source value) is archived verbatim in GCI-0032.01's implementation notes. Headline for this research: usage-insights has only dashboard-view and data-request events; data-request.source is request.app; Scenes-based app plugins appear to report 'scenes' unless their scene root implements enrichDataRequest, so per-app attribution (Drilldown, App O11y, K8s, KG) needs another signal. Candidates to test first: datasourceType split within scenes, panelPluginId, installed-plugin inventory from gcom, and product sentinel series in each stack's Mimir via the technology registry.

Existing reader scopes (collector/provision.py READER permissions) at task creation: Assistant, Adaptive Logs/Metrics/Traces and a databases-config plugin via plugins.app:access; serviceaccounts, datasources (read and caching read), folders, dashboards, snapshots, teams, user roles, roles and alert rules/receivers read; datasources:query pinned to grafanacloud-usage-insights (plus grafanacloud-usage on the write stack only). None of SLO, Synthetic Monitoring, Knowledge Graph, App O11y, K8s Monitoring, IRM, k6 or Frontend O11y plugin resources are in scope today.
<!-- SECTION:NOTES:END -->
