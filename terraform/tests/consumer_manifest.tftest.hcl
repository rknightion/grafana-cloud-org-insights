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
  mock_resource "aws_kinesis_firehose_delivery_stream" {
    defaults = { arn = "arn:aws:firehose:us-east-1:123456789012:deliverystream/synthetic" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::synthetic-insights-data", id = "synthetic-insights-data" }
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

# The explicit consumer glue, the full manifest and the pruned manifest render the same deployment.
run "manifest_mode_renders_the_explicit_wiring" {
  command = plan
  module {
    source = "./tests/equivalence"
  }

  assert {
    condition     = length(module.explicit.task_environments) == 5 && module.manifest.task_environments == module.explicit.task_environments && module.manifest.task_secret_references == module.explicit.task_secret_references
    error_message = "manifest mode must render the same container environment as explicit wiring for all four tiers and the provisioner"
  }
  assert {
    condition     = length(module.explicit.schedules) == 5 && module.manifest.schedules == module.explicit.schedules
    error_message = "manifest mode must render the same schedule expressions, timezones and states as explicit wiring"
  }
  assert {
    condition     = module.manifest.created_resources == module.explicit.created_resources && module.manifest.tags == module.explicit.tags
    error_message = "manifest mode must apply the same adoption and feature switches as explicit wiring"
  }
  assert {
    condition = alltrue([
      module.manifest.bucket_name == module.explicit.bucket_name,
      module.manifest.secret_name == module.explicit.secret_name,
      module.manifest.cluster_name == module.explicit.cluster_name,
      module.manifest.task_definition_families == module.explicit.task_definition_families,
      module.manifest.run_task_command == module.explicit.run_task_command,
    ])
    error_message = "manifest mode must name the same bucket, secret, cluster and task families as explicit wiring"
  }
  assert {
    condition = alltrue([for name, environment in module.manifest.task_environments :
      environment.GCINSIGHT_REQUIRE_EXPLICIT_CONFIG == "1" &&
      environment.GCINSIGHT_RUNTIME_CONFIG_DIGEST == (name == "provisioner" ? jsondecode(file("tests/fixtures/manifest-full.json")).runtime_projection_digests.provisioner : jsondecode(file("tests/fixtures/manifest-full.json")).runtime_projection_digests.scan)
    ])
    error_message = "manifest mode must force explicit configuration and render the manifest's projection digests"
  }
  assert {
    condition = alltrue([
      module.pruned.task_environments == module.manifest.task_environments,
      module.pruned.schedules == module.manifest.schedules,
      module.pruned.task_secret_references == module.manifest.task_secret_references,
      module.pruned.created_resources == module.manifest.created_resources,
      module.pruned.tags == module.manifest.tags,
      module.pruned.bucket_name == module.manifest.bucket_name,
      module.pruned.secret_name == module.manifest.secret_name,
      module.pruned.run_task_command == module.manifest.run_task_command,
    ])
    error_message = "a pruned manifest must render exactly what the full manifest renders"
  }
  assert {
    condition = alltrue([
      length(module.explicit_distinct.task_environments) == 5,
      module.manifest_distinct.task_environments == module.explicit_distinct.task_environments,
      module.manifest_distinct.schedules == module.explicit_distinct.schedules,
      module.manifest_distinct.task_secret_references == module.explicit_distinct.task_secret_references,
      endswith(module.manifest_distinct.task_secret_references.t1.GCINSIGHT_READ_TOKEN, ":SYNTHETIC_READ::"),
      endswith(module.manifest_distinct.task_secret_references.t1.GCINSIGHT_WRITE_TOKEN, ":SYNTHETIC_WRITE::"),
      endswith(module.manifest_distinct.task_secret_references.provisioner.GCINSIGHT_PROVISION_TOKEN, ":SYNTHETIC_PROVISION::"),
      module.manifest_distinct.created_resources == module.explicit_distinct.created_resources,
      module.manifest_distinct.tags == module.explicit_distinct.tags,
      module.manifest_distinct.bucket_name == module.explicit_distinct.bucket_name,
      module.manifest_distinct.secret_name == module.explicit_distinct.secret_name,
      module.manifest_distinct.run_task_command == module.explicit_distinct.run_task_command,
    ])
    error_message = "with every value distinct, each manifest key must reach the same module input as the explicit glue wires it to"
  }
  assert {
    condition = alltrue([
      module.manifest_distinct.schedules.provisioner.state == "DISABLED",
      module.manifest_distinct.created_resources.firehose_subscription,
      !module.manifest_distinct.created_resources.bucket,
      module.manifest_distinct.task_environments.t1.GCINSIGHT_S3_BUCKET == "synthetic-adopted-bucket",
      module.manifest_distinct.created_resources.bucket_configuration,
      module.manifest_distinct.tags == tomap({ Purpose = "synthetic-purpose", Namespace = "synthetic-cost-namespace", Owner = "synthetic-owner" }),
      module.manifest.tags == tomap({ Purpose = "estate-insights", Namespace = "synthetic-insights" }),
    ])
    error_message = "the distinct manifest must exercise the non-default switches it declares"
  }
}

variables {
  image      = "example.invalid/synthetic@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  subnet_ids = ["subnet-synthetic"]
}

run "manifest_values_reach_typed_resources" {
  command = plan
  variables {
    consumer_manifest = jsondecode(file("tests/fixtures/manifest-pruned.json"))
  }
  assert {
    condition     = alltrue([for task in aws_ecs_task_definition.scan : task.runtime_platform[0].cpu_architecture == "X86_64"]) && aws_ecs_task_definition.provisioner[0].runtime_platform[0].cpu_architecture == "X86_64"
    error_message = "aws.task_architecture must reach every task definition"
  }
  assert {
    condition     = length(aws_secretsmanager_secret.tokens) == 0 && length(aws_s3_bucket.data) == 1 && length(aws_iam_user.views_reader) == 0
    error_message = "the manifest's adoption switches must decide which resources exist"
  }
}

run "explicit_mode_tags_are_the_argument_alone" {
  command = plan
  variables {
    name_prefix      = "synthetic-insights"
    grafana_org_id   = "1"
    write_stack_slug = "synthetic"
    mimir_write_url  = "https://metrics.example.invalid"
    mimir_tenant     = "1"
    loki_write_url   = "https://logs.example.invalid"
    loki_tenant      = "1"
    tags             = { Owner = "synthetic-owner" }
  }
  assert {
    condition     = output.tags == tomap({ Owner = "synthetic-owner" }) && aws_ecs_cluster.this.tags == tomap({ Owner = "synthetic-owner" })
    error_message = "explicit mode must apply the tags argument unchanged"
  }
}

run "explicit_create_bucket_beside_a_manifest_is_refused" {
  command = plan
  variables {
    consumer_manifest = jsondecode(file("tests/fixtures/manifest-pruned.json"))
    create_bucket     = false
  }
  expect_failures = [aws_ecs_cluster.this]
}

run "explicit_assign_public_ip_beside_a_manifest_is_refused" {
  command = plan
  variables {
    consumer_manifest = jsondecode(file("tests/fixtures/manifest-pruned.json"))
    assign_public_ip  = true
  }
  expect_failures = [aws_ecs_cluster.this]
}

run "explicit_rendered_digest_beside_a_manifest_is_refused" {
  command = plan
  variables {
    consumer_manifest          = jsondecode(file("tests/fixtures/manifest-pruned.json"))
    scan_runtime_config_digest = "0000000000000000000000000000000000000000000000000000000000000000"
  }
  expect_failures = [aws_ecs_cluster.this]
}

run "tier_schedule_expression_beside_a_manifest_is_refused" {
  command = plan
  variables {
    consumer_manifest = jsondecode(file("tests/fixtures/manifest-pruned.json"))
    tiers             = { t1 = { schedule_expression = "cron(1 * * * ? *)" } }
  }
  expect_failures = [aws_ecs_cluster.this]
}

run "manifest_schedule_for_an_absent_tier_is_refused" {
  command = plan
  variables {
    consumer_manifest = jsondecode(file("tests/fixtures/manifest-full.json"))
    tiers             = { t1 = {}, t2 = {}, t3 = {} }
  }
  expect_failures = [aws_ecs_cluster.this]
}

run "explicit_mode_arguments_are_exactly_the_non_default_inputs" {
  command = plan
  variables {
    name_prefix      = "synthetic-insights"
    grafana_org_id   = "1"
    write_stack_slug = "synthetic"
    mimir_write_url  = "https://metrics.example.invalid"
    mimir_tenant     = "1"
    loki_write_url   = "https://logs.example.invalid"
    loki_tenant      = "1"
    loki_job         = "synthetic-job"
  }
  # Re-derives local.input_defaults against the real variable defaults: a wrong table entry shows up
  # here as an input that differs from its default although it was never passed.
  assert {
    condition     = toset(local.explicit_input_arguments) == toset(["name_prefix", "grafana_org_id", "write_stack_slug", "mimir_write_url", "mimir_tenant", "loki_write_url", "loki_tenant", "loki_job"])
    error_message = "local.input_defaults must equal the variable defaults"
  }
  assert {
    condition     = toset(keys(local.inputs)) == setunion(toset(keys(local.input_defaults)), toset(["schedules_enabled", "provisioner_enabled"]))
    error_message = "every represented input except the two kill switches must be in the plan-time refusal table"
  }
}

run "kill_switches_are_anded_with_the_manifest" {
  command = plan
  variables {
    consumer_manifest = jsondecode(file("tests/fixtures/manifest-pruned.json"))
    schedules_enabled = false
  }
  assert {
    condition     = alltrue([for schedule in values(output.schedules) : schedule.state == "DISABLED"])
    error_message = "schedules_enabled = false must disable every schedule even when the manifest enables them"
  }
}

run "provisioner_kill_switch" {
  command = plan
  variables {
    consumer_manifest   = jsondecode(file("tests/fixtures/manifest-pruned.json"))
    provisioner_enabled = false
  }
  assert {
    condition     = output.schedules.provisioner.state == "DISABLED" && output.schedules.t1.state == "ENABLED"
    error_message = "provisioner_enabled = false must pause only the provisioner schedule"
  }
}

run "explicit_argument_for_a_required_manifest_input_is_refused" {
  command = plan
  variables {
    consumer_manifest = jsondecode(file("tests/fixtures/manifest-pruned.json"))
    grafana_org_id    = "100001"
  }
  expect_failures = [var.consumer_manifest]
}

run "required_key_cannot_be_omitted" {
  command = plan
  variables {
    consumer_manifest = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")), {
      runtime = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")).runtime, {
        scan = { for name, value in jsondecode(file("tests/fixtures/manifest-pruned.json")).runtime.scan : name => value if name != "GCINSIGHT_MIMIR_URL" }
      })
    })
  }
  expect_failures = [var.consumer_manifest]
}

run "manifest_values_obey_the_input_rules" {
  command = plan
  variables {
    consumer_manifest = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")), {
      runtime = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")).runtime, {
        scan = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")).runtime.scan, { GCINSIGHT_MIMIR_URL = "http://metrics.example.invalid" })
      })
    })
  }
  expect_failures = [var.consumer_manifest]
}

run "manifest_label_tunables_obey_the_input_rule" {
  command = plan
  variables {
    consumer_manifest = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")), {
      runtime = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")).runtime, {
        scan = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")).runtime.scan, { GCINSIGHT_LABEL_INVENTORY_TUNABLES = "{\"coverage_floor\":0.79}" })
      })
    })
  }
  expect_failures = [var.consumer_manifest]
}

run "recorded_bucket_must_be_the_rendered_bucket" {
  command = plan
  variables {
    consumer_manifest = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")), {
      aws = merge(jsondecode(file("tests/fixtures/manifest-pruned.json")).aws, { bucket_name = "synthetic-other-bucket" })
    })
  }
  expect_failures = [aws_ecs_task_definition.scan]
}

run "explicit_mode_still_requires_its_target" {
  command = plan
  variables {
    name_prefix      = "synthetic-insights"
    write_stack_slug = "synthetic"
    mimir_write_url  = "https://metrics.example.invalid"
    mimir_tenant     = "1"
    loki_write_url   = "https://logs.example.invalid"
    loki_tenant      = "1"
  }
  expect_failures = [var.consumer_manifest]
}
