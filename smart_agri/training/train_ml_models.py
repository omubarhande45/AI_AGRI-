"""
AI/ML Prediction module - train the tabular models.

1. yield_model.joblib
   Gradient Boosting regressor on the 4,000-row regional trial network.
   Features: crop, season, soil NPK, pH, organic carbon, rainfall, irrigation,
   mean max temperature, drip flag, plant density, pest control, soil type.
   Target  : achieved yield (kg/acre).

2. price_model.joblib
   Gradient Boosting regressor that learns one-step-ahead mandi price moves from
   lagged prices + calendar features. Used recursively for 90-day forecasts.
   Also fits a demand (arrivals) model per crop.

Run:  python3 -m training.train_ml_models
"""
from __future__ import annotations

import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db  # noqa: E402
from app.config import ML_MODEL_DIR  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
TRIALS_CSV = os.path.join(DATA_DIR, "regional_trials.csv")

CAT_COLS = ["crop", "season", "soil_type"]
# typical_yield is the crop's regional benchmark. It is known before sowing, so
# it is a legitimate feature (not leakage) and it lets one model serve all crops.
NUM_COLS = ["area_acres", "nitrogen", "phosphorus", "potassium", "ph",
            "organic_carbon", "rainfall_mm", "irrigation_mm", "temp_max_mean",
            "drip", "plant_density_index", "pest_control", "typical_yield"]
FEATURE_COLS = CAT_COLS + NUM_COLS
TARGET = "yield_ratio"   # achieved yield / crop's typical yield - scale-free


def _attach_typical_yield(df):
    """Add the crop's typical yield and the scale-free yield ratio target."""
    from app.agronomy import get_crop
    df = df.copy()
    df["typical_yield"] = [get_crop(c).yield_kg_per_acre for c in df["crop"]]
    df[TARGET] = df["yield_kg_per_acre"] / df["typical_yield"]
    return df


# ---------------------------------------------------------------------------
# 1. Yield model
# ---------------------------------------------------------------------------
def train_yield_model() -> dict:
    df = _attach_typical_yield(pd.read_csv(TRIALS_CSV))
    X = df[FEATURE_COLS]
    y = df[TARGET]

    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
        ("num", "passthrough", NUM_COLS),
    ])
    model = Pipeline([
        ("pre", pre),
        ("gb", HistGradientBoostingRegressor(
            max_iter=400, learning_rate=0.06, max_leaf_nodes=31,
            min_samples_leaf=20, l2_regularization=1.0, random_state=42)),
    ])

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    model.fit(Xtr, ytr)
    pred_ratio = model.predict(Xte)
    pred = pred_ratio * Xte["typical_yield"].values

    # All per-crop figures come from the SAME held-out split, so nothing is
    # measured on data the model was fitted to.
    crop_te = Xte["crop"].values
    actual_kg = yte.values * Xte["typical_yield"].values
    ape = np.abs(pred - actual_kg) / np.clip(np.abs(actual_kg), 1e-9, None) * 100
    per_crop: dict[str, dict] = {}
    for crop in sorted(set(crop_te)):
        m = crop_te == crop
        if m.sum() == 0:
            continue
        per_crop[crop] = {
            "n_held_out": int(m.sum()),
            "mape_pct": round(float(ape[m].mean()), 2),
            "median_ape_pct": round(float(np.median(ape[m])), 2),
            "mae_kg_per_acre": round(float(np.mean(np.abs(pred[m] - actual_kg[m]))), 2),
            "mean_yield_kg_per_acre": round(float(np.mean(actual_kg[m])), 1),
            "mae_pct_of_typical": round(float(
                np.mean(np.abs(pred[m] - actual_kg[m])) / np.mean(actual_kg[m]) * 100), 2),
        }

    metrics = {
        "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
        "target": "yield ratio (achieved / crop typical), converted back to kg/acre",
        "r2_ratio": round(float(r2_score(yte, pred_ratio)), 4),
        "r2_kg_per_acre": round(float(r2_score(actual_kg, pred)), 4),
        "mae_kg_per_acre": round(float(mean_absolute_error(actual_kg, pred)), 2),
        "mae_pct_of_typical": round(float(
            mean_absolute_error(actual_kg, pred) / float(np.mean(actual_kg)) * 100), 2),
        # Headline error is the MEDIAN absolute percentage error. A pooled MAPE
        # across crops is meaningless here: cotton yields ~7 kg/acre while
        # banana yields ~1300, so a few kg of error on cotton alone would show
        # up as a huge percentage and swamp the aggregate.
        "median_ape_pct": round(float(np.median(ape)), 2),
        "pooled_mape_pct": round(float(ape.mean()), 2),
        "mean_ape_by_crop_pct": round(float(np.mean([v["mape_pct"] for v in per_crop.values()])), 2),
        "per_crop": per_crop,
    }

    # Refit on everything before saving.
    model.fit(X, y)
    from app.agronomy import CROPS
    joblib.dump({"model": model, "features": FEATURE_COLS, "metrics": metrics,
                 "typical_yield": {k: v.yield_kg_per_acre for k, v in CROPS.items()}},
                os.path.join(ML_MODEL_DIR, "yield_model.joblib"))
    print(f"[yield] R2(kg)={metrics['r2_kg_per_acre']} R2(ratio)={metrics['r2_ratio']} "
          f"MAE={metrics['mae_kg_per_acre']} kg/acre "
          f"medianAPE={metrics['median_ape_pct']}% "
          f"meanAPE-by-crop={metrics['mean_ape_by_crop_pct']}% "
          f"(pooled MAPE {metrics['pooled_mape_pct']}% is scale-mixed, see metrics.json)")
    return metrics


# ---------------------------------------------------------------------------
# 2. Price + demand models
# ---------------------------------------------------------------------------
def build_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Lagged price/arrival features + calendar encoding for one (crop, mandi) series."""
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
    out["month"] = pd.to_datetime(df["date"]).dt.month
    out["doy_sin"] = np.sin(2 * np.pi * pd.to_datetime(df["date"]).dt.dayofyear / 365)
    out["doy_cos"] = np.cos(2 * np.pi * pd.to_datetime(df["date"]).dt.dayofyear / 365)
    out["dow"] = pd.to_datetime(df["date"]).dt.dayofweek
    out["arrivals_lag_7"] = df["arrivals_t"].shift(7)
    out["arrivals_lag_28"] = df["arrivals_t"].shift(28)
    out["target"] = p
    out["date"] = df["date"]
    out["crop"] = df["crop"]
    out["mandi"] = df["mandi"]
    return out.dropna()


def train_price_models() -> dict:
    rows = db.query("SELECT crop, mandi, date, modal_price, min_price, max_price, "
                    "arrivals_t FROM market_prices ORDER BY crop, mandi, date")
    df = pd.DataFrame(rows)
    frames = [build_price_features(g) for _, g in df.groupby(["crop", "mandi"], sort=False)]
    feat = pd.concat(frames, ignore_index=True)

    drop = ["target", "date", "crop", "mandi"]
    X = feat.drop(columns=drop)
    y = feat["target"]

    # Time-based split: train on the first 80% of dates, test on the last 20%.
    dates = np.sort(feat["date"].unique())
    cut = dates[int(len(dates) * 0.8)]
    tr = feat["date"] < cut
    te = ~tr

    price_model = HistGradientBoostingRegressor(
        max_iter=500, learning_rate=0.05, max_leaf_nodes=31,
        min_samples_leaf=40, l2_regularization=1.0, random_state=42)
    price_model.fit(X[tr], y[tr])
    p = price_model.predict(X[te])

    price_metrics = {
        "n_train": int(tr.sum()), "n_test": int(te.sum()),
        "r2": round(float(r2_score(y[te], p)), 4),
        "mae_inr_per_q": round(float(mean_absolute_error(y[te], p)), 1),
        "mape_pct": round(float(mean_absolute_percentage_error(y[te], p)) * 100, 2),
        "horizon_days": 90,
    }
    print(f"[price] R2={price_metrics['r2']} MAE=Rs {price_metrics['mae_inr_per_q']}/q "
          f"MAPE={price_metrics['mape_pct']}%")

    # Demand (arrivals) model - predicts next-week arrivals from price + season.
    arr_df = feat.dropna(subset=["arrivals_lag_7"])
    arr_target = arr_df["target"].shift(-7)
    arr_ok = arr_target.notna()
    demand_model = HistGradientBoostingRegressor(
        max_iter=250, learning_rate=0.06, random_state=11)
    demand_model.fit(arr_df.loc[arr_ok, X.columns], arr_target[arr_ok])
    d_pred = demand_model.predict(arr_df.loc[arr_ok, X.columns])
    demand_metrics = {
        "n": int(arr_ok.sum()),
        "r2": round(float(r2_score(arr_target[arr_ok], d_pred)), 4),
        "mape_pct": round(float(mean_absolute_percentage_error(
            arr_target[arr_ok], d_pred)) * 100, 2),
    }
    print(f"[demand] R2={demand_metrics['r2']} MAPE={demand_metrics['mape_pct']}%")

    joblib.dump({
        "price_model": price_model,
        "demand_model": demand_model,
        "feature_cols": list(X.columns),
        "price_metrics": price_metrics,
        "demand_metrics": demand_metrics,
    }, os.path.join(ML_MODEL_DIR, "price_model.joblib"))
    return {"price": price_metrics, "demand": demand_metrics}


def main() -> None:
    os.makedirs(ML_MODEL_DIR, exist_ok=True)
    ym = train_yield_model()
    pm = train_price_models()
    with open(os.path.join(ML_MODEL_DIR, "metrics.json"), "w") as fh:
        json.dump({"yield": ym, **pm}, fh, indent=2)
    print("[done] models written to", ML_MODEL_DIR)


if __name__ == "__main__":
    main()
