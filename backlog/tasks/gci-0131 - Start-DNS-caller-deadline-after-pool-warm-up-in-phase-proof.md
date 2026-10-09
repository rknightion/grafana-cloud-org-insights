---
id: GCI-0131
title: Start DNS caller deadline after pool warm-up in phase proof
status: In Progress
assignee: []
created_date: '2026-10-09 16:36'
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
- [ ] #1 DNS phase constructs its deadline-bearing client after pool readiness; pool_start phase still tests admission expiry; every current deadline threshold and resolver-entry assertion unchanged
- [ ] #2 Deterministic delayed warm-up negative control fails old setup and passes repaired setup; all existing netbound tests pass; composed just check and exact CI pass
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Repair tests/test_netbound.py only, reproduce delayed setup at process edge, preserve phase assertions/time bounds; gate/review and land; composed gate then release resumes.
<!-- SECTION:PLAN:END -->
