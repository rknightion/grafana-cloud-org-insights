---
id: GCI-0131
title: Start DNS caller deadline after pool warm-up in phase proof
status: Done
assignee: []
created_date: '2026-10-09 16:36'
updated_date: '2026-10-09 17:04'
labels: []
dependencies: []
references:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop20-evidence/gate-dns-triage.log
priority: high
type: bug
ordinal: 168000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
loop20 composed gate b2b6477 fails DNS-entry assertion because ReadOnlyClient deadline starts before pool warm-up, whereas test wall clock starts after. Triage reproduced isolated pass but traced pre-DNS expiration from unchanged setup; no transport regression observed. Existing completed DNS phase task did not eliminate caller deadline consumption during setup. Release blocks on true composed proof, never a flaky retry substitute.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 DNS phase constructs its deadline-bearing client after pool readiness; pool_start phase still tests admission expiry; every current deadline threshold and resolver-entry assertion unchanged
- [x] #2 Deterministic delayed warm-up negative control fails old setup and passes repaired setup; all existing netbound tests pass; composed just check and exact CI pass
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Repair tests/test_netbound.py only, reproduce delayed setup at process edge, preserve phase assertions/time bounds; gate/review and land; composed gate then release resumes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop20:1 implementation attempt,0 review-repair rounds; accepted804063596dc244aec4f7cb0cf07de1cc4ebd07ce. Deterministic delayed warm-up old proof fails DNS entry, repaired twelve modes/phases and16 focused tests pass. All deadlines/assertions unchanged. CodeRabbit complete major0; preexisting backlog-path minor not changed. Independent review PASS; composed just check2611passed2existing skips/tofu37 exit0; exact CI37962580200 all jobs success. No production change.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Separated pool warm-up from DNS caller deadline without changing proof bounds; exact composed gate and CI passed.
<!-- SECTION:FINAL_SUMMARY:END -->
