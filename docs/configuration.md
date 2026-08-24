# Configuration

Everything is supplied through the process environment. **No deployment identifier is defaulted.** A default org id or tenant would be one deployment's identifiers baked into everyone else's collector, and the failure is silent rather than loud: the scan authenticates, succeeds, and writes a plausible set of series into somebody else's tenant.

## Required

| Variable | Meaning |
|---|---|
| `GCINSIGHT_ORG_ID` | the org to scan |
| `GCINSIGHT_WRITE_STACK` | the one stack results are published to |
| `GCINSIGHT_MIMIR_URL` | `https://prometheus-prod-NN-<region>.grafana.net` |
| `GCINSIGHT_MIMIR_TENANT` | the write stack's `hmInstancePromId` |
| `GCINSIGHT_LOKI_URL` | `https://logs-prod-NNN.grafana.net` |
| `GCINSIGHT_LOKI_TENANT` | the write stack's `hlInstanceId` |
| `GCINSIGHT_S3_BUCKET` | the deployment bucket |

## Credentials

| Variable | Read by | Realm |
|---|---|---|
| `GCINSIGHT_READ_TOKEN` | collector | org |
| `GCINSIGHT_WRITE_TOKEN` | collector | the write stack alone |
| provision token | provisioner only | org |
| `GCINSIGHT_STACK_TOKEN_PREFIX` | collector | SSM path holding per-stack reader tokens |

`GCINSIGHT_WRITE_TOKEN` falls back to the read token when unset, so a single-credential interactive run works. A deployment sets both. Per-stack reader tokens are SSM `SecureString` values below the configured prefix. The provisioner alone reads the provision token; the collector never receives it.

In a deployed setup the Secrets Manager object must contain separate read, write and provisioner token keys before any schedule is enabled.

## Dashboard build

Build-time Grafana credentials are separate from runtime credentials and should be short-lived. The build token is not a runtime secret.

| Variable | Meaning |
|---|---|
| `GCINSIGHT_VIEWS_DIR` | read views from a local directory instead of S3 |
| `GCINSIGHT_WRITE_STACK_URL` | `https://<slug>.grafana.net` |
| `GCINSIGHT_WRITE_STACK_ID` | numeric stack id |
| `GCINSIGHT_GRAFANA_TOKEN` | short-lived build token |

The builder resolves the insights folder by title.

## The rate card

Optional, and read from `config/ratecard.csv` in the deployment bucket by the task role. Absence means volume-only panels, which is a supported state rather than a degraded one.

`ratecard.example.csv` in the repository is the format reference.

Ten dimensions can be priced. `price()` returns `None`, never `0.0`, when a dimension is not priced - an unpriced dimension must read as unknown, not free. A deployment may price only some dimensions, but the UI discloses which components are omitted and must not present the subtotal as a complete estate total.

Configuration errors, all rejected rather than coerced:

- mixed currencies;
- duplicate dimensions;
- unsupported units;
- non-positive prices.

Currency and billing period come from the card. Metrics-series pricing is per 1,000 series where declared, and metrics support two explicit bases:

- `base_rate_only` excludes DPM;
- `dpm_aware` applies `max(active_series, total_dpm / included_dpm)` per stack, using live usage inputs and a dedicated dashboard calculation. It never falls back to the two-input base-series saving.

## Optional Firehose logs

The collector writes its own structured Loki records, but it cannot report an image-pull failure, bootstrap error, early traceback or OOM kill - by the time any of those happen there is no collector to do the writing. The optional Firehose path forwards ECS CloudWatch logs to Loki and is **off by default**.

Enable it in three stages, in this order:

1. set `firehose_logs_enabled=true` with a dedicated adopted secret containing `{"api_key":"<loki-tenant>:<logs-write-token>"}`;
2. send a deliberate test record and verify it lands in Loki, and that the failed-record S3 path works;
3. only then set `firehose_log_subscription_enabled=true`.

The subscription switch cannot stand alone. Failed deliveries have their own encrypted, lifecycle-bound bucket.

## Optional panel plugins

The shipped dashboards need no third-party panel plugins. If you adopt panels that use them, these are the minimum versions verified as Grafana 13.3 compatible from their installed manifests:

| Plugin ID | Minimum verified version |
|---|---:|
| `volkovlabs-echarts-panel` | 7.2.5 |
| `volkovlabs-table-panel` | 3.6.5 |
| `volkovlabs-variable-panel` | 5.2.0 |
| `marcusolsson-treemap-panel` | 2.1.1 |

They remain optional unless an adopted panel requires one of them.
