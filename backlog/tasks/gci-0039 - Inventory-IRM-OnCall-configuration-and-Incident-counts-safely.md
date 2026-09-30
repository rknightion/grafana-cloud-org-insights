---
id: GCI-0039
title: Inventory IRM OnCall configuration and Incident counts safely
status: Parked
assignee: []
created_date: '2026-09-23 18:35'
updated_date: '2026-09-30 16:11'
labels:
  - feature-usage
  - follow-on
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: low
type: enhancement
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 6 - medium value, higher access and privacy cost. OnCall group counters exist, but integrations, schedules, escalation chains and Incident records need separate product reads. Incident read RPC is POST and needs a specific read-only transport decision. Proposed new emitted series: 0; object counts are views.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Integration and schedule output excludes identities and routing secrets
- [ ] #2 Any Incident POST read has an explicit method and privilege contract before implementation
- [ ] #3 Counter activity and configured object counts are labelled separately
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Parked at Wave 1 boundary pending GCI-0041 reader scope decision and exact safe read-route verification. No new scope, policy or credential was granted during research.

loop3 exact-pair probe: disposable basic-None integration counters GET200 matched Admin25, baseline403; token/SA/role cleaned by recorded IDs with GET404. Alert-group stats remained403 under its exact pair despiteAdmin200. IRM implementation/grants remain DEFER: independent V-IRM-grant found archived backend maps list/retrieve/counters to the same integrations:read permission and serializers include ingress URLs; installed UI masking is cosmetic. Hosted server redaction/usable routing credentials unproven, no narrower proven permission. Do not fetch secret-bearing lists or adopt broader grant for count-only output. No Incident POST/identity/routing detail approved.
<!-- SECTION:NOTES:END -->
