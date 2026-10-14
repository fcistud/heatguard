#!/usr/bin/env python3
"""Build synthetic invalid identity databases for the WO-020 drill.

Never upload the generated files. Hashes and salts are dummy strings.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
SQL_FILES = (
    "forbidden_column.sql",
    "volatile_column.sql",
    "altered_role_check.sql",
    "supervisor_wildcard.sql",
    "schema_version_mismatch.sql",
    "multi_violation.sql",
)


def materialize_sql(sql_path: Path, dest: Path) -> Path:
    """Create a SQLite file from a committed invalid-schema SQL script."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    conn = sqlite3.connect(dest)
    try:
        conn.executescript(sql_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    return dest


def pad_to_size(src: Path, dest: Path, size: int) -> Path:
    """Copy *src* and pad with NULs so the object is exactly *size* bytes."""
    data = src.read_bytes()
    if len(data) > size:
        raise ValueError(f"{src} is already {len(data)} bytes (need <= {size})")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data + b"\0" * (size - len(data)))
    return dest


def write_invalid_set(dest_dir: Path, *, ceiling_bytes: int) -> dict[str, Path]:
    """Materialize every SQL fixture plus an over-ceiling object."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name in SQL_FILES:
        written[name] = materialize_sql(HERE / name, dest_dir / name.replace(".sql", ".db"))
    source = written["supervisor_wildcard.sql"]
    written["over_ceiling.db"] = pad_to_size(
        source, dest_dir / "over_ceiling.db", ceiling_bytes + 1
    )
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        default=str(Path("/tmp") / "identity-invalid"),
        help="Directory for generated .db files (default: /tmp/identity-invalid)",
    )
    parser.add_argument(
        "--ceiling-bytes",
        type=int,
        default=8 * 1024 * 1024,
        help="Identity size ceiling used for the over-ceiling object",
    )
    args = parser.parse_args(argv)
    written = write_invalid_set(Path(args.dest), ceiling_bytes=args.ceiling_bytes)
    for name, path in written.items():
        print(f"{name}: {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
