locals {
  buckets = {
    documents = "${var.name_prefix}-${var.aws_region}-${var.account_id}-documents"
    frontend  = "${var.name_prefix}-${var.aws_region}-${var.account_id}-frontend"
  }
}

resource "aws_s3_bucket" "this" {
  for_each      = local.buckets
  bucket        = each.value
  force_destroy = true

  tags = { Name = each.value, Layer = "l2-application" }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  rule { object_ownership = "BucketOwnerEnforced" }
}

# trivy:ignore:AWS-0132 ADR 003 selects low-cost SSE-S3 for short-lived non-regulated demo data.
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  depends_on = [aws_s3_bucket_versioning.this]

  rule {
    id     = "ephemeral-cleanup"
    status = "Enabled"
    filter {}

    abort_incomplete_multipart_upload { days_after_initiation = 1 }
    noncurrent_version_expiration { noncurrent_days = 1 }

    dynamic "expiration" {
      for_each = each.key == "documents" ? [1] : []
      content { days = var.document_retention_days }
    }
  }
}

resource "aws_s3_object" "frontend_index" {
  bucket       = aws_s3_bucket.this["frontend"].id
  key          = "index.html"
  content      = var.frontend_index_html
  content_type = "text/html; charset=utf-8"

  server_side_encryption = "AES256"
}
