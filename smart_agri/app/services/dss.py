"""
Decision Support System.

Reads the field, its latest soil test, the farm's weather, the Edge AI disease
history, the yield model, the irrigation/fertilizer engines, the digital twin
and the market module, then produces one ranked list of actions plus a farm
health report and a profit outlook.

This is the module the farmer actually reads: everything else feeds it.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .. import db
from ..agronomy import DISEASE_DB, get_crop
from . import fertilizer as fert_svc
from . import irrigation as irr_svc
from . import market as market_svc
from . import twin as twin_svc
from . import yield_prediction as yp


# ---------------------------------------------------------------------------
# Data assembly helpers
# ---------------------------------------------------------------------------
def latest_soil(field_id: int) -> dict | None:
    return db.query_one(
        "SELECT * FROM soil_readings WHERE field_id=? ORDER BY recorded_at DESC, id DESC LIMIT 1",
        (field_id,))


def farm_weather(farm_id: int, days_back: int = 30, days_forward: int = 7) -> list[dict]:
    lo = (date.today() - timedelta(days=days_back)).isoformat()
    hi = (date.today() + timedelta(days=days_forward)).isoformat()
    return db.query("SELECT * FROM weather_daily WHERE farm_id=? AND date BETWEEN ? AND ? "
                    "ORDER BY date", (farm_id, lo, hi))


def forecast_only(farm_id: int, days: int = 7) -> list[dict]:
    return db.query("SELECT * FROM weather_daily WHERE farm_id=? AND is_forecast=1 "
                    "ORDER BY date LIMIT ?", (farm_id, days))


def farm_fields(farm_id: int) -> list[dict]:
    return db.query("SELECT * FROM fields WHERE farm_id=? ORDER BY name", (farm_id,))


def user_farms(user_id: int) -> list[dict]:
    return db.query("SELECT * FROM farms WHERE user_id=? ORDER BY name", (user_id,))


def field_detections(field_id: int, limit: int = 5) -> list[dict]:
    return db.query("SELECT * FROM disease_reports WHERE field_id=? "
                    "ORDER BY created_at DESC, id DESC LIMIT ?", (field_id, limit))


def recent_spray_count(field_id: int) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM recommendations WHERE field_id=? AND kind='pesticide' "
        "AND status='done' AND created_at >= date('now','-21 days')", (field_id,))
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# Farm health report
# ---------------------------------------------------------------------------
def field_health(field: dict, farm: dict, soil: dict | None,
                 weather: list[dict]) -> dict[str, Any]:
    prof = get_crop(field["crop"])
    scores: dict[str, float] = {}
    notes: dict[str, str] = {}

    # 1. Nutrition
    if prof and soil:
        n_req, p_req, k_req = prof.npk_kg_per_acre
        n_s = min(100, (soil.get("nitrogen") or 0) / max(n_req * 0.7, 1) * 100)
        p_s = min(100, (soil.get("phosphorus") or 0) / max(p_req * 0.7, 1) * 100)
        k_s = min(100, (soil.get("potassium") or 0) / max(k_req * 0.7, 1) * 100)
        scores["nutrition"] = round((n_s + p_s + k_s) / 3, 1)
        notes["nutrition"] = (f"N {soil.get('nitrogen'):.0f} / P {soil.get('phosphorus'):.0f} / "
                              f"K {soil.get('potassium'):.0f} kg/acre against a requirement of "
                              f"{n_req:.0f}/{p_req:.0f}/{k_req:.0f}")
    else:
        scores["nutrition"] = 60.0
        notes["nutrition"] = "No soil test on record - schedule one."

    # 2. Water
    irr = irr_svc.recommend(field, farm, soil, forecast_only(farm["id"], 7))
    scores["water"] = round(100 * (1 - irr["water_stress_index"]), 1)
    notes["water"] = (f"{irr['days_until_irrigation']} day(s) to the next irrigation; "
                      f"weekly demand {irr['weekly_demand_mm']} mm vs "
                      f"{irr['weekly_effective_rain_mm']} mm effective rain")

    # 3. Plant protection
    risk = fert_svc.pest_risk(field, weather[-7:] or [], None, recent_spray_count(field["id"]))
    worst = risk["risks"][0]["risk_score"] if risk["risks"] else 0
    scores["protection"] = round(max(0, 100 - worst), 1)
    notes["protection"] = (f"Top threat: {risk['risks'][0]['threat']} "
                           f"({risk['risks'][0]['risk_score']:.0f}/100)" if risk["risks"]
                           else "No significant pest or disease pressure")

    # 4. Disease history from the Edge AI module
    det = field_detections(field["id"], 3)
    open_disease = [d for d in det if d["disease_class"] in DISEASE_DB
                    and DISEASE_DB[d["disease_class"]].pathogen_type != "none"]
    if open_disease:
        worst_conf = max(d["confidence"] for d in open_disease)
        scores["disease"] = round(max(0, 100 - worst_conf * 70), 1)
        notes["disease"] = (f"{open_disease[0]['disease_name']} detected at "
                            f"{worst_conf*100:.0f}% confidence "
                            f"({open_disease[0]['created_at'][:10]})")
    else:
        scores["disease"] = 100.0
        notes["disease"] = "No disease detected in the last leaf scans"

    # 5. Phenology / vigour from the digital twin
    sim = twin_svc.simulate(field, farm, soil, days_ahead=30)
    scores["vigour"] = sim["final"]["health_score"] if "error" not in sim else 70.0
    notes["vigour"] = (f"LAI {sim['final']['lai']}, NDVI {sim['final']['ndvi']}, "
                       f"stage {sim['stage']}") if "error" not in sim else "Twin unavailable"

    weights = {"nutrition": 0.25, "water": 0.20, "protection": 0.20,
               "disease": 0.20, "vigour": 0.15}
    overall = sum(scores[k] * w for k, w in weights.items())
    return {
        "field_id": field["id"], "field": field["name"], "crop": field["crop"],
        "area_acres": field["area_acres"],
        "overall_score": round(overall, 1),
        "grade": _grade(overall),
        "sub_scores": scores,
        "notes": notes,
        "irrigation": irr,
        "pest_risk": risk,
        "twin_summary": {
            "stage": sim.get("stage"), "lai": sim.get("final", {}).get("lai"),
            "ndvi": sim.get("final", {}).get("ndvi"),
            "projected_yield_kg_per_acre": sim.get("projected_yield_kg_per_acre"),
        },
        "detections": det,
    }


def _grade(score: float) -> str:
    return ("A - excellent" if score >= 85 else "B - good" if score >= 70 else
            "C - needs attention" if score >= 55 else "D - critical")


def farm_health_report(user_id: int, farm_id: int | None = None) -> dict[str, Any]:
    farms = user_farms(user_id)
    if farm_id:
        farms = [f for f in farms if f["id"] == farm_id]
    report = []
    for farm in farms:
        weather = farm_weather(farm["id"])
        fields = []
        for f in farm_fields(farm["id"]):
            fields.append(field_health(f, farm, latest_soil(f["id"]), weather))
        area = sum(f["area_acres"] for f in fields) or 1
        weighted = sum(f["overall_score"] * f["area_acres"] for f in fields) / area
        report.append({
            "farm_id": farm["id"], "farm": farm["name"], "village": farm["village"],
            "district": farm["district"], "total_area": farm["total_area"],
            "soil_type": farm["soil_type"], "irrigation": farm["irrigation"],
            "farm_score": round(weighted, 1), "grade": _grade(weighted),
            "fields": fields,
            "weather_7d": forecast_only(farm["id"], 7),
        })
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "farms": report}


# ---------------------------------------------------------------------------
# Recommended actions
# ---------------------------------------------------------------------------
def actions_for_field(field: dict, farm: dict, health: dict) -> list[dict[str, Any]]:
    acts: list[dict[str, Any]] = []
    prof = get_crop(field["crop"])
    soil = latest_soil(field["id"])
    irr = health["irrigation"]

    if irr["apply_mm"] > 0:
        acts.append({
            "kind": "irrigation", "priority": irr["urgency"],
            "title": f"Irrigate in {irr['days_until_irrigation']} day(s)",
            "detail": (f"Apply {irr['apply_mm']} mm ({irr['litres_per_acre']:,.0f} L/acre) "
                       f"through the {irr['system']} system. Crop is at "
                       f"{irr['growth_stage']} with Kc {irr['kc']}."),
            "score": 40 + (30 if irr["urgency"] == "high" else 10),
        })

    plan = fert_svc.fertilizer_plan(field, soil)
    if plan.get("plan"):
        gap = plan["gap_kg_per_acre"]
        if gap["N"] > 5 or gap["P2O5"] > 5 or gap["K2O"] > 5:
            cost = plan["total_cost_inr"]
            acts.append({
                "kind": "fertilizer",
                "priority": "high" if max(gap.values()) > 15 else "medium",
                "title": "Correct the nutrient gap",
                "detail": (f"Soil test shows a shortfall of N {gap['N']:.0f}, "
                           f"P2O5 {gap['P2O5']:.0f}, K2O {gap['K2O']:.0f} kg/acre. "
                           f"Recommended program costs Rs {cost:,.0f} for "
                           f"{field['area_acres']:.1f} acre."),
                "score": 30 + min(30, max(gap.values())),
            })
        for w in plan.get("warnings", []):
            acts.append({"kind": "fertilizer", "priority": "medium",
                         "title": "Soil correction", "detail": w, "score": 22})

    risk = health["pest_risk"]
    for r in risk["risks"][:2]:
        if r["risk_score"] >= 55:
            acts.append({
                "kind": "pesticide",
                "priority": "high" if r["risk_score"] >= 70 else "medium",
                "title": f"{r['threat']} risk {r['risk_score']:.0f}/100",
                "detail": f"{r['driver']}. {r['action']} "
                          f"{risk['spray_window']['note']}",
                "score": r["risk_score"] * 0.5,
            })

    for d in health["detections"]:
        info = DISEASE_DB.get(d["disease_class"])
        if info and info.pathogen_type != "none" and d["confidence"] >= 0.5:
            acts.append({
                "kind": "pesticide", "priority": "high" if info.severity_weight >= 0.8 else "medium",
                "title": f"Treat {info.display_name} ({d['confidence']*100:.0f}% confidence)",
                "detail": info.management[0] + (" " + info.management[1] if len(info.management) > 1 else ""),
                "score": 35 + info.severity_weight * 40,
            })

    if prof:
        harvest = field.get("expected_harvest")
        if harvest:
            try:
                days = (datetime.strptime(harvest, "%Y-%m-%d").date() - date.today()).days
            except ValueError:
                days = 999
            if 0 <= days <= 45:
                best = market_svc.best_mandi(field["crop"], harvest)
                if best:
                    acts.append({
                        "kind": "market", "priority": "high" if days <= 21 else "medium",
                        "title": f"Harvest in {days} days - lock in {best['mandi']}",
                        "detail": (f"Net realisation Rs {best['net_after_transit_loss_inr_q']:,.0f}/q "
                                   f"after {best['commission_pct']}% commission and "
                                   f"Rs {best['transport_inr_per_q']}/q transport "
                                   f"({best['distance_km']} km). Trend: {best['trend']}."),
                        "score": 45 if days <= 21 else 30,
                    })
                dem = market_svc.demand_outlook(field["crop"])
                if dem.get("glut_risk") == "high":
                    acts.append({
                        "kind": "market", "priority": "high",
                        "title": "Market is glutted - stagger your sale",
                        "detail": dem["interpretation"] + " " + dem["recommended_action"],
                        "score": 42,
                    })

    if soil and soil.get("organic_carbon") is not None and soil["organic_carbon"] < 0.4:
        acts.append({"kind": "agronomy", "priority": "medium",
                     "title": "Build soil organic carbon",
                     "detail": (f"OC is {soil['organic_carbon']:.2f}%. Add 4-6 t/acre FYM or "
                                f"grow a sunhemp green-manure crop before the next sowing."),
                     "score": 20})

    acts.sort(key=lambda a: a["score"], reverse=True)
    for a in acts:
        a["priority"] = a.get("priority") or "medium"
    return acts


def persist_actions(user_id: int, field: dict, actions: list[dict]) -> None:
    """Store open actions so the farmer can tick them off; skip duplicates."""
    for a in actions[:6]:
        dup = db.query_one(
            "SELECT id FROM recommendations WHERE field_id=? AND title=? AND status='open'",
            (field["id"], a["title"]))
        if dup:
            continue
        db.execute(
            "INSERT INTO recommendations (user_id, field_id, kind, title, detail, priority) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, field["id"], a["kind"], a["title"], a["detail"], a["priority"]))


def decision_pack(user_id: int, farm_id: int) -> dict[str, Any]:
    """The full Decision Support System output for one farm."""
    report = farm_health_report(user_id, farm_id)
    if not report["farms"]:
        return {"error": "no farm found"}
    farm_report = report["farms"][0]

    all_actions = []
    for f in farm_report["fields"]:
        acts = actions_for_field(
            {"id": f["field_id"], "name": f["field"], "crop": f["crop"],
             "area_acres": f["area_acres"],
             "expected_harvest": next((x["expected_harvest"] for x in
                                       farm_fields(farm_report["farm_id"])
                                       if x["id"] == f["field_id"]), None)},
            {"id": farm_report["farm_id"], "irrigation": farm_report["irrigation"],
             "soil_type": farm_report["soil_type"]},
            f)
        for a in acts:
            a["field"] = f["field"]
            a["field_id"] = f["field_id"]
            a["crop"] = f["crop"]
        all_actions.extend(acts)
        persist_actions(user_id, {"id": f["field_id"]}, acts)

    all_actions.sort(key=lambda a: a["score"], reverse=True)

    # Profit outlook per field
    outlook = []
    total_profit = 0.0
    for f in farm_report["fields"]:
        prof = get_crop(f["crop"])
        if not prof:
            continue
        sim = twin_svc.simulate(
            {"id": f["field_id"], "name": f["field"], "crop": f["crop"],
             "area_acres": f["area_acres"],
             "sowing_date": next((x["sowing_date"] for x in farm_fields(farm_report["farm_id"])
                                  if x["id"] == f["field_id"]), None),
             "expected_harvest": None},
            {"id": farm_report["farm_id"], "soil_type": farm_report["soil_type"],
             "irrigation": farm_report["irrigation"]},
            latest_soil(f["field_id"]), days_ahead=60)
        yield_q = sim["projected_yield_q_total"] if "error" not in sim else \
            prof.yield_kg_per_acre * f["area_acres"] / 100.0
        harvest = next((x["expected_harvest"] for x in farm_fields(farm_report["farm_id"])
                        if x["id"] == f["field_id"]), None)
        profit = market_svc.estimate_profit(f["crop"], f["area_acres"], yield_q, None)
        if "error" in profit:
            continue
        profit["field"] = f["field"]
        profit["health_score"] = f["overall_score"]
        outlook.append(profit)
        total_profit += profit["net_profit_inr"]

    outlook.sort(key=lambda p: p["net_profit_inr"], reverse=True)

    return {
        "generated_at": report["generated_at"],
        "farm": {k: v for k, v in farm_report.items() if k != "fields"},
        "farm_score": farm_report["farm_score"],
        "grade": farm_report["grade"],
        "fields": [{k: v for k, v in f.items()
                    if k not in ("irrigation", "pest_risk", "twin_summary", "detections")}
                   for f in farm_report["fields"]],
        "actions": all_actions[:12],
        "action_counts": {k: sum(1 for a in all_actions if a["kind"] == k)
                          for k in ("irrigation", "fertilizer", "pesticide", "market", "agronomy")},
        "profit_outlook": outlook,
        "total_expected_profit_inr": round(total_profit, 0),
        "expected_yield_q": round(sum(o["yield_q"] for o in outlook), 2),
        "best_mandis": sorted({o["mandi"] for o in outlook if o.get("mandi")}),
        "model_status": {
            "disease_cnn": _disease_status(),
            "yield_model": {"available": yp.model_available(), "metrics": yp.model_metrics()},
            "price_model": {"available": market_svc.model_available(),
                            "metrics": market_svc.model_metrics()},
        },
    }


def _disease_status() -> dict:
    from .disease import MODEL
    return {"available": MODEL.available, "backend": MODEL.backend,
            "classes": len(MODEL.class_names),
            "test_accuracy": MODEL.meta.get("test_accuracy")}


def open_recommendations(user_id: int) -> list[dict]:
    return db.query(
        "SELECT r.*, f.name AS field_name, f.crop FROM recommendations r "
        "LEFT JOIN fields f ON f.id = r.field_id "
        "WHERE r.user_id=? AND r.status='open' ORDER BY r.created_at DESC, r.id DESC LIMIT 40",
        (user_id,))
