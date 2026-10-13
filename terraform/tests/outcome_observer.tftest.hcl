mock_provider "aws" {
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::synthetic-insights-data" }
  }
  mock_resource "aws_kinesis_firehose_delivery_stream" {
    defaults = { arn = "arn:aws:firehose:us-east-1:123456789012:deliverystream/synthetic" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/ecs/synthetic-insights" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/synthetic" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:cluster/synthetic" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/synthetic:1" }
  }
  mock_data "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:synthetic-abcdef" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
}

variables {
  create_secret    = false
  secret_name      = "synthetic/secret"
  image            = "example.invalid/synthetic@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  name_prefix      = "synthetic-insights"
  grafana_org_id   = "123456"
  write_stack_slug = "synthetic"
  mimir_write_url  = "https://metrics.example.invalid"
  mimir_tenant     = "123456"
  loki_write_url   = "https://logs.example.invalid"
  loki_tenant      = "123456"
  subnet_ids       = ["subnet-synthetic"]
}

run "default_off_no_observer_resources" {
  command = plan
  assert {
    condition     = length(aws_ecs_task_definition.outcome_observer) == 0 && length(aws_scheduler_schedule.outcome_observer) == 0 && length(aws_iam_role.outcome_observer) == 0
    error_message = "Default-off must create no observer compute or role."
  }
  assert {
    condition     = alltrue([for task in aws_ecs_task_definition.scan : contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_OUTCOME_OBSERVER_ENABLED", value = "0" })]) && length([for s in data.aws_iam_policy_document.task.statement : s if s.sid == "ReserveOutcomeObserverWrites"]) == 0
    error_message = "Default-off task recording stays off and adds no collector deny."
  }
}
run "enabled_observer_is_isolated_and_installable" {
  command = plan
  variables {
    outcome_observer_enabled = true
    schedules_enabled        = false
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.outcome_observer[0].container_definitions)[0].entryPoint == ["python3", "-m", "collector.observer"] && jsondecode(aws_ecs_task_definition.outcome_observer[0].container_definitions)[0].command == ["--bucket", "synthetic-insights-data", "--region", "us-east-1", "--log-group", "/aws/ecs/synthetic-insights"]
    error_message = "Rendered entrypoint must override scanner and invoke installed observer with explicit resources."
  }
  assert {
    condition     = !can(jsondecode(aws_ecs_task_definition.outcome_observer[0].container_definitions)[0].secrets) && aws_scheduler_schedule.outcome_observer[0].state == "DISABLED"
    error_message = "Observer has no secret selectors and obeys the schedules kill switch."
  }
  assert {
    condition     = toset(flatten([for s in data.aws_iam_policy_document.outcome_observer[0].statement : s.actions])) == toset(["logs:FilterLogEvents", "s3:GetObject", "s3:PutObject"])
    error_message = "Observer task grants only configured log reads and object CAS access."
  }
  assert {
    condition     = toset(flatten([for s in data.aws_iam_policy_document.outcome_observer[0].statement : s.resources if contains(s.actions, "s3:PutObject")])) == toset([for tier in ["t1", "t2", "t3", "t4"] : "arn:aws:s3:::synthetic-insights-data/views/outcomes/${tier}.json"])
    error_message = "Writer resources must be four exact reserved keys."
  }
  assert {
    condition     = alltrue([for s in data.aws_iam_policy_document.outcome_observer[0].statement : s.resources == toset(["arn:aws:logs:us-east-1:123456789012:log-group:/aws/ecs/synthetic-insights:*"]) if contains(s.actions, "logs:FilterLogEvents")])
    error_message = "Log read must be restricted to configured group."
  }
  assert {
    condition     = length([for s in data.aws_iam_policy_document.task.statement : s if s.effect == "Deny" && s.resources == toset(["arn:aws:s3:::synthetic-insights-data/views/outcomes/*"]) && s.actions == toset(["s3:PutObject", "s3:DeleteObject"])]) == 1
    error_message = "Collector cannot write or delete reserved observer projection."
  }
  assert {
    condition     = length([for r in aws_s3_bucket_lifecycle_configuration.data[0].rule : r if r.id == "expire-outcome-observer" && r.filter[0].prefix == "views/outcomes/" && r.expiration[0].days == 90]) == 1
    error_message = "Outcome prefix must receive targeted finite expiry."
  }
  assert {
    condition     = length([for r in aws_s3_bucket_lifecycle_configuration.data[0].rule : r if r.id == "expire-noncurrent-versions" && r.noncurrent_version_expiration[0].noncurrent_days == 7]) == 1
    error_message = "Outcome noncurrent versions retain the existing seven-day expiry."
  }
  assert {
    condition     = alltrue([for s in data.aws_iam_policy_document.outcome_observer_scheduler[0].statement : s.resources == toset([aws_iam_role.outcome_observer[0].arn, aws_iam_role.outcome_observer_execution[0].arn]) if contains(s.actions, "iam:PassRole")]) && alltrue([for s in data.aws_iam_policy_document.outcome_observer_scheduler[0].statement : s.resources == toset(["${aws_ecs_task_definition.outcome_observer[0].arn_without_revision}:*"]) if contains(s.actions, "ecs:RunTask")])
    error_message = "Scheduler must not pass other roles or run unrelated definitions."
  }
}
run "unmanaged_adopted_bucket_refuses_enablement" {
  command = plan
  variables {
    create_bucket            = false
    bucket_name              = "synthetic-adopted"
    outcome_observer_enabled = true
  }
  expect_failures = [aws_ecs_task_definition.outcome_observer]
}

run "forwarded_task_logs_refuse_unapproved_receipt_audience" {
  command = plan
  variables {
    outcome_observer_enabled          = true
    firehose_logs_enabled             = true
    firehose_log_subscription_enabled = true
    firehose_access_key_secret_arn    = "arn:aws:secretsmanager:us-east-1:123456789012:secret:synthetic-firehose-abcdef"
  }
  expect_failures = [aws_ecs_task_definition.outcome_observer]
}
