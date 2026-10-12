---
id: GCI-0135
title: >-
  Restore deterministic legacy RPC body-read phase proof without weakening
  deadlines
status: Done
assignee:
  - '@loop23'
created_date: '2026-10-12 19:20'
updated_date: '2026-10-12 20:06'
labels:
  - gate
  - deadline
  - proof-integrity
dependencies: []
references:
  - /tmp/layout-composed-gate/gate.log
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/gate-rpc/gate.log
priority: high
type: bug
ordinal: 172000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop23 composed main ef164dd157f682e752dab17b7153caf6ab41ee55 failed tests/test_netbound.py::test_legacy_complete_transport_body_read_has_wall_time_bound[rpc]: the call timed out before the fixture observed body-read entry. Host load was high but causation unknown. Existing DNS warm-up proof repair GCI-0131 (start DNS deadline after pool warm-up) is Done and is not reopened. The RPC read closure constructs a real urllib opener before entering the mocked open/body boundary, so phase-isolation setup may consume the short budget. This is an acceptance blocker requiring deterministic process-edge evidence, not permission to increase any deadline or skip the phase.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A bounded deterministic reproduction distinguishes opener/setup-before-read from actual never-returning body read and fails the old phase proof for the observed reason; narrow original RPC and legacy-query cases are exercised without assuming load causation.
- [x] #2 Body-read phase observes actual read entry through the real bounded caller, while preserving every existing caller timeout, elapsed bound, subprocess timeout, survivor/admission and entry assertion; no test skip/loosen/special-case or production behavior change.
- [x] #3 A separate process-edge opener/setup never-returning control still proves the whole legacy RPC wait is bounded, so isolating body setup does not substitute a weaker transport proof.
- [x] #4 Independent guarded review, complete CodeRabbit, focused netbound checks, composed just check and exact required CI pass on the repair identity; failures/skips remain separately reported.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Bounded tests/test_netbound.py-only repair packet: first reproduce original RPC/query narrowly and inject deterministic delayed opener construction to establish whether pre-body setup consumes body phase. If proven, isolate mocked opener construction/open at process edge before starting unchanged body clock while preserving real helper/bounded caller and read-entry assertion; add separate never-returning opener/setup phase to prove complete caller fence remains. All timeouts/assertions unchanged, production untouched. Guarded independent review/CodeRabbit before root land; final composed gate and exact CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop23 one implementation attempt, zero review-repair rounds. Candidate delayed-opener negative control failed original body-entry proof, corrected real helper/body and new separate setup proofs retained every original deadline and entry assertion. New setup check fault control detected bypassed fence at unchanged process bound. Security review PASS; CodeRabbit complete zero findings/all one file; root landed e1f854d74564dd9370c0a223b48db7cf3864f7eb. Exact composed just check: 2703 passed, 2 pre-existing skips, 26726 subtests, Tofu37, identifier history clean; CI38300327556 required jobs success. Earlier host-load cause remains unknown, no production behavior change. RSS581.5MiB is pytest process only.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Separated body and opener-setup witnesses without weakening complete caller deadline proof; exact composed gate and required CI passed.
<!-- SECTION:FINAL_SUMMARY:END -->
