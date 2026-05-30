resource "aws_cloudwatch_metric_alarm" "dlq_visible_messages" {
  alarm_name        = "${var.name_prefix}-dlq-visible-messages"
  alarm_description = "Document processing jobs have failed and moved to the DLQ."

  namespace   = "AWS/SQS"
  metric_name = "ApproximateNumberOfMessagesVisible"
  statistic   = "Maximum"

  period              = 60
  evaluation_periods  = 1
  threshold           = var.dlq_visible_messages_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions

  dimensions = {
    QueueName = var.dlq_name
  }

  tags = {
    Name  = "${var.name_prefix}-document-dlq-visible-messages"
    Layer = "l2-application"
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name        = "${var.name_prefix}-processor-errors"
  alarm_description = "The document processor Lambda is reporting errors."

  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  statistic   = "Sum"

  period              = 60
  evaluation_periods  = 1
  threshold           = var.lambda_error_threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  tags = {
    Name  = "${var.name_prefix}-processor-errors"
    Layer = "l2-application"
  }
}