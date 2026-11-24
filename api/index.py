import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SMART_AGRI_ROOT = os.path.join(PROJECT_ROOT, "smart_agri")
if SMART_AGRI_ROOT not in sys.path:
    sys.path.insert(0, SMART_AGRI_ROOT)

from app import create_app, db

app = create_app()

if db.table_count("users") == 0:
    from app.seed.seed import main as seed_main
    seed_main()

# Vercel discovers the Flask WSGI app from this module.
