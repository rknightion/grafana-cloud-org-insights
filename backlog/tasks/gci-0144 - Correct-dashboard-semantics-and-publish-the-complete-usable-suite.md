---
id: GCI-0144
title: Correct dashboard semantics and publish the complete usable suite
status: In Progress
assignee:
  - '@codex'
created_date: '2026-10-15 09:12'
updated_date: '2026-10-15 09:27'
labels: []
dependencies: []
priority: high
type: enhancement
ordinal: 182000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The full-suite audit found saved dashboards behind current source, inconsistent AI seat populations, unsupported financial and causal claims, null numeric columns saved as strings, and poor visibility of legends, freshness and unavailable results. Owner approved correctness and usability improvements plus dev/customer validation and rollout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AI seat detail and headline use the same token-active population; numeric schema survives missing values without fabricated zeroes
- [ ] #2 All dashboards use qualified claims, actionable navigation, visible relevant freshness and useful legend and unavailable states while retaining approved data coverage
- [ ] #3 Complete final suite is published to existing dev/customer identities with saved source-contract readback and representative visual and query verification
- [ ] #4 Required gates and review pass; source and rollout evidence distinguish limitations and retain privacy and withdrawn requirements
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement independently owned AI arithmetic, shared builder behaviour and wording corrections; root integrates layout/freshness improvements. Review integrated candidate, run required gate, commit and push. Rebuild all dashboards from actual published views and existing deployment settings, preserve folders and customer price, publish full suite and verify saved contracts, targeted backend boundaries and visuals. No collector route, scope, storage or metric semantics expansion.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementation includes token-active AI seat reconciliation proven with real promtool; both deployed Infinity backends returned declared numeric null then numeric values without coercing null to zero. Source-aware landing context, bounded legends, risk triage, navigation qualification and preserved table/enum contracts integrated. Independent review found zero-versus-missing activity wording; corrected. Full gate first run found one obsolete test requiring a zero-cost claim; updated under approved semantics and focused regressions passed. Final gate and sanitized combined CodeRabbit review are in progress; no dashboards published yet.

Final just check passed:2841tests,29128subtests,2existing skips,45OpenTofu tests; identifiers/history and no-em-dashes clean. CodeRabbit completed all22files including sanitized private operator helpers with one minor residual wording finding, corrected; focused post-review15tests56subtests passed. Independent review correction also resolved. Dashboard-only rollout preserves running collector image/projection; no numerical collector or scope change. Finding summary prose source corrections do not attest changed historical/live Loki records.
<!-- SECTION:NOTES:END -->
