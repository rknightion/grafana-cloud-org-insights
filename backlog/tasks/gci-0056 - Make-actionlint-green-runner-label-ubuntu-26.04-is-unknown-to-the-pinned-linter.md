---
id: GCI-0056
title: >-
  Make actionlint green: runner label ubuntu-26.04 is unknown to the pinned
  linter
status: Done
assignee:
  - '@loop5-root'
created_date: '2026-10-01 07:03'
updated_date: '2026-10-01 07:48'
labels:
  - ci
dependencies: []
priority: medium
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Every actionlint run on main has been red since before loop4 and every loop report has disclosed it as a known failure (for example run 36823426186 at 542a871). The cause is not the harden-runner timeout the loop4 packets assumed: the shared reusable actionlint workflow at rknightion/.github f32275a reports runner-label errors because its actionlint does not know the ubuntu-26.04 label used by ci.yml (lines 19, 50, 81, 97), publish.yml (28) and release-please.yml (17). A permanently red check trains every reader to ignore it. Prefer a reusable release whose actionlint knows the label; otherwise declare the label in this repository's actionlint config. Do not change runner labels to dodge the check, and do not edit the shared reusable repository from this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 actionlint passes at an exact landed SHA with no runner-label error
- [x] #2 No workflow runner label, permission or job is weakened or removed to obtain the pass
- [x] #3 The chosen fix (reusable pin bump or repository config) is named with the reason the other was not used
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Admitted under owner loop5 goal, 2026-10-01. Root owns tracker writes; isolated lanes own only named seams. Acceptance pending terminal evidence.

loop5 L-alint-a1 landing-ready candidate71a16c17f3dd219cd85940cfa7677cd800642a87 accepted for integration. Only .github/actionlint.yaml added; root reviewed diff and patch SHA25649dde7061764dd52ab5db3d0d376462c58d0bd7b05acea23a2d8038305b05cc3. Shared latestv1.25.3/f32275a still pins actionlint1.7.12; no later fixed reusable, so explicit repo label declaration chosen, no workflow changes. Local1.7.7 reproduced six unknown-label errors then passed, just check1659passed/2existing skips/7971subtests, CRconfiguration exemption. AC1 pending exact landed hosted actionlint. Implementation count1, review-repair0, infra retries0; held for L-0055 main mutex.

loop5 exact landed actionlint36832334419 completed success atf767fad63ad92d9ca63ddea6777765125770e287; hosted runner-label proof now met. CI36832333607 still watched before final task close/next push.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
loop5 repository actionlint label declaration landedf767fad63ad92d9ca63ddea6777765125770e287, exact CI36832333607 and actionlint36832334419 successful. Latest shared releasev1.25.3 has no native runner-label support, so explicit config chosen without changing any hosted runner, job or permission. One implementation attempt, zero review repairs/retries; CRconfiguration exemption.
<!-- SECTION:FINAL_SUMMARY:END -->
