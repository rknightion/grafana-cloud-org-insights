---
id: GCI-0064
title: Return the documented CLI exit code for incomplete configuration
status: To Do
assignee: []
created_date: '2026-10-01 11:57'
labels:
  - cli
  - configuration
dependencies: []
references:
  - scan.py
  - collector/config.py
  - docs/getting-started.md
priority: medium
type: bug
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 reference audit found MissingConfig and MissingCredential are siblings of IncompleteConfig in collector/config.py:42-51. The CLI configuration handler catches MissingCredential only, so missing identifiers can produce a traceback and exit1 rather than the intended diagnostic/exit2. Current operator docs disclose the exception instead of claiming uniform behavior. Fix the CLI boundary without performing any live reads or hiding unexpected programming errors.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Incomplete required identifiers and credentials consistently produce a concise configuration diagnostic and intended exit2 before any network or publication
- [ ] #2 Unexpected runtime errors are not swallowed as configuration failures
- [ ] #3 An offline CLI reproduction fails against the old behavior and proves the corrected public exit contract
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
