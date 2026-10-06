---
id: GCI-0099
title: Harden dashboard coverage gates against their blind spots
status: In Progress
assignee:
  - '@loop13-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-06 18:21'
labels:
  - dashboards
  - tests
  - loop13
dependencies: []
priority: medium
type: enhancement
ordinal: 115000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Existing gates (tests/test_dashboards.py:2354-2470) prove every view, published field and declared metric is rendered somewhere. Blind spots: fields of views empty in the fixture are unobserved, a metric counts as rendered if its name appears in any query even when only one enum value is shown, per-tab coverage is not checked, and live hydration states are unobserved. Add stronger gates in a new test file, with an explicit reasoned exemption ledger for current gaps.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 New gates in tests/test_dashboard_coverage.py fail on a seeded unrendered field, an unrendered enum value and an empty-fixture view, then pass on the real tree
- [ ] #2 Every current gap is an exemption with a reason and the task that closes it; no existing test is weakened
- [ ] #3 just check green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Last dashboard-wave task on final assembled tree: add new coverage gate file only, cross assembled public artifacts/empty-fixture schemas/enums/tabs/hydration state; seeded meaningful field/enum/empty-view failures before realtreepass. Explicit reason-and-owning-task exemption ledger, no weakening existing tests or incidental substring/magiccount proofs. Finalgoal gate/CR and independentreview.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop13 worker2gatecycles exposed exact19selector debts and40incomplete domains; root authorised AC2 exact reasoned ledger with GCI-0120 (enum rendering/retirement), GCI-0121 (independent runtime vocabularies), GCI-0122 (per-tab ownership/granularity). Root limitedrescue3 fills declarative ownership, exactsets require stale/newdebts resolved; all3unsuppressed seeds still fail with ledger enabled,9newtest methods pass focused. Exemptions are not coverage, no prod/oldertest changes; finalgate/review still pending.
<!-- SECTION:NOTES:END -->
