---
id: GCI-0060
title: Establish segment-aware Adaptive Metrics savings coverage
status: Parked
assignee:
  - '@loop7-root'
created_date: '2026-10-01 11:45'
updated_date: '2026-10-01 14:53'
labels:
  - adaptive-metrics
  - accuracy
dependencies: []
references:
  - collector/sources/dataplane.py
  - CAPABILITIES.md
priority: medium
type: enhancement
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 reference audit at fb5803a found collector/sources/dataplane.py:293 reads only unsegmented Adaptive Metrics routes. Current docs now disclaim verified segment-aware savings, but an estate with segmentation may have incomplete savings attribution. GCI-0014 (Adaptive Metrics recommendation view) is already Done and does not establish segmented route coverage. No live tenant or scope change is implied by this follow-up.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Current supported segmented and unsegmented API contracts and completeness limits are established with authoritative evidence
- [ ] #2 Savings do not silently present a partial unsegmented result as complete where segmented coverage is required
- [ ] #3 Any implemented route preserves read-only access, bounded labels and live inventory joins and is proved across its public boundary
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop7 frozen packets: bounded implementation or AC1 research; public-boundary proof, offline gate and CodeRabbit before landing, exact landed CI. Root security review/guard landing, research staff GET probe and conditional reserve decision, integrated review, stable release and dev-only rollout proof. Tracker remains root-owned.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop7 AC1 evidence: authoritative Grafana Adaptive Metrics API and segmentation docs establish omitted/empty segment = default only, GET /aggregations/rules/segments discovery and per-segment rules/recommendations. M-seg-a1 inspected 4f652f2305c4e7ff1eb4cf6d4da97ea56d5303b5. Root staff-only GET probe 2026-10-01T13:59:53Z to 13:59:55Z: fresh inventory, seven GET responses all 200, stable empty segment enumeration, 681 default verbose recommendations, grouped rules one entry; shapes/counts only retained. This proves nonsegmented route behavior with existing broad staff CAP, not segmented arithmetic or deployed narrow reader authorisation. Conditional L-seg not admitted: no positive segmented verbose/fallback witness and declared reader lacks segments-read scope. A blanket fail-closed suppression fix could remove savings everywhere under the current reader without demonstrating the desired segmented public contract. AC2/AC3 remain open, no scope expansion or segment creation granted by this research. Evidence is local codex/loop7-evidence/M-seg and R-segprobe; public sources https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-metrics/additional-configuration/adaptive-metrics-rule-segmentation/ and https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-metrics/manage-as-code/adaptive-metrics-api/.

Loop7 committed AC1 accepted; conditional L-seg not admitted and AC2/AC3 explicitly parked. Resume boundary: verified positive segmented recommendation/fallback semantics and authorised discoverability for deployed reader, followed by a frozen owned source-to-consumer packet. This loop does not change collector scopes or fabricate a segment.
<!-- SECTION:NOTES:END -->
