---
id: GCI-0064
title: Return the documented CLI exit code for incomplete configuration
status: In Progress
assignee:
  - '@loop7-root'
created_date: '2026-10-01 11:57'
updated_date: '2026-10-01 13:51'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop7 frozen packets: bounded implementation or AC1 research; public-boundary proof, offline gate and CodeRabbit before landing, exact landed CI. Root security review/guard landing, research staff GET probe and conditional reserve decision, integrated review, stable release and dev-only rollout proof. Tracker remains root-owned.
<!-- SECTION:PLAN:END -->
