"""
AI/ML Prediction module - irrigation recommendation.

Computes reference evapotranspiration (Hargreaves-Samani, needs only Tmin/Tmax),
applies the FAO-56 crop coefficient curve for the field's growth stage, deducts
effective rainfall and current soil moisture, and returns:
  * days until irrigation is needed
  * mm of water to apply
  * litres per acre for the farmer's drip/sprinkler system
  * a 7-day schedule that already accounts for forecast rain
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..agronomy import get_crop
from ..config import ACRE_TO_HA

# FAO-56 style Kc curve, normalised to 0..1 of the growing period
KC_CURVE = [
    (0.00, 0.35), (0.10, 0.40), (0.20, 0.55), (0.35, 0.85), (0.50, 1.10),
    (0.65, 1.15), (0.80, 1.00), (0.90, 0.80), (1.00, 0.55),
]

# Soil-water budget: fraction of available water held between FC and WP (% vol)
SOIL_AWHC = {  # mm of plant-available water per 100 mm of soil (root zone 400 mm)
    "Deep black (clay)": 0.20, "Medium black (loam)": 0.17,
    "Sandy loam": 0.13, "Red sandy": 0.10,
}


def kc_at(progress: float) -> float:
    progress = min(max(progress, 0.0), 1.0)
    for i in range(1, len(KC_CURVE)):
        x0, y0 = KC_CURVE[i - 1]
        x1, y1 = KC_CURVE[i]
        if progress <= x1:
            t = (progress - x0) / (x1 - x0 or 1)
            return y0 + t * (y1 - y0)
    return KC_CURVE[-1][1]


def hargreaves_et0(tmin: float, tmax: float, extraterrestrial: float = 15.2) -> float:
    """FAO-24 Hargreaves-Samani: ET0 (mm/day) from Tmin/Tmax only."""
    td = max(tmax - tmin, 1.0)
    return 0.0023 * extraterrestrial * ((tmax + tmin) / 2 + 17.8) * (td ** 0.5)


def crop_progress(sowing_date: str | None, duration_days: int, today=None) -> float:
    today = today or datetime.now().date()
    if not sowing_date:
        return 0.5
    try:
        s = datetime.strptime(sowing_date, "%Y-%m-%d").date()
    except ValueError:
        return 0.5
    elapsed = (today - s).days
    return min(max(elapsed / max(duration_days, 1), 0.0), 1.0)


def recommend(field: dict, farm: dict, soil: dict | None,
              forecast: list[dict] | None = None) -> dict[str, Any]:
    """field/farm/soil are sqlite row dicts; forecast is a list of weather dicts."""
    prof = get_crop(field.get("crop"))
    duration = prof.duration_days if prof else 120
    progress = crop_progress(field.get("sowing_date"), duration)
    kc = kc_at(progress)

    forecast = forecast or []
    recent = [w for w in forecast if w.get("is_forecast")]
    if not recent:
        recent = [{"temp_min": 18, "temp_max": 32, "rainfall_mm": 0, "humidity": 50}
                  for _ in range(7)]
    recent = recent[:7]

    # 1. Evapotranspiration demand over the next 7 days
    et0 = [hargreaves_et0(w["temp_min"], w["temp_max"]) for w in recent]
    etc = [e * kc for e in et0]

    # 2. Effective rainfall (only ~70% of light rain reaches the root zone)
    eff_rain = [min(w.get("rainfall_mm", 0.0) * (0.75 if w.get("rainfall_mm", 0) < 25 else 0.9),
                    40.0) for w in recent]

    # 3. Soil moisture deficit from the latest reading
    soil_type = farm.get("soil_type") or "Medium black (loam)"
    awhc_frac = SOIL_AWHC.get(soil_type, 0.17)
    root_mm = 400.0
    awc_total = awhc_frac * root_mm                    # mm available at field capacity
    moisture = (soil or {}).get("moisture", 24.0) or 24.0
    wp_vol = 0.45 * awhc_frac * 100                    # wilting point % vol approx
    current_mm = max(0.0, (moisture - wp_vol) / 100.0 * root_mm)
    depletion = max(0.0, awc_total * 0.5 - current_mm)  # irrigate at 50% depletion
    mad = awc_total * 0.5                               # management allowable depletion

    # 4. Walk the water balance forward day by day
    balance = current_mm
    schedule: list[dict] = []
    days_to_irrigate: int | None = None
    total_net_mm = 0.0
    for i, w in enumerate(recent):
        balance += eff_rain[i] - etc[i]
        deficit = 0.0
        if balance < awc_total - mad:
            deficit = (awc_total - mad) - balance
            if days_to_irrigate is None:
                days_to_irrigate = i
            total_net_mm += deficit
            balance += deficit
            schedule.append({
                "date": w.get("date"),
                "day_label": "today" if i == 0 else f"day {i+1}",
                "irrigate": True,
                "net_mm": round(deficit, 1),
                "reason": f"Soil moisture falls to {balance - deficit:.0f} mm, below the "
                          f"{awc_total - mad:.0f} mm refill trigger",
                "et0_mm": round(et0[i], 2), "etc_mm": round(etc[i], 2),
                "effective_rain_mm": round(eff_rain[i], 1),
            })
        else:
            schedule.append({
                "date": w.get("date"),
                "day_label": "today" if i == 0 else f"day {i+1}",
                "irrigate": False,
                "net_mm": 0.0,
                "reason": ("Rainfall of "
                           f"{w.get('rainfall_mm', 0):.1f} mm covers the crop demand"
                           if eff_rain[i] > etc[i] * 0.6
                           else f"Balance {balance:.0f} mm is above the refill trigger"),
                "et0_mm": round(et0[i], 2), "etc_mm": round(etc[i], 2),
                "effective_rain_mm": round(eff_rain[i], 1),
            })

    # 5. Convert to farmer-facing volumes
    efficiency = 0.90 if (farm.get("irrigation") or "").lower() == "drip" else \
                 0.75 if (farm.get("irrigation") or "").lower() == "sprinkler" else 0.60
    first = next((s for s in schedule if s["irrigate"]), None)
    apply_mm = round((first["net_mm"] / efficiency), 1) if first else 0.0
    litres_per_acre = round(apply_mm * 10000 / 2.471 * 1000 / 1000, 0)  # mm -> L/acre
    # 1 mm over 1 acre = 4046.86 L
    litres_per_acre = round(apply_mm * 4046.86, 0)

    stress = min(1.0, max(0.0, 1 - (balance / max(awc_total, 1))))
    urgency = "high" if (days_to_irrigate or 99) <= 1 or stress > 0.65 else \
              "medium" if (days_to_irrigate or 99) <= 3 else "low"

    return {
        "crop": field.get("crop"),
        "growth_stage_progress_pct": round(progress * 100, 1),
        "growth_stage": _stage_name(progress),
        "kc": round(kc, 2),
        "soil_type": soil_type,
        "current_moisture_pct": round(moisture, 1),
        "available_water_capacity_mm": round(awc_total, 1),
        "refill_trigger_mm": round(awc_total - mad, 1),
        "days_until_irrigation": days_to_irrigate if days_to_irrigate is not None else ">7",
        "apply_mm": apply_mm,
        "litres_per_acre": litres_per_acre,
        "system": farm.get("irrigation"),
        "efficiency": efficiency,
        "urgency": urgency,
        "water_stress_index": round(stress, 3),
        "schedule": schedule,
        "weekly_demand_mm": round(sum(etc), 1),
        "weekly_effective_rain_mm": round(sum(eff_rain), 1),
        "weekly_net_requirement_mm": round(total_net_mm, 1),
        "saving_note": _saving_note(farm.get("irrigation"), efficiency, apply_mm,
                                    field.get("area_acres", 1)),
    }


def _stage_name(p: float) -> str:
    if p < 0.12: return "germination / establishment"
    if p < 0.30: return "vegetative growth"
    if p < 0.50: return "flowering"
    if p < 0.75: return "fruit / grain development"
    if p < 0.92: return "maturity"
    return "senescence / harvest ready"


def _saving_note(system: str | None, eff: float, mm: float, acres: float) -> str:
    if not mm:
        return "No irrigation needed in the next 7 days."
    if (system or "").lower() == "drip":
        return (f"Drip at {eff*100:.0f}% efficiency: {mm:.0f} mm needed. "
                f"Approx {mm * 4046.86 * acres / 1000:.0f} thousand litres for {acres:.1f} acre.")
    return (f"Flood/sprinkler at {eff*100:.0f}% efficiency wastes "
            f"{(1-eff)*100:.0f}% of applied water. Switching to drip would cut this "
            f"event from {mm:.0f} mm to {mm*eff/0.9:.0f} mm.")
