# --- Identity and naming ---------------------------------------------------------------------------

variable "name_prefix" {
  description = <<-EOT
    Prefix for every resource this module creates. It is the ONLY thing separating two instantiations
    in the same AWS account, which is not hypothetical: running a production deployment and a testbed
    side by side is the normal case. Change it and you get a completely independent deployment; reuse
    it and you collide.
  EOT
  type        = string

  validation {
    # S3 bucket names, IAM names and ECS names have overlapping-but-different rules; this is the
    # intersection, so a prefix that validates here is safe for all of them.
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,26}[a-z0-9]$", var.name_prefix))
    error_message = "name_prefix must be 3-28 chars, lowercase alphanumeric and hyphens, not starting or ending with a hyphen."
  }
}

variable "tags" {
  description = "Tags applied to every taggable resource, merged over the provider's default_tags."
  type        = map(string)
  default     = {}

  # COST ATTRIBUTION: pass a tag whose KEY is an ACTIVATED cost allocation tag in your payer account, or
  # this platform's spend cannot be isolated in Cost Explorer at all. A sensible-looking key that has not
  # been activated is invisible there - the tag exists on the resource and Cost Explorer cannot group by it.
  #
  #   aws ce get-tags --time-period Start=<date>,End=<date>   # tag keys you can actually group by
  #
  # Prefer `aws ce get-tags` over `aws ce list-cost-allocation-tags`: the latter needs the payer account
  # and returns AccessDenied from a linked account. Cost allocation tags are also NOT retroactive, so tag
  # before you want the data, and allow ~24h for values to appear.
  #
  # If you want Terraform to ACTIVATE a key rather than just apply it, `aws_ce_cost_allocation_tag` is the
  # resource - but it must run in the PAYER account, so it cannot live in this module.
  #
  # What this module cannot tag for you, and you should handle separately:
  #   * **An adopted S3 bucket (`create_bucket = false`) - permanently, not as an oversight.** Verified
  #     against the provider schema: of 1,700 AWS resource types there is no standalone S3 tagging
  #     resource, so tags can only be set on a bucket Terraform manages. Importing it would put the
  #     bucket holding every scan in scope for `tofu destroy`, which adoption exists to prevent. Tag it
  #     out of band - RUNBOOK.md has the command. A bucket this module CREATES is tagged normally.
  #   * An adopted Secrets Manager secret, UNLESS `tag_adopted_secret = true` - `aws_secretsmanager_tag`
  #     can tag a secret without owning it, so that path is available and opt-in.
  #   * EventBridge Scheduler schedules. They are only taggable via their schedule GROUP, and this module
  #     uses the shared `default` group. Scheduler cost here is negligible (a few dozen invocations a day
  #     against a 1M free tier), so this is noted rather than solved.
  #   * A task started by hand with `aws ecs run-task` - it needs an explicit
  #     `--propagate-tags TASK_DEFINITION`, or the task runs untagged and its Fargate cost is
  #     unattributable. Scheduled runs are fine: the schedule sets `propagate_tags = "TASK_DEFINITION"`.
}

# --- Grafana Cloud target --------------------------------------------------------------------------
#
# NO DEFAULTS on any of these, on purpose. A default would mean a `terraform apply` in the lab
# silently scanning one org and writing series into the wrong production stack. Making them
# required turns that into a plan-time error.

variable "grafana_org_id" {
  description = "Grafana Cloud organisation id the collector scans (gcom `/orgs/<id>`)."
  type        = string
}

variable "write_stack_slug" {
  description = "Slug of the single stack the platform publishes to. Everything lands here, so this is also the series denominator."
  type        = string
}

variable "mimir_write_url" {
  description = "Base URL for Mimir remote_write, e.g. https://prometheus-prod-NN-<region>.grafana.net. No path suffix."
  type        = string

  validation {
    condition     = startswith(var.mimir_write_url, "https://")
    error_message = "mimir_write_url must be https:// - the collector refuses a non-TLS endpoint by construction."
  }
}

variable "mimir_tenant" {
  description = "Mimir tenant id - the stack's hmInstancePromId. NOT the stack id; that fails as a 401 rather than a crash."
  type        = string
}

variable "loki_write_url" {
  description = "Base URL for the Loki push API, e.g. https://logs-prod-NNN.grafana.net. No path suffix."
  type        = string

  validation {
    condition     = can(regex("^https://[A-Za-z0-9.-]+/?$", var.loki_write_url))
    error_message = "loki_write_url must be an HTTPS origin with no path, query or fragment."
  }
}

variable "loki_tenant" {
  description = "Loki tenant id - the stack's hlInstanceId."
  type        = string
}

# --- Storage ---------------------------------------------------------------------------------------

variable "create_bucket" {
  description = <<-EOT
    Create the S3 bucket. Set false to adopt a bucket that already exists - which is the case for the
    first production deployment, where the bucket was provisioned by hand before this module existed.
    Adopting means Terraform manages neither the lifecycle rules nor the public-access block, so
    verify those separately.
  EOT
  type        = bool
  default     = true
}

variable "bucket_name" {
  description = "Bucket name. Defaults to `<name_prefix>-data` when empty. Required to be set explicitly when create_bucket is false."
  type        = string
  default     = ""
}

variable "scan_retention_days" {
  description = "Lifecycle expiry for the `scans/` prefix. `views/` never expires - the dashboards read it live."
  type        = number
  default     = 90
}

variable "coverage_score_weights" {
  description = "Relative weights for the seven visible service observability-completeness components. Zero excludes a component from the score but not from the S3 evidence columns."
  type = object({
    metrics   = number
    logs      = number
    traces    = number
    profiles  = number
    dashboard = number
    alert     = number
    slo       = number
  })
  default = {
    metrics   = 1
    logs      = 1
    traces    = 1
    profiles  = 1
    dashboard = 1
    alert     = 1
    slo       = 1
  }

  validation {
    condition = (
      alltrue([for weight in values(var.coverage_score_weights) : weight >= 0]) &&
      sum(values(var.coverage_score_weights)) > 0
    )
    error_message = "coverage_score_weights must be non-negative and at least one weight must be above zero."
  }
}

# --- Credentials -----------------------------------------------------------------------------------

variable "create_secret" {
  description = <<-EOT
    Create the Secrets Manager container for the collector's two Grafana Cloud tokens. The VALUES are
    never managed here - Terraform state is not a secret store, and a token in a plan output is a
    token in a CI log. Write them out of band:

      aws secretsmanager put-secret-value --secret-id <name> --secret-string \
        '{"GCINSIGHT_READ_TOKEN":"...","GCINSIGHT_WRITE_TOKEN":"...","GCINSIGHT_ORG_ID":"..."}'
  EOT
  type        = bool
  default     = true
}

variable "tag_adopted_secret" {
  description = <<-EOT
    Apply `tags` to the Secrets Manager secret when it is ADOPTED (`create_secret = false`), using
    `aws_secretsmanager_tag`. Off by default: this module does not write to resources it did not create
    unless asked. Turn it on when the secret's cost or ownership needs to be attributable in Cost Explorer.

    There is deliberately no S3 equivalent - the AWS provider has no standalone S3 bucket tagging
    resource, so an adopted bucket must be tagged out of band. See RUNBOOK.md.
  EOT
  type        = bool
  default     = false
}

variable "secret_name" {
  description = "Secrets Manager secret holding GCINSIGHT_READ_TOKEN and GCINSIGHT_WRITE_TOKEN as JSON keys. Defaults to `<name_prefix>/tokens`."
  type        = string
  default     = ""
}

variable "reader_secret_key" {
  description = "JSON key inside the secret holding the read (scanning) token."
  type        = string
  default     = "GCINSIGHT_READ_TOKEN"
}

variable "writer_secret_key" {
  description = "JSON key inside the secret holding the write (publishing) token."
  type        = string
  default     = "GCINSIGHT_WRITE_TOKEN"
}

# --- Container image -------------------------------------------------------------------------------

variable "create_ecr_repository" {
  description = "Create an ECR repository for the collector image. Set false when pushing to an existing registry."
  type        = bool
  default     = true
}

variable "image" {
  description = <<-EOT
    Full image reference the tasks run. Leave empty to use `<created ECR repo>:latest`.

    Pin a DIGEST rather than a tag for anything you care about reproducing: `:latest` means a task
    that fails today and succeeds tomorrow with no change in this configuration, which is the single
    most confusing failure mode a scheduled job has.
  EOT
  type        = string
  default     = ""
}

variable "task_architecture" {
  description = "Fargate CPU architecture. ARM64 is ~20% cheaper for identical work and the collector is pure Python."
  type        = string
  default     = "ARM64"

  validation {
    condition     = contains(["ARM64", "X86_64"], var.task_architecture)
    error_message = "task_architecture must be ARM64 or X86_64, and must match how the image was built - a mismatch fails at runtime with `exec format error`, not at plan time."
  }
}

# --- Network ---------------------------------------------------------------------------------------

variable "subnet_ids" {
  description = <<-EOT
    Subnets the Fargate tasks run in. They need egress to grafana.com, the Grafana Cloud write
    endpoints, S3, Secrets Manager, ECR and CloudWatch Logs - so either a NAT path or the
    corresponding VPC endpoints. Public subnets additionally need assign_public_ip.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) > 0
    error_message = "at least one subnet is required."
  }
}

variable "security_group_ids" {
  description = "Security groups for the tasks. Leave empty to have the module create one with egress on 443 only."
  type        = list(string)
  default     = []
}

variable "assign_public_ip" {
  description = "Assign a public IP. Required when subnet_ids are public subnets with no NAT."
  type        = bool
  default     = false
}

# --- Schedule --------------------------------------------------------------------------------------

variable "schedules_enabled" {
  description = <<-EOT
    Master switch for every schedule. When false the tasks, roles and storage are all created but
    nothing fires, so `terraform apply` is safe to run before anyone has reviewed what the collector
    would write. Individual tiers can also be disabled in `var.tiers`.
  EOT
  type        = bool
  default     = true
}

variable "schedule_timezone" {
  description = "Timezone for the cron expressions. UTC keeps the T4 diff intervals honest across DST."
  type        = string
  default     = "UTC"
}

variable "tiers" {
  description = <<-EOT
    The four scan tiers. Each becomes one task definition and one EventBridge schedule.

    Separate task definitions rather than one shared definition with per-schedule overrides, because
    EventBridge Scheduler's ECS target has NO container_overrides field - the AWS `EcsParameters` type
    does not support it. That constraint turns out to be useful: each tier gets its own sizing, and T3
    genuinely needs more memory than T1.

    `deadline_seconds` is the collector's own internal deadline and must stay shorter than the
    interval, so a slow scan cannot still be running when the next one fires. ECS has no max-runtime
    setting, so this is the only thing that bounds a run.
  EOT
  type = map(object({
    schedule_expression = string
    cpu                 = optional(number, 512)
    memory              = optional(number, 1024)
    deadline_seconds    = optional(number)
    enabled             = optional(bool, true)
    description         = optional(string, "")
  }))

  default = {
    # Hourly. One gcom call plus carry-forward, so it is cheap; it exists to keep T3's series resolvable
    # between runs and the dead-man's switch fresh.
    t1 = {
      schedule_expression = "cron(5 * * * ? *)"
      cpu                 = 512
      memory              = 1024
      deadline_seconds    = 900
      description         = "Hourly inventory + carry-forward of slower-tier series"
    }
    # Daily. The heaviest user of gcom by far (~813 calls), which is why it is not hourly.
    t2 = {
      schedule_expression = "cron(20 3 * * ? *)"
      cpu                 = 1024
      memory              = 2048
      deadline_seconds    = 3600
      description         = "Daily per-stack identity, plugin and service-account detail"
    }
    # Every 6 hours. Data plane across every stack: cardinality and Adaptive recommendations.
    # These signals can move within a day, and metrics are billed on active series rather than reads.
    #
    # **`deadline_seconds` must stay strictly SHORTER than the interval**, or a slow run overlaps the next
    # and both write `latest.json`. 3600 keeps the lock TTL (deadline + 5 min) well inside one interval.
    t3 = {
      schedule_expression = "cron(40 2,8,14,20 * * ? *)"
      cpu                 = 1024
      memory              = 4096
      deadline_seconds    = 3600
      description         = "6-hourly data-plane sweep"
    }
    # Daily, well after the 02:40 T3. Reads prior scans from S3 and makes no API calls at all, so its only
    # cost is a short Fargate task. Publishes both a week-over-week and a day-over-day diff.
    t4 = {
      schedule_expression = "cron(0 9 * * ? *)"
      cpu                 = 512
      memory              = 1024
      deadline_seconds    = 900
      description         = "Daily estate diff - 7-day and 1-day windows"
    }
  }
}

variable "schedule_retry_attempts" {
  description = <<-EOT
    EventBridge Scheduler retries for a failed RunTask *invocation*. This retries starting the task,
    not a scan that ran and exited non-zero - a scan that fails on coverage must not be silently
    re-run, because the second attempt spends the same rate-limit budget against the same wall.
  EOT
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for task output."
  type        = number
  default     = 30
}

# --- Optional CloudWatch Logs -> Grafana Cloud Firehose path --------------------------------------

variable "firehose_logs_enabled" {
  description = <<-EOT
    Create an AWS Data Firehose delivery stream for the ECS task log group, its failed-record S3
    backup, and the required IAM roles. Default off: this is an additional delivery path, not part of
    the collector's core contract. Enabling this does NOT connect the CloudWatch log group; use the
    separate firehose_log_subscription_enabled switch only after one manual delivery has succeeded.
  EOT
  type        = bool
  default     = false
}

variable "firehose_log_subscription_enabled" {
  description = <<-EOT
    Connect the ECS CloudWatch log group to the Firehose stream. Keep false for the first apply so the
    stream can be tested with `aws firehose put-record` before any live task logs are forwarded. This
    may be true only when firehose_logs_enabled is also true.
  EOT
  type        = bool
  default     = false
}

variable "firehose_access_key_secret_arn" {
  description = <<-EOT
    ARN of an ADOPTED, dedicated Secrets Manager secret whose SecretString is a JSON object with the
    Grafana Firehose access key in `api_key`. Firehose requires that field for HTTP destinations and
    cannot select the credential from the collector's differently shaped multi-key secret. The module
    never reads or creates this secret and the value never enters Terraform state. Required only when
    firehose_logs_enabled is true.
  EOT
  type        = string
  default     = ""
}

variable "firehose_access_key_secret_kms_key_arn" {
  description = <<-EOT
    Optional customer-managed KMS key ARN used by the adopted Firehose access-key secret. Leave blank
    when the secret uses the default AWS Secrets Manager key. When set, the Firehose delivery role is
    granted kms:Decrypt and kms:DescribeKey on this key alone.
  EOT
  type        = string
  default     = ""
}

variable "firehose_failed_record_retention_days" {
  description = "Retention for objects Firehose could not deliver to Grafana Cloud."
  type        = number
  default     = 7

  validation {
    condition     = var.firehose_failed_record_retention_days >= 1
    error_message = "firehose_failed_record_retention_days must be at least 1."
  }
}

# --- Grafana-side reader ---------------------------------------------------------------------------

variable "create_views_reader_user" {
  description = <<-EOT
    Create the IAM user the Grafana Infinity datasource authenticates as. It gets GetObject on
    `views/*` and nothing else - deliberately NOT `scans/*`, which holds raw per-user identity detail
    that no dashboard needs. Verify with `aws iam simulate-principal-policy`, not by reading the JSON.

    No access key is created: that would put a long-lived credential in Terraform state. Mint it out
    of band and store it alongside the tokens.
  EOT
  type        = bool
  default     = true
}

# --- Per-stack reader credentials (PLAN 17D) -------------------------------------------------------

variable "stack_token_prefix" {
  description = "SSM Parameter Store path prefix holding one SecureString per stack, each carrying that stack's read-only Assistant/service-account reader token. Must match `collector/provision.py::SSM_PREFIX` - the collector reads these by computed path, so a mismatch fails as an auth error against Grafana rather than as a missing parameter."
  type        = string
  default     = "/gcinsight/stack-token"

  validation {
    condition     = startswith(var.stack_token_prefix, "/") && !endswith(var.stack_token_prefix, "/")
    error_message = "stack_token_prefix must start with / and must not end with one: the slug is appended as `<prefix>/<slug>`."
  }
}

variable "metric_prefix" {
  description = "External Prometheus metric prefix. Core remains canonical gcinsight; consumers may preserve an established public namespace."
  type        = string
  default     = "gcinsight"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_.-]*$", var.metric_prefix))
    error_message = "metric_prefix must be a Prometheus-safe lower-case identifier prefix."
  }
}

variable "loki_job" {
  description = "Bounded Loki stream job identity for this consumer."
  type        = string
  default     = "gcinsight"
}

variable "collector_user_agent" {
  description = "HTTP User-Agent used by the Mimir remote writer."
  type        = string
  default     = "gcinsight-collector/1 (+grafana-ps)"
}

variable "role_name" {
  description = "Stable custom-role name reconciled on every stack. Changing it creates a parallel identity."
  type        = string
  default     = "custom:gcinsight.reader"
}

variable "role_display" {
  description = "Stable display name of the per-stack custom reader role."
  type        = string
  default     = "Grafana Cloud Org Insights reader"
}

variable "role_group" {
  description = "Stable group label of the per-stack custom reader role."
  type        = string
  default     = "Grafana Cloud Org Insights"
}

variable "reader_service_account_name" {
  description = "Stable basic-role-None service-account name reconciled on every stack."
  type        = string
  default     = "gcinsight-data"
}

variable "admin_service_account_name" {
  description = "Stable transient Admin service-account name used only during reconciliation."
  type        = string
  default     = "gcinsight-insights-provisioner"
}

variable "token_name_prefix" {
  description = "Stable org-unique prefix for per-stack token names."
  type        = string
  default     = "gcinsight-data"
}

variable "scan_runtime_config_digest" {
  description = "SHA-256 of the canonical non-secret scan-task environment projection. Empty permits generic defaults."
  type        = string
  default     = ""
}

variable "provisioner_runtime_config_digest" {
  description = "SHA-256 of the canonical non-secret provisioner environment projection. Empty permits generic defaults."
  type        = string
  default     = ""
}

variable "require_explicit_consumer_config" {
  description = "Require complete runtime projection digests and refuse generic-default fallback."
  type        = bool
  default     = false
}

variable "create_provisioner" {
  description = "Create the provisioner IAM role, task definition and schedule. The provisioner holds the only credential in this project that can write to gcom (stack-service-accounts:write), so it is a separate role from the collector's and is opt-in."
  type        = bool
  default     = false
}

variable "provisioner_secret_key" {
  description = "JSON key inside the secret holding the provisioner token (access policy `gcinsight-provisioner`: stacks:read + stack-service-accounts:write, org realm). Deliberately a different key from the collector's, so the collector's task definition cannot pick it up by accident."
  type        = string
  default     = "GCINSIGHT_PROVISION_TOKEN"
}

variable "provisioner_schedule_expression" {
  description = "When to reconcile per-stack credentials. Daily, not hourly: provisioning is a gcom write path and gcom is paced at 6 req/s per credential. Healthy steady state is reads and zero writes."
  type        = string
  default     = "cron(35 3 * * ? *)"
}

variable "provisioner_enabled" {
  description = "Whether the daily reconciliation schedule is ENABLED. Disable to pause reconciliation without destroying it - existing credentials keep working, and new stacks simply go unprovisioned until it is re-enabled."
  type        = bool
  default     = true
}

variable "provision_opt_out" {
  description = "Stack slugs to leave alone - ones the org has asked not to be provisioned against. These render as `opted out` in the coverage view rather than as failures; without that the missing-credential alert fires forever on a stack somebody deliberately excluded. This is the ONE piece of state that is genuine policy rather than discoverable, which is why it is configuration at all."
  type        = list(string)
  default     = []
}

variable "provisioner_cpu" {
  description = "Fargate CPU units for the provisioner. It is I/O bound on a 6 req/s rate limit, so the smallest size is correct."
  type        = string
  default     = "256"
}

variable "provisioner_memory" {
  description = "Fargate memory (MiB) for the provisioner."
  type        = string
  default     = "512"
}
