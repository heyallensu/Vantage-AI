resource "aws_sqs_queue" "dlq" {
  name                    = "${var.name_prefix}-documents-dlq"
  sqs_managed_sse_enabled = true

  tags = {
    Name  = "${var.name_prefix}-documents-dlq"
    Layer = "l2-application"
  }
}

resource "aws_sqs_queue" "main" {
  name                       = "${var.name_prefix}-documents"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = 10
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = {
    Name  = "${var.name_prefix}-documents"
    Layer = "l2-application"
  }
}
