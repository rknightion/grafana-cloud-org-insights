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

run "default_off_real_task_environments" {
  command = plan
  assert {
    condition     = !var.loki_volume_enabled && !var.rule_inventory_enabled
    error_message = "Both new input variables must default off."
  }
  assert {
    condition = alltrue([for task in aws_ecs_task_definition.scan :
      contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_LOKI_VOLUME_ENABLED", value = "0" }) &&
      contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_RULE_INVENTORY_ENABLED", value = "0" })
    ])
    error_message = "Both real task flags must render default off in every tier."
  }
}

run "explicit_flags_reach_real_task_environments" {
  command = plan
  variables {
    loki_volume_enabled    = true
    rule_inventory_enabled = true
  }
  assert {
    condition = alltrue([for task in aws_ecs_task_definition.scan :
      contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_LOKI_VOLUME_ENABLED", value = "1" }) &&
      contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_RULE_INVENTORY_ENABLED", value = "1" })
    ])
    error_message = "Both selected bool flags must reach actual ECS environments."
  }
}

run "legacy_manifest_keeps_both_flags_default_off" {
  command = plan
  variables {
    name_prefix       = null
    grafana_org_id    = null
    write_stack_slug  = null
    mimir_write_url   = null
    mimir_tenant      = null
    loki_write_url    = null
    loki_tenant       = null
    create_secret     = true
    secret_name       = ""
    consumer_manifest = jsondecode(file("tests/fixtures/manifest-full.json"))
  }
  assert {
    condition = alltrue([for task in aws_ecs_task_definition.scan :
      contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_LOKI_VOLUME_ENABLED", value = "0" }) &&
      contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_RULE_INVENTORY_ENABLED", value = "0" })
    ])
    error_message = "Old manifest absence must render both flags off without rewriting its digests."
  }
}

run "manifest_flags_override_defaults" {
  command = plan
  variables {
    name_prefix      = null
    grafana_org_id   = null
    write_stack_slug = null
    mimir_write_url  = null
    mimir_tenant     = null
    loki_write_url   = null
    loki_tenant      = null
    create_secret    = true
    secret_name      = ""
    consumer_manifest = merge(jsondecode(file("tests/fixtures/manifest-full.json")), {
      runtime = merge(jsondecode(file("tests/fixtures/manifest-full.json")).runtime, {
        scan = merge(jsondecode(file("tests/fixtures/manifest-full.json")).runtime.scan, {
          GCINSIGHT_LOKI_VOLUME_ENABLED    = "1"
          GCINSIGHT_RULE_INVENTORY_ENABLED = "1"
        })
      })
    })
  }
  assert {
    condition = alltrue([for task in aws_ecs_task_definition.scan :
      contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_LOKI_VOLUME_ENABLED", value = "1" }) &&
      contains(jsondecode(task.container_definitions)[0].environment, { name = "GCINSIGHT_RULE_INVENTORY_ENABLED", value = "1" })
    ])
    error_message = "Manifest flags must reach the actual rendered environments."
  }
}

run "manifest_rejects_noncanonical_flag" {
  command = plan
  variables {
    name_prefix      = null
    grafana_org_id   = null
    write_stack_slug = null
    mimir_write_url  = null
    mimir_tenant     = null
    loki_write_url   = null
    loki_tenant      = null
    create_secret    = true
    secret_name      = ""
    consumer_manifest = merge(jsondecode(file("tests/fixtures/manifest-full.json")), {
      runtime = merge(jsondecode(file("tests/fixtures/manifest-full.json")).runtime, {
        scan = merge(jsondecode(file("tests/fixtures/manifest-full.json")).runtime.scan, {
          GCINSIGHT_RULE_INVENTORY_ENABLED = "true"
        })
      })
    })
  }
  expect_failures = [var.consumer_manifest]
}
