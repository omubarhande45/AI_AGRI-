"""
Edge AI module - train the plant disease CNN.

Model    : torchvision MobileNetV3-Small (transfer learning from ImageNet)
Input    : 128x128 RGB, ImageNet normalisation
Data     : 43,503 train / 10,878 test images, 38 PlantVillage classes,
           read straight from a uint8 memmap so it fits in ~1 GB RAM
Strategy : freeze backbone 3 epochs (lr 1e-3) -> unfreeze 4 epochs (lr 5e-5)
Outputs  : models/disease_cnn/plant_disease_cnn.pt   (full state dict + meta)
           models/disease_cnn/plant_disease_cnn.onnx (portable edge artifact)
           models/disease_cnn/meta.json              (classes, metrics, history)

Run:  python3 training/train_disease_cnn.py [--epochs-frozen 3] [--epochs-fine 4] [--smoke]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torchvision import models
from torchvision.transforms import v2 as T

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "plantvillage_processed")
OUT_DIR = os.path.join(BASE_DIR, "models", "disease_cnn")
SIZE = 128
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
class MemmapLeafDataset(Dataset):
    """Random-slice reader over a uint8 memmap of (N, H, W, 3) leaves."""

    def __init__(self, split: str, augment: bool = False):
        meta = json.load(open(os.path.join(DATA_DIR, "meta.json")))
        n = meta[split]["count"]
        self.X = np.memmap(
            os.path.join(DATA_DIR, f"{split}_X.dat"),
            dtype=np.uint8, mode="r", shape=(n, SIZE, SIZE, 3),
        )
        self.y = np.load(os.path.join(DATA_DIR, f"{split}_y.npy"))
        self.augment = augment
        self.tf = T.Compose([
            T.ToImage(),
            T.ToDtype(torch.float32, scale=True),
            T.RandomHorizontalFlip(0.5),
            T.RandomVerticalFlip(0.5),
            T.RandomRotation(25),
            T.RandomResizedCrop(SIZE, scale=(0.7, 1.0), ratio=(0.8, 1.25)),
            T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05),
            T.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]) if augment else T.Compose([
            T.ToImage(),
            T.ToDtype(torch.float32, scale=True),
            T.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, i: int):
        img = np.array(self.X[i])          # force a copy out of the memmap
        return self.tf(img), int(self.y[i])


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
def build_model(num_classes: int, weights: bool = True) -> nn.Module:
    m = models.mobilenet_v3_small(
        weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1 if weights else None
    )
    # torchvision MobileNetV3 classifier is
    #   Linear(576,1024) -> Hardswish -> Dropout -> Linear(1024,1000)
    # so we replace the LAST Linear, keeping the 1024-d hidden layer.
    in_f = m.classifier[-1].in_features
    m.classifier[-1] = nn.Linear(in_f, num_classes)

    # Fail loudly on any shape mismatch instead of discovering it mid-training.
    with torch.no_grad():
        out = m(torch.zeros(2, 3, SIZE, SIZE))
    assert tuple(out.shape) == (2, num_classes), f"bad head shape {tuple(out.shape)}"
    return m


def freeze_backbone(model: nn.Module, freeze: bool) -> None:
    for name, p in model.named_parameters():
        p.requires_grad = not (freeze and name.startswith("features"))


# --------------------------------------------------------------------------
# Train / eval
# --------------------------------------------------------------------------
def evaluate(model, loader, device) -> tuple[float, float, list]:
    model.eval()
    correct = total = 0
    n_cls = model.classifier[-1].out_features
    tp = np.zeros(n_cls); fp = np.zeros(n_cls); fn = np.zeros(n_cls)
    with torch.no_grad():
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb).argmax(1)
            correct += (pred == yb).sum().item(); total += yb.numel()
            for t, p in zip(yb.tolist(), pred.tolist()):
                if t == p: tp[t] += 1
                else: fp[p] += 1; fn[t] += 1
    prec = tp / np.clip(tp + fp, 1, None)
    rec = tp / np.clip(tp + fn, 1, None)
    f1 = 2 * prec * rec / np.clip(prec + rec, 1e-9, None)
    return correct / max(total, 1), float(f1.mean()), f1.tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs-frozen", type=int, default=3)
    ap.add_argument("--epochs-fine", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-train", type=int, default=0, help="cap train samples (0 = all)")
    ap.add_argument("--max-test", type=int, default=0)
    ap.add_argument("--smoke", action="store_true", help="tiny run to validate the pipeline")
    args = ap.parse_args()

    if args.smoke:
        args.epochs_frozen, args.epochs_fine = 1, 1
        args.max_train, args.max_test = 640, 320

    os.makedirs(OUT_DIR, exist_ok=True)
    device = torch.device("cpu")
    torch.set_num_threads(os.cpu_count() or 2)

    meta = json.load(open(os.path.join(DATA_DIR, "meta.json")))
    class_names = meta["class_names"]
    num_classes = len(class_names)

    train_ds = MemmapLeafDataset("train", augment=True)
    test_ds = MemmapLeafDataset("test", augment=False)

    if args.max_train:
        idx = np.arange(len(train_ds))
        rng = np.random.default_rng(0)
        sel = rng.choice(idx, size=min(args.max_train, len(idx)), replace=False)
        train_ds = torch.utils.data.Subset(train_ds, sel.tolist())
    if args.max_test:
        rng = np.random.default_rng(1)
        sel = rng.choice(np.arange(len(test_ds)), size=min(args.max_test, len(test_ds)), replace=False)
        test_ds = torch.utils.data.Subset(test_ds, sel.tolist())

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=args.workers, persistent_workers=args.workers > 0,
                              drop_last=True)
    test_loader = DataLoader(test_ds, batch_size=128, shuffle=False,
                             num_workers=max(1, args.workers))

    print(f"[setup] train={len(train_ds)} test={len(test_ds)} classes={num_classes} "
          f"device={device} threads={torch.get_num_threads()}", flush=True)

    model = build_model(num_classes).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[model] MobileNetV3-Small params={n_params/1e6:.2f}M", flush=True)

    history: list[dict] = []
    best = {"acc": 0.0, "f1": 0.0, "epoch": -1}

    def run_phase(tag: str, epochs: int, lr: float, freeze: bool):
        nonlocal best
        freeze_backbone(model, freeze)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        opt = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=1e-4
        )
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(epochs, 1))
        print(f"[phase] {tag}: epochs={epochs} lr={lr:g} freeze={freeze} trainable={trainable/1e6:.2f}M",
              flush=True)
        for ep in range(epochs):
            model.train()
            t0 = time.time(); running = 0.0; nb = 0
            for xb, yb in train_loader:
                xb, yb = xb.to(device), yb.to(device)
                opt.zero_grad()
                loss = F.cross_entropy(model(xb), yb)
                loss.backward()
                opt.step()
                running += loss.item(); nb += 1
            sched.step()
            acc, f1, _ = evaluate(model, test_loader, device)
            dt = time.time() - t0
            rec = {"phase": tag, "epoch": ep + 1, "loss": running / max(nb, 1),
                   "test_acc": round(acc, 4), "test_macro_f1": round(f1, 4),
                   "epoch_seconds": round(dt, 1)}
            history.append(rec)
            print(f"  [{tag} {ep+1}/{epochs}] loss={rec['loss']:.4f} acc={acc:.4f} "
                  f"macroF1={f1:.4f} ({dt:.0f}s)", flush=True)
            if acc > best["acc"]:
                best = {"acc": acc, "f1": f1, "epoch": len(history) - 1}
                torch.save({"state_dict": model.state_dict(), "class_names": class_names,
                            "input_size": SIZE, "mean": IMAGENET_MEAN, "std": IMAGENET_STD,
                            "architecture": "mobilenet_v3_small",
                            "test_acc": round(acc, 4), "test_macro_f1": round(f1, 4)},
                           os.path.join(OUT_DIR, "plant_disease_cnn.pt"))
                print(f"  -> saved best checkpoint (acc={acc:.4f})", flush=True)

    run_phase("frozen-backbone", args.epochs_frozen, 1e-3, True)
    run_phase("fine-tune", args.epochs_fine, 5e-5, False)

    # Final metrics with the best checkpoint reloaded.
    ckpt = torch.load(os.path.join(OUT_DIR, "plant_disease_cnn.pt"), map_location=device,
                      weights_only=False)
    model.load_state_dict(ckpt["state_dict"])
    acc, f1, per_class = evaluate(model, test_loader, device)
    print(f"[final] acc={acc:.4f} macroF1={f1:.4f}", flush=True)

    y_test = test_ds.y if isinstance(test_ds, MemmapLeafDataset) else np.array(
        [test_ds.dataset.y[i] for i in test_ds.indices])
    counts = Counter(y_test.tolist())

    meta_out = {
        "architecture": "mobilenet_v3_small (transfer learning from ImageNet)",
        "framework": f"torch {torch.__version__}",
        "input_size": SIZE,
        "normalisation": {"mean": IMAGENET_MEAN, "std": IMAGENET_STD},
        "num_classes": num_classes,
        "class_names": class_names,
        "train_samples": len(train_ds),
        "test_samples": len(test_ds),
        "test_accuracy": round(acc, 4),
        "test_macro_f1": round(f1, 4),
        "per_class_f1": {class_names[i]: round(float(per_class[i]), 4) for i in range(num_classes)},
        "test_class_counts": {class_names[int(k)]: int(v) for k, v in counts.items()},
        "dataset": meta.get("source", "PlantVillage"),
        "history": history,
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w") as fh:
        json.dump(meta_out, fh, indent=2)

    # Portable edge artifact (ONNX) - runs on Raspberry Pi / Android via ONNX Runtime.
    try:
        dummy = torch.randn(1, 3, SIZE, SIZE)
        torch.onnx.export(model, dummy, os.path.join(OUT_DIR, "plant_disease_cnn.onnx"),
                          input_names=["input"], output_names=["logits"],
                          dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
                          opset_version=17)
        print("[export] ONNX written", flush=True)
    except Exception as exc:  # ONNX export is a bonus, never fatal
        print(f"[export] ONNX skipped: {exc}", flush=True)

    size_mb = os.path.getsize(os.path.join(OUT_DIR, "plant_disease_cnn.pt")) / 1e6
    print(f"[done] checkpoint {size_mb:.1f} MB, best acc={best['acc']:.4f}", flush=True)


if __name__ == "__main__":
    main()
