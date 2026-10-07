---
id: GCI-0101
title: Decide whether to read Loki index volume for top log producers per stack
status: To Do
assignee: []
created_date: '2026-10-06 10:23'
updated_date: '2026-10-07 01:21'
labels:
  - owner-decision
  - cost
dependencies: []
priority: medium
type: task
ordinal: 117000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment gap 9: Loki GET /loki/api/v1/index/volume or index/stats on hlInstanceUrl would answer which service drives log ingest cost. Existing logs:read, but a new route outside AGENTS.md's Loki label/limits reads; never read log content. Org-realm token reachability unverified.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner decision recorded on the route and the stream-label dimension allowed
- [ ] #2 If approved, a live staff witness of the route and response shape precedes any implementation task
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop14: D-LBL6 covers Loki /series, index/stats and index/volume routes for labelling purposes after recorded staff witnesses; the top-producers dimension remains open and is not admitted in this loop.
<!-- SECTION:NOTES:END -->
