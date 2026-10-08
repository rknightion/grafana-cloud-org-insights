output "bucket_name" {
  description = "S3 bucket holding scans/, views/, locks/, state/ and the optional config/ratecard.csv."
  value       = local.bucket_name
}

output "cluster_arn" {
  description = "ECS cluster the scan tasks run in."
  value       = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  description = "ECS cluster name, for `aws ecs run-task --cluster`."
  value       = aws_ecs_cluster.this.name
}

output "task_definition_arns" {
  description = "Task definition ARN per tier, including revision."
  value       = { for k, v in aws_ecs_task_definition.scan : k => v.arn }
}

output "task_definition_families" {
  description = "Task definition family per tier. Use this with `run-task`, not the pinned ARN, to get the current revision."
  value       = { for k, v in aws_ecs_task_definition.scan : k => v.family }
}

output "schedule_names" {
  description = "EventBridge Scheduler schedule name per tier. Every tier has one; see schedule_states for whether it fires."
  value       = { for k, v in aws_scheduler_schedule.scan : k => v.name }
}

output "schedule_states" {
  description = "ENABLED or DISABLED per tier. A tier that is not running should be checked here first."
  value       = local.schedule_state
}

output "ecr_repository_url" {
  description = "ECR repository to push the collector image to, when this module created one."
  value       = var.create_ecr_repository ? aws_ecr_repository.collector[0].repository_url : null
}

output "secret_name" {
  description = "Secrets Manager secret the tokens must be written to. The values are NOT managed by Terraform."
  value       = local.secret_name
}

output "task_role_arn" {
  description = "Collector task identity: S3 object read/write/delete on scans/, views/, locks/ and state/, bucket listing, read-only config/ratecard.csv access, SSM reader-credential path reads and KMS decrypt scoped by the parameter ARN encryption context. CAP secrets are injected by the execution role, not read by this role."
  value       = aws_iam_role.task.arn
}

output "views_reader_user_name" {
  description = "IAM user for the Grafana Infinity datasource. Mint its access key out of band."
  value       = local.inputs.create_views_reader_user ? aws_iam_user.views_reader[0].name : null
}

output "log_group_name" {
  description = "CloudWatch Logs group carrying task output."
  value       = aws_cloudwatch_log_group.tasks.name
}

output "firehose_delivery_stream_name" {
  description = "Optional ECS-log Firehose stream name. Null while firehose_logs_enabled is false."
  value       = local.inputs.firehose_logs_enabled ? aws_kinesis_firehose_delivery_stream.ecs_logs[0].name : null
}

output "firehose_delivery_stream_arn" {
  description = "Optional ECS-log Firehose stream ARN. Null while firehose_logs_enabled is false."
  value       = local.inputs.firehose_logs_enabled ? aws_kinesis_firehose_delivery_stream.ecs_logs[0].arn : null
}

output "firehose_failed_record_bucket_name" {
  description = "Optional bucket holding only Firehose records Grafana Cloud refused. Null while disabled."
  value       = local.inputs.firehose_logs_enabled ? aws_s3_bucket.firehose_failed[0].bucket : null
}

output "firehose_loki_endpoint" {
  description = "Grafana Cloud AWS-log endpoint derived from loki_write_url; useful when verifying the staged delivery."
  value       = local.inputs.firehose_logs_enabled ? local.firehose_loki_endpoint : null
}

output "firehose_log_subscription_enabled" {
  description = "Whether the live ECS CloudWatch log group is connected to Firehose, distinct from stream existence."
  value       = local.inputs.firehose_log_subscription_enabled
}

output "run_task_command" {
  description = "Copy-paste command to run one tier by hand - the backfill and smoke-test path."
  value = format(
    "aws ecs run-task --cluster %s --launch-type FARGATE --task-definition <family from task_definition_families> --propagate-tags TASK_DEFINITION --network-configuration 'awsvpcConfiguration={subnets=[%s],securityGroups=[%s],assignPublicIp=%s}' --region %s",
    aws_ecs_cluster.this.name,
    join(",", var.subnet_ids),
    join(",", local.security_group_ids),
    local.inputs.assign_public_ip ? "ENABLED" : "DISABLED",
    data.aws_region.current.region,
  )
}

output "task_environments" {
  description = "Non-secret container environment each task definition renders, keyed by tier and `provisioner` (when created). Compare it with `bin/consumer_manifest.py env` when a task refuses to start on a projection digest mismatch."
  value = merge(
    { for name, task in aws_ecs_task_definition.scan : name => { for entry in jsondecode(task.container_definitions)[0].environment : entry.name => entry.value } },
    { for task in aws_ecs_task_definition.provisioner : "provisioner" => { for entry in jsondecode(task.container_definitions)[0].environment : entry.name => entry.value } },
  )
}

output "task_secret_references" {
  description = "Secret selectors (`<secret ARN>:<JSON key>::`, never values) each task definition injects, keyed by tier and `provisioner` (when created)."
  value = merge(
    { for name, task in aws_ecs_task_definition.scan : name => { for entry in jsondecode(task.container_definitions)[0].secrets : entry.name => entry.valueFrom } },
    { for task in aws_ecs_task_definition.provisioner : "provisioner" => { for entry in jsondecode(task.container_definitions)[0].secrets : entry.name => entry.valueFrom } },
  )
}

output "schedules" {
  description = "Expression, timezone and state of every schedule, keyed by tier and `provisioner` (when created)."
  value = merge(
    { for name, schedule in aws_scheduler_schedule.scan : name => { expression = schedule.schedule_expression, timezone = schedule.schedule_expression_timezone, state = schedule.state } },
    { for schedule in aws_scheduler_schedule.provisioner : "provisioner" => { expression = schedule.schedule_expression, timezone = schedule.schedule_expression_timezone, state = schedule.state } },
  )
}

output "tags" {
  description = "Tags applied to every taggable resource: `tags`, with the manifest's Purpose and Namespace values over them in manifest mode."
  value       = local.tags
}

output "created_resources" {
  description = "Which optional resources this deployment creates rather than adopts or omits."
  value = {
    bucket                = length(aws_s3_bucket.data) > 0
    bucket_configuration  = length(aws_s3_bucket_policy.data) > 0
    secret                = length(aws_secretsmanager_secret.tokens) > 0
    views_reader_user     = length(aws_iam_user.views_reader) > 0
    provisioner           = length(aws_ecs_task_definition.provisioner) > 0
    firehose_stream       = length(aws_kinesis_firehose_delivery_stream.ecs_logs) > 0
    firehose_subscription = length(aws_cloudwatch_log_subscription_filter.ecs_logs) > 0
    ecr_repository        = length(aws_ecr_repository.collector) > 0
  }
}
