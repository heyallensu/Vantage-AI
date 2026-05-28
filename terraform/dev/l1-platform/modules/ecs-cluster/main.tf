resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name  = "${var.name_prefix}-cluster"
    Layer = "l1-platform"
  }
}