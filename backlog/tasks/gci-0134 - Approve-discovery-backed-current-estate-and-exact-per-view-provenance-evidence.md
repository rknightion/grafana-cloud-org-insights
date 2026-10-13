---
id: GCI-0134
title: Approve discovery-backed current-estate and exact per-view provenance evidence
status: In Progress
assignee:
  - '@loop25-root'
created_date: '2026-10-12 16:03'
updated_date: '2026-10-13 11:33'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop24 reviewed decision draft /Users/rob/repos/grafana-cloud-org-insights/codex/scratch/loop24-gci0134-contract.md: additive optional per-view evidence plus separate minimized outcome projection;0newseries/13827capacity unchanged. Current membership requires witnessed complete nonempty fresh inventory and dated stable identity, not label history; newer failure makes current unknown and preserves historical rows. Exact source observation intervals, composition marker and S3 object time/receipt are separate and digest/version-bound. Source-specific semantic completeness registry, compatibility/hydration carry and floor/future-skew fences retained. Whole-write refusal prevents collector-side failure projection: recommend separately approved typed outcome observer with its own bounded IAM/retention, or explicitly choose reduced success-only metadata and defer failure criterion. Before build Rob must grade exact source/visibility, identity privacy/audience/freshness, observer, schema/caps/strict consumers, clock/storage fidelity, targeted retention and0series scope; no approval follows from review.

loop25 D-PROV25: additive accepted-success evidence only in owned envelope/S3/inventory-validation seam and fail-first real-artifact tests; root frozen inventory-shape witness; root security review then CodeRabbit, local and composed just check, no new series. Outcome observer separately recorded and not admitted.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23: zero implementation attempts; named follow-up packet captured under D-DOC23, owner-parked. Current loop builds only conservative schema-free display; resume after owner-approved evidence/source/schema/reader/privacy/compatibility contract, preserving failed-inventory publication refusal and last-good behavior.

Loop24 contract-draft row completed and independent reviewer PASS at SHA2568e20a4e7c6990a18ec4d7a1e82795937b9887266a766186b42bacf0bf004dd1d; reviewed source base6bc17e11e4199983955779c0860832a248bb9cc9 and main da40892016c603714c42b6546bf4d3b12c72316d. Root reconciled output destination/self-review wording before independent review; no substantive blockers. Original approved-contract AC1-5 remain unchecked: Rob has not approved any source/schema/privacy/observer/access/retention/budget choice. No implementation attempt (cumulative0), no source/schema/customer/live changes or CodeRabbit/runtime gates. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/provenance-contract/review.md and retained loop23 counterexamples incorporated into draft.

loop25 root amended owned seam for inventory evidence transport in runner callsites and optional original-evidence hydration preservation, after read-only lane verified necessary gap. No implementation attempt consumed by inspection; sanitized existing-route shape witness captured exact200. No route, source floor, INPUT_OWNER, payload schema or metric grant widened.

loop25 provenance focused cycle1:83tests/7442subtests passed on partial tree, full just check not run. Root repaired second owned-file gap for copied non-S3 privacy projections: strip ONLY new optional evidence from Loki summary and diagnostic --out, preserve S3 and old semantics. Retained partial unsafe until correction, public CLI/assembled selector proof and final gate/security/CodeRabbit. Final gate must use real .venv not symlink.

loop25 cumulative implementation cycles3 observed (transport focused, privacy/fullgate, helper-stamp/fullgate). Final gate901 failures are new private evidence metadata display debts, not baseline-red. Root authorizes exact finite unrendered/audit declarations in the two existing coverage-test registries, no wildcard/exemption hiding or rendering credit; unknown seeded gap must still fail. Safety incident separately recorded: three attempted synthetic-bucket S3 locks returned2, provider outcome unknown; corrected tests refuse subprocess. Final rescue cycle4 only, no ceiling reset.

loop25 surface1 exact7file manifest6e78f67e accepted for rootlanding: independent guardedsecurityPASS/CodeRabbitcomplete0 coveringall7; final justcheck0/1114.892s Python2727pass/2skip/27626subtests +ToFu37pass and remaininggatesclean. PriorDNSred retained; newbaseproviderred diagnosed113-byteTMPDIR Unixsocketlimit, same6.68plugin passedshortpath then authorizedinfraretry1of2 fullgate0, no source/pin/testweakening. Cumulativeimplementation4 exhausted, infraretry1, no cycle5. PublicCLI+408metadata/12historical JSONata and privacy/nativeLoki/diagnostic failfirstproofs retained; 1051finite metadata debts explicitly unrendered audit, unknownseed stillfails. Root fresh actualapproved inventory payload6+selflink acceptedexactvalidator; visibility/authorityunknown. All privateS3/no-series/sourcefloor/refusal/hydration/timeguard contracts intact. Historicalthree syntheticbucket lockattempt exits2 stillunknown provideroutcome/currentHeadBucket+HeadObject404; correctedtestsrefuse subprocess. AC1-2 observer/current-estate status outsidethissurface remainopen underGCI-0134.01 (outcome observer).
<!-- SECTION:NOTES:END -->
