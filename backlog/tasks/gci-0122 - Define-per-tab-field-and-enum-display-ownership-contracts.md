---
id: GCI-0122
title: Define per-tab field and enum display ownership contracts
status: Parked
assignee:
  - '@loop24-root'
created_date: '2026-10-06 17:50'
updated_date: '2026-10-12 22:24'
labels:
  - dashboards
  - coverage-debt
  - owner-decision
dependencies: []
references:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/field-ownership/final-report.json
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/field-ownership/final-candidate.patch
priority: medium
type: task
ordinal: 157000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Current hardened per-tab checks prove placed query-bearing elements and field selectors against genuine envelopes, not an independently declared tab-specific product coverage contract. Enum selectors may include values while aggregating away their identities. This is disclosed coverage debt, not separately visible enum proof.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner grades tab-specific field/enum ownership and whether distinct enum granularity must survive aggregation, with explicit dispositions for explanatory-only tabs and intentional aggregate headlines.
- [ ] #2 An independent contract and meaningful seeded counterexamples prove each required tab/field/enum display; structural placement or query-name presence alone cannot claim that stronger coverage.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Build frozen D-LAY23 section2 independent field/enum ownership contract on accepted layout source. Owner tabs display each required field and enum value distinctly; seed meaningful per-value counterexamples across assembled JSONata/Prometheus/Grafana transformations rather than structural query-name or selector existence alone. Explicit explanatory-only and titled-aggregate exemptions; existing source/lineage/optional-state/privacy/OnCall/raw-unit guards unchanged. Dashboard files only, no source/schema/new-series/identity/reader expansion; root landing after full gate/review then exact composed gate and CI.

Final bounded packet: repair the older dashboard_coverage_inventory only to recognize the exact type-preserving two-field JSONata projection with negative controls against arbitrary replacement/filter; establish actual datasource range-table identity/cardinality before claiming retention behavior (do not infer deployed bug from adapter); add explicit route_parked/not_evaluated and Excluded-rules relationship seed; verify full47row contract, review delta, complete gate and exact CI only after an owner-raised ceiling. Existing source/schema/reader/series/identity fences remain.

Loop24 D-CAP24 resume: total ceiling8=4 consumed+4 conditional future ladder. No new attempt until boundary readiness is proved. (1) supply versioned genuine Prometheus range-table DataFrame fixture or exact local converter witness for A/B, >=2 identities and >=6 repeated samples per side; assert one intended row per stack, paired values, zero, unequal values, units; negative collapse/duplication/swapped/lost-values/scalar controls. Adapter72rows is NOT deployed bug proof; no instant-query substitution. (2) source/fixtures prove route_parked is not_evaluated and overlaps Not evaluated; Excluded rules counts only parked same-stack/signal rows. Future paired owner consumer-path seed with parked+missing_input plus not_applicable/deadline/truncated controls must display Reason and coverage count, reject remap-to-excluded and wrong-signal counts. (3) repair older dashboard_coverage_inventory only for exact two-field type-preserving tenant selector; actual assembled ten-field lineage must pass, fabricated key, literal true:false replacement, appended enabled filter, destructive object/scalar/filter and unknown-column controls must fail. Preserve older optional-root positive. Reconcile retained candidate old base to current main before any new ladder.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop23 four implementation attempts, one review-repair round, ceiling reached. Final uncommitted candidate at caf04314cf1da919f520ef9941f615daf9e39c4c has patch60df2aee20672219f647dedc4253544000b5825babab77159bb9f0cf31b900c7. Candidate gate red: older exact-lineage recognizer rejects two-field tenant projection (10 ai_tenant_config gaps); 2713 passed,2skips but Tofu not reached. Actual owner runtime65/66: retention range-table identities/cardinality unresolved at disclosed datasource-frame adapter; explicit route_parked/Excluded-rules pair proof missing. Boolean projection28/28 and tables181/181 passed; CRcomplete0/all5 does not clear red/fullAC. NO LAND. Resume requires owner ceiling increase and exact guarded lineage negative controls, proper retention datasource boundary and exclusion proof. Keep candidate/worktree/evidence; no weaker tests or new producer/source authority.

Loop24 read-only boundary research accepted, zero implementation attempts. Root inspected retention builder and evaluator/summary semantics; retained five hashes match historic candidate. Source/fixture boundaries2-3 established, but genuine retention datasource/converter frame is missing, so D-CAP24 readiness gate remains closed. Paired consumer display proof remains future acceptance, not missing producer semantics. Do not blindly replay historic red candidate. Remaining evidence blocker and exact controls in /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/field-boundaries/lane.md. Prior4 implementation attempts and1 review-repair remain; total8 authorized conditionally, not reset.
<!-- SECTION:NOTES:END -->
