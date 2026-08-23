from __future__ import annotations

import hashlib
import json
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Boot-time HMAC store: empty/unset digests fail FastAPI lifespan. Tests use
# the committed synthetic fixture (no production secrets).
_API_KEY_FIXTURE = Path(__file__).parent / "fixtures" / "api_key_digests.json"
if _API_KEY_FIXTURE.exists():
    _api_key_payload = json.loads(_API_KEY_FIXTURE.read_text(encoding="utf-8"))
    os.environ.setdefault("HEATGUARD_API_KEY_PEPPER", _api_key_payload["pepper"])
    os.environ.setdefault(
        "HEATGUARD_API_KEY_DIGESTS",
        json.dumps(_api_key_payload["bundle"], separators=(",", ":")),
    )

from heatguard import canonical, golden
from heatguard._paths import _REPO_ROOT
from heatguard.types import Site, Weather, Worker

TZ3 = timezone(timedelta(hours=3))
TZ4 = timezone(timedelta(hours=4))
GOLDEN_DIR = _REPO_ROOT / "tests" / "golden"


@pytest.fixture(autouse=True)
def _block_outbound_network(request, monkeypatch):
    """Fail loudly if any test attempts an outbound socket connect.

    Opt out with ``@pytest.mark.network`` (suite default skips those via
    ``addopts = -m 'not network'``).
    """
    if request.node.get_closest_marker("network"):
        yield
        return

    def _blocked_connect(self, address):  # noqa: ANN001
        host = address[0] if isinstance(address, tuple) else address
        raise RuntimeError(
            f"Outbound network blocked in tests (host={host!r}, "
            f"test={request.node.nodeid}). Use committed caches or "
            "@pytest.mark.network if live access is intentional."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)

    import httpx

    def _blocked_httpx(*_a, **_k):
        raise RuntimeError(
            f"httpx network blocked in tests (test={request.node.nodeid}). "
            "Use committed caches under data/cache/."
        )

    monkeypatch.setattr(httpx, "get", _blocked_httpx)
    monkeypatch.setattr(httpx, "request", _blocked_httpx)
    # Do not patch httpx.Client — Starlette TestClient uses ASGI transport via Client.
    yield


@pytest.fixture
def riyadh() -> Site:
    return Site("Riyadh", 24.7136, 46.6753, 612, "Asia/Riyadh", "SA")


@pytest.fixture
def dubai() -> Site:
    return Site("Dubai", 25.2048, 55.2708, 5, "Asia/Dubai", "AE")


def weather(hour, tdb, rh, wind=2.0, sw=0.0, direct=0.0, *, day=15, month=7, year=2024, tz=TZ3):
    return Weather(
        timestamp=datetime(year, month, day, hour, 0, tzinfo=tz),
        tdb_c=tdb, rh_pct=rh, wind_ms=wind,
        shortwave_wm2=sw, direct_wm2=direct, dew_point_c=tdb - 15, pressure_hpa=1004.0,
    )


@pytest.fixture
def veteran() -> Worker:
    return Worker("vet-1", days_on_job=120, acclimatized=True)


@pytest.fixture
def newcomer() -> Worker:
    return Worker("new-1", days_on_job=0, acclimatized=False)


def golden_bytes(site_key: str, artifact: str) -> bytes:
    path = GOLDEN_DIR / site_key / artifact
    if not path.exists():
        raise FileNotFoundError(f"Missing golden artifact: {path}")
    return path.read_bytes()


def assert_golden(obj, site_key: str, artifact: str) -> None:
    """Canonicalize *obj* and byte-compare to ``tests/golden/<site>/<artifact>``."""
    actual = canonical.dumps(obj) + "\n"
    expected = golden_bytes(site_key, artifact).decode("utf-8")
    if actual != expected:
        a_lines = actual.splitlines()
        e_lines = expected.splitlines()
        excerpt = []
        for i, (al, el) in enumerate(zip(a_lines, e_lines)):
            if al != el:
                excerpt.append(f"line {i}: expected={el[:120]!r} actual={al[:120]!r}")
            if len(excerpt) >= 5:
                break
        if len(a_lines) != len(e_lines):
            excerpt.append(f"length {len(e_lines)} vs {len(a_lines)}")
        raise AssertionError(
            f"Golden mismatch {site_key}/{artifact}:\n" + "\n".join(excerpt)
        )


def golden_tree_fingerprint() -> str:
    """SHA-256 over every file under tests/golden (sorted paths)."""
    h = hashlib.sha256()
    root = GOLDEN_DIR
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()
