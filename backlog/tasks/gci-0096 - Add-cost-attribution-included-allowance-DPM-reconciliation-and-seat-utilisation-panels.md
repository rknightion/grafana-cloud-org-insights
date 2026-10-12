---
id: GCI-0096
title: >-
  Add cost attribution, included-allowance, DPM reconciliation and seat
  utilisation panels
status: Parked
assignee:
  - '@loop24-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-12 22:24'
labels:
  - dashboards
  - cost
  - loop13
dependencies: []
priority: medium
type: enhancement
ordinal: 112000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment gaps 2, 3, 4 and 7: *_attributed_* families (attribution label values never become our labels), org usage against _included_* allowances (zero included is valid), vendor grafanacloud_instance_billable_usage / org_metrics_billable_series / included_dpm_per_series against the rate-card DPM model, and billable against active users for Grafana, IRM and plugins. Panels only over grafanacloud-usage.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Panels exist for each of the four families with metric names from the roster and descriptions stating window/unit as unverified where doc-0006 says so
- [x] #2 The DPM reconciliation shows modelled against vendor figures side by side and never substitutes one for the other
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
Root static seam map shows the showback edge serializes a shared writer, not a data/code consumer. Showback stopped and parked; remove that engineering edge, preserve original AC and ceilings, process one dashboard writer. Add raw vendor families with explicit unverified unit/window and no invented conversion; keep modeled and vendor figures distinct. Gate/CR then independent review and exact integration proof.

Loop24 resume packet: preserve accepted panels. Billing-only candidate in bin/dashboards.py _cost_context: grafanacloud_org_grafana_plugin_users, no sum/rate/increase/x30/currency or active-seat ratio; explicit latest applicable rated-month/proration/subscription quantity, calendar-month consumer range with lastNotNull and observation freshness. Included allowance remains separate. Before implementation obtain positive deployed source witness and authoritative exact plugin-active metric/expression with matching subscription eligibility, trial exclusion, period/proration, parent-child scope and cross-stack deduplication. Generic rolling30d active logins are not that cohort. Missing comparison remains unavailable.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop13: 2 change-and-verify cycles (initial implementation plus final source-name qualification narrowing), 0 review-repair rounds, CR connection outage charged0. Safe partial candidatea92258eb8157736a85865740179c4902a594c247 accepted/landed with independent exact archive/artifact/promtool PASS, final completed CodeRabbit0findings. Composed just check2192passed2skipped13364subtests; CI37465449908 exactSHA required leaves success. AC2/3 satisfied; fullAC1 remains unchecked because plugin billable-vs-active exact metric/unit/window/cohort unavailable. Explicit unavailable plugin comparison is not completion. Resume source witness; preserve landed panels and ceilings. Customer names/readback/browser/performance unverified.

Loop24 research accepted, no implementation attempt or AC completion. Pinned vendor producer and public user-pricing evidence establish billing-side current-month rated quantity, not matched plugin-active people. Root robk HTTP200/no-warning 35d roster and count_over_time reads plus calendar-month range returned no plugin samples; Loki reload control was present. Zero seats not inferred. Remaining blocker: positive deployed plugin source and matched active/cohort contract. Attempts: 0 implementation this loop; retain prior2. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/seats/lane.md and /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/root/usage-probe.json.
<!-- SECTION:NOTES:END -->
