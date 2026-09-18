module "boundary" {
  source = "../../modules/boundary"

  environment             = var.environment
  project_id              = var.project_id
  region                  = var.region
  network_name            = var.network_name
  connector_cidr          = var.connector_cidr
  runtime_service_account = var.runtime_service_account
  operator_group          = var.operator_group
}

check "env_root_matches_workspace" {
  assert {
    condition     = var.environment == "dev"
    error_message = "infra/terraform/envs/dev must be applied with environment=dev."
  }
}
