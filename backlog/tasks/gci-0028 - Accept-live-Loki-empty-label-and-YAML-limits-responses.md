---
id: GCI-0028
title: Accept live Loki empty-label and YAML limits responses
status: Done
assignee:
  - '@codex'
created_date: '2026-09-22 10:01'
updated_date: '2026-09-22 10:07'
labels:
  - deployment
  - collector
dependencies: []
modified_files:
  - collector/sources/signal_inventory.py
  - collector/sources/loki_config.py
  - tests/test_signal_inventory.py
  - tests/test_loki_config.py
priority: high
type: bug
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The v0.3.0-rc.60 dev rollout exposed two HTTP-200 response contracts that the synthetic source tests did not cover. Loki omits data for a successful empty label-value result, and /config/tenant/v1/limits returns text/plain YAML. Both were classified unavailable, so T2 correctly refused publication.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A successful Loki label response with omitted data is treated as a measured empty list only on the Loki label route
- [x] #2 Effective Loki limits accept the live text/plain YAML shape and retain per-stream period, priority and selector
- [x] #3 Malformed JSON or YAML remains unavailable rather than becoming an empty result
- [x] #4 The exact repository gate passes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
- [x] #4 just check
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Pin each live response shape with a focused failing source-contract test.
2. Parse only the required Loki YAML subset without adding a runtime dependency, and scope omitted-data handling to the Loki label call.
3. Run the exact gate, review, publish a replacement release, then resume the paused dev rollout.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-22 rollout evidence: dev T2 tasks 860aaa8f812746b3b3e28115931c89d7 and 5b613101f9484a818313a78841346837 exited 1 before publication. Direct probes confirmed HTTP 200 text/plain YAML from /config/tenant/v1/limits on the robk stack and successful Loki label envelopes without data on portinapushtests and rkaidev.

Verification: focused source tests first failed on all three live-contract cases, then passed 20/20. Full just check passed 1,486 tests plus 7,276 subtests, Terraform validation, formatting, identifier history and hygiene. CodeRabbit pass one found malformed ignored YAML could be accepted; structural validation was added. Pass two returned zero findings.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Accepted Loki's live HTTP 200 response contracts without weakening fail-closed behavior: omitted data is empty only for the Loki label route, and the text/plain limits YAML is parsed through a bounded retention-stream reader with whole-response structural checks. Verified by focused regression tests, the exact repository gate and a clean second CodeRabbit review.
<!-- SECTION:FINAL_SUMMARY:END -->
