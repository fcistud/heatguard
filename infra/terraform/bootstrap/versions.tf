terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.40.0, < 7.0.0"
    }
  }
}

# Local state only. This root creates the bucket that later holds remote
# state; it cannot store its own state in that bucket on first apply.
provider "google" {
  project = var.project_id
  region  = var.location
}
