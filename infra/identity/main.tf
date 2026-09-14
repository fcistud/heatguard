# Identity SQLite object store (ADR-1 / WO-018).
#
# Production identity data is Confidential and is never copied into
# non-production. Each environment (dev, staging, prod) gets its own bucket
# name and its own seeded object at identity/heatguard-identity.db.

locals {
  bucket_name = "${var.bucket_prefix}-${var.environment}-identity"
}

resource "google_storage_bucket" "identity" {
  name     = local.bucket_name
  location = var.location
  project  = var.project_id

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = var.noncurrent_version_retention_days
    }
  }

  labels = {
    environment = var.environment
    purpose     = "identity"
  }
}

# ADR-1 IAM split is non-negotiable: the Cloud Run runtime principal is
# object-read only. The operator group is the sole writer. No principal
# holds both write and the runtime identity.
resource "google_storage_bucket_iam_member" "runtime_reader" {
  bucket = google_storage_bucket.identity.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.runtime_service_account}"
}

resource "google_storage_bucket_iam_member" "operator_writer" {
  bucket = google_storage_bucket.identity.name
  role   = "roles/storage.objectAdmin"
  member = "group:${var.operator_group}"
}
