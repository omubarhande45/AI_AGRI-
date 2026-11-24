"""
Build the Project Progress Seminar deck.

Every number in this deck comes from models/disease_cnn/meta.json,
models/ml/metrics.json and the live SQLite database - nothing is a
placeholder. Run:  python3 docs/build_seminar_pptx.py
"""
from __future__ import annotations

import json
import os
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "docs", "Project_Progress_Seminar.pptx")

# ---- palette -------------------------------------------------------------
DARK = RGBColor(0x0D, 0x15, 0x12)
PANEL = RGBColor(0x16, 0x24, 0x1D)
PANEL2 = RGBColor(0x1C, 0x2E, 0x25)
LINE = RGBColor(0x2F, 0x50, 0x38)
GREEN = RGBColor(0x3E, 0xCF, 0x6E)
LEAF = RGBColor(0x7F, 0xD6, 0x94)
TEXT = RGBColor(0xE8, 0xF2, 0xEA)
MUTED = RGBColor(0x93, 0xA9, 0x9A)
DIM = RGBColor(0x6D, 0x84, 0x78)
AMBER = RGBColor(0xF0, 0xB4, 0x29)
RED = RGBColor(0xEF, 0x5F, 0x5F)
BLUE = RGBColor(0x4A, 0xA8, 0xE0)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

W, H = Inches(13.333), Inches(7.5)


def metrics() -> dict:
    cnn = json.load(open(os.path.join(BASE, "models/disease_cnn/meta.json")))
    ml = json.load(open(os.path.join(BASE, "models/ml/metrics.json")))
    from app import db
    db.init_db()
    return {"cnn": cnn, "ml": ml,
            "db": {t: db.table_count(t) for t in
                   ("users", "farms", "fields", "soil_readings", "weather_daily",
                    "market_prices", "disease_reports", "recommendations")}}


# ---- primitives ----------------------------------------------------------
def slide(prs, bg=DARK):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    r.fill.solid(); r.fill.fore_color.rgb = bg; r.line.fill.background()
    r.shadow.inherit = False
    return s


def box(s, x, y, w, h, fill=PANEL, line=LINE, radius=0.08):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.adjustments[0] = radius
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line; sh.line.width = Pt(1)
    sh.shadow.inherit = False
    return sh


def txt(s, x, y, w, h, text, size=14, color=TEXT, bold=False, align=PP_ALIGN.LEFT,
        font="Calibri", anchor=MSO_ANCHOR.TOP, spacing=1.0):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    lines = text.split("\n") if isinstance(text, str) else text
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        r = p.add_run(); r.text = ln
        f = r.font
        f.size = Pt(size); f.bold = bold; f.color.rgb = color; f.name = font
    return tb


def bullets(s, x, y, w, h, items, size=13, color=TEXT, gap=6, bullet_color=GREEN):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        bold = False
        if isinstance(item, tuple):
            item, bold = item
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap); p.line_spacing = 1.12
        r1 = p.add_run(); r1.text = "\u25AA  "
        r1.font.size = Pt(size); r1.font.color.rgb = bullet_color; r1.font.bold = True
        r2 = p.add_run(); r2.text = item
        r2.font.size = Pt(size); r2.font.color.rgb = color; r2.font.name = "Calibri"
        r2.font.bold = bold
    return tb


def title_bar(s, kicker, title, sub=None):
    box(s, Inches(0.55), Inches(0.42), Inches(0.09), Inches(0.62), fill=GREEN, line=None, radius=0.5)
    txt(s, Inches(0.82), Inches(0.40), Inches(11.5), Inches(0.28), kicker.upper(),
        size=10.5, color=GREEN, bold=True)
    txt(s, Inches(0.82), Inches(0.66), Inches(11.9), Inches(0.5), title,
        size=25, color=TEXT, bold=True)
    if sub:
        txt(s, Inches(0.82), Inches(1.18), Inches(11.9), Inches(0.4), sub, size=12.5, color=MUTED)
    ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(1.62), Inches(12.23), Pt(1))
    ln.fill.solid(); ln.fill.fore_color.rgb = LINE; ln.line.fill.background(); ln.shadow.inherit = False


def footer(s, n, total):
    txt(s, Inches(0.55), Inches(7.02), Inches(9), Inches(0.3),
        "AI-Powered Smart Agriculture System  ·  Project Progress Seminar", size=9, color=DIM)
    txt(s, Inches(11.6), Inches(7.02), Inches(1.2), Inches(0.3), f"{n} / {total}",
        size=9, color=DIM, align=PP_ALIGN.RIGHT)


def kpi(s, x, y, w, h, label, value, unit=None, accent=GREEN):
    box(s, x, y, w, h, fill=PANEL2)
    txt(s, x + Inches(0.18), y + Inches(0.14), w - Inches(0.36), Inches(0.24),
        label.upper(), size=9, color=DIM, bold=True)
    txt(s, x + Inches(0.18), y + Inches(0.40), w - Inches(0.36), Inches(0.44),
        value, size=25, color=accent, bold=True)
    if unit:
        txt(s, x + Inches(0.18), y + Inches(0.88), w - Inches(0.36), Inches(0.26),
            unit, size=9.5, color=MUTED)


def arrow(s, x, y, w=Inches(0.34), h=Inches(0.2), color=LINE):
    a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x, y, w, h)
    a.fill.solid(); a.fill.fore_color.rgb = color; a.line.fill.background(); a.shadow.inherit = False
    return a


def down_arrow(s, x, y, w=Inches(0.2), h=Inches(0.26), color=LINE):
    a = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, x, y, w, h)
    a.fill.solid(); a.fill.fore_color.rgb = color; a.line.fill.background(); a.shadow.inherit = False
    return a


def table(s, x, y, w, headers, rows, col_w=None, size=10.5, row_h=Inches(0.30)):
    n_r, n_c = len(rows) + 1, len(headers)
    gf = s.shapes.add_table(n_r, n_c, x, y, w, row_h * n_r)
    tbl = gf.table
    if col_w:
        tot = sum(col_w)
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = Emu(int(w * cw / tot))
    for c, htxt in enumerate(headers):
        cell = tbl.cell(0, c)
        cell.text = htxt
        cell.fill.solid(); cell.fill.fore_color.rgb = PANEL2
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT
            for r in p.runs:
                r.font.size = Pt(9.5); r.font.bold = True; r.font.color.rgb = LEAF
    for ri, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = tbl.cell(ri, c)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = PANEL if ri % 2 else RGBColor(0x13, 0x1F, 0x19)
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT
                for r in p.runs:
                    r.font.size = Pt(size); r.font.color.rgb = TEXT; r.font.name = "Calibri"
    return tbl
