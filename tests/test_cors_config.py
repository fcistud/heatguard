"""Unit tests for environment-scoped CORS resolution (WO-001)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from heatguard.boundary.cors_config import (
    CORS_HEADERS,
    CORS_METHODS,
    ConfigurationError,
    DEV_DEFAULT_ORIGINS,
    ENV_VAR_ALLOW_WILDCARD,
    ENV_VAR_ORIGINS,
    normalize_origin,
    resolve_cors_settings,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cors_env_matrix.json"


def _matrix_cases() -> list[dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return list(payload["cases"])


@pytest.mark.parametrize("case", _matrix_cases(), ids=lambda c: c["id"])
def test_cors_env_matrix(case: dict) -> None:
    expect = case["expect"]
    if expect["raises"]:
        with pytest.raises(ConfigurationError) as excinfo:
            resolve_cors_settings(case["env"])
        msg = str(excinfo.value)
        assert ENV_VAR_ORIGINS in msg
        if "wildcard" in case["id"] or case["env"].get(ENV_VAR_ORIGINS) == "*":
            assert ENV_VAR_ALLOW_WILDCARD in msg or "wildcard" in msg.lower()
        return

    settings = resolve_cors_settings(case["env"])
    assert settings.origins == tuple(expect["origins"])
    assert settings.methods == CORS_METHODS
    assert settings.headers == CORS_HEADERS
    assert settings.allow_credentials is False
    assert "*" not in settings.origins or case["id"].endswith("with_opt_in")


def test_default_resolution_has_no_wildcard() -> None:
    settings = resolve_cors_settings({})
    assert settings.origins == DEV_DEFAULT_ORIGINS
    assert "*" not in settings.origins
    assert "http://localhost:5173" in settings.origins


def test_comma_whitespace_and_duplicate_collapsing() -> None:
    settings = resolve_cors_settings(
        {
            "HEATGUARD_CORS_ORIGINS": (
                " http://localhost:5173 , http://localhost:5173,"
                "https://App.Example.com/ "
            )
        }
    )
    assert settings.origins == (
        "http://localhost:5173",
        "https://app.example.com",
    )


def test_trailing_slash_normalisation() -> None:
    assert normalize_origin("https://Example.COM/dashboard/") == (
        "https://example.com/dashboard"
    )
    assert normalize_origin("https://example.com/") == "https://example.com"


def test_production_wildcard_error_names_opt_in_flag() -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        resolve_cors_settings(
            {"HEATGUARD_ENV": "production", "HEATGUARD_CORS_ORIGINS": "*"}
        )
    msg = str(excinfo.value)
    assert ENV_VAR_ORIGINS in msg
    assert ENV_VAR_ALLOW_WILDCARD in msg
    # Must not echo unrelated secrets / full env dumps.
    assert "SECRET" not in msg
