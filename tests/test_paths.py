"""Unit tests for HEATGUARD_CACHE_DIR resolution (WO-010)."""
from __future__ import annotations

from pathlib import Path

import pytest

from heatguard._paths import ensure_cache_writable, resolve_cache_dir


def test_resolve_cache_dir_defaults_to_data_cache(tmp_path: Path) -> None:
    assert resolve_cache_dir(data_dir=tmp_path, env={}) == tmp_path / "cache"


def test_resolve_cache_dir_explicit_env_wins(tmp_path: Path) -> None:
    override = tmp_path / "redirected"
    got = resolve_cache_dir(
        data_dir=tmp_path / "data",
        env={"HEATGUARD_CACHE_DIR": str(override)},
    )
    assert got == override


def test_ensure_cache_writable_creates_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "cache"
    assert ensure_cache_writable(target) == target
    assert target.is_dir()


def test_ensure_cache_writable_nonwritable_raises(tmp_path: Path) -> None:
    """Non-writable target produces a clear HEATGUARD_CACHE_DIR error."""
    blocked = tmp_path / "ro"
    blocked.mkdir()
    blocked.chmod(0o555)
    try:
        with pytest.raises(RuntimeError, match="HEATGUARD_CACHE_DIR") as exc:
            ensure_cache_writable(blocked)
        assert str(blocked) in str(exc.value)
    finally:
        blocked.chmod(0o755)


def test_redirected_cache_fixture_is_hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Temporary redirected cache must not touch repository data/cache."""
    redirected = tmp_path / "isolated-cache"
    monkeypatch.setenv("HEATGUARD_CACHE_DIR", str(redirected))
    # Re-resolve via helper (module CACHE_DIR is import-time); fixture path is hermetic.
    path = resolve_cache_dir(env={"HEATGUARD_CACHE_DIR": str(redirected)})
    ensure_cache_writable(path)
    marker = path / "probe.json"
    marker.write_text("{}", encoding="utf-8")
    assert marker.exists()
    assert redirected in marker.parents or marker.parent == redirected
