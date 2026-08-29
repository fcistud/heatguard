"""Live FastAPI route-table helpers for the WO-006 coverage gate.

Walks ``app.routes`` (including ``include_in_schema=False`` routers) and classifies
each method-path pair plus each static mount with the production classifier.
Does not reimplement classification and does not write the committed inventory.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from starlette.routing import Mount

from heatguard.boundary.enforcement import classify_request

# Bumping this number requires classifying the new route in
# ``src/heatguard/boundary/enforcement.py`` (``_ROUTE_SPEC``) and updating
# ``tests/fixtures/route_inventory.json`` in the same change — do not bump blindly.
NON_PROBE_ROUTE_COUNT = 29

EXEMPT_PATHS = (
    "/health",
    "/health/",
    "/health/live",
    "/health/ready",
    "/metrics",
)

KIND_ROUTE = "route"
KIND_MOUNT = "mount"


def _included_routes(route: Any) -> Sequence[Any] | None:
    """Expand FastAPI ``include_router`` wrappers (private ``/metrics``)."""
    original = getattr(route, "original_router", None)
    nested = getattr(original, "routes", None) if original is not None else None
    if nested:
        return nested
    return None


def iter_registered_routes(routes: Iterable[Any]) -> list[Any]:
    """Flatten included routers; leave Mount objects intact (do not walk StaticFiles)."""
    found: list[Any] = []
    for route in routes:
        nested = _included_routes(route)
        if nested is not None:
            found.extend(iter_registered_routes(nested))
            continue
        found.append(route)
    return found


def _mount_path(route: Mount) -> str:
    path = route.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return path


def collect_live_route_entries(app: Any) -> list[dict[str, Any]]:
    """Enumerate live method-path pairs and mounts; classify via production helper."""
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for route in iter_registered_routes(app.routes):
        if isinstance(route, Mount):
            path = _mount_path(route)
            classified = classify_request(path, "GET")
            entry = {
                "kind": KIND_MOUNT,
                "path": path,
                "method": "",
                "name": route.name or "",
                "group": classified.group,
                "exempt": classified.exempt,
            }
            key = entry_key(entry)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
            continue
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not isinstance(path, str) or not methods:
            continue
        for method in sorted(methods):
            classified = classify_request(path, method)
            entry = {
                "kind": KIND_ROUTE,
                "path": path,
                "method": method,
                "name": getattr(route, "name", "") or "",
                "group": classified.group,
                "exempt": classified.exempt,
            }
            key = entry_key(entry)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
    entries.sort(key=lambda row: (row["kind"], row["path"], row["method"], row["name"]))
    return entries


def entry_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (str(entry["kind"]), str(entry["path"]), str(entry.get("method") or ""))


def _index(entries: Sequence[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in entries:
        indexed[entry_key(entry)] = entry
    return indexed


def required_and_optional(
    fixture: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    required = list(fixture["entries"])
    optional = list(fixture.get("optional_entries") or [])
    return required, optional


def coverage_report(
    live: Sequence[dict[str, Any]],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Diff live table vs committed inventory. Never auto-updates the fixture."""
    required, optional = required_and_optional(fixture)
    live_index = _index(live)
    required_index = _index(required)
    optional_index = _index(optional)
    allowed_keys = set(required_index) | set(optional_index)

    unclassified = [
        entry
        for entry in live
        if entry["group"] == "unknown"
    ]
    added = [entry for entry in live if entry_key(entry) not in allowed_keys]
    removed = [entry for entry in required if entry_key(entry) not in live_index]

    reclassified: list[dict[str, Any]] = []
    comparable = list(required) + [
        entry for entry in optional if entry_key(entry) in live_index
    ]
    for expected in comparable:
        actual = live_index.get(entry_key(expected))
        if actual is None:
            continue
        if actual["group"] != expected["group"] or bool(actual["exempt"]) != bool(
            expected["exempt"]
        ):
            reclassified.append({"expected": expected, "live": actual})

    live_exempt_paths = sorted(
        {
            entry["path"]
            for entry in live
            if entry["kind"] == KIND_ROUTE and entry["exempt"]
        }
    )
    fixture_exempt = list(fixture["exempt_paths"])
    extra_exempt = sorted(set(live_exempt_paths) - set(fixture_exempt))
    missing_exempt = sorted(set(fixture_exempt) - set(live_exempt_paths))

    required_live = [entry for entry in live if entry_key(entry) in required_index]
    non_probe = [
        entry for entry in required_live if entry["group"] not in {"probes"}
    ]
    expected_count = int(fixture["non_probe_count"])
    non_probe_ok = len(non_probe) == expected_count == NON_PROBE_ROUTE_COUNT

    business_exempt = [
        entry
        for entry in live
        if entry["exempt"]
        and entry["group"] not in {"probes", "metrics"}
    ]

    return {
        "unclassified": unclassified,
        "added": added,
        "removed": removed,
        "reclassified": reclassified,
        "extra_exempt": extra_exempt,
        "missing_exempt": missing_exempt,
        "live_exempt_paths": live_exempt_paths,
        "non_probe_count_live": len(non_probe),
        "non_probe_count_expected": expected_count,
        "non_probe_ok": non_probe_ok,
        "business_exempt": business_exempt,
    }


def format_coverage_failure(report: dict[str, Any]) -> str:
    lines = [
        "Route coverage gate failed (WO-006).",
        "Classify new routes in src/heatguard/boundary/enforcement.py (_ROUTE_SPEC)",
        "and update tests/fixtures/route_inventory.json in the same change.",
        "Do not bump non_probe_count blindly.",
        "",
    ]

    def _row(entry: dict[str, Any]) -> str:
        method = entry.get("method") or "MOUNT"
        return (
            f"  {method} {entry['path']} "
            f"(kind={entry['kind']} group={entry['group']} exempt={entry['exempt']})"
        )

    if report["unclassified"]:
        lines.append("unclassified (no group assignment):")
        lines.extend(_row(entry) for entry in report["unclassified"])
        lines.append("")
    if report["added"]:
        lines.append("added:")
        lines.extend(_row(entry) for entry in report["added"])
        lines.append("")
    if report["removed"]:
        lines.append("removed:")
        lines.extend(_row(entry) for entry in report["removed"])
        lines.append("")
    if report["reclassified"]:
        lines.append("reclassified:")
        for item in report["reclassified"]:
            expected = item["expected"]
            live = item["live"]
            method = expected.get("method") or "MOUNT"
            lines.append(
                f"  {method} {expected['path']}: "
                f"expected group={expected['group']} exempt={expected['exempt']}; "
                f"live group={live['group']} exempt={live['exempt']}"
            )
        lines.append("")
    if report["extra_exempt"] or report["missing_exempt"]:
        lines.append("exempt set (must be exactly probes + /metrics):")
        if report["extra_exempt"]:
            lines.append(f"  extra: {', '.join(report['extra_exempt'])}")
        if report["missing_exempt"]:
            lines.append(f"  missing: {', '.join(report['missing_exempt'])}")
        lines.append("")
    if not report["non_probe_ok"]:
        lines.append(
            "non_probe_count: "
            f"live={report['non_probe_count_live']} "
            f"fixture={report['non_probe_count_expected']} "
            f"constant={NON_PROBE_ROUTE_COUNT} — "
            "classify the new route in _ROUTE_SPEC; do not bump the number blindly."
        )
        lines.append("")
    if report["business_exempt"]:
        lines.append("non-probe business routes marked exempt:")
        lines.extend(_row(entry) for entry in report["business_exempt"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def report_is_clean(report: dict[str, Any]) -> bool:
    return not (
        report["unclassified"]
        or report["added"]
        or report["removed"]
        or report["reclassified"]
        or report["extra_exempt"]
        or report["missing_exempt"]
        or not report["non_probe_ok"]
        or report["business_exempt"]
    )
