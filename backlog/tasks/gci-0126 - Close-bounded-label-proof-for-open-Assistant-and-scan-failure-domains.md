---
id: GCI-0126
title: Close bounded-label proof for open Assistant and scan-failure domains
status: Parked
assignee: []
created_date: '2026-10-07 17:03'
updated_date: '2026-10-07 17:04'
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
- [ ] #1 Independent upstream taxonomy or an explicitly approved bounded projection defines the three domains and compatibility treatment without allowing identity-bearing or arbitrary upstream values as metric labels.
- [ ] #2 The real publication boundary rejects or safely normalizes unsupported values before output; fail-first public-boundary reproduction covers novel Assistant fields and failure classes, not only a helper or fixture echo.
- [ ] #3 Capacity, runtime vocabulary, reserves and residual UNKNOWN proof are kept distinct in budget and coverage reporting; existing consumers are preserved or deliberately migrated under an approved contract.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop15: GCI-0126 (close bounded-label proof for open Assistant and scan-failure domains) parked owner, implementation attempts 0 and review-repair rounds 0. Source inspection and local generic-guard helper reproduction complete; no deployed novel-value occurrence or publisher-path enforcement claim. Existing producer seams and consumer taxonomy cannot be silently changed by the domain-reporting task.
<!-- SECTION:NOTES:END -->
