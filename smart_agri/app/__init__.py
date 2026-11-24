"""Flask application factory for the AI-Powered Smart Agriculture System."""
from __future__ import annotations

import os

from flask import Flask, redirect, render_template, url_for
from flask import session as flask_session

from .config import SECRET_KEY, UPLOAD_DIR


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB photo uploads
    app.config["JSON_SORT_KEYS"] = False
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    from . import db
    db.init_db()

    from .routes.auth import bp as auth_bp
    from .routes.main import bp as main_bp
    from .routes.api import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.context_processor
    def inject_globals():
        user = flask_session.get("user")
        farm = None
        primary_crop = None
        cnn_acc = None
        yield_r2 = None
        if user:
            fid = flask_session.get("farm_id")
            farms = db.query("SELECT * FROM farms WHERE user_id=? ORDER BY name",
                             (user["id"],))
            farm = next((f for f in farms if f["id"] == fid), farms[0] if farms else None)
            if farm:
                row = db.query_one(
                    "SELECT crop FROM fields WHERE farm_id=? AND status='growing' "
                    "ORDER BY name LIMIT 1", (farm["id"],))
                primary_crop = row["crop"] if row else None
        try:
            from .services.disease import MODEL
            if MODEL.available:  # triggers the lazy load so meta is populated
                cnn_acc = MODEL.meta.get("test_accuracy")
        except Exception:
            cnn_acc = None
        try:
            from .services import yield_prediction as yp
            ym = yp.model_metrics()
            yield_r2 = round(ym.get("r2_kg_per_acre", 0), 3) if ym else None
        except Exception:
            yield_r2 = None
        return {
            "current_user": user,
            "current_farm_id": flask_session.get("farm_id"),
            # Templates call `inr(x)` as a function. Jinja filters only work
            # with pipe syntax (`x | inr`), so the helper must also be in the
            # template context - otherwise `inr` resolves to Undefined.
            "inr": inr,
            "farm": farm,
            "primary_crop": primary_crop,
            "cnn_acc": cnn_acc,
            "yield_r2": yield_r2,
        }

    def inr(value, decimals: int = 0) -> str:
        """Format a rupee amount with the Indian digit grouping: 1,23,45,678"""
        try:
            n = float(value)
        except (TypeError, ValueError):
            return "-"
        neg = n < 0
        n = abs(n)
        if decimals:
            whole = f"{n:.{decimals}f}"
        else:
            whole = f"{n:.0f}"
        int_part, _, frac = whole.partition(".")   # raw digits, no separators yet

        # Last three digits form one group; everything left of that groups by two.
        if len(int_part) > 3:
            head, tail = int_part[:-3], int_part[-3:]
            chunks = []
            while len(head) > 2:
                chunks.append(head[-2:])
                head = head[:-2]
            if head:
                chunks.append(head)
            int_part = ",".join(reversed(chunks)) + "," + tail

        return ("-" if neg else "") + "\u20b9" + int_part + ("." + frac if frac else "")

    # NOTE: use add_template_filter, not the @app.template_filter decorator.
    # The decorator returns None, which would rebind this name to None and
    # shadow the function inside the factory's closure.
    app.add_template_filter(inr, "inr")

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404,
                               message="That page does not exist."), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500,
                               message=f"Something broke on the server: {e}"), 500

    @app.route("/health")
    def health():
        from .services.disease import MODEL
        from .services import market as market_svc
        from .services import yield_prediction as yp
        return {
            "status": "ok",
            "disease_cnn": {"available": MODEL.available, "backend": MODEL.backend,
                            "classes": len(MODEL.class_names),
                            "test_accuracy": MODEL.meta.get("test_accuracy")},
            "yield_model": {"available": yp.model_available(), "metrics": yp.model_metrics()},
            "price_model": {"available": market_svc.model_available(),
                            "metrics": market_svc.model_metrics()},
            "database": {"users": db.table_count("users"),
                         "farms": db.table_count("farms"),
                         "fields": db.table_count("fields"),
                         "weather": db.table_count("weather_daily"),
                         "market_prices": db.table_count("market_prices")},
        }

    return app
