---
id: GCI-0041
title: Decide read-only product scopes for feature inventory
status: Parked
assignee: []
created_date: '2026-09-23 18:35'
updated_date: '2026-09-24 00:16'
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
- [ ] #1 Record an explicit approve, defer or reject decision per product read family, including exact action and scope pairs
- [ ] #2 For each approved family, identify data minimization, access control, encryption and retention for identity-bearing detail
- [ ] #3 Keep basic role None, datasource query uid pins, and refused secret/write actions unchanged
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Parked for Rob decision at Wave 1 report: candidate product read scopes and their data/risk are in doc-0006 and CAPABILITIES.md. No role or access policy changed in this wave.

Wave 2 decision: dev-only default-off approval for SLO and Synthetic Monitoring reads. SLO pairs: grafana-slo-app.orgpreferences:read and grafana-slo-app.slo:read with empty scope, plugins.app:access scoped to plugins:id:grafana-slo-app. Synthetic pairs: grafana-synthetic-monitoring-app:read and grafana-synthetic-monitoring-app.checks:read with empty scope, plugins.app:access scoped to plugins:id:grafana-synthetic-monitoring-app. k6, IRM and other families deferred. Customer grant needs a separate decision. Code at edc7abb preserves basic role None, datasource query uid pins and refused secret/write actions; L6 security PASS. Minimise future SLO output to counts, state and bounded source; Synthetic output to counts by bounded type and public/private probe class, dropping identities, URLs, scripts, headers and expressions at collection. Keep raw identity-bearing payloads out of logs, metrics, permanent views and scan envelopes; any future approved private S3 detail needs encryption, task-role access and retention. Dev grant and route proof pending R4.

Live R4: manual provisioner task dc4142d1fc5f4e77a2294877b156987e exited 1 after its immediate post-repair verification reported two stacks stale. A fresh root readback of all five roles matched exactly the six approved added pairs, with no removals, unchanged datasource query pins, basic role None, identical service account/token IDs and SSM versions, and reader GET 200. SLO list GET returned 200 on all five dev stacks. Synthetic Monitoring check-list GET returned 403 on the three stacks with its datasource; two stacks had no Synthetic datasource. This is an access-route gap under the approved D8 boundary, not authority to widen datasource query or mint another token. Dev rolled back after a separate T2 projection failure; the six approved read-only role pairs remain present.
<!-- SECTION:NOTES:END -->
