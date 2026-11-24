"""
Digital Twin module - a living virtual replica of each field.

The twin advances a simple but explicit crop-growth model day by day:
  * thermal time (growing degree days) drives phenological progress
  * LAI grows logistically toward a crop-specific maximum
  * daily biomass gain = radiation-use efficiency x intercepted PAR x stress
  * water stress comes from the same soil-water balance the irrigation
    recommender uses, so the twin and the advice can never disagree
  * NDVI, health score and projected yield follow from LAI and stress

Because every step is deterministic and parameterised, the UI can offer
"what-if" scenarios (extra irrigation, skip a spray, heat wave, early sowing)
and show the divergence from the baseline twin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from ..agronomy import get_crop
from ..config import ACRE_TO_HA
from .irrigation import SOIL_AWHC, hargreaves_et0, kc_at

RUE = {  # g dry matter per MJ intercepted PAR
    "Grape": 1.35, "Onion": 1.55, "Tomato": 1.75, "Maize": 1.95, "Potato": 1.70,
    "Sugarcane": 1.70, "Cotton": 1.50, "Soybean": 1.30, "Pomegranate": 1.20,
    "Pigeon pea (Tur)": 1.15, "Wheat": 1.90, "Banana": 1.60, "Bell pepper": 1.65,
    "Squash": 1.60,
}
LAI_MAX = {"Grape": 4.5, "Onion": 3.5, "Tomato": 4.2, "Maize": 4.8, "Potato": 4.0,
           "Sugarcane": 5.5, "Cotton": 3.8, "Soybean": 4.2, "Pomegranate": 3.6,
           "Pigeon pea (Tur)": 3.4, "Wheat": 4.6, "Banana": 4.4, "Bell pepper": 3.9,
           "Squash": 3.2}
HI = {"Grape": 0.45, "Onion": 0.70, "Tomato": 0.55, "Maize": 0.45, "Potato": 0.75,
      "Sugarcane": 0.50, "Cotton": 0.35, "Soybean": 0.40, "Pomegranate": 0.35,
      "Pigeon pea (Tur)": 0.25, "Wheat": 0.42, "Banana": 0.35, "Bell pepper": 0.50,
      "Squash": 0.45}
T_BASE = {"Maize": 10, "Sugarcane": 10, "Cotton": 12, "Tomato": 10, "Wheat": 4}
GDD_REQ = {"Maize": 1250, "Sugarcane": 2600, "Cotton": 1700, "Tomato": 1400,
           "Wheat": 1400, "Onion": 1200, "Potato": 1000, "Grape": 1500,
           "Soybean": 1100, "Pomegranate": 1900, "Pigeon pea (Tur)": 1600,
           "Banana": 2600, "Bell pepper": 1700, "Squash": 900}


@dataclass
class TwinState:
    date: str
    gdd: float
    progress: float          # 0..1 phenological progress from GDD
    lai: float
    biomass_kg_ha: float
    ndvi: float
    soil_water_mm: float
    water_stress: float      # 0 (no stress) .. 1 (severe)
    yield_kg_ha: float
    health_score: float


@dataclass
class Scenario:
    name: str = "baseline"
    extra_irrigation_mm_per_week: float = 0.0
    irrigation_efficiency: float | None = None
    pest_damage_pct: float = 0.0
    temp_anomaly_c: float = 0.0
    rain_multiplier: float = 1.0
    fertility_index: float = 1.0
    notes: str = ""


def _weather_window(farm_id: int, start: date, days: int) -> list[dict]:
    from .. import db
    rows = db.query(
        "SELECT date, temp_min, temp_max, rainfall_mm, humidity, solar_mj, is_forecast "
        "FROM weather_daily WHERE farm_id=? AND date >= ? ORDER BY date LIMIT ?",
        (farm_id, start.isoformat(), days))
    if not rows:  # no data yet - synthesize a plausible season
        return [{"date": (start + timedelta(days=i)).isoformat(),
                 "temp_min": 18, "temp_max": 32, "rainfall_mm": 0,
                 "humidity": 55, "solar_mj": 20, "is_forecast": 1}
                for i in range(days)]
    return rows


def simulate(field: dict, farm: dict, soil: dict | None,
             days_ahead: int = 60, scenario: Scenario | None = None,
             start: date | None = None) -> dict[str, Any]:
    """Run the twin forward and return the trajectory + summary."""
    sc = scenario or Scenario()
    prof = get_crop(field.get("crop"))
    if prof is None:
        return {"error": f"unknown crop {field.get('crop')}"}

    start = start or date.today()
    crop = field["crop"]
    t_base = T_BASE.get(crop, 8)
    gdd_req = GDD_REQ.get(crop, 1300)
    laimax = LAI_MAX.get(crop, 4.0)
    rue = RUE.get(crop, 1.5)
    hi = HI.get(crop, 0.45)

    # Starting phenology from the real sowing date
    sowing = field.get("sowing_date")
    gdd = 0.0
    if sowing:
        try:
            s = datetime.strptime(sowing, "%Y-%m-%d").date()
            past = _weather_window(farm["id"], s, max((start - s).days, 1))
            for w in past:
                tavg = (w["temp_min"] + w["temp_max"]) / 2
                gdd += max(0.0, min(tavg, 42) - t_base)
        except ValueError:
            pass
    gdd *= max(0.85, min(1.15, sc.fertility_index))

    # Soil water bucket
    awhc_frac = SOIL_AWHC.get(farm.get("soil_type") or "Medium black (loam)", 0.17)
    root_mm = 400.0
    awc = awhc_frac * root_mm
    wp_vol = 0.45 * awhc_frac * 100
    moisture = (soil or {}).get("moisture", 25.0) or 25.0
    water = max(0.0, min(awc, (moisture - wp_vol) / 100.0 * root_mm))
    efficiency = sc.irrigation_efficiency or 0.90

    lai = min(laimax, 0.3 + (gdd / max(gdd_req, 1)) ** 0.9 * laimax * sc.fertility_index)
    biomass = lai * 900.0 * max(0.4, sc.fertility_index)   # kg/ha
    trajectory: list[dict] = []
    peak_stress = 0.0
    days_irrigated = 0

    for i, w in enumerate(_weather_window(farm["id"], start, days_ahead)):
        d = _parse(w["date"]) or (start + timedelta(days=i))
        tmin = w["temp_min"] + sc.temp_anomaly_c
        tmax = w["temp_max"] + sc.temp_anomaly_c
        tavg = (tmin + tmax) / 2
        gdd += max(0.0, min(tavg, 42) - t_base)
        progress = min(1.0, gdd / max(gdd_req, 1))
        kc = kc_at(progress)

        # Water balance
        rain = w.get("rainfall_mm", 0.0) * sc.rain_multiplier
        eff_rain = rain * (0.75 if rain < 25 else 0.9)
        et0 = hargreaves_et0(tmin, tmax)
        etc = et0 * kc
        water += eff_rain - etc
        stress = 0.0
        if water < awc * 0.5:
            shortage = (awc * 0.5 - water)
            applied = min(shortage, sc.extra_irrigation_mm_per_week / 7.0 * efficiency
                          if sc.extra_irrigation_mm_per_week else 0.0)
            if applied > 0:
                water += applied
                days_irrigated += 1
            stress = min(1.0, shortage / max(awc * 0.5, 1))
        elif water > awc:
            water = awc                      # drainage
            stress = min(1.0, (water - awc * 0.95) / max(awc * 0.2, 1)) * 0.3
        water = max(0.0, min(awc * 1.05, water))
        peak_stress = max(peak_stress, stress)

        # Canopy growth
        lai_target = laimax * sc.fertility_index * (1 - 0.25 * stress)
        growth_rate = 0.06 * (1 - progress ** 3)
        lai += (min(lai_target, laimax) - lai) * growth_rate
        lai = max(0.1, min(laimax * 1.05, lai))

        # Biomass
        par = w.get("solar_mj", 20.0) * 0.5
        intercepted = par * (1 - 2.718281828 ** (-0.7 * lai))
        gain = rue * intercepted * (1 - 0.7 * stress) * (1 - 0.4 * sc.pest_damage_pct / 100.0)
        biomass += gain * 22.0                # scaled to kg/ha per day
        biomass *= (1 - 0.0025 * max(0.0, tmax - 38))

        ndvi = round(min(0.95, 0.15 + 0.16 * lai) * (1 - 0.35 * stress), 3)
        health = 100 * max(0, 1 - 0.6 * stress - 0.35 * sc.pest_damage_pct / 100.0
                           - 0.15 * max(0, tmax - 36) / 5)

        trajectory.append({
            "date": d.isoformat(),
            "gdd": round(gdd, 1),
            "progress_pct": round(progress * 100, 1),
            "lai": round(lai, 2),
            "biomass_kg_ha": round(biomass, 0),
            "ndvi": ndvi,
            "soil_water_mm": round(water, 1),
            "water_stress": round(stress, 3),
            "yield_kg_ha": round(biomass * hi * progress, 0),
            "health_score": round(min(100, max(0, health)), 1),
            "temp_max": round(tmax, 1), "rain_mm": round(rain, 1),
            "et0_mm": round(et0, 2),
        })

    last = trajectory[-1]
    proj_yield_kg_ha = last["yield_kg_ha"]
    proj_yield_kg_acre = proj_yield_kg_ha * ACRE_TO_HA
    area = float(field.get("area_acres") or 1.0)

    return {
        "field": field.get("name"), "crop": crop, "variety": field.get("variety"),
        "scenario": sc.name, "scenario_notes": sc.notes,
        "days_ahead": days_ahead,
        "start_date": start.isoformat(),
        "end_date": trajectory[-1]["date"],
        "trajectory": trajectory,
        "current": trajectory[0],
        "final": last,
        "peak_water_stress": round(peak_stress, 3),
        "days_irrigated": days_irrigated,
        "projected_yield_kg_per_acre": round(proj_yield_kg_acre, 1),
        "projected_yield_q_total": round(proj_yield_kg_acre * area / 100.0, 2),
        "typical_yield_kg_per_acre": prof.yield_kg_per_acre,
        "yield_vs_typical_pct": round(
            100 * (proj_yield_kg_acre - prof.yield_kg_per_acre) / prof.yield_kg_per_acre, 1),
        "crop_health_score": last["health_score"],
        "stage": _stage(progress_of(gdd, gdd_req)),
        "alerts": _twin_alerts(trajectory, prof),
    }


def compare_scenarios(field, farm, soil, days_ahead: int = 60) -> dict[str, Any]:
    """Baseline vs the four interventions the farmer is most likely to consider."""
    prof = get_crop(field.get("crop"))
    scenarios = {
        "baseline": Scenario("baseline", notes="Current plan, no change"),
        "extra_irrigation": Scenario(
            "extra_irrigation", extra_irrigation_mm_per_week=60,
            notes="Add 60 mm/week through the existing system"),
        "drip_upgrade": Scenario(
            "drip_upgrade", extra_irrigation_mm_per_week=45, irrigation_efficiency=0.92,
            notes="Drip at 92% efficiency with 45 mm/week"),
        "full_ipm": Scenario(
            "full_ipm", extra_irrigation_mm_per_week=45, pest_damage_pct=0,
            fertility_index=1.05,
            notes="Full IPM + 5% better nutrition"),
        "heat_wave": Scenario(
            "heat_wave", temp_anomaly_c=3.0,
            notes="A 3 C warmer season (climate-risk stress test)"),
        "dry_spell": Scenario(
            "dry_spell", rain_multiplier=0.35,
            notes="Monsoon failure - only 35% of normal rain"),
    }
    out = {}
    for k, sc in scenarios.items():
        r = simulate(field, farm, soil, days_ahead, sc)
        out[k] = {
            "name": k, "notes": sc.notes,
            "projected_yield_kg_per_acre": r["projected_yield_kg_per_acre"],
            "projected_yield_q_total": r["projected_yield_q_total"],
            "crop_health_score": r["final"]["health_score"],
            "peak_water_stress": r["peak_water_stress"],
            "days_irrigated": r["days_irrigated"],
            "alerts": len(r["alerts"]),
        }
    base = out["baseline"]["projected_yield_q_total"] or 1
    for k, v in out.items():
        v["yield_delta_vs_baseline_pct"] = round(
            100 * (v["projected_yield_q_total"] - base) / base, 1)
    best = max(out.items(), key=lambda kv: kv[1]["projected_yield_q_total"])
    return {"scenarios": out, "best_scenario": best[0],
            "best_yield_gain_pct": best[1]["yield_delta_vs_baseline_pct"]}


def progress_of(gdd: float, gdd_req: float) -> float:
    return min(1.0, gdd / max(gdd_req, 1))


def _stage(p: float) -> str:
    if p < 0.12: return "germination / establishment"
    if p < 0.30: return "vegetative growth"
    if p < 0.50: return "flowering"
    if p < 0.75: return "fruit / grain development"
    if p < 0.92: return "maturity"
    return "senescence / harvest ready"


def _twin_alerts(traj: list[dict], prof) -> list[dict[str, str]]:
    alerts = []
    stressed = [t for t in traj if t["water_stress"] > 0.35]
    if stressed:
        first = stressed[0]["date"]
        alerts.append({"level": "high", "date": first,
                       "message": f"Water stress crosses 35% on {first} during "
                                  f"{prof.critical_stage}. Irrigation before this date protects yield."})
    hot = [t for t in traj if t["temp_max"] > 38]
    if hot:
        alerts.append({"level": "medium", "date": hot[0]["date"],
                       "message": f"{len(hot)} days above 38 C expected - "
                                  f"expect flower drop and reduced grain filling."})
    low_health = [t for t in traj if t["health_score"] < 60]
    if low_health:
        alerts.append({"level": "medium", "date": low_health[0]["date"],
                       "message": f"Crop health score dips below 60 on {low_health[0]['date']}. "
                                  f"Scout the field and re-run disease detection."})
    return alerts


def _parse(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def harvest_window(field: dict, farm: dict, soil: dict | None) -> dict[str, Any]:
    """When should this field be harvested, given the twin and the market?"""
    prof = get_crop(field.get("crop"))
    sim = simulate(field, farm, soil, days_ahead=90)
    if "error" in sim:
        return sim
    traj = sim["trajectory"]
    # harvest when phenological progress passes ~0.95, or the last simulated day
    ready = next((t for t in traj if t["progress_pct"] >= 95), traj[-1])
    ready_date = _parse(ready["date"]) or date.today()
    from .market import mandi_comparison
    rows = mandi_comparison(field["crop"], ready_date.isoformat())
    return {
        "field": field.get("name"), "crop": field["crop"],
        "twin_harvest_date": ready_date.isoformat(),
        "twin_harvest_reason": f"Thermal-time model reaches 95% of the "
                               f"{prof.duration_days}-day requirement" if prof else "",
        "planned_harvest": field.get("expected_harvest"),
        "days_between": (ready_date - _parse(field.get("expected_harvest") or "")).days
                         if field.get("expected_harvest") else None,
        "expected_yield_q": sim["projected_yield_q_total"],
        "market_at_that_date": rows[:3] if rows else [],
        "advice": (f"Harvest on {ready_date.isoformat()}. Shelf life is "
                   f"{prof.shelf_life_days} days, so sell within that window."
                   if prof else ""),
    }
