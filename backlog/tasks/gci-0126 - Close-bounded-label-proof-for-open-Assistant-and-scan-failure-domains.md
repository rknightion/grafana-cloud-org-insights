---
id: GCI-0126
title: Close bounded-label proof for open Assistant and scan-failure domains
status: Done
assignee: []
created_date: '2026-10-07 17:03'
updated_date: '2026-10-08 00:03'
labels:
  - cardinality
  - owner-decision
  - metric-domains
dependencies: []
references:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop15-evidence/GCI-0121/V-0121-design.log
priority: high
type: task
ordinal: 161000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Runtime-domain source inspection and independent local helper checks prove three currently open dimensions: Assistant category and surface preserve novel upstream field names, and failure reason preserves arbitrary short exception-class names. The generic emission label guard accepts NovelCategory, NovelSurface and NovelShortError. Planning capacities of eight are not exhaustive taxonomies or cardinality enforcement. Existing producer and guard seams have accepted consumers; the current domain-declaration task must report UNKNOWN rather than silently hard-code or normalize them. No deployed novel-value occurrence or publisher-path enforcement was demonstrated by these helper checks.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Independent upstream taxonomy or an explicitly approved bounded projection defines the three domains and compatibility treatment without allowing identity-bearing or arbitrary upstream values as metric labels.
- [x] #2 The real publication boundary rejects or safely normalizes unsupported values before output; fail-first public-boundary reproduction covers novel Assistant fields and failure classes, not only a helper or fixture echo.
- [x] #3 Capacity, runtime vocabulary, reserves and residual UNKNOWN proof are kept distinct in budget and coverage reporting; existing consumers are preserved or deliberately migrated under an approved contract.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop17 D-TAX16/ASSIST17: use complete pinned private M-assist witness; define bounded public metric projections plus other at real publication boundary, fail-first novel values; preserve consumers, CodeRabbit and root reviewer before land.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop15: GCI-0126 (close bounded-label proof for open Assistant and scan-failure domains) parked owner, implementation attempts 0 and review-repair rounds 0. Source inspection and local generic-guard helper reproduction complete; no deployed novel-value occurrence or publisher-path enforcement claim. Existing producer seams and consumer taxonomy cannot be silently changed by the domain-reporting task.

loop16: GCI-0126 (bound Assistant and scan-failure metric label domains) remains parked, implementation attempts 0. Upstream checkout preflight refused; mapper produced only local open exception catch-boundary witness. D-TAX16 requires observable upstream taxonomy; no guessed vocabulary or private reads. Resume after safe upstream checkout and complete taxonomy witness.

loop17: implementation attempts3 (worker2, root rescue1), review-repair rounds1. Done at026db25ef95fa136bd125b852981ba32f1ac365c, base083df8b. Private pinned M-assist witness completed; fixed public projections plus other preserve existing labels, raw upstream uncertainty not claimed closed. Novel-field and exception fail-first observed real runner/accounting/compose/carry/native publication. Independent review found legacy carry/live double-count7->14; root realT1/native fail-first fixed pre-dedup identities, original loadedstate unchanged. CodeRabbit original+major delta complete0, reviewer delta PASS39tests382subtests; fullgate and composed gate2427passed2skipped23177subtests; exact CI37704917755 requiredleafsuccess. Minor corrupt expired carry robustness retained separately as GCI-0128 (preserve freshness-first rejection for malformed legacy carry records), no live occurrence. Ownership packet gaps amended for intended expectation changes in tests/test_dashboard_coverage.py and tests/test_coverage.py; assertions not weakened. This commit is main only, not signedv0.8.3 release frozen before it.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Enforced metric projection domains at real publication, collision aggregation and legacy carry identity dedup; public fail-first proofs and exact integrated gates accepted, upstream residual uncertainty retained.
<!-- SECTION:FINAL_SUMMARY:END -->
