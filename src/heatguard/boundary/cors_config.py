"""Environment-scoped CORS allowlist resolution (pure, FastAPI-free).

Lawful browser callers get an exact-origin echo; production wildcards fail
closed unless ``HEATGUARD_CORS_ALLOW_WILDCARD=true`` is set deliberately.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

# Documented Vite dev origins (localhost + loopback bind).
DEV_DEFAULT_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

CORS_METHODS: tuple[str, ...] = ("GET", "POST", "OPTIONS")
CORS_HEADERS: tuple[str, ...] = (
    "Content-Type",
    "Authorization",
    "X-API-Key",
    "X-Request-Id",
)

_HARD_ENVS = frozenset({"staging", "production", "prod"})

ENV_VAR_ORIGINS = "HEATGUARD_CORS_ORIGINS"
ENV_VAR_ALLOW_WILDCARD = "HEATGUARD_CORS_ALLOW_WILDCARD"
ENV_VAR_HEATGUARD_ENV = "HEATGUARD_ENV"


class ConfigurationError(ValueError):
    """Boot-time configuration fault — safe to surface; never embeds secret values."""


@dataclass(frozen=True)
class CorsSettings:
    """Resolved CORS policy for Starlette ``CORSMiddleware``."""

    origins: tuple[str, ...]
    methods: tuple[str, ...]
    headers: tuple[str, ...]
    allow_credentials: bool
    heatguard_env: str
    wildcard_requested: bool


def normalize_origin(raw: str) -> str:
    """Strip whitespace/trailing slash; lowercase scheme and host for exact match."""
    text = raw.strip()
    if not text:
        return ""
    if text == "*":
        return "*"
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text.rstrip("/")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = "" if parsed.path in ("", "/") else parsed.path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", "", ""))


def _parse_origin_list(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    parts = [normalize_origin(p) for p in raw.split(",")]
    cleaned = [p for p in parts if p]
    seen: set[str] = set()
    out: list[str] = []
    for origin in cleaned:
        if origin in seen:
            continue
        seen.add(origin)
        out.append(origin)
    return tuple(out)


def _canonical_env_name(raw: str | None) -> str:
    name = (raw or "").strip().lower()
    if name == "prod":
        return "production"
    return name


def _is_hard_env(env_name: str) -> bool:
    return env_name in _HARD_ENVS


def resolve_cors_settings(env: Mapping[str, str] | None = None) -> CorsSettings:
    """Resolve CORS settings from an environment mapping (defaults to safe local)."""
    source: Mapping[str, str] = env if env is not None else {}
    env_name = _canonical_env_name(source.get(ENV_VAR_HEATGUARD_ENV))
    hard = _is_hard_env(env_name)

    raw_origins = source.get(ENV_VAR_ORIGINS)
    # Missing or whitespace/comma-only → unconfigured (never allow-anything).
    parsed = _parse_origin_list(raw_origins)
    wildcard_in_list = any(o == "*" for o in parsed)
    explicit_origins = tuple(o for o in parsed if o != "*")
    allow_wildcard = (source.get(ENV_VAR_ALLOW_WILDCARD) or "").strip().lower() == "true"

    if wildcard_in_list:
        if hard and not allow_wildcard:
            raise ConfigurationError(
                f"Refusing wildcard CORS in {env_name or 'production'}: "
                f"{ENV_VAR_ORIGINS} contains '*' but {ENV_VAR_ALLOW_WILDCARD} is not "
                f"set to the literal 'true'. Set an explicit origin allowlist, or set "
                f"{ENV_VAR_ALLOW_WILDCARD}=true only for a deliberate temporary exception."
            )
        if allow_wildcard:
            origins: tuple[str, ...] = ("*",)
            wildcard_requested = True
        else:
            # Soft env + bare '*' without opt-in → safe local defaults (never ship '*').
            origins = DEV_DEFAULT_ORIGINS
            wildcard_requested = False
    elif not parsed:
        if hard:
            raise ConfigurationError(
                f"Refusing empty CORS allowlist in {env_name}: set {ENV_VAR_ORIGINS} "
                f"to an explicit comma-separated origin list (no wildcards)."
            )
        origins = DEV_DEFAULT_ORIGINS
        wildcard_requested = False
    else:
        origins = explicit_origins
        wildcard_requested = False

    return CorsSettings(
        origins=origins,
        methods=CORS_METHODS,
        headers=CORS_HEADERS,
        allow_credentials=False,
        heatguard_env=env_name or "dev",
        wildcard_requested=wildcard_requested,
    )
