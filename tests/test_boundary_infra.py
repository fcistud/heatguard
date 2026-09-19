"""Offline invariants for boundary Terraform, Cloud Run wiring, and the apply gate (WO-009)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from heatguard._paths import _REPO_ROOT

REPO = _REPO_ROOT
TF_ROOT = REPO / "infra" / "terraform"
MODULE_DIR = TF_ROOT / "modules" / "boundary"
CLOUDBUILD = REPO / "cloudbuild.yaml"
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
APPLY_WORKFLOW = REPO / ".github" / "workflows" / "boundary-terraform-apply.yml"
RUNBOOKS = REPO / "docs" / "RUNBOOKS.md"
DEPLOY = REPO / "docs" / "DEPLOY_GCP.md"
DEPLOY_SCRIPT = REPO / "scripts" / "deploy-gcp.sh"
README = TF_ROOT / "README.md"
MONITORING_README = REPO / "infra" / "monitoring" / "README.md"
STAGING_SECRETS = REPO / "tests" / "fixtures" / "boundary" / "staging-secrets.json"
ENVS = ("dev", "staging", "prod")

RUNTIME_ACCESSOR = "roles/secretmanager.secretAccessor"
OPERATOR_WRITE = "roles/secretmanager.secretVersionManager"
REDIS_VIEWER = "roles/redis.viewer"
ACCESSOR_ROLES = frozenset({RUNTIME_ACCESSOR, REDIS_VIEWER})
WRITE_ROLES = frozenset(
    {
        OPERATOR_WRITE,
        "roles/secretmanager.admin",
        "roles/secretmanager.secretVersionAdder",
        "roles/owner",
        "roles/editor",
        "roles/redis.admin",
        "roles/redis.editor",
    }
)
PUBLIC_MEMBERS = ("allUsers", "allAuthenticatedUsers")
PLACEHOLDER_MARKERS = ("example", "placeholder", "YOUR_", "changeme")
SECRET_VALUE_PATTERNS = (
    r"secret_data\s*=",
    r"secret_string\s*=",
    r'secret_data_wo\s*=',
    r'password\s*=\s*"',
    r'auth_string\s*=\s*"',
)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def load_tf_sources(root: Path = TF_ROOT) -> str:
    chunks: list[str] = []
    for path in sorted(root.rglob("*.tf")):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _normalize_member(expr: str) -> str:
    return expr.strip().strip('"').replace(" ", "")


def _iam_blocks(source: str, resource_type: str) -> list[str]:
    return re.findall(
        rf'resource\s+"{re.escape(resource_type)}"\s+"[^"]+"\s*\{{(.*?)\n\}}',
        source,
        flags=re.DOTALL,
    )


def collect_iam_bindings(source: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for resource_type in (
        "google_secret_manager_secret_iam_member",
        "google_project_iam_member",
        "google_storage_bucket_iam_member",
    ):
        for body in _iam_blocks(source, resource_type):
            role_m = re.search(r'role\s*=\s*"([^"]+)"', body)
            member_m = re.search(r"member\s*=\s*([^\n]+)", body)
            if role_m and member_m:
                found.append((role_m.group(1), member_m.group(1).strip()))
    return found


def validate_boundary_infra(
    *,
    tf_source: str,
    cloudbuild_text: str,
    workflow_text: str,
    apply_workflow_text: str,
    tfvars_texts: dict[str, str],
) -> ValidationResult:
    result = ValidationResult()
    module_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(MODULE_DIR.glob("*.tf"))
        if MODULE_DIR.exists()
    ) or tf_source

    if "prevent_destroy" not in module_source:
        result.fail("secret containers must set lifecycle prevent_destroy")
    if re.search(r"google_secret_manager_secret_version", tf_source):
        result.fail("Terraform must not declare secret versions")
    for pattern in SECRET_VALUE_PATTERNS:
        if re.search(pattern, tf_source):
            result.fail(f"Terraform must not inline secret values ({pattern})")

    if not re.search(r'tier\s*=\s*"BASIC"', module_source):
        result.fail("Memorystore must use BASIC tier (smallest viable, no HA)")
    if not re.search(r"memory_size_gb\s*=\s*1", module_source):
        result.fail("Memorystore must be 1 GiB (smallest paid size)")
    if re.search(r'tier\s*=\s*"STANDARD_HA"', tf_source):
        result.fail("STANDARD_HA is rejected without a recorded justification")
    if not re.search(r'machine_type\s*=\s*"e2-micro"', module_source):
        result.fail("VPC connector must use e2-micro")
    if not re.search(r"max_instances\s*=\s*3", module_source):
        result.fail("VPC connector max_instances must be 3 (Cloud Run max-instances)")
    if not re.search(r"min_instances\s*=\s*2", module_source):
        result.fail("VPC connector min_instances must be 2 (platform floor)")

    if 'backend "gcs"' not in tf_source:
        result.fail("env roots must declare a gcs backend block")
    if "google_storage_bucket" not in tf_source or "tfstate" not in tf_source:
        result.fail("bootstrap root must declare a versioned tfstate bucket")

    bindings = collect_iam_bindings(tf_source)
    normalized = [(role, _normalize_member(member)) for role, member in bindings]
    for role, member in normalized:
        joined = member + role
        if any(public in joined for public in PUBLIC_MEMBERS):
            result.fail(f"public IAM member is forbidden: {member} {role}")
        if role in {"roles/owner", "roles/editor"}:
            result.fail(f"owner/editor bindings are forbidden: {role}")
        if "runtime_service_account" in member and role not in ACCESSOR_ROLES:
            result.fail(
                f"runtime service account must hold accessor-only roles; found {role}"
            )
        if "runtime_service_account" in member and role in WRITE_ROLES:
            result.fail(f"runtime service account must never receive a write role; found {role}")
        if "operator_group" in member and role != OPERATOR_WRITE:
            result.fail(
                f"operator group must hold {OPERATOR_WRITE} only; found {role}"
            )

    accessor = [
        pair
        for pair in normalized
        if pair[0] == RUNTIME_ACCESSOR and "runtime_service_account" in pair[1]
    ]
    operator = [
        pair
        for pair in normalized
        if pair[0] == OPERATOR_WRITE and "operator_group" in pair[1]
    ]
    redis = [
        pair
        for pair in normalized
        if pair[0] == REDIS_VIEWER and "runtime_service_account" in pair[1]
    ]
    if len(accessor) != 3:
        result.fail(f"expected three secretAccessor runtime bindings, found {len(accessor)}")
    if len(operator) != 3:
        result.fail(f"expected three secretVersionManager operator bindings, found {len(operator)}")
    if len(redis) != 1:
        result.fail(f"expected one redis.viewer runtime binding, found {len(redis)}")

    required_env = (
        "HEATGUARD_CORS_ORIGINS",
        "HEATGUARD_AUTH_MODE",
        "HEATGUARD_QUOTA_CAPACITY",
        "HEATGUARD_QUOTA_REFILL_PER_SEC",
        "HEATGUARD_QUOTA_REDIS_URL",
        "HEATGUARD_QUOTA_REDIS_CONNECT_TIMEOUT",
        "HEATGUARD_QUOTA_REDIS_COMMAND_TIMEOUT",
        "HEATGUARD_API_KEY_PEPPER",
        "HEATGUARD_API_KEY_DIGESTS",
        "HEATGUARD_SESSION_SIGNING_SECRET",
    )
    for name in required_env:
        if name not in cloudbuild_text:
            result.fail(f"cloudbuild.yaml must set {name}")
    if "--set-secrets" not in cloudbuild_text and "set-secrets=" not in cloudbuild_text:
        result.fail("cloudbuild.yaml must mount the three secret references")
    if "--vpc-connector" not in cloudbuild_text and "vpc-connector=" not in cloudbuild_text:
        result.fail("cloudbuild.yaml must attach the VPC connector")
    if "private-ranges-only" not in cloudbuild_text:
        result.fail("cloudbuild.yaml must set vpc-egress=private-ranges-only")
    if "heatguard-${_BOUNDARY_ENV}-quota" not in cloudbuild_text:
        result.fail("cloudbuild.yaml must derive the VPC connector from _BOUNDARY_ENV")
    if re.search(r"_VPC_CONNECTOR:\s*heatguard-prod-quota", cloudbuild_text):
        result.fail("cloudbuild.yaml must not hardcode the production connector as the default")
    if "_RUNTIME_SERVICE_ACCOUNT" not in cloudbuild_text:
        result.fail("cloudbuild.yaml must accept a runtime service-account substitution")

    if re.search(r"(?m)^\s*terraform\s+apply\b", workflow_text):
        result.fail("CI must never run terraform apply")
    if "terraform fmt -check" not in workflow_text:
        result.fail("CI must run terraform fmt -check")
    if "terraform validate" not in workflow_text:
        result.fail("CI must run terraform validate")
    if "terraform plan" not in workflow_text:
        result.fail("CI must run terraform plan")
    if "boundary-terraform" not in workflow_text:
        result.fail("CI must define a boundary-terraform job")

    if "pull_request" in apply_workflow_text.split("jobs:", 1)[0]:
        result.fail("apply workflow must not trigger on pull_request")
    if "workflow_dispatch" not in apply_workflow_text:
        result.fail("apply workflow must be workflow_dispatch")
    if "environment: boundary-terraform" not in apply_workflow_text:
        result.fail("apply workflow must use GitHub Environment boundary-terraform")
    if re.search(r"(?m)^\s*terraform\s+apply\b", apply_workflow_text):
        result.fail("apply workflow must not run terraform apply")

    for env, text in tfvars_texts.items():
        lower = text.lower()
        if not any(marker in lower for marker in PLACEHOLDER_MARKERS):
            result.fail(f"{env} plan.tfvars must use placeholder identifiers")
        if f'environment             = "{env}"' not in text and f'environment = "{env}"' not in text:
            if env != "bootstrap" and f'environment' in text and env not in text:
                result.fail(f"{env} plan.tfvars must set environment={env}")

    return result


def _default_tfvars() -> dict[str, str]:
    texts = {
        env: (TF_ROOT / "envs" / env / "fixtures" / "plan.tfvars").read_text(encoding="utf-8")
        for env in ENVS
    }
    texts["bootstrap"] = (TF_ROOT / "bootstrap" / "fixtures" / "plan.tfvars").read_text(
        encoding="utf-8"
    )
    return texts


def test_committed_boundary_infra_invariants() -> None:
    result = validate_boundary_infra(
        tf_source=load_tf_sources(),
        cloudbuild_text=CLOUDBUILD.read_text(encoding="utf-8"),
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        apply_workflow_text=APPLY_WORKFLOW.read_text(encoding="utf-8"),
        tfvars_texts=_default_tfvars(),
    )
    assert result.ok, result.errors


def test_public_iam_member_fails() -> None:
    source = load_tf_sources() + '\nresource "google_project_iam_member" "bad" {\n  role = "roles/viewer"\n  member = "allUsers"\n}\n'
    result = validate_boundary_infra(
        tf_source=source,
        cloudbuild_text=CLOUDBUILD.read_text(encoding="utf-8"),
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        apply_workflow_text=APPLY_WORKFLOW.read_text(encoding="utf-8"),
        tfvars_texts=_default_tfvars(),
    )
    assert not result.ok
    assert any("public IAM" in err for err in result.errors)


def test_owner_binding_fails() -> None:
    source = load_tf_sources().replace(REDIS_VIEWER, "roles/owner", 1)
    result = validate_boundary_infra(
        tf_source=source,
        cloudbuild_text=CLOUDBUILD.read_text(encoding="utf-8"),
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        apply_workflow_text=APPLY_WORKFLOW.read_text(encoding="utf-8"),
        tfvars_texts=_default_tfvars(),
    )
    assert not result.ok
    assert any("owner" in err or "accessor-only" in err for err in result.errors)


def test_runtime_write_role_fails() -> None:
    source = load_tf_sources().replace(RUNTIME_ACCESSOR, OPERATOR_WRITE, 1)
    result = validate_boundary_infra(
        tf_source=source,
        cloudbuild_text=CLOUDBUILD.read_text(encoding="utf-8"),
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        apply_workflow_text=APPLY_WORKFLOW.read_text(encoding="utf-8"),
        tfvars_texts=_default_tfvars(),
    )
    assert not result.ok
    assert any("write role" in err or "secretAccessor" in err for err in result.errors)


def test_inline_secret_value_fails() -> None:
    source = load_tf_sources() + '\nresource "google_secret_manager_secret_version" "bad" {\n  secret_data = "super-secret"\n}\n'
    result = validate_boundary_infra(
        tf_source=source,
        cloudbuild_text=CLOUDBUILD.read_text(encoding="utf-8"),
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        apply_workflow_text=APPLY_WORKFLOW.read_text(encoding="utf-8"),
        tfvars_texts=_default_tfvars(),
    )
    assert not result.ok
    assert any("secret versions" in err or "inline secret" in err for err in result.errors)


def test_missing_vpc_egress_fails() -> None:
    text = CLOUDBUILD.read_text(encoding="utf-8").replace(
        "private-ranges-only", "all"
    )
    result = validate_boundary_infra(
        tf_source=load_tf_sources(),
        cloudbuild_text=text,
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        apply_workflow_text=APPLY_WORKFLOW.read_text(encoding="utf-8"),
        tfvars_texts=_default_tfvars(),
    )
    assert not result.ok
    assert any("private-ranges-only" in err for err in result.errors)


def test_workflow_boundary_terraform_job_has_no_apply() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert "boundary-terraform" in jobs
    job = jobs["boundary-terraform"]
    assert job.get("continue-on-error") in (None, False)
    runs = [
        step.get("run", "") for step in job.get("steps", []) if isinstance(step, dict)
    ]
    command_lines = [
        line
        for block in runs
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    joined_commands = "\n".join(command_lines)
    assert "terraform apply" not in joined_commands
    assert "terraform plan" in joined_commands
    assert "terraform fmt -check" in joined_commands
    assert any("upload-artifact" in str(step.get("uses", "")) for step in job["steps"])


def test_apply_workflow_is_environment_gated() -> None:
    text = APPLY_WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" not in text
    assert "workflow_dispatch:" in text
    payload = yaml.safe_load(text)
    job = payload["jobs"]["apply-gate"]
    assert job["environment"] == "boundary-terraform"
    runs = "\n".join(step.get("run", "") for step in job["steps"])
    assert "Do not terraform apply" in runs


def test_fixture_tfvars_are_placeholders() -> None:
    for env in ENVS:
        text = (TF_ROOT / "envs" / env / "fixtures" / "plan.tfvars").read_text(encoding="utf-8")
        assert "example-project" in text
        assert f'environment             = "{env}"' in text


def test_env_roots_exist() -> None:
    for env in ENVS:
        assert (TF_ROOT / "envs" / env / "main.tf").is_file()
        assert (TF_ROOT / "envs" / env / "backend.tf").is_file()


def test_deploy_script_enables_storage_and_passes_boundary_substitutions() -> None:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "storage.googleapis.com" in text
    assert "_QUOTA_REDIS_HOST=" in text
    assert "_BOUNDARY_ENV=" in text
    assert "_RUNTIME_SERVICE_ACCOUNT=" in text
    assert "GCP_QUOTA_REDIS_HOST" in text


def test_staging_secret_fixture_is_synthetic() -> None:
    payload = json.loads(STAGING_SECRETS.read_text(encoding="utf-8"))
    assert payload["environment"] == "staging"
    assert "synthetic" in payload["warning"]
    secrets = payload["secrets"]
    assert secrets["HEATGUARD_API_KEY_PEPPER"]
    assert secrets["HEATGUARD_API_KEY_DIGESTS"]
    assert secrets["HEATGUARD_SESSION_SIGNING_SECRET"]
    blob = json.dumps(payload)
    assert "BEGIN RSA" not in blob


def test_cost_note_documents_rejected_alternative() -> None:
    text = README.read_text(encoding="utf-8")
    assert "Memorystore" in text
    assert "per-instance" in text.lower()
    assert "STANDARD_HA" in text or "STANDARD_HA" in load_tf_sources()
    assert "min-instances=0" in text or "min-instances = 0" in text


def test_runbook_boundary_anchors_resolve() -> None:
    text = RUNBOOKS.read_text(encoding="utf-8")
    required = (
        "## Boundary infrastructure",
        "### Rotate the session signing key",
        "### Disable an integrator secret version",
        "### Revert the VPC connector attachment",
        "### Staging apply and smoke check",
        "## Egress",
    )
    for heading in required:
        assert heading in text, heading
    assert "Open-Meteo" in text
    assert "Memorystore" in text
    assert "Cloud Storage identity object" in text
    assert "boundary-terraform" in text


def test_egress_statements_amended_together() -> None:
    runbooks = RUNBOOKS.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "Memorystore" in runbooks
    assert "Open-Meteo" in runbooks
    assert "private-ranges-only" in runbooks or "private range" in runbooks.lower()
    assert "Memorystore" in deploy
    assert "Open-Meteo" in deploy
    assert "only outbound" not in runbooks.lower() or "Memorystore" in runbooks


def test_monitoring_readme_points_at_boundary_terraform() -> None:
    text = MONITORING_README.read_text(encoding="utf-8")
    assert "infra/terraform" in text
