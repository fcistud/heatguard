"""FastAPI backend exposing the HeatGuard engine to the dashboards.

Run with:  uvicorn heatguard.api:app --reload
Thin layer over ``heatguard.service``.
"""
from __future__ import annotations

import os
from datetime import date

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import service
from .types import MetabolicCategory

app = FastAPI(
    title="HeatGuard API",
    version="0.1.0",
    description="Adaptive WBGT-driven work-rest-hydration scheduler for Gulf outdoor crews.",
)

# Permissive by default for the local Vite dev server; lock down in production via
# HEATGUARD_CORS_ORIGINS="https://app.example.com,https://..." (comma-separated).
_cors_origins = [o.strip() for o in os.environ.get("HEATGUARD_CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/sites")
def sites() -> list[dict]:
    return service.list_sites()


@app.get("/demos")
def demos() -> list[str]:
    return list(service.DEMOS)


@app.get("/demo/{site_key}")
def demo(site_key: str, crew: int = Query(100, ge=1, le=100000)) -> dict:
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'. Try: {', '.join(service.DEMOS)}")
    try:
        return service.build_demo(site_key, crew)
    except FileNotFoundError:
        raise HTTPException(503, "Demo weather not cached. Run `heatguard fetch-demo`.")


_INTENSITIES = {m.value for m in MetabolicCategory}


def _check_intensity(intensity: str | None) -> None:
    if intensity is not None and intensity not in _INTENSITIES:
        raise HTTPException(400, f"intensity must be one of {sorted(_INTENSITIES)}")


@app.get("/timeline/{site_key}/{day}")
def timeline(
    site_key: str,
    day: str,
    intensity: str | None = Query(None, description="light|moderate|heavy|very_heavy (default: demo's)"),
    newcomer_days: int = Query(0, ge=0, le=14, description="days-on-job for the new-worker lane"),
) -> dict:
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'.")
    _check_intensity(intensity)
    try:
        return service.timeline_for_day(site_key, date.fromisoformat(day), intensity, newcomer_days)
    except ValueError:
        raise HTTPException(400, "day must be YYYY-MM-DD")


@app.get("/hour/{site_key}/{day}/{hour}")
def hour(
    site_key: str,
    day: str,
    hour: int,
    worker: str = Query("veteran", pattern="^(veteran|newcomer)$"),
    newcomer_days: int = Query(0, ge=0, le=14),
    intensity: str | None = Query(None),
    measured_wbgt: float | None = Query(None, ge=0, le=60, description="on-site meter reading degC; overrides the estimate"),
) -> dict:
    """One hour's advisory for a chosen worker/intensity, optionally using a
    measured WBGT instead of the model estimate (returns both for comparison)."""
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'.")
    if not 0 <= hour <= 23:
        raise HTTPException(400, "hour must be 0..23")
    _check_intensity(intensity)
    try:
        return service.hour_advisory(
            site_key, date.fromisoformat(day), hour, worker, newcomer_days, intensity, measured_wbgt
        )
    except ValueError:
        raise HTTPException(400, "day must be YYYY-MM-DD")
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip('"')) from exc


@app.get("/impact/{site_key}")
def impact(site_key: str, crew: int = Query(100, ge=1, le=100000)) -> dict:
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'.")
    return service.season_impact(site_key, crew)


@app.get("/economics/{site_key}")
def economics(site_key: str, crew: int = Query(100, ge=1, le=100000)) -> dict:
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'.")
    return service.business_case(site_key, crew)


@app.get("/sensitivity/{site_key}")
def sensitivity(site_key: str, crew: int = Query(100, ge=1, le=100000)) -> list[dict]:
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'.")
    return service.impact_sensitivity(site_key, crew)


@app.get("/scale/{site_key}")
def scale(
    site_key: str,
    workforce: int = Query(5000, ge=1, le=50_000_000, description="workers to project the impact to"),
) -> dict:
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'.")
    from .scale import SCALE_CONTEXT, WORKFORCE_PRESETS

    return {
        "projection": service.scale_projection(site_key, workforce),
        "presets": WORKFORCE_PRESETS,
        "context": SCALE_CONTEXT,
    }


@app.get("/backtest")
def backtest() -> dict:
    return service.backtest()


@app.get("/compliance/{site_key}/export")
def compliance_export(site_key: str, fmt: str = Query("csv", pattern="^(csv|jsonl)$")) -> Response:
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'.")
    log = service.compliance_for_day(site_key, service.DEMOS[site_key]["focus_day"])
    if fmt == "csv":
        return Response(log.export_csv(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={site_key}_compliance.csv"})
    return Response(log.export_jsonl(), media_type="application/x-ndjson")


class DecideRequest(BaseModel):
    site_key: str = "riyadh"
    tdb: float = Field(..., ge=-10, le=60, description="air temperature degC")
    rh: float = Field(..., ge=0, le=100, description="relative humidity %")
    wind: float = Field(2.0, ge=0, le=40, description="wind speed m/s")
    solar: float = Field(800.0, ge=0, le=1400, description="shortwave radiation W/m2")
    hour: int = Field(12, ge=0, le=23)
    intensity: str = "heavy"
    days_on_job: int = Field(120, ge=0, le=3650)
    acclimatized: bool = True
    experienced: bool = False
    measured_wbgt: float | None = Field(None, ge=0, le=60)


@app.post("/decide")
def decide(req: DecideRequest) -> dict:
    if req.intensity not in {m.value for m in MetabolicCategory}:
        raise HTTPException(400, f"intensity must be one of {[m.value for m in MetabolicCategory]}")
    try:
        return service.decide_one(
            req.site_key, req.tdb, req.rh, req.wind, req.solar, req.hour, req.intensity,
            req.days_on_job, req.acclimatized, req.experienced, req.measured_wbgt,
        )
    except KeyError as exc:
        raise HTTPException(404, f"Unknown site '{req.site_key}'") from exc
