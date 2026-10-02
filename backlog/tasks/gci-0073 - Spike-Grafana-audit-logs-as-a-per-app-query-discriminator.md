---
id: GCI-0073
title: 'Spike: Grafana audit logs as a per-app query discriminator'
status: To Do
assignee: []
created_date: '2026-10-02 08:17'
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
- [ ] #1 Exact stream selector, datasource and field names of audit events recorded from at least one stack with audit logging enabled, or a recorded negative with the stacks checked
- [ ] #2 Whether a field identifies the app/plugin behind a query is answered with evidence, and the join to usage-insights data-request events is described
- [ ] #3 Opt-in coverage, reader-scope requirements and privacy handling for identity-bearing audit fields are stated, with a follow-up task if a collector source is viable
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
