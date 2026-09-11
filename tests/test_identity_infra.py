"""Offline invariants for the identity Terraform module and Cloud Run wiring (WO-018)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from heatguard._paths import _REPO_ROOT

REPO = _REPO_ROOT
TF_DIR = REPO / "infra" / "identity"
CLOUDBUILD = REPO / "cloudbuild.yaml"
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
RUNBOOKS = REPO / "docs" / "RUNBOOKS.md"
FIXTURE_TFVARS = TF_DIR / "fixtures" / "plan.tfvars"

IDENTITY_OBJECT_SUFFIX = "identity/heatguard-identity.db"
RUNTIME_VIEWER_ROLE = "roles/storage.objectViewer"
OPERATOR_WRITE_ROLE = "roles/storage.objectAdmin"
WRITE_ROLES = frozenset(
    {
        "roles/storage.objectAdmin",
        "roles/storage.admin",
        "roles/storage.objectCreator",
        "roles/storage.objectUser",
        "roles/storage.legacyBucketWriter",
        "roles/storage.legacyBucketOwner",
    }
)
PLACEHOLDER_MARKERS = ("example", "placeholder", "YOUR_", "changeme")


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def load_tf_sources(root: Path = TF_DIR) -> str:
    chunks: list[str] = []
    for path in sorted(root.glob("*.tf")):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def collect_iam_bindings(source: str) -> list[tuple[str, str]]:
    """Return (role, member_expr) pairs from google_storage_bucket_iam_member blocks."""
    blocks = re.findall(
        r'resource\s+"google_storage_bucket_iam_member"\s+"[^"]+"\s*\{(.*?)\n\}',
        source,
        flags=re.DOTALL,
    )
    found: list[tuple[str, str]] = []
    for body in blocks:
        role_m = re.search(r'role\s*=\s*"([^"]+)"', body)
        member_m = re.search(r"member\s*=\s*([^\n]+)", body)
        if role_m and member_m:
            found.append((role_m.group(1), member_m.group(1).strip()))
    return found


def validate_identity_infra(
    *,
    tf_source: str,
    cloudbuild_text: str,
    workflow_text: str,
    tfvars_text: str,
) -> ValidationResult:
    result = ValidationResult()

    if "versioning" not in tf_source or not re.search(
        r"enabled\s*=\s*true", tf_source
    ):
        result.fail("identity bucket must declare versioning { enabled = true }")
    if "uniform_bucket_level_access" not in tf_source or not re.search(
        r"uniform_bucket_level_access\s*=\s*true", tf_source
    ):
        result.fail("identity bucket must enable uniform_bucket_level_access")
    if "days_since_noncurrent_time" not in tf_source:
        result.fail("lifecycle rule must delete noncurrent versions (days_since_noncurrent_time)")
    if not re.search(r'lifecycle_rule[\s\S]*?type\s*=\s*"Delete"', tf_source):
        result.fail("lifecycle rule action type must be Delete")

    if not re.search(
        r'bucket_name\s*=\s*"\$\{var\.bucket_prefix\}-\$\{var\.environment\}-identity"',
        tf_source,
    ):
        result.fail(
            "bucket name must be derived from bucket_prefix and environment "
            "so env collisions are impossible"
        )

    bindings = collect_iam_bindings(tf_source)
    if len(bindings) != 2:
        result.fail(
            f"expected exactly two google_storage_bucket_iam_member bindings, found {len(bindings)}"
        )
    roles = [role for role, _ in bindings]
    if roles.count(RUNTIME_VIEWER_ROLE) != 1:
        result.fail(f"expected exactly one {RUNTIME_VIEWER_ROLE} binding for the runtime account")
    if roles.count(OPERATOR_WRITE_ROLE) != 1:
        result.fail(f"expected exactly one {OPERATOR_WRITE_ROLE} binding for the operator group")

    for role, member in bindings:
        if "runtime_service_account" in member and role in WRITE_ROLES:
            result.fail(
                f"runtime service account must never receive a write role; found {role}"
            )
        if "operator_group" in member and role == RUNTIME_VIEWER_ROLE and OPERATOR_WRITE_ROLE not in roles:
            result.fail("operator group must hold the write role, not only objectViewer")

    if "HEATGUARD_IDENTITY_OBJECT_URI" not in cloudbuild_text:
        result.fail("cloudbuild.yaml must set HEATGUARD_IDENTITY_OBJECT_URI")
    if "HEATGUARD_IDENTITY_REFRESH_SECONDS=300" not in cloudbuild_text and (
        "HEATGUARD_IDENTITY_REFRESH_SECONDS" not in cloudbuild_text
        or "300" not in cloudbuild_text
    ):
        result.fail("cloudbuild.yaml must set HEATGUARD_IDENTITY_REFRESH_SECONDS=300")
    if IDENTITY_OBJECT_SUFFIX not in cloudbuild_text:
        result.fail(f"cloudbuild.yaml identity path must end with {IDENTITY_OBJECT_SUFFIX}")

    if 'backend "gcs"' not in tf_source and "backend \"gcs\"" not in tf_source:
        result.fail('identity module must declare a gcs backend block')
    if re.search(r"(?m)^\s*terraform\s+apply\b", workflow_text):
        result.fail("CI must never run terraform apply")
    if "terraform fmt -check" not in workflow_text:
        result.fail("CI must run terraform fmt -check")
    if "terraform validate" not in workflow_text:
        result.fail("CI must run terraform validate")
    if "terraform plan" not in workflow_text:
        result.fail("CI must run terraform plan")
    if "fixtures/plan.tfvars" not in workflow_text:
        result.fail("CI plan must use the committed fixture tfvars")

    lower_tfvars = tfvars_text.lower()
    if not any(marker in lower_tfvars for marker in PLACEHOLDER_MARKERS):
        result.fail("plan.tfvars must use placeholder project/bucket/SA values, not real identifiers")

    return result


def test_committed_identity_infra_invariants() -> None:
    result = validate_identity_infra(
        tf_source=load_tf_sources(),
        cloudbuild_text=CLOUDBUILD.read_text(encoding="utf-8"),
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        tfvars_text=FIXTURE_TFVARS.read_text(encoding="utf-8"),
    )
    assert result.ok, result.errors


def test_missing_lifecycle_rule_fails() -> None:
    source = re.sub(
        r"lifecycle_rule\s*\{[\s\S]*?\n  \}",
        "",
        load_tf_sources(),
        count=1,
    )
    result = validate_identity_infra(
        tf_source=source,
        cloudbuild_text=CLOUDBUILD.read_text(encoding="utf-8"),
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        tfvars_text=FIXTURE_TFVARS.read_text(encoding="utf-8"),
    )
    assert not result.ok
    assert any("noncurrent" in err for err in result.errors)


def test_runtime_write_role_fails() -> None:
    source = load_tf_sources().replace(RUNTIME_VIEWER_ROLE, "roles/storage.objectAdmin", 1)
    result = validate_identity_infra(
        tf_source=source,
        cloudbuild_text=CLOUDBUILD.read_text(encoding="utf-8"),
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        tfvars_text=FIXTURE_TFVARS.read_text(encoding="utf-8"),
    )
    assert not result.ok
    assert any("write role" in err or "objectViewer" in err for err in result.errors)


def test_missing_identity_uri_fails() -> None:
    text = CLOUDBUILD.read_text(encoding="utf-8").replace(
        "HEATGUARD_IDENTITY_OBJECT_URI", "HEATGUARD_MISSING_URI"
    )
    result = validate_identity_infra(
        tf_source=load_tf_sources(),
        cloudbuild_text=text,
        workflow_text=WORKFLOW.read_text(encoding="utf-8"),
        tfvars_text=FIXTURE_TFVARS.read_text(encoding="utf-8"),
    )
    assert not result.ok
    assert any("HEATGUARD_IDENTITY_OBJECT_URI" in err for err in result.errors)


def test_fixture_tfvars_is_placeholder() -> None:
    text = FIXTURE_TFVARS.read_text(encoding="utf-8")
    assert "example-project" in text
    assert "example-heatguard" in text
    assert IDENTITY_OBJECT_SUFFIX in text


def test_iam_split_comment_present() -> None:
    source = load_tf_sources()
    assert "non-negotiable" in source.lower()


def test_workflow_identity_terraform_job_has_no_apply() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert "identity-terraform" in jobs
    job = jobs["identity-terraform"]
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


def test_runbook_identity_anchors_resolve() -> None:
    text = RUNBOOKS.read_text(encoding="utf-8")
    required = (
        "## Identity object (Cloud Storage)",
        "### Initial upload",
        "### Inspect generations",
        "### Restore from a superseded generation",
        "## Egress",
    )
    for heading in required:
        assert heading in text, heading
    assert "Open-Meteo" in text
    assert IDENTITY_OBJECT_SUFFIX in text
    assert "identity-terraform" in text
