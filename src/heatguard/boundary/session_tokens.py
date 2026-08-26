"""Local HS256 session-token verification (WO-004).

Signing material is loaded once at boot. The request path parses a compact JWS,
verifies the HMAC in constant time, and validates claims against an in-memory
identity snapshot — no JWKS, no introspection, no I/O.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from heatguard.boundary.cors_config import ConfigurationError
from heatguard.types import PrincipalContext

ENV_SIGNING_SECRET = "HEATGUARD_SESSION_SIGNING_SECRET"
ENV_KID = "HEATGUARD_SESSION_KID"
ENV_SNAPSHOT = "HEATGUARD_IDENTITY_SNAPSHOT"
ENV_CLOCK_SKEW = "HEATGUARD_SESSION_CLOCK_SKEW_SECONDS"

ALG_HS256 = "HS256"
KEY_CLASS_DASHBOARD = "dashboard"
REVIEW_CONTEXTS = frozenset({"spot_check", "formal_audit"})
ROLE_INSPECTOR = "inspector"
MAX_LIFETIME_SECONDS = 3600
SESSION_MAX_AGE = 50400
DEFAULT_CLOCK_SKEW_SECONDS = 30
MIN_SECRET_BYTES = 32
MAX_TOKEN_CHARS = 4096
REQUIRED_CLAIMS = frozenset(
    {
        "sub",
        "roles",
        "sites",
        "review_context",
        "key_class",
        "auth_time",
        "iat",
        "exp",
        "token_version",
    }
)
_REDACTED_REPR = "SessionAuth(redacted)"


class SessionFailure(str, Enum):
    """Re-auth reason vocabulary — logs/counters only, never the HTTP body."""

    INVALID = "invalid"
    ABSOLUTE_CEILING = "absolute_ceiling"
    IDLE_EXPIRY = "idle_expiry"
    REVOKED = "revoked"
    DEACTIVATED = "deactivated"


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    roles: tuple[str, ...]
    sites: tuple[str, ...]
    token_version: int
    active: bool


class IdentitySnapshot(Protocol):
    """Narrow lookup used by the verifier — fixture or Cloud Storage loader."""

    def lookup(self, principal_id: str) -> IdentityRecord | None:
        ...


@dataclass(frozen=True, slots=True)
class MapIdentitySnapshot:
    """In-memory snapshot. ``lookup`` is a dict get — no I/O."""

    _records: Mapping[str, IdentityRecord]

    def lookup(self, principal_id: str) -> IdentityRecord | None:
        return self._records.get(principal_id)


@dataclass(frozen=True, slots=True)
class SessionVerifyResult:
    principal: PrincipalContext | None
    reason: SessionFailure | None


class SessionAuthRef:
    """Mutable slot filled once in FastAPI lifespan — not a token cache."""

    __slots__ = ("auth",)

    def __init__(self) -> None:
        self.auth: SessionAuth | None = None


def looks_like_compact_jws(token: str) -> bool:
    """True when ``token`` has exactly three non-empty dot-separated segments."""
    if not token or token.count(".") != 2:
        return False
    h, p, s = token.split(".")
    return bool(h) and bool(p) and bool(s)


def _b64url_decode(raw: str) -> bytes | None:
    if not raw or any(ch in raw for ch in "+/="):
        return None
    padding = "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(raw + padding)
    except (ValueError, OSError):
        return None


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _is_int(value: object) -> bool:
    return type(value) is int


def _string_tuple(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            return None
        out.append(item)
    return tuple(out)


def mint_session_token(
    *,
    secret: str | bytes,
    claims: Mapping[str, Any],
    kid: str | None = None,
) -> str:
    """Offline compact-JWS mint for tests. Not a production issuance path."""
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    header: dict[str, Any] = {"alg": ALG_HS256, "typ": "JWT"}
    if kid is not None:
        header["kid"] = kid
    header_part = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    payload_part = _b64url_encode(json.dumps(dict(claims), separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    sig = hmac.new(key, signing_input, hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{_b64url_encode(sig)}"


@dataclass(frozen=True, slots=True)
class SessionAuth:
    """Boot-loaded verifier. ``repr``/``str`` never leak the signing secret."""

    _secret: bytes
    _kid: str | None
    snapshot: IdentitySnapshot
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS

    def __repr__(self) -> str:
        return _REDACTED_REPR

    def __str__(self) -> str:
        return _REDACTED_REPR

    def verify(self, token: str, *, now: float | None = None) -> SessionVerifyResult:
        """Verify ``token`` against local key material and the identity snapshot."""
        return verify_session(
            token,
            secret=self._secret,
            snapshot=self.snapshot,
            kid=self._kid,
            now=now,
            clock_skew_seconds=self.clock_skew_seconds,
        )


def verify_session(
    token: str,
    *,
    secret: bytes,
    snapshot: IdentitySnapshot,
    kid: str | None = None,
    now: float | None = None,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
) -> SessionVerifyResult:
    """Pure CPU verification. Callers inject ``now`` in tests."""
    invalid = SessionVerifyResult(principal=None, reason=SessionFailure.INVALID)
    if not token or len(token) > MAX_TOKEN_CHARS or not looks_like_compact_jws(token):
        return invalid
    header_b64, payload_b64, sig_b64 = token.split(".")
    header_raw = _b64url_decode(header_b64)
    if header_raw is None:
        return invalid
    try:
        header = json.loads(header_raw)
    except json.JSONDecodeError:
        return invalid
    if not isinstance(header, dict):
        return invalid
    # Alg allowlist before any signature work (alg-confusion / none).
    if header.get("alg") != ALG_HS256:
        return invalid
    if "crit" in header:
        return invalid
    if kid is not None:
        presented_kid = header.get("kid")
        if presented_kid != kid:
            return invalid

    payload_raw = _b64url_decode(payload_b64)
    sig_raw = _b64url_decode(sig_b64)
    if payload_raw is None or sig_raw is None:
        return invalid
    expected = hmac.new(
        secret,
        f"{header_b64}.{payload_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    if len(sig_raw) != len(expected) or not hmac.compare_digest(sig_raw, expected):
        return invalid

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return invalid
    if not isinstance(payload, dict):
        return invalid
    return _validate_claims(
        payload,
        snapshot=snapshot,
        now=now,
        clock_skew_seconds=clock_skew_seconds,
    )


def _validate_claims(
    payload: Mapping[str, Any],
    *,
    snapshot: IdentitySnapshot,
    now: float | None,
    clock_skew_seconds: int,
) -> SessionVerifyResult:
    invalid = SessionVerifyResult(principal=None, reason=SessionFailure.INVALID)
    if not REQUIRED_CLAIMS <= payload.keys():
        return invalid
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        return invalid
    roles = _string_tuple(payload.get("roles"))
    sites = _string_tuple(payload.get("sites"))
    if roles is None or sites is None:
        return invalid
    review_context = payload.get("review_context")
    if review_context not in REVIEW_CONTEXTS:
        return invalid
    if payload.get("key_class") != KEY_CLASS_DASHBOARD:
        return invalid
    iat = payload.get("iat")
    exp = payload.get("exp")
    auth_time = payload.get("auth_time")
    token_version = payload.get("token_version")
    if not _is_int(iat) or not _is_int(exp) or not _is_int(auth_time) or not _is_int(token_version):
        return invalid
    if token_version < 0 or auth_time < 0 or iat < 0 or exp < 0:
        return invalid
    # Inclusive at-most: 3600 is accepted, 3601 is not.
    if exp - iat > MAX_LIFETIME_SECONDS:
        return invalid

    now_ts = float(now if now is not None else time.time())
    if now_ts - clock_skew_seconds > exp:
        return SessionVerifyResult(principal=None, reason=SessionFailure.IDLE_EXPIRY)
    if iat - clock_skew_seconds > now_ts:
        return invalid
    # Inclusive lineage ceiling: exactly SESSION_MAX_AGE is accepted.
    if now_ts - auth_time > SESSION_MAX_AGE:
        return SessionVerifyResult(principal=None, reason=SessionFailure.ABSOLUTE_CEILING)

    record = snapshot.lookup(sub)
    if record is None or not record.active:
        return SessionVerifyResult(principal=None, reason=SessionFailure.DEACTIVATED)
    if token_version < record.token_version:
        return SessionVerifyResult(principal=None, reason=SessionFailure.REVOKED)
    if token_version != record.token_version:
        return invalid
    if ROLE_INSPECTOR not in record.roles and "*" in record.sites:
        return invalid
    token_role_set = set(roles)
    snap_role_set = set(record.roles)
    if not token_role_set <= snap_role_set:
        return invalid
    if record.sites != ("*",) and not set(sites) <= set(record.sites):
        return invalid
    if "*" in sites and ROLE_INSPECTOR not in record.roles:
        return invalid

    return SessionVerifyResult(
        principal=PrincipalContext(
            principal_id=sub,
            key_class=KEY_CLASS_DASHBOARD,
            roles=roles,
            sites=sites,
            review_context=str(review_context),
            auth_time=auth_time,
            token_version=token_version,
        ),
        reason=None,
    )


def parse_identity_snapshot(raw: object) -> MapIdentitySnapshot:
    """Parse a JSON object of principal id → identity fields."""
    if not isinstance(raw, dict) or not raw:
        raise ConfigurationError(
            f"{ENV_SNAPSHOT} must be a non-empty JSON object of principals."
        )
    records: dict[str, IdentityRecord] = {}
    for principal_id, entry in raw.items():
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ConfigurationError("Identity principal id must be a non-empty string.")
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Identity {principal_id!r} entry must be a JSON object."
            )
        roles = _string_tuple(entry.get("roles"))
        sites = _string_tuple(entry.get("sites"))
        token_version = entry.get("token_version")
        active = entry.get("active")
        if roles is None or sites is None:
            raise ConfigurationError(
                f"Identity {principal_id!r} roles and sites must be non-empty string arrays."
            )
        if not _is_int(token_version) or token_version < 0:
            raise ConfigurationError(
                f"Identity {principal_id!r} token_version must be a non-negative integer."
            )
        if not isinstance(active, bool):
            raise ConfigurationError(
                f"Identity {principal_id!r} active flag must be a JSON boolean."
            )
        if ROLE_INSPECTOR not in roles and "*" in sites:
            raise ConfigurationError(
                f"Identity {principal_id!r} wildcard sites are inspector-only."
            )
        records[principal_id.strip()] = IdentityRecord(
            roles=roles,
            sites=sites,
            token_version=token_version,
            active=active,
        )
    return MapIdentitySnapshot(records)


def load_session_auth(env: Mapping[str, str]) -> SessionAuth:
    """Parse signing secret + snapshot. Missing/too-short secret → fail boot."""
    secret = (env.get(ENV_SIGNING_SECRET) or "").strip()
    if not secret:
        raise ConfigurationError(
            f"{ENV_SIGNING_SECRET} is missing or empty — refusing to start with "
            "unverifiable session tokens."
        )
    secret_bytes = secret.encode("utf-8")
    if len(secret_bytes) < MIN_SECRET_BYTES:
        raise ConfigurationError(
            f"{ENV_SIGNING_SECRET} is shorter than {MIN_SECRET_BYTES} bytes — "
            "refusing to start with a weak HMAC key."
        )
    kid_raw = (env.get(ENV_KID) or "").strip()
    kid = kid_raw or None
    snapshot_raw = env.get(ENV_SNAPSHOT)
    if snapshot_raw is None or not str(snapshot_raw).strip():
        raise ConfigurationError(
            f"{ENV_SNAPSHOT} is missing or empty — refusing to start with no "
            "identity snapshot."
        )
    try:
        parsed = json.loads(snapshot_raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"{ENV_SNAPSHOT} is not valid JSON — refusing to start."
        ) from exc
    snapshot = parse_identity_snapshot(parsed)
    skew_raw = (env.get(ENV_CLOCK_SKEW) or "").strip()
    if skew_raw:
        try:
            skew = int(skew_raw)
        except ValueError as exc:
            raise ConfigurationError(
                f"{ENV_CLOCK_SKEW} must be an integer number of seconds."
            ) from exc
        if skew < 0 or skew > 120:
            raise ConfigurationError(
                f"{ENV_CLOCK_SKEW} must be between 0 and 120 seconds."
            )
    else:
        skew = DEFAULT_CLOCK_SKEW_SECONDS
    return SessionAuth(
        _secret=secret_bytes,
        _kid=kid,
        snapshot=snapshot,
        clock_skew_seconds=skew,
    )


def synthetic_session_fixture() -> dict[str, Any]:
    """Deterministic offline fixture — not a production secret or identity."""
    secret = "hg-synth-session-hs256-not-for-production"
    kid = "hg-synth"
    principals = {
        "dashboard-inspector": {
            "roles": ["inspector"],
            "sites": ["*"],
            "token_version": 3,
            "active": True,
        },
        "dashboard-supervisor": {
            "roles": ["supervisor"],
            "sites": ["dubai"],
            "token_version": 1,
            "active": True,
        },
        "dashboard-inactive": {
            "roles": ["supervisor"],
            "sites": ["dubai"],
            "token_version": 1,
            "active": False,
        },
    }
    return {"signing_secret": secret, "kid": kid, "principals": principals}


def default_claims(
    *,
    sub: str,
    now: int,
    lifetime: int = MAX_LIFETIME_SECONDS,
    auth_time: int | None = None,
    token_version: int = 1,
    roles: list[str] | None = None,
    sites: list[str] | None = None,
    review_context: str = "spot_check",
    key_class: str = KEY_CLASS_DASHBOARD,
) -> dict[str, Any]:
    """Claim set for the minting helper. Inclusive lifetime defaults to 3600."""
    return {
        "sub": sub,
        "roles": roles if roles is not None else ["supervisor"],
        "sites": sites if sites is not None else ["dubai"],
        "review_context": review_context,
        "key_class": key_class,
        "auth_time": now if auth_time is None else auth_time,
        "iat": now,
        "exp": now + lifetime,
        "token_version": token_version,
    }
