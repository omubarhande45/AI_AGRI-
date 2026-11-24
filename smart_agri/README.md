# AI-Powered Smart Agriculture System

A working full-stack decision-support system for a farm in **Nashik, Maharashtra**.
It implements all nine modules of the project structure: User Interface, Data
Collection, Edge AI, Digital Twin, AI/ML Prediction, Market Intelligence,
Decision Support System, Database and Future Integration.

Everything here actually runs. The disease model is a real CNN trained on
43,503 leaf images; the yield and price models are real gradient-boosted
regressors fitted to the seeded data.

---

## Quick start

```bash
pip install -r requirements.txt
python3 run.py                  # http://localhost:5000
```

First run creates the SQLite schema and seeds the demo farm automatically.

**Login:** `ramesh` / `farmer123` (9 fields, 2 farms) or `sunita` / `farmer123`.

---

## Seminar and report deliverables

```
docs/Project_Progress_Seminar.pptx   22-slide deck (16:9)
docs/Project_Report.docx             ~4,800-word report, 12 chapters + 3 appendices
docs/build_seminar_pptx.py           regenerates the deck
docs/build_report_docx.py            regenerates the report
```

Both documents read their figures from `models/disease_cnn/meta.json`,
`models/ml/metrics.json` and the live database at build time, so they cannot drift
away from the code. Rebuild them any time with:

```bash
python3 docs/build_seminar_pptx.py
python3 docs/build_report_docx.py
```

The deck follows the agreed seminar order: Problem → Objectives → System
Architecture → Modules → Technologies → Workflow → Results → Expected
Output → Limitations → Future Scope.

## What is implemented

| Module | Where | What it really does |
|---|---|---|
| **1. User Interface** | `app/templates`, `app/static` | Login, dashboard, crop monitoring, disease scan, digital twin, predictions, market board, DSS, weather, profile |
| **2. Data Collection** | `app/seed/seed.py`, `app/db.py` | Crop images, soil tests, weather, IoT-style sensor readings, mandi prices |
| **3. Edge AI** | `app/services/disease.py`, `training/` | MobileNetV3-Small CNN, 38 classes, **93.86 % test accuracy**, Grad-CAM explainability, ONNX artifact for Raspberry Pi / Android |
| **4. Digital Twin** | `app/services/twin.py` | Thermal-time phenology, logistic LAI growth, soil-water balance, 6 what-if scenarios |
| **5. AI/ML Prediction** | `app/services/yield_prediction.py`, `irrigation.py`, `fertilizer.py` | Yield (median APE 8.1 %), FAO-56 Kc irrigation, NPK-balanced fertilizer plan, pest risk scoring |
| **6. Market Intelligence** | `app/services/market.py` | 90-day recursive price forecast, demand outlook, mandi net-realisation ranking, profit estimation |
| **7. Decision Support** | `app/services/dss.py` | Farm health report, ranked actions, expected yield, expected profit, best market |
| **8. Database** | `app/db.py`, SQLite | 12 tables, swappable for MySQL/Mongo by replacing this one module |
| **9. Future Integration** | `app/routes/api.py` | 14 REST endpoints for IoT sensors, drones, satellite and mobile clients |

---

## The models

### Disease CNN (`training/train_disease_cnn.py`)

* Architecture: torchvision **MobileNetV3-Small**, transfer learning from ImageNet
* Data: PlantVillage, 43,503 train / 10,878 test images, 38 classes
* Schedule: 3 epochs frozen backbone (lr 1e-3) then 4 epochs full fine-tune (lr 5e-5)
* **Result: 93.86 % accuracy, 92.74 % macro F1** on the held-out test split
* Exports a `.pt` checkpoint and an `.onnx` graph (verified 100 % prediction
  parity with PyTorch on 512 images)

Per-class F1 is in `models/disease_cnn/meta.json`. The hardest classes are the
visually similar tomato leaf spots (early blight 0.73, target spot 0.74) — this
is reported honestly rather than hidden behind the headline accuracy.

A 228-image held-out subset (6 per class) is kept in `data/validation_set/` so the
model can be re-checked without re-downloading the dataset:

`training/check_model.py` re-scores the model on that subset:

```bash
python3 training/check_model.py
```

That subset scores **92.1 %**, consistent with the 93.86 % full-split figure.
The residual errors are genuinely confusable pairs — tomato early vs late blight,
potato early vs late blight, maize Cercospora vs northern leaf blight, grape
black rot vs Esca — which is exactly where the per-class F1 scores are lowest.

```bash
python3 training/preprocess.py            # parquet -> uint8 memmap (~2.7 GB)
python3 training/train_disease_cnn.py     # ~55 min on 2 CPU cores
python3 training/finalize_disease_model.py  # eval + meta.json + ONNX
python3 training/make_demo_images.py      # 8 held-out test leaves for the demo
```

### Yield model (`training/train_ml_models.py`)

Gradient-boosted regressor on a 4,000-row regional trial network.

The target is **yield ratio** (achieved ÷ crop-typical), not raw kg/acre. Predicting
raw kilograms makes the loss dominated by banana and grape (600–1300 kg/acre) and
leaves tur and cotton (3–5 kg/acre) badly fitted — pooled MAPE was 46 %.
Normalising brought per-crop error to **8.3–16.3 %** and median APE to **8.1 %**.

### Price and demand models

One-step-ahead gradient-boosted regressor on lagged prices plus calendar
features, applied recursively for a 90-day horizon. Time-based 80/20 split:
**MAE ₹23.9/quintal, MAPE 1.13 %**. A seasonal-naive fallback is used and clearly
labelled if the artifact is missing.

---

## REST API

```
GET  /api/status                      module + model health
POST /api/disease/detect              multipart 'image' -> diagnosis + Grad-CAM
GET  /api/disease/classes             knowledge base for all 38 classes
GET  /api/yield/predict?crop=...      yield model
GET  /api/field/<id>/irrigation       7-day irrigation schedule
GET  /api/field/<id>/fertilizer       NPK gap + product plan
GET  /api/field/<id>/pest-risk        ranked pest/disease risk
GET  /api/field/<id>/twin?days=60     digital twin trajectory
GET  /api/market/prices|forecast|mandis|demand|profit
GET  /api/farm/<id>/report            full DSS pack
GET  /api/weather/<farm_id>
```

---

## Project layout

```
smart_agri/
├── run.py                     entry point
├── requirements.txt
├── app/
│   ├── __init__.py            app factory + inr() template helper
│   ├── config.py              paths, mandi table, units
│   ├── db.py                  SQLite schema + helpers
│   ├── agronomy.py            14 Maharashtra crop profiles + 38-class disease KB
│   ├── routes/                main.py (pages), api.py (REST), auth.py
│   ├── services/              disease, twin, yield_prediction, irrigation,
│   │                          fertilizer, market, dss
│   ├── seed/seed.py           Nashik demo data + regional trial network
│   ├── static/                style.css, app.js, vendored Chart.js
│   └── templates/             13 Jinja pages
├── training/                  preprocess, train_disease_cnn, finalize,
│                              train_ml_models, make_demo_images
├── models/                    disease_cnn/ (.pt + .onnx + meta.json), ml/
└── data/                      smart_agri.db, regional_trials.csv, uploads/demo
```

---

## Honest limitations

* **Weather is simulated** from Nashik climatological normals. The service
  boundary is clean — swap `app/seed/seed.py:gen_weather_day` for an OpenWeather /
  IMD API call and everything downstream keeps working.
* **Mandi prices are synthetic** but generated with trend, seasonality and
  mean-reverting noise, so the forecaster has real structure to learn. Connect
  Agmarknet for live data.
* The yield model learns a **synthetic response surface**, not real field trials.
  The agronomy behind it (Liebig-style nutrient limitation, water stress, heat
  stress) is standard, but the fitted coefficients are not calibrated to real
  Maharashtra yield data.
* PlantVillage images are lab-shot leaves on plain backgrounds. Field photos with
  complex backgrounds will score noticeably lower than 93.9 %.
* Flask's development server is fine for a seminar demo; use gunicorn in production.

---

## Technology stack

Flask · Python · scikit-learn · PyTorch + torchvision · OpenCV · ONNX Runtime ·
SQLite · Chart.js (vendored, no CDN) · NumPy / pandas
