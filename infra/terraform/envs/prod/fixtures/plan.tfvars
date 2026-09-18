# Placeholder values for terraform validate / plan. Not a real GCP project.
# Production secret versions and production identity must never be copied here.

project_id              = "example-project"
environment             = "prod"
region                  = "us-central1"
network_name            = "default"
connector_cidr          = "10.8.0.32/28"
runtime_service_account = "heatguard-runtime@example-project.iam.gserviceaccount.com"
operator_group          = "heatguard-operators@example.com"
