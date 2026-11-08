---
id: doc-0004
title: Deployment and rollback safety model
type: guide
created_date: '2026-08-24 12:02'
updated_date: '2026-08-24 12:18'
---
# Deployment and rollback safety model

## Authority boundary

Product validation, local image builds, read-only cloud inspection, Terraform validation, and Terraform planning are preparation. The following are live mutations and require separate approval: registry push or tag movement, task-definition registration, schedule state changes, Terraform apply, live collector or provisioner execution, dashboard or alert publication, token or role changes, and object-store writes.

## Pre-deployment stopping conditions

Stop before deployment unless every item is true:

- the product and deployment repositories are clean, committed, and pushed;
- the manifest uses a full generic commit and the Terraform module uses the same ref;
- a candidate image exists by immutable registry digest and its labels match the committed generic and deployment revisions plus overlay digest;
- the currently deployed task definitions, image digest, schedule states, schedule targets, and tag propagation have been captured read-only;
- both candidate and rollback image digests are protected from lifecycle expiry for the approved rollback window;
- the saved Terraform plan contains only classified actions and is still valid for the exact source, manifest, variables, and external state;
- no adopted storage, secret, reader, IAM policy, schedule, or data resource is destroyed or replaced;
- permissions, secret selectors, schedules, architecture, image, and deployment defaults have received a final diff review;
- catalogue, views, dashboards, alerts, labels, hydration, tier, rate-card, and limited-publication contracts have no unexplained difference; and
- the customer has approved the maintenance sequence and rollback window.

Hosted CI failure caused solely by account billing is recorded as unavailable evidence, not treated as a code failure and not fixed by changing billing.

## Controlled go-live

Use saved, reviewed plans. If schedule pausing is approved, pause through infrastructure configuration rather than deleting schedules. Confirm no task or lock is active. Deploy collector task definitions with the provisioner independently disabled, then inspect the rendered definitions and effective runtime identity before executing anything.

Run collector tiers serially in dependency order using deployed task definitions and task-definition tag propagation. Verify both a log stream and the corresponding scan envelope for every tier. Treat a lock collision as a collision, not a product failure. Enable collector schedules only after output comparison passes. Enable the write-capable provisioner last, after its dry-run shows no unexpected create, patch, mint, or prune action.

Stop immediately on an unexpected Terraform action, generic-named customer object, missing envelope, runtime-digest mismatch, permission widening, secret-selector change, unexplained output difference, or unexpected provisioner write. An explicitly approved reconciliation or repair window may perform the reviewed writes predicted by its clean dry run; any additional write is a stop condition.

## Rollback

Rollback restores the pre-recorded generic module ref, deployment revision, image digest, task definitions, scheduler targets, schedule states, and provisioner gate. It does not delete or overwrite object-store data automatically.

After rollback, verify rendered task definitions, image resolution, every schedule target and state, and tag propagation. If a bad candidate wrote scan, carry, or view state, preserve evidence and assess those objects separately. Source rollback and data recovery are different operations.
