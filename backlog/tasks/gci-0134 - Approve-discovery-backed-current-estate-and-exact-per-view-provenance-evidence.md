---
id: GCI-0134
title: Approve discovery-backed current-estate and exact per-view provenance evidence
status: In Progress
assignee:
  - '@loop24-root'
created_date: '2026-10-12 16:03'
updated_date: '2026-10-12 22:20'
labels:
  - dashboards
  - owner-decision
  - schema
dependencies: []
references:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/view-metadata/report.json
priority: medium
type: task
ordinal: 171000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The bounded dashboard-only metadata build in GCI-0114 (per-view history and metadata gaps) cannot prove present estate membership, departure or universal view completeness from existing last-good objects or historical Mimir label values. Current generated_at is an envelope composition/publication marker, not exact S3 upload or source observation time; input provenance ages are estimates. A failed inventory call withholds publication, so old snapshots alone cannot establish a newer failure/current identity set. This packet requires a separately approved source/schema/privacy and dashboard-readable evidence contract, not implementation authority in loop23. No configured estate roster, scan-reader access, extra series or source-route/scope widening is implied.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An approved bounded evidence contract distinguishes successful fresh current-inventory identity/status observation from failed/ambiguous unknown inventory and historical snapshot membership, while preserving existing all-publication refusal and last-good objects.
- [ ] #2 A dated successful nonempty authoritative inventory observation can establish departure only at its own identity/time; failed or ambiguous evidence retains historical rows and never publishes estate zero or label-history union as current.
- [ ] #3 Source-specific measured-empty, unavailable, bounded-partial and complete semantics are explicit; partial reads and missing legacy metadata never manufacture exhaustiveness or zero.
- [ ] #4 Exact source observation time, envelope composition/publication marker and S3 upload time have separate meaning; missing or older metadata stays unknown and own-input hydration, future-skew, privacy and source-floor fences remain intact.
- [ ] #5 Before implementation, owner approves exact source/schema/reader-access/retention/metric-budget scope and compatibility for accepted consumers; public artifact counterexamples cover failed inventory, removed stack, missing metadata and retained last-good without configured rosters.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23: zero implementation attempts; named follow-up packet captured under D-DOC23, owner-parked. Current loop builds only conservative schema-free display; resume after owner-approved evidence/source/schema/reader/privacy/compatibility contract, preserving failed-inventory publication refusal and last-good behavior.
<!-- SECTION:NOTES:END -->
