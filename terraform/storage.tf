# S3: the raw scans, the pre-shaped dashboard views, and the per-tier run locks.
#
# Three prefixes with genuinely different readers and lifecycles, which is why they are one bucket with
# prefix-scoped IAM rather than three buckets:
#
#   scans/  raw envelopes. Replay, audit, and the input the T4 diff reads. Holds per-user identity
#           detail, so Grafana must NOT be able to read it. Expires.
#   views/  pre-shaped tables the dashboards render directly. Readable by the Grafana datasource user.
#           Never expires - a dashboard reads the current object, and an expired view is a blank panel.
#   locks/  one small object per tier, the single-run lock. Never expires: a lock is deleted by its
#           holder, and an expiry racing a live scan would silently permit the double run the lock
#           exists to prevent.

resource "aws_s3_bucket" "data" {
  count = var.create_bucket ? 1 : 0

  bucket = local.bucket_name
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "data" {
  count = var.create_bucket ? 1 : 0

  bucket                  = aws_s3_bucket.data[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data" {
  count = var.create_bucket ? 1 : 0

  bucket = aws_s3_bucket.data[0].id
  versioning_configuration {
    # Versioning is the recovery path for the failure this platform is most exposed to: a bad scan
    # overwriting a good `views/*.json` and blanking a dashboard. Noncurrent versions expire quickly
    # below, so it costs almost nothing.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  count = var.create_bucket ? 1 : 0

  bucket = aws_s3_bucket.data[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  count = var.create_bucket ? 1 : 0

  bucket = aws_s3_bucket.data[0].id

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
  count = var.create_bucket ? 1 : 0

  bucket = aws_s3_bucket.data[0].id
  policy = data.aws_iam_policy_document.bucket[0].json

  depends_on = [aws_s3_bucket_public_access_block.data]
}

data "aws_iam_policy_document" "bucket" {
  count = var.create_bucket ? 1 : 0

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [aws_s3_bucket.data[0].arn, "${aws_s3_bucket.data[0].arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
