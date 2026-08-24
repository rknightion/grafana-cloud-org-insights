---
id: GCI-0005
title: Run a clean-room zero-to-live operator walkthrough
status: To Do
assignee: []
created_date: '2026-08-24 12:02'
labels: []
dependencies: []
references:
  - >-
    backlog/docs/doc-0003 -
    Consumer-manifest-provenance-and-immutable-upgrade-contract.md
  - backlog/docs/doc-0004 - Deployment-and-rollback-safety-model.md
priority: medium
type: task
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Prove a new operator can start with only this product repository and a deployment repository, create a valid consumer manifest, build and validate an immutable candidate, and reach the live-change approval gate without relying on an engagement workspace or undocumented local state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Walkthrough starts from fresh clones and empty Terraform plugin/state directories
- [ ] #2 Every required credential and private-repository assumption is documented without storing secrets
- [ ] #3 The operator reaches a reviewed candidate plan and rollback package without live mutation
- [ ] #4 Every missing instruction found during the walkthrough is fixed in durable product or deployment documentation
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
