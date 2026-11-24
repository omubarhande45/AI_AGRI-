"""Entry point: python3 run.py  ->  http://0.0.0.0:5000"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app  # noqa: E402
from app import db  # noqa: E402
from app.config import DB_PATH  # noqa: E402

app = create_app()

# First run: create the schema and load the demo dataset.
if db.table_count("users") == 0:
    print("[setup] empty database detected - seeding demo farm data...")
    from app.seed.seed import main as seed_main
    seed_main()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
