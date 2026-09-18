# Boundary Terraform (WO-009)

Environment-scoped roots for Secret Manager containers, a BASIC-tier
Memorystore Redis instance, and a Serverless VPC Access connector. Identity
bucket Terraform stays in `infra/identity/` (WO-018).

| Path | Purpose |
|------|---------|
| `bootstrap/` | Versioned GCS bucket for **remote state**. Local state only. |
| `modules/boundary/` | Shared resources (secrets, IAM, Redis, connector). |
| `envs/dev`, `envs/staging`, `envs/prod` | Separate state prefixes so non-prod never shares prod secrets. |

No `.tfstate` files are committed. Secret **versions** are never declared in
Terraform — operators add them out of band so a plan cannot show plaintext.

## Bootstrap sequence

The state bucket cannot create itself through the backend it stores.

1. Enable APIs: `secretmanager`, `redis`, `vpcaccess`, `servicenetworking`, `storage`.
2. From `infra/terraform/bootstrap`, with **no** `-backend-config`:

   ```bash
   terraform init
   terraform plan -var-file=fixtures/plan.tfvars   # replace with operator tfvars
   terraform apply -var-file=…                     # local state; keep the tfstate private
   ```

3. Copy `envs/<env>/fixtures/backend.hcl.example` to an untracked `backend.hcl`,
   set `bucket` to the bootstrap output `tfstate_bucket` and keep
   `prefix = "boundary/<env>"`.
4. From `infra/terraform/envs/<env>`:

   ```bash
   terraform init -backend-config=backend.hcl
   terraform plan -var-file=operator.tfvars
   terraform apply -var-file=operator.tfvars
   ```

   Apply is **manual**. Pull requests never apply. GitHub Environment
   `boundary-terraform` (required reviewers) is the apply gate:
   `.github/workflows/boundary-terraform-apply.yml` is `workflow_dispatch` only
   and does not run `terraform apply`.

5. Add secret versions (synthetic staging helper:
   `python scripts/generate_boundary_secret_payloads.py --print-gcloud`).
6. Cloud Build substitutions: `_BOUNDARY_ENV`, `_QUOTA_REDIS_HOST` from
   `terraform output redis_host`, `_VPC_CONNECTOR` from
   `terraform output vpc_connector_name`.

### Importing console-created resources

If a secret, Redis instance, or connector already exists, **import before the
first apply** so the plan cannot propose destroy:

```bash
terraform import module.boundary.google_secret_manager_secret.hmac_pepper \
  projects/PROJECT/secrets/heatguard-ENV-hmac-pepper
terraform import module.boundary.google_redis_instance.quota \
  projects/PROJECT/locations/REGION/instances/heatguard-ENV-quota
terraform import module.boundary.google_vpc_access_connector.quota \
  projects/PROJECT/locations/REGION/connectors/heatguard-ENV-quota
```

## Cost at target scale (min-instances=0, max-instances=3)

List-price ballpark for **us-central1**, operator must re-check current
[Google Cloud pricing](https://cloud.google.com/pricing). Figures are monthly
steady-state, not including Cloud Run request charges (those stay near zero
when idle).

| Component | Choice | Approx. monthly | Why this size |
|-----------|--------|-----------------|---------------|
| Memorystore Redis | **BASIC**, 1 GiB, no replica | ~$35–50 | Smallest paid tier. Quota keys are tiny TTLs. |
| Serverless VPC Access | **e2-micro**, min 2 / max 3 instances | ~$70–110 | Connector instances **do not scale to zero**. min 2 is the platform floor; max 3 matches Cloud Run max-instances so the connector is not the bottleneck. |
| Secret Manager | 3 secret containers | pennies | Versions added out of band. |
| **Rejected: per-instance quota only** | no Memorystore / no connector | **~$0 extra** | Under-counts by up to 3× at max-instances=3 (WO-008). Cheaper, but the general limiter would not be globally accurate — not acceptable as the steady state. |
| **Rejected: Memorystore STANDARD_HA** | replica in another zone | ~2× BASIC | No recorded HA justification at this scale. |

Idle Cloud Run (min-instances=0) remains near zero; the connector is the
dominant always-on cost of enabling a shared quota store.

## CI

Job `boundary-terraform` runs `terraform fmt -check`, backend-less `init`,
`validate`, and `plan` against committed placeholder tfvars, then uploads the
plan as an artifact. `terraform apply` is forbidden in CI.
