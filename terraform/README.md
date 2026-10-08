# Estate insights platform - infrastructure

Terraform/OpenTofu module for the scheduled collector: storage, identity, compute and schedule. It
provisions the platform; it does not provision the Grafana dashboards, which are published separately
by `bin/dashboards.py`.

Works on OpenTofu 1.8 or later and Terraform 1.9 or later, with the AWS provider v6. Variable
validations reference other variables and locals, which needs those versions; `required_version`
says `>= 1.8` because one constraint has to cover both tools, so Terraform 1.8 passes it and then
fails on those validations.

## What it creates

| | |
|---|---|
| S3 bucket | `scans/` (raw, expiring), `views/` (last-good tables, permanent except raw label-risk view), `locks/` (single-run locks), `state/` (carry-forward), optional deployment-owned `config/ratecard.csv` |
| ECS | Fargate cluster, one task definition per tier, CloudWatch log group |
| EventBridge Scheduler | one schedule per configured tier, retained when disabled; optional separate provisioner task/role/schedule |
| IAM | execution role, task role, scheduler role, and a `views/`-only reader for the Grafana datasource |
| Secrets Manager | the container for the two Grafana Cloud tokens - **values are never managed here** |
| ECR | optional repository for the collector image |
| Data Firehose | optional, default-off ECS-log delivery to the same Grafana Cloud Loki target, with failed-record S3 backup |

## Default-off label inventory policy

`label_inventory_enabled` defaults to false. `label_inventory_tunables` is a JSON string
(default `{}`) containing only evaluator `size_floor` (positive whole, default 100),
`static_multiplier` (whole >=1, default 10), `coverage_floor` (0.8..1, default 0.8),
and complete ordered positive threshold-band overrides keyed by accepted catalogue rule.
Published hard limits are not overridable. The module validates against the repository's
accepted catalogue; module packaging must retain the sibling `collector/label_rules.json`.
`label_inventory_static_names` defaults to the source's static-infrastructure names,
is limited to 64 unique syntactically valid names, and can be an empty list.
`label_inventory_budget_seconds` defaults to 900 positive whole seconds, cannot exceed
900, and is further limited to a quarter of remaining T2 time. No variable changes
permissions, response caps, persisted schemas, opt-outs or process-memory guarantees.
The standalone example projects these fields and inherits the module's validations.

ECS renders all four fields into the non-secret scan projection. Old consumer digests
remain admissible only for exact canonical new defaults; any changed policy requires
regenerated digests and explicit matching consumer module wiring. No secret, estate list,
source scope, IAM grant or deployment enablement is introduced here. See
/Users/rob/repos/grafana-cloud-org-insights/RUNBOOK.md for config names, privacy boundaries
and the strictly local read-only stability verification recipe. Missing/unreadable inputs
stay absent; enablement is not a route grant or customer-rollout proof.

## Raw label-risk retention

`scan_retention_days` is a positive whole number of days (default 90). In the existing
bucket lifecycle configuration it expires current `scans/` objects and, separately, current
`views/risk_label_hygiene.json` objects. The latter filter is the full key, not `views/`:
all other last-good views remain permanent, and IAM/readers are unchanged. Reserve this
full-key prefix; S3 prefix matching also covers keys with suffixes after `.json`.

Expiry eligibility is measured since **last publication**, not original observation.
Cross-tier hydration can republish the same matches and reset that age. Withholding a view
when inputs are stale leaves its last good copy, which this targeted rule can then expire.
In the versioned bucket, current-object expiry makes the version noncurrent; the existing
seven-day noncurrent-version rule then applies. AWS lifecycle processing is asynchronous.
This is not a strict 90-day-from-observation erasure guarantee.

With `create_bucket = false`, set `manage_adopted_bucket_config = true` to have this module apply
the same lifecycle rules, versioning, encryption, public-access block and TLS-deny policy as a
created bucket. Each resource replaces the bucket's existing configuration of that kind, so fold
any extra owner lifecycle rules in first and pass extra policy statements as `bucket_policy_source_json`, and never manage the same configuration from a second
lifecycle or policy resource. Without the flag, the bucket owner must configure and verify equivalent
targeted retention in the bucket's existing lifecycle policy **before publishing raw matches**.
Either way, deployment validation must read back effective lifecycle, versioning, encryption and reader access,
plus a fresh effective bucket-policy witness denying non-TLS access, before allowing publication.
Missing controls block raw publication.

## The two credentials

The collector wants two tokens, and the split is the security property rather than tidiness:

- **reader** - org realm, read-only scopes, reaches every stack in the org.
- **writer** - *stack* realm covering the one publishing target, with `metrics:write` + `logs:write`.

The writer cannot touch any other stack because the realm forbids it, not because a scope check says
so. A single combined credential able to both scan the estate and write to it would be strictly more
dangerous than the pair. Both live as JSON keys in one Secrets Manager secret and are injected by the
ECS agent, so they never appear in Terraform state, a plan diff, or the task role's permissions.

## First deployment, in order

Doing these out of order can leave scheduled tasks failing to start, and the first symptom can be a
CloudWatch bill rather than an error anyone reads.

Before any live operation, follow [Clean-room validation](../docs/clean-room-validation.md) and obtain
separate live-change approval. The sequence below is not approval to apply or mint credentials.

1. After approval, apply with `schedules_enabled = false` and `provisioner_enabled = false` wired in
   the deployment root. These disable schedules, not manual invocation. A full deployment also needs
   an explicitly approved `create_provisioner = true`; its module default is false.
2. Write reader, writer and provisioner tokens into the secret out of band (shape in `secrets.tf`).
3. Build and push the image. **It must match `task_architecture`** - the default is ARM64, and an x86
   image on an ARM64 task definition fails at runtime with `exec format error`, not at plan time.
   Pin the reviewed immutable digest in the deployment root and apply again.
4. Run the provisioner first, before any scan tier, to establish per-stack reader credentials.
5. Run tiers serially T2, T3, T1, T4 and verify logs plus advanced scan envelopes.
6. Mint the access key for the views reader and wire the Grafana Infinity datasource to it.
7. Publish dashboards and new paused, unrouted alerts (ordinary updates preserve existing pause/routing). Enable collector schedules after verification,
   and enable the write-capable provisioner schedule last.

See [Standing up a new deployment](../RUNBOOK.md#standing-up-a-new-deployment) for the full sequence.
The standalone example is a starting point, not complete consumer wiring. It exposes `image` and
`provisioner_enabled`, with the provisioner schedule defaulting off independently of collector
schedules. Set `image` to the reviewed registry manifest digest before runtime approval. Its
`next_steps` output describes the same provisioner-first sequence, not authorization to execute it.

## Schedules and module interface

The module defaults are T1 hourly at :05, T2 daily, T3 six-hourly, T4 daily and an opt-in daily
provisioner, all interpreted in `schedule_timezone` (default `UTC`). Deployment expressions/timezone
may override these. See the [RUNBOOK scheduled-jobs table](../RUNBOOK.md#scheduled-jobs) for the
canonical five-job purpose and timetable rather than treating module defaults as live state.
`create_provisioner = false` means no provisioner task, role or schedule exists. When created,
its schedule requires both `schedules_enabled` and `provisioner_enabled`. Each scan schedule requires
`schedules_enabled` and its tier's `enabled`; disabling a tier retains its task and schedule.

`variables.tf` and `outputs.tf` are the complete interface. The tables below group inputs by operator
purpose; omitted defaults in the required row mean Terraform requires an explicit value.

| Inputs | Module default / contract |
|---|---|
| `consumer_manifest` | `null`; the decoded consumer manifest, which then supplies every input it represents and the Purpose/Namespace tags (see [Manifest mode](#manifest-mode-for-consumer-deployments)) |
| `name_prefix`, `grafana_org_id`, `write_stack_slug`, `mimir_write_url`, `mimir_tenant`, `loki_write_url`, `loki_tenant`, `subnet_ids` | required; deployment identity, signal tenants and egress subnets. In manifest mode all but `subnet_ids` come from the manifest and must be left out |
| `tags` | `{}`; merged over provider defaults |
| `create_bucket`, `bucket_name` | `true`, empty; empty name resolves to `<name_prefix>-data`, explicit name required for adoption |
| `manage_adopted_bucket_config` | `false`; with an adopted bucket, manage its lifecycle, versioning, encryption, public-access block and TLS-deny policy (never the bucket) |
| `bucket_policy_source_json` | empty; extra policy statements merged into the managed bucket policy, which otherwise replaces any existing one |
| `scan_retention_days` | `90` positive whole days; current scans and reserved raw-match view prefix |
| `coverage_score_weights`, `dashboard_detail_enabled` | seven equal weights, `false`; detailed dashboard selector evidence is opt-in |
| `expected_retention_policy`, `fleet_default_scrape_interval` | `[]`, `60s`; genuine deployment policy, not configured estate inventory |
| `create_secret`, `tag_adopted_secret`, `secret_name` | `true`, `false`, empty; empty resolves to `<name_prefix>/tokens`, adopted tags are opt-in |
| `reader_secret_key`, `writer_secret_key` | `GCINSIGHT_READ_TOKEN`, `GCINSIGHT_WRITE_TOKEN`; JSON keys, never token values |
| `create_ecr_repository`, `image`, `task_architecture` | `true`, empty, `ARM64`; empty image uses created ECR `:latest`, unsuitable for reviewed runtime rollout |
| `security_group_ids`, `assign_public_ip` | `[]`, `false`; empty creates HTTPS-egress group |
| `schedules_enabled`, `schedule_timezone`, `tiers` | `true`, `UTC`, four default tiers; disable schedules explicitly for first deployment. A tier's `schedule_expression` is optional: t1-t4 fall back to `local.default_tier_schedules` |
| `schedule_retry_attempts`, `log_retention_days` | `2`, `30`; invocation retry count and CloudWatch retention |
| `firehose_logs_enabled`, `firehose_log_subscription_enabled` | both `false`; staged stream creation then subscription |
| `firehose_access_key_secret_arn`, `firehose_access_key_secret_kms_key_arn` | both empty; dedicated adopted secret ARN required when enabled, KMS ARN only for a CMK |
| `firehose_failed_record_retention_days` | `7`; failed-delivery object retention |
| `create_views_reader_user` | `true`; views-only IAM user, no access key in state |
| `stack_token_prefix` | `/gcinsight/stack-token`; shared scan/provisioner SSM credential prefix |
| `metric_prefix`, `loki_job`, `collector_user_agent` | `gcinsight`, `gcinsight`, `gcinsight-collector/1 (+grafana-ps)`; consumer publication identity |
| `role_name`, `role_display`, `role_group` | `custom:gcinsight.reader`, `Grafana Cloud Org Insights reader`, `Grafana Cloud Org Insights`; stable reader role identity |
| `reader_service_account_name`, `admin_service_account_name`, `token_name_prefix` | `gcinsight-data`, `gcinsight-insights-provisioner`, `gcinsight-data`; recorded provisioning identities |
| `scan_runtime_config_digest`, `provisioner_runtime_config_digest`, `require_explicit_consumer_config` | empty, empty, `false`; consumer projections may require both validated digests |
| `create_provisioner`, `provisioner_secret_key` | `false`, `GCINSIGHT_PROVISION_TOKEN`; independent opt-in write-capable task |
| `provisioner_schedule_expression`, `provisioner_enabled` | daily module default, `true`; see RUNBOOK timetable and both schedule gates above |
| `provision_opt_out`, `provisioner_product_reads` | `[]`, `[]`; approved stack opt-outs and optional `slo`/`synthetic-monitoring`/`synthetic-monitoring-query`/`irm-integrations`/`faro-apps`/`ml-jobs`/`cloud-accounts`/`pdc-networks`/`reports` read families |
| `provisioner_cpu`, `provisioner_memory` | `256`, `512` MiB; separate provisioner sizing |

| Outputs | Use / availability |
|---|---|
| `bucket_name`, `cluster_arn`, `cluster_name`, `log_group_name` | resolved storage, compute and task-log targets |
| `task_definition_arns`, `task_definition_families` | per-scan-tier revision ARNs and moving families; use reviewed revisions for controlled runs |
| `schedule_names`, `schedule_states` | per-scan-tier names and effective enabled/disabled states, not provisioner outputs |
| `ecr_repository_url`, `views_reader_user_name` | null when the corresponding resource is not created |
| `secret_name`, `task_role_arn` | resolved token container and collector IAM identity; task role also reads SSM and decrypts scoped parameters |
| `firehose_delivery_stream_name`, `firehose_delivery_stream_arn`, `firehose_failed_record_bucket_name`, `firehose_loki_endpoint` | null until Firehose is enabled |
| `firehose_log_subscription_enabled` | subscription switch, distinct from stream existence |
| `run_task_command` | command template with a task-definition placeholder; not live-run authority |
| `task_environments` | non-secret container environment per tier and `provisioner`; compare with `bin/consumer_manifest.py env` on a digest mismatch |
| `tags` | tags applied to every taggable resource, manifest tag values included |
| `schedules` | expression, timezone and state per tier and `provisioner` |
| `created_resources` | which optional resources this deployment creates rather than adopts or omits |

The standalone example leaves collector and provisioner schedules off, unlike the module's schedule
switch defaults. It does not wire `create_provisioner`, so enabling its provisioner schedule switch
alone cannot create that task. Complete deployment wiring belongs to the approved deployment root.

## Service observability completeness weights

`coverage_score_weights` controls the relative contribution of the seven visible components in the
Pillar K service register: metrics, logs, traces, profiles, an explicit service dashboard tag, an alert
label and an SLO label. They default to equal weight. Values must be non-negative and at least one must
be above zero; setting a weight to zero removes that component from the arithmetic but not from the
evidence columns. The weighted score remains in S3 rather than becoming a metric label, so deployment
policy cannot expand Mimir cardinality.

## Optional Loki retention expectations

`expected_retention_policy` accepts a list of `selector` and `minimum_period` objects. The module
serialises the list into the collector task environment. Its empty default disables policy-gap
reporting; no selector or period is embedded in this module. Treat selectors as customer data and
keep deployment-specific values in the consumer configuration.

## Fleet Management default scrape interval

`fleet_default_scrape_interval` (default `60s`) is the cadence Fleet Management pipelines are compared
against. An enabled pipeline that reaches live collectors and declares a shorter `scrape_interval` is
counted on the Risk dashboard's Fleet tab and by the paused `fleet_fast_scrape` alert rule, because it
raises DPM. Set it to the organisation's agreed cadence; it accepts Go durations such as `30s` or `1m`.

## Optional ECS task logs through Data Firehose

The collector already writes its structured application records to Loki. The optional Firehose path is
for failures outside that code path: image/bootstrap failures, early unhandled exceptions and OOM output
that otherwise exists only in CloudWatch Logs. It sends to the **same** stack as the collector. The module
derives `https://aws-<loki-host>/aws-logs/api/v1/push` from `loki_write_url`; there is deliberately no
second Grafana destination input.

It is a staged opt-in:

1. Create a dedicated Secrets Manager secret out of band. Its secret string must be
   `{"api_key":"<loki_tenant>:<logs-write-token>"}`: AWS Data Firehose requires the `api_key` JSON field
   for an HTTP endpoint. Do not use the collector's multi-key secret because Firehose cannot select its
   credential field. Pass only the dedicated secret's ARN as `firehose_access_key_secret_arn`. The module
   neither reads nor creates the secret, so the value never reaches Terraform state. The AWS-managed
   Secrets Manager key needs no extra input. If the adopted secret uses a customer-managed KMS key, also
   pass its ARN as `firehose_access_key_secret_kms_key_arn`; the delivery role then receives decrypt
   access to that key alone.
2. Set `firehose_logs_enabled = true` and keep `firehose_log_subscription_enabled = false`. Apply. This
   creates the failed-record bucket, IAM and delivery stream without touching the live ECS log group.
3. Send one deliberate test record to `firehose_delivery_stream_name`. Confirm it reaches the derived
   `firehose_loki_endpoint` and that the failed-record bucket stays empty. This live delivery is required:
   AWS and provider validation cannot prove the adopted secret's value shape.
4. Only then set `firehose_log_subscription_enabled = true` and apply to create the CloudWatch Logs
   subscription filter.

The HTTP request is GZIP-encoded and buffered at 1 MB or 60 seconds; only failed deliveries are backed up,
also as GZIP, and expire after seven days by default. The configured Loki labels are bounded to `job`,
`service_name`, `tier`, `env` and `aws_account`. Their Firehose names carry the required `lbl_` prefix,
which Grafana removes at query time. The shared log group cannot supply a per-record scanner tier through
Firehose common attributes, so `tier="ecs"` is the fixed source class; the actual CloudWatch stream prefix
remains in the record body. Task ARN/id, container id and image digest are never stream labels.

At this platform's small batch-log volume the incremental Firehose and failed-record S3 cost is expected
to be negligible. It creates no metric series and needs no dashboard panel or Grafana panel plugin. It
does require a stack-realm `logs:write` token represented by the adopted access-key secret.

## Things that will bite

- **The Mimir and Loki tenant ids are not the stack id.** Using the stack id fails as a **401**, which
  reads as a bad token rather than a wrong tenant. They are `hmInstancePromId` and `hlInstanceId`.
- **EventBridge Scheduler has no `container_overrides`.** The AWS `EcsParameters` type does not support
  it, which is why there is one task definition per tier rather than one shared definition. If you add
  a tier, it gets its own definition automatically via `var.tiers`.
- **Neither Scheduler nor ECS deduplicates runs.** Two concurrent scans of one tier race on
  `latest.json`, and the one that finishes *last* wins regardless of which started first - so the
  estate can appear to go backwards. This is prevented in the collector by a per-tier S3 lock, not by
  any scheduler setting. The task role therefore needs `s3:DeleteObject` on `locks/*`; without it every
  run leaves its lock behind and the next one refuses to start, which looks exactly like a scheduling
  bug.
- **ECS has no max-runtime setting.** The collector's `--deadline-seconds`, passed from `var.tiers`,
  fences source caller waits and prevents starting more work; it is not hard termination of all local
  computation or surviving HTTP reads. Keep it shorter than the tier's interval. See
  [source resource fences](../docs/source-resource-fences.md).
- **`scans/` must stay unreadable by Grafana.** It holds per-user identity detail that no dashboard
  needs. The reader user is scoped to `views/*`; verify with `aws iam simulate-principal-policy`, not
  by reading the policy JSON, because a prefix typo looks fine and denies everything.
- **Tiers share one rate-limit quota.** `grafana.com` meters per credential, so two tiers running at
  once halve each other's effective pacing. The default cron expressions are staggered for this reason.

## Reader product policy

The following optional families describe current main, not retroactive stable v0.5.0 content or
proof of a deployed upgrade. Dev v0.5.0 execution remains unproven after an AWS authentication block.
No new customer product-read grant follows module support. See the
[operator family reference](../docs/configuration.md#optional-product-readers).

Faro, ML, AWS accounts, PDC and reports require exact HTTP 200 and complete validated responses.
IRM implementation still admits HTTP 206; its count-integrity acceptance is parked and it must not
be treated as an accepted delivered counter. Library/playlist controls remain parked, and k6 has
no admitted route. Optional counters add input-freshness series only, not product metrics.

`provisioner_product_reads` remains default-off (`[]`) and accepts `slo`, `synthetic-monitoring`,
`synthetic-monitoring-query`, `irm-integrations`, `faro-apps`, `ml-jobs`, `cloud-accounts`, `pdc-networks` and `reports`.
`reports` adds exactly `reports:read` at `reports:*`, no plugin, send, settings,
query or write grant. T2 calls only guarded GET `/api/reports` without query or
redirects on the fresh inventory's validated HTTPS origin and requires HTTP 200.
Only a complete bare array of objects with valid transient IDs is supported;
wrappers, pagination, malformed or partial responses are unavailable. Configured
objects include disabled reports. All report details are discarded using the
unchanged structural credential guard. Genuine complete empty lists measure zero;
unreadable stacks are absent. This is not execution, delivery or scheduling activity,
universal visibility, strict minimality, credential write isolation or a customer grant.
`pdc-networks` adds exactly `grafana-pdc-app.private-networks:read` (empty scope) and
`plugins.app:access` at `plugins:id:grafana-pdc-app`. T2 counts only policies matching
the current stack realm and `set:pdc-signing`, after every fresh-inventory region plus
control realm and page succeeds. Only the fixed accesspolicies GET is called; no tokens,
connections, traffic or policy writes. All policy details are dropped. Complete empty
reads measure zero; unknown, malformed or partial coverage is absent. The permission
also reaches a tokens GET, which is not used. Staff visibility is conditional, not a
universal completeness or customer rollout claim. The query token requires `synthetic-monitoring`
and adds query access only to the stack's single uniquely discovered, valid Synthetic datasource
UID plus unscoped probes read. Ambiguous or invalid discovery grants neither pair. Without the
query token, collection makes no Synthetic HTTP calls and legacy role grants stay unchanged.
`cloud-accounts` adds only `grafana-csp-app:read` (empty scope) and
`plugins.app:access` scoped to `plugins:id:grafana-csp-app` for T2 configured AWS
account counts. Only GET `/api/plugin-proxy/grafana-csp-app/he-api/api/v2/stacks/<fresh stack.id>/aws/accounts`
without query is permitted, using the fresh inventory HTTPS origin and numeric stack ID.
The supported data-only array is validated with the unchanged structural credential guard;
all account details are discarded. Genuine empty data measures zero; failed or partial responses
are absent. Other providers are unknown, not zero, and this is not an all-provider total.
The owner permits this GET while backend write isolation of the credential remains unproven;
GET-only construction is not server-enforced credential isolation or a customer grant.

`ml-jobs` adds only `grafana-ml-app.forecasting:read` (empty scope) and
`plugins.app:access` scoped to `plugins:id:grafana-ml-app` for T2 configured forecast job
counts only. The owner accepts transient receipt of job-top-level `grafanaApiKey` on GET
`/api/plugins/grafana-ml-app/resources/manage/api/v1/jobs` without query. That field is
removed before structural credential validation; nested keys and other known credential fields
remain rejected. All job details are discarded. Unreadable or partial coverage is absent.
This is not a customer grant, a query permission, or a credential memory-secrecy claim.

`faro-apps` adds only `grafana-kowalski-app.apps:read` (empty scope) and
`plugins.app:access` scoped to `plugins:id:grafana-kowalski-app`. It enables default-off T2
point-in-time app counts by web/mobile/unknown type, not sessions or usage. App identifiers,
names, ingest keys/endpoints and settings are discarded at parse. Unreadable stacks are absent;
visibility is conditional on product permissions, not a universal estate completeness claim.

`irm-integrations` adds only `grafana-irm-app.integrations:read` (empty scope) and
`plugins.app:access` (`plugins:id:grafana-irm-app`) for T2 configured integration counts, not activity.
That credential also reaches secret-bearing configuration; the collector is restricted to GET
`/api/plugins/grafana-irm-app/resources/alert_receive_channels/counters/` without query.
No configuration lists, retrieve routes, schedules or test-alert calls are permitted. This opt-in
is not a customer grant. The module mirrors this one policy into both provisioner and
scan tasks as `GCINSIGHT_READER_PRODUCT_READS`; no separate scanner grant or family list exists.
The scan runtime digest includes this value, so update consumer manifests and module/image pins
together before rollout. Selecting `slo` enables count-only SLO definition collection on T2; selecting
`synthetic-monitoring` does not grant its datasource query scope or establish check/result collection. `bin/consumer_manifest.py upgrade` verifies an older manifest's existing
digests, then carries its provisioner policy into the added scan field. Explicit `regenerate` also
carries the policy when the scan field is absent; `check` requires the current projection and never
rewrites it. An explicit scan/provisioner mismatch is rejected rather than silently changed. This
wiring alone does not select a new token or change credentials. The query token must be explicitly
approved per deployment; T2 retains only bounded check-type, enabled and public/private probe counts.
Missing or unreadable coverage is absent, not zero. Deselection permits one bounded datasource lookup
only for a held query outside approved telemetry (usage-insights everywhere, usage only on the write
stack); only the unique valid SM query and held probes read are removable. No wildcard or write grant
is permitted and a working credential is kept.

## Consuming it

The normal image source is the public multi-architecture image at
`ghcr.io/rknightion/grafana-cloud-org-insights`, pinned by manifest digest. Set
`create_ecr_repository = false` when consuming it directly. ECS pulls public GHCR images anonymously;
the task subnets need outbound registry access.

An organisation with an ECR-only policy can instead configure Amazon ECR pull-through cache for GHCR
and pass the cached digest reference as `image`. AWS requires that cache rule to use a same-account,
same-region Secrets Manager upstream credential even for a public GHCR package. The secret name must
begin with `ecr-pullthroughcache/` and carry the GHCR username and personal access token. That credential
and cache policy belong to the deployment, not this generic module.

As a module from an existing root:

```hcl
module "insights" {
  source = "./modules/gcinsight"

  name_prefix      = "estate-insights"
  grafana_org_id   = "..."
  write_stack_slug = "..."
  mimir_write_url  = "https://prometheus-prod-NN-<region>.grafana.net"
  mimir_tenant     = "..."
  loki_write_url   = "https://logs-prod-NNN.grafana.net"
  loki_tenant      = "..."
  subnet_ids       = ["subnet-...", "subnet-..."]

  schedules_enabled  = false # until the manual tiers and dashboards are verified
  provisioner_enabled = false # enable independently, last

  # Optional staged ECS-log delivery. Both switches default false.
  firehose_logs_enabled             = false
  firehose_log_subscription_enabled = false
  # firehose_access_key_secret_arn   = "arn:aws:secretsmanager:...:secret:..."
  # firehose_access_key_secret_kms_key_arn = "arn:aws:kms:...:key/..." # only for a CMK secret
}
```

Or copy `examples/standalone/`, which owns its own provider and backend.

## Manifest mode for consumer deployments

A consumer that keeps a deployment manifest (`consumer/manifest.schema.json`) passes it to the module
instead of hand-copying it into arguments. Resource addresses are the same as explicit wiring, so
switching an existing deployment needs no `moved` block; the plan must show only in-place changes,
if any.

```hcl
module "<consumer>_insights" {
  count  = var.<consumer>_insights_enabled ? 1 : 0
  source = "git::https://github.com/rknightion/grafana-cloud-org-insights.git//terraform?ref=<40-character-sha>"

  consumer_manifest = jsondecode(file("${path.module}/<consumer>-insights.overlay.json"))

  # Kill switches, ANDed with the manifest's aws.schedules_enabled / aws.provisioner_enabled.
  schedules_enabled   = var.<consumer>_insights_schedules_enabled
  provisioner_enabled = var.<consumer>_insights_provisioner_enabled

  # Inputs the manifest does not represent stay ordinary arguments.
  image                          = var.<consumer>_insights_consumer_image
  subnet_ids                     = module.vpc.private_subnets
  firehose_access_key_secret_arn = var.<consumer>_insights_firehose_access_key_secret_arn
  tiers = {
    t1 = { cpu = 512, memory = 1024, deadline_seconds = 900, description = "Hourly inventory + carry-forward" }
    t2 = { cpu = 1024, memory = 2048, deadline_seconds = 3600, description = "Daily per-stack identity, plugin and service-account detail" }
    t3 = { cpu = 1024, memory = 4096, deadline_seconds = 3600, description = "6-hourly data-plane sweep" }
    t4 = { cpu = 512, memory = 1024, deadline_seconds = 900, description = "Daily estate diff - 7-day and 1-day windows" }
  }
  tags = var.tags # the module sets Purpose and Namespace from the manifest over these; the manifest wins
  # tag_adopted_secret        = true  # adopted secret only
  # bucket_policy_source_json = ...   # adopted bucket with aws.manage_adopted_bucket_config only
}
```

- Every manifest key takes effect when present, and the module default applies when it is absent.
  `terraform/consumer_manifest.tf` holds the one table of which key feeds which input.
- The module renders `scan_runtime_config_digest` and `provisioner_runtime_config_digest` from
  `runtime_projection_digests` and forces `require_explicit_consumer_config = true`.
- It applies `aws.purpose_tag` as tag `Purpose` and `aws.cost_namespace` as tag `Namespace`, merged
  over `tags`, so the manifest wins a key clash, as the consumers' own `merge(var.tags, {...})` did.
  Explicit mode applies `tags` alone.
- `aws.manage_adopted_bucket_config` (optional, absent means `false`) feeds
  `manage_adopted_bucket_config`; read [Adopting resources](#adopting-resources-that-already-exist)
  before setting it. `bucket_policy_source_json` stays an ordinary argument.
- At plan time the module refuses, by name, an argument for any input the manifest represents (other
  than the two kill switches) whose value differs from the variable default, a tier
  `schedule_expression` other than its module default (the `aws.t1_schedule`..`t4_schedule` keys own
  it), and an `aws.<tier>_schedule` for a tier `tiers` does not declare. An argument passed with exactly
  its default value cannot be told from an omitted one and is harmless; `bin/consumer_manifest.py check
  --terraform` refuses even that, statically, by name.
- At plan time the module refuses a manifest whose `GCINSIGHT_S3_BUCKET`, `GCINSIGHT_S3_REGION` or
  `GCINSIGHT_SSM_REGION` differs from what it renders, rather than shipping tasks that refuse to start.
- `bin/consumer_manifest.py regenerate --prune-defaults` removes every key whose value is exactly this
  checkout's module default and leaves every digest unchanged. Run it with the tool from the module
  revision you pin: a pruned manifest means "that revision's defaults". `upgrade` names (never values)
  every omitted key whose default the target revision changes and refuses unless
  `--accept-default-changes` is passed; it then re-derives the digests
  for the target revision.
- The explicit-argument interface is unchanged when `consumer_manifest` is null. A v0.9 manifest
  validates with byte-identical digests.

## Adopting resources that already exist

`create_bucket`, `create_secret`, `create_ecr_repository` and `create_views_reader_user` all default
to true and can be turned off to adopt something provisioned earlier. When `create_bucket = false`
Terraform never manages the bucket itself, so `tofu destroy` cannot reach its objects. Its lifecycle,
public-access blocking, versioning, encryption and bucket policy are managed only with
`manage_adopted_bucket_config = true`; otherwise verify all separately, because an adopted bucket is
not a validated one. Turning the flag back off destroys those resources, which suspends versioning and
removes the lifecycle rules and policy.

The Firehose access-key secret is different: it is **always adopted** and supplied by ARN. There is no
create switch and no secret data source because even reading the value would put the credential on the
wrong side of the Terraform state boundary.
