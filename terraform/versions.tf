# No `provider` block, deliberately: this is a reusable module, so the caller owns provider
# configuration (region, credentials, default_tags). A provider block here would make the module
# un-composable and would silently override the caller's region.
#
# Works on both OpenTofu and Terraform. The floor is set by variable validations that reference other
# variables and locals (labelling.tf, consumer_manifest.tf): OpenTofu 1.8. The Terraform equivalent is
# 1.9, which `required_version` cannot express for both tools at once, so Terraform 1.8 passes this
# check and then fails on those validations.
terraform {
  required_version = ">= 1.8"

  required_providers {
    aws = {
      # v6 floor, not v5: this module reads `data.aws_region.current.region`, which does not exist in
      # v5 (it was `.name` there, and is deprecated in v6). Straddling both would mean picking the
      # attribute that warns on one major and errors on the other.
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
}
