---
id: GCI-0097
title: >-
  Add Tempo metrics-generator, ruler and Cloud Logs Export health panels to
  Operations
status: Parked
assignee:
  - '@loop13-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-06 13:33'
labels:
  - dashboards
  - operations
  - loop13
dependencies: []
priority: medium
type: enhancement
ordinal: 113000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment gaps 5, 6 and 14: grafanacloud_traces_instance_metrics_generator_* saturation and drops, Mimir/Loki ruler missed iterations, rule evaluation and reload failures, Alertmanager config reload, and grafanacloud_logs_instance_cloud_logs_export_* status. Percent-versus-ratio trap applies (docs/traps.md).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Operations gains per-stack panels for each family with metric names from the roster
- [x] #2 Units are stated as verified or unverified per doc-0006; no ratio is rendered as a percentage without evidence
- [x] #3 just check green; zero new metric
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Root static seam mapping: Operations health consumes no missing cost/plugin/showback code or semantic contract. Writer-order dependency removed after cost-context stopped and composed gate completed. Preserve original AC and attempt history; build roster-proven health families with verified/unverified units, no unsupported percent scaling. Local real artifacts/meaningful PromQL proof, final gate/CR and independent review before root integration.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop13: 2 change/verify cycles (worker1 implementation, root1 four-line visible-legend review correction), 1 review-repair round; original CodeRabbit complete0findings and trivial wiring delta not rerun. Safe partial raw-observation panels accepted/landed9a002e8368300310454634555323ed37c612eac2; independent original and exact legend deltaPASS, real17expressions/34cases PromQL source-value and absence proof. Final+composed just check2195passed2skipped13380subtests; exactSHA CI37470747210 required leaves success. AC2/3 satisfied; AC1 remains missing exact Loki iteration/evaluation/failure names/contracts. Unavailable notice is not full completion. Historical export-name customer readback, vendor units/enums and file-sync meaning remain unverified. Resume exact missing Loki witness; preserve landed safe slice/ceilings.
<!-- SECTION:NOTES:END -->
