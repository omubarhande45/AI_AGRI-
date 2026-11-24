"""
REST API.

These endpoints are what a Raspberry Pi / Android edge client, a drone, or a
third-party app would call. They return JSON and are session-independent where
it makes sense, so the same backend serves the web UI and the field devices.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, session

from .. import db
from ..agronomy import DISEASE_DB, REGIONAL_CLASSES, get_crop
from ..services import dss, fertilizer as fert_svc, irrigation as irr_svc
from ..services import market as market_svc, twin as twin_svc
from ..services import yield_prediction as yp
from ..services.disease import MODEL, detect_from_upload, encode_png

bp = Blueprint("api", __name__)


@bp.route("/status")
def status():
    return jsonify({
        "system": "AI-Powered Smart Agriculture System",
        "modules": {
            "edge_ai": {"available": MODEL.available, "backend": MODEL.backend,
                        "classes": len(MODEL.class_names),
                        "test_accuracy": MODEL.meta.get("test_accuracy"),
                        "test_macro_f1": MODEL.meta.get("test_macro_f1")},
            "yield_model": {"available": yp.model_available(), "metrics": yp.model_metrics()},
            "price_model": {"available": market_svc.model_available(),
                            "metrics": market_svc.model_metrics()},
            "digital_twin": {"available": True, "engine": "thermal-time + soil water balance"},
        },
        "database": {t: db.table_count(t) for t in
                     ("users", "farms", "fields", "soil_readings", "weather_daily",
                      "market_prices", "disease_reports", "recommendations")},
    })


@bp.route("/disease/detect", methods=["POST"])
def detect():
    """POST a leaf photo (multipart field 'image') -> top-k disease predictions."""
    if not MODEL.available:
        return jsonify({"error": "disease model not trained"}), 503
    f = request.files.get("image")
    if not f:
        return jsonify({"error": "send a multipart file under the field name 'image'"}), 400
    try:
        result, bgr = detect_from_upload(f.stream)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    cam = MODEL.gradcam(__import__("cv2").cvtColor(bgr, __import__("cv2").COLOR_BGR2RGB))
    payload = {
        "prediction": result["top"],
        "is_healthy": result["is_healthy"],
        "confident": result["confident"],
        "top_k": result["predictions"],
        "backend": result["backend"],
        "model_accuracy": result["model_accuracy"],
        "gradcam_png": encode_png(cam) if cam is not None else None,
    }
    if session.get("user"):
        payload["report_id"] = db.execute(
            """INSERT INTO disease_reports (user_id, crop, disease_class, disease_name,
               confidence, severity, advice, source) VALUES (?,?,?,?,?,?,?,?)""",
            (session["user"]["id"], result["top"]["crop"], result["top"]["class"],
             result["top"]["disease"], result["top"]["confidence"], result["top"]["severity"],
             "; ".join(result["top"]["management"][:2]), f"api_{result['backend']}"))
    return jsonify(payload)


@bp.route("/disease/classes")
def disease_classes():
    return jsonify({
        "total": len(DISEASE_DB),
        "regional": list(REGIONAL_CLASSES),
        "classes": {k: {"crop": v.crop, "name": v.display_name,
                        "pathogen": v.pathogen_type,
                        "yield_loss_pct": v.yield_loss_pct,
                        "spread_risk": v.spread_risk,
                        "symptoms": v.symptoms,
                        "management": list(v.management),
                        "organic": v.organic}
                    for k, v in DISEASE_DB.items()},
    })


@bp.route("/yield/predict", methods=["GET", "POST"])
def predict_yield_api():
    payload = request.get_json(silent=True) if request.method == "POST" else request.args.to_dict()
    if not payload.get("crop"):
        return jsonify({"error": "crop is required"}), 400
    return jsonify(yp.predict_yield(payload))


@bp.route("/field/<int:field_id>/irrigation")
def irrigation_api(field_id: int):
    f = db.query_one("SELECT * FROM fields WHERE id=?", (field_id,))
    if not f:
        return jsonify({"error": "field not found"}), 404
    farm = db.query_one("SELECT * FROM farms WHERE id=?", (f["farm_id"],))
    soil = dss.latest_soil(field_id)
    return jsonify(irr_svc.recommend(f, farm, soil, dss.forecast_only(farm["id"], 7)))


@bp.route("/field/<int:field_id>/fertilizer")
def fertilizer_api(field_id: int):
    f = db.query_one("SELECT * FROM fields WHERE id=?", (field_id,))
    if not f:
        return jsonify({"error": "field not found"}), 404
    return jsonify(fert_svc.fertilizer_plan(f, dss.latest_soil(field_id)))


@bp.route("/field/<int:field_id>/pest-risk")
def pest_api(field_id: int):
    f = db.query_one("SELECT * FROM fields WHERE id=?", (field_id,))
    if not f:
        return jsonify({"error": "field not found"}), 404
    farm = db.query_one("SELECT * FROM farms WHERE id=?", (f["farm_id"],))
    weather = dss.farm_weather(farm["id"])[-7:]
    return jsonify(fert_svc.pest_risk(f, weather, None, dss.recent_spray_count(field_id)))


@bp.route("/field/<int:field_id>/twin")
def twin_api(field_id: int):
    f = db.query_one("SELECT * FROM fields WHERE id=?", (field_id,))
    if not f:
        return jsonify({"error": "field not found"}), 404
    farm = db.query_one("SELECT * FROM farms WHERE id=?", (f["farm_id"],))
    days = min(int(request.args.get("days", 60)), 180)
    scenario = request.args.get("scenario", "baseline")
    presets = {
        "baseline": twin_svc.Scenario("baseline"),
        "extra_irrigation": twin_svc.Scenario("extra_irrigation",
                                              extra_irrigation_mm_per_week=60),
        "drip_upgrade": twin_svc.Scenario("drip_upgrade", extra_irrigation_mm_per_week=45,
                                          irrigation_efficiency=0.92),
        "heat_wave": twin_svc.Scenario("heat_wave", temp_anomaly_c=3.0),
        "dry_spell": twin_svc.Scenario("dry_spell", rain_multiplier=0.35),
    }
    sim = twin_svc.simulate(f, farm, dss.latest_soil(field_id), days_ahead=days,
                            scenario=presets.get(scenario, presets["baseline"]))
    if request.args.get("trajectory") != "1":
        sim.pop("trajectory", None)
    return jsonify(sim)


@bp.route("/market/prices")
def prices_api():
    crop = request.args.get("crop")
    if not crop:
        return jsonify({"error": "crop is required"}), 400
    days = min(int(request.args.get("days", 180)), 400)
    return jsonify({"crop": crop, "history": market_svc.price_history(crop, None, days)})


@bp.route("/market/forecast")
def forecast_api():
    crop = request.args.get("crop")
    mandi = request.args.get("mandi")
    if not crop or not mandi:
        return jsonify({"error": "crop and mandi are required"}), 400
    horizon = min(int(request.args.get("horizon", 90)), 180)
    return jsonify(market_svc.price_forecast(crop, mandi, horizon))


@bp.route("/market/mandis")
def mandis_api():
    crop = request.args.get("crop")
    if not crop:
        return jsonify({"error": "crop is required"}), 400
    return jsonify({"crop": crop, "harvest_date": request.args.get("harvest"),
                    "mandis": market_svc.mandi_comparison(crop, request.args.get("harvest"))})


@bp.route("/market/demand")
def demand_api():
    crop = request.args.get("crop")
    if not crop:
        return jsonify({"error": "crop is required"}), 400
    return jsonify(market_svc.demand_outlook(crop))


@bp.route("/market/profit")
def profit_api():
    try:
        crop = request.args.get("crop")
        area = float(request.args.get("area", 1))
        yield_q = float(request.args.get("yield_q", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "area and yield_q must be numbers"}), 400
    if not crop:
        return jsonify({"error": "crop is required"}), 400
    if not yield_q:
        prof = get_crop(crop)
        if prof is None:
            return jsonify({"error": "unknown crop"}), 400
        yield_q = prof.yield_kg_per_acre * area / 100.0
    return jsonify(market_svc.estimate_profit(crop, area, yield_q,
                                              request.args.get("mandi")))


@bp.route("/farm/<int:farm_id>/report")
def report_api(farm_id: int):
    if not session.get("user"):
        return jsonify({"error": "log in to get a farm report"}), 401
    return jsonify(dss.decision_pack(session["user"]["id"], farm_id))


@bp.route("/weather/<int:farm_id>")
def weather_api(farm_id: int):
    days = min(int(request.args.get("days", 30)), 400)
    rows = dss.farm_weather(farm_id, days_back=days, days_forward=7)
    return jsonify({"farm_id": farm_id,
                    "history": [r for r in rows if not r["is_forecast"]],
                    "forecast": [r for r in rows if r["is_forecast"]]})


@bp.route("/twin/sectors/<int:field_id>")
def sectors_api(field_id: int):
    from ..services import sectors as sector_svc
    return jsonify({"field_id": field_id, "sectors": sector_svc.ensure_sectors(field_id)})


@bp.route("/twin/simulate", methods=["POST"])
def twin_simulate():
    """In-silico forecast: perturb the digital twin (pathogen pressure, extra
    irrigation, fungicide programme) and return the divergence."""
    from ..services import sectors as sector_svc
    data = request.get_json(silent=True) or request.form
    field_id = int(data.get("field_id") or 0)
    field = db.query_one("SELECT * FROM fields WHERE id=?", (field_id,))
    if not field:
        return jsonify({"error": "unknown field"}), 400
    farm = db.query_one("SELECT * FROM farms WHERE id=?", (field["farm_id"],))
    soil = dss.latest_soil(field_id)

    pathogen = max(0.0, min(40.0, float(data.get("pathogen_delta") or 0)))
    irrig = max(0.0, min(120.0, float(data.get("irrigation_delta") or 0)))
    fungicide = str(data.get("fungicide") or "") in ("1", "true", "on", "True")

    pest = pathogen * (0.35 if fungicide else 1.0)
    sc = twin_svc.Scenario(
        "insilico", extra_irrigation_mm_per_week=irrig, pest_damage_pct=pest,
        notes=f"pathogen +{pathogen:.0f}, irrigation +{irrig:.0f} mm/wk, "
              f"fungicide {'on' if fungicide else 'off'}")
    base = twin_svc.simulate(field, farm, soil, days_ahead=45)
    r = twin_svc.simulate(field, farm, soil, days_ahead=45, scenario=sc)
    recovery = r["final"]["health_score"]
    sector_svc.log_sim_run(field_id, {"pathogen_delta": pathogen,
                                      "irrigation_delta": irrig,
                                      "fungicide": fungicide},
                           recovery, r["projected_yield_q_total"], recovery)
    return jsonify({
        "recovery": recovery,
        "yield_q": r["projected_yield_q_total"],
        "yield_kg_per_acre": r["projected_yield_kg_per_acre"],
        "peak_water_stress": r["peak_water_stress"],
        "baseline_health": base["final"]["health_score"],
        "baseline_yield_q": base["projected_yield_q_total"],
        "delta_health": round(recovery - base["final"]["health_score"], 1),
        "delta_yield_q": round(r["projected_yield_q_total"] -
                               base["projected_yield_q_total"], 2),
        "alerts": len(r["alerts"]),
    })
