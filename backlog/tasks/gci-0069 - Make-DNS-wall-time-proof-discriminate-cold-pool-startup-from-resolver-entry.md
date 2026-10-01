---
id: GCI-0069
title: Make DNS wall-time proof discriminate cold pool startup from resolver entry
status: To Do
assignee: []
created_date: '2026-10-01 14:53'
labels: []
dependencies: []
references:
  - tests/test_netbound.py
  - collector/netbound.py
priority: medium
type: task
ordinal: 79000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 security r2 and root exact gate independently saw unchanged test_netbound resolver tests time out before setting the entered-DNS event. The 0.1s caller budget can be exhausted while the fixed thread pool starts under host contention (observed load180); isolated reruns passed. This is not proof that a blocked DNS read exceeded its caller bound, but it destabilises the required gate and leaves the measured phase ambiguous. Do not relax timeout/assertions or hide a real resource-bound regression.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Offline proofs distinguish pool-start/admission deadline behavior from actually entered blocked DNS with objective phase evidence
- [ ] #2 Blocked resolver and caller wall-time contracts remain enforced without weakened assertions or special-case input behavior
- [ ] #3 The prior entry-race is reproduced under a controlled local process-edge fixture before the correction and no live network is used
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
