"""Unit tests for cache integrity helper."""
from __future__ import annotations

import json

from heatguard import cache_integrity as ci
from heatguard.canonical import dump


def test_compute_sha256_match(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"hourly":{"time":["2024-01-01T00:00"]}}')
    assert ci.compute_sha256(p) == ci.compute_sha256(p)


def test_verify_match(tmp_path):
    raw = {"hourly": {"time": ["2024-01-01T00:00", "2024-01-01T01:00"]}}
    f = tmp_path / "dubai_2025-05-01_2025-09-15.json"
    f.write_text(json.dumps(raw))
    digest = ci.compute_sha256(f)
    manifest = tmp_path / "CHECKSUMS.json"
    dump(
        {
            "version": 2,
            "files": {
                f.name: {
                    "sha256": digest,
                    "source": "archive",
                    "endpoint": "https://archive-api.open-meteo.com/v1/archive",
                    "fetched_at_utc": "2024-01-01T00:00:00Z",
                    "row_count": 2,
                    "bytes": f.stat().st_size,
                    "required": True,
                }
            },
        },
        manifest,
    )
    # Only verify this isolated dir — required demo set won't be present
    problems = ci.verify_cache_manifest(
        cache_dir=tmp_path, checksums_path=manifest, require_required=False
    )
    assert problems == []


def test_verify_mismatch(tmp_path):
    f = tmp_path / "x.json"
    f.write_text('{"hourly":{"time":["t"]}}')
    manifest = tmp_path / "CHECKSUMS.json"
    dump(
        {
            "version": 2,
            "files": {
                "x.json": {
                    "sha256": "0" * 64,
                    "source": "archive",
                    "endpoint": "https://example.com",
                    "fetched_at_utc": "2024-01-01T00:00:00Z",
                    "row_count": 1,
                    "bytes": f.stat().st_size,
                    "required": False,
                }
            },
        },
        manifest,
    )
    problems = ci.verify_cache_manifest(
        cache_dir=tmp_path, checksums_path=manifest, require_required=False
    )
    assert any(p.kind == "mismatch" for p in problems)


def test_verify_missing(tmp_path):
    manifest = tmp_path / "CHECKSUMS.json"
    dump(
        {
            "version": 2,
            "files": {
                "gone.json": {
                    "sha256": "a" * 64,
                    "source": "archive",
                    "endpoint": "https://example.com",
                    "fetched_at_utc": "2024-01-01T00:00:00Z",
                    "row_count": 0,
                    "bytes": 0,
                    "required": True,
                }
            },
        },
        manifest,
    )
    problems = ci.verify_cache_manifest(
        cache_dir=tmp_path, checksums_path=manifest, require_required=False
    )
    assert any(p.kind == "missing" and p.filename == "gone.json" for p in problems)


def test_verify_empty(tmp_path):
    f = tmp_path / "empty.json"
    f.write_bytes(b"")
    digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    manifest = tmp_path / "CHECKSUMS.json"
    dump(
        {
            "version": 2,
            "files": {
                "empty.json": {
                    "sha256": digest,
                    "source": "forecast",
                    "endpoint": "https://example.com",
                    "fetched_at_utc": "2024-01-01T00:00:00Z",
                    "row_count": 0,
                    "bytes": 0,
                    "required": False,
                }
            },
        },
        manifest,
    )
    problems = ci.verify_cache_manifest(
        cache_dir=tmp_path, checksums_path=manifest, require_required=False
    )
    assert any(p.kind == "empty" for p in problems)
