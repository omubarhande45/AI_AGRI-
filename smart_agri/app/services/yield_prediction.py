"""
AI/ML Prediction module - crop yield prediction.

Primary path  : the trained Gradient Boosting model (models/ml/yield_model.joblib).
Fallback path : a transparent agronomic calculation from the crop profile, used
                only when the model artifact is missing, and always reported as
                such in the UI so the farmer is never misled.
"""
from __future__ import annotations

import json
import os
from typing import Any

import joblib
import numpy as np

from ..agronomy import get_crop
from ..config import ML_MODEL_DIR

_CACHE: dict[str, Any] = {}


def _load():
    if "bundle" in _CACHE:
        return _CACHE["bundle"]
    path = os.path.join(ML_MODEL_DIR, "yield_model.joblib")
    bundle = None
    if os.path.exists(path):
        try:
            bundle = joblib.load(path)
        except Exception as exc:
            print(f"[yield] could not load model: {exc}")
    _CACHE["bundle"] = bundle
    return bundle


def model_available() -> bool:
    return _load() is not None


def model_metrics() -> dict:
    b = _load()
    return b["metrics"] if b else {}


def _rule_based(row: dict[str, float]) -> float:
    """Transparent agronomic estimate - mirrors the response surface used to
    build the trial network, so numbers stay comparable."""
    prof = get_crop(row["crop"])
    if prof is None:
        return 0.0
    n_req, p_req, k_req = prof.npk_kg_per_acre
    nut = ((min(1.25, row["nitrogen"] / max(n_req, 1)) ** 0.55)
           * (min(1.25, row["phosphorus"] / max(p_req, 1)) ** 0.22)
           * (min(1.25, row["potassium"] / max(k_req, 1)) ** 0.23))
    water_avail = row["irrigation_mm"] + row["rainfall_mm"] * (0.55 if row.get("drip") else 0.75)
    wsi = min(1.4, water_avail / max(prof.water_mm_season, 1))
    water_f = min(1.18, (1.0 if wsi >= 1 else (0.35 + 0.65 * wsi)) * (1.08 if row.get("drip") else 1.0))
    heat = max(0.45, 1.0 - 0.055 * max(0.0, row["temp_max_mean"] - 30.0) ** 1.15)
    ph_f = 1.0 - 0.16 * abs(row["ph"] - 6.9) / 1.5
    oc_f = 0.9 + 0.22 * min(1.0, row["organic_carbon"] / 0.7)
    return prof.yield_kg_per_acre * nut * water_f * heat * ph_f * oc_f


def predict_yield(features: dict[str, Any]) -> dict[str, Any]:
    """features: crop, season, soil_type, area_acres, nitrogen, phosphorus,
    potassium, ph, organic_carbon, rainfall_mm, irrigation_mm, temp_max_mean,
    drip, plant_density_index, pest_control"""
    prof = get_crop(features.get("crop"))
    row = {
        "crop": features.get("crop"),
        "season": features.get("season") or (prof.seasons[0] if prof else "kharif"),
        "soil_type": features.get("soil_type") or "Medium black (loam)",
        "area_acres": float(features.get("area_acres") or 1.0),
        "nitrogen": float(features.get("nitrogen") or 0),
        "phosphorus": float(features.get("phosphorus") or 0),
        "potassium": float(features.get("potassium") or 0),
        "ph": float(features.get("ph") or 7.0),
        "organic_carbon": float(features.get("organic_carbon") or 0.5),
        "rainfall_mm": float(features.get("rainfall_mm") or 0),
        "irrigation_mm": float(features.get("irrigation_mm") or 0),
        "temp_max_mean": float(features.get("temp_max_mean") or 32.0),
        "drip": int(features.get("drip") or 0),
        "plant_density_index": float(features.get("plant_density_index") or 1.0),
        "pest_control": int(features.get("pest_control") if features.get("pest_control") is not None else 1),
    }

    bundle = _load()

    # The model was trained on the crop's regional benchmark yield, which is a
    # legitimate pre-sowing input - supply it so the feature vector matches training.
    if bundle is not None and "typical_yield" in bundle["features"] and prof is not None:
        row["typical_yield"] = prof.yield_kg_per_acre

    crop_error_pct = None
    if bundle is not None:
        model = bundle["model"]
        import pandas as pd
        feats = bundle["features"]
        for missing in (c for c in feats if c not in row):
            row[missing] = 0.0
        X = pd.DataFrame([row])[feats]
        raw = float(model.predict(X)[0])
        # The model predicts yield RATIO (achieved / crop typical); convert back.
        typical = (bundle.get("typical_yield") or {}).get(row["crop"])
        y = raw * typical if typical else raw
        source = "ml_model"
        metrics = bundle["metrics"]
        crop_error_pct = (metrics.get("per_crop") or {}).get(row["crop"], {}).get("mape_pct")
        err_pct = crop_error_pct or metrics.get("median_ape_pct", 10.0)
        band = max(0.08, min(0.35, err_pct / 100.0 * 1.25))
    else:
        y = _rule_based(row)
        source = "rule_based_fallback"
        band = 0.20

    if prof is not None:
        lo_floor, hi_cap = prof.yield_range
        y = max(lo_floor * 0.5, min(hi_cap * 1.2, y))

    per_acre = round(y, 1)
    total_q = round(per_acre * row["area_acres"] / 100.0, 2)
    return {
        "source": source,
        "model_metrics": model_metrics(),
        "crop": row["crop"],
        "area_acres": row["area_acres"],
        "yield_kg_per_acre": per_acre,
        "yield_range_kg_per_acre": [round(per_acre * (1 - band), 1), round(per_acre * (1 + band), 1)],
        "confidence_pct": round(100 * (1 - band), 1),
        "crop_error_pct": crop_error_pct,
        "total_yield_q": total_q,
        "total_yield_range_q": [round(total_q * (1 - band), 2), round(total_q * (1 + band), 2)],
        "typical_yield_kg_per_acre": prof.yield_kg_per_acre if prof else None,
        "performance_vs_typical_pct": (
            round(100 * (per_acre - prof.yield_kg_per_acre) / prof.yield_kg_per_acre, 1)
            if prof else None),
        "limiting_factors": limiting_factors(row, prof),
    }


def limiting_factors(row: dict[str, Any], prof) -> list[dict[str, Any]]:
    """Rank the agronomic constraints for this field - feeds the DSS actions."""
    out: list[dict[str, Any]] = []
    if prof is None:
        return out
    n_req, p_req, k_req = prof.npk_kg_per_acre

    for label, have, need, unit in (
        ("Nitrogen", row["nitrogen"], n_req, "kg/acre"),
        ("Phosphorus", row["phosphorus"], p_req, "kg/acre"),
        ("Potassium", row["potassium"], k_req, "kg/acre"),
    ):
        frac = have / max(need, 1)
        if frac < 0.85:
            out.append({"factor": label, "impact_pct": round((1 - frac) * 45, 1),
                        "detail": f"{have:.0f} of {need:.0f} {unit} required "
                                  f"({frac*100:.0f}% sufficiency)",
                        "gap": round(max(0.0, need - have), 1), "unit": unit})

    water_avail = row["irrigation_mm"] + row["rainfall_mm"] * (0.55 if row["drip"] else 0.75)
    wsi = water_avail / max(prof.water_mm_season, 1)
    if wsi < 0.9:
        out.append({"factor": "Water availability", "impact_pct": round((1 - min(wsi, 1)) * 70, 1),
                    "detail": f"{water_avail:.0f} mm available vs {prof.water_mm_season:.0f} mm "
                              f"season requirement ({wsi*100:.0f}%)",
                    "gap": round(max(0.0, prof.water_mm_season - water_avail), 1), "unit": "mm"})

    if row["temp_max_mean"] > 33:
        out.append({"factor": "Heat stress", "impact_pct": round(min(35, 5 * (row["temp_max_mean"] - 30)), 1),
                    "detail": f"Mean max {row['temp_max_mean']:.1f} C exceeds the 30 C optimum "
                              f"during {prof.critical_stage}",
                    "gap": 0, "unit": ""})

    if not (6.2 <= row["ph"] <= 7.8):
        out.append({"factor": "Soil pH", "impact_pct": round(min(25, 8 * abs(row["ph"] - 7.0)), 1),
                    "detail": f"pH {row['ph']:.2f} outside the 6.2-7.8 optimum - "
                              f"nutrient uptake is restricted",
                    "gap": 0, "unit": ""})

    if row["organic_carbon"] < 0.5:
        out.append({"factor": "Organic carbon", "impact_pct": round((0.5 - row["organic_carbon"]) * 30, 1),
                    "detail": f"OC {row['organic_carbon']:.2f}% - low for water holding capacity",
                    "gap": round(0.6 - row["organic_carbon"], 2), "unit": "%"})

    if row["pest_control"] == 0:
        out.append({"factor": "Plant protection", "impact_pct": 14.0,
                    "detail": "No pest/disease control recorded - IPM schedule recommended",
                    "gap": 0, "unit": ""})

    return sorted(out, key=lambda d: d["impact_pct"], reverse=True)
