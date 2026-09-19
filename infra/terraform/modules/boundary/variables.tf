variable "environment" {
  type        = string
  description = "Deployment environment. Drives secret, Redis, and connector names."

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
  description = "Region for Memorystore, the VPC connector, and Cloud Run. Must match."
  default     = "us-central1"

  validation {
    condition     = length(var.region) > 0
    error_message = "region must be a non-empty Cloud Run / Memorystore region."
  }
}

variable "network_name" {
  type        = string
  description = "VPC network name in this project. Redis and the connector must share it."
  default     = "default"

  validation {
    condition     = length(var.network_name) > 0
    error_message = "network_name must be a non-empty VPC network in project_id."
  }
}

variable "connector_cidr" {
  type        = string
  description = "Unused /28 for the Serverless VPC Access connector."
  default     = "10.8.0.0/28"

  validation {
    condition     = can(cidrnetmask(var.connector_cidr)) && split("/", var.connector_cidr)[1] == "28"
    error_message = "connector_cidr must be a /28 IPv4 range that does not overlap existing subnets."
  }
}

variable "runtime_service_account" {
  type        = string
  description = "Cloud Run runtime service account email. Receives secretAccessor and redis.viewer only."
}

variable "operator_group" {
  type        = string
  description = "Operator Google group (without group: prefix). Receives secretVersionManager only."
}
