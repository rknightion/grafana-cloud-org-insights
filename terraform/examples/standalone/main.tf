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

  # FIRST APPLY SHOULD LEAVE THIS FALSE.
  #
  # The order that avoids a broken first run: apply with schedules off, write the two tokens into the
  # secret, push the image, run one tier by hand with `aws ecs run-task`, read its logs, confirm the
  # dashboards populate - then set this true. Turning schedules on before the secret has values gives
  # four tasks an hour failing to start, and the first thing anyone sees is a CloudWatch bill.
  schedules_enabled      = var.schedules_enabled
  coverage_score_weights = var.coverage_score_weights

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
    1. Write the tokens (values are never managed by Terraform):
         aws secretsmanager put-secret-value --region ${var.region} \
           --secret-id ${module.insights.secret_name} \
           --secret-string '{"GCINSIGHT_READ_TOKEN":"<reader>","GCINSIGHT_WRITE_TOKEN":"<writer>","GCINSIGHT_ORG_ID":"${var.grafana_org_id}"}'

    2. Build and push the image (must match the task architecture, ARM64 by default):
         aws ecr get-login-password --region ${var.region} | docker login --username AWS --password-stdin ${try(split("/", module.insights.ecr_repository_url)[0], "<registry>")}
         docker build --platform linux/arm64 -t ${try(module.insights.ecr_repository_url, "<repo>")}:latest ../../..
         docker push ${try(module.insights.ecr_repository_url, "<repo>")}:latest

    3. Smoke-test one tier by hand and read its logs:
         ${module.insights.run_task_command}
         aws logs tail ${module.insights.log_group_name} --follow --region ${var.region}

    4. Mint the Grafana datasource credential:
         aws iam create-access-key --user-name ${try(module.insights.views_reader_user_name, "<user>")}

    5. Only then set schedules_enabled = true and apply again.
  EOT
}
