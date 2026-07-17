data "aws_region" "current" {}

resource "aws_cloudwatch_log_group" "ecs_platform" {
  name              = "/ecs/${var.name_prefix}/platform"
  retention_in_days = var.log_retention_days

  tags = {
    Name  = "/ecs/${var.name_prefix}-ecs-platform-logs"
    Layer = "l1-platform"
  }
}

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${var.name_prefix}-operations"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 2
        properties = {
          markdown = "# Vantage AI portfolio operations\nEphemeral environment: review ECS health, application logs, Lambda errors, and DLQ depth before destroy."
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 2
        width  = 12
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "ECS cluster CPU and memory"
          period = 300
          stat   = "Average"
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", "${var.name_prefix}-api"],
            [".", "MemoryUtilization", ".", ".", ".", "."],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 2
        width  = 6
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "Lambda processor errors"
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", "${var.name_prefix}-processor"],
          ]
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 2
        width  = 6
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "DLQ visible messages"
          period = 300
          stat   = "Maximum"
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "${var.name_prefix}-documents-dlq"],
          ]
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 8
        width  = 24
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "Recent API logs"
          view   = "table"
          query  = "SOURCE '${aws_cloudwatch_log_group.ecs_platform.name}' | fields @timestamp, @message | sort @timestamp desc | limit 20"
        }
      },
    ]
  })
}
