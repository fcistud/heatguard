"""Cache fixture integrity — SHA-256 manifests and offline verification.

``data/cache/CHECKSUMS.json`` is the authoritative digest of every committed
Open-Meteo payload. Golden capture and the offline test suite both consume it.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ._paths import CACHE_DIR
from .canonical import dump, load
from .datasets import archive_specs, forecast_specs, load_manifest
from .weather import openmeteo

CHECKSUMS_PATH = CACHE_DIR / "CHECKSUMS.json"
SourceKind = Literal["archive", "forecast"]


@dataclass(frozen=True, slots=True)
class CacheEntry:
    sha256: str
    source: SourceKind
    endpoint: str
    fetched_at_utc: str
    row_count: int
    bytes: int
    required: bool


@dataclass(frozen=True, slots=True)
class CacheProblem:
    kind: str  # missing | mismatch | empty | unexpected | row_count
    filename: str
    detail: str

    def message(self) -> str:
        return f"{self.kind}: {self.filename} — {self.detail}"


def compute_sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_count(path: Path) -> int:
    payload = json.loads(path.read_text())
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    return len(times)


def _fetched_at(path: Path) -> str:
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _classify(name: str) -> tuple[SourceKind, str, bool]:
    """Return (source, endpoint, required) for a cache filename."""
    demo_keys = {r["site_key"] for r in load_manifest()["weather"]["archive"]["demo"]}
    gulf_keys = {r["site_key"] for r in load_manifest()["weather"]["archive"]["gulf_season"]}
    fc_sites = set(load_manifest()["weather"]["forecast"]["sites"])

    for spec in archive_specs():
        if spec.cache_file == name:
            required = spec.site_key in demo_keys
            return "archive", openmeteo.ARCHIVE_URL, required
    for spec in forecast_specs():
        if spec.cache_file == name:
            return "forecast", openmeteo.FORECAST_URL, spec.site_key in fc_sites
    # Unknown filename — treat as optional forecast-looking or archive
    if "_forecast_" in name:
        return "forecast", openmeteo.FORECAST_URL, False
    return "archive", openmeteo.ARCHIVE_URL, name.split("_")[0] in demo_keys | gulf_keys


def build_cache_entries(cache_dir: Path = CACHE_DIR) -> dict[str, CacheEntry]:
    entries: dict[str, CacheEntry] = {}
    for path in sorted(cache_dir.glob("*.json")):
        if path.name == "CHECKSUMS.json":
            continue
        source, endpoint, required = _classify(path.name)
        size = path.stat().st_size
        if size == 0:
            raise ValueError(f"Empty cache file: {path}")
        entries[path.name] = CacheEntry(
            sha256=compute_sha256(path),
            source=source,
            endpoint=endpoint,
            fetched_at_utc=_fetched_at(path),
            row_count=_row_count(path),
            bytes=size,
            required=required,
        )
    return entries


def write_checksums_manifest(
    path: Path = CHECKSUMS_PATH,
    cache_dir: Path = CACHE_DIR,
) -> dict[str, CacheEntry]:
    entries = build_cache_entries(cache_dir)
    payload = {
        "version": 2,
        "files": {name: asdict(entry) for name, entry in entries.items()},
    }
    dump(payload, path)
    return entries


def load_checksum_entries(path: Path = CHECKSUMS_PATH) -> dict[str, CacheEntry]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run heatguard golden capture or "
            "heatguard.cache_integrity.write_checksums_manifest()."
        )
    data = load(path)
    files = data.get("files") or {}
    out: dict[str, CacheEntry] = {}
    for name, raw in files.items():
        if isinstance(raw, str):
            # v1 flat digest map — upgrade in memory with best-effort classify
            source, endpoint, required = _classify(name)
            file_path = CACHE_DIR / name
            out[name] = CacheEntry(
                sha256=raw,
                source=source,
                endpoint=endpoint,
                fetched_at_utc="unknown",
                row_count=_row_count(file_path) if file_path.exists() else 0,
                bytes=file_path.stat().st_size if file_path.exists() else 0,
                required=required,
            )
        else:
            out[name] = CacheEntry(
                sha256=raw["sha256"],
                source=raw["source"],
                endpoint=raw.get("endpoint", ""),
                fetched_at_utc=raw.get("fetched_at_utc", "unknown"),
                row_count=int(raw.get("row_count", 0)),
                bytes=int(raw.get("bytes", 0)),
                required=bool(raw.get("required", False)),
            )
    return out


def sha256_map(entries: dict[str, CacheEntry] | None = None) -> dict[str, str]:
    if entries is None:
        entries = load_checksum_entries()
    return {name: e.sha256 for name, e in entries.items()}


def required_cache_names() -> set[str]:
    """Demo archives + forecast sites — must be offline-complete."""
    demo_keys = {r["site_key"] for r in load_manifest()["weather"]["archive"]["demo"]}
    names: set[str] = set()
    for spec in archive_specs():
        if spec.site_key in demo_keys:
            names.add(spec.cache_file)
    for spec in forecast_specs():
        names.add(spec.cache_file)
    return names


def verify_cache_manifest(
    cache_dir: Path = CACHE_DIR,
    checksums_path: Path = CHECKSUMS_PATH,
    *,
    require_required: bool = True,
) -> list[CacheProblem]:
    """Return structured problems (empty ⇒ all good). Does not raise."""
    problems: list[CacheProblem] = []
    try:
        entries = load_checksum_entries(checksums_path)
    except FileNotFoundError as exc:
        return [CacheProblem("missing", "CHECKSUMS.json", str(exc))]

    on_disk = {
        p.name
        for p in cache_dir.glob("*.json")
        if p.name != "CHECKSUMS.json"
    }

    for name in sorted(entries):
        path = cache_dir / name
        entry = entries[name]
        if not path.exists():
            if entry.required or require_required and name in required_cache_names():
                problems.append(
                    CacheProblem("missing", name, f"expected SHA-256 {entry.sha256}")
                )
            continue
        size = path.stat().st_size
        if size == 0:
            problems.append(CacheProblem("empty", name, "zero-length file"))
            continue
        digest = compute_sha256(path)
        if digest != entry.sha256:
            problems.append(
                CacheProblem(
                    "mismatch",
                    name,
                    f"got {digest}, expected {entry.sha256} — "
                    "re-fetch with heatguard fetch-datasets then rewrite CHECKSUMS",
                )
            )
            continue
        rows = _row_count(path)
        if entry.row_count and rows != entry.row_count:
            problems.append(
                CacheProblem(
                    "row_count",
                    name,
                    f"parsed {rows} hourly rows, manifest says {entry.row_count}",
                )
            )

    if require_required:
        for name in sorted(required_cache_names()):
            if name not in entries:
                problems.append(
                    CacheProblem(
                        "missing",
                        name,
                        "required for offline replay but absent from CHECKSUMS.json",
                    )
                )
            elif name not in on_disk:
                problems.append(
                    CacheProblem("missing", name, "required cache file not on disk")
                )

    return problems


def assert_caches_ok() -> None:
    problems = verify_cache_manifest()
    if problems:
        raise RuntimeError(
            "Cache integrity failed:\n"
            + "\n".join(f"  - {p.message()}" for p in problems)
        )
