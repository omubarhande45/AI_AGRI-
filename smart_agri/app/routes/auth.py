"""Authentication routes - farmer login, registration, farm selection."""
from __future__ import annotations

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = db.query_one("SELECT * FROM users WHERE username=?", (username,))
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = {"id": user["id"], "username": user["username"],
                               "full_name": user["full_name"], "phone": user["phone"]}
            farm = db.query_one("SELECT * FROM farms WHERE user_id=? ORDER BY id LIMIT 1",
                                (user["id"],))
            session["farm_id"] = farm["id"] if farm else None
            return redirect(url_for("main.dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html", demo_users=_demo_users())


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip()
        farm_name = (request.form.get("farm_name") or "My Farm").strip()
        village = (request.form.get("village") or "").strip()
        district = (request.form.get("district") or "Nashik").strip()
        area = float(request.form.get("total_area") or 1.0)
        soil_type = request.form.get("soil_type") or "Medium black (loam)"
        irrigation = request.form.get("irrigation") or "drip"

        if not username or len(password) < 6:
            flash("Username is required and the password must be at least 6 characters.", "error")
            return render_template("register.html")
        if db.query_one("SELECT id FROM users WHERE username=?", (username,)):
            flash("That username is already taken.", "error")
            return render_template("register.html")

        uid = db.execute(
            "INSERT INTO users (username, password_hash, full_name) VALUES (?,?,?)",
            (username, generate_password_hash(password), full_name or username))
        fid = db.execute(
            """INSERT INTO farms (user_id, name, village, district, total_area,
               soil_type, irrigation) VALUES (?,?,?,?,?,?,?)""",
            (uid, farm_name, village, district, area, soil_type, irrigation))
        from ..seed.seed import seed_weather
        seed_weather(fid, days_back=365, days_forecast=7)

        session["user"] = {"id": uid, "username": username, "full_name": full_name}
        session["farm_id"] = fid
        flash("Account created. Add your first field from the Crops page.", "success")
        return redirect(url_for("main.crops"))
    return render_template("register.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/select-farm/<int:farm_id>")
def select_farm(farm_id: int):
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    farm = db.query_one("SELECT * FROM farms WHERE id=? AND user_id=?",
                        (farm_id, user["id"]))
    if farm:
        session["farm_id"] = farm["id"]
    return redirect(request.referrer or url_for("main.dashboard"))


def _demo_users() -> list[dict]:
    return [{"username": u["username"], "password": "farmer123", "name": u["full_name"],
             "farms": db.query_one("SELECT COUNT(*) AS n FROM farms WHERE user_id=?",
                                   (u["id"],))["n"],
             "fields": db.query_one(
                 "SELECT COUNT(*) AS n FROM fields f JOIN farms fa ON fa.id=f.farm_id "
                 "WHERE fa.user_id=?", (u["id"],))["n"]}
            for u in db.query("SELECT id, username, full_name FROM users ORDER BY id")]
