# Fargate cluster, log group, task definitions and the tasks' security group.
#
# Fargate rather than Lambda because two tiers exceed Lambda's 15-minute ceiling by design: the daily
# tier is paced deliberately slowly against a rate-limited control plane, and the data-plane tier sweeps the
# data plane of every stack. An idle Fargate cluster costs nothing, so the cluster existing between runs
# is free.

resource "aws_ecs_cluster" "this" {
  name = local.inputs.name_prefix
  tags = local.tags

  # Manifest mode refuses what would otherwise be silently overridden or ignored. The cluster always
  # exists, so these always run; each is true in explicit mode.
  lifecycle {
    precondition {
      condition     = !local.manifest_mode || length(local.explicit_input_arguments) == 0
      error_message = "consumer_manifest supplies these inputs; remove the explicit arguments: ${join(", ", local.explicit_input_arguments)}."
    }
    precondition {
      condition     = !local.manifest_mode || length(local.explicit_tier_schedules) == 0
      error_message = "consumer_manifest supplies tier schedules through aws.<tier>_schedule; remove schedule_expression from tiers: ${join(", ", local.explicit_tier_schedules)}."
    }
    precondition {
      condition     = length(local.manifest_schedule_orphans) == 0
      error_message = "consumer_manifest schedules a tier that tiers does not declare: ${join(", ", local.manifest_schedule_orphans)}."
    }
  }

  setting {
    # Container Insights is off: the useful signal for a scheduled batch job is its own emitted metrics
    # and the dead-man's switch, not per-task CPU curves, and Insights is billed per metric.
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_cloudwatch_log_group" "tasks" {
  name              = "/aws/ecs/${local.inputs.name_prefix}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

# Created only when the caller supplies no security groups. Egress on 443 only - everything the
# collector talks to is HTTPS, and the read client refuses a non-TLS endpoint by construction anyway.
resource "aws_security_group" "tasks" {
  count = length(var.security_group_ids) > 0 ? 0 : 1

  name        = "${local.inputs.name_prefix}-tasks"
  description = "Egress-only for ${local.inputs.name_prefix} collector tasks"
  vpc_id      = data.aws_subnet.first[0].vpc_id
  tags        = local.tags

  egress {
    description = "HTTPS to grafana.com, the Grafana Cloud write endpoints, and AWS APIs"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # No ingress rule at all. Nothing connects to a scan.
}

# The VPC is derived from the subnets rather than taken as a variable, so the two cannot disagree - a
# security group in the wrong VPC fails at RunTask with an error that names neither.
data "aws_subnet" "first" {
  count = length(var.security_group_ids) > 0 ? 0 : 1

  id = var.subnet_ids[0]
}

# --- Task definitions ------------------------------------------------------------------------------
#
# One per tier. EventBridge Scheduler's ECS target has no container_overrides field, so the tier cannot
# be varied per schedule and must be baked into the definition's `command`.

resource "aws_ecs_task_definition" "scan" {
  for_each = local.tiers

  family                   = "${local.inputs.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  tags                     = local.tags

  lifecycle {
    # Without this, `create_ecr_repository = false` and an empty `image` fail deep inside a local with
    # "index 0 out of range" - an error that names neither variable and sends you reading the module.
    precondition {
      condition     = local.image != ""
      error_message = "No container image: set var.image, or leave create_ecr_repository = true so the module can default to the repository it creates."
    }
    # In manifest mode these three projected values are recorded in the manifest but rendered from the
    # module, so a mismatch would only surface as every task refusing to start on a digest mismatch.
    precondition {
      condition = alltrue([
        try(local.manifest.scan.GCINSIGHT_S3_BUCKET, local.bucket_name) == local.bucket_name,
        try(local.manifest.scan.GCINSIGHT_S3_REGION, data.aws_region.current.region) == data.aws_region.current.region,
        try(local.manifest.scan.GCINSIGHT_SSM_REGION, data.aws_region.current.region) == data.aws_region.current.region,
      ])
      error_message = "consumer_manifest runtime.scan GCINSIGHT_S3_BUCKET must equal the bucket this module renders (aws.bucket_name, or <name_prefix>-data), and GCINSIGHT_S3_REGION and GCINSIGHT_SSM_REGION the provider region."
    }
  }

  runtime_platform {
    operating_system_family = "LINUX"
    # Must match how the image was built. A mismatch is not caught at plan time; the task starts and
    # dies with `exec format error`.
    cpu_architecture = local.inputs.task_architecture
  }

  container_definitions = jsonencode([
    {
      name      = "collector"
      image     = local.image
      essential = true

      # Appended to the image's ENTRYPOINT (`python3 /app/scan.py`). The deadline is passed explicitly
      # rather than left to the collector's own per-tier default, so the value declared in `var.tiers`
      # is the value that actually bounds the run instead of documentation that drifts.
      command = concat(
        ["--tier", each.key],
        each.value.deadline_seconds == null ? [] : ["--deadline-seconds", tostring(each.value.deadline_seconds)],
      )

      environment = [
        { name = "GCINSIGHT_ORG_ID", value = local.inputs.grafana_org_id },
        { name = "GCINSIGHT_WRITE_STACK", value = local.inputs.write_stack_slug },
        { name = "GCINSIGHT_MIMIR_URL", value = local.inputs.mimir_write_url },
        { name = "GCINSIGHT_MIMIR_TENANT", value = local.inputs.mimir_tenant },
        { name = "GCINSIGHT_LOKI_URL", value = local.inputs.loki_write_url },
        { name = "GCINSIGHT_LOKI_TENANT", value = local.inputs.loki_tenant },
        # The collector defaults to a hardcoded bucket for laptop convenience. It MUST be told the
        # deployment's bucket, or it writes somewhere the task role has no permission for and fails with
        # an AccessDenied that reads like a broken policy.
        { name = "GCINSIGHT_S3_BUCKET", value = local.bucket_name },
        { name = "GCINSIGHT_S3_REGION", value = data.aws_region.current.region },
        { name = "GCINSIGHT_SSM_REGION", value = data.aws_region.current.region },
        { name = "GCINSIGHT_STACK_TOKEN_PREFIX", value = local.inputs.stack_token_prefix },
        { name = "GCINSIGHT_METRIC_PREFIX", value = local.inputs.metric_prefix },
        { name = "GCINSIGHT_LOKI_JOB", value = local.inputs.loki_job },
        { name = "GCINSIGHT_USER_AGENT", value = local.inputs.collector_user_agent },
        { name = "GCINSIGHT_OPT_OUT", value = join(",", local.inputs.provision_opt_out) },
        { name = "GCINSIGHT_READER_PRODUCT_READS", value = join(",", local.inputs.provisioner_product_reads) },
        { name = "GCINSIGHT_COVERAGE_SCORE_WEIGHTS", value = jsonencode(local.inputs.coverage_score_weights) },
        { name = "GCINSIGHT_DASHBOARD_DETAIL_ENABLED", value = local.inputs.dashboard_detail_enabled ? "1" : "0" },
        { name = "GCINSIGHT_LABEL_INVENTORY_ENABLED", value = local.inputs.label_inventory_enabled ? "1" : "0" },
        { name = "GCINSIGHT_LOKI_VOLUME_ENABLED", value = local.inputs.loki_volume_enabled ? "1" : "0" },
        { name = "GCINSIGHT_RULE_INVENTORY_ENABLED", value = local.inputs.rule_inventory_enabled ? "1" : "0" },
        { name = "GCINSIGHT_LABEL_INVENTORY_TUNABLES", value = jsonencode(jsondecode(local.inputs.label_inventory_tunables)) },
        { name = "GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES", value = jsonencode(local.inputs.label_inventory_static_names) },
        { name = "GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS", value = tostring(local.inputs.label_inventory_budget_seconds) },
        { name = "GCINSIGHT_EXPECTED_RETENTION_POLICY", value = jsonencode(local.inputs.expected_retention_policy) },
        { name = "GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL", value = local.inputs.fleet_default_scrape_interval },
        { name = "GCINSIGHT_RUNTIME_CONFIG_DIGEST", value = local.inputs.scan_runtime_config_digest },
        { name = "GCINSIGHT_REQUIRE_EXPLICIT_CONFIG", value = local.inputs.require_explicit_consumer_config ? "1" : "0" },
        # The bundled AWS CLI needs a region; without it every S3 call fails with a
        # NoRegionError that reads like a credential problem.
        { name = "AWS_REGION", value = data.aws_region.current.region },
        { name = "AWS_DEFAULT_REGION", value = data.aws_region.current.region },
      ]

      # Injected by the ECS agent, never visible to the task role or in any Terraform output.
      #
      # The full grammar is `<secret-arn>:<json-key>:<version-stage>:<version-id>`, and AWS documents
      # that unused trailing positions MUST still be present as colons to take their defaults. So one
      # JSON key at AWSCURRENT is `<arn>:KEY::` - both trailing colons required.
      #
      # Selecting a JSON key at all needs Fargate platform 1.4.0+, which is why schedules.tf pins that
      # version rather than leaving it unset. A manual `run-task` defaults to LATEST and so clears the
      # floor on its own.
      secrets = [
        { name = "GCINSIGHT_READ_TOKEN", valueFrom = "${local.secret_arn}:${local.inputs.reader_secret_key}::" },
        { name = "GCINSIGHT_WRITE_TOKEN", valueFrom = "${local.secret_arn}:${local.inputs.writer_secret_key}::" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.tasks.name
          "awslogs-region"        = data.aws_region.current.region
          "awslogs-stream-prefix" = each.key
        }
      }
    }
  ])
}
