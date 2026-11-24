"""
Sub-field sector telemetry for the Interactive Farm Digital Twin.

Each field is divided into four virtual LoRaWAN sensor sectors.  The values are
deterministic per (field, sector) so the twin is stable between page loads, and
they are persisted in the `twin_sectors` table so closed-loop actions taken in
the UI (e.g. executing a fungicide prescription) permanently change the stored
telemetry.
"""
from __future__ import annotations

import hashlib

from .. import db

SECTOR_DEFS = [
    ("SEC-A1", "North – Vegetative Sector", "vegetative",
     "Uniform canopy establishment; vegetative phase peaking with rising N demand."),
    ("SEC-B1", "East – Blossom Plot", "flowering",
     "Active flowering cluster; monitor Ca demand and blossom drop under heat."),
    ("SEC-C2", "South Ridge – Infection Zone", "infection",
     "Elevated Alternaria solani signature flagged by the canopy model; treatment block."),
    ("SEC-D1", "West Hydro-Drip Block", "drip",
     "Drip laterals 8–16 under high-frequency fertigation; stable root-zone VWC."),
]

_BASE = {
    "vegetative": dict(health=91, vwc=34, npk=(142, 41, 186), temp=22.1),
    "flowering":  dict(health=88, vwc=30, npk=(128, 46, 172), temp=22.6),
    "infection":  dict(health=47, vwc=38, npk=(118, 36, 150), temp=23.4),
    "drip":       dict(health=85, vwc=31, npk=(135, 44, 180), temp=21.9),
}


def _jit(field_id: int, code: str, salt: str, span: float) -> float:
    h = hashlib.md5(f"{field_id}:{code}:{salt}".encode()).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF - 0.5) * 2 * span


def _status(health: float, role: str) -> str:
    if role == "infection" and health < 60:
        return "alert"
    return "ok" if health >= 80 else "watch" if health >= 60 else "alert"


def ensure_sectors(field_id: int) -> list[dict]:
    rows = db.query("SELECT * FROM twin_sectors WHERE field_id=? ORDER BY code", (field_id,))
    if rows:
        return rows
    for code, name, role, note in SECTOR_DEFS:
        b = _BASE[role]
        health = round(b["health"] + _jit(field_id, code, "h", 4), 0)
        vwc = round(b["vwc"] + _jit(field_id, code, "v", 2.5), 1)
        n = round(b["npk"][0] + _jit(field_id, code, "n", 8), 0)
        p = round(b["npk"][1] + _jit(field_id, code, "p", 4), 0)
        k = round(b["npk"][2] + _jit(field_id, code, "k", 9), 0)
        t = round(b["temp"] + _jit(field_id, code, "t", 0.6), 1)
        db.execute(
            """INSERT OR IGNORE INTO twin_sectors
               (field_id, code, name, role, npk_n, npk_p, npk_k, health_idx, vwc,
                soil_temp_c, status, note)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (field_id, code, name, role, n, p, k, health, vwc, t,
             _status(health, role), note))
    return db.query("SELECT * FROM twin_sectors WHERE field_id=? ORDER BY code", (field_id,))


def treat_infection_sector(field_id: int, gain: float = 18.0) -> None:
    """Closed-loop feedback: executing a fungicide prescription heals SEC-C2."""
    rows = db.query("SELECT * FROM twin_sectors WHERE field_id=? AND role='infection'",
                    (field_id,))
    for r in rows:
        health = min(72.0, r["health_idx"] + gain)
        db.execute("UPDATE twin_sectors SET health_idx=?, status=?, vwc=ROUND(vwc-2.0,1), "
                   "note=? WHERE id=?",
                   (health, _status(health, "ok"),
                    "Fungicide executed in-silico; defoliation pressure receding, "
                    "micro-climate humidity being pulled below 70%.", r["id"]))


def log_sim_run(field_id: int, scenario: dict, recovery: float, yield_q: float,
                health: float) -> int:
    import json
    return db.execute(
        "INSERT INTO sim_runs (field_id, scenario, recovery, yield_q, health) "
        "VALUES (?,?,?,?,?)",
        (field_id, json.dumps(scenario), round(recovery, 1), round(yield_q, 2),
         round(health, 1)))
