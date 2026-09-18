# Boundary infrastructure (WO-009).
#
# Secret Manager holds containers only — operators add versions out of band
# so a plan never shows plaintext. Memorystore BASIC 1 GiB is the smallest
# viable shared quota store; STANDARD_HA is rejected without a recorded
# justification. The VPC connector is sized for Cloud Run max-instances=3.

locals {
  network_id = "projects/${var.project_id}/global/networks/${var.network_name}"
  secret_ids = {
    integrator_digests = "heatguard-${var.environment}-integrator-digests"
    hmac_pepper        = "heatguard-${var.environment}-hmac-pepper"
    session_signing    = "heatguard-${var.environment}-session-signing"
  }
}

resource "google_secret_manager_secret" "integrator_digests" {
  secret_id = local.secret_ids.integrator_digests
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "boundary"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "hmac_pepper" {
  secret_id = local.secret_ids.hmac_pepper
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "boundary"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "session_signing" {
  secret_id = local.secret_ids.session_signing
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "boundary"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Runtime reads secret payloads. Operators add/disable versions. Neither
# principal receives the other's role.
resource "google_secret_manager_secret_iam_member" "integrator_digests_runtime" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.integrator_digests.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.runtime_service_account}"
}

resource "google_secret_manager_secret_iam_member" "hmac_pepper_runtime" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.hmac_pepper.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.runtime_service_account}"
}

resource "google_secret_manager_secret_iam_member" "session_signing_runtime" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.session_signing.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.runtime_service_account}"
}

resource "google_secret_manager_secret_iam_member" "integrator_digests_operator" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.integrator_digests.secret_id
  role      = "roles/secretmanager.secretVersionManager"
  member    = "group:${var.operator_group}"
}

resource "google_secret_manager_secret_iam_member" "hmac_pepper_operator" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.hmac_pepper.secret_id
  role      = "roles/secretmanager.secretVersionManager"
  member    = "group:${var.operator_group}"
}

resource "google_secret_manager_secret_iam_member" "session_signing_operator" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.session_signing.secret_id
  role      = "roles/secretmanager.secretVersionManager"
  member    = "group:${var.operator_group}"
}

resource "google_redis_instance" "quota" {
  name               = "heatguard-${var.environment}-quota"
  project            = var.project_id
  region             = var.region
  tier               = "BASIC"
  memory_size_gb     = 1
  redis_version      = "REDIS_7_0"
  display_name       = "HeatGuard quota ${var.environment}"
  authorized_network = local.network_id
  connect_mode       = "DIRECT_PEERING"
  # AUTH would require an operator-managed secret version outside Terraform.
  # Data-plane isolation is the VPC + connector; do not put AUTH in .tf.
  auth_enabled            = false
  transit_encryption_mode = "DISABLED"

  labels = {
    environment = var.environment
    purpose     = "quota"
  }

  lifecycle {
    precondition {
      condition     = var.region != ""
      error_message = "Memorystore region must be set and must match Cloud Run."
    }
  }
}

resource "google_vpc_access_connector" "quota" {
  name          = "heatguard-${var.environment}-quota"
  project       = var.project_id
  region        = var.region
  network       = var.network_name
  ip_cidr_range = var.connector_cidr
  min_instances = 2
  max_instances = 3
  machine_type  = "e2-micro"

  lifecycle {
    precondition {
      condition     = var.region != ""
      error_message = "VPC connector region must be set and must match Cloud Run and Memorystore."
    }
  }
}

# Memorystore data-plane is IP + VPC; this IAM binding is inventory/read only.
resource "google_project_iam_member" "runtime_redis_viewer" {
  project = var.project_id
  role    = "roles/redis.viewer"
  member  = "serviceAccount:${var.runtime_service_account}"
}

check "region_and_network_alignment" {
  assert {
    condition = (
      google_redis_instance.quota.region == var.region
      && google_vpc_access_connector.quota.region == var.region
      && google_redis_instance.quota.authorized_network == local.network_id
    )
    error_message = "Memorystore and the VPC connector must share var.region and var.network_name."
  }
}
