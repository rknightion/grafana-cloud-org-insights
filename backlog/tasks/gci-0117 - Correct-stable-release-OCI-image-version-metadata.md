---
id: GCI-0117
title: Correct stable-release OCI image version metadata
status: To Do
assignee: []
created_date: '2026-10-06 11:19'
labels:
  - release
  - owner-decision
dependencies: []
priority: medium
type: bug
ordinal: 133000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The v0.7.0 readback established exact release manifest/tag/source SHA and source-bound cosign identity, but both platform OCI version labels were main rather than 0.7.0. An extra version-label assertion failed and is not claimed green. Root did not retag or republish; the pinned shared publisher generated this metadata and its repository is outside the loop13 write envelope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner grants the bounded publisher/caller change; future stable image platform configs have the exact semantic release version while source/revision and signing SHA remain pinned.
- [ ] #2 Real published artifact readback verifies both platforms; no historical tag deletion, movement or source-witness relaxation is used to get green.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
