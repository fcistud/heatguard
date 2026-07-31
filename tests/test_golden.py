"""Tests for golden-master capture harness and regeneration parity."""
from __future__ import annotations

from pathlib import Path

import pytest

from heatguard import canonical, golden
from heatguard.canonical import dumps_bytes


@pytest.fixture(scope="module")
def checksums(tmp_path_factory):
    """Ensure CHECKSUMS.json exists for the committed cache tree."""
    golden.write_cache_checksums()
    return golden.load_cache_checksums()


def test_capture_idempotent_single_site(checksums, tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    golden.capture_site("dubai", a, checksums)
    golden.capture_site("dubai", b, checksums)
    diffs = golden.compare_trees(a / "dubai", b / "dubai")
    assert diffs == [], diffs


def test_networking_disabled_raises(monkeypatch):
    import httpx

    with golden.networking_disabled():
        with pytest.raises(golden.NetworkDisabledError):
            httpx.get("https://example.com")


def test_canonical_serializer_used_for_artifacts(checksums, tmp_path):
    golden.capture_site("dubai", tmp_path, checksums)
    raw = (tmp_path / "dubai" / "MANIFEST.json").read_bytes()
    # Trailing newline, no spaces after colons/commas inside (compact).
    assert raw.endswith(b"\n")
    body = raw[:-1]
    assert b": " not in body
    assert b", " not in body


def test_compliance_chain_verified_in_manifest(checksums, tmp_path):
    golden.capture_site("riyadh", tmp_path, checksums)
    manifest = canonical.load(tmp_path / "riyadh" / "MANIFEST.json")
    assert manifest["compliance_chain_verified"] is True
    chain = canonical.load(tmp_path / "riyadh" / "compliance_chain.json")
    assert chain["verified"] is True
    assert chain["records"]
    assert chain["records"][0]["prev_hash"] == "0" * 64
    assert all("record_hash" in r for r in chain["records"])


@pytest.mark.slow
def test_regenerate_matches_committed_golden_tree():
    """System integration: committed tests/golden must match a fresh capture."""
    if not golden.GOLDEN_DIR.exists() or not any(golden.GOLDEN_DIR.iterdir()):
        pytest.skip("tests/golden not captured yet — run heatguard golden capture")
    diffs = golden.check_against_committed()
    assert diffs == [], "\n".join(diffs)


def test_dumps_bytes_empty_input():
    assert dumps_bytes({}) == b"{}"
    assert dumps_bytes([]) == b"[]"
