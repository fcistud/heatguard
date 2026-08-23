"""Unit tests for HMAC API-key store and header extraction (WO-003)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from heatguard.boundary.api_keys import (
    ENV_DIGESTS,
    ENV_PEPPER,
    KeyStore,
    compute_digest,
    load_key_store,
    synthetic_bundle,
)
from heatguard.boundary.cors_config import ConfigurationError
from heatguard.boundary.enforcement import extract_presented_secret

FIXTURE = Path(__file__).parent / "fixtures" / "api_key_digests.json"
API_KEYS_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "heatguard" / "boundary" / "api_keys.py"
)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _store(**overrides: str) -> KeyStore:
    payload = _payload()
    env = {
        ENV_PEPPER: payload["pepper"],
        ENV_DIGESTS: json.dumps(payload["bundle"], separators=(",", ":")),
    }
    env.update(overrides)
    return load_key_store(env)


def test_fixture_matches_helper() -> None:
    assert _payload() == synthetic_bundle()


def test_valid_digest_resolves_key_class() -> None:
    payload = _payload()
    store = _store()
    ctx = store.verify(payload["secrets"]["demo-integrator"])
    assert ctx is not None
    assert ctx.principal_id == "demo-integrator"
    assert ctx.key_class == "demo"
    partner = store.verify(payload["secrets"]["partner-integrator"])
    assert partner is not None
    assert partner.key_class == "partner"
    internal = store.verify(payload["secrets"]["internal-integrator"])
    assert internal is not None
    assert internal.key_class == "internal"


def test_unknown_and_revoked_do_not_resolve() -> None:
    payload = _payload()
    store = _store()
    assert store.verify("not-a-real-key") is None
    assert store.verify(payload["secrets"]["revoked-integrator"]) is None


def test_verify_uses_compare_digest() -> None:
    tree = ast.parse(API_KEYS_SOURCE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    assert "compare_digest" in names


def test_store_holds_no_plaintext_or_digest_in_repr() -> None:
    payload = _payload()
    store = _store()
    dumped = repr(store) + str(store)
    assert "redacted" in dumped
    held: list[object] = [store._pepper, *store._by_digest]
    held.extend(record.principal_id for record in store._by_digest.values())
    for secret in payload["secrets"].values():
        assert secret not in dumped
        assert secret not in held
        assert secret.encode("utf-8") not in held
    for entry in payload["bundle"].values():
        assert entry["digest"] not in dumped
    assert payload["pepper"] not in dumped


def test_empty_bundle_fails_boot() -> None:
    payload = _payload()
    with pytest.raises(ConfigurationError, match="empty"):
        load_key_store({ENV_PEPPER: payload["pepper"], ENV_DIGESTS: ""})
    with pytest.raises(ConfigurationError, match="empty"):
        load_key_store({ENV_PEPPER: payload["pepper"], ENV_DIGESTS: "{}"})
    with pytest.raises(ConfigurationError, match="missing"):
        load_key_store({ENV_PEPPER: payload["pepper"]})


def test_malformed_bundle_fails_boot() -> None:
    payload = _payload()
    with pytest.raises(ConfigurationError, match="JSON"):
        load_key_store({ENV_PEPPER: payload["pepper"], ENV_DIGESTS: "not-json"})
    with pytest.raises(ConfigurationError, match="key_class"):
        load_key_store(
            {
                ENV_PEPPER: payload["pepper"],
                ENV_DIGESTS: json.dumps(
                    {"x": {"digest": "a" * 64, "key_class": "admin", "active": True}}
                ),
            }
        )


def test_duplicate_digest_fails_boot() -> None:
    payload = _payload()
    digest = payload["bundle"]["demo-integrator"]["digest"]
    bundle = {
        "one": {"digest": digest, "key_class": "demo", "active": True},
        "two": {"digest": digest, "key_class": "partner", "active": True},
    }
    with pytest.raises(ConfigurationError, match="Duplicate"):
        load_key_store({ENV_PEPPER: payload["pepper"], ENV_DIGESTS: json.dumps(bundle)})


def test_missing_pepper_fails_boot() -> None:
    payload = _payload()
    with pytest.raises(ConfigurationError, match="PEPPER"):
        load_key_store({ENV_DIGESTS: json.dumps(payload["bundle"])})


def test_extract_x_api_key_and_bearer_match() -> None:
    secret = b"hg_synth_demo_key_aaaaaaaaaaaaaaaa"
    assert extract_presented_secret([(b"x-api-key", secret)]).secret == secret.decode()
    bearer = extract_presented_secret([(b"authorization", b"Bearer " + secret)])
    assert bearer.secret == secret.decode()
    both = extract_presented_secret(
        [(b"x-api-key", secret), (b"authorization", b"Bearer " + secret)]
    )
    assert both.secret == secret.decode()
    assert both.refuse is False


def test_extract_conflict_and_malformed() -> None:
    assert extract_presented_secret(
        [
            (b"x-api-key", b"aaa"),
            (b"authorization", b"Bearer bbb"),
        ]
    ).refuse is True
    assert extract_presented_secret([(b"x-api-key", b"   ")]).refuse is True
    assert extract_presented_secret([(b"x-api-key", b"")]).refuse is True
    assert extract_presented_secret([(b"x-api-key", "café".encode())]).refuse is True
    assert extract_presented_secret([(b"x-api-key", b"x" * 257)]).refuse is True
    assert extract_presented_secret([]).secret is None
    assert extract_presented_secret([]).refuse is False


def test_compute_digest_matches_fixture() -> None:
    payload = _payload()
    secret = payload["secrets"]["demo-integrator"]
    assert compute_digest(payload["pepper"], secret) == payload["bundle"]["demo-integrator"]["digest"]
