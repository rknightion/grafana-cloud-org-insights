---
id: GCI-0068
title: Restore insights fixture coverage for hydration dependency re-derivation
status: Done
assignee:
  - '@loop8-root'
created_date: '2026-10-01 14:18'
updated_date: '2026-10-01 21:24'
labels: []
dependencies: []
references:
  - tests/fixtures
  - collector/emit/hydrate.py
priority: low
type: task
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 L-cli targeted tests emitted the pre-existing warning that synthetic scans/t2/latest.json lacks an insights payload, so Pillar J dependencies cannot be re-derived from that fixture. The suite passes, but this warning leaves that contract less directly exercised. Investigate the fixture/source contract without copying live identity-bearing data or pinning incidental output.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Synthetic compose fixtures supply the inputs needed to re-derive Pillar J hydration dependencies or explicitly document a justified separate proof
- [x] #2 The dependency derivation observes the real optional input contract without weakening existing gates
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop8 bounded implementation per frozen packet; worker owns offline reproduction/gate/review and terminal return; root owns tracker reconciliation and integrated acceptance.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop8 L-fix-a1 landed 50d8e509532e9f229b03bc058fea2a6c3a80ff73; exact CI 36927879064 success, CodeRabbit complete zero findings on owned tests/test_scan.py. Fixture already guarded: 44 insights entries; removing key fails derivation, removing declared dependencies causes ten failures; empty payload passes structurally and is not proof of populated observations. Minimal exporter tests now assert intentional missing-insights warning. Procedural deviation: sibling rebase was not re-gated before push; full gate passed immediately afterward at exact landed SHA. Root accepts functional criteria on that evidence, does not claim sequencing compliance or retroactively waive it. No remaining runtime defect demonstrated; R-int will independently review.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Already-guarded hydration fixture confirmed with discriminating mutations; minimal synthetic exporter warnings asserted rather than misdiagnosed as absent fixture coverage. Exact landed gate 1682 passed, 2 skipped, 8003 subtests and CI green. Missed pre-push re-gate disclosed separately; evidence codex/loop8-evidence/L-fix.
<!-- SECTION:FINAL_SUMMARY:END -->
