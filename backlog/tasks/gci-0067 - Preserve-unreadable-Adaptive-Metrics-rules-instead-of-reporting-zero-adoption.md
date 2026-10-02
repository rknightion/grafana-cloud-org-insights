---
id: GCI-0067
title: Preserve unreadable Adaptive Metrics rules instead of reporting zero adoption
status: Done
assignee:
  - '@loop8-root'
created_date: '2026-10-01 14:18'
updated_date: '2026-10-02 00:34'
labels: []
dependencies: []
references:
  - collector/sources/dataplane.py
  - collector/pillars/cost.py
  - collector/pillars/maturity.py
priority: medium
type: bug
ordinal: 77000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 read-only M-seg found adaptive_metrics converts an unsuccessful rules response into an empty rule list when recommendations succeed, so rules_applied zero and adopted false can look like measured absence. This is independent of segmented savings coverage; no live failure demonstrated. Source availability and downstream cost/maturity interpretation need an honest unknown state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A failed or malformed applied-rules read is distinguished from a successful empty list
- [x] #2 Consumers do not present unreadable applied-rule state as measured zero or nonadoption
- [x] #3 Offline source-to-consumer public-boundary reproduction fails before the correction and proves unknown versus measured empty
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop8 bounded implementation per frozen packet; worker owns offline reproduction/gate/review and terminal return; root owns tracker reconciliation and integrated acceptance.

L-am-a2: fix all-unknown headroom withholding and full-in-scope estate completeness guards, prove each failing first, preserve measured-population usability, rerun unchanged hydration derivation/gate, CodeRabbit and exact landed CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root loop8 disposition S-AMR-R1 (medium materiality): CodeRabbit major finding on incomplete estate aggregates accepted. Strengthen the unlanded seam: measured per-stack values, measured-population benchmarks and explicitly labelled measured summary subtotals remain useful; unqualified estate additive rules/adoption totals are withheld/null unless every live in-scope stack has readable rule input. Unknown stacks stay excluded from unadopted lists and adoption scoring. All-unknown cost_adaptive_headroom is withheld, preserving last good view; recommendations view remains independently available. No new metric/label/catalogue or route. Existing new mixed-estate test expectations change because intended completeness contract changes, never to mask a defect. Rejected retaining unqualified partial total because it could mislead. Rejected discarding measurable per-stack inputs because source availability is independent. Reversal cost local guard/test changes before any accepted consumer; no landing yet. L-am-a1 blocked with final gate green and two unresolved majors; L-am-a2 authorized for these bounded repairs, two attempts remain afterward.

Loop8 L-am-a2 landed a889d7492732decd01f382814a79543f4632e85a, exact CI 36931046877 success. Final pre-push gate 1685 passed, 2 skipped, 8016 subtests; CodeRabbit completed zero findings all seven changed files. Both a1 major findings repaired under root S-AMR-R1 with failing-first source-to-compose and mixed/missing-live-member proofs, unchanged hydration table/fixtures/dashboard gates. Unknown rule metrics absent; incomplete unqualified estate totals withheld/null; all-unknown headroom withheld preserving last good; measured per-stack/benchmarks remain. a1/a2 consumed, zero infra retries; no live proof yet. Intermediate a2 probes red for URL overfiltering/paused population fixed without weakening tests. Evidence codex/loop8-evidence/L-am/a2-*.

R-int-r1 rejected a889d749: downstream findings derive partial headroom view into an unqualified zero/partial estate gauge; dashboard sums applied per-stack series without measured-population qualification. Root rescue L-am-a3 expands root-owned repair to cost headroom completeness, existing test_cost public compose-to-findings proof, and bin/dashboards.py panel qualification. Changed premise: source/cost-only tests stopped before findings collaborator. Withhold headroom unless complete live scope so findings stays absent; fully measured empty yields zero. Explicit measured subtotal title/legends/description preserve stack selector without claiming estate adoption or remediation from changing coverage. a1+a2 used, a3 root rescue now; a4 specialist remains, integration review rounds 2/3 available. Release not merged, no deployments.

Root L-am-a3 repaired R-int majors: headroom now requires full live-scope readable rules before publishing its findings source view; compose-to-real-findings test proves absent partial gauge and recovered true-empty zero. Selected-stack applied/pending chart now explicitly measured subtotals, not estate adoption/remediation; query remains selector-aware. Failing-first a3/findings-red.log then narrow and full gate green (1685 passed, 2 skipped, 8016 subtests); offline real dashboard CLI artifact readback passed after supplying synthetic bucket config. CodeRabbit complete zero findings, all three changed code/test files reviewed. Evidence codex/loop8-evidence/L-am/a3. a3 root rescue consumed, no infra retry; a4 specialist remains; R-int round2 still required.

Root L-am-a3 landed fbecf541417508aac30b61e2266787dee3759d67; exact CI36933153109 success, all four jobs, one watch and one readback. Changed-headroom expectation is the intended S-AMR-R2 repair, not weakening. Round2 integration reviewer resumed before release. This completion means code criteria/gate/review/CI accepted; release/live-runtime proof remains separately pending.

Loop8 live proof: signed stable v0.4.3 source8e7423045ee0efa23619ea8e8b5a4af3d1a6f338, separate unsigned consumers. Dev T3 actual new rules_available observed5 measured/0unknown with fresh cost/maturity views; failed-rule branch remains offline proof, not a forced live fault. Authorized customer T2/T1 fleet/profiles310/310 not worse; cost/maturity readback has no new false nonadoption from identifiable unknown inputs. Customer consumes retained legacy natural T3 observations because an extra customer T3 was not granted; no new customer source-flag sample claimed. Changed cost dashboards published/read back on both targets. Both final plans No changes, schedules ENABLED/unchanged; evidence R-dev/acceptance.json and R-cust/acceptance.json. Customer T2 exceeded fit estimate, so T1 held next safe window, never suspended or collided.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Preserved failed/malformed Adaptive Metrics rule reads as unknown rather than zero/nonadoption, with source-through-public-compose proofs and complete live-inventory estate guards. Exact landed gate/review/CI green; live release/runtime readback remains root rollout work.

Final consumer repair also prevents partial headroom views deriving false estate findings gauges and qualifies selected-stack dashboard sums as measured subtotals. Root a3 failing-first compose-to-findings proof, local real dashboard build/readback, CodeRabbit zero findings, exact landed CI36933153109 green.
<!-- SECTION:FINAL_SUMMARY:END -->
