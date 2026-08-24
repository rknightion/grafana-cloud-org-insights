# Estate insights platform - infrastructure

Terraform/OpenTofu module for the scheduled collector: storage, identity, compute and schedule. It
provisions the platform; it does not provision the Grafana dashboards, which are published separately
by `bin/dashboards.py`.

Works on OpenTofu and Terraform. Requires the AWS provider v6.

## What it creates

| | |
|---|---|
| S3 bucket | `scans/` (raw, expiring), `views/` (dashboard tables, permanent), `locks/` (single-run locks) |
| ECS | Fargate cluster, one task definition per tier, CloudWatch log group |
| EventBridge Scheduler | one schedule per enabled tier |
| IAM | execution role, task role, scheduler role, and a `views/`-only reader for the Grafana datasource |
| Secrets Manager | the container for the two Grafana Cloud tokens - **values are never managed here** |
| ECR | optional repository for the collector image |
| Data Firehose | optional, default-off ECS-log delivery to the same Grafana Cloud Loki target, with failed-record S3 backup |

## The two credentials

The collector wants two tokens, and the split is the security property rather than tidiness:

- **reader** - org realm, read-only scopes, reaches every stack in the org.
- **writer** - *stack* realm covering the one publishing target, with `metrics:write` + `logs:write`.

The writer cannot touch any other stack because the realm forbids it, not because a scope check says
so. A single combined credential able to both scan the estate and write to it would be strictly more
dangerous than the pair. Both live as JSON keys in one Secrets Manager secret and are injected by the
ECS agent, so they never appear in Terraform state, a plan diff, or the task role's permissions.

## First deployment, in order

Doing these out of order gives four tasks an hour failing to start, and the first symptom is a
CloudWatch bill rather than an error anyone reads.

1. `terraform apply` with `schedules_enabled = false`. Everything exists; nothing fires.
2. Write the tokens into the secret (`aws secretsmanager put-secret-value`, shape in `secrets.tf`).
3. Build and push the image. **It must match `task_architecture`** - the default is ARM64, and an x86
   image on an ARM64 task definition fails at runtime with `exec format error`, not at plan time.
4. Run one tier by hand (`terraform output run_task_command`) and read its logs.
5. Mint the access key for the views reader and wire the Grafana Infinity datasource to it.
6. Set `schedules_enabled = true` and apply again.

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
- **ECS has no max-runtime setting.** A run is bounded only by the collector's own
  `--deadline-seconds`, passed from `var.tiers`. Keep it shorter than the tier's interval.
- **`scans/` must stay unreadable by Grafana.** It holds per-user identity detail that no dashboard
  needs. The reader user is scoped to `views/*`; verify with `aws iam simulate-principal-policy`, not
  by reading the policy JSON, because a prefix typo looks fine and denies everything.
- **Tiers share one rate-limit quota.** `grafana.com` meters per credential, so two tiers running at
  once halve each other's effective pacing. The default cron expressions are staggered for this reason.

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

  schedules_enabled = false # until step 6 above

  # Optional staged ECS-log delivery. Both switches default false.
  firehose_logs_enabled             = false
  firehose_log_subscription_enabled = false
  # firehose_access_key_secret_arn   = "arn:aws:secretsmanager:...:secret:..."
  # firehose_access_key_secret_kms_key_arn = "arn:aws:kms:...:key/..." # only for a CMK secret
}
```

Or copy `examples/standalone/`, which owns its own provider and backend.

## Adopting resources that already exist

`create_bucket`, `create_secret`, `create_ecr_repository` and `create_views_reader_user` all default
to true and can be turned off to adopt something provisioned earlier. When `create_bucket = false`
Terraform manages neither the lifecycle rules nor the public-access block, so verify both separately -
an adopted bucket is not a validated one.

The Firehose access-key secret is different: it is **always adopted** and supplied by ARN. There is no
create switch and no secret data source because even reading the value would put the credential on the
wrong side of the Terraform state boundary.
