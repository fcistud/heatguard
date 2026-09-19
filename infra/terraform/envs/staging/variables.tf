variable "environment" {
  type        = string
  description = "Must match this env root (dev / staging / prod)."

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "project_id" {
  type        = string
  description = "GCP project id. Placeholder values only in committed fixtures."
}

variable "region" {
  type        = string
  description = "Region for Memorystore, the VPC connector, and Cloud Run."
  default     = "us-central1"
}

variable "network_name" {
  type        = string
  description = "VPC network name in this project."
  default     = "default"
}

variable "connector_cidr" {
  type        = string
  description = "Unused /28 for the Serverless VPC Access connector."
  default     = "10.8.0.0/28"
}

variable "runtime_service_account" {
  type        = string
  description = "Cloud Run runtime service account email."
}

variable "operator_group" {
  type        = string
  description = "Operator Google group (without group: prefix)."
}
