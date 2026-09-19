output "secret_ids" {
  description = "Secret Manager secret_id values for Cloud Run --set-secrets."
  value       = local.secret_ids
}

output "redis_host" {
  description = "Memorystore host for HEATGUARD_QUOTA_REDIS_URL. Not a secret."
  value       = google_redis_instance.quota.host
}

output "redis_port" {
  description = "Memorystore port for HEATGUARD_QUOTA_REDIS_URL."
  value       = google_redis_instance.quota.port
}

output "vpc_connector_name" {
  description = "Serverless VPC Access connector name for Cloud Run --vpc-connector."
  value       = google_vpc_access_connector.quota.name
}

output "quota_redis_url" {
  description = "redis:// URL without AUTH. Operators pass this as HEATGUARD_QUOTA_REDIS_URL."
  value       = "redis://${google_redis_instance.quota.host}:${google_redis_instance.quota.port}/0"
}
