"""Page routes - the farmer-facing AgriSmartAI dashboard."""
from __future__ import annotations

import functools
import os
import time
from datetime import date, datetime, timedelta

import numpy as np
from flask import (Blueprint, abort, current_app, flash, redirect, request,
                   render_template, send_from_directory, session, url_for)
from werkzeug.utils import secure_filename

from .. import db
from ..agronomy import CROPS, CROP_NAMES, DISEASE_DB, REGIONAL_CLASSES, get_crop
from ..config import MANDIS, UPLOAD_DIR
from ..services import dss, fertilizer as fert_svc, irrigation as irr_svc
from ..services import market as market_svc, sectors as sector_svc
from ..services import twin as twin_svc, pdf_reports as pdf_svc
from ..services import yield_prediction as yp
from ..services.disease import MODEL, detect_from_upload, encode_png

bp = Blueprint("main", __name__)


def login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def _farm():
    uid = session["user"]["id"]
    fid = session.get("farm_id")
    farms = dss.user_farms(uid)
    farm = next((f for f in farms if f["id"] == fid), farms[0] if farms else None)
    return farm, farms


def _field_or_404(field_id: int, farm_id: int) -> dict:
    f = db.query_one("SELECT * FROM fields WHERE id=? AND farm_id=?", (field_id, farm_id))
    if not f:
        abort(404)
    return f


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
STAGE_DEFS = [
    ("Nursery & Rooting", 0.00, 0.12, "Completed"),
    ("Vegetative", 0.12, 0.35, "Completed"),
    ("Flowering / Fruit Set", 0.35, 0.62, "In Active Growth"),
    ("Ripening & Harvest", 0.62, 1.00, "Projected"),
]


def _stages(field, prof):
    """Growth-stage timeline chips from the real sowing date."""
    sowing = None
    if field.get("sowing_date"):
        try:
            sowing = datetime.strptime(field["sowing_date"], "%Y-%m-%d").date()
        except ValueError:
            sowing = None
    duration = prof.duration_days if prof else 120
    if sowing is None and field.get("expected_harvest"):
        try:
            sowing = datetime.strptime(field["expected_harvest"], "%Y-%m-%d").date() \
                - timedelta(days=duration)
        except ValueError:
            sowing = date.today() - timedelta(days=int(duration * 0.45))
    if sowing is None:
        sowing = date.today() - timedelta(days=int(duration * 0.45))
    now_frac = max(0.0, min(1.0, (date.today() - sowing).days / max(duration, 1)))
    out = []
    for name, lo, hi, tag in STAGE_DEFS:
        start = sowing + timedelta(days=int(lo * duration))
        if now_frac >= hi:
            state, sub = "done", "Completed"
        elif now_frac >= lo:
            state, sub = "now", "In Active Growth"
        else:
            state, sub = "future", "Projected: %s" % start.strftime("%b %d")
        out.append({"name": name, "state": state,
                    "days": "Stage %d · %s" % (len(out) + 1, start.strftime("%b %d")),
                    "sub": sub})
    return out, now_frac


@bp.route("/")
@login_required
def dashboard():
    farm, farms = _farm()
    if not farm:
        flash("Add your first farm to get started.", "info")
        return redirect(url_for("main.add_farm"))

    fields = dss.farm_fields(farm["id"])
    weather = dss.farm_weather(farm["id"])
    forecast = dss.forecast_only(farm["id"], 7)

    primary = next((f for f in fields if f["status"] == "growing"), fields[0] if fields else None)
    soil = dss.latest_soil(primary["id"]) if primary else None
    health = dss.field_health(primary, farm, soil, weather) if primary else None
    yield_pred = _yield_for(primary, farm, soil, weather) if primary else None
    sim = twin_svc.simulate(primary, farm, soil, days_ahead=60) if primary else None
    prof = get_crop(primary["crop"]) if primary else None
    stages, now_frac = (_stages(primary, prof) if primary else ([], 0))

    crops = sorted({f["crop"] for f in fields})
    price_rows = []
    for c in crops:
        rows = market_svc.price_history(c, None, days=60)
        if not rows:
            continue
        now = rows[-1]["modal_price"]
        prev = rows[-30]["modal_price"] if len(rows) > 30 else rows[0]["modal_price"]
        price_rows.append({"crop": c, "price": now,
                           "change_pct": round(100 * (now - prev) / max(prev, 1), 1),
                           "series": [r["modal_price"] for r in rows]})

    alerts = dss.open_recommendations(session["user"]["id"])
    prio = {"high": 0, "medium": 1, "low": 2}
    prescriptions = sorted(alerts, key=lambda r: (prio.get(r["priority"], 3), -r["id"]))[:3]

    detections = db.query(
        "SELECT d.*, f.name AS field_name FROM disease_reports d "
        "LEFT JOIN fields f ON f.id=d.field_id "
        "WHERE d.user_id=? ORDER BY d.created_at DESC, d.id DESC LIMIT 5",
        (session["user"]["id"],))
    latest_scan = next((d for d in detections if d.get("image_path")), None) or \
        (detections[0] if detections else None)

    wx = weather[-1] if weather else None

    return render_template(
        "dashboard.html", farm=farm, farms=farms, fields=fields,
        primary=primary, health=health, yield_pred=yield_pred, sim=sim,
        stages=stages, now_frac=now_frac, wx=wx, soil=soil,
        score=health["overall_score"] if health else 0,
        prices=price_rows, alerts=alerts, prescriptions=prescriptions,
        detections=detections, latest_scan=latest_scan,
        weather_history=[w for w in weather if not w["is_forecast"]][-60:],
    )


# ---------------------------------------------------------------------------
# Farms / fields / soil
# ---------------------------------------------------------------------------
@bp.route("/farm/new", methods=["GET", "POST"])
@login_required
def add_farm():
    if request.method == "POST":
        fid = db.execute(
            """INSERT INTO farms (user_id, name, village, district, total_area,
               soil_type, irrigation) VALUES (?,?,?,?,?,?,?)""",
            (session["user"]["id"], request.form["name"], request.form.get("village"),
             request.form.get("district", "Nashik"), float(request.form.get("total_area") or 1),
             request.form.get("soil_type", "Medium black (loam)"),
             request.form.get("irrigation", "drip")))
        from ..seed.seed import seed_weather
        seed_weather(fid)
        session["farm_id"] = fid
        return redirect(url_for("main.crops"))
    return render_template("add_farm.html")


@bp.route("/field/new", methods=["GET", "POST"])
@login_required
def add_field():
    farm, farms = _farm()
    if request.method == "POST":
        db.execute(
            """INSERT INTO fields (farm_id, name, area_acres, crop, variety, sowing_date,
               expected_harvest, season) VALUES (?,?,?,?,?,?,?,?)""",
            (farm["id"], request.form["name"], float(request.form["area_acres"]),
             request.form["crop"], request.form.get("variety"),
             request.form.get("sowing_date"), request.form.get("expected_harvest"),
             request.form.get("season", "kharif")))
        flash("Field added.", "success")
        return redirect(url_for("main.crops"))
    return render_template("add_field.html", farm=farm, crops=CROP_NAMES,
                           profiles={k: v for k, v in CROPS.items()})


@bp.route("/soil/new/<int:field_id>", methods=["POST"])
@login_required
def add_soil(field_id: int):
    farm, _ = _farm()
    f = _field_or_404(field_id, farm["id"])
    db.execute(
        """INSERT INTO soil_readings (field_id, nitrogen, phosphorus, potassium, ph,
           organic_carbon, moisture, ec) VALUES (?,?,?,?,?,?,?,?)""",
        (f["id"], float(request.form.get("nitrogen") or 0),
         float(request.form.get("phosphorus") or 0), float(request.form.get("potassium") or 0),
         float(request.form.get("ph") or 7), float(request.form.get("organic_carbon") or 0.5),
         float(request.form.get("moisture") or 25), float(request.form.get("ec") or 0.8)))
    flash("Soil test recorded - recommendations updated.", "success")
    return redirect(request.referrer or url_for("main.crops"))


@bp.route("/recommendation/<int:rec_id>/<action>")
@login_required
def rec_action(rec_id: int, action: str):
    db.execute("UPDATE recommendations SET status=? WHERE id=? AND user_id=?",
               ({"done": "done", "ignore": "ignored"}.get(action, "open"),
                rec_id, session["user"]["id"]))
    return redirect(request.referrer or url_for("main.dss_page"))


@bp.route("/act/<int:rec_id>", methods=["POST"])
@login_required
def act(rec_id: int):
    """Closed-loop prescription execution: writes the physical log row that the
    prescription describes (irrigation / spray / fertilizer), then closes it."""
    rec = db.query_one("SELECT * FROM recommendations WHERE id=? AND user_id=?",
                       (rec_id, session["user"]["id"]))
    if not rec:
        abort(404)
    field_id = rec["field_id"]
    action = request.form.get("action", "apply")
    if action == "apply" and field_id:
        field = db.query_one("SELECT * FROM fields WHERE id=?", (field_id,))
        farm = db.query_one("SELECT * FROM farms WHERE id=?", (field["farm_id"],)) if field else None
        if field and farm:
            soil = dss.latest_soil(field_id)
            if rec["kind"] == "irrigation":
                irr = irr_svc.recommend(field, farm, soil, dss.forecast_only(farm["id"], 7))
                mm = max(irr.get("apply_mm") or 0, 20.0)
                db.execute("INSERT INTO irrigation_logs (field_id, water_mm, method, source) "
                           "VALUES (?,?,?,?)",
                           (field_id, mm, irr.get("system") or "drip", "recommended"))
                flash("Irrigation authorised - %d mm logged to the %s system."
                      % (mm, irr.get("system") or "drip"), "success")
            elif rec["kind"] == "pesticide":
                db.execute("INSERT INTO fertilizer_logs (field_id, product, dose_kg_per_acre, "
                           "nutrient) VALUES (?,?,?,?)",
                           (field_id, rec["title"], 0.6, "crop_protection"))
                sector_svc.treat_infection_sector(field_id)
                flash("Spray task dispatched - digital twin infection zone updated.", "success")
            else:
                plan = fert_svc.fertilizer_plan(field, soil)
                for p in (plan.get("plan") or [])[:2]:
                    db.execute("INSERT INTO fertilizer_logs (field_id, product, "
                               "dose_kg_per_acre, nutrient) VALUES (?,?,?,?)",
                               (field_id, p.get("product"), p.get("dose_per_acre"), "NPK"))
                flash("Dosage logged against the fertilizer program.", "success")
    db.execute("UPDATE recommendations SET status='done' WHERE id=? AND user_id=?",
               (rec_id, session["user"]["id"]))
    if action != "apply":
        flash("Prescription marked as done.", "success")
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/uploads/<path:path>")
@login_required
def uploaded_file(path: str):
    return send_from_directory(UPLOAD_DIR, path)


def _demo_files() -> list[str]:
    """Bundled sample leaves, images only (the folder also holds manifest.json)."""
    demo_dir = os.path.join(UPLOAD_DIR, "demo")
    if not os.path.isdir(demo_dir):
        return []
    exts = (".jpg", ".jpeg", ".png", ".webp")
    return sorted(f for f in os.listdir(demo_dir) if f.lower().endswith(exts))


PRESET_LABELS = [
    ("tomato_early_blight", "Tomato Early Blight (Demo)"),
    ("potato_late_blight", "Late Blight Oomycete"),
    ("tomato_yellow_leaf_curl", "Tomato Leaf Curl (TYLCV)"),
    ("tomato_healthy", "Healthy Tomato"),
]


def _xai_stats() -> dict | None:
    """Saliency statistics from the last Grad-CAM map, for the XAI panel."""
    cam = getattr(MODEL, "_last_cam", None)
    if cam is None:
        return None
    total = float(cam.sum()) + 1e-8
    flat = np.sort(cam.ravel())[::-1]
    top10 = float(flat[: max(1, flat.size // 10)].sum() / total) * 100
    mask = cam > 0.5 * cam.max()
    cover = float(mask.mean()) * 100
    ys, xs = np.nonzero(mask)
    cx = float(xs.mean()) / cam.shape[1] if len(xs) else 0.5
    cy = float(ys.mean()) / cam.shape[0] if len(ys) else 0.5
    h, w = cam.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.sqrt((xx - cx * w) ** 2 + (yy - cy * h) ** 2) / (0.5 * min(h, w))
    core = float(cam[rr <= 0.45].sum()) / total * 100
    ring = float(cam[(rr > 0.45) & (rr <= 1.1)].sum()) / total * 100
    return {"top10": round(top10, 1), "cover": round(cover, 1),
            "core": round(core, 1), "ring": round(ring, 1)}


# ---------------------------------------------------------------------------
# Crop monitoring
# ---------------------------------------------------------------------------
@bp.route("/crops")
@login_required
def crops():
    farm, farms = _farm()
    fields = dss.farm_fields(farm["id"])
    weather = dss.farm_weather(farm["id"])
    cards = []
    for f in fields:
        soil = dss.latest_soil(f["id"])
        h = dss.field_health(f, farm, soil, weather)
        twin = twin_svc.simulate(f, farm, soil, days_ahead=30)
        cards.append({
            "field": f, "health": h, "soil": soil,
            "twin": twin if "error" not in twin else None,
            "irrigation": h["irrigation"],
            "top_risk": h["pest_risk"]["risks"][0] if h["pest_risk"]["risks"] else None,
            "detections": dss.field_detections(f["id"], 3),
        })
    return render_template("crops.html", farm=farm, farms=farms, cards=cards,
                           profiles=CROPS)


@bp.route("/crop/<int:field_id>")
@login_required
def crop_detail(field_id: int):
    farm, farms = _farm()
    f = _field_or_404(field_id, farm["id"])
    soil = dss.latest_soil(f["id"])
    weather = dss.farm_weather(farm["id"])
    health = dss.field_health(f, farm, soil, weather)
    sim = twin_svc.simulate(f, farm, soil, days_ahead=60)
    soil_history = db.query("SELECT * FROM soil_readings WHERE field_id=? ORDER BY recorded_at",
                            (field_id,))
    irrigation_log = db.query("SELECT * FROM irrigation_logs WHERE field_id=? "
                              "ORDER BY date DESC LIMIT 12", (field_id,))
    fert_log = db.query("SELECT * FROM fertilizer_logs WHERE field_id=? ORDER BY date DESC LIMIT 10",
                        (field_id,))
    prof = get_crop(f["crop"])
    return render_template("crop_detail.html", farm=farm, farms=farms, field=f, profile=prof,
                           health=health, twin=sim, soil=soil, soil_history=soil_history,
                           irrigation_log=irrigation_log, fert_log=fert_log,
                           yield_pred=_yield_for(f, farm, soil, weather))


def _yield_for(field, farm, soil, weather):
    """Assemble the feature vector for the yield model from live farm data."""
    prof = get_crop(field["crop"])
    if not prof:
        return None
    recent = [w for w in weather if not w["is_forecast"]][-90:] or weather[-90:]
    rainfall = sum(w["rainfall_mm"] for w in recent)
    temp_max_mean = sum(w["temp_max"] for w in recent) / max(len(recent), 1)
    irr_mm = db.query_one(
        "SELECT COALESCE(SUM(water_mm),0) AS s FROM irrigation_logs WHERE field_id=?",
        (field["id"],))["s"]
    return yp.predict_yield({
        "crop": field["crop"], "season": field.get("season"),
        "soil_type": farm.get("soil_type"), "area_acres": field["area_acres"],
        "nitrogen": (soil or {}).get("nitrogen"), "phosphorus": (soil or {}).get("phosphorus"),
        "potassium": (soil or {}).get("potassium"), "ph": (soil or {}).get("ph"),
        "organic_carbon": (soil or {}).get("organic_carbon"),
        "rainfall_mm": rainfall, "irrigation_mm": irr_mm, "temp_max_mean": temp_max_mean,
        "drip": 1 if (farm.get("irrigation") or "").lower() == "drip" else 0,
        "pest_control": 1,
    })


# ---------------------------------------------------------------------------
# Disease detection (Edge AI) + Grad-CAM XAI
# ---------------------------------------------------------------------------
def _presets(files):
    out = []
    for key, label in PRESET_LABELS:
        idx = next((i for i, f in enumerate(files) if f.startswith(key)), None)
        if idx is not None:
            out.append({"idx": idx, "label": label, "file": files[idx]})
    return out


def _render_disease(farm, fields, result, gradcam_uri, uploaded, history, files,
                    image_rel=None, xai=None):
    return render_template(
        "disease.html", farm=farm, fields=fields, result=result, gradcam=gradcam_uri,
        uploaded=uploaded, history=history, model=MODEL, classes=len(DISEASE_DB),
        regional=list(REGIONAL_CLASSES), disease_db=DISEASE_DB, demo_files=files,
        presets=_presets(files), image_rel=image_rel, xai=xai)


@bp.route("/disease", methods=["GET", "POST"])
@login_required
def disease():
    farm, farms = _farm()
    fields = dss.farm_fields(farm["id"])
    files = _demo_files()
    result = gradcam_uri = uploaded_name = image_rel = None
    xai = None

    if request.method == "POST":
        file = request.files.get("leaf_image")
        field_id = request.form.get("field_id")
        if not file or not file.filename:
            flash("Choose a leaf photo first.", "error")
        elif not MODEL.available:
            flash("The disease model is not trained yet.", "error")
        else:
            try:
                result, bgr = detect_from_upload(file.stream)
                uploaded_name = file.filename
                import cv2
                cam = MODEL.gradcam(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                if cam is not None:
                    gradcam_uri = encode_png(cam)
                xai = _xai_stats()
                # persist the photo so Reports can embed it in the PDF
                scans = os.path.join(UPLOAD_DIR, "scans")
                os.makedirs(scans, exist_ok=True)
                name = "%d_%s" % (int(time.time()), secure_filename(file.filename) or "leaf.jpg")
                file.stream.seek(0)
                file.save(os.path.join(scans, name))
                image_rel = "scans/" + name
                fld = next((f for f in fields if str(f["id"]) == str(field_id)), None)
                top = result["top"]
                result["report_id"] = db.execute(
                    """INSERT INTO disease_reports (user_id, field_id, crop, disease_class,
                       disease_name, confidence, severity, advice, source, image_path)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (session["user"]["id"], fld["id"] if fld else None, top["crop"],
                     top["class"], top["disease"], top["confidence"], top["severity"],
                     "; ".join(top["management"][:2]), result["backend"], image_rel))
            except Exception as exc:
                flash(f"Detection failed: {exc}", "error")

    history = db.query(
        "SELECT d.*, f.name AS field_name FROM disease_reports d "
        "LEFT JOIN fields f ON f.id=d.field_id WHERE d.user_id=? "
        "ORDER BY d.created_at DESC, d.id DESC LIMIT 12", (session["user"]["id"],))
    return _render_disease(farm, fields, result, gradcam_uri, uploaded_name, history,
                           files, image_rel, xai)


@bp.route("/disease/demo/<int:idx>")
@login_required
def disease_demo(idx: int):
    """Run detection on a bundled sample leaf so the demo works without a camera."""
    farm, farms = _farm()
    fields = dss.farm_fields(farm["id"])
    files = _demo_files()
    if not files:
        flash("No demo images available.", "error")
        return redirect(url_for("main.disease"))
    path = os.path.join(UPLOAD_DIR, "demo", files[idx % len(files)])

    import cv2
    bgr = cv2.imread(path)
    if bgr is None:
        flash(f"Could not read the demo image '{files[idx % len(files)]}'.", "error")
        return redirect(url_for("main.disease"))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    result = MODEL.predict_array(rgb)
    cam = MODEL.gradcam(rgb)
    gradcam_uri = encode_png(cam) if cam is not None else None
    xai = _xai_stats()
    top = result["top"]
    image_rel = "demo/" + files[idx % len(files)]
    result["report_id"] = db.execute(
        """INSERT INTO disease_reports (user_id, field_id, crop, disease_class, disease_name,
           confidence, severity, advice, source, image_path) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (session["user"]["id"], fields[0]["id"] if fields else None, top["crop"],
         top["class"], top["disease"], top["confidence"], top["severity"],
         "; ".join(top["management"][:2]), "edge_ai_demo", image_rel))
    history = db.query(
        "SELECT d.*, f.name AS field_name FROM disease_reports d "
        "LEFT JOIN fields f ON f.id=d.field_id WHERE d.user_id=? "
        "ORDER BY d.created_at DESC, d.id DESC LIMIT 12", (session["user"]["id"],))
    return _render_disease(farm, fields, result, gradcam_uri, os.path.basename(path),
                           history, files, image_rel, xai)


# ---------------------------------------------------------------------------
# Digital Twin & sensors
# ---------------------------------------------------------------------------
@bp.route("/twin")
@login_required
def twin():
    farm, farms = _farm()
    fields = dss.farm_fields(farm["id"])
    field_id = int(request.args.get("field_id") or (fields[0]["id"] if fields else 0))
    f = next((x for x in fields if x["id"] == field_id), fields[0] if fields else None)
    if not f:
        return render_template("twin.html", farm=farm, cards=[], sectors=[])
    soil = dss.latest_soil(f["id"])
    weather = dss.farm_weather(farm["id"])
    days = int(request.args.get("days") or 60)
    sim = twin_svc.simulate(f, farm, soil, days_ahead=days)
    comparison = twin_svc.compare_scenarios(f, farm, soil, days_ahead=days)
    harvest = twin_svc.harvest_window(f, farm, soil)
    if request.args.get("recal"):
        db.execute("DELETE FROM twin_sectors WHERE field_id=?", (f["id"],))
        flash("Sensor mesh recalibrated - sector telemetry re-baselined.", "success")
    sectors = sector_svc.ensure_sectors(f["id"])
    micro = weather[-1] if weather else None
    sim_count = db.query_one("SELECT COUNT(*) AS n FROM sim_runs WHERE field_id=?",
                             (f["id"],))["n"]
    return render_template("twin.html", farm=farm, cards=fields, field=f, sim=sim,
                           comparison=comparison, harvest=harvest, days=days,
                           sectors=sectors, micro=micro, soil=soil, sim_count=sim_count)


# ---------------------------------------------------------------------------
# AI/ML predictions lab
# ---------------------------------------------------------------------------
@bp.route("/predictions", methods=["GET", "POST"])
@login_required
def predictions():
    farm, farms = _farm()
    fields = dss.farm_fields(farm["id"])
    field_id = int(request.args.get("field_id") or (fields[0]["id"] if fields else 0))
    f = next((x for x in fields if x["id"] == field_id), fields[0] if fields else None)
    if not f:
        return render_template("predictions.html", farm=farm, cards=[])
    soil = dss.latest_soil(f["id"])
    weather = dss.farm_weather(farm["id"])

    y = _yield_for(f, farm, soil, weather)
    irr = irr_svc.recommend(f, farm, soil, dss.forecast_only(farm["id"], 7))
    fert = fert_svc.fertilizer_plan(f, soil)
    pest = fert_svc.pest_risk(f, weather[-7:] or [], None, dss.recent_spray_count(f["id"]))

    if request.method == "POST":  # what-if overrides
        override = {
            "crop": request.form.get("crop") or f["crop"],
            "season": request.form.get("season") or f.get("season"),
            "soil_type": request.form.get("soil_type") or farm.get("soil_type"),
            "area_acres": float(request.form.get("area_acres") or f["area_acres"]),
            "nitrogen": float(request.form.get("nitrogen") or (soil or {}).get("nitrogen") or 0),
            "phosphorus": float(request.form.get("phosphorus") or (soil or {}).get("phosphorus") or 0),
            "potassium": float(request.form.get("potassium") or (soil or {}).get("potassium") or 0),
            "ph": float(request.form.get("ph") or (soil or {}).get("ph") or 7),
            "organic_carbon": float(request.form.get("organic_carbon")
                                    or (soil or {}).get("organic_carbon") or 0.5),
            "rainfall_mm": float(request.form.get("rainfall_mm") or 0),
            "irrigation_mm": float(request.form.get("irrigation_mm") or 0),
            "temp_max_mean": float(request.form.get("temp_max_mean") or 32),
            "drip": 1 if request.form.get("drip") else 0,
            "pest_control": int(request.form.get("pest_control") or 1),
        }
        y = yp.predict_yield(override)
        flash("What-if prediction recalculated.", "success")

    return render_template("predictions.html", farm=farm, cards=fields,
                           field=f, soil=soil, yield_pred=y, irrigation=irr,
                           fertilizer=fert, pest=pest, profiles=CROPS,
                           crop_names=CROP_NAMES)


# ---------------------------------------------------------------------------
# Market intelligence
# ---------------------------------------------------------------------------
@bp.route("/market")
@login_required
def market():
    farm, farms = _farm()
    fields = dss.farm_fields(farm["id"])
    grown = sorted({f["crop"] for f in fields})
    crop = request.args.get("crop") or (grown[0] if grown else CROP_NAMES[0])

    hist = market_svc.price_history(crop, None, days=180)
    mandis = market_svc.mandi_comparison(crop)
    demand = market_svc.demand_outlook(crop)
    best = mandis[0] if mandis else None

    area = sum(f["area_acres"] for f in fields if f["crop"] == crop) or 1.0
    prof = get_crop(crop)
    profit = market_svc.estimate_profit(crop, area, prof.yield_kg_per_acre * area / 100.0) \
        if prof else None

    per_mandi_series = {}
    for m in MANDIS:
        s = market_svc.price_history(crop, m[0], days=90)
        if s:
            per_mandi_series[m[0]] = [r["modal_price"] for r in s]

    alternatives = market_svc.crop_alternatives(farm.get("soil_type", ""), 1.0, None)
    return render_template("market.html", farm=farm, crop=crop,
                           crop_names=grown or CROP_NAMES, history=hist, mandis=mandis,
                           demand=demand, best=best, profit=profit,
                           series=per_mandi_series, alternatives=alternatives[:8],
                           profile=prof)


# ---------------------------------------------------------------------------
# Integrated DSS & market directive
# ---------------------------------------------------------------------------
@bp.route("/dss")
@login_required
def dss_page():
    farm, farms = _farm()
    if not farm:
        return redirect(url_for("main.add_farm"))
    pack = dss.decision_pack(session["user"]["id"], farm["id"])
    recs = dss.open_recommendations(session["user"]["id"])

    fields = dss.farm_fields(farm["id"])
    primary = next((f for f in fields if f["crop"] == "Tomato" and f["status"] == "growing"),
                   next((f for f in fields if f["status"] == "growing"),
                        fields[0] if fields else None))
    soil = dss.latest_soil(primary["id"]) if primary else None
    weather = dss.farm_weather(farm["id"])
    yield_pred = _yield_for(primary, farm, soil, weather) if primary else None
    irr = irr_svc.recommend(primary, farm, soil, dss.forecast_only(farm["id"], 7)) \
        if primary else None
    mandi_rows = market_svc.mandi_comparison(primary["crop"]) if primary else []
    fin = None
    if primary and yield_pred:
        fin = market_svc.estimate_profit(primary["crop"], primary["area_acres"],
                                         yield_pred["total_yield_q"])
        fin["field"] = primary["name"]

    det = dss.field_detections(primary["id"], 3) if primary else []
    sick = next((d for d in det if d["disease_class"] in DISEASE_DB and
                 DISEASE_DB[d["disease_class"]].pathogen_type != "none"), None)

    spray = next((a for a in pack.get("actions", []) if a["kind"] == "pesticide"), None)
    mkt = next((a for a in pack.get("actions", []) if a["kind"] == "market"), None)
    crop_age = None
    if primary and primary.get("sowing_date"):
        try:
            crop_age = (date.today() -
                        datetime.strptime(primary["sowing_date"], "%Y-%m-%d").date()).days
        except ValueError:
            crop_age = None

    return render_template("dss.html", farm=farm, pack=pack, recs=recs,
                           disease_db=DISEASE_DB, primary=primary, soil=soil,
                           yield_pred=yield_pred, irr=irr, mandi_rows=mandi_rows,
                           fin=fin, sick=sick, spray=spray, mkt=mkt, crop_age=crop_age,
                           wx=weather[-1] if weather else None)


# ---------------------------------------------------------------------------
# Reports + PDF generation
# ---------------------------------------------------------------------------
@bp.route("/reports")
@login_required
def reports():
    farm, farms = _farm()
    history = db.query(
        "SELECT d.*, f.name AS field_name FROM disease_reports d "
        "LEFT JOIN fields f ON f.id=d.field_id WHERE d.user_id=? "
        "ORDER BY d.created_at DESC, d.id DESC LIMIT 30", (session["user"]["id"],))
    done = db.query_one("SELECT COUNT(*) AS n FROM recommendations WHERE user_id=? "
                        "AND status='done'", (session["user"]["id"],))["n"]
    sims = db.query_one("SELECT COUNT(*) AS n FROM sim_runs")["n"]
    sales = db.query("SELECT * FROM sales ORDER BY date DESC LIMIT 8")
    return render_template("reports.html", farm=farm, history=history, done=done,
                           sims=sims, sales=sales)


@bp.route("/reports/farm.pdf")
@login_required
def reports_farm_pdf():
    farm, farms = _farm()
    pack = dss.decision_pack(session["user"]["id"], farm["id"])
    fields = dss.farm_fields(farm["id"])
    primary = next((f for f in fields if f["status"] == "growing"), fields[0] if fields else None)
    mandi_rows = market_svc.mandi_comparison(primary["crop"]) if primary else []
    buf = pdf_svc.farm_report_pdf(farm, pack, pack.get("profit_outlook", []), mandi_rows)
    return send_from_directory_or_bytes(buf, "AgriSmartAI_Farm_Report.pdf")


def send_from_directory_or_bytes(buf, name):
    from flask import Response
    return Response(buf.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=%s" % name})


@bp.route("/reports/diagnostic/<int:report_id>.pdf")
@login_required
def reports_diagnostic_pdf(report_id: int):
    rep = db.query_one(
        "SELECT d.*, f.name AS field_name FROM disease_reports d "
        "LEFT JOIN fields f ON f.id=d.field_id WHERE d.id=? AND d.user_id=?",
        (report_id, session["user"]["id"]))
    if not rep:
        abort(404)
    img = os.path.join(UPLOAD_DIR, rep["image_path"]) if rep.get("image_path") else None
    buf = pdf_svc.diagnostic_pdf(rep, img if img and os.path.exists(img) else None)
    return send_from_directory_or_bytes(buf, "Diagnostic_%d.pdf" % report_id)


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
@bp.route("/weather")
@login_required
def weather():
    farm, farms = _farm()
    rows = dss.farm_weather(farm["id"], days_back=90, days_forward=7)
    history = [r for r in rows if not r["is_forecast"]]
    forecast = [r for r in rows if r["is_forecast"]]
    monthly = {}
    for r in history:
        m = r["date"][:7]
        monthly.setdefault(m, {"rain": 0.0, "tmax": [], "tmin": [], "n": 0})
        monthly[m]["rain"] += r["rainfall_mm"]
        monthly[m]["tmax"].append(r["temp_max"])
        monthly[m]["tmin"].append(r["temp_min"])
        monthly[m]["n"] += 1
    summary = [{"month": k, "rain": round(v["rain"], 1),
                "tmax": round(sum(v["tmax"]) / v["n"], 1),
                "tmin": round(sum(v["tmin"]) / v["n"], 1)}
               for k, v in sorted(monthly.items())]
    return render_template("weather.html", farm=farm, history=history,
                           forecast=forecast, summary=summary)


@bp.route("/profile")
@login_required
def profile():
    user = db.query_one("SELECT * FROM users WHERE id=?", (session["user"]["id"],))
    farm, farms = _farm()
    stats = {
        "farms": len(farms),
        "fields": db.query_one("SELECT COUNT(*) AS n FROM fields f JOIN farms fa "
                               "ON fa.id=f.farm_id WHERE fa.user_id=?", (user["id"],))[("n")],
        "scans": db.query_one("SELECT COUNT(*) AS n FROM disease_reports WHERE user_id=?",
                              (user["id"],))["n"],
        "soil_tests": db.query_one(
            "SELECT COUNT(*) AS n FROM soil_readings s JOIN fields f ON f.id=s.field_id "
            "JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (user["id"],))["n"],
    }
    sales = db.query("SELECT * FROM sales ORDER BY date DESC LIMIT 10")
    return render_template("profile.html", user=user, farm=farm, stats=stats, sales=sales,
                           model_status=dss._disease_status())
