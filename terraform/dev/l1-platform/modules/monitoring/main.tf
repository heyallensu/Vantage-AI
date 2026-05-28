resource "aws_cloudwatch_log_group" "ecs_platform" {
  name              = "/ecs/${var.name_prefix}/platform"
  retention_in_days = var.log_retention_days

  tags = {
    Name  = "/ecs/${var.name_prefix}-ecs-platform-logs"
    Layer = "l1-platform"
  }
}