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

run "default_off" {
  command = plan
  assert {
    condition     = toset(aws_ecs_cluster.this.setting) == toset([{ name = "containerInsights", value = "disabled" }])
    error_message = "Container Insights must stay default-off."
  }
}
run "enabled_policy" {
  command = plan
  variables { container_insights_enabled = true }
  assert {
    condition     = toset(aws_ecs_cluster.this.setting) == toset([{ name = "containerInsights", value = "enabled" }])
    error_message = "Explicit policy must preserve the enabled capture setting."
  }
}

run "manifest_enabled_policy" {
  command = plan
  variables {
    name_prefix      = null
    secret_name      = ""
    create_secret    = true
    grafana_org_id   = null
    write_stack_slug = null
    mimir_write_url  = null
    mimir_tenant     = null
    loki_write_url   = null
    loki_tenant      = null
    consumer_manifest = merge(jsondecode(file("tests/fixtures/manifest-full.json")), {
      aws = merge(jsondecode(file("tests/fixtures/manifest-full.json")).aws, { container_insights_enabled = true })
    })
  }
  assert {
    condition     = toset(aws_ecs_cluster.this.setting) == toset([{ name = "containerInsights", value = "enabled" }])
    error_message = "Manifest policy must reach the cluster setting."
  }
}
