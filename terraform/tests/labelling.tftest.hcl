mock_provider "aws" {
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

run "reject_low_coverage" {
  command = plan
  variables { label_inventory_tunables = "{\"coverage_floor\":0.79}" }
  expect_failures = [var.label_inventory_tunables]
}
run "reject_unknown_rule" {
  command = plan
  variables { label_inventory_tunables = "{\"thresholds\":{\"unknown\":{\"warn\":1}}}" }
  expect_failures = [var.label_inventory_tunables]
}
run "reject_published_limit" {
  command = plan
  variables { label_inventory_tunables = "{\"thresholds\":{\"M6\":{\"warn\":31,\"high\":41}}}" }
  expect_failures = [var.label_inventory_tunables]
}
run "reject_incomplete_bands" {
  command = plan
  variables { label_inventory_tunables = "{\"thresholds\":{\"M4\":{\"warn\":200}}}" }
  expect_failures = [var.label_inventory_tunables]
}
run "reject_unordered_bands" {
  command = plan
  variables { label_inventory_tunables = "{\"thresholds\":{\"M4\":{\"warn\":2000,\"high\":100,\"critical\":10000}}}" }
  expect_failures = [var.label_inventory_tunables]
}
run "reject_non_object_thresholds" {
  command = plan
  variables { label_inventory_tunables = "{\"thresholds\":[]}" }
  expect_failures = [var.label_inventory_tunables]
}
run "reject_boolean_floor" {
  command = plan
  variables { label_inventory_tunables = "{\"size_floor\":true}" }
  expect_failures = [var.label_inventory_tunables]
}
run "reject_large_budget" {
  command = plan
  variables { label_inventory_budget_seconds = 901 }
  expect_failures = [var.label_inventory_budget_seconds]
}
run "reject_fractional_budget" {
  command = plan
  variables { label_inventory_budget_seconds = 1.5 }
  expect_failures = [var.label_inventory_budget_seconds]
}
run "reject_static_values" {
  command = plan
  variables { label_inventory_static_names = ["contains a value"] }
  expect_failures = [var.label_inventory_static_names]
}
run "reject_duplicate_static_names" {
  command = plan
  variables { label_inventory_static_names = ["host", "host"] }
  expect_failures = [var.label_inventory_static_names]
}
run "default_off_projection" {
  command = plan
  assert {
    condition     = var.label_inventory_enabled == false && var.label_inventory_budget_seconds == 900
    error_message = "Label inventory must preserve default-off enablement and the bounded source slice."
  }
  assert {
    condition = alltrue([for definition in values(aws_ecs_task_definition.scan) :
      contains(jsondecode(definition.container_definitions)[0].environment, { name = "GCINSIGHT_LABEL_INVENTORY_ENABLED", value = "0" })
    ])
    error_message = "Real assembled ECS container environments must keep label inventory off."
  }
}
run "valid_policy_projection" {
  command = plan
  variables {
    label_inventory_enabled        = true
    label_inventory_budget_seconds = 60
    label_inventory_static_names   = ["custom_host"]
    label_inventory_tunables       = "{\"coverage_floor\":0.9,\"size_floor\":200,\"thresholds\":{\"M4\":{\"warn\":200,\"high\":2000,\"critical\":20000}}}"
  }
  assert {
    condition = alltrue([for definition in values(aws_ecs_task_definition.scan) :
      contains(jsondecode(definition.container_definitions)[0].environment, { name = "GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS", value = "60" }) &&
      contains(jsondecode(definition.container_definitions)[0].environment, { name = "GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES", value = "[\"custom_host\"]" })
    ])
    error_message = "Real ECS task definitions must project the selected source budget and allowlist."
  }
}
