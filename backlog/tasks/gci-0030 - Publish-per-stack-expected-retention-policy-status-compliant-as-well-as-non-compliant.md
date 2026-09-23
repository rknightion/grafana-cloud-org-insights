---
id: GCI-0030
title: >-
  Publish per-stack expected-retention-policy status, compliant as well as
  non-compliant
status: Parked
assignee:
  - '@codex'
created_date: '2026-09-23 08:35'
updated_date: '2026-09-23 23:08'
labels:
  - retention
  - dashboards
dependencies:
  - GCI-0022
priority: high
type: enhancement
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Requested by Rob on 2026-09-23 for a consumer deployment's audit-retention finding. Today the Logs retention tab shows a gap COUNT (gcinsight_risk_retention_policy_gap_stacks) and a 'Configured retention policy gaps' table listing only stacks BELOW policy (view risk_retention_policy_gaps). Nothing lists the stacks that DO satisfy the configured expectation, so a reader cannot see the compliant set or tell compliant from unmeasured.

Add a per-stack status view produced by collector/pillars/retention.py alongside the existing three, one row per stack per configured expectation entry, with a Status column taking exactly three values: compliant, below policy, unreadable. A stack whose Loki dataplane or plugin route failed is unreadable and never compliant or below policy (GCI-0022 AC9 semantics). Add a table panel for it on the Logs retention tab in bin/dashboards.py, beside the existing gap row, and a compliant-count stat so the coverage row reads measured / compliant / below policy / unreadable.

Generic mechanism only: no expectation value, selector or stack identity is hardcoded, and the selector stays a view column, never a metric label (GCI-0022 AC6). An empty expectation list produces no status rows rather than a table of false compliance. Any new metric is declared in budget.py CATALOGUE.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A new view lists every measured stack against each configured expectation entry with Status exactly one of compliant, below policy or unreadable, and its schema is declared in VIEW_SCHEMAS
- [ ] #2 Unreadable stacks are never reported compliant or below policy, and an empty expectation list yields no status rows
- [ ] #3 The Logs retention tab carries the status table and a compliant-count stat beside the existing measured and gap stats, and the generated dashboards match a fresh render
- [ ] #4 No expectation value, selector or stack identity is hardcoded, the selector is never a metric label, and any new metric is in budget.py CATALOGUE
- [ ] #5 Released as a signed auto-RC whose digest a consumer can pin
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement generic status view and aggregate coverage metrics with unreadable kept separate; test the mixed readable/unreadable case, render dashboard, run just check including private identifier pattern, review, then release by exact SHA and signed auto-RC.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 8 parked by owner before commit or push. Local staged implementation and unstaged attempt-4 regression tests remain in checkout. Two new tests currently fail: malformed retention_stream leaks a partial row; dashboard assembly fails when the status view is absent. Resume with fixes for those two cases, targeted tests and full just check, then exact-SHA CI and release. CodeRabbit slice used two passes; do not call those findings resolved without fixes.

Wave 2 exhausted the two authorised attempts without shipping. The recovered patch and the second correction pass are preserved in the isolated L1 worktree and private codex backup; no GCI-0030 code was committed. Focused tests passed (242 passed, 2 skipped), but CodeRabbit found a remaining major accuracy issue: a lower-priority overlapping Loki selector is classified unreadable even when it cannot govern retention. Do not count AC1-5 or release proof as complete. Resume from that exact selector-priority case with a new explicit attempt budget.
<!-- SECTION:NOTES:END -->
