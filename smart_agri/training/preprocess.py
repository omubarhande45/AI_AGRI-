"""
Preprocess the PlantVillage parquet shards into memory-mapped uint8 arrays.

The sandbox only has ~1 GB RAM, so we cannot hold 54k decoded PIL images in
memory. We decode -> resize to 128x128 RGB -> append to a numpy memmap. The
training script then reads random slices straight off disk.

Outputs (in smart_agri/data/plantvillage_processed/):
    train_X.dat / test_X.dat   uint8 memmap, shape (N, 128, 128, 3)
    train_y.npy / test_y.npy   int16 labels
    meta.json                  class names, counts, shape, split info
"""
from __future__ import annotations

import io
import json
import os
import sys
from collections import Counter

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "plantvillage")
OUT_DIR = os.path.join(BASE_DIR, "data", "plantvillage_processed")
SIZE = 128
DTYPE = np.uint8

TRAIN_FILES = ["train-00000-of-00002.parquet", "train-00001-of-00002.parquet"]
TEST_FILES = ["test-00000-of-00001.parquet"]


def label_names_from_parquet(path: str) -> dict[int, str]:
    """Read the int->class-name map out of the parquet schema metadata."""
    schema = pq.read_schema(path)
    raw = (schema.metadata or {}).get(b"huggingface")
    if raw:
        info = json.loads(raw)
        feats = info.get("info", {}).get("features", {})
        names = feats.get("label", {}).get("names")
        if isinstance(names, dict):
            return {int(k): v for k, v in names.items()}
        if isinstance(names, list):
            return {i: v for i, v in enumerate(names)}
    return {}


def process(files: list[str], split: str, names: dict[int, str]) -> tuple[int, list[str]]:
    os.makedirs(OUT_DIR, exist_ok=True)
    x_path = os.path.join(OUT_DIR, f"{split}_X.dat")
    y_path = os.path.join(OUT_DIR, f"{split}_y.npy")

    # First pass: count rows so we can allocate the memmap exactly.
    total = 0
    for f in files:
        total += pq.ParquetFile(os.path.join(RAW_DIR, f)).metadata.num_rows
    print(f"[{split}] rows={total}", flush=True)

    X = np.memmap(x_path, dtype=DTYPE, mode="w+", shape=(total, SIZE, SIZE, 3))
    y = np.zeros(total, dtype=np.int16)

    idx = 0
    counter: Counter[int] = Counter()
    for f in files:
        pf = pq.ParquetFile(os.path.join(RAW_DIR, f))
        for batch in pf.iter_batches(batch_size=512, columns=["image", "label"]):
            imgs = batch.column("image").to_pylist()
            labs = batch.column("label").to_pylist()
            for rec, lab in zip(imgs, labs):
                raw = rec["bytes"] if isinstance(rec, dict) else rec
                if raw is None:
                    continue
                try:
                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                except Exception:
                    continue
                im = im.resize((SIZE, SIZE), Image.BILINEAR)
                X[idx] = np.asarray(im, dtype=DTYPE)
                y[idx] = int(lab)
                counter[int(lab)] += 1
                idx += 1
            if idx % 10240 < 512:
                print(f"[{split}] processed {idx}/{total}", flush=True)
                X.flush()

    # Trim memmap if some images failed to decode.
    if idx < total:
        X.flush()
        del X
        X = np.memmap(x_path, dtype=DTYPE, mode="r+", shape=(total, SIZE, SIZE, 3))
        arr = np.asarray(X[:idx])
        X = None
        X2 = np.memmap(x_path, dtype=DTYPE, mode="w+", shape=(idx, SIZE, SIZE, 3))
        X2[:] = arr
        X2.flush()
        y = y[:idx]

    np.save(y_path, y)
    del X
    print(f"[{split}] saved {idx} images -> {x_path} ({os.path.getsize(x_path)/1e6:.1f} MB)", flush=True)
    return idx, [names.get(k, str(k)) for k in sorted(counter)]


def main() -> None:
    names = label_names_from_parquet(os.path.join(RAW_DIR, TRAIN_FILES[0]))
    if not names:
        print("ERROR: could not read class names from parquet schema", file=sys.stderr)
        sys.exit(1)
    print(f"[meta] {len(names)} classes", flush=True)

    n_train, _ = process(TRAIN_FILES, "train", names)
    n_test, _ = process(TEST_FILES, "test", names)

    y_train = np.load(os.path.join(OUT_DIR, "train_y.npy"))
    counts = {names[int(k)]: int(v) for k, v in Counter(y_train.tolist()).items()}
    meta = {
        "num_classes": len(names),
        "class_names": [names[i] for i in range(len(names))],
        "image_size": SIZE,
        "train": {"count": int(n_train), "file": "train_X.dat"},
        "test": {"count": int(n_test), "file": "test_X.dat"},
        "train_class_counts": counts,
        "source": "GVJahnavi/PlantVillage_dataset (HuggingFace), PlantVillage / Mohanty et al. 2016",
        "license": "cc-by-sa-3.0",
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    print(f"[done] train={n_train} test={n_test} classes={len(names)}", flush=True)


if __name__ == "__main__":
    main()
