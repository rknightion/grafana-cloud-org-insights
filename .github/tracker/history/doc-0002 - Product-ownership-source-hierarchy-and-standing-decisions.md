---
id: doc-0002
title: 'Product ownership, source hierarchy, and standing decisions'
type: specification
created_date: '2026-08-24 12:02'
updated_date: '2026-10-07 01:21'
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
- Declared reader scopes are documented by what the scope permits, not only by the routes this collector currently calls. Where a scope is materially wider than its use, the breadth is retained deliberately and the reason is recorded beside it.
- `logs:read` is a full Loki read scope and reaches log content. It is retained deliberately: the label inventory requires it, there is no narrower Grafana Cloud scope that reaches label names and values, and planned log analytics will require it outright. The collector's restraint is that its code calls Loki label-name and label-value, `/series`, `index/stats`, `index/volume` and limits/config endpoints only, never `query`, `query_range`, `tail` or any route returning log lines; each requires a recorded staff witness, which is an implementation property enforced by review, not a property of the credential. Deployments run only against organisations that have explicitly consented to that access.

## Repository hierarchy

When sources disagree, safety and authority come first:

1. `AGENTS.md` and explicitly approved standing contracts define the safety, ownership, and authorization boundaries. Changing one requires an explicit decision, even when current behavior differs.
2. `SPEC.md`, `RUNBOOK.md`, `CAPABILITIES.md`, `BUDGET.md`, and `docs/traps.md` define the current product contract.
3. Current code, tests, and generated contracts describe observed implementation behavior and provide evidence that it satisfies those contracts.
4. Backlog tasks and documents preserve decisions, history, and open product work.
5. A consumer deployment manifest and its infrastructure wiring own customer policy within the generic product boundary.
6. Historical migration evidence is supporting context only.

Historical status is evidence, not present-tense truth. Re-query live state before deployment decisions.


## Labelling owner decisions (2026-10-06)


- **D-LBL1 Retention.**
  - `label_inventory` may persist the following in S3 views and the private `label_inventory` hydration input only:
    - label and attribute NAMES;
    - distinct-value counts (`exact` or `at_least`);
    - closed non-PII value-shape class counts (uuid, hex_id, epoch, url_with_id, long_value);
    - series and stream counts.
  - These items never go to Loki, finding events, metric labels, stdout, `--out` or errors.
  - A name over 512 bytes, or one matching a `pii` key or value class, persists only as a class and a count.
  - Raw values are transient and never written. The GCI-0018 raw-value exception is not widened.
- **D-LBL2 Deterministic only.** No LLM in the scanner or operator tooling. Judgement rules are catalogued and excluded from applicable weight.
- **D-LBL3 Layered, tunable thresholds.**
  - Published limits are hard rules.
  - The Professional Services bands are the defaults: metrics warn at 100, high at 1,000, critical at 10,000; Loki dynamic labels warn at 100+.
  - Everything else is policy.
  - Each threshold carries a provenance tag (`published`, `ps` or `policy`) and a source URL, and is overridable through the tunables.
- **D-LBL4 Presentation.**
  - Per stack and signal: findings by severity, rules evaluated vs passed, a 0-100 score, and the coverage figure.
  - The score is computed only at coverage of 0.8 or more; otherwise it is absent.
- **D-LBL5 Maturity.** The labelling score replaces `cardinality_discipline`. This waits for the dev proof.
- **D-LBL6 Routes.** Staff witnesses are approved for:
  - Mimir `cardinality/label_values` and `label_names` (limit/selector);
  - Loki `/series`, `index/stats` and `index/volume`;
  - Loki applied limits/OTLP config;
  - Tempo intrinsic `name` values and Tempo overrides.

  Each route is implemented only after its witness. A parked route's rules are excluded from applicable weight.
- **D-LBL7 Customer grant.** The customer deployment may enable `label-inventory` once it ships in a release and the task K dev proof is recorded. No further owner decision is needed. Routes without a passing witness are not covered. Every reader-role, route, privacy and publication rule is preserved.
- **D-LBL8 Fairness.**
  - Cardinality bands apply only to metrics and streams above a size floor (tunable, same pattern as `CARDINALITY_MIN_SERIES`).
  - A static-infrastructure allowlist (host, cluster, namespace, node and similar) has its own higher band.
- **D-LBL9 PII shapes.** Email, ip, phone, jwt and card shapes stay on label_risk's retention-governed path. The labelling register refers to `risk_label_hygiene` and does not duplicate them.
- **D-LBL10 Witness stacks.** Witnesses may query all five staff stacks and choose or combine evidence. Each recorded witness names the stack slug.
- **D-LBL11 Pre-approved read scopes.** When a witness shows the org reader lacks a READ scope for an approved route, the witness task may add that read-only scope to this project's own access policy.
  - The addition is recorded with its object ID, and CAPABILITIES.md is updated.
  - Write or admin scopes, other policies and the per-stack reader role are never covered.
  - A new scope can 401 for about 46 minutes; wait it out, never re-mint.


### Loop14 read-scope execution boundary (2026-10-07)

D-LBL11 is conditional on a witness showing a missing READ scope for a D-LBL6 route. Only the root may add that single scope to this project's own policy after a fresh policy witness, record its object ID and read back. Never write or admin scopes, another policy or the per-stack role; wait out propagation and never re-mint. D-LBL7 remains conditional on a shipped release and recorded dev proof; loop14 does not enable label-inventory on the customer deployment.
