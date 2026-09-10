"""Golden-master capture for HeatGuard demo sites.

Produces byte-identical reference artifacts under ``tests/golden/<site>/`` from
committed Open-Meteo caches only (networking disabled). See ``docs/TESTING.md``.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterator

from . import canonical
from ._paths import CACHE_DIR, _REPO_ROOT
from .datasets import load_manifest
from .service import (
    DEMOS,
    build_demo,
    business_case,
    compliance_for_day,
    forecast_timeline,
    impact_sensitivity,
    season_impact,
    timeline_for_day,
)
from .weather import openmeteo

GOLDEN_DIR = _REPO_ROOT / "tests" / "golden"
CHECKSUMS_PATH = CACHE_DIR / "CHECKSUMS.json"
DEFAULT_CREW = 100

ARTIFACT_NAMES = (
    "hourly.json",
    "focus_day.json",
    "forecast.json",
    "impact_economics_sensitivity.json",
    "compliance_chain.json",
    "MANIFEST.json",
)


class NetworkDisabledError(RuntimeError):
    """Raised when golden capture would hit the network."""


@contextmanager
def networking_disabled() -> Iterator[None]:
    """Block httpx network calls so capture can only use committed caches."""

    def _blocked(*_a: Any, **_k: Any) -> Any:
        raise NetworkDisabledError(
            "Golden capture must use committed caches only — network is disabled."
        )

    import httpx

    original_get = httpx.get
    original_request = httpx.request
    client_get = httpx.Client.get
    httpx.get = _blocked  # type: ignore[assignment]
    httpx.request = _blocked  # type: ignore[assignment]
    httpx.Client.get = _blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        httpx.get = original_get  # type: ignore[assignment]
        httpx.request = original_request  # type: ignore[assignment]
        httpx.Client.get = client_get  # type: ignore[method-assign]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_cache_checksums(path: Path = CHECKSUMS_PATH) -> dict[str, str]:
    """SHA-256 every ``*.json`` under ``data/cache/`` except CHECKSUMS itself.

    Writes the v2 enriched manifest via ``cache_integrity`` and returns the
    flat ``{filename: sha256}`` map used by golden capture.
    """
    from . import cache_integrity

    entries = cache_integrity.write_checksums_manifest(path=path)
    return {name: e.sha256 for name, e in entries.items()}


def load_cache_checksums(path: Path = CHECKSUMS_PATH) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run write_cache_checksums() or heatguard golden capture first."
        )
    from . import cache_integrity

    return cache_integrity.sha256_map(cache_integrity.load_checksum_entries(path))


def verify_input_caches(site_key: str, checksums: dict[str, str]) -> dict[str, str]:
    """Return the subset of checksums consumed by *site_key*; abort if missing/mismatched."""
    cfg = DEMOS[site_key]
    from .sites import get_site

    site = get_site(cfg["site"])
    archive_name = openmeteo.cache_name_for(site, cfg["season_start"], cfg["season_end"])
    fc_cfg = load_manifest()["weather"]["forecast"]
    forecast_name = openmeteo.forecast_cache_name_for(
        site, int(fc_cfg["forecast_days"]), int(fc_cfg["past_days"])
    )
    needed = [archive_name, forecast_name]
    used: dict[str, str] = {}
    for name in needed:
        path = CACHE_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"Required cache missing for {site_key}: {path}")
        digest = sha256_file(path)
        expected = checksums.get(name)
        if expected is None:
            raise KeyError(f"{name} not listed in CHECKSUMS.json")
        if digest != expected:
            raise ValueError(
                f"Cache checksum mismatch for {name}: got {digest}, expected {expected}"
            )
        used[name] = digest
    return used


def _pkg_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _git_commit() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=_REPO_ROOT,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.environ.get("GIT_COMMIT", "unknown")


def _advisory_surface(adv: dict) -> dict:
    """Project an Advisory.to_dict() payload to the golden-master field set."""
    cycle = adv.get("cycle", {})
    hyd = adv.get("hydration", {})
    return {
        "signal": adv.get("signal"),
        "work_min_per_hour": cycle.get("work_min_per_hour"),
        "rest_min_per_hour": cycle.get("rest_min_per_hour"),
        "cups_250ml_per_h": hyd.get("cups_250ml_per_h"),
        "water_ml_per_h": hyd.get("water_ml_per_h"),
        "max_exposure_min": hyd.get("max_exposure_min"),
        "phs_valid": hyd.get("phs_valid"),
        "rationale": adv.get("rationale"),
        "wbgt_c": adv.get("wbgt_c"),
        "wbgt_source": adv.get("wbgt_source"),
        "timestamp": adv.get("timestamp"),
        "worker_id": adv.get("worker_id"),
        "cycle": cycle,
        "hydration": hyd,
        "acclim_fraction": adv.get("acclim_fraction"),
        "risk_score": adv.get("risk_score"),
        "personal_risk_score": adv.get("personal_risk_score"),
        "elevated_risk": adv.get("elevated_risk"),
        "personal_risk_note": adv.get("personal_risk_note"),
    }


def _hourly_from_timeline(tl: dict) -> list[dict]:
    rows = []
    for r in tl["rows"]:
        rows.append(
            {
                "hour": r["hour"],
                "time": r["time"],
                "tdb_c": r["tdb_c"],
                "rh_pct": r["rh_pct"],
                "wbgt_c": r["wbgt_c"],
                "wbgt_source": r["wbgt_source"],
                "banned": r["banned"],
                "gap": r["gap"],
                "veteran": _advisory_surface(r["veteran"]),
                "newcomer": _advisory_surface(r["newcomer"]),
            }
        )
    return rows


def capture_site(
    site_key: str,
    out_dir: Path,
    checksums: dict[str, str],
    crew: int = DEFAULT_CREW,
) -> dict[str, bytes]:
    """Capture one demo site into *out_dir*; return mapping of filename → bytes written."""
    if site_key not in DEMOS:
        raise KeyError(f"Unknown demo site '{site_key}'")

    used_caches = verify_input_caches(site_key, checksums)
    cfg = DEMOS[site_key]
    focus = cfg["focus_day"]

    with networking_disabled():
        tl = timeline_for_day(site_key, focus)
        forecast = forecast_timeline(site_key)
        impact = season_impact(site_key, crew)
        econ = business_case(site_key, crew)
        sens = impact_sensitivity(site_key, crew)
        # build_demo also exercises the full assembly path (offline)
        demo = build_demo(site_key, crew)
        log = compliance_for_day(site_key, focus)

    if not log.verify_chain():
        raise RuntimeError(
            f"Compliance chain failed verify_chain() for {site_key} — aborting capture"
        )

    hourly = {
        "site_key": site_key,
        "date": str(focus),
        "rows": _hourly_from_timeline(tl),
    }
    focus_day = {
        "site_key": site_key,
        "timeline": tl,
        "demo_headline": demo["headline"],
        "demo_focus_day": demo["focus_day"],
        "demo_intensity": demo["intensity"],
    }
    impact_bundle = {
        "site_key": site_key,
        "crew": crew,
        "impact": impact,
        "economics": econ,
        "sensitivity": sens,
    }
    compliance = {
        "site_key": site_key,
        "site_name": log.site_name,
        "genesis": "0" * 64,
        "verified": True,
        "head_hash": log.head_hash,
        "summary": log.summary(),
        "records": [asdict(r) for r in log.records],
    }
    manifest = {
        "site_key": site_key,
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "git_commit": _git_commit(),
        "packages": {
            "numpy": _pkg_version("numpy"),
            "pythermalcomfort": _pkg_version("pythermalcomfort"),
            "thermofeel": _pkg_version("thermofeel"),
            "scikit-learn": _pkg_version("scikit-learn"),
        },
        "input_cache_sha256": used_caches,
        "compliance_chain_verified": True,
        "crew": crew,
        "focus_day": str(focus),
        "artifacts": list(ARTIFACT_NAMES),
    }

    site_dir = out_dir / site_key
    written: dict[str, bytes] = {}
    written["hourly.json"] = canonical.dump(hourly, site_dir / "hourly.json")
    written["focus_day.json"] = canonical.dump(focus_day, site_dir / "focus_day.json")
    written["forecast.json"] = canonical.dump(
        {"site_key": site_key, "forecast": forecast}, site_dir / "forecast.json"
    )
    written["impact_economics_sensitivity.json"] = canonical.dump(
        impact_bundle, site_dir / "impact_economics_sensitivity.json"
    )
    written["compliance_chain.json"] = canonical.dump(
        compliance, site_dir / "compliance_chain.json"
    )
    written["MANIFEST.json"] = canonical.dump(manifest, site_dir / "MANIFEST.json")
    return written


def demo_site_keys() -> list[str]:
    """Archive.demo keys from the manifest that are also registered in DEMOS."""
    keys = [row["site_key"] for row in load_manifest()["weather"]["archive"]["demo"]]
    return [k for k in keys if k in DEMOS]


def capture_all(
    out_dir: Path | None = None,
    sites: list[str] | None = None,
    crew: int = DEFAULT_CREW,
    refresh_checksums: bool = True,
) -> Path:
    """Capture all demo sites into *out_dir* (default ``tests/golden``)."""
    target = Path(out_dir) if out_dir is not None else GOLDEN_DIR
    target.mkdir(parents=True, exist_ok=True)
    if refresh_checksums:
        write_cache_checksums()
    checksums = load_cache_checksums()
    keys = sites or demo_site_keys()
    for key in keys:
        capture_site(key, target, checksums, crew=crew)
    return target


def file_tree_bytes(root: Path) -> dict[str, bytes]:
    """Map relative posix paths → file bytes for every file under *root*."""
    out: dict[str, bytes] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


# Host / VCS fields that must not fail parity (science + package pins are kept).
_MANIFEST_VOLATILE = frozenset({"git_commit", "platform", "python_implementation"})


def _python_majmin(version: str) -> str:
    """``3.12.14`` → ``3.12`` so CPython security patches do not fail golden."""
    parts = version.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}.{parts[1]}"
    return version


def _manifest_for_compare(raw: bytes) -> bytes:
    """Drop host/VCS fields so Linux CI can match goldens captured on macOS.

    ``python_version`` is compared at major.minor (same policy as
    ``scripts/ci_version_drift.py``) so ``3.12.13`` vs ``3.12.14`` is not a
    mismatch; ``3.11`` vs ``3.12`` still fails.
    """
    data = json.loads(raw.decode("utf-8"))
    for key in _MANIFEST_VOLATILE:
        data.pop(key, None)
    raw_py = data.get("python_version")
    if isinstance(raw_py, str):
        data["python_version"] = _python_majmin(raw_py)
    return canonical.dumps_bytes(data) + b"\n"


def compare_trees(expected: Path, actual: Path) -> list[str]:
    """Return a list of human-readable differences (empty ⇒ byte-identical)."""
    a = file_tree_bytes(expected)
    b = file_tree_bytes(actual)
    diffs: list[str] = []
    for key in sorted(set(a) | set(b)):
        if key not in a:
            diffs.append(f"+ only in actual: {key}")
        elif key not in b:
            diffs.append(f"- missing in actual: {key}")
        else:
            left, right = a[key], b[key]
            if key.endswith("MANIFEST.json") or key == "MANIFEST.json":
                left, right = _manifest_for_compare(left), _manifest_for_compare(right)
            if left != right:
                diffs.append(f"! bytes differ: {key} ({len(a[key])} vs {len(b[key])} bytes)")
    return diffs


def check_against_committed(
    committed: Path | None = None,
    sites: list[str] | None = None,
    crew: int = DEFAULT_CREW,
) -> list[str]:
    """Regenerate into a temp dir and byte-compare to the committed golden tree."""
    ref = Path(committed) if committed is not None else GOLDEN_DIR
    keys = sites or demo_site_keys()
    with tempfile.TemporaryDirectory(prefix="heatguard-golden-") as tmp:
        capture_all(Path(tmp), sites=keys, crew=crew, refresh_checksums=False)
        diffs: list[str] = []
        for key in keys:
            for d in compare_trees(ref / key, Path(tmp) / key):
                diffs.append(f"{key}: {d}")
        return diffs


def assert_capture_idempotent(sites: list[str] | None = None, crew: int = DEFAULT_CREW) -> None:
    """Two consecutive captures into separate temps must be byte-identical."""
    keys = sites or demo_site_keys()
    write_cache_checksums()
    with tempfile.TemporaryDirectory(prefix="hg-gold-a-") as a, tempfile.TemporaryDirectory(
        prefix="hg-gold-b-"
    ) as b:
        capture_all(Path(a), sites=keys, crew=crew, refresh_checksums=False)
        capture_all(Path(b), sites=keys, crew=crew, refresh_checksums=False)
        diffs = compare_trees(Path(a), Path(b))
        if diffs:
            raise AssertionError("Capture not idempotent:\n" + "\n".join(diffs))
