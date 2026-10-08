# Test fixture for tests/consumer_manifest.tftest.hcl, never a deployment.
#
#   full      a realistic manifest mixing default-equal and non-default values
#   pruned    the same manifest after `bin/consumer_manifest.py regenerate --prune-defaults`
#   distinct  every value non-default and different from every other, so a manifest key wired to the
#             wrong module input cannot render the same environment by coincidence
#
# Each manifest is rendered by the explicit v0.9 consumer glue (./explicit) and by manifest mode.

locals {
  full     = jsondecode(file("${path.module}/../fixtures/manifest-full.json"))
  pruned   = jsondecode(file("${path.module}/../fixtures/manifest-pruned.json"))
  distinct = jsondecode(file("${path.module}/../fixtures/manifest-distinct.json"))

  image        = "example.invalid/synthetic@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  subnets      = ["subnet-synthetic"]
  firehose_key = "arn:aws:secretsmanager:us-east-1:123456789012:secret:synthetic-firehose"
  # Carries Purpose and Namespace, as a live consumer's var.tags does: the manifest values must win.
  caller_tags = { Owner = "synthetic-owner", Purpose = "caller-purpose", Namespace = "caller-namespace" }
  sizes = {
    t1 = { cpu = 512, memory = 1024, deadline_seconds = 900, description = "Hourly" }
    t2 = { cpu = 1024, memory = 2048, deadline_seconds = 3600, description = "Daily" }
    t3 = { cpu = 1024, memory = 4096, deadline_seconds = 3600, description = "Six-hourly" }
    t4 = { cpu = 512, memory = 1024, deadline_seconds = 900, description = "Daily diff" }
  }
}

module "explicit" {
  source     = "./explicit"
  manifest   = local.full
  image      = local.image
  subnet_ids = local.subnets
  tiers      = local.sizes
}

module "manifest" {
  source = "../.."

  consumer_manifest = local.full
  image             = local.image
  subnet_ids        = local.subnets
  tiers             = local.sizes
}

module "pruned" {
  source = "../.."

  consumer_manifest = local.pruned
  image             = local.image
  subnet_ids        = local.subnets
  tiers             = local.sizes
}

module "explicit_distinct" {
  source = "./explicit"

  manifest                       = local.distinct
  image                          = local.image
  subnet_ids                     = local.subnets
  tiers                          = local.sizes
  firehose_access_key_secret_arn = local.firehose_key
  tags                           = local.caller_tags
}

module "manifest_distinct" {
  source = "../.."

  consumer_manifest              = local.distinct
  image                          = local.image
  subnet_ids                     = local.subnets
  tiers                          = local.sizes
  firehose_access_key_secret_arn = local.firehose_key
  tags                           = local.caller_tags
}
