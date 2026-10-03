---
id: GCI-0088
title: Keep missing daily user counts out of dormant-stack findings
status: Done
assignee:
  - '@loop11-root'
created_date: '2026-10-02 22:02'
updated_date: '2026-10-03 12:13'
labels:
  - data-quality
dependencies: []
references:
  - collector/pillars/usage.py
priority: medium
type: bug
ordinal: 98000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Independent loop10 documentation review reproduced usage.build with currentActiveUsers5 and dailyUserCnt null: usage_dormant_stacks reports daily0/stickiness0. Inventory missing/null daily counts are coerced to0, so unknown can look dormant. Source behavior predates this docs change. Correct current documentation to disclose it; this source follow-up is outside the frozen implementation envelope and NOT admitted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Real usage.build reproduction for missing/null daily counts is observed failing before correction; unavailable daily data is not emitted as measured dormancy.
- [x] #2 Known positive daily activity and known zero daily activity keep their intended behavior; missing active-user counts remain distinct.
- [x] #3 No unrelated scoring/metric/provenance changes; public-boundary proof, final just check, complete review and exact-SHA CI identify the delivered correction.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop11 frozen scope: missing/null dailyUserCnt excluded from measured dormancy and absent stickiness; preserve known zero/positive and distinct missing active counts. Lane a1 red-first real usage boundary, final-rebase gate, CodeRabbit, exact-SHA CI, focused review. No fixture/table regeneration.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Loop11a1 accepted00a1cd927bcdabb7465644100b53479fff8bd62c CI37121686915success; missing/null daily notmeasured dormancy/stickiness, knownzero/positive preserved, missingactivedistinct. Originalrealusagebuildredfirst11:39:03Z; finalrebasejustcheck1945pass2skips8635subtests, CRinitial2majors/finalcomplete0; denominatorfix made, daily_total finding explicitlyexcluded andtrackedseparately. FocusedindependentreviewPASS24tests plusparentreplay/mixedestatecontrols. Root inspected rawchildsession to repair reviewer missingartifact attestationgap. Preexistingpartial-active estate denominator residual likewiseoutofscope; no liveestateclaim. Impla1, infra0; landing-only nativecontinuation samea1.
<!-- SECTION:FINAL_SUMMARY:END -->
