"""Required CI gate: login/lockout/last-login state never hits the shared quota store."""
from __future__ import annotations

import ast
from pathlib import Path

from heatguard.boundary.quota_redis import (
    KEY_PREFIX,
    InMemoryQuotaRedis,
    RedisQuotaStore,
    redis_quota_key,
)
from heatguard._paths import _REPO_ROOT

SRC = _REPO_ROOT / "src" / "heatguard"
FORBIDDEN_MARKERS = (
    "hg:login:",
    "hg:lockout:",
    "hg:last-login:",
    "failed-login",
    "failed_login",
    "last_login",
    "last-successful-login",
    "lockout:",
)
IDENTITY_MODULES = (
    "boundary/session_tokens.py",
    "boundary/api_keys.py",
    "boundary/auth_mode.py",
)


def test_quota_eval_keys_use_quota_prefix_only() -> None:
    fake = InMemoryQuotaRedis()
    store = RedisQuotaStore(fake)
    store.consume("anon:none|reference", 1.0, 0.0, capacity=4.0, refill_per_sec=1.0)
    store.consume("user-1|advisory", 1.0, 0.0, capacity=4.0, refill_per_sec=1.0)
    keys = [str(cmd[3][0]) for cmd in fake.commands if cmd[0] == "EVAL"]
    assert keys
    for key in keys:
        assert key.startswith(KEY_PREFIX)
        blob = key.lower()
        for marker in FORBIDDEN_MARKERS:
            assert marker not in blob
    assert redis_quota_key("anon:none|reference") in keys


def test_identity_modules_do_not_import_redis() -> None:
    for rel in IDENTITY_MODULES:
        text = (SRC / rel).read_text(encoding="utf-8")
        assert "import redis" not in text
        assert "from redis" not in text


def test_only_quota_redis_module_imports_redis_client() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.name == "quota_redis.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "redis" or alias.name.startswith("redis."):
                        offenders.append(str(path.relative_to(SRC)))
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module == "redis" or node.module.startswith("redis.")
            ):
                offenders.append(str(path.relative_to(SRC)))
    assert offenders == []
