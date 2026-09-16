"""Identity object fetch behind a Protocol (WO-019).

Tests inject ``LocalFileFetcher`` or ``MemoryFetcher``. Production uses
``GcsFetcher`` against the JSON API with a metadata-server access token so
the identity package does not take a GCS SDK dependency (types-layer leaf).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.parse import quote, urlparse

ENV_IDENTITY_OBJECT_URI = "HEATGUARD_IDENTITY_OBJECT_URI"
ENV_IDENTITY_FETCH_TIMEOUT = "HEATGUARD_IDENTITY_FETCH_TIMEOUT_SECONDS"
DEFAULT_FETCH_TIMEOUT_SECONDS = 30.0
_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)
_GCS_OBJECT_URL = "https://storage.googleapis.com/storage/v1/b/{bucket}/o/{object_name}"


class IdentityLoadError(Exception):
    """Typed load failure with a stable ``reason`` code (never includes secrets)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True, slots=True)
class FetchedObject:
    payload: bytes
    generation: str


class IdentityFetcher(Protocol):
    def fetch(self) -> FetchedObject:
        """Return object bytes and an opaque generation string."""


@dataclass(frozen=True, slots=True)
class MemoryFetcher:
    """In-memory fetcher for unit tests (no filesystem, no network)."""

    payload: bytes
    generation: str = "memory"

    def fetch(self) -> FetchedObject:
        return FetchedObject(self.payload, self.generation)


class LocalFileFetcher:
    """Read a local SQLite snapshot. Used by tests and ``file://`` URIs."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def fetch(self) -> FetchedObject:
        try:
            payload = self.path.read_bytes()
        except FileNotFoundError as exc:
            raise IdentityLoadError("missing_object", "identity object is missing") from exc
        except PermissionError as exc:
            raise IdentityLoadError(
                "permission_denied", "identity object is not readable"
            ) from exc
        except OSError as exc:
            raise IdentityLoadError("corrupt", "identity object could not be read") from exc
        generation = str(self.path.stat().st_mtime_ns)
        return FetchedObject(payload, generation)


class GcsFetcher:
    """Download ``gs://bucket/object`` using the Cloud Storage JSON API."""

    def __init__(
        self,
        uri: str,
        *,
        timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
        token_provider: Callable[[], str] | None = None,
        request: Callable[..., object] | None = None,
    ) -> None:
        self.uri = uri
        self.timeout_seconds = timeout_seconds
        self._token_provider = token_provider
        self._request = request
        self.bucket, self.object_name = parse_gs_uri(uri)

    def fetch(self) -> FetchedObject:
        import httpx

        token = (self._token_provider or _metadata_access_token)()
        encoded = quote(self.object_name, safe="")
        url = _GCS_OBJECT_URL.format(bucket=self.bucket, object_name=encoded)
        headers = {"Authorization": f"Bearer {token}"}
        request = self._request or httpx.request
        try:
            meta = request(
                "GET",
                url,
                headers=headers,
                params={"fields": "generation,size"},
                timeout=self.timeout_seconds,
            )
            _raise_for_gcs_status(meta)
            generation = str(getattr(meta, "json")().get("generation", ""))
            media = request(
                "GET",
                url,
                headers=headers,
                params={"alt": "media"},
                timeout=self.timeout_seconds,
            )
            _raise_for_gcs_status(media)
        except IdentityLoadError:
            raise
        except httpx.TimeoutException as exc:
            raise IdentityLoadError("timeout", "identity object fetch timed out") from exc
        except TimeoutError as exc:
            raise IdentityLoadError("timeout", "identity object fetch timed out") from exc
        except OSError as exc:
            raise IdentityLoadError("timeout", "identity object fetch failed") from exc
        payload = getattr(media, "content", b"")
        if not isinstance(payload, (bytes, bytearray)):
            payload = bytes(payload)
        if not generation:
            generation = "unknown"
        return FetchedObject(bytes(payload), generation)


def parse_gs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise IdentityLoadError("invalid_uri", "identity object URI must use gs://")
    rest = uri[5:]
    bucket, sep, object_name = rest.partition("/")
    if not sep or not bucket or not object_name:
        raise IdentityLoadError("invalid_uri", "gs:// URI must be gs://bucket/object")
    return bucket, object_name


def _metadata_access_token() -> str:
    import httpx

    try:
        response = httpx.get(
            _METADATA_TOKEN_URL,
            headers={"Metadata-Flavor": "Google"},
            timeout=DEFAULT_FETCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
    except httpx.TimeoutException as exc:
        raise IdentityLoadError("timeout", "identity object fetch timed out") from exc
    except Exception as exc:  # noqa: BLE001 — map every ADC failure to a reason code
        raise IdentityLoadError(
            "permission_denied", "identity object is not readable"
        ) from exc
    if not isinstance(token, str) or not token:
        raise IdentityLoadError("permission_denied", "identity object is not readable")
    return token


def _raise_for_gcs_status(response: object) -> None:
    status = int(getattr(response, "status_code", 0))
    if 200 <= status < 300:
        return
    if status in {401, 403}:
        raise IdentityLoadError("permission_denied", "identity object is not readable")
    if status == 404:
        raise IdentityLoadError("missing_object", "identity object is missing")
    raise IdentityLoadError("corrupt", "identity object fetch failed")


def fetch_timeout_seconds(env: Mapping[str, str] | None = None) -> float:
    environ = os.environ if env is None else env
    raw = environ.get(ENV_IDENTITY_FETCH_TIMEOUT, str(DEFAULT_FETCH_TIMEOUT_SECONDS))
    try:
        return max(0.1, float(raw))
    except ValueError:
        return DEFAULT_FETCH_TIMEOUT_SECONDS


def fetcher_from_env(env: Mapping[str, str] | None = None) -> IdentityFetcher:
    """Select GCS vs local-file fetcher from ``HEATGUARD_IDENTITY_OBJECT_URI``."""
    environ = os.environ if env is None else env
    uri = (environ.get(ENV_IDENTITY_OBJECT_URI) or "").strip()
    if not uri:
        raise IdentityLoadError(
            "missing_uri",
            "HEATGUARD_IDENTITY_OBJECT_URI is required for identity boot",
        )
    timeout = fetch_timeout_seconds(environ)
    parsed = urlparse(uri)
    if parsed.scheme == "gs":
        return GcsFetcher(uri, timeout_seconds=timeout)
    if parsed.scheme == "file":
        return LocalFileFetcher(Path(parsed.path))
    if parsed.scheme == "":
        return LocalFileFetcher(Path(uri))
    raise IdentityLoadError("invalid_uri", "identity object URI scheme is not supported")
