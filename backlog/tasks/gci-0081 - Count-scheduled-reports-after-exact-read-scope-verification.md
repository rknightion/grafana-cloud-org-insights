---
id: GCI-0081
title: Count scheduled reports after exact read-scope verification
status: To Do
assignee: []
created_date: '2026-10-02 09:25'
labels:
  - feature-usage
  - scope-decision
dependencies: []
references:
  - codex/loop9-evidence/L-fam/packets.md
priority: medium
type: task
ordinal: 91000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Historical Admin empty and reader403 do not establish full visibility. Exact reports:read scope, positive control and paging require proof; no report creation or sending. Owner decision GCI-0041 (product read scope approval) is conditional future authority, not a customer grant or loop9 implementation admission. Packet 8 in codex/loop9-evidence/L-fam/packets.md (sha256 e46afeb70fca8cd53ee0843c898c810a80cc05bc4238db02d8df2c6310eac6ad) holds exact routes/pairs, exclusions and outstanding witnesses.
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
