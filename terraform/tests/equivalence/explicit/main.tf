# Test fixture: the explicit glue a v0.9 consumer hand-copies from its manifest into module arguments.
# Never a deployment. Re-exports the core module outputs the equivalence test compares.

variable "manifest" {
  type = any
}

variable "image" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "tiers" {
  type = any
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "firehose_access_key_secret_arn" {
  type    = string
  default = ""
}

locals {
  scan = var.manifest.runtime.scan
  prov = var.manifest.runtime.provisioner
  aws  = var.manifest.aws
}

module "insights" {
  source = "../../.."

  name_prefix              = local.aws.name_prefix
  grafana_org_id           = local.scan.GCINSIGHT_ORG_ID
  create_bucket            = local.aws.create_bucket
  bucket_name              = local.aws.bucket_name
  create_secret            = local.aws.create_secret
  secret_name              = local.aws.secret_name
  create_views_reader_user = local.aws.create_views_reader_user

  manage_adopted_bucket_config = try(local.aws.manage_adopted_bucket_config, false)
  tags                         = merge(var.tags, { Purpose = local.aws.purpose_tag, Namespace = local.aws.cost_namespace })

  write_stack_slug = local.scan.GCINSIGHT_WRITE_STACK
  mimir_write_url  = local.scan.GCINSIGHT_MIMIR_URL
  mimir_tenant     = local.scan.GCINSIGHT_MIMIR_TENANT
  loki_write_url   = local.scan.GCINSIGHT_LOKI_URL
  loki_tenant      = local.scan.GCINSIGHT_LOKI_TENANT

  firehose_logs_enabled             = local.aws.firehose_logs_enabled
  firehose_log_subscription_enabled = local.aws.firehose_log_subscription_enabled
  firehose_access_key_secret_arn    = var.firehose_access_key_secret_arn

  subnet_ids       = var.subnet_ids
  assign_public_ip = local.aws.assign_public_ip
  image            = var.image

  schedules_enabled              = local.aws.schedules_enabled
  coverage_score_weights         = jsondecode(local.scan.GCINSIGHT_COVERAGE_SCORE_WEIGHTS)
  dashboard_detail_enabled       = local.scan.GCINSIGHT_DASHBOARD_DETAIL_ENABLED == "1"
  label_inventory_enabled        = local.scan.GCINSIGHT_LABEL_INVENTORY_ENABLED == "1"
  label_inventory_tunables       = local.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES
  label_inventory_static_names   = jsondecode(local.scan.GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES)
  label_inventory_budget_seconds = tonumber(local.scan.GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS)
  expected_retention_policy      = jsondecode(local.scan.GCINSIGHT_EXPECTED_RETENTION_POLICY)
  fleet_default_scrape_interval  = local.scan.GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL

  create_provisioner     = local.aws.create_provisioner
  provisioner_enabled    = local.aws.provisioner_enabled
  reader_secret_key      = local.aws.reader_secret_key
  writer_secret_key      = local.aws.writer_secret_key
  provisioner_secret_key = local.aws.provisioner_secret_key

  stack_token_prefix          = local.scan.GCINSIGHT_STACK_TOKEN_PREFIX
  metric_prefix               = local.scan.GCINSIGHT_METRIC_PREFIX
  loki_job                    = local.scan.GCINSIGHT_LOKI_JOB
  collector_user_agent        = local.scan.GCINSIGHT_USER_AGENT
  provision_opt_out           = compact(split(",", local.scan.GCINSIGHT_OPT_OUT))
  role_name                   = local.prov.GCINSIGHT_ROLE_NAME
  role_display                = local.prov.GCINSIGHT_ROLE_DISPLAY
  role_group                  = local.prov.GCINSIGHT_ROLE_GROUP
  reader_service_account_name = local.prov.GCINSIGHT_READER_SA_NAME
  admin_service_account_name  = local.prov.GCINSIGHT_ADMIN_SA_NAME
  token_name_prefix           = local.prov.GCINSIGHT_TOKEN_NAME_PREFIX
  provisioner_product_reads   = compact(split(",", local.prov.GCINSIGHT_READER_PRODUCT_READS))

  scan_runtime_config_digest        = var.manifest.runtime_projection_digests.scan
  provisioner_runtime_config_digest = var.manifest.runtime_projection_digests.provisioner
  require_explicit_consumer_config  = true

  schedule_timezone               = local.aws.schedule_timezone
  provisioner_schedule_expression = local.aws.provisioner_schedule
  task_architecture               = local.aws.task_architecture

  tiers = { for name, size in var.tiers : name => merge(size, { schedule_expression = local.aws["${name}_schedule"] }) }
}

output "task_environments" {
  value = module.insights.task_environments
}

output "task_secret_references" {
  value = module.insights.task_secret_references
}

output "schedules" {
  value = module.insights.schedules
}

output "created_resources" {
  value = module.insights.created_resources
}

output "tags" {
  value = module.insights.tags
}

output "bucket_name" {
  value = module.insights.bucket_name
}

output "secret_name" {
  value = module.insights.secret_name
}

output "cluster_name" {
  value = module.insights.cluster_name
}

output "task_definition_families" {
  value = module.insights.task_definition_families
}

output "run_task_command" {
  value = module.insights.run_task_command
}
