"""
Market Intelligence module.

  * price history + 90-day forecast (recursive ML model, falls back to a
    transparent seasonal-naive estimator if the model artifact is missing)
  * demand (arrivals) forecast
  * mandi comparison and recommendation (net realisation after commission and
    transport, weighted by distance and price outlook)
  * profit estimation for a field, including best-mandi selection
"""
from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ..agronomy import get_crop
from ..config import MANDIS, ML_MODEL_DIR

_CACHE: dict[str, Any] = {}
FORECAST_HORIZON = 90
# Recursive 90-step forecasts are the expensive call in this module and the
# market page needs them for every mandi plus every alternative crop, so cache
# them for the life of the process. Keyed on (crop, mandi, horizon).
_FC_CACHE: dict[tuple, dict] = {}


def _load():
    if "bundle" in _CACHE:
        return _CACHE["bundle"]
    path = os.path.join(ML_MODEL_DIR, "price_model.joblib")
    bundle = None
    if os.path.exists(path):
        try:
            bundle = joblib.load(path)
        except Exception as exc:
            print(f"[market] could not load price model: {exc}")
    _CACHE["bundle"] = bundle
    return bundle


def model_available() -> bool:
    return _load() is not None


def model_metrics() -> dict:
    b = _load()
    if not b:
        return {}
    return {"price": b.get("price_metrics", {}), "demand": b.get("demand_metrics", {})}


# ---------------------------------------------------------------------------
# Price series
# ---------------------------------------------------------------------------
def price_history(crop: str, mandi: str | None = None, days: int = 180) -> list[dict]:
    if mandi:
        rows = db_rows("SELECT date, modal_price, min_price, max_price, arrivals_t "
                       "FROM market_prices WHERE crop=? AND mandi=? ORDER BY date", (crop, mandi))
    else:
        rows = db_rows("SELECT date, AVG(modal_price) AS modal_price, AVG(min_price) AS min_price, "
                       "AVG(max_price) AS max_price, SUM(arrivals_t) AS arrivals_t "
                       "FROM market_prices WHERE crop=? GROUP BY date ORDER BY date", (crop,))
    return rows[-days:]


def db_rows(sql: str, params: tuple = ()) -> list[dict]:
    from .. import db
    return db.query(sql, params)


def _features_from_frame(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Rebuild the exact lag features the price model was trained on."""
    df = df.sort_values("date").reset_index(drop=True)
    p = df["modal_price"]
    out = pd.DataFrame(index=df.index)
    for lag in (1, 2, 3, 7, 14, 28):
        out[f"lag_{lag}"] = p.shift(lag)
    out["ma_7"] = p.shift(1).rolling(7).mean()
    out["ma_30"] = p.shift(1).rolling(30).mean()
    out["ma_7_over_ma_30"] = out["ma_7"] / out["ma_30"]
    out["ret_7"] = p.shift(1) / p.shift(8) - 1
    out["ret_28"] = p.shift(1) / p.shift(29) - 1
    out["vol_14"] = p.shift(1).pct_change().rolling(14).std()
    dt = pd.to_datetime(df["date"])
    out["month"] = dt.dt.month
    out["doy_sin"] = np.sin(2 * np.pi * dt.dt.dayofyear / 365)
    out["doy_cos"] = np.cos(2 * np.pi * dt.dt.dayofyear / 365)
    out["dow"] = dt.dt.dayofweek
    out["arrivals_lag_7"] = df["arrivals_t"].shift(7)
    out["arrivals_lag_28"] = df["arrivals_t"].shift(28)
    return out[cols]


def price_forecast(crop: str, mandi: str, horizon: int = FORECAST_HORIZON) -> dict[str, Any]:
    key = (crop, mandi, horizon)
    if key in _FC_CACHE:
        return _FC_CACHE[key]
    hist = price_history(crop, mandi, days=200)
    if len(hist) < 60:
        return {"error": "not enough price history for this crop/mandi"}

    bundle = _load()
    if bundle is None:
        return _naive_forecast(crop, mandi, hist, horizon)

    model = bundle["price_model"]
    cols = bundle["feature_cols"]

    # Rolling windows only - the lag structure never looks back further than
    # 30 days, so we keep a short deque and build one feature row per step
    # instead of re-deriving the whole history 90 times.
    from collections import deque
    W = 32
    p_hist = deque([float(r["modal_price"]) for r in hist], maxlen=W)
    a_hist = deque([float(r["arrivals_t"]) for r in hist], maxlen=W)
    last_date = datetime.strptime(hist[-1]["date"], "%Y-%m-%d").date()
    preds: list[dict] = []

    def features() -> pd.DataFrame:
        h = list(p_hist)
        arr = list(a_hist)
        f: dict[str, float] = {}
        for lag in (1, 2, 3, 7, 14, 28):
            f[f"lag_{lag}"] = h[-lag] if len(h) >= lag else h[0]
        ma7 = float(np.mean(h[-8:-1])) if len(h) >= 8 else float(np.mean(h[:-1]))
        ma30 = float(np.mean(h[-31:-1])) if len(h) >= 31 else float(np.mean(h[:-1]))
        f["ma_7"] = ma7
        f["ma_30"] = ma30
        f["ma_7_over_ma_30"] = ma7 / ma30 if ma30 else 1.0
        f["ret_7"] = (h[-1] / h[-8] - 1) if len(h) >= 8 else 0.0
        f["ret_28"] = (h[-1] / h[-29] - 1) if len(h) >= 29 else 0.0
        diffs = np.diff(h[-15:])
        f["vol_14"] = float(np.std(diffs / np.clip(h[-15:-1], 1, None))) if len(diffs) > 2 else 0.0
        d = last_date + timedelta(days=len(preds) + 1)
        f["month"] = d.month
        f["doy_sin"] = math.sin(2 * math.pi * d.timetuple().tm_yday / 365)
        f["doy_cos"] = math.cos(2 * math.pi * d.timetuple().tm_yday / 365)
        f["dow"] = d.weekday()
        f["arrivals_lag_7"] = arr[-7] if len(arr) >= 7 else arr[0]
        f["arrivals_lag_28"] = arr[-28] if len(arr) >= 28 else arr[0]
        return pd.DataFrame([[f[c] for c in cols]], columns=cols)

    for h in range(1, horizon + 1):
        d = last_date + timedelta(days=h)
        X = features()
        if X.isna().any(axis=None):
            break
        next_p = float(model.predict(X)[0])
        next_p = max(next_p, p_hist[-1] * 0.55)
        next_p = min(next_p, p_hist[-1] * 1.9)
        preds.append({"date": d.isoformat(), "predicted_price": round(next_p, 0), "horizon": h})
        p_hist.append(next_p)
        a_hist.append(float(np.mean(list(a_hist)[-28:])))

    prices = [p["predicted_price"] for p in preds]
    arr = np.array(list(a_hist)[-len(prices):], dtype=float)
    hist_arr = np.array([r["arrivals_t"] for r in hist[-28:]], dtype=float)
    demand_ratio = float(np.mean(arr) / max(np.mean(hist_arr), 1e-6)) if len(arr) else 1.0

    result = {
        "crop": crop, "mandi": mandi, "source": "ml_model",
        "model_metrics": model_metrics().get("price", {}),
        "current_price": float(hist[-1]["modal_price"]),
        "forecast": preds,
        "forecast_7d": float(np.mean(prices[:7])),
        "forecast_30d": float(np.mean(prices[:30])),
        "forecast_60d": float(np.mean(prices[30:60])) if len(prices) >= 60 else None,
        "forecast_90d": float(np.mean(prices[60:])) if len(prices) >= 90 else None,
        "forecast_min": float(np.min(prices)), "forecast_max": float(np.max(prices)),
        "trend_pct": round(100 * (float(np.mean(prices[:30])) - hist[-1]["modal_price"])
                           / hist[-1]["modal_price"], 1),
        "price_volatility_pct": round(100 * float(np.std(prices) / max(np.mean(prices), 1)), 1),
        "demand_index": round(demand_ratio, 3),
        "trend_label": _trend_label(hist[-1]["modal_price"], float(np.mean(prices[:30]))),
    }
    _FC_CACHE[key] = result
    return result


def _naive_forecast(crop, mandi, hist, horizon) -> dict[str, Any]:
    """Seasonal-naive fallback: last year's shape, clearly labelled as fallback."""
    prof = get_crop(crop)
    last = float(hist[-1]["modal_price"])
    same_season = [h for h in hist
                   if datetime.strptime(h["date"], "%Y-%m-%d").month == (date.today().month % 12 + 1)]
    shape = float(np.mean([h["modal_price"] for h in same_season])) if same_season else last
    drift = (shape - last) / max(len(hist), 1)
    preds = []
    last_date = datetime.strptime(hist[-1]["date"], "%Y-%m-%d").date()
    for h in range(1, horizon + 1):
        v = last + drift * h
        preds.append({"date": (last_date + timedelta(days=h)).isoformat(),
                      "predicted_price": round(v, 0), "horizon": h})
    prices = [p["predicted_price"] for p in preds]
    res = {"crop": crop, "mandi": mandi, "source": "seasonal_naive_fallback",
            "current_price": last, "forecast": preds,
            "forecast_7d": float(np.mean(prices[:7])),
            "forecast_30d": float(np.mean(prices[:30])),
            "forecast_60d": float(np.mean(prices[30:60])),
            "forecast_90d": float(np.mean(prices[60:])),
            "forecast_min": float(np.min(prices)), "forecast_max": float(np.max(prices)),
            "trend_pct": round(100 * (np.mean(prices[:30]) - last) / last, 1),
            "price_volatility_pct": round(100 * float(np.std(prices) / max(np.mean(prices), 1)), 1),
            "demand_index": 1.0,
            "trend_label": _trend_label(last, float(np.mean(prices[:30])))}
    _FC_CACHE[key] = res
    return res


def _trend_label(now: float, next30: float) -> str:
    chg = (next30 - now) / max(now, 1) * 100
    if chg > 6: return "rising"
    if chg < -6: return "falling"
    return "stable"


# ---------------------------------------------------------------------------
# Mandi intelligence
# ---------------------------------------------------------------------------
def mandi_comparison(crop: str, harvest_date: str | None = None,
                     horizon: int = FORECAST_HORIZON) -> list[dict[str, Any]]:
    """Compare every mandi on net realisation per quintal, adjusted for the
    price outlook at the expected selling time."""
    prof = get_crop(crop)
    if prof is None:
        return []
    harvest = _parse_date(harvest_date)
    rows = db_rows(
        "SELECT mandi, AVG(modal_price) AS avg30, COUNT(*) AS n, AVG(arrivals_t) AS arrivals "
        "FROM market_prices WHERE crop=? AND date >= ? GROUP BY mandi",
        (crop, (date.today() - timedelta(days=30)).isoformat()))
    by_mandi = {r["mandi"]: r for r in rows}

    out = []
    for name, district, dist_km, commission, transport in MANDIS:
        r = by_mandi.get(name)
        if not r:
            continue
        avg30 = float(r["avg30"])
        fc = price_forecast(crop, name, horizon=horizon)
        # price at the expected selling date, if we know it
        expected = None
        if fc.get("forecast") and harvest:
            for p in fc["forecast"]:
                if _parse_date(p["date"]) >= harvest:
                    expected = p["predicted_price"]
                    break
            expected = expected or fc["forecast"][-1]["predicted_price"]
        base = expected or fc.get("forecast_30d") or avg30
        commission_amt = base * commission / 100.0
        net = base - commission_amt - transport
        spoil = max(0.0, (dist_km / 100.0) * (1.0 / max(prof.shelf_life_days, 1)) * 12)
        net_after_loss = net * (1 - spoil / 100.0)
        out.append({
            "mandi": name, "district": district, "distance_km": dist_km,
            "commission_pct": commission, "transport_inr_per_q": transport,
            "current_price_inr_q": round(avg30, 0),
            "price_at_harvest_inr_q": round(float(base), 0) if expected else None,
            "forecast_30d_inr_q": round(float(fc.get("forecast_30d") or 0), 0),
            "trend": fc.get("trend_label"),
            "trend_pct": fc.get("trend_pct"),
            "demand_index": fc.get("demand_index"),
            "avg_arrivals_t": round(float(r["arrivals"]), 1),
            "commission_inr_q": round(commission_amt, 0),
            "net_realisation_inr_q": round(net, 0),
            "transit_loss_pct": round(spoil, 2),
            "net_after_transit_loss_inr_q": round(net_after_loss, 0),
            "forecast_source": fc.get("source"),
        })
    out.sort(key=lambda d: d["net_after_transit_loss_inr_q"], reverse=True)
    if out:
        best = out[0]["net_after_transit_loss_inr_q"]
        for d in out:
            d["vs_best_pct"] = round(100 * (d["net_after_transit_loss_inr_q"] - best)
                                     / max(best, 1), 1)
    return out


def best_mandi(crop: str, harvest_date: str | None = None) -> dict[str, Any] | None:
    rows = mandi_comparison(crop, harvest_date)
    return rows[0] if rows else None


def demand_outlook(crop: str) -> dict[str, Any]:
    """Next 90 days demand (arrivals proxy) vs the trailing 30 days."""
    prof = get_crop(crop)
    rows = db_rows(
        "SELECT date, SUM(arrivals_t) AS arrivals, AVG(modal_price) AS price "
        "FROM market_prices WHERE crop=? GROUP BY date ORDER BY date", (crop,))
    if len(rows) < 40:
        return {"error": "insufficient market history"}
    df = pd.DataFrame(rows)
    last30 = float(df["arrivals"].tail(30).mean())
    doy = date.today().timetuple().tm_yday
    # same calendar window from the previous year
    prev = df[df["date"].apply(
        lambda s: abs(datetime.strptime(s, "%Y-%m-%d").timetuple().tm_yday - doy) < 45)]
    seasonal_ref = float(prev["arrivals"].mean()) if len(prev) else last30
    index = last30 / max(seasonal_ref, 1e-6)
    return {
        "crop": crop,
        "arrivals_last30_t_per_day": round(last30, 1),
        "seasonal_reference_t_per_day": round(seasonal_ref, 1),
        "demand_index": round(index, 3),
        "interpretation": ("Arrivals below the seasonal norm - supply is tight, "
                           "sellers have bargaining power" if index < 0.92 else
                           "Arrivals above the seasonal norm - the market is glutted, "
                           "consider storage or an alternate mandi" if index > 1.08 else
                           "Arrivals in line with the seasonal norm - normal trading"),
        "glut_risk": "high" if index > 1.15 else "moderate" if index > 1.05 else "low",
        "price_now": round(float(df["price"].tail(7).mean()), 0),
        "recommended_action": _demand_action(index, prof),
    }


def _demand_action(index: float, prof) -> str:
    if prof is None:
        return "Check mandi arrivals before dispatch."
    if index > 1.08:
        return (f"Market is glutted. {prof.name} keeps {prof.shelf_life_days} days - "
                f"hold harvest and dispatch in tranches to Lasalgaon and Pune.")
    if index < 0.92:
        return (f"Supply is tight and prices are firm. Harvest at the earliest "
                f"safe maturity and sell the full lot in one trip.")
    return "Normal arrivals. Sell on a 7-10 day schedule and track the mandi bulletin daily."


# ---------------------------------------------------------------------------
# Profit estimation
# ---------------------------------------------------------------------------
def estimate_profit(crop: str, area_acres: float, yield_q: float,
                    mandi: str | None = None,
                    extra_cost_inr: float = 0.0) -> dict[str, Any]:
    prof = get_crop(crop)
    if prof is None:
        return {"error": f"unknown crop {crop}"}
    rows = mandi_comparison(crop)
    if not rows:
        return {"error": "no market data for this crop"}
    target = next((r for r in rows if r["mandi"] == mandi), None) or rows[0]

    gross = yield_q * target["net_after_transit_loss_inr_q"]
    base_cost = prof.cost_per_acre * area_acres + extra_cost_inr
    # Fertilizer/pesticide plan costs are already inside cost_per_acre; keep them
    # separate only if the caller supplies a replacement figure.
    net = gross - base_cost
    margin = net / max(gross, 1) * 100

    # Sensitivity: +/- 15% yield and +/- 10% price
    sens = []
    for dy, dp, label in ((-0.15, -0.10, "pessimistic"), (0, 0, "expected"), (0.15, 0.10, "optimistic")):
        g = yield_q * (1 + dy) * target["net_after_transit_loss_inr_q"] * (1 + dp)
        sens.append({"scenario": label, "yield_q": round(yield_q * (1 + dy), 2),
                     "price_inr_q": round(target["net_after_transit_loss_inr_q"] * (1 + dp), 0),
                     "gross_inr": round(g, 0), "net_inr": round(g - base_cost, 0)})

    breakeven_q = base_cost / max(target["net_after_transit_loss_inr_q"], 1)
    return {
        "crop": crop, "area_acres": area_acres,
        "mandi": target["mandi"], "mandi_rank": rows.index(target) + 1,
        "yield_q": round(yield_q, 2),
        "net_price_inr_q": target["net_after_transit_loss_inr_q"],
        "gross_revenue_inr": round(gross, 0),
        "cost_breakdown_inr": prof.cost_breakdown,
        "total_cost_inr": round(base_cost, 0),
        "cost_per_acre_inr": round(base_cost / max(area_acres, 0.1), 0),
        "net_profit_inr": round(net, 0),
        "profit_per_acre_inr": round(net / max(area_acres, 0.1), 0),
        "margin_pct": round(margin, 1),
        "breakeven_yield_q": round(breakeven_q, 2),
        "breakeven_price_inr_q": round(prof.breakeven_price, 0),
        "roi_pct": round(net / max(base_cost, 1) * 100, 1),
        "scenarios": sens,
        "verdict": _verdict(margin, net),
    }


def _verdict(margin: float, net: float) -> str:
    if margin >= 30: return "Strong margin - this crop and market combination is worth scaling."
    if margin >= 15: return "Healthy margin - proceed, but lock in the mandi before harvest."
    if margin >= 5:  return "Thin margin - cut input cost or shift to the higher-paying mandi."
    return "Loss-making at these prices - consider storage, an alternate mandi or a different crop."


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def crop_alternatives(farm_soil: str, area: float, season: str,
                      horizon: int = 30) -> list[dict[str, Any]]:
    """Which crop would earn most right now on this land?

    This ranks up to 14 crops x 7 mandis, so it uses a short forecast horizon;
    a 90-day recursive forecast per pair would make the page take minutes.
    """
    out = []
    for name, prof in _all_crops().items():
        if season and season not in prof.seasons:
            continue
        rows = mandi_comparison(name, horizon=horizon)
        if not rows:
            continue
        net_q = rows[0]["net_after_transit_loss_inr_q"]
        yield_q = prof.yield_kg_per_acre * area / 100.0
        gross = yield_q * net_q
        cost = prof.cost_per_acre * area
        out.append({"crop": name, "best_mandi": rows[0]["mandi"],
                    "net_price_inr_q": net_q,
                    "expected_yield_q": round(yield_q, 1),
                    "gross_inr": round(gross, 0), "cost_inr": round(cost, 0),
                    "net_profit_inr": round(gross - cost, 0),
                    "profit_per_acre_inr": round((gross - cost) / max(area, 0.1), 0),
                    "margin_pct": round((gross - cost) / max(gross, 1) * 100, 1)})
    out.sort(key=lambda d: d["net_profit_inr"], reverse=True)
    return out


def _all_crops():
    from ..agronomy import CROPS
    return CROPS
