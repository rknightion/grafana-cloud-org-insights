---
id: GCI-0041
title: Decide read-only product scopes for feature inventory
status: In Progress
assignee:
  - '@loop9-root'
created_date: '2026-09-23 18:35'
updated_date: '2026-10-02 09:13'
labels:
  - feature-usage
  - scope-decision
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: high
type: task
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0032 found product object APIs beyond the existing basic-role-None stack reader. This is a scope decision, not authorization to change the role. The SLO GET returned 403 on nine sampled stacks. Live role metadata showed SLO reader actions grafana-slo-app.orgpreferences:read and grafana-slo-app.slo:read plus plugins.app:access scoped to plugins:id:grafana-slo-app; Synthetic Monitoring checks reader actions grafana-synthetic-monitoring-app:read and grafana-synthetic-monitoring-app.checks:read plus plugin access scoped to plugins:id:grafana-synthetic-monitoring-app; IRM integrations reader action grafana-irm-app.integrations:read plus plugin access scoped to plugins:id:grafana-irm-app; and k6 reader action k6-app.settings:read plus plugin access scoped to plugins:id:k6-app. Further product roles for probes, alert groups, schedules, app observability, knowledge graph, frontend, Kubernetes, cloud provider, database, PDC, ML, reporting, library panels and playlists need action/scope and safe-output verification. Each grant may expose customer configuration, identities, URLs or scripts. Datasource query scope remains pinned to the two exact Grafana-provisioned uids; decrypted secrets and write actions remain refused. Decide which products merit a narrow read grant before any provisioner change. Proposed new emitted series: 0 for the inventory views; access breadth, not cardinality, is the cost.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Record an explicit approve, defer or reject decision per product read family, including exact action and scope pairs
- [x] #2 For each approved family, identify data minimization, access control, encryption and retention for identity-bearing detail
- [x] #3 Keep basic role None, datasource query uid pins, and refused secret/write actions unchanged
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop3 D1a: discover live staff product routes, exact minimal pairs, minimization and per-family verdicts. Root freezes evidence-backed table before I-scopes implementation and independent security review; customer grants bounded by goal D7.

Loop9: record owner table and narrow S-SM exception in AGENTS and LOOP, gate and hosted CI, then file unbuilt family packets as To Do.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Parked for Rob decision at Wave 1 report: candidate product read scopes and their data/risk are in doc-0006 and CAPABILITIES.md. No role or access policy changed in this wave.

Wave 2 decision: dev-only default-off approval for SLO and Synthetic Monitoring reads. SLO pairs: grafana-slo-app.orgpreferences:read and grafana-slo-app.slo:read with empty scope, plugins.app:access scoped to plugins:id:grafana-slo-app. Synthetic pairs: grafana-synthetic-monitoring-app:read and grafana-synthetic-monitoring-app.checks:read with empty scope, plugins.app:access scoped to plugins:id:grafana-synthetic-monitoring-app. k6, IRM and other families deferred. Customer grant needs a separate decision. Code at edc7abb preserves basic role None, datasource query uid pins and refused secret/write actions; L6 security PASS. Minimise future SLO output to counts, state and bounded source; Synthetic output to counts by bounded type and public/private probe class, dropping identities, URLs, scripts, headers and expressions at collection. Keep raw identity-bearing payloads out of logs, metrics, permanent views and scan envelopes; any future approved private S3 detail needs encryption, task-role access and retention. Dev grant and route proof pending R4.

Live R4: manual provisioner task dc4142d1fc5f4e77a2294877b156987e exited 1 after its immediate post-repair verification reported two stacks stale. A fresh root readback of all five roles matched exactly the six approved added pairs, with no removals, unchanged datasource query pins, basic role None, identical service account/token IDs and SSM versions, and reader GET 200. SLO list GET returned 200 on all five dev stacks. Synthetic Monitoring check-list GET returned 403 on the three stacks with its datasource; two stacks had no Synthetic datasource. This is an access-route gap under the approved D8 boundary, not authority to widen datasource query or mint another token. Dev rolled back after a separate T2 projection failure; the six approved read-only role pairs remain present.

loop3 admitted 2026-09-30 under owner goal: root owns tracker; bounded lanes own implementation/discovery, evidence pending. No acceptance claimed yet.

loop3 IRM decision: DEFER all new IRM grants. Exact P(IRM)+integrations:read counters proof succeeds but permission breadth fails approval prerequisite; static archived source and installed frontend imply routing credential exposure, hosted equivalence unproven. Exact P(IRM)+alert-groups:read remains403. Schedules/Incident content lists remain unapproved; no readRPC added. BasicNone/query pins/refused secret/write actions unchanged; no current reader was modified. SLO/Adaptive existing approved route boundaries remain the only implemented feature-inventory reads; remaining D1a families retain individual deferred verdicts.

Loop3 final scoped decision table: retain existing approved SLO/Synthetic pairs without widening query pins; SLO/Adaptive operational read seams implemented, Synthetic datasource-query denial unresolved. No additional families granted. IRM counter access proved but credential breadth blocked; ML/Faro/IRM secret/content lists and Incident/schedules not approved. Remaining D1a families retain explicit defer packets. Five live dev None readers/SA-role-token IDs/SSM versions/pairs identical pre/post provisioner; no new customer grant. Scope research remains partial rather than claiming every candidate pair minimally proven.

loop4 M-ac map: AC1 and AC2 remain partial (full per-family decision/pair table and effective privacy safeguards not independently evidenced); AC3 pre/post five-reader None/query-pin equality evidenced historically. No widening or blanket approval.

loop4 freshpre/post5readerfullaction-scopepairs,IDs/tokenIDs/SSMversionsunchanged, basicNone/queryUIDpinsretained. MetadataUID/folderssharedwithme extras arealreadyexistingandcoveredbyapprovedmetadatareadwildcards, notquerywidening. AC1/2completefamilytable/privacydecisionremainpartial, no newfamilyapproved.

Owner decision table (Rob, 2026-10-02, loop9 preparation, from loop3 D1a evidence; P(x) = plugins.app:access scoped plugins:id:x; other scopes empty). Reader stays basic role None; write actions and write-bundling product roles are never assigned; every collector keeps counts/bounded enums only and never persists or logs raw bodies.
APPROVED:
- SLO: grafana-slo-app.orgpreferences:read, grafana-slo-app.slo:read, P(grafana-slo-app). Counts only (existing, GCI-0036).
- Adaptive Traces: config:read, plugin:access, policies:read, recommendations:read, P(grafana-adaptivetraces-app). Counts only (existing, GCI-0020).
- Adaptive Metrics and Adaptive Logs: existing pairs retained.
- Synthetic Monitoring checks and probes (GCI-0037): grafana-synthetic-monitoring-app:read, .checks:read, .probes:read, P(grafana-synthetic-monitoring-app), plus datasources:query scoped to the exact per-stack discovered Synthetic Monitoring datasource uid (an owner-approved exception to the usage-datasource query pin; never a wildcard). Counts by bounded check type, enabled count, public/private probe class; drop targets, scripts, headers, labels at parse.
- IRM integration counters (GCI-0039): grafana-irm-app.integrations:read, P(grafana-irm-app); collector calls only alert_receive_channels/counters and publishes len(map). Accepted residual risk: the same pair also reaches secret-bearing integration list/retrieve routes the collector never calls.
- IRM alert-group stats (GCI-0039): grafana-irm-app.alert-groups:read, P(grafana-irm-app); route alertgroups/stats; exact-pair reader 403 must be diagnosed before build.
- IRM Incident counts (GCI-0039): one exact-path read-RPC POST exception, approved in principle; exact read action unverified; counts and bounded status/severity/isDrill only.
- Frontend Observability apps (Faro): grafana-kowalski-app.apps:read, P(grafana-kowalski-app) (viewer pairs to verify). appKey and collect endpoints are public ingest values per owner. Counts by bounded app type.
- Machine Learning jobs: grafana-ml-app.forecasting:read, P(grafana-ml-app) (viewer pairs to verify). Accepted residual risk: each job item carries grafanaApiKey; dropped at parse, never logged or persisted. Counts only.
- Cloud provider: grafana-csp-app:read, P(grafana-csp-app); count by provider enum; he-api write isolation unproven, so GET only on the exact accounts route.
- PDC: grafana-pdc-app.private-networks:read, P(grafana-pdc-app) (pairs to verify); count of stack-realm private-network policies, never tokens.
- Reports, library panels, playlists: counts only, once exact pairs are verified (reports:read; library.panels:read folder scope; playlist action unobserved).
- k6: k6-app.settings:read, P(k6-app) approved; blocked on a service-account-supported project/run route (GCI-0038 stays parked).
REJECTED: IRM integrations list, IRM alert-group list, IRM schedules (identity-bearing; no count route).
DEFERRED (low value): Knowledge Graph status, Application Observability instance, Database Observability instance, Kubernetes connections, Adaptive Profiles.
Customer grants: each needs its own rollout decision; none granted now. Full evidence table: private loop9 preparation record.

AC3 amended by the same owner decision: basic role None and refused secret/write actions stay unchanged; the datasource query pin gains exactly one approved exception, datasources:query on each stack's discovered Synthetic Monitoring datasource uid, to be recorded in AGENTS.md before any code relies on it.
<!-- SECTION:NOTES:END -->
