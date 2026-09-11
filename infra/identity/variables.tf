variable "environment" {
  type        = string
  description = "Deployment environment. Drives the bucket name so env collisions are impossible."

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "project_id" {
  type        = string
  description = "GCP project id. Placeholder values only in committed fixtures."
}

variable "bucket_prefix" {
  type        = string
  description = "Environment-scoped bucket name prefix. Final name is {prefix}-{environment}-identity."
}

variable "location" {
  type        = string
  description = "GCS bucket location."
  default     = "us-central1"
}

variable "runtime_service_account" {
  type        = string
  description = "Cloud Run runtime service account email. Receives objectViewer only."
}

variable "operator_group" {
  type        = string
  description = "Operator Google group (without group: prefix). Receives objectAdmin only."
}

variable "noncurrent_version_retention_days" {
  type        = number
  description = "Days to retain noncurrent object generations before lifecycle delete (rollback window)."
  default     = 30

  validation {
    condition     = var.noncurrent_version_retention_days >= 1 && var.noncurrent_version_retention_days <= 365
    error_message = "noncurrent_version_retention_days must be between 1 and 365."
  }
}

variable "identity_object_name" {
  type        = string
  description = "Object key for the identity SQLite snapshot. Seeded per environment; never copy prod into non-prod."
  default     = "identity/heatguard-identity.db"
}

variable "tfstate_bucket" {
  type        = string
  description = "Remote-state GCS bucket. Passed to terraform init -backend-config=bucket=..."
}

variable "tfstate_prefix" {
  type        = string
  description = "Remote-state prefix. Passed to terraform init -backend-config=prefix=..."
}
