# Build state

Working notes for the generic distribution. Delete this file when the remaining deployment-level
unknowns are resolved.

## Current code state

The generic repository contains the accepted collector, dashboard and infrastructure capabilities from
the production-derived implementation while retaining generic deployment boundaries:

- `GCINSIGHT_*` configuration, `gcinsight_` metrics, generic stable dashboard and alert uids.
- No default org, stack, tenant, folder, bucket, Grafana context or container registry.
- Synthetic committed fixtures and generated views; live fixture exports cannot overwrite them.
- A stdlib-only collector and an ARM64 Fargate image.
- Ten dashboards, including Pillar J dashboard usage.
- A basic-role-None per-stack reader with a custom read-only role, uid-scoped usage-insights query
  permission, daily reconciliation, and path-scoped SSM storage.
- Adaptive Metrics verbose recommendation arithmetic, Adaptive Logs collection, an optional rate card,
  public-dashboard enumeration, service-account inventory, alert-routing inventory, org members and
  Fleet Management pipeline reach.
- Cross-tier hydration for every optional input; an unsatisfied view is withheld rather than published
  as zero.
- A 100,000-series runaway ceiling with the bounded-label guard unchanged.
- UID-keyed alert publication and the one-time title migration path.
- Optional, default-off CloudWatch Logs delivery through AWS Data Firehose.
- Coverage gates for every published view and every emitted metric, plus synthetic-identifier hygiene.

## Genericisation contract

The public tree must contain no customer names, stack slugs, org or tenant ids, AWS account ids, folder
or datasource uids, named individuals, customer metric prefixes, or live tokens. Configuration raises
instead of guessing. `GCINSIGHT_STAFF_LOGINS` is empty by default. Shipped examples use unmistakable
placeholders. The externally configured CI identifier gate, fixture namespace tests and em-dash check
enforce these boundaries without publishing the sensitive pattern set.

## Still unproven here

1. Nothing has been deployed from this repository. Terraform validation proves syntax and internal
   contracts, not a successful installation in another organisation.
2. The README has the component-level path, but no single worked zero-to-live walkthrough has been
   exercised by a new operator.
3. Hosted CI availability depends on the repository owner's Actions billing state. Local gates remain
   the release authority until a hosted run actually starts and passes.

## Standing decisions

- Deployment identifiers and build targets are always explicit.
- The collector stays stdlib-only.
- Per-stack identity remains in S3/Loki when the deploying organisation has approved that policy, but
  identity never becomes a metric label.
- Public-dashboard inventory is compared with the deploying organisation's policy; the generic
  dashboards do not assume a zero-tolerance target.
- Currency appears only for rate-card dimensions that can be priced. Missing or partial pricing is
  disclosed and never represented as a zero total.
- The collector never receives the provisioner's org-wide service-account write credential.
