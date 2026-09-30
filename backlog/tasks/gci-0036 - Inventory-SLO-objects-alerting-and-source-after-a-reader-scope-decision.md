---
id: GCI-0036
title: 'Inventory SLO objects, alerting and source after a reader-scope decision'
status: Parked
assignee:
  - '@loop3-root'
created_date: '2026-09-23 18:35'
updated_date: '2026-09-30 21:58'
labels:
  - feature-usage
  - follow-on
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: medium
type: enhancement
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 3 - high value, low code cost after authorization. The documented SLO GET returned 403 with the existing reader on nine sampled stacks. After the separate scope decision, count SLOs, alerting state and metrics-versus-KG source with output minimization. Proposed new emitted series: 0; current object state belongs in a view.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Reader grants are approved separately and remain basic-role None
- [ ] #2 Live list readback is compared with an authorized control before zero counts are trusted
- [ ] #3 View reports SLO count, alerting and source without storing expression bodies
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop3 I-0036: implement the accepted existing-reader SLO list seam and count-only view, compare positive dev control, preserve source unknowns, integrate source/tier/hydration/schema/dashboard, synthetic captured-artifact contract, gate/CodeRabbit/exact-SHA CI; root live rollout proof remains separate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Parked at Wave 1 boundary pending GCI-0041 reader scope decision and exact safe read-route verification. No new scope, policy or credential was granted during research.

D1a accepted operational reader sufficiency and positive Admin control on staff dev. Existing separately approved slo pairs stay unchanged; strict subtract-one minimality is unproven and no removal is authorised. Reader None and query pins remain frozen. No AC completion yet.

Loop3 source inventory shipped and dev proved five live rows including a positive configured SLO under existing None readers; original authentication/schema blockers cleared at96b. Strong hard DNS/connect wall-time criterion remains unmet after four cumulative attempts (worker2, rootwiring rescue, specialist); no fifth attempt or criterion waiver. Resume only the named timing concern under new owner direction, not source-count reinvention.

2026-09-30 Rob: the hard DNS/connect wall-time criterion is split into GCI-0053 (collector-wide). GCI-0036 closes on its own three ACs once the next loop re-checks them against loop3 dev evidence.
<!-- SECTION:NOTES:END -->
