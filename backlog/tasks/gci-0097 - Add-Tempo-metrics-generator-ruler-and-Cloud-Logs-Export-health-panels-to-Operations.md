---
id: GCI-0097
title: >-
  Add Tempo metrics-generator, ruler and Cloud Logs Export health panels to
  Operations
status: Parked
assignee:
  - '@loop24-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-12 22:24'
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

Loop24 resume packet: preserve all accepted Operations raw panels. Public export docs establish grafanacloud_logs_instance_cloud_logs_export_status{status="succeeded"} in grafanacloud-usage and recommended24h observation absence. Additive panel only after positive deployed schema witness: status observations vs succeeded observations, title source-series observed, no jobs/events/failed-export claim, no or-vector-zero. Seven-day initial export lag prevents subday failure inference. Do not calculate timestamp age until exact epoch/unit contract, or rate exported bytes without TYPE/reset contract. Loki upstream counters are not Cloud aliases: obtain exact grafanacloud_logs_instance_ iteration/evaluation/failure producer aliases on approved surface; never replace with Mimir cohort or broaden datasource query permissions.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop13: 2 change/verify cycles (worker1 implementation, root1 four-line visible-legend review correction), 1 review-repair round; original CodeRabbit complete0findings and trivial wiring delta not rerun. Safe partial raw-observation panels accepted/landed9a002e8368300310454634555323ed37c612eac2; independent original and exact legend deltaPASS, real17expressions/34cases PromQL source-value and absence proof. Final+composed just check2195passed2skipped13380subtests; exactSHA CI37470747210 required leaves success. AC2/3 satisfied; AC1 remains missing exact Loki iteration/evaluation/failure names/contracts. Unavailable notice is not full completion. Historical export-name customer readback, vendor units/enums and file-sync meaning remain unverified. Resume exact missing Loki witness; preserve landed safe slice/ceilings.

Loop24 research accepted, AC1 remains partial. Root robk HTTP200/no-warning35d roster had only Loki reload family; count control50330 observations, no Loki iteration/evaluation/failure aliases. Export status35d and succeeded24h returned no samples: bounded datasource/window absence, not no jobs or global metric absence. Remaining blockers exact Cloud aliases/contracts and positive current export schema. Attempts: 0 implementation this loop; prior2 cycles/1 review-repair retained. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/health-metrics/lane.md and /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/root/usage-probe.json.
<!-- SECTION:NOTES:END -->
