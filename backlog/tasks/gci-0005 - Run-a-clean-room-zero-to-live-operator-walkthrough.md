---
id: GCI-0005
title: Run a clean-room zero-to-live operator walkthrough
status: To Do
assignee: []
created_date: '2026-08-24 12:02'
updated_date: '2026-08-25 08:28'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
A real zero-to-live run happened on 2026-08-25 - a second deployment stood up beside an existing one in the same AWS account, scanning a different Grafana organisation and publishing to a different stack. It went past this task deliberate stopping point (it applied, ran and went live), so it does not close AC #3, but it does supply the evidence AC #4 asks for.

What was missing or wrong, all now fixed in durable documentation:

1. **The bring-up order in RUNBOOK and `docs/deployment.md` was WRONG.** Both listed the manual tier runs before the provisioner. T2 cannot pass before the provisioner has minted per-stack readers into SSM - every stack-local source returns `no_credential`, coverage is 0.0, and T2 exits 1 refusing all writes. It reads like a broken reader token and is not one. RUNBOOK now runs the provisioner first, with the symptom spelled out.
2. **Nothing documented which REGION an access policy is created in.** Realm decides it: an org-realm policy belongs to the organisation own region, which is not necessarily where its stacks are; a stack-realm policy belongs to the stack `regionSlug`. Getting it wrong does not fail at creation - it fails later as a 404. `docs/credentials.md` now has this, including that the only reliable way to discover the org region is to list existing policies.
3. **Nothing documented that the insights folder must exist BEFORE a dashboard build**, that the dashboard builder resolves it by TITLE while the alert builder addresses it by UID, or that stack API calls need a Grafana service-account token rather than a cloud access-policy token. RUNBOOK phase 2 now covers all three, including creating and deleting a short-lived Admin service account through the grafana.com stack proxy.
4. **The Infinity datasource configuration was not written down anywhere.** RUNBOOK phase 8 now carries the exact `auth_method: aws` / `service: s3` payload and the health check that proves it.
5. **`bin/check-customer-identifiers` hard-fails with exit 2 when `GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN` is unset**, and the value exists only as a CI secret. A new operator therefore cannot validate ANY consumer manifest locally. This is AC #2 territory and is not yet solved in this repository - the pattern is genuinely customer context and must not be committed here, but the failure mode needs to be stated where an operator meets it rather than discovered as an exit 2.

Two product defects the walkthrough surfaced are tracked separately: GCI-0010 (Firehose subscription unusable for a new deployment) and the empty-view dashboard build failure on a small estate.

The strongest single finding for this task: every one of these is invisible to an established deployment. Ordering only matters once, a region is only chosen once, a folder only created once, and a subscription filter trust condition is only evaluated once. An existing healthy deployment is not evidence that any of it works.
<!-- SECTION:NOTES:END -->
