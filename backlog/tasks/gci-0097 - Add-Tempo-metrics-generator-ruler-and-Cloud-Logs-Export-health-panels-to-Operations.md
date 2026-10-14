---
id: GCI-0097
title: >-
  Add Tempo metrics-generator, ruler and Cloud Logs Export health panels to
  Operations
status: In Progress
assignee:
  - '@codex'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-14 20:00'
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
- [ ] #1 Operations preserves accepted Tempo/backend observations, includes exact Grafana-managed ruler observations and Cloud Logs Export24h source/succeeded-presence panels; omitted Loki ruler additions are owner-withdrawn.
- [ ] #2 Units remain qualified; no undocumented percent scaling, failed-job counts, sync age or byte rate is inferred.
- [ ] #3 just check green; zero new collector metric; changed Operations dashboard published and read back on dev and customer.
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

Owner 2026-10-14 withdraws missing Loki ruler iteration/evaluation/failure requirement; retain supported ruler health. Authorizes customer Cloud Logs Export positive witness and resulting panel work; do not infer job count or failure from source observations.

Owner scope2026-10-14: missing Loki ruler iteration/evaluation/failure requirement withdrawn; preserve accepted existing observations and add Grafana-managed ruler signals. Fresh customer witness126/129/130 live stacks for exact Grafana-managed failure/evaluation/group metrics, five live stacks with exact Cloud Logs Export succeeded status samples in24h; IDs join fresh316 inventory. Added three raw ruler panels and two24h source-presence tables, never jobs/counts/sync age. Fail-first KeyError proves missing panels; corrected focused3tests/16subtests and assembled layout visibility pass. Source metadata empty, units/rate normalization/epoch remain explicitly unknown. Original AC1 missing Loki remainder is a withdrawal, not a passing witness.
<!-- SECTION:NOTES:END -->
