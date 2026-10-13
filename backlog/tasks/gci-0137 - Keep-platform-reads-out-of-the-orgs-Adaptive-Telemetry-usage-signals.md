---
id: GCI-0137
title: Keep platform reads out of the org's Adaptive Telemetry usage signals
status: In Progress
assignee: []
created_date: '2026-10-13 17:19'
updated_date: '2026-10-13 19:37'
labels:
  - adaptive
  - cost
dependencies: []
references:
  - collector/sources/signal_inventory.py
  - collector/sources/label_inventory.py
  - collector/sources/label_risk.py
  - collector/sources/dataplane.py
  - collector/sources/loki_volume.py
  - collector/sources/capability_adoption.py
  - collector/sources/usage_insights.py
  - >-
    https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-metrics/manage-recommendations/understand-recommended-rules/
  - 'https://github.com/grafana/mimir/pull/14474'
priority: high
type: task
ordinal: 171000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Platform reads must avoid altering Adaptive Telemetry recommendations. A bounded customer incident investigation found only metadata reads by this collector; causality is unproved. Private incident identities and token metadata remain outside this public tracker.

Metrics: the documented empty __ignore_usage__="" matcher preserves results and excludes marked PromQL queries from Adaptive Metrics usage. Metadata label, series and cardinality tracking/suppression require an exact contract.

Logs: research recommendation tracking and any supported read opt-out. Traces: establish the current product model and record limitations instead of inventing a workaround.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every PromQL selector the collectors send to an org stack carries __ignore_usage__="", with a test that fails if a new data-plane metrics read omits it
- [ ] #2 The metadata endpoints in use (label values with match[], series, cardinality API) are classified as counted or not counted toward Adaptive Metrics usage, with the evidence cited, and covered where the matcher is accepted
- [ ] #3 Adaptive Logs: the docs research outcome is recorded; either an opt-out exists and every Loki read uses it, or none exists and the affected reads are listed
- [ ] #4 Adaptive Traces: whether any opt-out exists is recorded; if none, the Tempo reads that could register usage are listed as a known gap
- [ ] #5 CAPABILITIES.md states what the platform does and does not do to an org's Adaptive Telemetry usage signals
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Construct marked PromQL literals with fail-first HTTP-boundary proof; independently research metadata/Logs/Traces contracts and document unknowns. Run independent review, CodeRabbit and just check, then exact-source CI/release. Upgrade dev/customer immutable consumer pairs preserving configuration, review/apply saved targeted plans and verify live readback/no-change. Freshly pulled donor task duplicates provenance ID; backlog doctor safely renamed it to GCI-0137. Interim sanitized GCI-0136 is archived through CLI, preserving its evidence.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Leads from ~/repos/adaptive-telemetry-pm/knowledge/adaptive-logs/README.md: Adaptive Logs counts queries per pattern by query hash over 15 days (sampled), and already excludes broad bytes_over_time/bytes_rate queries from the recommendation algorithm (grafana/log-template-service pkg/recommendations/recommendations.go). No ignore-usage opt-out is documented there; check that source for one before concluding none exists. Per-metric Adaptive Metrics usage detail, including dashboard_uids, is at GET <prom url>/adaptive-metrics/api/v2/segments/default/metrics/<metric> (basic auth <prom instance id>:<CAP>); use it to verify the matcher works by watching usages_in_queries on a test metric.

All 27 expressions differ only by the empty ignore matcher. Fail-first boundary guard then 26 focused tests/351subtests pass; full final gate exit0,2747tests/27920subtests/2skips,37Tofu. Independent review PASS, CodeRabbitcomplete0/allfourfiles. Live marked staff query exact200/vector/fourpositive rows. Metadata usage tracking unknown; Logs opt-out unestablished; current official Traces model does not use query usage. Source hashes unchanged through full gate. Two donor commits newly fetched AFTER history-ref snapshot contain private identifiers; narrow exact-commit history check proves a release blocker. Current task sanitized; no source push or live rollout until published-history correction is authorized and verified.

Final integrated source candidate includes all27markedPromQL expressions plus default-off observer. Final semantic checks2783tests/27921subtests/2skips/41Tofupass, formatting/lint clean, CodeRabbitcomplete0. Root history repair revision2 prepared and verified: only incident-bearing task text/duplicateID differ; original research notes and all non-task bytes preserved. Await explicit atomicforcewithlease approval on originmain and releaseplease branch before publishing source/release/consumer rollouts. No ECRpush/apply or customer mutation occurred. Fresh existing ECR policy witness isMUTABLE for both consumers; publisher now uses unique128bitnonce tags and immutable verified runtime digests without changing ECR policy. Metadata/Logs tracking ACs remain unproven, never treated as absent.
<!-- SECTION:NOTES:END -->
