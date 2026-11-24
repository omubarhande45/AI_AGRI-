"""Extract a handful of real PlantVillage test leaves as demo inputs.

Lets the seminar audience run disease detection without a camera. Uses only
held-out TEST images, so the demo never shows a training photo.
"""
from __future__ import annotations

import json
import os

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE_DIR, "data", "plantvillage_processed")
OUT = os.path.join(BASE_DIR, "data", "uploads", "demo")
WANT = [
    ("Tomato___Early_blight", "tomato_early_blight.jpg"),
    ("Tomato___Tomato_Yellow_Leaf_Curl_Virus", "tomato_yellow_leaf_curl.jpg"),
    ("Tomato___healthy", "tomato_healthy.jpg"),
    ("Corn_(maize)___Common_rust_", "maize_common_rust.jpg"),
    ("Corn_(maize)___Northern_Leaf_Blight", "maize_northern_leaf_blight.jpg"),
    ("Grape___Black_rot", "grape_black_rot.jpg"),
    ("Potato___Late_blight", "potato_late_blight.jpg"),
    ("Pepper,_bell___Bacterial_spot", "bell_pepper_bacterial_spot.jpg"),
]


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    names = meta["class_names"]
    X = np.memmap(os.path.join(DATA, "test_X.dat"), dtype=np.uint8, mode="r",
                  shape=(meta["test"]["count"], 128, 128, 3))
    y = np.load(os.path.join(DATA, "test_y.npy"))

    written = []
    for cls, fname in WANT:
        if cls not in names:
            print(f"[skip] {cls} not in dataset")
            continue
        idx = int(names.index(cls))
        rows = np.where(y == idx)[0]
        if len(rows) == 0:
            print(f"[skip] no test samples for {cls}")
            continue
        pick = rows[len(rows) // 2]          # deterministic middle sample
        bgr = cv2.cvtColor(np.array(X[pick]), cv2.COLOR_RGB2BGR)
        bgr = cv2.resize(bgr, (512, 512), interpolation=cv2.INTER_CUBIC)
        path = os.path.join(OUT, fname)
        cv2.imwrite(path, bgr)
        written.append((fname, cls))
        print(f"[ok] {fname:38} <- {cls} (test sample #{pick})")

    manifest = {f: c for f, c in written}
    with open(os.path.join(OUT, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"[done] {len(written)} demo images in {OUT}")


if __name__ == "__main__":
    main()
