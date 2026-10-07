---
id: GCI-0120
title: Render or explicitly retire uncovered metric enum combinations
status: In Progress
assignee: []
created_date: '2026-10-06 17:49'
updated_date: '2026-10-07 15:09'
labels:
  - dashboards
  - coverage-debt
  - owner-decision
dependencies: []
priority: medium
type: bug
ordinal: 155000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The final dashboard coverage gate exposed 19 exact selector debts: seven value-benchmark kinds (active_series, alert_rules, dashboards_per_user, datasource_types, maturity_score, series_per_billed_user, signals_in_use); coverage_metric_names kind matched; both carry families at t2/t3/t4; and five scan families at t4 (completed timestamp, coverage ratio, scannable, scanned, total). No blanket exemption or alert-as-panel claim is approved. This future task closes the exact debts by meaningful display or evidence-backed retirement/reserve disposition, not new series.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every enumerated debt has an independently witnessed actual-emission and rendering/alert-only/reserve disposition; emitted combinations are explicitly rendered with intended population granularity or receive an owner-approved omission.
- [ ] #2 All seeded unrendered field, role enum and empty-fixture defects still fail the hardened gate; exact ledger entries retire only when real rendering or approved contract evidence closes them; no older test is weakened.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop15: consume M-0120 actual-emission witness; render debts meaningfully or provide source-backed retirement/reserve contract evidence; return owner-only omission choices, retain seeded-defect failures; hold landing until R-rel3 readback.

Design reviewed independently: ten reserves require final-output/transitive emission proof including t2/t3 composition and shared processing, not callsite AST alone; preserve reserve-violation and older negative seeds. Wording must disclose truthy datasource counts, producer zero defaults and upper-middle quantile; Mimir completion timestamp is not all-sink success.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Also own the exact superseded never-emitted gcinsight_risk_public_dashboards_total catalogue declaration: prior GCI-0085 (published-data coverage remediation) explains history but does not claim this declaration rendered. Resolve catalogue retirement with source evidence, not a synthetic panel.
<!-- SECTION:NOTES:END -->
