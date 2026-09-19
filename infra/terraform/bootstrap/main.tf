# Remote-state bootstrap (WO-009). Apply once with local state, then point
# env roots at this bucket via -backend-config. Never commit the resulting
# local terraform.tfstate.

locals {
  bucket_name = "${var.bucket_prefix}-tfstate"
}

resource "google_storage_bucket" "tfstate" {
  name     = local.bucket_name
  location = var.location
  project  = var.project_id

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  labels = {
    purpose = "terraform-state"
  }
}
