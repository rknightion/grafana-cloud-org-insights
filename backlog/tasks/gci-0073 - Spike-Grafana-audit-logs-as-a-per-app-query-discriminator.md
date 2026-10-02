---
id: GCI-0073
title: 'Spike: Grafana audit logs as a per-app query discriminator'
status: Done
assignee:
  - '@loop9-root'
created_date: '2026-10-02 08:17'
updated_date: '2026-10-02 09:36'
labels:
  - feature-usage
  - research
dependencies: []
references:
  - backlog/tasks
priority: medium
type: task
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0040 and GCI-0032.01 cannot attribute queries to individual Scenes apps from usage-insights alone. Owner direction (Rob, 2026-10-02): audit logs, where an org has opted in upstream, land in the stack's main logs datasource as {kind="auditing", service_name="grafana-audit-log"}. Loop9 preparation found no such streams on one candidate customer stack over 7 days; the owner names others. Read-only research: which fields identify the originating app or plugin, how they join to usage-insights data-request events, the opt-in and coverage limits, and whether a collector can read them under the existing reader scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Exact stream selector, datasource and field names of audit events recorded from at least one stack with audit logging enabled, or a recorded negative with the stacks checked
- [x] #2 Whether a field identifies the app/plugin behind a query is answered with evidence, and the join to usage-insights data-request events is described
- [x] #3 Opt-in coverage, reader-scope requirements and privacy handling for identity-bearing audit fields are stated, with a follow-up task if a collector source is viable
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Root bounded read-only Loki count sweep on owner-named contexts/datasources; retain negatives or private positive sample; mapper analysis only if positive. No new scope or live writes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop9 read-only spike found positive main-Loki audit events on two owner-listed contexts (7d), with bounded 24h/500-row private sample; third primary datasource negative30d. Sample SHA256 3ef17a0178d316c97aee0f03e13591ca40f01f95ca44ccd7981164c6c31909b8. Independent L-audit observed decrypt458/list27/get8/patch7, caller/decrypter identity fields, no requestID/userID/path or data-request join key. Identity is audited service caller, not established originating browser app/plugin. Time-only correlation cannot prove per-app attribution. Existing deployed stack-reader main-logs proxy count GET returned403; usage-insights query pin is insufficient, and no new datasource grant is authorised. Upstream audit opt-in and bounded sample cap limit coverage. Drop subjectUID/object/namespace/IPs/user-agent/raw identity fields; retain only purpose-qualified bounded counts. Extra datasource query failures are unproven, not negative results. No viable collector source or follow-up implementation admitted. Private evidence R-audit and L-audit; exact selectors service_name=grafana-audit-log and kind=auditing, datasource grafanacloud-logs; recorded label names and typed field inventory stay in private evidence.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Audit spike answered from bounded positive main-Loki events and independent field analysis. Caller/decrypter identities are not proven browser-app identity; no exact audit-to-data-request join in500 sampled rows. Deployed reader main-logs GET403 proves current scope insufficient. Upstream opt-in and sample limits/privacy exclusions recorded; no viable source or follow-up implementation admitted. Repository documentation-only checks inherit exact root CI36990463778, not proof of live attribution.
<!-- SECTION:FINAL_SUMMARY:END -->
