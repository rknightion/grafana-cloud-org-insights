---
id: doc-0002
title: 'Product ownership, source hierarchy, and standing decisions'
type: specification
created_date: '2026-08-24 12:02'
updated_date: '2026-08-24 12:18'
---
# Product ownership, source hierarchy, and standing decisions

## Ownership boundary

This repository is the only editable implementation of Grafana Cloud Org Insights. Product logic, collector sources, dashboard and alert builders, reusable Terraform, schemas, tests, container build inputs, and generic operating documentation are maintained here first.

A deployment repository is a consumer. It owns customer-specific identifiers, schedules, cloud resource names, adopted-resource choices, policy identities, rate-card selection, datasource and folder identities, secret selectors, an immutable generic source revision, an overlay digest, and the deployed image digest. Credentials and customer data never belong here.

An engagement workspace, migration checkout, or historical fork is not an input to build, test, upgrade, rollback, or deployment. Migration-only parity artifacts may be retained as durable evidence, but they do not become an editable second implementation.

## One-way source relationship

The source flow is one way:

1. Review and commit product changes here.
2. Select a full 40-character Git commit for a consumer.
3. Validate the consumer manifest against the source contract at that commit.
4. Build a pristine image from this repository and label it with the generic revision, deployment revision, and overlay digest.
5. Consume the Terraform module from the same full Git commit.
6. Pin the resulting image by registry digest before deployment.

No command copies product files into a consumer. A consumer may contain adapters only when they represent a legitimate deployment boundary and are explicitly justified; reusable behavior moves here.

## Standing product contracts

- Estate membership is discovered on every run. Stack or region inventories are not customer configuration.
- The collector HTTP client remains read-only by construction.
- Runtime configuration uses `GCINSIGHT_*`; Terraform inputs use `gcinsight_*` or generic module variables.
- Metric labels remain bounded and exclude people, dashboards, rules, service-account identities, and other customer identity.
- Every emitted metric is catalogued and every view and metric has a dashboard or alert consumer.
- A missing input is absent or withheld, never represented as a confident zero.
- Every tier composes from the full hydrated input contract while never hydrating its own failed input.
- Limited runs cannot publish.
- Provisioning and collector execution remain separate identities and schedules.
- Alert publication preserves live routing and pause state; new alerts start paused and unrouted.
- Contracted prices are deployment data. The generic product contains only the rate-card schema and semantics.

## Repository hierarchy

When sources disagree, safety and authority come first:

1. `AGENTS.md` and explicitly approved standing contracts define the safety, ownership, and authorization boundaries. Changing one requires an explicit decision, even when current behavior differs.
2. `SPEC.md`, `RUNBOOK.md`, `CAPABILITIES.md`, `BUDGET.md`, and `docs/traps.md` define the current product contract.
3. Current code, tests, and generated contracts describe observed implementation behavior and provide evidence that it satisfies those contracts.
4. Backlog tasks and documents preserve decisions, history, and open product work.
5. A consumer deployment manifest and its infrastructure wiring own customer policy within the generic product boundary.
6. Historical migration evidence is supporting context only.

Historical status is evidence, not present-tense truth. Re-query live state before deployment decisions.
