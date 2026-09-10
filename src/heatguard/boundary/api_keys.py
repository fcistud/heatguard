"""Integrator API-key HMAC digest store (WO-003).

Digests and the HMAC pepper are loaded once at boot. The request path only
hashes the presented secret and does a constant-time compare — no I/O.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from heatguard.boundary.cors_config import ConfigurationError
from heatguard.types import PrincipalContext

ENV_DIGESTS = "HEATGUARD_API_KEY_DIGESTS"
ENV_PEPPER = "HEATGUARD_API_KEY_PEPPER"
KEY_CLASSES = frozenset({"demo", "partner", "internal"})
MAX_SECRET_CHARS = 256
_DUMMY_DIGEST = "0" * 64
_REDACTED_REPR = "KeyStore(redacted)"


def compute_digest(pepper: str | bytes, secret: str) -> str:
    """HMAC-SHA-256 hex digest of ``secret`` keyed by ``pepper``."""
    key = pepper.encode("utf-8") if isinstance(pepper, str) else pepper
    return hmac.new(key, secret.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class _KeyRecord:
    principal_id: str
    key_class: str
    active: bool
    digest: str


class KeyStoreRef:
    """Mutable slot filled once in FastAPI lifespan — not a credential cache."""

    __slots__ = ("store",)

    def __init__(self) -> None:
        self.store: KeyStore | None = None


@dataclass(frozen=True, slots=True)
class KeyStore:
    """Immutable boot-time credential set. ``repr``/``str`` never leak material."""

    _pepper: bytes
    _by_digest: dict[str, _KeyRecord]

    def __repr__(self) -> str:
        return _REDACTED_REPR

    def __str__(self) -> str:
        return _REDACTED_REPR

    def __len__(self) -> int:
        return len(self._by_digest)

    def verify(self, presented: str) -> PrincipalContext | None:
        """Return a principal if ``presented`` matches an active digest."""
        digest = compute_digest(self._pepper, presented)
        record = self._by_digest.get(digest)
        expected = record.digest if record is not None else _DUMMY_DIGEST
        if not hmac.compare_digest(digest, expected):
            return None
        if record is None or not record.active:
            return None
        return PrincipalContext(
            principal_id=record.principal_id,
            key_class=record.key_class,
        )


def load_key_store(env: Mapping[str, str]) -> KeyStore:
    """Parse ``HEATGUARD_API_KEY_DIGESTS`` + pepper. Empty/malformed → fail boot."""
    pepper = (env.get(ENV_PEPPER) or "").strip()
    if not pepper:
        raise ConfigurationError(
            f"{ENV_PEPPER} is missing or empty — refusing to start with no HMAC key."
        )
    raw = env.get(ENV_DIGESTS)
    if raw is None or not str(raw).strip():
        raise ConfigurationError(
            f"{ENV_DIGESTS} is missing or empty — refusing to start with an empty "
            "credential set."
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"{ENV_DIGESTS} is not valid JSON — refusing to start."
        ) from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ConfigurationError(
            f"{ENV_DIGESTS} must be a non-empty JSON object of integrator entries."
        )

    by_digest: dict[str, _KeyRecord] = {}
    for principal_id, entry in parsed.items():
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ConfigurationError("Integrator id must be a non-empty string.")
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Integrator {principal_id!r} entry must be a JSON object."
            )
        digest = entry.get("digest")
        key_class = entry.get("key_class")
        active = entry.get("active")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ConfigurationError(
                f"Integrator {principal_id!r} digest must be a 64-char hex HMAC-SHA-256."
            )
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ConfigurationError(
                f"Integrator {principal_id!r} digest is not hexadecimal."
            ) from exc
        if key_class not in KEY_CLASSES:
            raise ConfigurationError(
                f"Integrator {principal_id!r} has unknown key_class {key_class!r}; "
                f"expected one of {sorted(KEY_CLASSES)}."
            )
        if not isinstance(active, bool):
            raise ConfigurationError(
                f"Integrator {principal_id!r} active flag must be a JSON boolean."
            )
        digest_l = digest.lower()
        if digest_l in by_digest:
            raise ConfigurationError(
                "Duplicate digest in API key bundle — refusing ambiguous principal."
            )
        by_digest[digest_l] = _KeyRecord(
            principal_id=principal_id.strip(),
            key_class=str(key_class),
            active=active,
            digest=digest_l,
        )

    if not by_digest:
        raise ConfigurationError(
            f"{ENV_DIGESTS} parsed to zero integrators — refusing to start."
        )
    return KeyStore(pepper.encode("utf-8"), by_digest)


def synthetic_bundle() -> dict[str, Any]:
    """Deterministic offline fixture — not a production secret."""
    pepper = "hg-synth-pepper-wo003-not-for-production"
    secrets = {
        "demo-integrator": "hg_synth_demo_key_aaaaaaaaaaaaaaaa",
        "partner-integrator": "hg_synth_partner_key_bbbbbbbbbbbb",
        "internal-integrator": "hg_synth_internal_key_cccccccccccc",
        "revoked-integrator": "hg_synth_revoked_key_dddddddddddd",
    }
    classes = {
        "demo-integrator": "demo",
        "partner-integrator": "partner",
        "internal-integrator": "internal",
        "revoked-integrator": "demo",
    }
    active = {
        "demo-integrator": True,
        "partner-integrator": True,
        "internal-integrator": True,
        "revoked-integrator": False,
    }
    bundle = {
        principal_id: {
            "digest": compute_digest(pepper, secret),
            "key_class": classes[principal_id],
            "active": active[principal_id],
        }
        for principal_id, secret in secrets.items()
    }
    return {"pepper": pepper, "secrets": secrets, "bundle": bundle}
