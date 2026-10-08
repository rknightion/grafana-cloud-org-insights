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
  create_bucket    = false
  bucket_name      = "synthetic-adopted"
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

# An adopted bucket stays outside destroy scope; its configuration is managed only on request.
run "adopted_bucket_config_unmanaged_by_default" {
  command = plan
  assert {
    condition     = length(aws_s3_bucket.data) == 0 && length(aws_s3_bucket_lifecycle_configuration.data) == 0 && length(aws_s3_bucket_policy.data) == 0 && length(aws_s3_bucket_versioning.data) == 0
    error_message = "adoption without manage_adopted_bucket_config must manage no bucket configuration"
  }
}

run "adopted_bucket_config_managed_on_request" {
  command = plan
  variables { manage_adopted_bucket_config = true }
  assert {
    condition     = length(aws_s3_bucket.data) == 0
    error_message = "the adopted bucket itself must never be managed"
  }
  assert {
    condition = alltrue([
      aws_s3_bucket_lifecycle_configuration.data[0].bucket == "synthetic-adopted",
      aws_s3_bucket_policy.data[0].bucket == "synthetic-adopted",
      aws_s3_bucket_versioning.data[0].bucket == "synthetic-adopted",
      aws_s3_bucket_server_side_encryption_configuration.data[0].bucket == "synthetic-adopted",
      aws_s3_bucket_public_access_block.data[0].bucket == "synthetic-adopted",
    ])
    error_message = "every bucket configuration resource must target the adopted bucket by name"
  }
  assert {
    condition     = toset([for r in aws_s3_bucket_lifecycle_configuration.data[0].rule : r.id]) == toset(["expire-scans", "expire-label-risk-view", "expire-noncurrent-versions", "abort-incomplete-uploads"])
    error_message = "an adopted bucket must get the same four lifecycle rules as a created one"
  }
}
