"""Resolve the repo-level ``data/`` directory regardless of working directory.

For an editable install (``pip install -e .``) ``__file__`` lives at
``<repo>/src/heatguard/_paths.py`` so the repo root is ``parents[2]``. An explicit
``HEATGUARD_DATA_DIR`` env var overrides everything (useful for packaged deploys).

``HEATGUARD_CACHE_DIR`` independently redirects the weather cache (default:
``DATA_DIR/cache``) so a read-only root filesystem can mount a writable tmpfs
without relocating the baked offline baseline under ``data/``.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("HEATGUARD_DATA_DIR", _REPO_ROOT / "data"))


def resolve_cache_dir(
    *,
    data_dir: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Resolve the weather cache directory.

    Precedence: ``HEATGUARD_CACHE_DIR`` when set, else ``<data_dir>/cache``.
    """
    environ = os.environ if env is None else env
    override = environ.get("HEATGUARD_CACHE_DIR")
    if override:
        return Path(override)
    base = DATA_DIR if data_dir is None else data_dir
    return base / "cache"


CACHE_DIR = resolve_cache_dir()


def data_file(name: str) -> Path:
    """Path to a file in ``data/`` (does not check existence)."""
    return DATA_DIR / name


def cache_file(name: str) -> Path:
    return CACHE_DIR / name


def ensure_cache_writable(cache_dir: Path | None = None) -> Path:
    """Create ``cache_dir`` (or ``CACHE_DIR``) and verify it is writable.

    Raises ``RuntimeError`` with an actionable message naming
    ``HEATGUARD_CACHE_DIR`` when the target cannot be written (e.g. read-only
    root without a tmpfs mount).
    """
    path = cache_dir if cache_dir is not None else CACHE_DIR
    try:
        path.mkdir(parents=True, exist_ok=True)
        # Unique probe name avoids races when multiple processes check concurrently.
        fd, probe_path = tempfile.mkstemp(prefix=".heatguard_write_probe_", dir=path)
        os.close(fd)
        Path(probe_path).unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"HeatGuard cache directory is not writable: {path}. "
            "Set HEATGUARD_CACHE_DIR to a writable mount (for example a tmpfs) "
            "when running with a read-only root filesystem."
        ) from exc
    return path
