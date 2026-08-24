# No `provider` block, deliberately: this is a reusable module, so the caller owns provider
# configuration (region, credentials, default_tags). A provider block here would make the module
# un-composable and would silently override the caller's region.
#
# Works on both OpenTofu and Terraform. `required_version` is the floor for the `moved`/`import`
# semantics and optional object attributes used below.
terraform {
  required_version = ">= 1.6"

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
