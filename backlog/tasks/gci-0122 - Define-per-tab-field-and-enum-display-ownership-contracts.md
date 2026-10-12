---
id: GCI-0122
title: Define per-tab field and enum display ownership contracts
status: Parked
assignee:
  - '@loop23'
created_date: '2026-10-06 17:50'
updated_date: '2026-10-12 21:43'
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
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop23 four implementation attempts, one review-repair round, ceiling reached. Final uncommitted candidate at caf04314cf1da919f520ef9941f615daf9e39c4c has patch60df2aee20672219f647dedc4253544000b5825babab77159bb9f0cf31b900c7. Candidate gate red: older exact-lineage recognizer rejects two-field tenant projection (10 ai_tenant_config gaps); 2713 passed,2skips but Tofu not reached. Actual owner runtime65/66: retention range-table identities/cardinality unresolved at disclosed datasource-frame adapter; explicit route_parked/Excluded-rules pair proof missing. Boolean projection28/28 and tables181/181 passed; CRcomplete0/all5 does not clear red/fullAC. NO LAND. Resume requires owner ceiling increase and exact guarded lineage negative controls, proper retention datasource boundary and exclusion proof. Keep candidate/worktree/evidence; no weaker tests or new producer/source authority.
<!-- SECTION:NOTES:END -->
