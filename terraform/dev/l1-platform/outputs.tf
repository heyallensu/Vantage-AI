output "ecs_cluster_id" {
  value = module.ecs_cluster.cluster_id
}

output "ecs_cluster_name" {
  value = module.ecs_cluster.cluster_name
}

output "ecs_cluster_arn" {
  value = module.ecs_cluster.cluster_arn
}

output "ecr_repository_name" {
  value = module.ecr.repository_name
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "ecr_repository_arn" {
  value = module.ecr.repository_arn
}

output "shared_alb_arn" {
  value = module.shared_alb.alb_arn
}

output "shared_alb_dns_name" {
  value = module.shared_alb.alb_dns_name
}

output "shared_alb_zone_id" {
  value = module.shared_alb.alb_zone_id
}

output "shared_alb_security_group_id" {
  value = module.shared_alb.security_group_id
}

output "shared_http_listener_arn" {
  value = module.shared_alb.http_listener_arn
}

output "ecs_platform_log_group_name" {
  value = module.monitoring.ecs_platform_log_group_name
}

output "ecs_platform_log_group_arn" {
  value = module.monitoring.ecs_platform_log_group_arn
}