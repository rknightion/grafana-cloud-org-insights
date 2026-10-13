# Isolated, default-off observer. Application code has no Grafana credentials or source IAM.
resource "aws_iam_role" "outcome_observer" {
  count              = local.inputs.outcome_observer_enabled ? 1 : 0
  name               = "${local.inputs.name_prefix}-outcome-observer"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "outcome_observer" {
  count = local.inputs.outcome_observer_enabled ? 1 : 0
  statement {
    sid       = "ReadDeploymentOutcomeLogs"
    actions   = ["logs:FilterLogEvents"]
    resources = ["${trimsuffix(aws_cloudwatch_log_group.tasks.arn, ":*")}:*"]
  }
  statement {
    sid       = "ConditionalOutcomeObjects"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = [for tier in ["t1", "t2", "t3", "t4"] : "${local.bucket_arn}/views/outcomes/${tier}.json"]
  }
}

resource "aws_iam_role_policy" "outcome_observer" {
  count  = local.inputs.outcome_observer_enabled ? 1 : 0
  name   = "observe-deployment-outcomes"
  role   = aws_iam_role.outcome_observer[0].id
  policy = data.aws_iam_policy_document.outcome_observer[0].json
}

# Separate agent role has image/log access, with no collector secret-reading policy attached.
resource "aws_iam_role" "outcome_observer_execution" {
  count              = local.inputs.outcome_observer_enabled ? 1 : 0
  name               = "${local.inputs.name_prefix}-observer-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}
resource "aws_iam_role_policy_attachment" "outcome_observer_execution" {
  count      = local.inputs.outcome_observer_enabled ? 1 : 0
  role       = aws_iam_role.outcome_observer_execution[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_ecs_task_definition" "outcome_observer" {
  count                    = local.inputs.outcome_observer_enabled ? 1 : 0
  family                   = "${local.inputs.name_prefix}-outcome-observer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.outcome_observer_execution[0].arn
  task_role_arn            = aws_iam_role.outcome_observer[0].arn
  tags                     = local.tags

  lifecycle {
    precondition {
      condition     = local.manage_bucket_config
      error_message = "Outcome observer requires managed bucket retention: create the bucket or explicitly opt into manage_adopted_bucket_config before enabling it."
    }
    precondition {
      condition = !local.inputs.firehose_log_subscription_enabled || try(
        aws_cloudwatch_log_subscription_filter.ecs_logs[0].filter_pattern == "-\"gcinsight_outcome\"", false,
      )
      error_message = "Forwarded task logs must exclude the private gcinsight_outcome discriminator before enabling outcome recording."
    }
    precondition {
      condition     = local.image != ""
      error_message = "Outcome observer requires a collector image."
    }
  }
  # The observer and collector definitions become runnable only after private events are excluded.
  depends_on = [aws_cloudwatch_log_subscription_filter.ecs_logs]

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = local.inputs.task_architecture
  }
  container_definitions = jsonencode([{
    name       = "status"
    image      = local.image
    essential  = true
    entryPoint = ["python3", "-m", "collector.observer"]
    command    = ["--bucket", local.bucket_name, "--region", data.aws_region.current.region, "--log-group", aws_cloudwatch_log_group.tasks.name]
    environment = [
      { name = "AWS_REGION", value = data.aws_region.current.region },
      { name = "AWS_DEFAULT_REGION", value = data.aws_region.current.region },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.tasks.name
        "awslogs-region"        = data.aws_region.current.region
        "awslogs-stream-prefix" = "observer"
      }
    }
  }])
}

resource "aws_iam_role" "outcome_observer_scheduler" {
  count              = local.inputs.outcome_observer_enabled ? 1 : 0
  name               = "${local.inputs.name_prefix}-observer-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = local.tags
}
data "aws_iam_policy_document" "outcome_observer_scheduler" {
  count = local.inputs.outcome_observer_enabled ? 1 : 0
  statement {
    actions   = ["ecs:RunTask"]
    resources = ["${aws_ecs_task_definition.outcome_observer[0].arn_without_revision}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.outcome_observer[0].arn, aws_iam_role.outcome_observer_execution[0].arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}
resource "aws_iam_role_policy" "outcome_observer_scheduler" {
  count  = local.inputs.outcome_observer_enabled ? 1 : 0
  name   = "run-outcome-observer"
  role   = aws_iam_role.outcome_observer_scheduler[0].id
  policy = data.aws_iam_policy_document.outcome_observer_scheduler[0].json
}
resource "aws_scheduler_schedule" "outcome_observer" {
  count                        = local.inputs.outcome_observer_enabled ? 1 : 0
  name                         = "${local.inputs.name_prefix}-outcome-observer"
  group_name                   = "default"
  schedule_expression          = "rate(15 minutes)"
  schedule_expression_timezone = local.inputs.schedule_timezone
  state                        = local.inputs.schedules_enabled ? "ENABLED" : "DISABLED"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_ecs_cluster.this.arn
    role_arn = aws_iam_role.outcome_observer_scheduler[0].arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.outcome_observer[0].arn
      launch_type         = "FARGATE"
      task_count          = 1
      platform_version    = "1.4.0"
      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = local.security_group_ids
        assign_public_ip = local.inputs.assign_public_ip
      }
    }
    retry_policy {
      maximum_retry_attempts       = var.schedule_retry_attempts
      maximum_event_age_in_seconds = 300
    }
  }
}
