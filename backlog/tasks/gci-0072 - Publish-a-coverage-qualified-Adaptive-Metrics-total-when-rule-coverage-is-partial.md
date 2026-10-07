---
id: GCI-0072
title: >-
  Publish a coverage-qualified Adaptive Metrics total when rule coverage is
  partial
status: Done
assignee:
  - '@loop10-root'
created_date: '2026-10-02 08:17'
updated_date: '2026-10-07 03:53'
labels:
  - adaptive-metrics
  - accuracy
dependencies: []
references:
  - collector/sources/dataplane.py
  - collector/pillars/cost.py
priority: medium
type: enhancement
ordinal: 82000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop8 S-AMR withholds unqualified estate Adaptive Metrics totals (applied rules, savings, headroom) whenever any live in-scope stack's rules read fails. On a large estate one transient failure hides the headline figure and leaves an older last-good copy. Owner decision (Rob, 2026-10-02): when coverage is partial, publish the measured total explicitly qualified as covering N of M live in-scope stacks, never labelled or summed as the estate total; a fully measured estate keeps the unqualified total. Gaps stay absent, never zero.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When rule coverage is partial, the cost/adaptive views publish the measured total with measured and live in-scope stack counts, and nothing presents it as the estate total
- [x] #2 Full coverage still publishes the unqualified estate total; zero coverage publishes no total; findings gauges keep the loop8 complete-coverage rule unless the owner-approved qualified form is explicitly declared
- [x] #3 Any new metric is declared in budget.py CATALOGUE with a time-series justification, BUDGET.md is regenerated, VIEW_INPUTS re-derives cleanly, and a public-boundary proof crosses compose into the dashboards/findings consumers
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
L-amq implements S-AMQ failing-first, gates final rebased candidate, CodeRabbit and exact landed CI; root live readback after release.

Loop10 a2: frozen S-COV extends compose/publication/findings ownership; implement packet AC1-3 failing-first, CodeRabbit, final-rebase just check, exact landed CI; root live readback after release.

a3 root rescue implements explicit three-item compose return, channel through scan emission/publication/findings and mechanical caller adapters, with no hidden compatibility state. Original packet ACs unchanged.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop9 L-amq-a1 blocked without edits: frozen ownership lacks a coverage channel for a fully measured empty headroom view. Per-view publication metadata would require compose/S3 publisher shared-seam changes not granted to lane, with compose owned by L-sm. Existing safe withholding retained; no new contract invented. Offline AC1 compose/findings reproduction failed as expected at 73eed45. Resume requires explicit frozen coverage placement/ownership.

Loop10 recommission: loop9 a1 blocked on empty-view coverage channel -> S-COV frozen and files assigned -> failing-first empty-rows partial estate publication assertion -> a2 reserved, a3 root rescue and a4 specialist remain. No attempt reset.

Loop10 a2 consumed, infra 0, blocked without implementation: S-COV omitted scan compose unpack/_emit/findings propagation and concrete API. Root §9 amendment freezes explicit (metrics, views, view_coverage) tuple, grants runtime plumbing and mechanical caller unpack migration. a3 root rescue reserved; empty partial compose-to-real-S3 failing reproduction is discriminator; a4 remains.

Loop10 a3 consumed infra0, blocked before runtime implementation: mandatory value_savings envelope coverage metadata outside cost-only golden ownership. Root explicitly grants value_savings golden and any additional Adaptive metadata-only envelopes, mechanical S-COV caller propagation within final a4 specialist rescue. Existing failing test retained. a1/a2/a3 consumed; a4 final reserved, no ceiling raised.

Loop10 a4 final implementation locally proved AC1-3, gate1688pass/2skipped/8016subtests, CodeRabbitcomplete30/30 with one minor denominator suggestion left because row is explicitly org share. Rescue push blocked by runtime loop-guard before execution; staged tree9b9233960bd035b34373697766f09cc714113e32 and patch7401e82d5929c318f23479b03474a2d4bbe88c29c6f16a422288fc43a69906f1 captured/verified. Root reviewed full diff and landed EXACT same tree f908c07baa45a622c3e1014ed57a7b0ec09ddb2d via authorized path-bounded commit/push. CI pending exactSHA. All a1-a4 consumed, infra0; no new implementation allowance or guard/config bypass.

Root-landed exact immutable candidate f908c07baa45a622c3e1014ed57a7b0ec09ddb2d CI37023316214 success. Implementation delivery accepted locally+hosted, no live partial-estate claim; R-dev release readback still owed. L-seg source packet prerequisite unlocked by landed coverage seam.

Loop10 offline/publicboundary/exactCI/release0.5.0 allAC1-3 met, Goal liveR-dev qualifiedfieldsreadbackunproven (AWSauthblocked) thereforecampaignacceptancePARKED, notpartial-liveproof. No livepartialestateobserved; no newmetricnames. a1-a4consumed/infra0, no implementationallowance reset; resume deployment/readback only existinggatedcode, notanotherimplementation.

loop14 live readback only; all4 historical implementation attempts remain consumed, no code or ceiling reset. Fresh v0.7.1 manual-T1 views03:24:08Z carry measured4/in_scope5/completefalse; qualified row labels inspected, all4 actual installed Infinity backend metadata queries returned matching count/boolean frames. Real partial qualification observed from4 unsegmented plus1 unknown segment discovery; no complete-estate total claimed. Shared publisher verifier false rejection is separately tracked as GCI-0123 (accept intact Infinity metadata queries), not another Adaptive-total implementation. No visible browser claim. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop14-evidence/R-dev/qualified-live-acceptance.json.
<!-- SECTION:NOTES:END -->
