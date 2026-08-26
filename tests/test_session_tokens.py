"""Unit tests for local HS256 session verification (WO-004)."""
from __future__ import annotations

import ast
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from heatguard.boundary.cors_config import ConfigurationError
from heatguard.boundary.session_tokens import (
    ENV_KID,
    ENV_SIGNING_SECRET,
    ENV_SNAPSHOT,
    KEY_CLASS_DASHBOARD,
    MAX_LIFETIME_SECONDS,
    SESSION_MAX_AGE,
    SessionFailure,
    _b64url_encode,
    default_claims,
    load_session_auth,
    mint_session_token,
    synthetic_session_fixture,
    verify_session,
)

FIXTURE = Path(__file__).parent / "fixtures" / "session_tokens.json"
SOURCE = Path(__file__).resolve().parents[1] / "src" / "heatguard" / "boundary" / "session_tokens.py"
NOW = 1_700_000_000


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _auth(**overrides: str):
    payload = _payload()
    env = {
        ENV_SIGNING_SECRET: payload["signing_secret"],
        ENV_KID: payload["kid"],
        ENV_SNAPSHOT: json.dumps(payload["principals"], separators=(",", ":")),
    }
    env.update(overrides)
    return load_session_auth(env)


def _token(*, sub: str = "dashboard-supervisor", **claim_overrides: object) -> str:
    payload = _payload()
    principal = payload["principals"].get(sub, payload["principals"]["dashboard-supervisor"])
    claims = default_claims(
        sub=sub,
        now=NOW,
        token_version=int(principal["token_version"]),
        roles=list(principal["roles"]),
        sites=["dubai"] if principal["sites"] == ["*"] else list(principal["sites"]),
    )
    claims.update(claim_overrides)
    return mint_session_token(
        secret=payload["signing_secret"],
        claims=claims,
        kid=payload["kid"],
    )


def _verify(token: str, *, now: float = NOW):
    payload = _payload()
    auth = _auth()
    return verify_session(
        token,
        secret=auth._secret,
        snapshot=auth.snapshot,
        kid=payload["kid"],
        now=now,
        clock_skew_seconds=auth.clock_skew_seconds,
    )


def test_fixture_matches_helper() -> None:
    assert _payload() == synthetic_session_fixture()


def test_valid_token_resolves_dashboard_principal() -> None:
    result = _verify(_token())
    assert result.reason is None
    assert result.principal is not None
    assert result.principal.principal_id == "dashboard-supervisor"
    assert result.principal.key_class == KEY_CLASS_DASHBOARD
    assert result.principal.roles == ("supervisor",)
    assert result.principal.sites == ("dubai",)
    assert result.principal.review_context == "spot_check"
    assert result.principal.auth_time == NOW
    assert result.principal.token_version == 1


def test_accepted_tokens_never_exceed_lifetime_ceiling() -> None:
    from heatguard.boundary.session_tokens import _b64url_decode

    tokens = [
        _token(),
        _token(sub="dashboard-inspector", roles=["inspector"], sites=["*"], token_version=3),
    ]
    for token in tokens:
        result = _verify(token)
        assert result.principal is not None
        raw = _b64url_decode(token.split(".")[1])
        assert raw is not None
        payload = json.loads(raw)
        assert payload["exp"] - payload["iat"] <= MAX_LIFETIME_SECONDS


def test_lifetime_3600_inclusive_3601_refused() -> None:
    ok = _verify(_token(exp=NOW + MAX_LIFETIME_SECONDS, iat=NOW))
    assert ok.principal is not None
    bad = _verify(_token(exp=NOW + MAX_LIFETIME_SECONDS + 1, iat=NOW))
    assert bad.principal is None
    assert bad.reason is SessionFailure.INVALID


def test_auth_time_ceiling_inclusive() -> None:
    ok = _verify(_token(auth_time=NOW - SESSION_MAX_AGE), now=NOW)
    assert ok.principal is not None
    over = _verify(_token(auth_time=NOW - SESSION_MAX_AGE - 1), now=NOW)
    assert over.principal is None
    assert over.reason is SessionFailure.ABSOLUTE_CEILING


def test_expired_beyond_skew_is_idle_expiry() -> None:
    auth = _auth()
    skew = auth.clock_skew_seconds
    expired = _verify(
        _token(exp=NOW - skew - 1, iat=NOW - MAX_LIFETIME_SECONDS),
        now=NOW,
    )
    assert expired.reason is SessionFailure.IDLE_EXPIRY
    within = _verify(
        _token(exp=NOW - skew + 1, iat=NOW - MAX_LIFETIME_SECONDS + 1),
        now=NOW,
    )
    assert within.principal is not None


def test_stale_token_version_is_revoked() -> None:
    result = _verify(_token(token_version=0))
    assert result.reason is SessionFailure.REVOKED


def test_inactive_and_missing_principal_are_deactivated() -> None:
    inactive = _verify(
        _token(sub="dashboard-inactive", token_version=1, roles=["supervisor"])
    )
    assert inactive.reason is SessionFailure.DEACTIVATED
    missing = _verify(_token(sub="deleted-account", token_version=1, roles=["supervisor"]))
    assert missing.reason is SessionFailure.DEACTIVATED


def test_alg_none_and_rs256_rejected() -> None:
    payload = _payload()
    claims = default_claims(
        sub="dashboard-supervisor",
        now=NOW,
        token_version=1,
        roles=["supervisor"],
        sites=["dubai"],
    )
    good = mint_session_token(
        secret=payload["signing_secret"], claims=claims, kid=payload["kid"]
    )
    _header, body, sig = good.split(".")

    def _swap_alg(alg: str) -> str:
        raw = json.dumps({"alg": alg, "kid": payload["kid"], "typ": "JWT"}, separators=(",", ":"))
        return f"{_b64url_encode(raw.encode())}.{body}.{sig}"

    assert _verify(_swap_alg("none")).reason is SessionFailure.INVALID
    assert _verify(_swap_alg("RS256")).reason is SessionFailure.INVALID
    assert _verify(_swap_alg("ES256")).reason is SessionFailure.INVALID


def test_kid_mismatch_and_missing_kid_refused() -> None:
    payload = _payload()
    claims = default_claims(
        sub="dashboard-supervisor",
        now=NOW,
        token_version=1,
        roles=["supervisor"],
        sites=["dubai"],
    )
    wrong = mint_session_token(secret=payload["signing_secret"], claims=claims, kid="other")
    assert _verify(wrong).reason is SessionFailure.INVALID
    missing = mint_session_token(secret=payload["signing_secret"], claims=claims, kid=None)
    assert _verify(missing).reason is SessionFailure.INVALID


def test_bad_signature_and_tampered_payload_refused() -> None:
    token = _token()
    header, body, sig = token.split(".")
    forged = f"{header}.{body}.{sig[:-2]}aa"
    assert _verify(forged).reason is SessionFailure.INVALID
    tampered_body = body[:-1] + ("A" if body[-1] != "A" else "B")
    tampered = f"{header}.{tampered_body}.{sig}"
    assert _verify(tampered).reason is SessionFailure.INVALID


def test_malformed_shapes_refused() -> None:
    for token in ("", "a.b", "a.b.c.d", "....", "not-a-jwt"):
        assert _verify(token).reason is SessionFailure.INVALID


def test_non_object_payload_refused() -> None:
    payload = _payload()
    claims = default_claims(
        sub="dashboard-supervisor",
        now=NOW,
        token_version=1,
        roles=["supervisor"],
        sites=["dubai"],
    )
    header = mint_session_token(
        secret=payload["signing_secret"], claims=claims, kid=payload["kid"]
    ).split(".")[0]
    array_payload = _b64url_encode(b"[1,2,3]")
    signing_input = f"{header}.{array_payload}".encode("ascii")
    sig = hmac.new(payload["signing_secret"].encode(), signing_input, hashlib.sha256).digest()
    token = f"{header}.{array_payload}.{_b64url_encode(sig)}"
    assert _verify(token).reason is SessionFailure.INVALID


def test_bool_token_version_refused() -> None:
    result = _verify(_token(token_version=True))  # type: ignore[arg-type]
    assert result.reason is SessionFailure.INVALID


def test_non_inspector_wildcard_sites_refused() -> None:
    result = _verify(_token(sites=["*"]))
    assert result.reason is SessionFailure.INVALID


def test_role_widening_refused() -> None:
    result = _verify(_token(roles=["supervisor", "inspector"]))
    assert result.reason is SessionFailure.INVALID


def test_verify_uses_compare_digest() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    assert "compare_digest" in names


def test_repr_hides_signing_secret() -> None:
    payload = _payload()
    auth = _auth()
    dumped = repr(auth) + str(auth)
    assert "redacted" in dumped
    assert payload["signing_secret"] not in dumped


def test_missing_or_short_secret_fails_boot() -> None:
    payload = _payload()
    snapshot = json.dumps(payload["principals"])
    with pytest.raises(ConfigurationError, match="SIGNING_SECRET"):
        load_session_auth({ENV_SNAPSHOT: snapshot, ENV_KID: payload["kid"]})
    with pytest.raises(ConfigurationError, match="shorter"):
        load_session_auth(
            {
                ENV_SIGNING_SECRET: "too-short",
                ENV_SNAPSHOT: snapshot,
                ENV_KID: payload["kid"],
            }
        )


def test_empty_snapshot_fails_boot() -> None:
    payload = _payload()
    with pytest.raises(ConfigurationError, match="empty"):
        load_session_auth(
            {
                ENV_SIGNING_SECRET: payload["signing_secret"],
                ENV_KID: payload["kid"],
                ENV_SNAPSHOT: "",
            }
        )
    with pytest.raises(ConfigurationError, match="empty"):
        load_session_auth(
            {
                ENV_SIGNING_SECRET: payload["signing_secret"],
                ENV_KID: payload["kid"],
                ENV_SNAPSHOT: "{}",
            }
        )


def test_non_inspector_wildcard_in_snapshot_fails_boot() -> None:
    payload = _payload()
    bad = {
        "oops": {
            "roles": ["supervisor"],
            "sites": ["*"],
            "token_version": 1,
            "active": True,
        }
    }
    with pytest.raises(ConfigurationError, match="inspector-only"):
        load_session_auth(
            {
                ENV_SIGNING_SECRET: payload["signing_secret"],
                ENV_KID: payload["kid"],
                ENV_SNAPSHOT: json.dumps(bad),
            }
        )
