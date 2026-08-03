"""ASGI middleware: correlation id + single http.request access event + SLI metrics."""
from __future__ import annotations

import re
import time
from typing import Any

from . import logging as obs_logging
from . import metrics as obs_metrics
from .events import HTTP_REQUEST

_SITE_PATH_RE = re.compile(
    r"^/(?:demo|forecast|compliance|hour|timeline|impact|economics|sensitivity|scale)/"
    r"(?P<site>[^/]+)"
)

# Known public routes — anything else becomes label ``unmatched`` (cardinality guard).
_KNOWN_EXACT = frozenset({
    "/",
    "/health",
    "/health/live",
    "/health/ready",
    "/sites",
    "/demos",
    "/backtest",
    "/datasets",
    "/policy/corpus",
    "/policy/demo-questions",
    "/policy/query",
    "/decide",
    "/metrics",
    "/dashboard",
    "/landing",
})

_SITE_PREFIXES = (
    "/demo/",
    "/forecast/",
    "/compliance/",
    "/hour/",
    "/timeline/",
    "/impact/",
    "/economics/",
    "/sensitivity/",
    "/scale/",
)


def _route_template(path: str) -> str:
    """Collapse path-bound site keys; unknown paths become ``unmatched``."""
    normalized = path.rstrip("/") or "/"
    if normalized in _KNOWN_EXACT or path in _KNOWN_EXACT:
        return normalized if normalized != "/health" else "/health"

    # /timeline/{site}/{day}, /hour/{site}/{day}/{hour}, /compliance/{site}/export
    if path.startswith("/timeline/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 3:
            return "/timeline/{site_key}/{day}"
        return "unmatched"
    if path.startswith("/hour/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 4:
            return "/hour/{site_key}/{day}/{hour}"
        return "unmatched"
    if path.startswith("/compliance/") and path.endswith("/export"):
        return "/compliance/{site_key}/export"
    for prefix in (
        "/demo/",
        "/forecast/",
        "/impact/",
        "/economics/",
        "/sensitivity/",
        "/scale/",
    ):
        if path.startswith(prefix):
            rest = path[len(prefix) :]
            site, _, tail = rest.partition("/")
            if site and not tail:
                return f"{prefix.rstrip('/')}/{{site_key}}"
            if site:
                return "unmatched"
    if path.startswith("/landing"):
        return "/landing"
    if path.startswith("/dashboard"):
        return "/dashboard"
    return "unmatched"


def _site_key_from_path(path: str) -> str | None:
    m = _SITE_PATH_RE.match(path)
    return m.group("site") if m else None


class CorrelationMiddleware:
    """Outermost ASGI middleware: request id binding + http.request event + metrics."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin1"): v.decode("latin1") for k, v in scope.get("headers", [])}
        request_id = obs_logging.resolve_request_id(headers)
        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        route = _route_template(path)
        site_key = _site_key_from_path(path)
        obs_logging.bind_request_context(
            request_id=request_id,
            **{"http.method": method, "http.route": route, "site_key": site_key},
        )

        status_code = 500
        response_bytes = 0
        content_encoding: str | None = None
        # Response-side cache hint only (never trust a client-supplied value).
        cache_status = "miss"
        started = time.perf_counter()

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code, response_bytes, cache_status, content_encoding
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
                raw_headers = [
                    (hk, hv)
                    for hk, hv in (message.get("headers") or [])
                    if hk.lower() != b"x-request-id"
                ]
                raw_headers.append((b"x-request-id", request_id.encode("ascii")))
                for hk, hv in raw_headers:
                    lower = hk.lower()
                    if lower == b"x-cache-status":
                        cache_status = hv.decode("latin1")
                    elif lower == b"content-encoding":
                        content_encoding = hv.decode("latin1")
                message = {**message, "headers": raw_headers}
            elif message["type"] == "http.response.body":
                body = message.get("body") or b""
                response_bytes += len(body)
            await send(message)

        log = obs_logging.get_logger("heatguard.http")
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_s = time.perf_counter() - started
            duration_ms = round(duration_s * 1000.0, 3)
            log.info(
                HTTP_REQUEST,
                request_id=request_id,
                method=method,
                route=route,
                status_code=status_code,
                duration_ms=duration_ms,
                response_bytes=response_bytes,
                cache_status=cache_status,
                site_key=site_key,
            )
            obs_metrics.observe_http_request(
                route=route,
                method=method,
                status_code=status_code,
                duration_seconds=duration_s,
                response_bytes=response_bytes,
                content_encoding=content_encoding,
            )
            obs_logging.clear_request_context()
