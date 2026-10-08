---
id: GCI-0104
title: 'Publish gcom billing-period, plan and provider fields already fetched'
status: In Progress
assignee: []
created_date: '2026-10-06 10:23'
updated_date: '2026-10-08 10:46'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop18 candidate operator uses: Billing period start/end contextualize billed-user review; Provider/Provider region localize infrastructure incidents; Plan name groups commercial reviews without inferring entitlement; Admins/Editors/Viewers(daily) support access reviews, not billing calculations; Contact-point type mix identifies configured channel dependencies and counts returned integrations, not receiver names or delivery health. Dropped trial because rawflag proves neither expiry nor conversion; dropped support because boolean proves neither tier nor SLA; dropped recording-rule count because existing fetched alert-provisioning schema has no recording discriminator or complete ruler inventory, so a count/zero would invent coverage. Independent patch-bound reviewPASS, CodeRabbitcomplete0findings and gate0 on retained5df805b8 candidate; not landed yet.
<!-- SECTION:NOTES:END -->
