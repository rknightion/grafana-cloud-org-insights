---
id: GCI-0040
title: Find a defensible per-app discriminator for Scenes query events
status: Parked
assignee:
  - '@loop3-root'
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
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 7 - valuable but upstream-dependent. In a live 55-stack sample, scenes lines contained datasource and dashboard fields but no plugin or URL field. Determine whether an upstream enrichDataRequest change or a different existing source can distinguish Metrics, Logs, Traces and Profiles Drilldown and other Scenes apps. Proposed new emitted series: 0 until a discriminator is proven; any future enum metric would cost live stacks times the approved bounded enum.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A known app query is observed before and after any proposed discriminator
- [x] #2 A single source value is never attributed to a specific app by datasource type alone
- [x] #3 The result is documented as supported or unavailable with the exact evidence
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop3 D1b: controlled known-app read queries and guarded delayed usage-insights observations; implement proven discriminator or document unavailable with exact evidence, never attribute by datasource type.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Parked pending a defensible app discriminator: 55 guarded usage-insights stack probes saw scenes, but log lines carried no plugin or URL and datasourceType is ambiguous. Resume with a known Drilldown user query or upstream event enrichment evidence.

loop3 admitted 2026-09-30 under owner goal: root owns tracker; bounded lanes own implementation/discovery, evidence pending. No acceptance claimed yet.

Docs d0b5bb0210870f4ce54031455397be5411e21f74 CI36737688385success, gate1647passed2existing skips7966subtests, CRdocs exemption. Genuine Logs2.6 Chrome frontend40queryPOSTs emitted43actual sourceapp analytics events; exact-stack guarded usage-insights confirmed43. ExistingAdminSA browser control, not human adoption; no app-specific plugin/URL field. AC1 remains partial: no genuine frontend before/after proposed-discriminator trial. First browser blocked analytics so is not absence/before proof; backend-only header trial not substitute. Generic app/scenes remain unsplit; no datasource-type attribution or universal impossibility claim.
<!-- SECTION:NOTES:END -->
