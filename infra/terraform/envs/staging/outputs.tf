output "secret_ids" {
  description = "Secret Manager secret_id values for Cloud Run --set-secrets."
  value       = module.boundary.secret_ids
}

output "redis_host" {
  description = "Memorystore host for HEATGUARD_QUOTA_REDIS_URL."
  value       = module.boundary.redis_host
}

output "redis_port" {
  description = "Memorystore port for HEATGUARD_QUOTA_REDIS_URL."
  value       = module.boundary.redis_port
}

output "vpc_connector_name" {
  description = "Serverless VPC Access connector name for Cloud Run --vpc-connector."
  value       = module.boundary.vpc_connector_name
}

output "quota_redis_url" {
  description = "redis:// URL without AUTH."
  value       = module.boundary.quota_redis_url
}
