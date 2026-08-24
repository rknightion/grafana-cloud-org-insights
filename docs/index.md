# grafana-cloud-org-insights

Estate-wide insight for a large Grafana Cloud organisation. A collector scans every stack in the org on a schedule, transforms what it finds, and publishes it as ordinary Grafana dashboards on one stack you nominate.

It exists because past a couple of dozen stacks nobody can answer simple questions any more. Which stacks cost the most and why. Who has admin on what. What is provisioned and never used. Which stacks are on last quarter's build. Answering those by hand, stack by stack, is a day's work that goes stale the moment it finishes.

Two audiences, two cadences. A platform team reads it weekly and wants to know who is struggling, who is over-alerting and who needs help. Leadership reads it quarterly and wants to know whether the spend is defensible and whether adoption is growing.

## What it is not

- **Not a replacement for showback.** If your org already emails per-owner cost reports, this answers "which lever moves that number", not "what did it cost".
- **Not an agent on your stacks.** Nothing is installed anywhere. The collector runs in your AWS account and talks to `grafana.com` and to each stack's own API over HTTPS.
- **Not a write path.** The scanning credential is read-only by scope, and the collector's HTTP client refuses any method other than GET. Publishing uses a second credential whose realm is a single stack.

## How it works

Four scheduled scan tiers plus a provisioner, all ECS Fargate tasks on EventBridge schedules.

| Tier | Cadence | Gathers |
|---|---|---|
| T1 | hourly | org inventory, access policies, org members and Fleet Management |
| T2 | daily | per-stack users, plugins, service accounts, Assistant, dashboard usage, public dashboards and alert routing |
| T3 | every 6h | the data plane: cardinality and Adaptive Metrics rules and recommendations |
| T4 | daily | the estate diff, over two windows: 7 days and 1 day |
| provisioner | daily | reconciles one read-only service account per stack |

Results land in three places, each chosen for what it is good at. Mimir takes bounded metrics for trends and alerting. Loki takes the finding detail, including the offender names a metric label must never carry. S3 takes pre-shaped tables the dashboards render directly, plus a raw scan archive for the diff and for audit.

[Architecture](architecture.md) covers the tiers, hydration and the cardinality rule in full.

## Ten dashboards

`estate`, `cost`, `usage`, `maturity`, `risk`, `value`, `operations`, `commercial`, `ai`, `dashboards`.

Two of them — `operations` and `commercial` — are panels only. They read `grafanacloud-usage`, a Prometheus datasource already provisioned on every Grafana Cloud stack, so they need no collector code, no credential and no series at all.

That is the general rule this project keeps relearning: if the data is already a datasource on the target stack, a panel beats a pipeline. The collector is for what no datasource exposes.

See [Dashboards and alerts](dashboards.md) for what each surface answers and how to publish them.

## Start here

- [Getting started](getting-started.md) — run a scan against your own org and build the dashboards from a synthetic fixture.
- [Credentials and permissions](credentials.md) — every identity, what it reaches, and what it is deliberately refused.
- [Deployment](deployment.md) — the Terraform module, the signed container image, and how a customer deployment pins it.
- [Operations](operations.md) — manual scans, the provisioner, rotation, rollback and teardown.

## Licence

Apache 2.0.
