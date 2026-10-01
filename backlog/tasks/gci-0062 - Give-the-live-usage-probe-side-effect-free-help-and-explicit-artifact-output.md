---
id: GCI-0062
title: Give the live usage probe side-effect-free help and explicit artifact output
status: Done
assignee:
  - '@loop7-root'
created_date: '2026-10-01 11:48'
updated_date: '2026-10-01 14:12'
labels:
  - cli
  - safety
dependencies: []
references:
  - bin/probe_usage_signals.py
priority: medium
type: bug
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 operator-doc audit found bin/probe_usage_signals.py has no argument parser or help boundary. Lines27-29 require a live context immediately, and line529 overwrites the committed testdata/usage-datasource-signals.json artifact. A --help inspection fails without a context and can perform live reads and overwrite measurements with one. This follow-up does not authorize a live probe or replacement of committed evidence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Calling --help or invalid arguments makes no network call and writes no artifact, regardless of configured context
- [x] #2 A live probe requires explicit context and output choices, and existing committed evidence is not overwritten implicitly
- [x] #3 CLI-boundary proof covers help and refusal without live tenants or committed baseline replacement
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
Explicit --context and --out; parsing/refusals precede live reads and writes, existing artifacts require --overwrite, exclusive creation protects a later destination race. Ten offline CLI tests, read-back synthetic gcx artifact proof, just check 1668 passed/2 existing skips/7971 subtests, completed CodeRabbit zero findings covering four files. Landed 72bcf2943ac1408094e115147f08814c73869977, exact CI 36873088668 all four required jobs successful. Execution deviation: first reproduction transiently overwrote only isolated synthetic baseline; restored byte-for-byte, strengthened tripwires reproduced safely. Root verified baseline, landed blob and lane worktree bytes equal; no baseline modification committed or pushed. No live tenant reads.
<!-- SECTION:FINAL_SUMMARY:END -->
