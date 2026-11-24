"""Global configuration for the AI-Powered Smart Agriculture System."""
from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

DB_PATH = os.path.join(DATA_DIR, "smart_agri.db")

# --- Disease CNN (Edge AI module) -------------------------------------------
DISEASE_MODEL_DIR = os.path.join(MODEL_DIR, "disease_cnn")
DISEASE_MODEL_FILE = os.path.join(DISEASE_MODEL_DIR, "plant_disease_cnn.pt")
DISEASE_META_FILE = os.path.join(DISEASE_MODEL_DIR, "meta.json")
DISEASE_INPUT_SIZE = 128
DISEASE_CONFIDENCE_FLOOR = 0.35  # below this we report "uncertain / re-shoot"

# --- Tabular ML models (AI/ML Prediction module) ----------------------------
ML_MODEL_DIR = os.path.join(MODEL_DIR, "ml")

# --- Region / market defaults (Nashik, Maharashtra) -------------------------
DEFAULT_REGION = "Nashik, Maharashtra"
MANDIS = [
    # name, district, distance_km, commission_pct, transport_per_quintal
    ("Nashik APMC (Lasalgaon)", "Nashik", 0, 1.5, 0),
    ("Pimpalgaon Basvant APMC", "Nashik", 24, 1.5, 45),
    ("Dindori APMC", "Nashik", 28, 1.5, 55),
    ("Sinnar APMC", "Nashik", 42, 1.5, 70),
    ("Yeola APMC", "Nashik", 62, 1.5, 95),
    ("Pune APMC (Gultekdi)", "Pune", 195, 2.0, 260),
    ("Mumbai APMC (Vashi)", "Mumbai", 165, 2.5, 240),
]

SECRET_KEY = os.environ.get("SMART_AGRI_SECRET", "smart-agri-dev-key-change-me")

# Currency / units used across the app
CURRENCY = "INR"
AREA_UNIT = "acre"          # 1 acre = 0.404686 ha
ACRE_TO_HA = 0.404686
QUINTAL = 100               # kg
