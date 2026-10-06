---
id: GCI-0103
title: 'Use or drop the unused rules:read and alerts:read reader scopes'
status: To Do
assignee: []
created_date: '2026-10-06 10:23'
labels:
  - owner-decision
  - security
dependencies: []
priority: medium
type: task
ordinal: 119000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment: config.py:86-87 declare rules:read and alerts:read but no source calls them (CAPABILITIES.md:26-27); they reach raw Alertmanager config with secrets and full firing label sets. Least privilege says drop them unless a bounded count needs them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner decision recorded: drop, or name the bounded count route that keeps them
- [ ] #2 If dropped, the provisioner removes only recorded pairs and a staff readback shows the reduced role
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
