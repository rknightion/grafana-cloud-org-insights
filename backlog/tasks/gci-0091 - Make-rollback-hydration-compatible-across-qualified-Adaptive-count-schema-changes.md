---
id: GCI-0091
title: >-
  Make rollback hydration compatible across qualified Adaptive count schema
  changes
status: To Do
assignee: []
created_date: '2026-10-03 20:03'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 101000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dev v0.6.0 T3 published recommendations_pending=null for unknown Adaptive coverage. Restoring the saved v0.4.4 deployment alone made its T1 cost builder crash at float(None) while hydrating that newer T3 input. Root restored the exact retained pre-upgrade T3 scan version after fresh estate equality and numeric-field checks; a subsequent naturally scheduled T1 completed exit0 and published a healthy five-stack scan. No replacement manual T1 was launched. This establishes a rollback compatibility gap, not permission or pricing repair authority.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A red public-boundary reproduction covers an older consumer hydrating the newer qualified/unknown Adaptive payload; do not manufacture zero savings or loosen committed coverage expectations.
- [ ] #2 Define and verify the supported upgrade and rollback hydration contract, including retained-version recovery and fresh estate checks, before another deployment.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
