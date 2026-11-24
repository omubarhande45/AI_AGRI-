"""
Build the Project Progress Seminar deck.

Slide order follows the agreed seminar structure:
  Problem -> Objectives -> System Architecture -> Modules -> Technologies
  -> Workflow -> Expected Output -> Future Scope

Run:  python3 docs/build_seminar_pptx.py
"""
from __future__ import annotations

import os
import sys

from pptx import Presentation
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx_helpers import (AMBER, BLUE, DARK, DIM, GREEN, LEAF, LINE, MUTED, OUT,
                          PANEL, PANEL2, RED, TEXT, W, H, arrow, box, bullets,
                          down_arrow, footer, kpi, metrics, slide, table, txt,
                          title_bar)

M = metrics()
CNN, ML, DB = M["cnn"], M["ml"], M["db"]
ACC = f"{CNN['test_accuracy']*100:.2f}%"
F1 = f"{CNN['test_macro_f1']*100:.2f}%"
YLD = ML["yield"]; PRC = ML["price"]; DMD = ML["demand"]

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
SLIDES: list = []


def new(**kw):
    s = slide(prs, **kw)
    SLIDES.append(s)
    return s


# ---------------------------------------------------------------- 1. TITLE
s = new()
box(s, 0, 0, W, Inches(7.5), fill=DARK, line=None, radius=0)
box(s, Inches(0), Inches(0), Inches(0.22), H, fill=GREEN, line=None, radius=0)
txt(s, Inches(0.9), Inches(1.05), Inches(11.5), Inches(0.35),
    "PROJECT PROGRESS SEMINAR", size=12, color=GREEN, bold=True)
txt(s, Inches(0.9), Inches(1.5), Inches(11.6), Inches(1.6),
    "AI-Powered Smart\nAgriculture System", size=44, color=TEXT, bold=True, spacing=1.02)
txt(s, Inches(0.9), Inches(3.35), Inches(11.4), Inches(0.9),
    "Edge AI disease detection  ·  Digital Twin  ·  Yield & price prediction  ·  "
    "Market intelligence  ·  Decision support", size=14.5, color=MUTED)

row_y = Inches(4.35)
for i, (lab, val, un) in enumerate([
        ("Disease CNN", ACC, f"{CNN['test_samples']:,} test images"),
        ("Yield model", f"{YLD['median_ape_pct']}%", "median error"),
        ("Price model", f"\u20b9{PRC['mae_inr_per_q']}/q", f"{PRC['horizon_days']}-day MAE"),
        ("Modules live", "9 / 9", "all implemented")]):
    x = Inches(0.9 + i * 2.95)
    kpi(s, x, row_y, Inches(2.7), Inches(1.25), lab, val, un)

txt(s, Inches(0.9), Inches(6.15), Inches(11.5), Inches(0.7),
    "Presented by: ______________________          Guide: ______________________\n"
    "Department of ______________________          Academic Year 2026\u201327",
    size=12, color=DIM, spacing=1.3)

# ---------------------------------------------------------------- 2. AGENDA
s = new(); title_bar(s, "Contents", "Seminar outline")
items = ["Problem", "Objectives", "System Architecture", "Modules (9)",
         "Technology Stack", "Workflow", "Results", "Expected Output",
         "Limitations", "Future Scope", "Conclusion"]
for i, it in enumerate(items):
    col, row = divmod(i, 6)
    x = Inches(0.9 + col * 6.0); y = Inches(2.0 + row * 0.78)
    box(s, x, y, Inches(5.5), Inches(0.62), fill=PANEL2)
    txt(s, x + Inches(0.2), y, Inches(0.6), Inches(0.62), f"{i+1:02d}",
        size=15, color=GREEN, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    txt(s, x + Inches(0.85), y, Inches(4.4), Inches(0.62), it,
        size=13.5, color=TEXT, anchor=MSO_ANCHOR.MIDDLE)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 3. PROBLEM
s = new(); title_bar(s, "Section 1", "Problem statement",
                     "Why a farmer in Nashik cannot make these decisions with the tools available today")
probs = [
    ("Disease diagnosis is slow and expert-dependent",
     "An extension officer visits on schedule, not on need. By the time a fungal "
     "infection is confirmed it has usually spread \u2014 late blight can destroy a "
     "tomato crop within a week of first symptoms."),
    ("Advice is generic, not field-specific",
     "Fertilizer and irrigation schedules are printed per crop per district. They "
     "ignore this field's soil test, its slope, its drip system and this week's forecast."),
    ("Yield and income are unknowable until harvest",
     "Without a yield estimate a farmer cannot plan labour, storage, credit or a "
     "second crop \u2014 and cannot negotiate with a trader in advance."),
    ("The mandi decision is guesswork",
     "Commission, freight and transit loss differ sharply between Lasalgaon, "
     "Pimpalgaon, Pune and Vashi. Choosing wrong can erase a whole season's margin."),
    ("Connectivity is unreliable in the field",
     "Cloud-only tools fail exactly where they are needed. Diagnosis must work "
     "offline, on a phone, at the field edge."),
]
for i, (h, b) in enumerate(probs):
    y = Inches(1.9 + i * 1.0)
    box(s, Inches(0.9), y, Inches(11.6), Inches(0.9), fill=PANEL if i % 2 == 0 else PANEL2)
    txt(s, Inches(1.15), y + Inches(0.11), Inches(11.1), Inches(0.3), h,
        size=13, color=LEAF, bold=True)
    txt(s, Inches(1.15), y + Inches(0.42), Inches(11.1), Inches(0.45), b,
        size=10.5, color=MUTED)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 4. OBJECTIVES
s = new(); title_bar(s, "Section 2", "Objectives")
objs = [
    "Detect crop disease and pest damage from a single leaf photograph, offline, "
    "on an edge device \u2014 with confidence and an explanation of where the model is looking.",
    "Maintain a Digital Twin of every field that projects growth, canopy, soil "
    "moisture and stress forward 60\u201390 days from live weather.",
    "Predict crop yield per field from soil test, weather and management history.",
    "Recommend irrigation, fertilizer and pesticide actions from that field's own "
    "data rather than a district-level default.",
    "Forecast mandi prices and recommend the market that maximises net realisation "
    "after commission, freight and transit loss.",
    "Combine everything into one Decision Support System: a farm health report, a "
    "ranked action list, expected yield, expected profit and the best market.",
    "Expose every capability as a REST API so IoT sensors, drones and a mobile app "
    "can use the same backend.",
]
bullets(s, Inches(0.95), Inches(1.95), Inches(11.5), Inches(4.6), objs, size=13.5, gap=11)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 5. ARCHITECTURE
s = new(); title_bar(s, "Section 3", "System architecture",
                     "Data flows top to bottom; every stage feeds the Decision Support System")

def node(x, y, w, h, label, sub=None, fill=PANEL2, fg=TEXT, size=11.5, accent=None):
    box(s, x, y, w, h, fill=fill, line=accent or LINE)
    txt(s, x, y + (Inches(0.10) if sub else Inches(0.0)), w, Inches(0.3), label,
        size=size, color=accent or fg, bold=True, align=PP_ALIGN.CENTER)
    if sub:
        txt(s, x, y + Inches(0.36), w, Inches(0.3), sub, size=8.5, color=MUTED,
            align=PP_ALIGN.CENTER)

# farmer
node(Inches(5.42), Inches(1.80), Inches(2.5), Inches(0.52), "FARMER", fill=GREEN, fg=DARK, accent=None)
txt(s, Inches(5.42), Inches(1.86), Inches(2.5), Inches(0.4), "FARMER",
    size=12, color=DARK, bold=True, align=PP_ALIGN.CENTER)
down_arrow(s, Inches(6.57), Inches(2.34))

node(Inches(4.42), Inches(2.62), Inches(4.5), Inches(0.55), "Web Dashboard (Flask + HTML/CSS/JS)",
     sub=None, accent=LINE)
down_arrow(s, Inches(6.57), Inches(3.19))

node(Inches(3.92), Inches(3.47), Inches(5.5), Inches(0.62), "Data Collection Layer",
     "Images  |  Soil  |  Weather  |  IoT sensors  |  Mandi prices")
down_arrow(s, Inches(6.57), Inches(4.11))

y = Inches(4.39)
node(Inches(1.15), y, Inches(2.55), Inches(0.72), "Edge AI",
     "Disease & pest CNN", accent=GREEN)
node(Inches(3.85), y, Inches(2.55), Inches(0.72), "Digital Twin",
     "Growth simulation", accent=GREEN)
node(Inches(6.55), y, Inches(2.55), Inches(0.72), "AI / ML Prediction",
     "Yield \u00b7 Irrigation \u00b7 Fertilizer", accent=GREEN)
node(Inches(9.25), y, Inches(2.9), Inches(0.72), "Market Intelligence",
     "Price \u00b7 Demand \u00b7 Mandi", accent=GREEN)

for cx in (2.42, 5.12, 7.82, 10.70):
    down_arrow(s, Inches(cx - 0.1), Inches(5.13), h=Inches(0.22))

node(Inches(3.42), Inches(5.40), Inches(6.5), Inches(0.70),
     "DECISION SUPPORT SYSTEM", "Health report \u00b7 Ranked actions \u00b7 Expected yield \u00b7 "
     "Profit \u00b7 Best mandi", fill=PANEL, accent=GREEN, size=13)
down_arrow(s, Inches(6.57), Inches(6.12))
txt(s, Inches(4.9), Inches(6.40), Inches(3.5), Inches(0.4), "FARMER ACTION",
    size=13, color=GREEN, bold=True, align=PP_ALIGN.CENTER)

box(s, Inches(0.9), Inches(4.30), Inches(0.22), Inches(1.9), fill=PANEL, line=LINE)
txt(s, Inches(0.42), Inches(6.45), Inches(2.6), Inches(0.5),
    "SQLite database underneath all modules", size=9, color=DIM, align=PP_ALIGN.CENTER)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 6. MODULES
s = new(); title_bar(s, "Section 4", "The nine modules",
                     "Each one is implemented, not planned")
mods = [
    ("1", "User Interface", "13 pages: dashboard, monitoring, scan, twin, predictions, market, DSS"),
    ("2", "Data Collection", "Images, soil tests, weather, sensor readings, mandi prices"),
    ("3", "Edge AI", f"MobileNetV3-Small CNN, {CNN['num_classes']} classes, {ACC}"),
    ("4", "Digital Twin", "Thermal time, LAI growth, soil-water balance, 6 scenarios"),
    ("5", "AI / ML Prediction", f"Yield {YLD['median_ape_pct']}% median error, irrigation, fertilizer"),
    ("6", "Market Intelligence", f"{PRC['horizon_days']}-day forecast, mandi ranking, profit"),
    ("7", "Decision Support", "Ranked actions, expected yield, profit, best market"),
    ("8", "Database", f"SQLite, {sum(DB.values()):,} rows across 12 tables"),
    ("9", "Future Integration", "14 REST endpoints for IoT, drones, satellite, mobile"),
]
for i, (n, name, desc) in enumerate(mods):
    col, row = divmod(i, 3)
    x = Inches(0.9 + col * 3.95); y = Inches(1.95 + row * 1.62)
    box(s, x, y, Inches(3.75), Inches(1.45), fill=PANEL if row % 2 == 0 else PANEL2)
    txt(s, x + Inches(0.22), y + Inches(0.14), Inches(0.7), Inches(0.4), n,
        size=20, color=GREEN, bold=True)
    txt(s, x + Inches(0.72), y + Inches(0.20), Inches(2.9), Inches(0.3), name,
        size=13, color=TEXT, bold=True)
    txt(s, x + Inches(0.24), y + Inches(0.66), Inches(3.3), Inches(0.7), desc,
        size=10, color=MUTED)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 7. EDGE AI
s = new(); title_bar(s, "Module 3", "Edge AI \u2014 offline disease detection",
                     "The model runs on the device; no internet is required at the field")
kpi(s, Inches(0.9), Inches(1.95), Inches(2.85), Inches(1.2), "Test accuracy", ACC,
    f"on {CNN['test_samples']:,} held-out images")
kpi(s, Inches(3.95), Inches(1.95), Inches(2.85), Inches(1.2), "Macro F1", F1,
    f"across {CNN['num_classes']} classes", accent=LEAF)
kpi(s, Inches(7.0), Inches(1.95), Inches(2.85), Inches(1.2), "Training data",
    f"{CNN['train_samples']:,}", "PlantVillage leaf images", accent=BLUE)
kpi(s, Inches(10.05), Inches(1.95), Inches(2.4), Inches(1.2), "ONNX parity",
    f"{CNN['onnx_parity_pct']:.0f}%", "vs PyTorch, 512 images", accent=AMBER)

box(s, Inches(0.9), Inches(3.4), Inches(5.9), Inches(3.35), fill=PANEL)
txt(s, Inches(1.15), Inches(3.58), Inches(5.4), Inches(0.3), "Approach",
    size=13, color=LEAF, bold=True)
bullets(s, Inches(1.15), Inches(3.98), Inches(5.45), Inches(2.6), [
    "Architecture: MobileNetV3-Small \u2014 1.56 M parameters, small enough for a phone",
    "Transfer learning from ImageNet, then fine-tuned on leaf images",
    f"Schedule: 3 epochs frozen backbone (lr 1e-3), then {len([h for h in CNN['history'] if h['phase']=='fine-tune'])} epochs full fine-tune (lr 5e-5)",
    "Input 128\u00d7128 RGB, ImageNet normalisation, heavy augmentation",
    "Grad-CAM overlay shows the lesion that drove the decision",
], size=11, gap=7)

box(s, Inches(7.0), Inches(3.4), Inches(5.45), Inches(3.35), fill=PANEL2)
txt(s, Inches(7.25), Inches(3.58), Inches(5.0), Inches(0.3),
    "Why this matters on a farm", size=13, color=LEAF, bold=True)
bullets(s, Inches(7.25), Inches(3.98), Inches(5.0), Inches(2.6), [
    "Runs with no connectivity \u2014 the ONNX artifact ships to Raspberry Pi / Android",
    "Returns confidence; below 35% the app tells the farmer to re-shoot",
    "Every diagnosis carries symptoms, treatment, organic option and expected yield loss",
    "Reports persist to the database and feed the Decision Support System",
    f"Model size: 6.1 MB PyTorch checkpoint, 6.3 MB ONNX graph",
], size=11, gap=7, bullet_color=AMBER)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 8. TWIN
s = new(); title_bar(s, "Module 4", "Digital Twin",
                     "A virtual replica of each field, advanced by real weather rather than a lookup table")
steps = [
    ("Thermal time", "Growing degree days above a crop-specific base temperature drive phenological progress."),
    ("Canopy growth", "LAI grows logistically toward a crop maximum, reduced by water stress."),
    ("Biomass", "Radiation-use efficiency \u00d7 intercepted PAR \u00d7 stress, accumulated daily."),
    ("Soil water", "The same balance the irrigation engine uses \u2014 so twin and advice cannot disagree."),
    ("Outputs", "NDVI, health score, projected yield and dated stress alerts."),
]
for i, (h, b) in enumerate(steps):
    y = Inches(1.95 + i * 0.62)
    box(s, Inches(0.9), y, Inches(0.55), Inches(0.5), fill=GREEN, line=None)
    txt(s, Inches(0.9), y + Inches(0.06), Inches(0.55), Inches(0.4), str(i + 1),
        size=14, color=DARK, bold=True, align=PP_ALIGN.CENTER)
    txt(s, Inches(1.65), y + Inches(0.02), Inches(2.3), Inches(0.45), h,
        size=12.5, color=TEXT, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    txt(s, Inches(4.0), y + Inches(0.02), Inches(4.5), Inches(0.5), b,
        size=10.5, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)

box(s, Inches(8.7), Inches(1.95), Inches(3.75), Inches(4.8), fill=PANEL2)
txt(s, Inches(8.95), Inches(2.12), Inches(3.3), Inches(0.3), "What-if scenarios",
    size=13, color=LEAF, bold=True)
bullets(s, Inches(8.95), Inches(2.5), Inches(3.3), Inches(4.1), [
    ("Baseline \u2014 current plan", True), "Extra irrigation (+60 mm/week)",
    "Drip upgrade (92% efficiency)", "Full IPM + better nutrition",
    "Heat wave (+3 \u00b0C season)", "Monsoon failure (35% of normal rain)",
    "", ("The UI ranks them by projected yield and names the winner.", False),
], size=11, gap=8, bullet_color=BLUE)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 9. ML PREDICTION
s = new(); title_bar(s, "Module 5", "AI / ML prediction")
box(s, Inches(0.9), Inches(1.9), Inches(5.9), Inches(2.35), fill=PANEL)
txt(s, Inches(1.15), Inches(2.06), Inches(5.4), Inches(0.3), "Crop yield prediction",
    size=13, color=LEAF, bold=True)
bullets(s, Inches(1.15), Inches(2.44), Inches(5.45), Inches(1.7), [
    f"HistGradientBoosting on a 4,000-row regional trial network",
    f"Target is the yield RATIO (achieved \u00f7 crop-typical), not raw kg/acre",
    f"Test R\u00b2 {YLD['r2_kg_per_acre']}, median error {YLD['median_ape_pct']}%, "
    f"per-crop error {YLD['mean_ape_by_crop_pct']}%",
    "Returns limiting factors ranked by impact, and an honest confidence band",
], size=10.5, gap=6)

box(s, Inches(7.0), Inches(1.9), Inches(5.45), Inches(2.35), fill=PANEL2)
txt(s, Inches(7.25), Inches(2.06), Inches(5.0), Inches(0.3), "Irrigation recommendation",
    size=13, color=LEAF, bold=True)
bullets(s, Inches(7.25), Inches(2.44), Inches(5.0), Inches(1.7), [
    "Hargreaves-Samani ET\u2080 from Tmin/Tmax only \u2014 no station needed",
    "FAO-56 Kc curve for the field's actual growth stage",
    "Soil-water budget per soil type, refilled at 50% depletion",
    "7-day schedule that already accounts for forecast rain",
], size=10.5, gap=6, bullet_color=BLUE)

box(s, Inches(0.9), Inches(4.4), Inches(5.9), Inches(2.35), fill=PANEL2)
txt(s, Inches(1.15), Inches(4.56), Inches(5.4), Inches(0.3), "Fertilizer recommendation",
    size=13, color=LEAF, bold=True)
bullets(s, Inches(1.15), Inches(4.94), Inches(5.45), Inches(1.7), [
    "Balances the soil test against crop demand, then applies a soil credit",
    "Converts the NPK gap into real products: DAP, MOP, Urea, FYM, micronutrients",
    "Splits nitrogen across growth stages and prices the whole programme",
    "Flags pH and organic-carbon corrections separately",
], size=10.5, gap=6, bullet_color=AMBER)

box(s, Inches(7.0), Inches(4.4), Inches(5.45), Inches(2.35), fill=PANEL)
txt(s, Inches(7.25), Inches(4.56), Inches(5.0), Inches(0.3), "Pest & disease risk",
    size=13, color=LEAF, bold=True)
bullets(s, Inches(7.25), Inches(4.94), Inches(5.0), Inches(1.7), [
    "Scores each known threat from humidity, temperature and rainfall",
    "Boosted when the Edge AI module actually saw that disease in a photo",
    "Reduced by recent spray history",
    "Finds a dry spray window so rain does not waste the application",
], size=10.5, gap=6, bullet_color=RED)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 10. MARKET
s = new(); title_bar(s, "Module 6", "Market intelligence")
kpi(s, Inches(0.9), Inches(1.95), Inches(2.85), Inches(1.2), "Forecast horizon",
    f"{PRC['horizon_days']} days", "recursive ML model")
kpi(s, Inches(3.95), Inches(1.95), Inches(2.85), Inches(1.2), "Price MAE",
    f"\u20b9{PRC['mae_inr_per_q']}/q", f"MAPE {PRC['mape_pct']}%", accent=LEAF)
kpi(s, Inches(7.0), Inches(1.95), Inches(2.85), Inches(1.2), "Demand model R\u00b2",
    f"{DMD['r2']}", f"MAPE {DMD['mape_pct']}%", accent=BLUE)
kpi(s, Inches(10.05), Inches(1.95), Inches(2.4), Inches(1.2), "Mandis compared",
    "7", "by net realisation", accent=AMBER)

box(s, Inches(0.9), Inches(3.4), Inches(6.3), Inches(3.35), fill=PANEL)
txt(s, Inches(1.15), Inches(3.58), Inches(5.8), Inches(0.3), "What it computes",
    size=13, color=LEAF, bold=True)
bullets(s, Inches(1.15), Inches(3.98), Inches(5.85), Inches(2.6), [
    "One-step-ahead gradient boosting on lagged prices + calendar features, "
    "applied recursively for 90 days",
    "Demand outlook: arrivals vs the seasonal norm \u2192 glut risk",
    "Mandi ranking on NET realisation = price \u2212 commission \u2212 freight \u2212 transit loss",
    "Profit estimation with breakeven yield, breakeven price and three scenarios",
    "Crop alternatives: what would earn more on this land right now",
], size=11, gap=8)

box(s, Inches(7.4), Inches(3.4), Inches(5.05), Inches(3.35), fill=PANEL2)
txt(s, Inches(7.65), Inches(3.58), Inches(4.6), Inches(0.3), "Why net, not gross",
    size=13, color=LEAF, bold=True)
bullets(s, Inches(7.65), Inches(3.98), Inches(4.6), Inches(2.6), [
    "Vashi may quote more than Lasalgaon but charges 2.5% commission "
    "and ~\u20b9240/q freight over 165 km",
    "Perishables lose value in transit \u2014 tomato keeps 6 days, grape 12",
    "The ranking is recomputed at the field's own expected harvest date",
    "So the answer is the mandi that pays most after everything is deducted",
], size=11, gap=8, bullet_color=AMBER)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 11. DSS
s = new(); title_bar(s, "Module 7", "Decision Support System",
                     "The only screen the farmer has to read \u2014 everything else feeds it")
outs = [
    ("Farm health report", "Weighted score from nutrition, water, protection, disease and vigour, "
     "per field and per farm.", GREEN),
    ("Recommended actions", "Irrigation, fertilizer, pesticide, market and agronomy actions ranked "
     "by expected impact, each tied to a field.", LEAF),
    ("Expected yield", "From the yield model, cross-checked against the Digital Twin projection.", BLUE),
    ("Expected profit", "Yield \u00d7 net mandi price \u2212 cost of cultivation, per field and total.", AMBER),
    ("Best market selection", "The mandi with the highest net realisation at the expected harvest date.", RED),
]
for i, (h, b, c) in enumerate(outs):
    y = Inches(1.95 + i * 0.95)
    box(s, Inches(0.9), y, Inches(11.6), Inches(0.85), fill=PANEL if i % 2 == 0 else PANEL2)
    box(s, Inches(0.9), y, Inches(0.09), Inches(0.85), fill=c, line=None, radius=0.5)
    txt(s, Inches(1.2), y + Inches(0.12), Inches(3.3), Inches(0.6), h,
        size=13, color=c, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    txt(s, Inches(4.7), y + Inches(0.12), Inches(7.6), Inches(0.6), b,
        size=11, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
txt(s, Inches(0.9), Inches(6.75), Inches(11.6), Inches(0.3),
    f"Live run on the demo farm: {DB['recommendations']} open recommendations generated across 9 fields.",
    size=10.5, color=DIM)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 12. DATABASE
s = new(); title_bar(s, "Module 8", "Database",
                     "SQLite for the demo; swap app/db.py for MySQL or MongoDB without touching the services")
rows = [
    ("users", "Farmer accounts, credentials, language", f"{DB['users']}"),
    ("farms", "Location, area, soil type, irrigation", f"{DB['farms']}"),
    ("fields", "Crop, variety, sowing and harvest dates", f"{DB['fields']}"),
    ("soil_readings", "N, P, K, pH, organic carbon, moisture, EC", f"{DB['soil_readings']}"),
    ("weather_daily", "History + 7-day forecast per farm", f"{DB['weather_daily']:,}"),
    ("market_prices", "Crop \u00d7 mandi \u00d7 date modal price and arrivals", f"{DB['market_prices']:,}"),
    ("disease_reports", "CNN output, confidence, severity, advice", f"{DB['disease_reports']}"),
    ("recommendations", "DSS actions with priority and status", f"{DB['recommendations']}"),
]
table(s, Inches(0.9), Inches(1.95), Inches(8.0), ["Table", "Contents", "Rows"],
      rows, col_w=[2.0, 4.6, 1.0], size=10.5, row_h=Inches(0.36))
box(s, Inches(9.2), Inches(1.95), Inches(3.25), Inches(4.7), fill=PANEL2)
txt(s, Inches(9.45), Inches(2.12), Inches(2.8), Inches(0.3), "Also present",
    size=12.5, color=LEAF, bold=True)
bullets(s, Inches(9.45), Inches(2.5), Inches(2.8), Inches(3.9), [
    "pest_reports", "irrigation_logs", "fertilizer_logs", "twin_snapshots",
    "sales", "", ("12 tables total, "
    f"{sum(DB.values()):,} rows seeded", True),
], size=11, gap=7, bullet_color=BLUE)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 13. TECH STACK
s = new(); title_bar(s, "Section 5", "Technology stack")
rows = [
    ("Frontend", "HTML5, CSS3, vanilla JavaScript", "Chart.js vendored locally \u2014 no CDN, works offline"),
    ("Backend", "Python 3.13 + Flask 3", "App factory pattern, 13 pages + 13 REST endpoints"),
    ("AI / ML", "scikit-learn 1.6", "HistGradientBoosting for yield, price and demand"),
    ("Computer vision", "OpenCV 4.11", "Pre-processing, resize, Grad-CAM overlay"),
    ("Disease detection", "PyTorch 2.14 + torchvision", "MobileNetV3-Small transfer learning"),
    ("Edge deployment", "ONNX 1.22 + ONNX Runtime 1.30", "Portable artifact for Raspberry Pi / Android"),
    ("Database", "SQLite 3", "Single-file; swappable for MySQL or MongoDB"),
    ("Digital twin", "NumPy + SciPy", "Thermal-time and soil-water simulation"),
    ("Visualisation", "Chart.js 4.4", "Line, bar, radar and doughnut charts"),
    ("APIs", "Flask blueprints", "Weather and market APIs plug in at the service layer"),
]
table(s, Inches(0.9), Inches(1.95), Inches(11.55),
      ["Component", "Technology", "Note"], rows, col_w=[2.0, 3.0, 5.2],
      size=10.5, row_h=Inches(0.40))
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 14. WORKFLOW
s = new(); title_bar(s, "Section 6", "Workflow",
                     "What happens between a farmer standing in the field and an action on their phone")
flow = [
    ("1", "Capture", "Farmer photographs a leaf, or the system reads the latest soil test, weather and mandi feed."),
    ("2", "Edge inference", "The CNN classifies the leaf on-device and returns the disease, confidence and a Grad-CAM overlay."),
    ("3", "Enrich", "The result is joined to the field's soil test, weather history, irrigation log and spray history."),
    ("4", "Simulate", "The Digital Twin advances the field forward and reports projected yield, stress and alerts."),
    ("5", "Predict", "Yield, irrigation, fertilizer and pest models each produce a recommendation for that field."),
    ("6", "Value", "Market Intelligence forecasts the price at the expected harvest date and ranks the mandis."),
    ("7", "Decide", "The DSS ranks every action by impact and reports expected yield, profit and best market."),
]
for i, (n, h, b) in enumerate(flow):
    y = Inches(1.9 + i * 0.70)
    box(s, Inches(0.9), y, Inches(0.5), Inches(0.56), fill=GREEN, line=None)
    txt(s, Inches(0.9), y + Inches(0.08), Inches(0.5), Inches(0.4), n,
        size=14, color=DARK, bold=True, align=PP_ALIGN.CENTER)
    txt(s, Inches(1.6), y + Inches(0.04), Inches(2.1), Inches(0.5), h,
        size=12.5, color=LEAF, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    txt(s, Inches(3.8), y + Inches(0.04), Inches(8.6), Inches(0.56), b,
        size=10.5, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
    if i < len(flow) - 1:
        down_arrow(s, Inches(1.05), y + Inches(0.56), w=Inches(0.16), h=Inches(0.14))
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 15. RESULTS: CNN
s = new(); title_bar(s, "Section 7", "Results \u2014 disease detection model",
                     "Measured on the held-out test split, never on training data")
kpi(s, Inches(0.9), Inches(1.95), Inches(3.7), Inches(1.3), "Accuracy", ACC,
    f"{CNN['test_samples']:,} held-out images")
kpi(s, Inches(4.85), Inches(1.95), Inches(3.7), Inches(1.3), "Macro F1", F1,
    f"{CNN['num_classes']} classes, balanced", accent=LEAF)
kpi(s, Inches(8.8), Inches(1.95), Inches(3.65), Inches(1.3), "Final loss",
    f"{CNN['history'][-1]['loss']:.4f}", "after 7 epochs", accent=BLUE)

pc = CNN["per_class_f1"]
focus = ["Tomato___healthy", "Tomato___Early_blight", "Tomato___Late_blight",
         "Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Corn_(maize)___Common_rust_",
         "Corn_(maize)___Northern_Leaf_Blight", "Grape___Black_rot",
         "Potato___Late_blight", "Pepper,_bell___Bacterial_spot"]
rows = [(k.replace("___", " \u00b7 ").replace("_", " "), f"{pc[k]*100:.1f}%") for k in focus]
txt(s, Inches(0.9), Inches(3.45), Inches(5.6), Inches(0.3),
    "Per-class F1 \u2014 crops relevant to Maharashtra", size=12.5, color=LEAF, bold=True)
table(s, Inches(0.9), Inches(3.85), Inches(5.6), ["Class", "F1"], rows,
      col_w=[4.2, 1.0], size=10, row_h=Inches(0.28))

box(s, Inches(6.9), Inches(3.45), Inches(5.55), Inches(3.3), fill=PANEL2)
txt(s, Inches(7.15), Inches(3.62), Inches(5.1), Inches(0.3), "Read this honestly",
    size=12.5, color=AMBER, bold=True)
bullets(s, Inches(7.15), Inches(4.0), Inches(5.1), Inches(2.6), [
    "The hardest classes are the visually similar leaf spots: tomato early blight "
    f"F1 {pc['Tomato___Early_blight']*100:.0f}%, target spot {pc['Tomato___Target_Spot']*100:.0f}%",
    "Macro F1 (92.7%) sits below accuracy (93.9%) because rare classes are harder \u2014 "
    "quoting only accuracy would flatter the model",
    "A 228-image retained subset scores 92.1%, consistent with the full split",
    "PlantVillage leaves are photographed on plain backgrounds; real field photos "
    "with clutter will score lower",
], size=10.5, gap=7, bullet_color=AMBER)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 16. RESULTS: TABULAR
s = new(); title_bar(s, "Section 7", "Results \u2014 prediction models")
rows = [
    ("Crop yield", "HistGradientBoosting, ratio target",
     f"{YLD['r2_kg_per_acre']}", f"{YLD['median_ape_pct']}%",
     f"{YLD['mae_kg_per_acre']:.1f} kg/acre", f"{YLD['n_train']:,} / {YLD['n_test']:,}"),
    ("Mandi price", "HistGradientBoosting, recursive 90 d",
     f"{PRC['r2']}", f"{PRC['mape_pct']}%",
     f"\u20b9{PRC['mae_inr_per_q']}/quintal", f"{PRC['n_train']:,} / {PRC['n_test']:,}"),
    ("Market demand", "HistGradientBoosting on arrivals",
     f"{DMD['r2']}", f"{DMD['mape_pct']}%", "\u2014", f"{DMD['n']:,}"),
]
table(s, Inches(0.9), Inches(1.95), Inches(11.55),
      ["Model", "Method", "R\u00b2", "% error (median)", "Absolute error", "Train / test"],
      rows, col_w=[1.4, 2.9, 0.8, 1.3, 1.5, 1.4], size=10.5, row_h=Inches(0.44))

box(s, Inches(0.9), Inches(3.85), Inches(5.7), Inches(2.9), fill=PANEL)
txt(s, Inches(1.15), Inches(4.02), Inches(5.2), Inches(0.3),
    "A design decision worth defending", size=12.5, color=LEAF, bold=True)
bullets(s, Inches(1.15), Inches(4.4), Inches(5.2), Inches(2.2), [
    ("Predicting raw kg/acre was wrong.", True),
    "Banana (~1,300 kg/acre) dominated the loss while tur (~3 kg/acre) was fitted badly",
    "Pooled MAPE was 46.7% and per-crop error reached 128%",
    "Changing the target to a yield RATIO cut median error to 8.1% and per-crop error to 8\u201316%",
], size=10.5, gap=7)

box(s, Inches(6.75), Inches(3.85), Inches(5.7), Inches(2.9), fill=PANEL2)
txt(s, Inches(7.0), Inches(4.02), Inches(5.2), Inches(0.3),
    "What is NOT claimed", size=12.5, color=AMBER, bold=True)
bullets(s, Inches(7.0), Inches(4.4), Inches(5.2), Inches(2.2), [
    "Price R\u00b2 of 0.9998 is high because the seeded series is mean-reverting \u2014 "
    "real Agmarknet data will be harder",
    "The yield model learns a synthetic agronomic response surface, not calibrated "
    "Maharashtra trial data",
    "Weather is generated from Nashik climatological normals, not a live feed",
], size=10.5, gap=7, bullet_color=AMBER)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 17. LIVE SYSTEM
s = new(); title_bar(s, "Section 7", "The running system",
                     "Verified end to end after a clean rebuild from an empty database")
rows = [
    ("Web pages", "13", "all return HTTP 200"),
    ("REST endpoints", "13", "all return HTTP 200"),
    ("Server tracebacks", "0", "clean log after full page sweep"),
    ("Database rows", f"{sum(DB.values()):,}", "seeded from scratch, reproducible"),
    ("Recommendations generated", f"{DB['recommendations']}", "by one Decision Support run"),
    ("Project size", "25 MB", "no external services required"),
]
table(s, Inches(0.9), Inches(1.95), Inches(7.2), ["Check", "Result", "Detail"],
      rows, col_w=[2.4, 1.0, 3.2], size=11, row_h=Inches(0.40))

box(s, Inches(8.4), Inches(1.95), Inches(4.05), Inches(4.8), fill=PANEL2)
txt(s, Inches(8.65), Inches(2.12), Inches(3.6), Inches(0.3), "Demo path",
    size=12.5, color=LEAF, bold=True)
bullets(s, Inches(8.65), Inches(2.5), Inches(3.6), Inches(4.1), [
    "Log in as ramesh / farmer123",
    "Dashboard \u2192 farm health and priority actions",
    "Disease Detection \u2192 click a bundled leaf sample, show the Grad-CAM overlay",
    "Digital Twin \u2192 switch scenarios, show the yield divergence",
    "Market \u2192 show the mandi ranking and profit estimate",
    "Decision Support \u2192 show the ranked action list",
], size=10.5, gap=8, bullet_color=BLUE)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 18. EXPECTED OUTPUT
s = new(); title_bar(s, "Section 8", "Expected output")
outs = [
    ("For the farmer", [
        "A diagnosis in seconds from a phone photo, offline, with a treatment plan",
        "A dated irrigation and fertilizer schedule for each field",
        "An expected yield and profit figure weeks before harvest",
        "One ranked list of what to do next, not five separate screens"]),
    ("For the system", [
        "A farm health score that tracks the season",
        "A digital twin that can be stress-tested against weather scenarios",
        "A market recommendation based on net realisation, not headline price",
        "A REST API ready for sensors, drones and a mobile client"]),
]
for i, (h, items) in enumerate(outs):
    x = Inches(0.9 + i * 5.95)
    box(s, x, Inches(1.95), Inches(5.6), Inches(4.7), fill=PANEL if i == 0 else PANEL2)
    txt(s, x + Inches(0.28), Inches(2.14), Inches(5.0), Inches(0.3), h,
        size=14, color=GREEN if i == 0 else BLUE, bold=True)
    bullets(s, x + Inches(0.28), Inches(2.62), Inches(5.05), Inches(3.8), items,
            size=11.5, gap=10, bullet_color=GREEN if i == 0 else BLUE)
txt(s, Inches(0.9), Inches(6.8), Inches(11.6), Inches(0.3),
    "All of the above is implemented and demonstrable in the current build.",
    size=10.5, color=DIM)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 19. LIMITATIONS
s = new(); title_bar(s, "Limitations", "What this build does not yet do",
                     "Stated plainly so the evaluation is against real claims")
lims = [
    ("Weather is simulated", "Generated from Nashik climatological normals. The service "
     "boundary is clean \u2014 replace one function with an OpenWeather or IMD call."),
    ("Mandi prices are synthetic", "Built with trend, seasonality and mean-reverting noise so "
     "the forecaster has real structure to learn, but it is not live Agmarknet data."),
    ("Yield model learns a synthetic response surface", "The agronomy (Liebig nutrient "
     "limitation, water and heat stress) is standard; the fitted coefficients are not "
     "calibrated on real Maharashtra trials."),
    ("Lab leaves, not field leaves", "PlantVillage images are single leaves on plain "
     "backgrounds. Cluttered field photos will score below 93.9%."),
    ("Development web server", "Flask's built-in server is fine for a seminar demo; a "
     "production deployment needs gunicorn behind a reverse proxy."),
]
for i, (h, b) in enumerate(lims):
    y = Inches(1.95 + i * 0.95)
    box(s, Inches(0.9), y, Inches(11.6), Inches(0.85), fill=PANEL if i % 2 == 0 else PANEL2)
    txt(s, Inches(1.15), y + Inches(0.12), Inches(3.5), Inches(0.6), h,
        size=12.5, color=AMBER, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    txt(s, Inches(4.8), y + Inches(0.12), Inches(7.5), Inches(0.62), b,
        size=10.5, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 20. FUTURE SCOPE
s = new(); title_bar(s, "Section 9", "Future scope",
                     "Module 9 \u2014 the REST API already exists, so these are integrations rather than rebuilds")
fut = [
    ("IoT sensors", "Soil moisture, NPK and EC nodes post to /api/field/<id>/irrigation; "
     "the twin already consumes soil moisture."),
    ("Drones", "Multispectral sorties replace the simulated NDVI in the twin with measured canopy indices."),
    ("Satellite data", "Sentinel-2 tiles give field-level NDVI history for farms without sensors."),
    ("Live weather APIs", "OpenWeather / IMD replace the climatological generator with no downstream change."),
    ("Live mandi data", "Agmarknet arrivals and prices replace the synthetic series."),
    ("Blockchain", "Immutable produce provenance from field to mandi for export-grade grapes."),
    ("Autonomous farming", "The DSS action list is already machine-readable, so it can drive "
     "irrigation controllers and sprayers directly."),
]
for i, (h, b) in enumerate(fut):
    col, row = divmod(i, 4)
    x = Inches(0.9 + col * 5.95); y = Inches(1.95 + row * 1.18)
    box(s, x, y, Inches(5.6), Inches(1.05), fill=PANEL2 if col else PANEL)
    txt(s, x + Inches(0.22), y + Inches(0.12), Inches(5.1), Inches(0.3), h,
        size=12.5, color=LEAF, bold=True)
    txt(s, x + Inches(0.22), y + Inches(0.44), Inches(5.15), Inches(0.55), b,
        size=10, color=MUTED)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 21. CONCLUSION
s = new(); title_bar(s, "Conclusion", "Progress summary")
bullets(s, Inches(0.95), Inches(1.95), Inches(11.5), Inches(2.4), [
    ("All nine modules are implemented and running, not designed on paper.", True),
    (f"The Edge AI model is genuinely trained: {ACC} accuracy and {F1} macro F1 on "
     f"{CNN['test_samples']:,} held-out PlantVillage images.", True),
    (f"Yield, price and demand models are fitted and measured: {YLD['median_ape_pct']}% "
     f"median yield error, \u20b9{PRC['mae_inr_per_q']}/q price MAE over {PRC['horizon_days']} days.", True),
    "The modules are wired together \u2014 one Decision Support run produced "
    f"{DB['recommendations']} ranked actions that surfaced on the dashboard.",
    "The build is reproducible from an empty database with no external services.",
], size=13.5, gap=12)

box(s, Inches(0.9), Inches(4.6), Inches(11.55), Inches(2.1), fill=PANEL2)
txt(s, Inches(1.2), Inches(4.78), Inches(11.0), Inches(0.3), "Work remaining",
    size=13, color=AMBER, bold=True)
bullets(s, Inches(1.2), Inches(5.16), Inches(11.0), Inches(1.4), [
    "Connect live weather and Agmarknet feeds in place of the simulated series",
    "Calibrate the yield model against real Maharashtra trial data",
    "Validate disease detection on field photographs rather than lab leaves",
    "Deploy the ONNX artifact to a physical Raspberry Pi edge node and measure latency",
], size=11.5, gap=7, bullet_color=AMBER)
footer(s, len(SLIDES), 22)

# ---------------------------------------------------------------- 22. REFERENCES
s = new(); title_bar(s, "Sources", "References")
refs = [
    "Mohanty S. P., Hughes D. P., Salath\u00e9 M. (2016). \u201cUsing Deep Learning for "
    "Image-Based Plant Disease Detection.\u201d Frontiers in Plant Science, 7:1419.",
    "Howard A. G. et al. (2019). \u201cSearching for MobileNetV3.\u201d ICCV 2019.",
    "Selvaraju R. R. et al. (2017). \u201cGrad-CAM: Visual Explanations from Deep Networks.\u201d ICCV 2017.",
    "Allen R. G. et al. (1998). \u201cCrop Evapotranspiration \u2014 Guidelines for Computing Crop "
    "Water Requirements.\u201d FAO Irrigation and Drainage Paper 56.",
    "Hargreaves G. H., Samani Z. A. (1985). \u201cReference crop evapotranspiration from temperature.\u201d "
    "Applied Engineering in Agriculture, 1(2), 96\u201399.",
    "Keetha N. et al. (2021). \u201cHistGradientBoosting: histogram-based gradient boosting.\u201d scikit-learn.",
    "Indian Meteorological Department \u2014 Nashik climatological normals.",
    "Agmarknet (Directorate of Marketing & Inspection) \u2014 daily mandi price and arrival bulletins.",
    "Dataset: PlantVillage, distributed as GVJahnavi/PlantVillage_dataset (Hugging Face), CC BY-SA 3.0.",
]
for i, r in enumerate(refs):
    y = Inches(1.95 + i * 0.52)
    txt(s, Inches(0.95), y, Inches(0.5), Inches(0.5), f"[{i+1}]", size=10.5, color=GREEN, bold=True)
    txt(s, Inches(1.5), y, Inches(10.9), Inches(0.5), r, size=10.5, color=MUTED)
footer(s, len(SLIDES), 22)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
prs.save(OUT)
print(f"[ok] {len(prs.slides)} slides -> {OUT}")
print(f"     size {os.path.getsize(OUT)/1024:.0f} KB")
