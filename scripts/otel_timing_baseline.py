#!/usr/bin/env python3
"""Cold + warm GET /demo/{site} span-duration baseline (WO-015 O2 artifact).

Forces sampling 1.0 and an in-memory exporter, then writes a JSON summary
suitable for CI artifact upload.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

# Force tracing before importing the app.
os.environ.setdefault("HEATGUARD_ENV", "test")
os.environ["HEATGUARD_TRACE_SAMPLE_RATIO"] = "1.0"
os.environ["HEATGUARD_TRACE_EXPORTER"] = "none"
os.environ["HEATGUARD_TRACE_SIMPLE"] = "1"

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

ROOT = Path(__file__).resolve().parents[1]


def _ms(ns: int) -> float:
    return round(ns / 1e6, 3)


def main() -> int:
    site = os.environ.get("HEATGUARD_TIMING_SITE", "dubai")
    out = Path(
        os.environ.get(
            "HEATGUARD_TIMING_OUT",
            str(ROOT / "artifacts" / "o2-latency-baseline.json"),
        )
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    from heatguard.observability import tracing as t

    t.force_reconfigure()

    from fastapi.testclient import TestClient

    from heatguard.api import app
    from heatguard.service import _season_hourly

    t.reset_tracing_for_tests(provider, app=app)
    _season_hourly.cache_clear()

    client = TestClient(app)
    # Lifespan already warm; clear season cache so first request pays replay cost.
    _season_hourly.cache_clear()
    exporter.clear()

    t0 = time.perf_counter()
    r1 = client.get(f"/demo/{site}")
    cold_wall_s = time.perf_counter() - t0
    assert r1.status_code == 200, r1.text[:200]
    cold_spans = list(exporter.get_finished_spans())
    exporter.clear()

    t1 = time.perf_counter()
    r2 = client.get(f"/demo/{site}")
    warm_wall_s = time.perf_counter() - t1
    assert r2.status_code == 200, r2.text[:200]
    warm_spans = list(exporter.get_finished_spans())

    def summarize(spans):
        by_name: dict[str, list[float]] = defaultdict(list)
        for sp in spans:
            by_name[sp.name].append(_ms(sp.end_time - sp.start_time))
        return {
            name: {
                "count": len(vals),
                "total_ms": round(sum(vals), 3),
                "max_ms": round(max(vals), 3),
            }
            for name, vals in sorted(by_name.items())
        }

    payload = {
        "site_key": site,
        "sample_ratio": 1.0,
        "cold": {
            "wall_seconds": round(cold_wall_s, 4),
            "span_count": len(cold_spans),
            "by_name": summarize(cold_spans),
        },
        "warm": {
            "wall_seconds": round(warm_wall_s, 4),
            "span_count": len(warm_spans),
            "by_name": summarize(warm_spans),
        },
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {out}")
    print(
        f"cold={payload['cold']['wall_seconds']}s "
        f"warm={payload['warm']['wall_seconds']}s "
        f"cold_spans={payload['cold']['span_count']} "
        f"warm_spans={payload['warm']['span_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
