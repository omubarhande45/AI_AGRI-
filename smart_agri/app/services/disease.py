"""
Edge AI module - plant disease & pest detection service.

Runs the trained MobileNetV3-Small CNN offline on a single leaf photo.
  * PyTorch is used if available, otherwise the ONNX artifact via ONNX Runtime
    (this is the code path that ships to a Raspberry Pi / Android edge device).
  * Returns top-k classes, confidence, severity, crop mapping, management
    advice from the disease knowledge base and an expected yield-loss figure.

The model is loaded once and cached in a module-level singleton.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from datetime import datetime
from typing import Any

import numpy as np

from ..agronomy import (CLASS_TO_CROP, DISEASE_DB, REGIONAL_CLASSES,
                        severity_from_confidence, yield_loss)
from ..config import (DISEASE_CONFIDENCE_FLOOR, DISEASE_META_FILE,
                      DISEASE_MODEL_FILE, DISEASE_INPUT_SIZE)

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _norm(name: str) -> str:
    """Normalise a PlantVillage class name for lookup.

    Different mirrors of PlantVillage spell the crop/disease separator with two
    or three underscores (``Apple__Apple_scab`` vs ``Apple___Apple_scab``), so a
    strict dict lookup silently misses those rows. Collapsing underscore runs
    and case makes the knowledge base robust to either spelling.
    """
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip().lower()


_INFO_BY_NORM = {_norm(k): v for k, v in DISEASE_DB.items()}
_CLASS_BY_NORM = {_norm(k): k for k in DISEASE_DB}


def disease_info(cls: str):
    """Return the DiseaseInfo for a raw model class name, or None."""
    return _INFO_BY_NORM.get(_norm(cls))


def canonical_class(cls: str) -> str:
    """Map a model class name onto the knowledge-base spelling."""
    return _CLASS_BY_NORM.get(_norm(cls), cls)


class DiseaseModel:
    """Lazy singleton wrapper around the trained CNN."""

    def __init__(self) -> None:
        self._ready = False
        self._backend: str = "none"
        self._model = None
        self._session = None
        self.class_names: list[str] = []
        self.meta: dict[str, Any] = {}
        self.input_size = DISEASE_INPUT_SIZE

    # -- loading ---------------------------------------------------------
    @property
    def available(self) -> bool:
        if not self._ready:
            self._load()
        return self._backend != "none"

    @property
    def backend(self) -> str:
        if not self._ready:
            self._load()
        return self._backend

    def _load(self) -> None:
        self._ready = True
        if os.path.exists(DISEASE_META_FILE):
            with open(DISEASE_META_FILE) as fh:
                self.meta = json.load(fh)
            self.class_names = self.meta.get("class_names", [])
            self.input_size = int(self.meta.get("input_size", DISEASE_INPUT_SIZE))

        # Prefer PyTorch (fastest to set up here), fall back to ONNX Runtime.
        pt_path = DISEASE_MODEL_FILE
        onnx_path = pt_path.replace(".pt", ".onnx")
        try:
            if os.path.exists(pt_path):
                import torch
                from torchvision import models

                ckpt = torch.load(pt_path, map_location="cpu", weights_only=False)
                names = ckpt.get("class_names") or self.class_names
                if not names:
                    raise RuntimeError("checkpoint has no class names")
                m = models.mobilenet_v3_small(weights=None)
                in_f = m.classifier[-1].in_features
                import torch.nn as nn
                m.classifier[-1] = nn.Linear(in_f, len(names))
                m.load_state_dict(ckpt["state_dict"])
                m.eval()
                self._model = (m, torch)
                self.class_names = names
                self._backend = "pytorch"
                if "test_accuracy" in ckpt:
                    self.meta.setdefault("test_accuracy", ckpt["test_accuracy"])
                return
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"[edge_ai] PyTorch backend unavailable: {exc}")

        try:
            if os.path.exists(onnx_path):
                import onnxruntime as ort
                self._session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
                self._backend = "onnxruntime"
                return
        except Exception as exc:  # pragma: no cover
            print(f"[edge_ai] ONNX backend unavailable: {exc}")

        print("[edge_ai] no model artifact found - service will report unavailable")

    # -- inference -------------------------------------------------------
    def preprocess(self, img_rgb: np.ndarray) -> np.ndarray:
        """HxWx3 uint8 RGB -> 1x3xSxS float32 ImageNet-normalised."""
        from PIL import Image
        s = self.input_size
        pil = Image.fromarray(img_rgb.astype(np.uint8), mode="RGB")
        pil = pil.resize((s, s), resample=Image.Resampling.BILINEAR)
        img = np.asarray(pil, dtype=np.float32) / 255.0
        img = (img - _IMAGENET_MEAN) / _IMAGENET_STD
        return np.transpose(img, (2, 0, 1))[None, ...].astype(np.float32)

    def logits(self, x: np.ndarray) -> np.ndarray:
        if self._backend == "pytorch":
            m, torch = self._model
            with torch.no_grad():
                return m(torch.from_numpy(x)).numpy()[0]
        if self._backend == "onnxruntime":
            name = self._session.get_inputs()[0].name
            return self._session.run(None, {name: x})[0][0]
        raise RuntimeError("disease model not available")

    def softmax(self, z: np.ndarray) -> np.ndarray:
        z = z - z.max()
        e = np.exp(z)
        return e / e.sum()

    def predict_array(self, img_rgb: np.ndarray, top_k: int = 5) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError("disease model is not trained/loaded yet")
        probs = self.softmax(self.logits(self.preprocess(img_rgb)))
        order = np.argsort(probs)[::-1][:top_k]
        regional_norm = {_norm(c) for c in REGIONAL_CLASSES}
        preds = []
        for i in order:
            raw_cls = self.class_names[int(i)]
            info = disease_info(raw_cls)
            conf = float(probs[int(i)])
            cls = canonical_class(raw_cls)
            if info is None:
                preds.append({
                    "class": cls, "disease": cls, "crop": "Unknown", "confidence": conf,
                    "pathogen_type": "unknown", "regional": False,
                    "severity": "unknown", "symptoms": "", "management": [],
                    "organic": "", "expected_yield_loss_pct": 0.0, "spread_risk": "unknown",
                })
                continue
            preds.append({
                "class": cls,
                "disease": info.display_name,
                "crop": info.crop,
                "confidence": conf,
                "pathogen_type": info.pathogen_type,
                "regional": _norm(raw_cls) in regional_norm,
                "severity": severity_from_confidence(conf, info.severity_weight),
                "symptoms": info.symptoms,
                "management": list(info.management),
                "organic": info.organic,
                "expected_yield_loss_pct": yield_loss(conf, info),
                "spread_risk": info.spread_risk,
            })
        top = preds[0]
        return {
            "top": top,
            "predictions": preds,
            "is_healthy": top["pathogen_type"] == "none",
            "confident": top["confidence"] >= DISEASE_CONFIDENCE_FLOOR,
            "backend": self._backend,
            "model_accuracy": self.meta.get("test_accuracy"),
            "input_size": self.input_size,
            "predicted_at": datetime.now().isoformat(timespec="seconds"),
        }

    # -- Grad-CAM explainability ----------------------------------------
    def gradcam(self, img_rgb: np.ndarray, target_class: int | None = None) -> np.ndarray | None:
        """Class-activation heatmap so the farmer can see WHERE the disease is."""
        if self._backend != "pytorch":
            return None
        import torch
        from PIL import Image

        m, _ = self._model
        s = self.input_size
        resized = Image.fromarray(img_rgb.astype(np.uint8), mode="RGB").resize(
            (s, s), resample=Image.Resampling.BILINEAR)
        img = np.asarray(resized, dtype=np.float32) / 255.0
        img = (img - _IMAGENET_MEAN) / _IMAGENET_STD
        x = torch.from_numpy(np.transpose(img, (2, 0, 1))[None, ...]).float()

        # Register a TENSOR hook on the last conv block's output. A module
        # backward hook would give the gradient wrt the block's INPUT (96 ch),
        # which cannot be combined with the 576-channel activations.
        target = m.features[-1]
        acts: list[torch.Tensor] = []
        grads: list[torch.Tensor] = []
        handle_holder: list = []

        def fwd_hook(_mod, _inp, out):
            acts.append(out)
            handle_holder.append(out.register_hook(lambda g: grads.append(g)))

        h = target.register_forward_hook(fwd_hook)
        try:
            m.zero_grad()
            out = m(x)
            cls = int(out.argmax(1)[0]) if target_class is None else int(target_class)
            out[0, cls].backward()
            if not acts or not grads:
                return None
            a = acts[0][0]                      # (576, 4, 4)
            g = grads[0][0]                     # (576, 4, 4)
            w = g.mean(dim=(1, 2), keepdim=True)
            cam = (w * a).sum(dim=0).clamp(min=0)
        finally:
            h.remove()
            for hh in handle_holder:
                hh.remove()

        cam = cam.detach().numpy()
        if cam.max() <= 0:
            return None
        cam_img = Image.fromarray((cam * 255).astype(np.uint8)).resize(
            (s, s), resample=Image.Resampling.BILINEAR)
        cam = np.asarray(cam_img, dtype=np.float32) / 255.0
        cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
        self._last_cam = cam

        heat = np.empty((s, s, 3), dtype=np.uint8)
        heat[..., 0] = np.clip(cam * 255 * 2, 0, 255)
        heat[..., 1] = np.clip((1.0 - np.abs(cam - 0.5) * 2) * 255, 0, 255)
        heat[..., 2] = np.clip((1.0 - cam) * 255, 0, 255)
        base = np.asarray(Image.fromarray(img_rgb.astype(np.uint8)).resize(
            (s, s), resample=Image.Resampling.BILINEAR), dtype=np.uint8)
        return np.clip(base * 0.55 + heat * 0.45, 0, 255).astype(np.uint8)


MODEL = DiseaseModel()


def encode_png(rgb: np.ndarray) -> str:
    """RGB array -> inline PNG data URI."""
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8), mode="RGB").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def detect_from_upload(storage, max_side: int = 900) -> tuple[dict[str, Any], np.ndarray]:
    """Read an uploaded image and run detection; return (result, rgb_image)."""
    from PIL import Image
    raw = storage.read()
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise ValueError("could not decode image - please upload a JPG or PNG photo")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), resample=Image.Resampling.BILINEAR)
    rgb = np.asarray(img, dtype=np.uint8)
    result = MODEL.predict_array(rgb)
    return result, rgb
