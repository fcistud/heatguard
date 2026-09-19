# Partial GCS backend. Bucket and prefix are supplied at init via
# -backend-config (see fixtures/backend.hcl.example). Terraform cannot
# interpolate variables inside a backend block. Never put credentials here.
#
# CI moves this file aside so plan can run with the default local backend
# and no GCP credentials. Operators keep it in place for apply.
terraform {
  backend "gcs" {}
}
