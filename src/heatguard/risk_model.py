"""Personal heat-risk stratification (ML overlay on the standards engine).

Labels for training come from ISO 7933 PHS outputs on **real cached weather**
(Dubai + Riyadh archives). The classifier learns non-linear interactions between
worker profile and site conditions; it **never overrides** the regulatory signal.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from ._paths import DATA_DIR
from .types import Conditions, MetabolicCategory, PersonalRisk, Worker

MODEL_REL_PATH = "models/risk_model.joblib"
META_REL_PATH = "models/risk_model_meta.json"
ELEVATED_THRESHOLD = 0.45

FEATURE_NAMES: tuple[str, ...] = (
    "days_on_job",
    "acclimatized",
    "experienced_elsewhere",
    "bmi",
    "age",
    "has_comorbidity",
    "wbgt_c",
    "met_ordinal",
    "hour",
    "rh_pct",
    "tdb_c",
    "wind_ms",
)


def model_path() -> Path:
    return DATA_DIR / MODEL_REL_PATH


def meta_path() -> Path:
    return DATA_DIR / META_REL_PATH


def worker_bmi(worker: Worker) -> float:
    h = max(worker.height_m, 1.0)
    return worker.weight_kg / (h * h)


def feature_vector(c: Conditions, worker: Worker) -> np.ndarray:
    met_ord = float(list(MetabolicCategory).index(c.met_category))
    return np.array(
        [
            float(worker.days_on_job),
            float(worker.acclimatized),
            float(worker.experienced_elsewhere),
            worker_bmi(worker),
            float(worker.age),
            float(worker.has_comorbidity),
            c.wbgt_c,
            met_ord,
            float(c.weather.timestamp.hour),
            c.weather.rh_pct,
            c.weather.tdb_c,
            c.weather.wind_ms,
        ],
        dtype=np.float64,
    )


def phs_elevated_label(c: Conditions, worker: Worker) -> bool:
    """Ground-truth label from ISO 7933 PHS (used only for offline training)."""
    from dataclasses import replace

    from . import acclimatization, hydration

    table_accl = not acclimatization.use_unacclimatized_thresholds(worker)
    eff = replace(worker, acclimatized=table_accl)
    mins, valid = hydration.max_safe_minutes(c, eff)
    if valid and mins < 45.0:
        return True
    hyd = hydration.hydration_target(c, eff, 1.0, mins if valid else 480.0)
    if hyd.phs_valid and hyd.core_temp_c >= 38.0:
        return True
    if worker.days_on_job < 5 and not worker.acclimatized and c.wbgt_c >= 28.0:
        return True
    return False


def _heuristic(c: Conditions, worker: Worker) -> PersonalRisk:
    """Conservative fallback when the serialized model is unavailable."""
    score = 0.0
    drivers: list[str] = []
    if worker.days_on_job < 5 and not worker.acclimatized:
        score += 0.35
        drivers.append("new/unacclimatized worker")
    if c.wbgt_c >= 30.0:
        score += min(0.35, (c.wbgt_c - 28.0) * 0.05)
        drivers.append(f"high WBGT ({c.wbgt_c:.1f} °C)")
    bmi = worker_bmi(worker)
    if bmi >= 30.0:
        score += 0.12
        drivers.append(f"elevated BMI ({bmi:.1f})")
    if worker.has_comorbidity:
        score += 0.15
        drivers.append("comorbidity flagged")
    if worker.age >= 50:
        score += 0.08
        drivers.append("age ≥ 50")
    score = min(1.0, score)
    note = "Heuristic stratification: " + (", ".join(drivers) if drivers else "low individual risk")
    return PersonalRisk(score=score, elevated=score >= ELEVATED_THRESHOLD, note=note)


@lru_cache(maxsize=1)
def _load_model():
    path = model_path()
    if not path.exists():
        return None
    try:
        import importlib
        joblib = importlib.import_module("joblib")
        return joblib.load(path)
    except ImportError:
        return None


def _load_meta() -> dict:
    path = meta_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _explain(score: float, worker: Worker, c: Conditions) -> str:
    parts: list[str] = []
    if worker.days_on_job < 5 and not worker.acclimatized:
        parts.append("new worker ramp")
    if worker.has_comorbidity:
        parts.append("comorbidity")
    if worker_bmi(worker) >= 30:
        parts.append("BMI")
    if c.wbgt_c >= 28:
        parts.append(f"WBGT {c.wbgt_c:.1f} °C")
    if not parts:
        parts.append("profile within expected band")
    return f"ML personal risk {score:.0%}: " + ", ".join(parts)


def assess(c: Conditions, worker: Worker) -> PersonalRisk:
    """Return personal risk overlay for one (conditions, worker) pair."""
    model = _load_model()
    if model is None:
        return _heuristic(c, worker)

    x = feature_vector(c, worker).reshape(1, -1)
    proba = float(model.predict_proba(x)[0, 1])
    elevated = proba >= ELEVATED_THRESHOLD
    meta = _load_meta()
    source = meta.get("label_source", "ISO 7933 PHS on cached Gulf weather")
    note = _explain(proba, worker, c) + f" [{source}]"
    return PersonalRisk(score=proba, elevated=elevated, note=note)


@dataclass(frozen=True, slots=True)
class TrainingSummary:
    rows: int
    positive_rate: float
    train_accuracy: float
    model_path: str


def train_and_save(
    *,
    intensity: MetabolicCategory = MetabolicCategory.HEAVY,
    worker_profiles: list[Worker] | None = None,
) -> TrainingSummary:
    """Build training matrix from demo archive weather + PHS labels; persist model."""
    import importlib
    sklearn_ensemble = importlib.import_module("sklearn.ensemble")
    GradientBoostingClassifier = getattr(sklearn_ensemble, "GradientBoostingClassifier")

    from .datasets import load_manifest
    from .scheduler import build_conditions
    from .service import DEMOS
    from .sites import get_site
    from .weather import fetch_archive

    if worker_profiles is None:
        worker_profiles = _default_worker_profiles()

    xs: list[np.ndarray] = []
    ys: list[int] = []
    for row in load_manifest()["weather"]["archive"]["demo"]:
        key = row["site_key"]
        cfg = DEMOS[key]
        site = get_site(key)
        season = fetch_archive(site, cfg["season_start"], cfg["season_end"])
        for w in _sample_weather_hours(season):
            c = build_conditions(w, site, intensity)
            for worker in worker_profiles:
                xs.append(feature_vector(c, worker))
                ys.append(int(phs_elevated_label(c, worker)))

    x_arr = np.vstack(xs)
    y_arr = np.array(ys, dtype=np.int8)
    model = GradientBoostingClassifier(
        random_state=42,
        max_depth=3,
        n_estimators=120,
        learning_rate=0.08,
    )
    model.fit(x_arr, y_arr)
    acc = float(model.score(x_arr, y_arr))

    out_dir = DATA_DIR / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    import importlib
    joblib = importlib.import_module("joblib")

    joblib.dump(model, model_path())
    meta_path().write_text(
        json.dumps(
            {
                "feature_names": list(FEATURE_NAMES),
                "elevated_threshold": ELEVATED_THRESHOLD,
                "label_source": "ISO 7933 PHS on Open-Meteo archive hours",
                "training_rows": len(y_arr),
                "positive_rate": float(y_arr.mean()),
                "train_accuracy": acc,
            },
            indent=2,
        )
    )
    _load_model.cache_clear()
    return TrainingSummary(
        rows=len(y_arr),
        positive_rate=float(y_arr.mean()),
        train_accuracy=acc,
        model_path=str(model_path()),
    )


def _default_worker_profiles() -> list[Worker]:
    """Small grid — keeps PHS labelling tractable on laptop training runs."""
    profiles: list[Worker] = []
    for days, accl in [(0, False), (2, False), (30, True), (120, True)]:
        for weight, height in [(65.0, 1.70), (85.0, 1.78)]:
            for age, comorb in [(28, False), (52, True)]:
                profiles.append(
                    Worker(
                        f"p-{days}-{weight}-{age}",
                        days_on_job=days,
                        acclimatized=accl,
                        weight_kg=weight,
                        height_m=height,
                        age=age,
                        has_comorbidity=comorb,
                    )
                )
    return profiles


def _sample_weather_hours(season: list, step: int = 3) -> list:
    """Subsample daylight hours so training finishes in seconds, not minutes."""
    from .weather import daytime

    hours = daytime(season, 5, 20)
    return hours[::step]
