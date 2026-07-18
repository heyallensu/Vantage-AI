data "aws_iam_policy_document" "s3" {
  statement {
    sid       = "DocumentBucketOnly"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [var.document_bucket_arn, "${var.document_bucket_arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids
  policy            = data.aws_iam_policy_document.s3.json

  tags = { Name = "${var.name_prefix}-s3-endpoint", Layer = "l2-application" }
}

data "aws_iam_policy_document" "secrets" {
  statement {
    sid       = "ApplicationRuntimeSecretsOnly"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.database_secret_arn, var.api_key_secret_arn]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [var.secretsmanager_endpoint_security_group_id]
  private_dns_enabled = true
  policy              = data.aws_iam_policy_document.secrets.json

  tags = { Name = "${var.name_prefix}-secrets-endpoint", Layer = "l2-application" }
}
