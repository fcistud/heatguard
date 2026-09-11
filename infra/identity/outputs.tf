output "bucket_name" {
  description = "Environment-scoped identity bucket name."
  value       = google_storage_bucket.identity.name
}

output "identity_object_name" {
  description = "Object key of the identity snapshot. Seeded separately per environment."
  value       = var.identity_object_name
}

output "identity_object_uri" {
  description = "gs:// URI consumed as HEATGUARD_IDENTITY_OBJECT_URI."
  value       = "gs://${google_storage_bucket.identity.name}/${var.identity_object_name}"
}

output "identity_refresh_seconds" {
  description = "Default refresh interval for the identity snapshot loader."
  value       = 300
}
