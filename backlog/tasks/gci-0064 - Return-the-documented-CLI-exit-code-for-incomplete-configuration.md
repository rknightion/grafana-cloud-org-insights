---
id: GCI-0064
title: Return the documented CLI exit code for incomplete configuration
status: Done
assignee:
  - '@loop7-root'
created_date: '2026-10-01 11:57'
updated_date: '2026-10-01 14:18'
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
- [x] #1 Incomplete required identifiers and credentials consistently produce a concise configuration diagnostic and intended exit2 before any network or publication
- [x] #2 Unexpected runtime errors are not swallowed as configuration failures
- [x] #3 An offline CLI reproduction fails against the old behavior and proves the corrected public exit contract
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop7 frozen packets: bounded implementation or AC1 research; public-boundary proof, offline gate and CodeRabbit before landing, exact landed CI. Root security review/guard landing, research staff GET probe and conditional reserve decision, integrated review, stable release and dev-only rollout proof. Tracker remains root-owned.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
CLI catches shared IncompleteConfig base (both subclasses) before metadata/source/publication calls: actual cleared-environment subprocess missing identifier exits 2 with one JSON stderr record and no stdout. Unexpected error propagates unchanged. Three added boundary tests and two publication-guard tests updated because S-EXIT requires config validation before metadata. Failing-first watched missing identifier traceback/exit 1. Landed b073f9182dc73613005e32b4d3d694dbdd84a613, exact CI 36874121093 all four jobs successful; 57 targeted tests, final just check, completed CodeRabbit zero findings. No live calls.
<!-- SECTION:FINAL_SUMMARY:END -->
