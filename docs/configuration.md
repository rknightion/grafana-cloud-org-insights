# Configuration

Everything is supplied through the process environment. **No deployment identifier is defaulted.** A default org id or tenant would be one deployment's identifiers baked into everyone else's collector, and the failure is silent rather than loud: the scan authenticates, succeeds, and writes a plausible set of series into somebody else's tenant.

## Required scan configuration

`collector.config.load()` requires the org, write stack, both endpoints and both tenants even with
`--dry-run`. The bucket is required for S3-backed hydration, rate-card and diff reads and for
publication. A dry run suppresses writes, not reads. Local publishing is refused; use deployed ECS
task definitions for production or manual publishing.

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
| `GCINSIGHT_PROVISION_TOKEN` | provisioner only | org |
| `GCINSIGHT_STACK_TOKEN_PREFIX` | collector | SSM path holding per-stack reader tokens |

`GCINSIGHT_WRITE_TOKEN` falls back to the read token when unset, so a single-credential interactive run works. A deployment sets both. Per-stack reader tokens are SSM `SecureString` values below the configured prefix. The provisioner alone reads the provision token; the collector never receives it.

In a deployed setup the Secrets Manager object must contain separate read and write token keys
before scan schedules are enabled, plus the provisioner key if that opt-in task is created.
Secret values are populated outside Terraform; the module manages the container or adopts one.

## Runtime policy and regions

| Variable | Generic default and contract |
|---|---|
| `GCINSIGHT_S3_REGION` | `eu-west-1`; bucket region for AWS operations and generated S3 URLs |
| `GCINSIGHT_SSM_REGION` | `eu-west-1`; region holding per-stack reader credentials |
| `GCINSIGHT_STACK_TOKEN_PREFIX` | `/gcinsight/stack-token`; shared by scan and provisioner |
| `GCINSIGHT_OPT_OUT` | empty; comma-separated stack slugs the owner asks not to provision |
| `GCINSIGHT_COVERAGE_SCORE_WEIGHTS` | equal weights; partial JSON overrides for `metrics`, `logs`, `traces`, `profiles`, `dashboard`, `alert`, `slo`; finite non-negative numbers with positive total |
| `GCINSIGHT_DASHBOARD_DETAIL_ENABLED` | false; `true`/`1` or `false`/`0`; opt-in dashboard JSON inspection for service attribution, with no retained query text |
| `GCINSIGHT_READER_PRODUCT_READS` | empty; comma-separated family tokens described under [Optional product readers](#optional-product-readers); scan and provisioner must agree, with separate deployment approval |

Maturity ownership attribution excludes only identities containing `@grafana.com` (case-insensitive)
in an Admin's login or email. Vendor and partner logins otherwise remain owner candidates; there is no
configurable login exclusion list.

Expected retention and Fleet scrape policy are described below. The Terraform module exposes
`coverage_score_weights`, `dashboard_detail_enabled`, `provision_opt_out` and
`provisioner_product_reads` for the corresponding runtime policies. Do not use these tunables to
store discovered inventory. A consumer must populate every projection field, even where the generic
runtime has a default.

## Optional product readers

All families default off. Selecting a token changes desired reader permissions only through separately
authorised reconciliation; it does not grant customer rollout authority. Counts are point-in-time
configured inventory, not use, executions or business outcomes. Inputs join fresh live inventory;
unreadable stacks are absent, not zero. Each input adds at most eight bounded input-freshness series
across four tiers, not a product-count time series or a stack multiplier.

| Token | Operator meaning |
|---|---|
| `slo` | SLO definition and configured-alerting counts with bounded source/status enums; not objectives, SLI history or firing alerts. |
| `synthetic-monitoring` | Existing app/check read and plugin-access pairs only; alone it causes no Synthetic collection calls. |
| `synthetic-monitoring-query` | Requires the preceding token. Adds only query access to the single uniquely discovered `synthetic-monitoring-datasource` UID matching `^[A-Za-z0-9_-]{1,40}$` and empty-scope probes read. Counts checks by type/enabled state and probes by public/private class, not probe execution. Ambiguous/invalid discovery grants nothing. |
| `faro-apps` | Configured apps by web/mobile/unknown type. Apps read plus Kowalski plugin access; no names, ingest keys or endpoints leave the source. |
| `ml-jobs` | Configured forecast jobs. Forecasting read plus ML plugin access; only job-top-level `grafanaApiKey` is discarded before the unchanged credential guard. Nested/other credential fields still reject the input. |
| `cloud-accounts` | Configured AWS accounts only. CSP read plus plugin access; numeric fresh stack ID and data-only array required. Other providers are unknown, not zero; no all-provider total. Backend write isolation of the credential remains unknown. |
| `pdc-networks` | Policies matching exactly the current stack realm and `set:pdc-signing`, after complete reads of live inventory regions unioned with control realms and every validated page. Private-networks read plus PDC plugin access; server realm filtering is not trusted. Continuations are reconstructed on the fixed proxy, never fetched as supplied credential-bearing URLs. No tokens GET, connections POST or policy write is called. |
| `library-panels` | Configured library panel counts only, not usage or rendered instances. Requires `library.panels:read@folders:*` plus existing baseline `folders:read@folders:*`, verified using the same token's effective permissions GET before exact-200 paged library collection. No model, target, creator or element ID is retained; unavailable wildcard coverage or incomplete pages are absent, never zero. No customer grant follows selection or default-off shipping. |
| `reports` | Configured report objects, including disabled reports. Only `reports:read` at `reports:*`; no executions, delivery or scheduling activity. |
| `irm-integrations` | Implementation exists for counters only, but acceptance is parked: its current transport still accepts HTTP 206. Do not enable it as an accepted delivered counter. Its permission also reaches secret-bearing integration configuration; lists, schedules and alert groups are not admitted. |

Faro, ML, AWS, PDC and reports require exact HTTP 200 and complete validated envelopes; valid empty
collections measure zero, partial or unsupported responses are unavailable. General `Response.ok`
is not this contract. All raw identities and details are discarded from these count outputs, not
guaranteed erased from memory. ML transient-key receipt and IRM credential breadth are named owner
risk decisions, not permission to call other routes. Staff reader/Admin controls do not establish
universal visibility or strict minimum permissions. See the [exact route/pair map](../CAPABILITIES.md#optional-count-only-product-inputs)
and [resource fences](source-resource-fences.md) for transport and schema limits.

With `library-panels` absent, T2 makes no extra credential-store load, permissions GET or library
collection call. The count-only `library_panels_inventory` input is T2-owned and schema-versioned;
other tiers can hydrate it with its original provenance and age, but T2 never hydrates its own failed
input. Missing inputs withhold the Usage table and preserve its last-good S3 object. Empty live
inventory is unknown, not an estate of zero. The zero-series view adds only eight planned series to
the existing input availability/age metrics across four tiers, with no new metric name or product
series. The illustrative local artifact is synthetic, not an estate measurement.

With the Synthetic query token absent, scans make zero Synthetic calls. Reconciliation also makes
zero discovery calls for a legacy-correct role. A held query outside the approved telemetry baseline
can trigger one bounded discovery for deselection; only the pair matching the uniquely discovered
valid Synthetic UID is removable. Ambiguous/invalid discovery removes nothing and reports it; any
other extra query remains dangerous. Working reader tokens are never re-minted just to change pairs.

## Schedules and retention

Module defaults are T1 hourly at :05, T2 daily, T3 six-hourly, T4 daily and the opt-in provisioner
daily, with `schedule_timezone = "UTC"`. `tiers` and `provisioner_schedule_expression` can override
those defaults. See the [operator timetable](https://github.com/rknightion/grafana-cloud-org-insights/blob/main/RUNBOOK.md#scheduled-jobs)
for the canonical times and enablement gates. Set `schedules_enabled = false` during initial setup:
the module default is true. `create_provisioner` defaults to false; its schedule additionally depends
on `provisioner_enabled`. Schedule changes require corresponding deadline, staleness-alert and
carry-forward review, not just a cron edit.

`scan_retention_days` defaults to 90 positive whole days. It governs current `scans/` objects and
the reserved full-key prefix `views/risk_label_hygiene.json`, not all views. Age starts at last
publication; hydration republishes and resets it. Noncurrent versions expire after seven days and
AWS lifecycle processing is asynchronous. Adopted buckets need equivalent targeted retention in
their existing lifecycle policy before raw-match publication. See [Security](security.md).

## Dashboard build

Build-time Grafana credentials are separate from runtime credentials and should be short-lived. The build token is not a runtime secret.

| Variable | Meaning |
|---|---|
| `GCINSIGHT_VIEWS_DIR` | read views from a local directory instead of S3 |
| `GCINSIGHT_WRITE_STACK_URL` | `https://<slug>.grafana.net` |
| `GCINSIGHT_WRITE_STACK_ID` | numeric stack id |
| `GCINSIGHT_GRAFANA_TOKEN` | short-lived build token |

The builder resolves the insights folder by title. An offline build supplies `--ds-uid`, local
views and a synthetic bucket name for generated URLs; that placeholder JSON must not be published.

## Immutable consumer identity

`collector.identity.PROJECTION_ENVS` is the exact non-secret projection contract. A deployment owns
these values in its manifest; use the consumer tools rather than editing a task's environment by
hand. `GCINSIGHT_RUNTIME_CONFIG_DIGEST` verifies the resolved projection;
`GCINSIGHT_REQUIRE_EXPLICIT_CONFIG=1` requires it and all non-optional projection values.
See [Consumer upgrades and rollback](https://github.com/rknightion/grafana-cloud-org-insights/blob/main/consumer/MIGRATION-RUNBOOK.md).

| Variables | Meaning |
|---|---|
| `GCINSIGHT_METRIC_PREFIX`, `GCINSIGHT_LOKI_JOB`, `GCINSIGHT_USER_AGENT` | emitted metric namespace, Loki job and publisher user agent |
| `GCINSIGHT_ROLE_NAME`, `GCINSIGHT_ROLE_DISPLAY`, `GCINSIGHT_ROLE_GROUP` | per-stack custom-role identity |
| `GCINSIGHT_READER_SA_NAME`, `GCINSIGHT_ADMIN_SA_NAME`, `GCINSIGHT_TOKEN_NAME_PREFIX` | persistent reader, transient provisioning Admin and minted-token names |
| `GCINSIGHT_DASHBOARD_UID_PREFIX`, `GCINSIGHT_DASHBOARD_TITLE_PREFIX`, `GCINSIGHT_DASHBOARD_TAG` | generated dashboard identity |
| `GCINSIGHT_DASHBOARD_DS_NAME`, `GCINSIGHT_DASHBOARD_FOLDER_TITLE` | Infinity datasource and insights-folder lookup names |
| `GCINSIGHT_INSIGHTS_FOLDER_UID` | explicit target folder for alert publication; dashboard publication resolves the folder by title |
| `GCINSIGHT_PROM_DS_UID` | alert Prometheus datasource uid; generic default `grafanacloud-prom` |
| `GCINSIGHT_ALERT_RULE_GROUP`, `GCINSIGHT_ALERT_RULE_UIDS_JSON` | alert group and JSON mapping from rule keys to stable uids |
| `GCINSIGHT_ALERT_TITLE_PREFIX`, `GCINSIGHT_ALERT_TITLE_SEPARATOR`, `GCINSIGHT_ALERT_SERVICE_LABEL` | alert title and service-label identity |
| `GCINSIGHT_GCX_CONTEXT` | optional context default for `bin/trace.py --live`; the usage probe requires explicit `--context` and `--out` and ignores this variable; not a collector credential |

Generic identity defaults live in `collector.identity`, `collector.provision`, `bin/dashboards.py`,
`bin/alerts.py` and the emitters. Changing provisioner names affects live reconciliation; changing
output identity affects dashboard queries and alerts. Treat either as a reviewed consumer change,
not cosmetic renaming.

## The rate card

Optional, and read from `config/ratecard.csv` in the deployment bucket by the task role. Absence means volume-only panels, which is a supported state rather than a degraded one.

`ratecard.example.csv` in the repository is the format reference.

Ten dimensions can be priced. `price()` returns `None`, never `0.0`, when a dimension is not priced - an unpriced dimension must read as unknown, not free. A deployment may price only some dimensions, but the UI discloses which components are omitted and must not present the subtotal as a complete estate total.

Configuration errors, all rejected rather than coerced:

- mixed currencies;
- duplicate dimensions;
- unsupported units;
- non-positive prices;
- unsupported dimensions or billing bases, wrong fixed divisors, invalid included quantities, or a
  period other than `month`.

Currency and billing period come from the card. Metrics-series pricing is per 1,000 series where declared, and metrics support two explicit bases:

- `base_rate_only` excludes DPM;
- `dpm_aware` applies `max(active_series, total_dpm / included_dpm)` per stack, using live usage inputs and a dedicated dashboard calculation. It never falls back to the two-input base-series saving.

## Fleet Management default scrape interval

`GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL` is the organisation's expected scrape cadence, as a Go
duration such as `60s`, `1m` or `1m30s`. It defaults to `60s`. Terraform exposes it as
`fleet_default_scrape_interval`.

The hourly tier already lists every Fleet Management pipeline; it parses each pipeline's declared
`scrape_interval` values, plus any explicit `collection_interval` on other wired OTel pull receivers,
in memory and compares them with this default, so the check adds no Fleet
Management calls. An enabled pipeline that reaches active collectors and declares a shorter interval
raises DPM and is counted per stack, listed in `risk_fleet_scrape_intervals` and raises the paused
`fleet_fast_scrape` alert rule. An omitted `scrape_interval` is the component default of 60s; an omitted
`collection_interval` is not read, because its default differs per receiver. An interval that
is not a literal (a module argument or an environment lookup) is counted as unparsed, never as the
default. Local Alloy and collector configs outside Fleet Management are not visible.

## Expected Loki retention policy

`GCINSIGHT_EXPECTED_RETENTION_POLICY` is an optional JSON list of `selector` and `minimum_period`
objects. Terraform exposes the same value as `expected_retention_policy` and passes it into every scan
task. It is genuine deployment policy, not an estate inventory:

```json
[{"selector":"{service=\"example\"}","minimum_period":"14d"}]
```

The default is an empty list. In that state the policy metric is absent and the policy-gap view is
empty. A configured selector is evaluated only against readable effective `retention_stream` data;
an unreadable or undisclosed response is not called compliant and is not called a breach. Selectors
can contain customer label names and values, so the redacted runtime configuration logs only the
number of configured expectations.

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
