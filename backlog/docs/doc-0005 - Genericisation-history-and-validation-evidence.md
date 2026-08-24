---
id: doc-0005
title: Genericisation history and validation evidence
type: other
created_date: '2026-08-24 12:02'
updated_date: '2026-08-24 13:13'
---
# Genericisation history and validation evidence

## Migration result

The independent customer fork was retired in favor of one canonical product implementation plus a non-secret deployment manifest. Reusable collector, dashboard, alert, container, test, and Terraform logic now lives only in this repository. The deployment consumes the Terraform module at a full Git commit and carries customer configuration outside the product repository.

The migration preserved the externally visible contract while deliberately changing ownership and provenance. Internal environment and metric identities are generic; consumer-specific public namespaces and object identities remain overlay configuration. The image contains product source only, while the runtime receives narrow environment projections from deployment infrastructure.

## Exact validated baseline

At generic revision `09c30b35db1d7a10355145542c6cdeeecbdb2a24`, the completed migration validation recorded:

- complete suite: 1,318 passed, 2 skipped, 6,570 subtests passed;
- identity, label, budget, fixture, and service-account hygiene: 68 passed, 5,980 subtests passed;
- customer-identifier denylist: clean;
- contract inventory: 152 catalogue entries, 121 Mimir metrics, 58 views, 10 dashboards, 7 alerts, and 27 permission pairs;
- exact legacy-fork parity for metric definitions, composed labels, view schemas, dashboards, alerts, permissions, input ownership, schedules, and rate-card dimensions;
- reusable module, standalone example, and deployment-root OpenTofu validation: successful;
- generic source tree and downloaded module tree: byte-identical at `4e8257e4f6e3403146278b6dc88012bcb2bca5e8a02aca3c7410317d48807e55`; and
- automated pre-push review: no findings.

This is historical evidence. Repeat all gates at the selected candidate revisions and compare their command output before deployment.

## Final containing revision

Product revision `8020bbfe0058ed1f5defd0c217f3069b88d1b0ec` contains the reviewed implementation and produced:

- complete suite: 1,333 passed, 2 skipped, 6,570 subtests passed in 67.67 seconds;
- reusable module and standalone example initialization and validation in fresh data directories: successful;
- recursive Terraform formatting: clean;
- customer-identifier denylist and shipped-text gate: clean;
- consumer manifest, immutable-ref, deterministic-digest and replacement-core tests: included in the complete suite; and
- deployment-consumer check against the exact pin and a byte-identical downloaded module tree: successful.

The later Backlog-only completion commit does not change product, test, container or Terraform files. Repeat the full gate at any future product pin.

## Intentional structural differences

- There is no independently editable customer copy of product code or reusable Terraform.
- The deployment manifest, not an engagement workspace, is the customer configuration authority.
- Images are built from a pristine generic tree and record both source revisions plus the overlay digest.
- Terraform consumes the reusable module at a full commit instead of a synchronized vendor directory.
- Collector and provisioner schedules can be gated independently without changing their established default state.
- Alert operator prose and generated documentation use generic credential and write-target terminology.

No metric label, view schema, dashboard identity, alert identity or expression, permission pair, tier owner, schedule, hydration contract, rate-card dimension, or limited-publication guard was intentionally changed by the structural migration.

## Evidence that is deliberately not durable truth

Live task-definition revisions, image digests, schedule states, estate counts, output timestamps, policy metadata, and registry lifecycle conditions drift. Capture them read-only immediately before an approved deployment. Never copy a dated live value from this document into a plan without re-verification.
