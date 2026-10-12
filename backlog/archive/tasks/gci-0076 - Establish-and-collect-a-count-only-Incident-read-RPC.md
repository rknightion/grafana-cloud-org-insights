---
id: GCI-0076
title: Establish and collect a count-only Incident read RPC
status: Parked
assignee:
  - '@loop24-root'
created_date: '2026-10-02 09:25'
updated_date: '2026-10-12 22:21'
labels:
  - feature-usage
  - scope-decision
dependencies: []
references:
  - codex/loop9-evidence/L-fam/packets.md
priority: medium
type: task
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner approves one exact-path POST in principle; exact safe method, read privilege and all-population completeness remain unverified. No previews/content fallback or blanket RPC grant. Owner decision GCI-0041 (product read scope approval) is conditional future authority, not a customer grant or loop9 implementation admission. Packet 3 in codex/loop9-evidence/L-fam/packets.md (sha256 e46afeb70fca8cd53ee0843c898c810a80cc05bc4238db02d8df2c6310eac6ad) holds exact routes/pairs, exclusions and outstanding witnesses.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Fresh authorised dev evidence establishes exact action/scope pairs, permitted route/method and complete count visibility, or records the precise blocker without widening authority
- [ ] #2 Any implemented source emits counts and bounded enums only; sensitive sentinels are absent from payloads, logs, errors and persisted envelopes; unavailable coverage remains absent
- [ ] #3 Any implementation follows fresh inventory, exact selected read boundaries and offline public-boundary proofs with final just check and hosted CI; conditional blockers in the packet are resolved before build
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop24 D-DEAD23 final witness: robk POST read-confirmation StatusService.GetAffectedIncidentsBeforeStatusMutate at granted /api/plugins/grafana-irm-app/resources/api/v1/ path, body {}, returned HTTP404/curl22 at 2026-10-12T22:19:40Z. Historical source lacks v1: this is failure within the granted exact witness, not universal route absence. No readable complete all-incident count or reader-compatible action/scope established. No fallback, scope change, content previews or implementation. Wont-do under frozen owner ruling; archive. Attempts: 0 implementation this loop; one final witness consumed. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/root/incident.json.
<!-- SECTION:NOTES:END -->
