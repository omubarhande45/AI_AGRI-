"""
AI/ML Prediction module - fertilizer & pesticide recommendation.

Fertilizer: balances soil-test NPK against the crop's demand, converts the gap
into real commercial products (Urea, DAP, MOP, 19:19:19, FYM, micronutrients)
with dose in kg/acre, splits it across the growth stages, and prices it.

Pesticide: scores pest/disease risk from the crop's known threats, the detected
disease (from the Edge AI module), recent weather (humidity/temperature drive
fungal pressure) and recent spray history.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..agronomy import DISEASE_DB, get_crop

# product -> (% N, % P2O5, % K2O, INR per kg)
PRODUCTS = {
    "Urea":          (46.0, 0.0, 0.0, 6.0),
    "DAP":           (18.0, 46.0, 0.0, 32.0),
    "MOP":           (0.0, 0.0, 60.0, 34.0),
    "10:26:26":      (10.0, 26.0, 26.0, 30.0),
    "19:19:19":      (19.0, 19.0, 19.0, 42.0),
    "SSP":           (0.0, 16.0, 0.0, 14.0),
    "FYM (tonne)":   (5.0, 2.5, 5.0, 2200.0),   # per tonne, not per kg
    "Zinc sulphate": (0.0, 0.0, 0.0, 55.0),
    "Boron":         (0.0, 0.0, 0.0, 180.0),
}


def fertilizer_plan(field: dict, soil: dict | None, area: float | None = None) -> dict[str, Any]:
    prof = get_crop(field.get("crop"))
    if prof is None:
        return {"error": f"unknown crop: {field.get('crop')}"}
    area = float(area if area is not None else field.get("area_acres") or 1.0)
    n_req, p_req, k_req = prof.npk_kg_per_acre

    soil = soil or {}
    have_n = float(soil.get("nitrogen") or 0)
    have_p = float(soil.get("phosphorus") or 0)
    have_k = float(soil.get("potassium") or 0)
    ph = float(soil.get("ph") or 7.0)
    oc = float(soil.get("organic_carbon") or 0.5)

    # Soil-test credit: what is already in the root zone (kg/acre).
    credit_n = min(have_n * 0.35, n_req * 0.45)
    credit_p = min(have_p * 0.40, p_req * 0.50)
    credit_k = min(have_k * 0.40, k_req * 0.50)
    need_n = max(0.0, n_req - credit_n)
    need_p = max(0.0, p_req - credit_p)
    need_k = max(0.0, k_req - credit_k)

    plan: list[dict[str, Any]] = []
    remaining_n, remaining_p, remaining_k = need_n, need_p, need_k

    # 1. Basal phosphorus from DAP (also supplies some N).
    if remaining_p > 0:
        dap = remaining_p / 0.46
        plan.append(_product("DAP", dap, area, "Basal", "Apply at sowing / after pruning, incorporate 10-15 cm deep"))
        remaining_p -= dap * 0.46
        remaining_n -= dap * 0.18

    # 2. Potash from MOP.
    if remaining_k > 0:
        mop = remaining_k / 0.60
        plan.append(_product("MOP", mop, area, "Basal",
                             "Apply with DAP; avoid on chloride-sensitive grape in sandy soil"))
        remaining_k = 0.0

    # 3. Organic carbon builder.
    if oc < 0.5:
        fym = max(2.0, round((0.6 - oc) * 12, 1))
        plan.append(_product("FYM (tonne)", fym, area, "Basal",
                             f"Soil OC is {oc:.2f}% - well-rotted FYM improves water holding and CEC"))
        remaining_n = max(0.0, remaining_n - fym * 5)

    # 4. Remaining nitrogen as split urea doses.
    if remaining_n > 0:
        splits = _n_splits(field.get("crop"), remaining_n)
        for stage, kg in splits:
            plan.append(_product("Urea", kg / 0.46, area, stage,
                                 "Apply on moist soil, irrigate the same day to limit volatilisation"))

    # 5. Micronutrients for pH-sensitive situations.
    if ph > 7.8:
        plan.append(_product("Zinc sulphate", 8.0, area, "Basal",
                             f"pH {ph:.2f} locks up zinc - foliar ZnSO4 0.5% is the faster fix"))
        plan.append(_product("Boron", 2.0, area, "Basal",
                             "Alkaline soil induces boron deficiency; critical for fruit set"))

    total_cost = round(sum(p["cost_inr"] for p in plan), 0)
    return {
        "crop": field.get("crop"),
        "area_acres": area,
        "soil_test": {"nitrogen": have_n, "phosphorus": have_p, "potassium": have_k,
                      "ph": ph, "organic_carbon": oc},
        "crop_requirement_kg_per_acre": {"N": n_req, "P2O5": p_req, "K2O": k_req},
        "soil_credit_kg_per_acre": {"N": round(credit_n, 1), "P2O5": round(credit_p, 1),
                                    "K2O": round(credit_k, 1)},
        "gap_kg_per_acre": {"N": round(need_n, 1), "P2O5": round(need_p, 1),
                            "K2O": round(need_k, 1)},
        "plan": plan,
        "total_cost_inr": total_cost,
        "cost_per_acre_inr": round(total_cost / max(area, 0.1), 0),
        "warnings": _fert_warnings(ph, oc, plan),
    }


def _product(name: str, kg_per_acre: float, area: float, stage: str, note: str) -> dict[str, Any]:
    n, p, k, price = PRODUCTS[name]
    unit = "tonne/acre" if "tonne" in name else "kg/acre"
    kg_per_acre = round(kg_per_acre, 1)
    total = kg_per_acre * area
    return {
        "product": name, "stage": stage,
        "dose_per_acre": kg_per_acre, "unit": unit,
        "total_for_field": round(total, 1), "total_unit": unit.split("/")[0],
        "nutrient": "NPK" if (n and p and k) else "N" if n else "P" if p else "K" if k else "Micro",
        "nutrients_supplied_kg_per_acre": {"N": round(n / 100 * kg_per_acre * (1000 if "tonne" in name else 1), 1),
                                           "P2O5": round(p / 100 * kg_per_acre * (1000 if "tonne" in name else 1), 1),
                                           "K2O": round(k / 100 * kg_per_acre * (1000 if "tonne" in name else 1), 1)},
        "rate_inr_per_kg": price,
        "cost_inr": round(total * price, 0),
        "note": note,
    }


def _n_splits(crop: str | None, total_n: float) -> list[tuple[str, float]]:
    if (crop or "").lower() in {"grape", "pomegranate", "banana", "sugarcane"}:
        return [("Basal", total_n * 0.25), ("Active growth", total_n * 0.25),
                ("Fruit/bunch development", total_n * 0.30), ("Maturity", total_n * 0.20)]
    return [("Basal", total_n * 0.33), ("Tillering / vegetative", total_n * 0.33),
            ("Flowering / grain filling", total_n * 0.34)]


def _fert_warnings(ph: float, oc: float, plan: list) -> list[str]:
    w = []
    if ph > 8.2:
        w.append(f"pH {ph:.2f} is strongly alkaline - apply gypsum 200 kg/acre and grow a green-manure crop.")
    elif ph < 6.0:
        w.append(f"pH {ph:.2f} is acidic - apply agricultural lime 400 kg/acre before the next sowing.")
    if oc < 0.4:
        w.append("Organic carbon below 0.4% - prioritise residue retention and FYM over chemical N.")
    if any(p["product"] == "Urea" for p in plan) and len(plan) > 3:
        w.append("Split urea into at least 3 doses; a single heavy dose loses 30-40% to leaching and volatilisation.")
    return w


# ---------------------------------------------------------------------------
# Pesticide / plant protection risk
# ---------------------------------------------------------------------------
def pest_risk(field: dict, weather_recent: list[dict],
              detection: dict[str, Any] | None = None,
              recent_sprays: int = 0) -> dict[str, Any]:
    prof = get_crop(field.get("crop"))
    risks: list[dict[str, Any]] = []

    if not weather_recent:
        weather_recent = [{"humidity": 55, "temp_max": 32, "rainfall_mm": 0}]
    rh = sum(w.get("humidity", 55) for w in weather_recent) / len(weather_recent)
    tmax = sum(w.get("temp_max", 32) for w in weather_recent) / len(weather_recent)
    rain = sum(w.get("rainfall_mm", 0) for w in weather_recent) / len(weather_recent)

    def score(base: float, likes: tuple[str, ...]) -> float:
        s = base
        if "humid" in likes and rh > 70: s += 25
        if "humid" in likes and rh < 45: s -= 15
        if "hot" in likes and tmax > 33: s += 20
        if "hot" in likes and tmax < 26: s -= 12
        if "wet" in likes and rain > 3: s += 20
        if "dry" in likes and rh < 50: s += 18
        return min(98, max(3, s))

    threats = {
        "Tomato": [("Fruit borer", 45, ("hot",)), ("Whitefly", 50, ("hot", "dry")),
                   ("Leaf miner", 35, ("hot",)), ("Two-spotted spider mite", 40, ("hot", "dry")),
                   ("Early blight", 40, ("humid", "wet")), ("Late blight", 35, ("humid", "wet")),
                   ("Powdery mildew", 30, ("dry",))],
        "Grape": [("Thrips", 55, ("hot", "dry")), ("Mealybug", 40, ("dry",)),
                  ("Powdery mildew", 55, ("humid",)), ("Downy mildew", 50, ("humid", "wet")),
                  ("Anthracnose", 45, ("wet",))],
        "Onion": [("Thrips", 60, ("hot", "dry")), ("Purple blotch", 45, ("humid", "wet")),
                  ("Downy mildew", 35, ("humid",))],
        "Maize": [("Fall armyworm", 55, ("humid",)), ("Stem borer", 40, ("hot",)),
                  ("Common rust", 35, ("humid",)), ("Northern leaf blight", 30, ("humid", "wet"))],
        "Potato": [("Aphid", 45, ("humid",)), ("Potato tuber moth", 40, ("hot", "dry")),
                   ("Late blight", 50, ("humid", "wet")), ("Early blight", 40, ("hot",))],
        "Sugarcane": [("Early shoot borer", 40, ("hot",)), ("Pyrilla", 45, ("humid",)),
                      ("Red rot", 30, ("wet",))],
        "Cotton": [("Pink bollworm", 55, ("humid",)), ("Whitefly", 55, ("hot", "dry")),
                   ("Jassid", 40, ("hot",))],
        "Pomegranate": [("Fruit borer", 50, ("hot",)), ("Thrips", 45, ("hot", "dry")),
                        ("Anthracnose", 40, ("wet",))],
        "Banana": [("Banana pseudostem weevil", 40, ("humid",)), ("Banana aphid", 45, ("humid",)),
                   ("Sigatoka leaf spot", 50, ("humid", "wet"))],
    }

    for name, base, likes in threats.get(field.get("crop", ""), []):
        s = score(base, likes)
        risks.append({"threat": name, "type": "pest", "risk_score": round(s, 1),
                      "driver": _driver(likes, rh, tmax, rain)})

    # Fungal pressure index from the disease DB for this crop
    for cls, info in DISEASE_DB.items():
        if info.crop != field.get("crop") or info.pathogen_type == "none":
            continue
        base = 30 + info.severity_weight * 20
        likes = ("humid", "wet") if info.pathogen_type == "fungal" else ("humid",)
        risks.append({"threat": info.display_name, "type": "disease",
                      "risk_score": round(score(base, likes), 1),
                      "driver": _driver(likes, rh, tmax, rain)})

    # Boost anything the Edge AI module actually saw in a leaf photo.
    if detection and not detection.get("is_healthy"):
        seen = detection["top"]["disease"]
        for r in risks:
            if r["threat"].lower() in seen.lower() or seen.lower() in r["threat"].lower():
                r["risk_score"] = min(99, r["risk_score"] + 35)
                r["confirmed_by_image"] = True
                r["confidence"] = detection["top"]["confidence"]

    if recent_sprays:
        for r in risks:
            r["risk_score"] = max(2, r["risk_score"] - min(20, recent_sprays * 7))

    risks.sort(key=lambda r: r["risk_score"], reverse=True)
    top = risks[:5]
    for r in top:
        r["action"] = _action(r["threat"], r["risk_score"], field.get("crop"))
        r["level"] = ("high" if r["risk_score"] >= 65 else
                      "moderate" if r["risk_score"] >= 40 else "low")

    return {
        "crop": field.get("crop"),
        "window_days": len(weather_recent),
        "avg_humidity_pct": round(rh, 1),
        "avg_temp_max_c": round(tmax, 1),
        "avg_rainfall_mm": round(rain, 1),
        "recent_sprays": recent_sprays,
        "risks": top,
        "spray_window": _spray_window(weather_recent),
    }


def _driver(likes, rh, tmax, rain) -> str:
    parts = []
    if "humid" in likes and rh > 70: parts.append(f"humidity {rh:.0f}%")
    if "hot" in likes and tmax > 33: parts.append(f"max temp {tmax:.0f} C")
    if "dry" in likes and rh < 50: parts.append(f"dry air {rh:.0f}% RH")
    if "wet" in likes and rain > 3: parts.append(f"rain {rain:.1f} mm/day")
    return "Favourable: " + ", ".join(parts) if parts else "No strong weather driver"


def _action(threat: str, score: float, crop: str | None) -> str:
    if score >= 65:
        base = "Act within 48 h: "
    elif score >= 40:
        base = "Monitor weekly and be ready to spray: "
    else:
        base = "Keep under observation: "
    t = threat.lower()
    if "blight" in t:
        return base + "cymoxanil + mancozeb 3 g/L, repeat in 7 days if rain continues."
    if "mildew" in t:
        return base + "wettable sulphur 2 g/L (evening) or hexaconazole 1 ml/L."
    if "rust" in t:
        return base + "propiconazole 1 ml/L or mancozeb 2.5 g/L."
    if "spot" in t or "scab" in t or "rot" in t:
        return base + "mancozeb 2.5 g/L or copper oxychloride 3 g/L; remove infected leaves."
    if "armyworm" in t or "borer" in t:
        return base + "pheromone traps 5/acre + emamectin benzoate 0.4 g/L on fresh damage."
    if "whitefly" in t or "aphid" in t or "jassid" in t or "thrips" in t:
        return base + "yellow/blue sticky traps 10/acre + spinetoram 0.3 ml/L or neem oil 5 ml/L."
    if "mite" in t:
        return base + "spiromesifen 1 ml/L; raise humidity and remove border weeds."
    if "virus" in t or "curl" in t or "mosaic" in t:
        return base + "no cure - rogue infected plants and control the insect vector."
    if "mealybug" in t:
        return base + "chlorpyriphos drench on trunk base + release Cryptolaemus predators."
    return base + "IPM spray as per the crop schedule; rotate modes of action."


def _spray_window(forecast: list[dict]) -> dict[str, Any]:
    """Find a 6-hour dry window - spraying before rain wastes money."""
    for i, w in enumerate(forecast[:7]):
        if w.get("rainfall_mm", 0) < 1.0:
            return {"safe": True, "days_from_today": i,
                    "date": w.get("date"),
                    "note": "Low rain probability - spray in the early morning or after 4 pm."}
    return {"safe": False, "days_from_today": None, "date": None,
            "note": "Rain expected every day for a week - use a rainfast systemic or wait."}
