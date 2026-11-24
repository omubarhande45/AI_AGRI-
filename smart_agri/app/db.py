"""SQLite access layer.

Plain sqlite3 with a row factory -> dict helper. No ORM, so the project stays
easy to read and easy to port to MySQL (swap this module only).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable

from .config import DB_PATH

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    phone         TEXT,
    language      TEXT DEFAULT 'en',
    role          TEXT DEFAULT 'farmer',
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS farms (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    village      TEXT,
    district     TEXT,
    state        TEXT DEFAULT 'Maharashtra',
    total_area   REAL NOT NULL,            -- acres
    lat          REAL,
    lon          REAL,
    soil_type    TEXT,
    irrigation   TEXT,                     -- drip / sprinkler / flood / rainfed
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fields (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id        INTEGER NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    area_acres     REAL NOT NULL,
    crop           TEXT NOT NULL,
    variety        TEXT,
    sowing_date    TEXT,
    expected_harvest TEXT,
    season         TEXT,                   -- kharif / rabi / summer
    status         TEXT DEFAULT 'growing', -- growing / harvested / fallow
    health_score   REAL DEFAULT 100.0
);

CREATE TABLE IF NOT EXISTS soil_readings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id      INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    recorded_at   TEXT DEFAULT (date('now')),
    nitrogen      REAL,   -- kg/ha
    phosphorus    REAL,   -- kg/ha
    potassium     REAL,   -- kg/ha
    ph            REAL,
    organic_carbon REAL,  -- %
    moisture      REAL,   -- % volumetric
    ec            REAL    -- dS/m
);

CREATE TABLE IF NOT EXISTS weather_daily (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id     INTEGER NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    temp_min    REAL,
    temp_max    REAL,
    humidity    REAL,
    rainfall_mm REAL,
    wind_kmph   REAL,
    solar_mj    REAL,     -- MJ/m2/day
    condition   TEXT,
    is_forecast INTEGER DEFAULT 0,
    UNIQUE(farm_id, date)
);

CREATE TABLE IF NOT EXISTS market_prices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    crop       TEXT NOT NULL,
    mandi      TEXT NOT NULL,
    date       TEXT NOT NULL,
    modal_price REAL NOT NULL,   -- INR per quintal
    min_price  REAL,
    max_price  REAL,
    arrivals_t REAL,            -- tonnes
    UNIQUE(crop, mandi, date)
);

CREATE TABLE IF NOT EXISTS disease_reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    field_id     INTEGER REFERENCES fields(id) ON DELETE SET NULL,
    crop         TEXT,
    disease_class TEXT,
    disease_name TEXT,
    confidence   REAL,
    severity     TEXT,
    image_path   TEXT,
    advice       TEXT,
    source       TEXT DEFAULT 'edge_ai',
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pest_reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    field_id     INTEGER REFERENCES fields(id) ON DELETE SET NULL,
    crop         TEXT,
    pest         TEXT,
    risk_level   TEXT,
    detail       TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS irrigation_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id    INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    date        TEXT DEFAULT (date('now')),
    water_mm    REAL,
    method      TEXT,
    source      TEXT DEFAULT 'manual'   -- manual / recommended
);

CREATE TABLE IF NOT EXISTS fertilizer_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id    INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    date        TEXT DEFAULT (date('now')),
    product     TEXT,
    dose_kg_per_acre REAL,
    nutrient    TEXT
);

CREATE TABLE IF NOT EXISTS recommendations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    field_id     INTEGER REFERENCES fields(id) ON DELETE SET NULL,
    kind         TEXT NOT NULL,   -- irrigation / fertilizer / pesticide / market / agronomy
    title        TEXT NOT NULL,
    detail       TEXT,
    priority     TEXT DEFAULT 'medium',  -- high / medium / low
    status       TEXT DEFAULT 'open',    -- open / done / ignored
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS twin_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id    INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    lai         REAL,     -- leaf area index
    biomass_kg  REAL,     -- kg/ha dry matter
    ndvi        REAL,
    soil_moist  REAL,
    water_stress REAL,
    yield_kg_ha REAL,
    health_score REAL,
    scenario    TEXT DEFAULT 'baseline'
);

CREATE TABLE IF NOT EXISTS sales (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id    INTEGER REFERENCES fields(id) ON DELETE SET NULL,
    crop        TEXT,
    mandi       TEXT,
    quantity_q  REAL,
    price_per_q REAL,
    date        TEXT DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS twin_sectors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id    INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,          -- SEC-A1 ..
    name        TEXT NOT NULL,
    role        TEXT NOT NULL,          -- vegetative / flowering / infection / drip
    npk_n       REAL, npk_p REAL, npk_k REAL,
    health_idx  REAL,                   -- 0..100 plant health index
    vwc         REAL,                   -- volumetric water content %
    soil_temp_c REAL,
    status      TEXT,                   -- ok / watch / alert
    note        TEXT,
    UNIQUE(field_id, code)
);

CREATE TABLE IF NOT EXISTS sim_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id    INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    scenario    TEXT NOT NULL,          -- json of the perturbations
    recovery    REAL,                   -- predicted dry-matter recovery 0..100
    yield_q     REAL,
    health      REAL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mp_crop_date ON market_prices(crop, date);
CREATE INDEX IF NOT EXISTS idx_wx_farm_date ON weather_daily(farm_id, date);
CREATE INDEX IF NOT EXISTS idx_soil_field   ON soil_readings(field_id, recorded_at);
"""


def init_db(path: str | None = None) -> None:
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with sqlite3.connect(path) as con:
        con.executescript(SCHEMA)
        con.commit()


@contextmanager
def get_conn(path: str | None = None):
    con = sqlite3.connect(path or DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def query(sql: str, params: Iterable[Any] = (), path: str | None = None) -> list[dict]:
    with get_conn(path) as con:
        return [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = (), path: str | None = None) -> dict | None:
    rows = query(sql, params, path)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = (), path: str | None = None) -> int:
    with get_conn(path) as con:
        cur = con.execute(sql, tuple(params))
        return cur.lastrowid or cur.rowcount


def executemany(sql: str, seq: Iterable[Iterable[Any]], path: str | None = None) -> None:
    with get_conn(path) as con:
        con.executemany(sql, [tuple(s) for s in seq])


def table_count(table: str, path: str | None = None) -> int:
    row = query_one(f"SELECT COUNT(*) AS n FROM {table}", (), path)
    return int(row["n"]) if row else 0
