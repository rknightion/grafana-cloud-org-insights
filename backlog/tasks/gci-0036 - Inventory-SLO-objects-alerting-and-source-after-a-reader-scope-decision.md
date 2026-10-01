---
id: GCI-0036
title: 'Inventory SLO objects, alerting and source after a reader-scope decision'
status: Done
assignee:
  - '@loop3-root'
created_date: '2026-09-23 18:35'
updated_date: '2026-10-01 03:09'
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
- [x] #1 Reader grants are approved separately and remain basic-role None
- [x] #2 Live list readback is compared with an authorized control before zero counts are trusted
- [x] #3 View reports SLO count, alerting and source without storing expression bodies
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
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

loop4 M-ac mapped three criteria: role approval and minimized five-row dev view supported by existing artifacts. Positive authorized reader/Admin comparison exists in private D1a slo-comparison witness (18/18, equal UUID set, same payload except allowedActions). Current live rollout revalidation remains separate; DNS criterion belongs to GCI-0053.

loop4 acceptance reconciled at stable9ba3a4c CI36790758947. Freshfull-estateT2/currentSLOview5rows19definitions, source18Metrics1KnowledgeGraph,19configuredalerting, no expressionsstored; rootpre/post5None readersfullpairs/IDs/SSMversionsexactlyunchanged andqueryUIDpinsintact. SeparatelyapprovedD1agranthistoricalpositive18/18SLOreader/Admincontrol matchedUUIDsets/fullpayloadexceptallowedActions, independentlyrederived byroot; not a rolecount. DNScriterion splittoGCI0053 nowDone, no furtherGCI0036implementationattemptspent. Existing privacy/source scope boundary preserved.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed the three actual SLO criteria using separate approved unchanged reader grants, historical positive authorized reader/Admin control and fresh positive minimized live inventory under the stable image. No expression bodies or new credential/role grants. Exact-SHA CI green; hard caller deadline tracked separately in GCI0053.
<!-- SECTION:FINAL_SUMMARY:END -->
