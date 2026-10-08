# S3: the raw scans, the pre-shaped dashboard views, and the per-tier run locks.
#
# Three prefixes with genuinely different readers and lifecycles, which is why they are one bucket with
# prefix-scoped IAM rather than three buckets:
#
#   scans/  raw envelopes. Replay, audit, and the input the T4 diff reads. Holds per-user identity
#           detail, so Grafana must NOT be able to read it. Expires.
#   views/  pre-shaped tables the dashboards render directly. Readable by the Grafana datasource user.
#           Last-good views never expire, except risk_label_hygiene.json: raw classified matches
#           require expiry even when stale-input withholding leaves the last copy in place.
#   locks/  one small object per tier, the single-run lock. Never expires: a lock is deleted by its
#           holder, and an expiry racing a live scan would silently permit the double run the lock
#           exists to prevent.

# The bucket itself is created only when `create_bucket` is true; an adopted bucket is never in this
# module's destroy scope. Its configuration below (public-access block, versioning, encryption,
# lifecycle, TLS-deny policy) is managed for a created bucket, and for an adopted one only when
# `manage_adopted_bucket_config` is true. `local.bucket_id` references the created bucket when there is
# one, keeping the implicit dependency, and the adopted bucket's name otherwise.

resource "aws_s3_bucket" "data" {
  count = var.create_bucket ? 1 : 0

  bucket = local.bucket_name
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "data" {
  count = local.manage_bucket_config ? 1 : 0

  bucket                  = local.bucket_id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data" {
  count = local.manage_bucket_config ? 1 : 0

  bucket = local.bucket_id
  versioning_configuration {
    # Versioning is the recovery path for the failure this platform is most exposed to: a bad scan
    # overwriting a good `views/*.json` and blanking a dashboard. Noncurrent versions expire quickly
    # below, so it costs almost nothing.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  count = local.manage_bucket_config ? 1 : 0

  bucket = local.bucket_id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  count = local.manage_bucket_config ? 1 : 0

  bucket = local.bucket_id

  # Raw scans age out. The T4 diff only ever reaches back to the scan nearest T-7d, so the retention
  # window is about audit and replay, not about the platform working.
  rule {
    id     = "expire-scans"
    status = "Enabled"

    filter {
      prefix = "scans/"
    }

    expiration {
      days = var.scan_retention_days
    }
  }

  # Reserve this full-key prefix: S3 prefix matching also includes any suffixed keys.
  # This raw-match view ages from its last publication, including hydrated republication,
  # not from the original observation. Other last-good views remain permanent.
  rule {
    id     = "expire-label-risk-view"
    status = "Enabled"

    filter {
      prefix = "views/risk_label_hygiene.json"
    }

    expiration {
      days = var.scan_retention_days
    }
  }

  # Applies to every prefix including views/: the point is that yesterday's overwritten view is
  # recoverable for a week, not that it is kept forever.
  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.data]
}

# Deny any non-TLS request. Cheap, and it closes the one gap the public-access block does not cover.
resource "aws_s3_bucket_policy" "data" {
  count = local.manage_bucket_config ? 1 : 0

  bucket = local.bucket_id
  policy = data.aws_iam_policy_document.bucket[0].json

  depends_on = [aws_s3_bucket_public_access_block.data]
}

data "aws_iam_policy_document" "bucket" {
  count = local.manage_bucket_config ? 1 : 0

  # The bucket policy is one document, so an owner's own statements must be merged here or they are
  # replaced. A source statement reusing the DenyInsecureTransport sid is overridden by the one below.
  source_policy_documents = var.bucket_policy_source_json != "" ? [var.bucket_policy_source_json] : []

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [local.bucket_config_arn, "${local.bucket_config_arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
