"""Re-score the trained disease CNN on the small held-out validation subset.

The full PlantVillage split is deleted after training to keep the repo small, so
this uses the 228-image subset in data/validation_set/. Expect variance: 228
images is a much smaller sample than the 10,878-image test split.
"""
from __future__ import annotations

import json
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.disease import MODEL, canonical_class  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "validation_set")


def main() -> None:
    if not MODEL.available:
        sys.exit("No trained model found - run training/train_disease_cnn.py first.")
    manifest = json.load(open(os.path.join(HERE, "manifest.json")))
    images = manifest["images"]

    correct = 0
    misses: list[str] = []
    for item in images:
        bgr = cv2.imread(os.path.join(HERE, item["file"]))
        if bgr is None:
            continue
        pred = MODEL.predict_array(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        # Compare through canonical_class(): the dataset spells some classes with
        # two underscores (Apple__Apple_scab) while the knowledge base uses three,
        # and a raw string compare would count a correct hit as a miss.
        if canonical_class(pred["top"]["class"]) == canonical_class(item["class"]):
            correct += 1
        else:
            misses.append(f"{item['class']} -> {pred['top']['disease']} "
                          f"({pred['top']['confidence']*100:.0f}%)")

    n = len(images)
    print(f"backend        : {MODEL.backend}")
    print(f"reported test  : {MODEL.meta.get('test_accuracy')} accuracy on "
          f"{MODEL.meta.get('test_samples')} images")
    print(f"this subset    : {100*correct/n:.1f}% on {n} images ({n // len(MODEL.class_names)} per class)")
    if misses:
        print(f"\n{len(misses)} misclassifications:")
        for m in misses:
            print("  ", m)


if __name__ == "__main__":
    main()
