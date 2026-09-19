variable "project_id" {
  type        = string
  description = "GCP project id. Placeholder values only in committed fixtures."
}

variable "location" {
  type        = string
  description = "GCS location for the Terraform state bucket."
  default     = "us-central1"
}

variable "bucket_prefix" {
  type        = string
  description = "Prefix for the versioned state bucket. Final name is {prefix}-tfstate."
}
