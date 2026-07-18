output "default_security_group_id" {
  description = "The ID of the default security group that has been locked down."
  value       = aws_default_security_group.this.id
}