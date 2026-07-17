resource "aws_security_group" "lambda" {
  name_prefix = "${var.name_prefix}-lambda-sg"
  description = "Security group for lambda function"
  vpc_id      = var.vpc_id

  tags = {
    Name  = "${var.name_prefix}-lambda-sg"
    Layer = "l2-application"
  }
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.lambda.id
  description       = "Allow all outbound traffic"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name_prefix}-lambda"
  retention_in_days = 14

  tags = {
    Name  = "${var.name_prefix}-processor-logs"
    Layer = "l2-application"
  }
}

resource "aws_lambda_function" "processor" {
  function_name = "${var.name_prefix}-processor"
  role          = var.lambda_execution_role_arn
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime

  filename         = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

  timeout     = var.lambda_timeout_seconds
  memory_size = var.lambda_memory_size

  vpc_config {
    security_group_ids = [aws_security_group.lambda.id]
    subnet_ids         = var.private_subnet_ids
  }

  environment {
    variables = {
      DATABASE_URL = var.database_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = {
    Name  = "${var.name_prefix}-processor"
    Layer = "l2-application"
  }
}

resource "aws_lambda_event_source_mapping" "sqs" {
  event_source_arn        = var.sqs_queue_arn
  function_name           = aws_lambda_function.processor.arn
  batch_size              = 10
  enabled                 = true
  function_response_types = ["ReportBatchItemFailures"]
}
