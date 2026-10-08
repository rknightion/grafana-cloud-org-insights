---
id: GCI-0104
title: 'Publish gcom billing-period, plan and provider fields already fetched'
status: In Progress
assignee: []
created_date: '2026-10-06 10:23'
updated_date: '2026-10-08 10:13'
labels:
  - estate
dependencies: []
priority: low
type: enhancement
ordinal: 120000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment gap 15: gcom.py:15-34 fetch billingStartDate, billingEndDate, provider, providerRegion, planName, trial, support and daily role counts that no pillar uses. Also contact-point type mix and recording-rule counts from payloads alert_routing.py already fetches (gap 11), settings dropped at parse.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 View columns added for the fields with a stated operator use; no new metric without a time-series reason
- [ ] #2 just check green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop18: select existing payload fields with named operator uses; view-only columns within owned files; test public composition, independent review and exact-SHA gate.
<!-- SECTION:PLAN:END -->
