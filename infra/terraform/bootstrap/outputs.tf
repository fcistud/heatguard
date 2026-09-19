output "tfstate_bucket" {
  description = "GCS bucket name for Terraform remote state (pass as backend bucket=)."
  value       = google_storage_bucket.tfstate.name
}
