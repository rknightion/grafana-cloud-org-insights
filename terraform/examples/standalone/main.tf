# Standalone deployment of the insights platform.
#
# This is the copy-and-edit starting point: it owns the provider and the backend, and calls the module
# with values for one environment. Copy this directory, set `terraform.tfvars`, and apply.
#
# If you already run Terraform for this AWS account, prefer calling the module from your existing root
# instead of adding a second state file - everything below except the module block is boilerplate you
# already have.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Uncomment and point at your own state bucket. Left commented so `terraform init` works for a
  # read-through without provisioning a backend first.
  #
  # backend "s3" {
  #   bucket       = "my-terraform-state"
  #   key          = "insights/terraform.tfstate"
  #   region       = "eu-west-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "grafana-estate-insights"
      ManagedBy = "terraform"
    }
  }
}

module "insights" {
  source = "../../"

  name_prefix = var.name_prefix

  # Grafana Cloud target. No defaults exist for these on purpose - a default would mean an apply in the
  # wrong environment silently scanning a live org and publishing into a production stack.
  grafana_org_id   = var.grafana_org_id
  write_stack_slug = var.write_stack_slug
  mimir_write_url  = var.mimir_write_url
  mimir_tenant     = var.mimir_tenant
  loki_write_url   = var.loki_write_url
  loki_tenant      = var.loki_tenant

  subnet_ids       = var.subnet_ids
  assign_public_ip = var.assign_public_ip

  # First deployment keeps both schedules off. After separate live-change approval, write all three
  # tokens, pin the image digest, run the provisioner first, then T2 -> T3 -> T1 -> T4 serially.
  # Verify the published views and dashboards before enabling scans; enable the provisioner last.
  image                          = var.image
  provisioner_enabled            = var.provisioner_enabled
  schedules_enabled              = var.schedules_enabled
  coverage_score_weights         = var.coverage_score_weights
  dashboard_detail_enabled       = var.dashboard_detail_enabled
  label_inventory_enabled        = var.label_inventory_enabled
  label_inventory_tunables       = var.label_inventory_tunables
  label_inventory_static_names   = var.label_inventory_static_names
  label_inventory_budget_seconds = var.label_inventory_budget_seconds
  expected_retention_policy      = var.expected_retention_policy
  fleet_default_scrape_interval  = var.fleet_default_scrape_interval

  # Optional two-stage CloudWatch Logs -> Firehose -> the same Loki target. First enable the stream,
  # manually prove delivery, and only then enable the subscription. The secret is adopted by ARN; its
  # value never passes through this state.
  firehose_logs_enabled                  = var.firehose_logs_enabled
  firehose_log_subscription_enabled      = var.firehose_log_subscription_enabled
  firehose_access_key_secret_arn         = var.firehose_access_key_secret_arn
  firehose_access_key_secret_kms_key_arn = var.firehose_access_key_secret_kms_key_arn
}

output "next_steps" {
  value = <<-EOT
    These operations require separate live-change approval. A plan is not approval to execute them.
    First apply keeps schedules_enabled=false and provisioner_enabled=false.

    1. Write all three token keys into ${module.insights.secret_name} out of band:
         GCINSIGHT_READ_TOKEN, GCINSIGHT_WRITE_TOKEN, GCINSIGHT_PROVISION_TOKEN.
       Use a protected local JSON input with Secrets Manager; never put token values in shell history,
       Terraform variables/state, a plan, or the deployment manifest. GCINSIGHT_ORG_ID is not a token.

    2. Use the reviewed immutable image for ARM64, the standalone task architecture.
       For a consumer, commit and check the deployment manifest/module ref, then use consumer-build.
       Publish only with separate approval and record the registry manifest digest.
       Set image="<registry>/<repository>@sha256:<reviewed-manifest-digest>" and apply the reviewed
       task-definition update with both schedules still disabled. A push alone does not change it.

    3. A full deployment needs an explicitly approved provisioner task in its deployment-owned root
       (module create_provisioner=true). This standalone example leaves that module default off;
       provisioner_enabled controls scheduling only and does not create the task.
       Once that prerequisite is reviewed, run ${var.name_prefix}-provisioner FIRST for stack readers.
       Then run T2 -> T3 -> T1 -> T4 serially, using the exact reviewed task-definition revisions:
         ${module.insights.run_task_command}
       Replace the task-definition placeholder with the provisioner revision first, then each tier.
       Verify task logs and advanced scan envelopes after each run. Do not run the provisioner
       concurrently with scans. Consult RUNBOOK.md for provisioning and publication proof.

    4. Wire the views-only Infinity datasource, publish dashboards and paused/unrouted alerts.
       Mint any datasource credential out of band only with explicit approval.

    5. After verification enable collector schedules, keeping provisioner_enabled=false.
       Enable the write-capable provisioner schedule last, with separate approval.
  EOT
}
