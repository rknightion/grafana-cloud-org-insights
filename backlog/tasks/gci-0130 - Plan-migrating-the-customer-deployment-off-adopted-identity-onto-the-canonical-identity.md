---
id: GCI-0130
title: >-
  Plan migrating the customer deployment off adopted identity onto the canonical
  identity
status: To Do
assignee: []
created_date: '2026-10-08 18:57'
labels:
  - consumer
  - handover
  - owner-decision
dependencies: []
priority: medium
ordinal: 167000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decision 2026-10-08 (Rob): plan a full migration before handover. Adopted identity still in the customer consumer: metric prefix, Loki job, Grafana reader role name/display/group (present on every stack), reader/admin service-account and token names containing the lab owner token, SSM per-stack token path, the three custom secret key names, adopted alert rule uids/group and folder. Each move has live cost: series history split under a new metric prefix (carry-forward cannot rescue), new roles and reassignment on every stack with the old role orphaned unless pruned by recorded id, re-mint of every per-stack token (a repair must not re-mint a working credential, so this needs its own explicit owner grant), alert routing re-established. Planning only: produce an ordered, reversible-by-fix-forward plan with per-step live witnesses and owner grants; no live change under this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Plan document lists each adopted identity item, its migration step, live blast radius, required owner grant and witness
- [ ] #2 Plan reviewed adversarially and corrected
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
