# HeatGuard monitoring (IaC)

Declarative alert policies for Cloud Monitoring (or any pipeline that consumes
this YAML). Console-clicked policies are **not** acceptable — review and apply
from version control.

| File | Purpose |
|------|---------|
| `policies.yaml` | Alert policies (severity, metrics, runbook URLs) |
| `notification_channels.yaml` | Channel references (data sources / placeholders) |
| `alerts.tf.example` | Optional Terraform shape for `google_monitoring_alert_policy` |

Applied infrastructure (Secret Manager, Memorystore, VPC connector) lives in
`infra/terraform/` — see that README for bootstrap, cost, and the reviewed
plan gate. This monitoring YAML is still validated offline and is not applied
by the boundary Terraform roots.

Validate locally (PyYAML is in the `dev` extra):

```bash
uv sync --frozen --extra api --extra ml --extra dev
uv run python scripts/validate_monitoring.py --check-docs-links
uv run pytest tests/test_monitoring_config.py -q
```
