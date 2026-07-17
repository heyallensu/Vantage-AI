output "environment" {
  value = local.environment
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "vpc_cidr" {
  value = var.vpc_cidr
}

output "public_subnet_ids" {
  value = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

output "default_security_group_id" {
  value = module.security_baseline.default_security_group_id
}

output "nat_gateway_id" {
  value = module.vpc.nat_gateway_id
}
