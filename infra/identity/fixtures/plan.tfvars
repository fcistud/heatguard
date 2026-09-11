# Placeholder values for terraform validate / plan. Not a real GCP project.
# Production identity data must never be copied into this (or any non-prod) path.

project_id                        = "example-project"
environment                       = "dev"
bucket_prefix                     = "example-heatguard"
location                          = "us-central1"
runtime_service_account           = "heatguard-runtime@example-project.iam.gserviceaccount.com"
operator_group                    = "heatguard-operators@example.com"
noncurrent_version_retention_days = 30
identity_object_name              = "identity/heatguard-identity.db"
tfstate_bucket                    = "example-tfstate"
tfstate_prefix                    = "identity/dev"
