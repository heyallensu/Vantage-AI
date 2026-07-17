data "aws_partition" "current" {}
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_secretsmanager_random_password" "api_key" {
  password_length     = 32
  exclude_punctuation = true
}

resource "aws_secretsmanager_secret" "api_key" {
  name                    = "${var.name_prefix}/api-key"
  description             = "Ephemeral API key for the portfolio CloudFront endpoint"
  recovery_window_in_days = 0

  tags = { Name = "${var.name_prefix}-api-key", Layer = "l2-application" }
}

resource "aws_secretsmanager_secret_version" "api_key" {
  secret_id     = aws_secretsmanager_secret.api_key.id
  secret_string = data.aws_secretsmanager_random_password.api_key.random_password

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${var.name_prefix}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = { Name = "${var.name_prefix}-ecs-execution-role", Layer = "l2-application" }
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_execution_secret" {
  statement {
    sid       = "ReadInjectedApiKeyOnly"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.api_key.arn]
  }
}

resource "aws_iam_role_policy" "ecs_execution_secret" {
  name   = "${var.name_prefix}-api-key-injection"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.ecs_execution_secret.json
}

resource "aws_iam_role" "ecs_task" {
  name               = "${var.name_prefix}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = { Name = "${var.name_prefix}-ecs-task-role", Layer = "l2-application" }
}

data "aws_iam_policy_document" "ecs_task" {
  statement {
    sid       = "PublishDocumentJobs"
    actions   = ["sqs:GetQueueAttributes", "sqs:SendMessage"]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid       = "WriteDocumentObjects"
    actions   = ["s3:PutObject"]
    resources = ["${var.document_bucket_arn}/*"]
  }

  statement {
    sid       = "ReadManagedDatabaseSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.database_secret_arn]
  }

  statement {
    sid = "InvokeConfiguredBedrockProfile"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = var.bedrock_invoke_resource_arns
  }
}

resource "aws_iam_role_policy" "ecs_task" {
  name   = "${var.name_prefix}-ecs-task-runtime"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task.json
}

resource "aws_iam_role" "lambda_execution" {
  name               = "${var.name_prefix}-lambda-execution-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = { Name = "${var.name_prefix}-lambda-execution-role", Layer = "l2-application" }
}

data "aws_iam_policy_document" "lambda_runtime" {
  statement {
    sid = "ConsumeDocumentJobs"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
    ]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid       = "ReadDocumentObjects"
    actions   = ["s3:GetObject"]
    resources = ["${var.document_bucket_arn}/*"]
  }

  statement {
    sid       = "ReadManagedDatabaseSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.database_secret_arn]
  }

  statement {
    sid       = "WriteProcessorLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-processor:*"]
  }

  statement {
    sid = "ManageVpcNetworkInterfaces"
    actions = [
      "ec2:AssignPrivateIpAddresses",
      "ec2:CreateNetworkInterface",
      "ec2:DeleteNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:UnassignPrivateIpAddresses",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_runtime" {
  name   = "${var.name_prefix}-lambda-runtime"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_runtime.json
}
