"""
Finalise the disease CNN artifacts.

The training run saves its best checkpoint but was killed before writing the
side files, so this script rebuilds them from the saved state dict:
  * evaluates the checkpoint on the held-out test split (per-class F1)
  * writes models/disease_cnn/meta.json  (what the web app reads)
  * exports models/disease_cnn/plant_disease_cnn.onnx (portable edge artifact)
  * folds the per-epoch history out of training/cnn_train.log into meta.json

Memory-light: it streams the test memmap in batches instead of loading images.
"""
from __future__ import annotations

import json
import os
import re
import sys

import numpy as np
import torch
import torch.nn as nn
from torchvision import models

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

DATA = os.path.join(BASE_DIR, "data", "plantvillage_processed")
OUT = os.path.join(BASE_DIR, "models", "disease_cnn")
CKPT = os.path.join(OUT, "plant_disease_cnn.pt")
LOG = os.path.join(BASE_DIR, "training", "cnn_train.log")
BATCH = 128


def build(names: list[str]) -> nn.Module:
    m = models.mobilenet_v3_small(weights=None)
    in_f = m.classifier[-1].in_features
    m.classifier[-1] = nn.Linear(in_f, len(names))
    return m


def parse_history() -> list[dict]:
    if not os.path.exists(LOG):
        return []
    hist = []
    pat = re.compile(
        r"\[(frozen-backbone|fine-tune) (\d+)/(\d+)\] loss=([\d.]+) "
        r"acc=([\d.]+) macroF1=([\d.]+) \((\d+)s\)")
    for line in open(LOG, errors="ignore"):
        mm = pat.search(line)
        if mm:
            hist.append({"phase": mm.group(1), "epoch": int(mm.group(2)),
                         "loss": float(mm.group(4)), "test_acc": float(mm.group(5)),
                         "test_macro_f1": float(mm.group(6)),
                         "epoch_seconds": int(mm.group(7))})
    return hist


def main() -> None:
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    names = ck["class_names"]
    model = build(names)
    model.load_state_dict(ck["state_dict"])
    model.eval()
    print(f"[load] {len(names)} classes, arch={ck.get('architecture')}", flush=True)

    meta = json.load(open(os.path.join(DATA, "meta.json")))
    n_test = meta["test"]["count"]
    X = np.memmap(os.path.join(DATA, "test_X.dat"), dtype=np.uint8, mode="r",
                  shape=(n_test, 128, 128, 3))
    y = np.load(os.path.join(DATA, "test_y.npy"))

    mean = torch.tensor(ck.get("mean", [0.485, 0.456, 0.406])).view(1, 3, 1, 1)
    std = torch.tensor(ck.get("std", [0.229, 0.224, 0.225])).view(1, 3, 1, 1)

    tp = np.zeros(len(names)); fp = np.zeros(len(names)); fn = np.zeros(len(names))
    correct = 0
    with torch.no_grad():
        for start in range(0, n_test, BATCH):
            stop = min(start + BATCH, n_test)
            batch = torch.from_numpy(np.asarray(X[start:stop])).permute(0, 3, 1, 2).float() / 255.0
            batch = (batch - mean) / std
            pred = model(batch).argmax(1).numpy()
            truth = y[start:stop]
            correct += int((pred == truth).sum())
            for t, p in zip(truth.tolist(), pred.tolist()):
                if t == p:
                    tp[t] += 1
                else:
                    fp[p] += 1
                    fn[t] += 1
            if start % (BATCH * 20) == 0:
                print(f"  evaluated {stop}/{n_test}", flush=True)

    acc = correct / n_test
    prec = tp / np.clip(tp + fp, 1, None)
    rec = tp / np.clip(tp + fn, 1, None)
    f1 = 2 * prec * rec / np.clip(prec + rec, 1e-9, None)
    print(f"[eval] accuracy={acc:.4f} macro_f1={f1.mean():.4f} on {n_test} images", flush=True)

    out = {
        "architecture": ck.get("architecture", "mobilenet_v3_small"),
        "framework": f"torch {torch.__version__}",
        "input_size": int(ck["input_size"]),
        "normalisation": {"mean": ck.get("mean"), "std": ck.get("std")},
        "num_classes": len(names),
        "class_names": names,
        "train_samples": meta["train"]["count"],
        "test_samples": int(n_test),
        "test_accuracy": round(float(acc), 4),
        "test_macro_f1": round(float(f1.mean()), 4),
        "per_class_f1": {names[i]: round(float(f1[i]), 4) for i in range(len(names))},
        "per_class_accuracy": {names[i]: round(float(rec[i]), 4) for i in range(len(names))},
        "test_class_counts": {names[int(k)]: int(v)
                              for k, v in zip(*np.unique(y, return_counts=True))},
        "dataset": meta.get("source", "PlantVillage"),
        "dataset_license": meta.get("license"),
        "history": parse_history(),
    }
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"[meta] wrote meta.json (per-class F1 for {len(names)} classes)", flush=True)

    try:
        torch.onnx.export(model, torch.randn(1, 3, 128, 128),
                          os.path.join(OUT, "plant_disease_cnn.onnx"),
                          input_names=["input"], output_names=["logits"],
                          dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
                          opset_version=17)
        sz = os.path.getsize(os.path.join(OUT, "plant_disease_cnn.onnx")) / 1e6
        print(f"[onnx] exported ({sz:.1f} MB)", flush=True)
    except Exception as exc:
        print(f"[onnx] export failed: {exc}", flush=True)

    # Confirm the ONNX artifact reproduces the PyTorch predictions.
    onnx_path = os.path.join(OUT, "plant_disease_cnn.onnx")
    if os.path.exists(onnx_path):
        try:
            import onnxruntime as ort
            sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
            xb = torch.from_numpy(np.asarray(X[:64])).permute(0, 3, 1, 2).float() / 255.0
            xb = ((xb - mean) / std).numpy()
            with torch.no_grad():
                a = model(torch.from_numpy(xb)).argmax(1).numpy()
            b = sess.run(None, {sess.get_inputs()[0].name: xb})[0].argmax(1)
            agree = float((a == b).mean())
            print(f"[verify] ONNX vs PyTorch agreement on 64 images: {agree*100:.1f}%", flush=True)
            out["onnx_parity_pct"] = round(agree * 100, 2)
            with open(os.path.join(OUT, "meta.json"), "w") as fh:
                json.dump(out, fh, indent=2)
        except Exception as exc:
            print(f"[verify] ONNX parity check failed: {exc}", flush=True)
    print("[done]", flush=True)


if __name__ == "__main__":
    main()
