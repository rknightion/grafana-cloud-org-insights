---
id: GCI-0056
title: >-
  Make actionlint green: runner label ubuntu-26.04 is unknown to the pinned
  linter
status: To Do
assignee: []
created_date: '2026-10-01 07:03'
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
- [ ] #1 actionlint passes at an exact landed SHA with no runner-label error
- [ ] #2 No workflow runner label, permission or job is weakened or removed to obtain the pass
- [ ] #3 The chosen fix (reusable pin bump or repository config) is named with the reason the other was not used
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
