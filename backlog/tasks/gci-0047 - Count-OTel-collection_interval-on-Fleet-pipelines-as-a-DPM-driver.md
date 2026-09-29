---
id: GCI-0047
title: Count OTel collection_interval on Fleet pipelines as a DPM driver
status: To Do
assignee: []
created_date: '2026-09-29 16:36'
labels: []
dependencies: []
priority: medium
type: enhancement
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0046 compares only scrape_interval. OTel pull receivers such as hostmetrics use collection_interval, which also sets DPM. Lab stacks carry 10s and 15s collection_interval values that GCI-0046 does not see. Extend the same in-memory parser and view rather than adding a second surface.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 collection_interval on wired OTel pull receivers is parsed and compared with the default alongside scrape_interval
- [ ] #2 The view states which attribute produced each interval
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
