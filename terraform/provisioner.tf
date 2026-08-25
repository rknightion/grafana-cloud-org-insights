# The per-stack credential provisioner (PLAN 17D).
#
# A SEPARATE task, role and schedule from the collector, and the separation is the security property:
# this is the only thing in the project holding a credential that can WRITE to gcom
# (`stack-service-accounts:write`). The collector reads SSM and never sees that token.
#
# It runs DAILY, not hourly, and the reason is measured rather than aesthetic. gcom is one shared control
# plane paced at 6 req/s; an unthrottled estate-wide read sweep can draw HTTP 429s and
# covered only 71.6% of the estate. Provisioning is ~5 writes per stack, so a per-run mint-and-destroy
# model would spend ~1,600 gcom writes an hour and be throttled or flagged. Steady state here is ~270
# reads and ZERO writes: the run only writes for a stack that is new, or whose credential is broken.
#
# The one-day delay for a brand-new stack is the accepted cost of that. Coverage is published as
# `gcinsight_stacks_missing_credential` plus the AGE of the oldest gap, and the alert is on the age -
# a count above zero is normal for a few hours after a stack is created, while a gap that persists past
# two runs means this job is broken.

resource "aws_ecs_task_definition" "provisioner" {
  count = var.create_provisioner ? 1 : 0

  family                   = "${var.name_prefix}-provisioner"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.provisioner_cpu
  memory                   = var.provisioner_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.provisioner[0].arn
  tags                     = local.tags

  lifecycle {
    precondition {
      condition     = local.image != ""
      error_message = "No container image: set var.image, or leave create_ecr_repository = true so the module can default to the repository it creates."
    }
  }

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.task_architecture
  }

  container_definitions = jsonencode([
    {
      name      = "provisioner"
      image     = local.image
      essential = true

      # The image's ENTRYPOINT is `python3 /app/scan.py`, so it has to be replaced rather than appended
      # to. Leaving it and passing arguments would run the COLLECTOR with provisioner arguments, which
      # fails as an unrecognised-argument error rather than doing nothing.
      entryPoint = ["python3", "/app/bin/provision.py"]
      command    = []

      environment = [
        { name = "GCINSIGHT_ORG_ID", value = var.grafana_org_id },
        # Only this stack's reader receives the second exact datasource query scope needed by the
        # capability-adoption collector input. Every other stack stays usage-insights-only.
        { name = "GCINSIGHT_WRITE_STACK", value = var.write_stack_slug },
        # The credential store's region, read by bin/provision.py. Distinct from the bucket region
        # variable so the two can diverge without a code change.
        { name = "GCINSIGHT_SSM_REGION", value = data.aws_region.current.region },
        { name = "GCINSIGHT_STACK_TOKEN_PREFIX", value = var.stack_token_prefix },
        { name = "GCINSIGHT_ROLE_NAME", value = var.role_name },
        { name = "GCINSIGHT_ROLE_DISPLAY", value = var.role_display },
        { name = "GCINSIGHT_ROLE_GROUP", value = var.role_group },
        { name = "GCINSIGHT_READER_SA_NAME", value = var.reader_service_account_name },
        { name = "GCINSIGHT_ADMIN_SA_NAME", value = var.admin_service_account_name },
        { name = "GCINSIGHT_TOKEN_NAME_PREFIX", value = var.token_name_prefix },
        { name = "GCINSIGHT_RUNTIME_CONFIG_DIGEST", value = var.provisioner_runtime_config_digest },
        { name = "GCINSIGHT_REQUIRE_EXPLICIT_CONFIG", value = var.require_explicit_consumer_config ? "1" : "0" },
        { name = "AWS_REGION", value = data.aws_region.current.region },
        { name = "AWS_DEFAULT_REGION", value = data.aws_region.current.region },
        # Comma-separated slugs to leave alone. Empty by default. These
        # render as `opted out` in the coverage view rather than as failures - without that, the
        # missing-credential alert would fire forever on a stack we were told to leave alone.
        { name = "GCINSIGHT_OPT_OUT", value = join(",", var.provision_opt_out) },
      ]

      # Deliberately NOT given GCINSIGHT_READ_TOKEN or GCINSIGHT_WRITE_TOKEN. This task provisions; it does not
      # scan and it does not publish. See the grammar note in ecs.tf for the trailing colons.
      secrets = [
        { name = "GCINSIGHT_PROVISION_TOKEN", valueFrom = "${local.secret_arn}:${var.provisioner_secret_key}::" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.tasks.name
          "awslogs-region"        = data.aws_region.current.region
          "awslogs-stream-prefix" = "provisioner"
        }
      }
    }
  ])
}

resource "aws_scheduler_schedule" "provisioner" {
  count = var.create_provisioner ? 1 : 0

  name        = "${var.name_prefix}-provisioner"
  description = "Reconcile the per-stack read-only reader credential across the estate"
  group_name  = "default"

  schedule_expression          = var.provisioner_schedule_expression
  schedule_expression_timezone = var.schedule_timezone
  # Gated by BOTH switches. `schedules_enabled` is the platform-wide kill switch, and someone reaching
  # for it to "stop the platform" would not expect a job with estate-wide write authority to keep
  # running. `provisioner_enabled` pauses only this one.
  state = (var.schedules_enabled && var.provisioner_enabled) ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.this.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.provisioner[0].arn
      launch_type         = "FARGATE"
      task_count          = 1
      # 1.4.0 is a floor, not a preference: injecting a single JSON key of a secret requires it. Lower
      # and GCINSIGHT_PROVISION_TOKEN arrives as the whole JSON object rather than failing loudly.
      platform_version        = "1.4.0"
      enable_ecs_managed_tags = true
      propagate_tags          = "TASK_DEFINITION"

      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = local.security_group_ids
        assign_public_ip = var.assign_public_ip
      }
    }

    retry_policy {
      maximum_retry_attempts = var.schedule_retry_attempts
      # Matches schedules.tf: retry the RunTask INVOCATION briefly, never re-run a job that
      # started and exited non-zero - a second pass would spend the same rate-limit budget.
      maximum_event_age_in_seconds = 300
    }
  }
}
