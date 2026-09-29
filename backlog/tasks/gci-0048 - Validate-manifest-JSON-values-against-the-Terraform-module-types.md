---
id: GCI-0048
title: Validate manifest JSON values against the Terraform module types
status: To Do
assignee: []
created_date: '2026-09-29 17:05'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0045 review F2/F5: Terraform coerces JSON values through module variable types. list(object({selector, minimum_period})) drops extra attributes, the weights object turns a string '2' into 2, and very large integral floats lose precision in Python's int(). A manifest holding any of these hashes differently from the rendered task environment and the task refuses to start, while the wiring preflight passes because the key is wired. The preflight also does not check that an assignment reads the local of the right projection.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 validate() rejects or normalises retention items to exactly selector and minimum_period strings and weights to numbers
- [ ] #2 A contract test proves the normalised manifest digest equals the tofu-rendered task env digest for each coerced case
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
