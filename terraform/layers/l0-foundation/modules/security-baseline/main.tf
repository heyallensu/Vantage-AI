resource "aws_default_security_group" "this" {
  vpc_id = var.vpc_id

  tags = {
    Name  = "${var.name_prefix}-default-sg-locked"
    Layer = "l0-foundation"
  }
}
