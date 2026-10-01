---
id: GCI-0057
title: Audit and refresh operator documentation across the product
status: To Do
assignee: []
created_date: '2026-10-01 09:58'
labels:
  - documentation
  - operations
dependencies: []
references:
  - README.md
  - RUNBOOK.md
  - docs/configuration.md
  - terraform/variables.tf
  - consumer/MIGRATION-RUNBOOK.md
priority: medium
type: docs
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner requested a dedicated documentation freshness audit during loop5 on 2026-10-01 after asking which scan tier is hourly versus six-hourly and requesting a complete scheduled-job timetable. Tier cadence exists in README but operator references need to agree with current code, CLI and deployment contracts. Review documentation across the product, including stale historical limitations and command examples, without publishing deployment identifiers. This is future work, not a new implementation lane in the ongoing rollout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 README, RUNBOOK, SPEC, configuration, infrastructure and consumer upgrade/rollback documentation are checked against current supported behavior; every discrepancy is corrected or explicitly tracked
- [ ] #2 All five scheduled jobs have a consistent purpose, cadence and timezone-aware schedule explanation, clearly distinguishing module defaults from deployment-specific overrides
- [ ] #3 Operator command examples and publication/credential/privacy/rollback constraints match current CLI contracts and named authority gates
- [ ] #4 Documentation changes contain no customer identifiers and pass proportionate documentation/text/link validation, with exact evidence and remaining gaps recorded
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
