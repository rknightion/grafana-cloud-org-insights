# grafana-cloud-org-insights

Estate-wide insight for a large Grafana Cloud organisation. A collector scans every stack in the org on a schedule, transforms what it finds, and publishes it as ordinary Grafana dashboards on one stack you nominate.

It exists because past a couple of dozen stacks nobody can answer simple questions any more. Which stacks cost the most and why. Who has admin on what. What is provisioned but has no observed use in the measured window. Which stacks are on last quarter's build. Answering those by hand, stack by stack, is a day's work that goes stale the moment it finishes.

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
| T2 | daily | per-stack users, plugins, service accounts, Assistant, usage insights, public dashboards, alert routing, Loki retention, signal labels and capability adoption |
| T3 | every 6h | the data plane: cardinality and Adaptive Metrics rules and recommendations |
| T4 | daily | the estate diff, over two windows: 7 days and 1 day |
| provisioner | daily | reconciles one read-only service account per stack |

Results land in three places, each chosen for what it is good at. Mimir takes bounded metrics for trends and alerting. Loki takes finding detail; identity-bearing fields require deployment acceptance and privacy controls and never become metric labels. S3 takes pre-shaped tables the dashboards render directly, plus a raw scan archive for the diff and for audit.

[Architecture](architecture.md) covers the tiers, hydration and the cardinality rule in full.

## What you can observe

Eleven dashboards cover inventory, cost, usage, maturity, risk, value, operations, commercial
consumption, AI usage, dashboard usage and observed coverage. [The dashboard guide](dashboards.md)
lists each panel group, its source, window, caveats and screenshot. Use it to tell configured state,
telemetry production and recorded human activity apart.

The collector discovers the live estate on every run. Scan-fed dashboards include measured-population
and input-age context. Operations and Commercial read `grafanacloud-usage` directly;
AI usage and Coverage mix live billing panels with collector output. Live billing panels are not
filtered by the Stack selector.

### What it cannot see

A provisioned datasource, plugin or capability does not prove a person used it. Usage insights sees
dashboard opens and panel data requests, but a page visit without a query is invisible, and the
`scenes` request bucket cannot identify individual apps. A missing series can mean an unavailable
reader or stale input rather than zero use. See [Dashboard usage](dashboards.md#dashboard-usage)
and the [interpretation guide](dashboards.md) before quoting an adoption figure.

## Start here

- [Getting started](getting-started.md) - run a scan against your own org and build the dashboards from a synthetic fixture.
- [Credentials and permissions](credentials.md) - every identity, what it reaches, and what it is deliberately refused.
- [Deployment](deployment.md) - the Terraform module, the signed container image, and how a customer deployment pins it.
- [Operations](operations.md) - manual scans, the provisioner, rotation, rollback and teardown.

## Licence

Apache 2.0.
