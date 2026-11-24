"""
Seed the SQLite database with a realistic Nashik (Maharashtra) farm scenario.

Everything here is *synthetic but physically coherent*:
  * 2 farmers, 3 farms, 9 fields across Maharashtra crops
  * 365 days of weather history + 7-day forecast generated from Nashik
    climatological normals (monsoon Jun-Sep, hot Mar-May, cool Nov-Jan)
  * 400 days of mandi prices per crop x mandi, with trend + seasonality +
    mean-reverting noise (the price forecaster learns from these)
  * a 4,000-row "regional trial network" of field-seasons (soil + weather +
    management -> achieved yield) used to train the yield model
  * soil readings, irrigation/fertilizer logs, disease & pest history

Idempotent: running it twice does not duplicate data.
"""
from __future__ import annotations

import math
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db
from app.agronomy import CROPS, get_crop
from app.config import DB_PATH, MANDIS
from werkzeug.security import generate_password_hash

TODAY = date.today()
RNG = random.Random(20260913)

# Nashik climatological normals (monthly): tmin, tmax degC, rain mm, RH %
CLIMATE = {
    1:  (9.5, 29.5, 1.0, 46), 2:  (11.0, 31.5, 0.5, 40),
    3:  (15.0, 35.0, 1.5, 33), 4:  (19.0, 38.0, 5.0, 30),
    5:  (22.0, 39.0, 12.0, 34), 6:  (22.5, 33.0, 120.0, 62),
    7:  (21.5, 28.5, 195.0, 76), 8:  (21.0, 27.5, 150.0, 78),
    9:  (20.5, 29.5, 125.0, 70), 10: (17.5, 32.0, 55.0, 56),
    11: (13.0, 30.5, 12.0, 48), 12: (10.0, 29.0, 3.0, 47),
}

SOIL_TYPES = ["Medium black (loam)", "Deep black (clay)", "Sandy loam", "Red sandy"]


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
def gen_weather_day(d: date) -> dict:
    tmin_n, tmax_n, rain_n, rh_n = CLIMATE[d.month]
    # smooth between months using day-of-month fraction
    nxt = CLIMATE[1 if d.month == 12 else d.month + 1]
    f = d.day / 30.0
    tmin_n += (nxt[0] - tmin_n) * f * 0.5
    tmax_n += (nxt[1] - tmax_n) * f * 0.5
    rain_n += (nxt[2] - rain_n) * f * 0.5
    rh_n += (nxt[3] - rh_n) * f * 0.5

    rainy = RNG.random() < min(0.85, (rain_n / 30.0) ** 0.65)
    rain = 0.0
    if rainy:
        rain = round(max(0.2, RNG.gammavariate(1.6, rain_n / 30.0 * 1.4)), 1)
    tmin = round(tmin_n + RNG.gauss(0, 1.4) - (2.0 if rain > 1 else 0), 1)
    tmax = round(tmax_n + RNG.gauss(0, 1.6) - (4.0 if rain > 1 else 0), 1)
    rh = round(min(96, max(18, rh_n + RNG.gauss(0, 6) + (12 if rain > 1 else -6))), 1)
    wind = round(max(1.0, RNG.gauss(9, 4) + (6 if d.month in (3, 4, 5) else 0)), 1)
    clear = 1.0 if rain < 1 else max(0.15, 1 - rain / 60.0)
    solar = round(max(3.0, RNG.gauss(22, 3) * clear * (0.72 + 0.28 * math.cos(math.radians((d.month - 1) * 30)))), 1)
    cond = ("Rain" if rain >= 10 else "Light rain" if rain > 0.5 else
            "Cloudy" if rain > 0 else "Clear" if rh < 55 else "Hazy")
    return {"temp_min": tmin, "temp_max": tmax, "humidity": rh, "rainfall_mm": rain,
            "wind_kmph": wind, "solar_mj": solar, "condition": cond}


def seed_weather(farm_id: int, days_back: int = 365, days_forecast: int = 7) -> None:
    rows = []
    for i in range(days_back, -days_forecast, -1):
        d = TODAY - timedelta(days=i)
        w = gen_weather_day(d)
        rows.append((farm_id, d.isoformat(), w["temp_min"], w["temp_max"], w["humidity"],
                     w["rainfall_mm"], w["wind_kmph"], w["solar_mj"], w["condition"],
                     1 if i < 0 else 0))
    db.executemany(
        """INSERT OR REPLACE INTO weather_daily
           (farm_id, date, temp_min, temp_max, humidity, rainfall_mm, wind_kmph,
            solar_mj, condition, is_forecast)
           VALUES (?,?,?,?,?,?,?,?,?,?)""", rows)


# ---------------------------------------------------------------------------
# Market prices
# ---------------------------------------------------------------------------
def seed_market_prices(days_back: int = 400) -> None:
    """Price series = trend + annual seasonality + mandi premium + OU noise.

    The forecaster sees only the price history, so it must recover the
    structure we generate here.
    """
    mandi_factor = {}
    for name, district, dist_km, comm, transport in MANDIS:
        # bigger urban mandis pay a premium, offset by distance & commission
        premium = 1.0 + (0.10 if "Mumbai" in name else 0.05 if "Pune" in name else 0.0)
        premium -= dist_km * 0.00015 + (comm - 1.5) * 0.03
        mandi_factor[name] = premium

    rows = []
    for crop, prof in CROPS.items():
        base = prof.base_price_per_q
        for name in mandi_factor:
            price = base * mandi_factor[name]
            trend = RNG.gauss(0.00016, 0.0004)          # slow drift
            for i in range(days_back, -1, -1):
                d = TODAY - timedelta(days=i)
                doy = d.timetuple().tm_yday
                seasonal = 1 + 0.13 * math.sin(2 * math.pi * (doy - 80) / 365.0) \
                             + 0.05 * math.sin(2 * math.pi * (doy - 30) / 182.5)
                shock = 1.0
                if crop == "Onion" and d.month in (11, 12, 1):
                    shock = 1.22                        # rabi arrival scarcity
                if crop == "Tomato" and d.month in (4, 5):
                    shock = 1.35                        # summer gap
                if crop == "Grape" and d.month in (2, 3):
                    shock = 0.82                        # peak export arrivals
                noise = RNG.gauss(0, prof.price_volatility / 6.0)
                price = max(base * 0.35,
                            price * (1 - 0.12) + base * mandi_factor[name] * 0.12
                            + price * trend + price * noise * 0.25)
                modal = round(price * seasonal * shock, 0)
                lo = round(modal * RNG.uniform(0.80, 0.93), 0)
                hi = round(modal * RNG.uniform(1.07, 1.24), 0)
                arrivals = max(0.5, RNG.gammavariate(3.0, 14.0) *
                               (1.25 if d.month in (10, 11, 12, 1, 2, 3) else 0.75) *
                               (0.8 if "Mumbai" in name or "Pune" in name else 1.0))
                rows.append((crop, name, d.isoformat(), modal, lo, hi, round(arrivals, 2)))
    db.executemany(
        """INSERT OR REPLACE INTO market_prices
           (crop, mandi, date, modal_price, min_price, max_price, arrivals_t)
           VALUES (?,?,?,?,?,?,?)""", rows)


# ---------------------------------------------------------------------------
# Regional trial network -> training data for the yield model
# ---------------------------------------------------------------------------
def build_trial_rows(n: int = 4000) -> list[dict]:
    """Synthetic agronomic trials with a known response surface + noise.

    Yield responds to N-P-K sufficiency, water availability, heat stress and
    pH, so the trained model recovers a real (if synthetic) agronomy.
    """
    out: list[dict] = []
    names = list(CROPS.keys())
    for _ in range(n):
        crop = RNG.choice(names)
        prof = CROPS[crop]
        n_req, p_req, k_req = prof.npk_kg_per_acre
        nitrogen = max(2, RNG.gauss(n_req, n_req * 0.32))
        phos = max(1, RNG.gauss(p_req, p_req * 0.35))
        potash = max(1, RNG.gauss(k_req, k_req * 0.35))
        ph = min(9.0, max(4.8, RNG.gauss(7.4, 0.7)))
        oc = min(1.6, max(0.15, RNG.gauss(0.55, 0.2)))
        rainfall = max(0, RNG.gauss(700 if RNG.random() < 0.5 else 350, 220))
        irr_mm = max(0, RNG.gauss(prof.water_mm_season * 0.85, prof.water_mm_season * 0.28))
        tmax_mean = min(43, max(22, RNG.gauss(32, 3.2)))
        density = RNG.uniform(0.85, 1.15)
        drip = 1 if RNG.random() < 0.62 else 0
        pest_ctrl = RNG.choice([0, 1, 1, 2])       # 0 none, 1 basic, 2 IPM
        soil_type = RNG.choice(SOIL_TYPES)

        n_frac = min(1.25, nitrogen / max(n_req, 1))
        p_frac = min(1.25, phos / max(p_req, 1))
        k_frac = min(1.25, potash / max(k_req, 1))
        nut = (n_frac ** 0.55) * (p_frac ** 0.22) * (k_frac ** 0.23)

        water_need = prof.water_mm_season
        water_avail = irr_mm + rainfall * (0.55 if drip else 0.75)
        wsi = min(1.4, water_avail / max(water_need, 1))
        water_f = 1.0 if wsi >= 1.0 else (0.35 + 0.65 * wsi) * (1.08 if drip else 1.0)
        water_f = min(1.18, water_f)

        t_opt = 30.0
        heat = max(0.45, 1.0 - 0.055 * max(0.0, tmax_mean - t_opt) ** 1.15)
        ph_f = 1.0 - 0.16 * abs(ph - 6.9) / 1.5
        oc_f = 0.9 + 0.22 * min(1.0, oc / 0.7)
        drip_f = 1.0 + (0.07 if drip else 0.0)
        pest_f = {0: 0.86, 1: 0.96, 2: 1.0}[pest_ctrl]
        soil_f = {"Medium black (loam)": 1.03, "Deep black (clay)": 1.0,
                  "Sandy loam": 0.94, "Red sandy": 0.9}[soil_type]

        y = (prof.yield_kg_per_acre * density * nut * water_f * heat
             * ph_f * oc_f * drip_f * pest_f * soil_f)
        y *= RNG.gauss(1.0, 0.085)
        y = max(prof.yield_range[0] * 0.45, min(prof.yield_range[1] * 1.25, y))

        out.append({
            "crop": crop, "season": RNG.choice(prof.seasons),
            "area_acres": round(RNG.uniform(0.5, 8.0), 2),
            "nitrogen": round(nitrogen, 1), "phosphorus": round(phos, 1),
            "potassium": round(potash, 1), "ph": round(ph, 2),
            "organic_carbon": round(oc, 2), "rainfall_mm": round(rainfall, 1),
            "irrigation_mm": round(irr_mm, 1), "temp_max_mean": round(tmax_mean, 1),
            "drip": drip, "plant_density_index": round(density, 3),
            "pest_control": pest_ctrl, "soil_type": soil_type,
            "yield_kg_per_acre": round(y, 1),
        })
    return out


# ---------------------------------------------------------------------------
# Demo users, farms, fields
# ---------------------------------------------------------------------------
FARM_PLAN = [
    {
        "user": ("ramesh", "farmer123", "Ramesh Pawar", "+91 98220 11234"),
        "farms": [
            {"name": "Shivneri Farms", "village": "Mohadi", "district": "Nashik",
             "total_area": 9.0, "lat": 20.0100, "lon": 73.7300,
             "soil_type": "Medium black (loam)", "irrigation": "drip",
             "fields": [
                 ("Block A", 3.0, "Grape", "Thompson Seedless", "kharif",
                  (TODAY - timedelta(days=120)), (TODAY + timedelta(days=55))),
                 ("Block B", 2.0, "Onion", "Agrifound Light Red", "rabi",
                  (TODAY - timedelta(days=65)), (TODAY + timedelta(days=65))),
                 ("Block C", 2.5, "Tomato", "Arka Rakshak", "kharif",
                  (TODAY - timedelta(days=45)), (TODAY + timedelta(days=75))),
                 ("Block D", 1.5, "Maize", "DKC 9144", "kharif",
                  (TODAY - timedelta(days=70)), (TODAY + timedelta(days=40))),
             ]},
            {"name": "Gangapur Road Plot", "village": "Gangapur", "district": "Nashik",
             "total_area": 4.0, "lat": 19.9800, "lon": 73.7000,
             "soil_type": "Sandy loam", "irrigation": "drip",
             "fields": [
                 ("Plot 1", 2.0, "Pomegranate", "Bhagwa", "rabi",
                  (TODAY - timedelta(days=150)), (TODAY + timedelta(days=40))),
                 ("Plot 2", 2.0, "Sugarcane", "Co 86032", "kharif",
                  (TODAY - timedelta(days=210)), (TODAY + timedelta(days=120))),
             ]},
        ],
    },
    {
        "user": ("sunita", "farmer123", "Sunita Deshmukh", "+91 99702 45678"),
        "farms": [
            {"name": "Deshmukh Wadi", "village": "Dindori", "district": "Nashik",
             "total_area": 6.0, "lat": 20.1900, "lon": 73.8300,
             "soil_type": "Deep black (clay)", "irrigation": "sprinkler",
             "fields": [
                 ("Field 1", 2.5, "Grape", "Sonaka", "kharif",
                  (TODAY - timedelta(days=110)), (TODAY + timedelta(days=60))),
                 ("Field 2", 1.5, "Tomato", "Pusa Ruby", "kharif",
                  (TODAY - timedelta(days=50)), (TODAY + timedelta(days=70))),
                 ("Field 3", 2.0, "Pigeon pea (Tur)", "BSMR-736", "kharif",
                  (TODAY - timedelta(days=95)), (TODAY + timedelta(days=65))),
             ]},
        ],
    },
]


def seed_users_farms() -> list[int]:
    user_ids = []
    for plan in FARM_PLAN:
        uname, pwd, fname, phone = plan["user"]
        existing = db.query_one("SELECT id FROM users WHERE username=?", (uname,))
        if existing:
            uid = existing["id"]
        else:
            uid = db.execute(
                "INSERT INTO users (username, password_hash, full_name, phone) VALUES (?,?,?,?)",
                (uname, generate_password_hash(pwd), fname, phone))
        user_ids.append(uid)

        for farm in plan["farms"]:
            frow = db.query_one(
                "SELECT id FROM farms WHERE user_id=? AND name=?", (uid, farm["name"]))
            if frow:
                fid = frow["id"]
            else:
                fid = db.execute(
                    """INSERT INTO farms (user_id, name, village, district, state,
                       total_area, lat, lon, soil_type, irrigation)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (uid, farm["name"], farm["village"], farm["district"], "Maharashtra",
                     farm["total_area"], farm["lat"], farm["lon"], farm["soil_type"],
                     farm["irrigation"]))

            for (fname_, area, crop, variety, season, sow, harvest) in farm["fields"]:
                f = db.query_one(
                    "SELECT id FROM fields WHERE farm_id=? AND name=?", (fid, fname_))
                if f:
                    continue
                db.execute(
                    """INSERT INTO fields (farm_id, name, area_acres, crop, variety,
                       sowing_date, expected_harvest, season, status)
                       VALUES (?,?,?,?,?,?,?,?, 'growing')""",
                    (fid, fname_, area, crop, variety, sow.isoformat(),
                     harvest.isoformat(), season))
    return user_ids


def seed_soil_and_logs() -> None:
    fields = db.query("SELECT * FROM fields")
    for f in fields:
        prof = get_crop(f["crop"])
        if not prof:
            continue
        n_req, p_req, k_req = prof.npk_kg_per_acre
        already = db.query_one("SELECT COUNT(*) AS n FROM soil_readings WHERE field_id=?",
                               (f["id"],))["n"]
        if not already:
            for k in range(3):   # last 3 soil tests
                d = (TODAY - timedelta(days=30 * k + RNG.randint(0, 8))).isoformat()
                db.execute(
                    """INSERT INTO soil_readings (field_id, recorded_at, nitrogen, phosphorus,
                       potassium, ph, organic_carbon, moisture, ec) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (f["id"], d,
                     round(max(3, RNG.gauss(n_req * 0.72, n_req * 0.2)), 1),
                     round(max(2, RNG.gauss(p_req * 0.65, p_req * 0.25)), 1),
                     round(max(2, RNG.gauss(k_req * 0.7, k_req * 0.22)), 1),
                     round(min(8.6, max(5.6, RNG.gauss(7.3, 0.45))), 2),
                     round(max(0.2, RNG.gauss(0.5, 0.15)), 2),
                     round(min(48, max(8, RNG.gauss(26, 6))), 1),
                     round(max(0.2, RNG.gauss(0.9, 0.25)), 2)))

        # irrigation log - last 12 events
        if not db.query_one("SELECT COUNT(*) AS n FROM irrigation_logs WHERE field_id=?",
                            (f["id"],))["n"]:
            for k in range(12):
                d = (TODAY - timedelta(days=4 * k + RNG.randint(0, 2))).isoformat()
                db.execute(
                    "INSERT INTO irrigation_logs (field_id, date, water_mm, method) VALUES (?,?,?,?)",
                    (f["id"], d, round(RNG.uniform(8, 34), 1),
                     "drip" if RNG.random() < 0.8 else "sprinkler"))

        if not db.query_one("SELECT COUNT(*) AS n FROM fertilizer_logs WHERE field_id=?",
                            (f["id"],))["n"]:
            for k, (prod, nut) in enumerate([("Urea", "N"), ("DAP", "P"), ("MOP", "K"),
                                             ("19:19:19", "NPK")]):
                d = (TODAY - timedelta(days=25 * (k + 1))).isoformat()
                db.execute(
                    """INSERT INTO fertilizer_logs (field_id, date, product,
                       dose_kg_per_acre, nutrient) VALUES (?,?,?,?,?)""",
                    (f["id"], d, prod, round(RNG.uniform(20, 60), 1), nut))


def seed_disease_history(user_ids: list[int]) -> None:
    if db.table_count("disease_reports"):
        return
    fields = db.query("SELECT * FROM fields")
    events = [
        ("Tomato", "Tomato___Early_blight", "Early blight", 0.87, "moderate",
         "Concentric target spots on lower leaves. Mancozeb 2.5 g/L advised."),
        ("Grape", "Grape___Black_rot", "Grape black rot", 0.79, "mild",
         "Mummified berries found. Sanitation + mancozeb before rains advised."),
        ("Tomato", "Tomato___Leaf_Mold", "Leaf mold", 0.68, "mild",
         "Olive mould on leaf underside. Improve ventilation."),
        ("Maize", "Corn_(maize)___Common_rust_", "Maize common rust", 0.74, "mild",
         "Cinnamon pustules below 10% severity. Monitor; propiconazole if it spreads."),
        ("Potato", "Potato___Late_blight", "Potato late blight", 0.91, "severe",
         "Emergency spray cymoxanil + mancozeb within 24 h."),
    ]
    for i, (crop, cls, name, conf, sev, advice) in enumerate(events):
        fld = next((f for f in fields if f["crop"] == crop), fields[0])
        db.execute(
            """INSERT INTO disease_reports (user_id, field_id, crop, disease_class,
               disease_name, confidence, severity, advice, source,
               created_at) VALUES (?,?,?,?,?,?,?,?, 'edge_ai', datetime('now', ?))""",
            (user_ids[0], fld["id"], crop, cls, name, conf, sev, advice,
             f"-{i*7 + 2} days"))


def seed_pest_history(user_ids: list[int]) -> None:
    if db.table_count("pest_reports"):
        return
    fields = db.query("SELECT * FROM fields")
    pests = [("Tomato", "Fruit borer", "high", "12% fruit damage observed; pheromone traps advised."),
             ("Grape", "Thrips", "moderate", "Thrips above ETL on 3 of 10 sampled bunches."),
             ("Maize", "Fall armyworm", "high", "Whorl damage in 8% plants; sand+insecticide whorl fill."),
             ("Onion", "Thrips", "moderate", "Silvering on 15% leaves; blue sticky traps advised.")]
    for i, (crop, pest, risk, detail) in enumerate(pests):
        fld = next((f for f in fields if f["crop"] == crop), fields[0])
        db.execute(
            """INSERT INTO pest_reports (user_id, field_id, crop, pest, risk_level, detail,
               created_at) VALUES (?,?,?,?,?,?, datetime('now', ?))""",
            (user_ids[0], fld["id"], crop, pest, risk, detail, f"-{i*4 + 1} days"))


def seed_sales(user_ids: list[int]) -> None:
    if db.table_count("sales"):
        return
    crops = ["Grape", "Onion", "Tomato", "Maize"]
    for i, crop in enumerate(crops):
        prof = get_crop(crop)
        row = db.query_one(
            """SELECT modal_price FROM market_prices WHERE crop=? AND mandi LIKE 'Nashik%'
               ORDER BY date DESC LIMIT 1 OFFSET ?""", (crop, 90 + i * 15))
        price = row["modal_price"] if row else prof.base_price_per_q
        db.execute(
            "INSERT INTO sales (field_id, crop, mandi, quantity_q, price_per_q, date) VALUES (?,?,?,?,?,?)",
            (None, crop, "Nashik APMC (Lasalgaon)", round(RNG.uniform(20, 90), 1),
             price, (TODAY - timedelta(days=90 + i * 20)).isoformat()))


def save_trial_csv(path: str) -> list[dict]:
    rows = build_trial_rows()
    import csv
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def main() -> None:
    db.init_db(DB_PATH)
    print(f"[db] {DB_PATH}")
    if not db.table_count("users"):
        ids = seed_users_farms()
        print(f"[seed] users={len(ids)} farms={db.table_count('farms')} fields={db.table_count('fields')}")
        seed_soil_and_logs()
        print(f"[seed] soil={db.table_count('soil_readings')} irrigation={db.table_count('irrigation_logs')} fertilizer={db.table_count('fertilizer_logs')}")
        seed_disease_history(ids)
        seed_pest_history(ids)
        seed_sales(ids)
        print(f"[seed] disease={db.table_count('disease_reports')} pests={db.table_count('pest_reports')} sales={db.table_count('sales')}")
    else:
        print("[seed] users already present, skipping user/farm seeding")

    if not db.table_count("weather_daily"):
        for farm in db.query("SELECT id FROM farms"):
            seed_weather(farm["id"])
        print(f"[seed] weather={db.table_count('weather_daily')}")
    else:
        print("[seed] weather already present")

    if not db.table_count("market_prices"):
        seed_market_prices()
        print(f"[seed] market_prices={db.table_count('market_prices')}")
    else:
        print("[seed] market prices already present")

    trial_path = os.path.join(os.path.dirname(DB_PATH), "regional_trials.csv")
    if not os.path.exists(trial_path):
        rows = save_trial_csv(trial_path)
        print(f"[seed] regional trials -> {trial_path} ({len(rows)} rows)")
    else:
        print("[seed] regional trials already present")
    print("[done] seed complete")


if __name__ == "__main__":
    main()
