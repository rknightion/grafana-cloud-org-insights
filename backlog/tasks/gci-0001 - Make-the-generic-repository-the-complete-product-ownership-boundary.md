---
id: GCI-0001
title: Make the generic repository the complete product ownership boundary
status: Done
assignee:
  - '@codex'
created_date: '2026-08-24 11:58'
updated_date: '2026-08-24 13:13'
labels: []
dependencies: []
priority: high
type: enhancement
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Move all reusable consumer tooling, schemas, architecture and operating context into this private generic repository; leave customer identifiers and deployment values only in the deployment repository; establish the standard Backlog board so the former engagement workspace is no longer required for product maintenance.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The generic repository contains every reusable script and schema needed to validate, build and upgrade a pinned consumer
- [x] #2 The deployment repository is authoritative for its customer overlay and records immutable generic, overlay and image identities
- [x] #3 The generic identifier denylist remains clean and no customer identity is introduced
- [x] #4 Backlog documents and tasks preserve the product decisions, migration evidence, open risks and repeatable operating model
- [x] #5 The former engagement workspace is no longer an input to build, validation, upgrade or rollback procedures
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Inventory the remaining engagement-owned consumer artifacts and classify each as reusable product tooling, deployment-specific configuration, migration-only evidence or obsolete history.
2. Initialize the standard Backlog documents/tasks and register the canonical fan-out document through agent-docs without introducing customer identifiers.
3. Move and genericize reusable consumer validation/build/upgrade tooling into this repository with tests; make the deployment repository own its overlay and provenance.
4. Rewrite upgrade, deployment and rollback instructions so neither repository reads the former engagement workspace.
5. Re-run full product, denylist, consumer, image-provenance and isolated OpenTofu gates; adversarially review permissions, schedules, credentials and destructive actions.
6. Commit and push each owner repository independently, preserving unrelated work, then establish the exact live-deployment plan and stop before any live mutation unless separately approved.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Artifact classification complete: reusable schema, validation, build, exec, upgrade, architecture and rollback guidance belong here; the deployment manifest and customer values belong in the deployment repository; legacy-fork parity is migration-only evidence.

Initialized the fleet Backlog board, populated four durable product documents and six historical/open tasks, registered doc-0001 with agent-docs, rendered the canonical fan-out document, and added the repository to the OpenBao read-token permission set.

Implemented reusable manifest validation, deterministic digest regeneration, immutable source/Terraform upgrade, local-only provenance build, projected execution tooling, schema, architecture/runbook, and focused tests. Targeted tests pass: 21 passed.

CodeRabbit raised five Major issues. Fixed remote commit reachability, authority hierarchy, and unexpected-provisioner-write wording. Dismissed two findings against generated doc-0001 because its agent-docs source is outside this migration and consumer copies must not be edited.

Second CodeRabbit pass raised six in-scope Major issues and four generated-doc issues. Fixed identity-storage controls, symbolic cardinality guidance, executable identifier/core-drift checks, atomic two-file upgrade rollback, deterministic upgrade tests, and controlled end-to-end build/exec tests. Generated fan-out findings remain source-owned outside this task.

Final generic gate: 1,331 passed, 2 skipped, 6,570 subtests in 65.30s. Fresh module and standalone OpenTofu init/validate succeeded. Formatting, identifier denylist, and shipped-text gates are clean.

Superseding the earlier test total after review fixes: the final pre-commit candidate suite is 1,333 passed, 2 skipped, 6,570 subtests in 67.67s. The containing revision will be recorded after commit.

Deployment ownership proof: the deployment repository's canonical manifest validates against product revision 8020bbfe0058ed1f5defd0c217f3069b88d1b0ec with unchanged deterministic overlay digest; its Terraform ref matches, downloaded module tree is byte-identical excluding local init artifacts, and its deployment-owned consumer check rejects former-workspace dependencies and replacement core.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Established the generic repository as the sole editable product source with tested immutable consumer tooling, provenance, reusable Terraform, durable Backlog context and customer-identifier gates. A deployment repository now owns its canonical overlay and rollback contract, consumes one full Git ref, and validates without the former engagement workspace. Final product suite: 1,333 passed, 2 skipped, 6,570 subtests; both fresh Terraform configurations and identifier/shipped-text gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
