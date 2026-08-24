---
id: GCI-0007
title: Retire transitional repository state documentation
status: To Do
assignee: []
created_date: '2026-08-24 12:02'
labels: []
dependencies: []
references:
  - STATE.md
  - >-
    backlog/docs/doc-0002 -
    Product-ownership-source-hierarchy-and-standing-decisions.md
priority: low
type: docs
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Remove STATE.md after every remaining deployment unknown has either been resolved into current product documentation, moved to the owning deployment repository, or recorded as an explicit Backlog task. Do not delete it while it is the only source for an unresolved contract.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No current operational instruction exists only in STATE.md
- [ ] #2 Deployment-specific state is owned by the deployment repository
- [ ] #3 Open product work is represented by Backlog tasks
- [ ] #4 STATE.md is removed and all documentation links remain valid
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
