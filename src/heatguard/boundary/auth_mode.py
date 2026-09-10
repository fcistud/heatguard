"""Per-endpoint-group auth mode resolution (WO-005).

Pure in-memory lookup: no I/O on the request path. Invalid configuration
fails boot with a descriptive error naming the variable and permitted values.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from heatguard.boundary.cors_config import ConfigurationError
from heatguard.types import PrincipalContext

ENV_BASELINE = "HEATGUARD_AUTH_MODE"
ENV_GROUP_PREFIX = "HEATGUARD_AUTH_MODE_"
PERMITTED_MODES = ("dual", "enforce")

# Groups that appear in EnforcementMiddleware._ROUTE_SPEC (WO-002/006).
ROUTE_GROUPS: frozenset[str] = frozenset(
    {"probes", "metrics", "session", "advisory", "reference", "static"}
)
STRUCTURALLY_EXEMPT_GROUPS: frozenset[str] = frozenset({"probes", "metrics"})
ROLE_INSPECTOR = "inspector"

_SITE_PATH_RE = re.compile(
    r"^/(?:demo|forecast|compliance|hour|timeline|impact|economics|sensitivity|scale)/"
    r"(?P<site>[^/]+)"
)


class AuthMode(str, Enum):
    DUAL = "dual"
    ENFORCE = "enforce"


class AuthModeRef:
    """Mutable slot filled once at bind — request path only reads ``snapshot``."""

    __slots__ = ("snapshot",)

    def __init__(self) -> None:
        self.snapshot: AuthModeSnapshot | None = None


@dataclass(frozen=True, slots=True)
class AuthModeSnapshot:
    """Immutable per-group posture resolved at boot."""

    baseline: AuthMode
    overrides: tuple[tuple[str, AuthMode], ...]

    def mode_for(self, group: str) -> AuthMode:
        """Return the mode for ``group``.

        Unset and request-time ``unknown`` groups follow the service baseline
        (default dual). That is the most restrictive treatment available when
        only the baseline is configured — never unconditional admission.
        """
        for name, mode in self.overrides:
            if name == group:
                return mode
        return self.baseline


DEFAULT_SNAPSHOT = AuthModeSnapshot(baseline=AuthMode.DUAL, overrides=())


def _normalise_mode(raw: str, *, variable: str) -> AuthMode:
    value = raw.strip().lower()
    if value == AuthMode.DUAL.value:
        return AuthMode.DUAL
    if value == AuthMode.ENFORCE.value:
        return AuthMode.ENFORCE
    permitted = ", ".join(PERMITTED_MODES)
    raise ConfigurationError(
        f"{variable}={raw!r} is not a permitted auth mode; use one of: {permitted}."
    )


def resolve_auth_modes(env: Mapping[str, str] | None = None) -> AuthModeSnapshot:
    """Parse baseline + ``HEATGUARD_AUTH_MODE_<GROUP>`` overrides.

    Naming a group that is not in the route table, overriding probes/metrics,
    or supplying an invalid mode string fails boot.
    """
    source: Mapping[str, str] = env if env is not None else os.environ
    raw_baseline = source.get(ENV_BASELINE)
    if raw_baseline is None or not raw_baseline.strip():
        baseline = AuthMode.DUAL
    else:
        baseline = _normalise_mode(raw_baseline, variable=ENV_BASELINE)

    overrides: list[tuple[str, AuthMode]] = []
    seen: set[str] = set()
    for key, raw in source.items():
        if not key.startswith(ENV_GROUP_PREFIX) or key == ENV_BASELINE:
            continue
        suffix = key[len(ENV_GROUP_PREFIX) :]
        group = suffix.strip().lower()
        if group not in ROUTE_GROUPS:
            raise ConfigurationError(
                f"{key} names group {group!r} which is not in the route table "
                f"({', '.join(sorted(ROUTE_GROUPS))})."
            )
        if group in STRUCTURALLY_EXEMPT_GROUPS:
            raise ConfigurationError(
                f"{key} cannot override {group}; probes and metrics stay "
                "unauthenticated regardless of HEATGUARD_AUTH_MODE."
            )
        if group in seen:
            continue
        seen.add(group)
        overrides.append((group, _normalise_mode(raw, variable=key)))
    overrides.sort(key=lambda item: item[0])
    return AuthModeSnapshot(baseline=baseline, overrides=tuple(overrides))


def site_key_from_path(path: str) -> str | None:
    """First path segment after a site-scoped prefix, or None."""
    if not path:
        return None
    match = _SITE_PATH_RE.match(path.rstrip("/") or "/")
    return match.group("site") if match else None


def principal_permits_route(path: str, principal: PrincipalContext) -> bool:
    """Site-scope check. Wildcard ``*`` is inspector-only.

    Integrator API keys carry no roles/sites and are not site-bound (WO-031
    will attach the four-role table). Anonymous empty principals are denied
    when a site is present — callers should 401 before this check.
    """
    site = site_key_from_path(path)
    if site is None:
        return True
    if not principal.principal_id and not principal.roles and not principal.sites:
        return False
    if not principal.roles and not principal.sites:
        return True
    if "*" in principal.sites:
        return ROLE_INSPECTOR in principal.roles
    return site in principal.sites


def load_auth_modes(env: Mapping[str, str] | None = None) -> AuthModeSnapshot:
    """Bind-time wrapper so api.py matches load_key_store / load_session_auth."""
    return resolve_auth_modes(env)
