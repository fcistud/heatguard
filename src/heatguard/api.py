"""FastAPI backend exposing the HeatGuard engine to the dashboards.

Run with:  uvicorn heatguard.api:app --reload
Thin layer over ``heatguard.service``.
"""
from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import service
from .types import MetabolicCategory

app = FastAPI(
    title="HeatGuard API",
    version="0.1.0",
    description="Adaptive WBGT-driven work-rest-hydration scheduler for Gulf outdoor crews.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev: allow the Vite dev server
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


@app.get("/timeline/{site_key}/{day}")
def timeline(site_key: str, day: str) -> dict:
    if site_key not in service.DEMOS:
        raise HTTPException(404, f"Unknown demo '{site_key}'.")
    try:
        return service.timeline_for_day(site_key, date.fromisoformat(day))
    except ValueError:
        raise HTTPException(400, "day must be YYYY-MM-DD")


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
    tdb: float
    rh: float
    wind: float = 2.0
    solar: float = 800.0
    hour: int = 12
    intensity: str = "heavy"
    days_on_job: int = 120
    acclimatized: bool = True
    experienced: bool = False
    measured_wbgt: float | None = None


@app.post("/decide")
def decide(req: DecideRequest) -> dict:
    if req.intensity not in {m.value for m in MetabolicCategory}:
        raise HTTPException(400, f"intensity must be one of {[m.value for m in MetabolicCategory]}")
    return service.decide_one(
        req.site_key, req.tdb, req.rh, req.wind, req.solar, req.hour, req.intensity,
        req.days_on_job, req.acclimatized, req.experienced, req.measured_wbgt,
    )
