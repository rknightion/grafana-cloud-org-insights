---
id: GCI-0091
title: >-
  Make rollback hydration compatible across qualified Adaptive count schema
  changes
status: In Progress
assignee:
  - '@loop12-root'
created_date: '2026-10-03 20:03'
updated_date: '2026-10-05 16:35'
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
- [x] #1 A red public-boundary reproduction covers an older consumer hydrating the newer qualified/unknown Adaptive payload; do not manufacture zero savings or loosen committed coverage expectations.
- [ ] #2 Define and verify the supported upgrade and rollback hydration contract, including retained-version recovery and fresh estate checks, before another deployment.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement D-HYD12 integer input schema versions, red public-boundary compatibility reproduction, unknown future schema withholding and retained scan recovery documentation; review and gate before landing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop12: 2 implementation attempts, 1 review-repair round. Integer hydrated-input versions and future/malformed-version withholding proven through real hydrate/compose/scan artifact boundaries; nullable Adaptive pending never crash or manufacture zero headroom. Initial CodeRabbit major corrected, final delta complete zero findings; independent review PASS. Landed b8bd98e and 6934546 covered by exact main bbb9668dd89b5733d6817b6cfb1fdaaf1d05cb57 real clean gate, composed gate and CI37329484807 success. Two skipped tests disclosed separately. Historical v0.4.4 crash reproduced at a93e92c3ceaff1489f7be028fa537303dacc3659; retained scan restoration remains mandatory below v0.7.0.

Loop12 correction: previous Done claim covered cost/unknown-rules cases but not valid known applied rules with recommendations_pending=null under unsegmented inputs. Root real compose.build_all reproduction confirms maturity._adaptive_adoption TypeError at applied+pending. Reopen supported-consumer contract for root rescue attempt3; original historical/newer-schema proofs remain valid, no ceiling reset. First scratch reproduction had an incomplete fake and KeyError, discarded as proof; corrected existing synthetic payload reproduces exact maturity failure. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop12-evidence/L-hyd/maturity-supported-null-red-confirmed.log.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Version-aware hydration treats unsupported input schemas unavailable and withholds dependent views; legacy version0 remains conservative. Unknown pending counts omit samples and qualify known-only summaries. RUNBOOK documents fresh-estate-checked retained-version recovery for older binaries. Verified 2011 passed,2 skipped,8925 subtests on integrated bbb9668; evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop12-evidence/L-hyd/ and /Users/rob/repos/grafana-cloud-org-insights/codex/loop12-evidence/repair-batch/.
<!-- SECTION:FINAL_SUMMARY:END -->
