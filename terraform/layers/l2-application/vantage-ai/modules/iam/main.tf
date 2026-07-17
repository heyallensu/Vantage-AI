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

resource "aws_iam_role" "ecs_execution" {
  name               = "${var.name_prefix}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = {
    Name  = "${var.name_prefix}-ecs-execution-role"
    Layer = "l2-application"
  }
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ECS task role is used by the FastAPI application code.
resource "aws_iam_role" "ecs_task" {
  name               = "${var.name_prefix}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = {
    Name  = "${var.name_prefix}-ecs-task-role"
    Layer = "l2-application"
  }
}

# FastAPI needs to send document jobs to SQS and call Bedrock
data "aws_iam_policy_document" "ecs_task_app_permissions" {
  statement {
    sid = "SendDocumentJobsToSQS"

    actions = [
      "sqs:GetQueueAttributes",
      "sqs:SendMessage"
    ]

    resources = [var.sqs_queue_arn]
  }

  statement {
    sid = "InvokeBedrockModels"

    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = ["*"]
  }

  statement {
    sid = "BedrockMarketplaceAccess"

    actions = [
      "aws-marketplace:ViewSubscriptions",
      "aws-marketplace:Subscribe"
    ]
    resources = ["*"]
  }
}

# Attach app permissions directly to the ECS task role
resource "aws_iam_role_policy" "ecs_task_app_permissions" {
  name   = "${var.name_prefix}-ecs-task-app-permissions"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_app_permissions.json
}

# Lambda execution role is used by the document processor
resource "aws_iam_role" "lambda_execution" {
  name               = "${var.name_prefix}-lambda-execution-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name  = "${var.name_prefix}-lambda-execution-role"
    Layer = "l2-application"
  }
}

# Attach basic Lambda logging permissions
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allow Lambda to create ENIs when it runs inside the VPC
resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Lambda consumes SQS messages from the document processing queue
data "aws_iam_policy_document" "lambda_sqs_permissions" {
  statement {
    sid = "ConsumeDocumentJobsFromSQS"

    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage"
    ]

    resources = [var.sqs_queue_arn]
  }
}

# Attach SQS consume permissions to the Lambda role
resource "aws_iam_role_policy" "lambda_sqs_permissions" {
  name   = "${var.name_prefix}-lambda-sqs-permissions"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_sqs_permissions.json
}