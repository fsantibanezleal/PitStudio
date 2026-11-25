# ruff: noqa: E501
"""Shared COCO fixtures and the `pycocotools` reference of the spec 009 evaluation tests (T-009-032 and later). Holds no test.

Imported with `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))`. Locked with T-009-032. Standard library and
numpy at import time; `pycocotools` is imported inside `ref_eval` only (it is a dependency of the code under test, resolved by
T-009-000, so a red test fails first on the missing first-party module, never here).

- builders of images, annotations (polygon = the box) and COCO ground-truth documents for the five perception classes;
- `random_fixture`: a seeded random ground truth and detection set with distinct scores (numpy PCG64);
- `ref_eval`: the reference implementation the spec names (FR-009-22): COCOeval called directly with the COCO protocol (IoU
  thresholds 0.50:0.05:0.95, 101 recall points, maxDets 100, area "all"); per class it returns AP50 and AP50:95 as the mean of the
  precision array over its defined (> -1) entries, exactly the quantity COCOeval's summary prints for `area=all, maxDets=100`.
"""

from __future__ import annotations

import contextlib
import copy
import io
from collections.abc import Sequence
from typing import Any

import numpy as np

CATEGORIES = [
    {"id": i, "name": n, "supercategory": s}
    for i, n, s in [
        (1, "haul_truck", "vehicle"),
        (2, "shovel", "vehicle"),
        (3, "light_vehicle", "vehicle"),
        (4, "person", "person"),
        (5, "boulder", "rock"),
    ]
]


def image(image_id: int, width: int = 100, height: int = 100) -> dict[str, Any]:
    return {"id": image_id, "file_name": f"rgb/{image_id:06d}.png", "width": width, "height": height}


def poly_of(x: float, y: float, w: float, h: float) -> list[list[float]]:
    return [[x, y, x + w, y, x + w, y + h, x, y + h]]


def annotation(ann_id: int, image_id: int, category_id: int, bbox: Sequence[float]) -> dict[str, Any]:
    x, y, w, h = (float(v) for v in bbox)
    return {
        "id": ann_id,
        "image_id": image_id,
        "category_id": category_id,
        "bbox": [x, y, w, h],
        "segmentation": poly_of(x, y, w, h),
        "area": w * h,
        "iscrowd": 0,
    }


def gt_doc(images: list[dict], annotations: list[dict]) -> dict[str, Any]:
    return {"images": images, "annotations": annotations, "categories": copy.deepcopy(CATEGORIES)}


def detection(image_id: int, category_id: int, bbox: Sequence[float], score: float) -> dict[str, Any]:
    return {"image_id": image_id, "category_id": category_id, "bbox": [float(v) for v in bbox], "score": float(score)}


def random_fixture(
    seed: int, n_images: int, max_boxes: int, *, size: int = 1000, n_classes: int = 5, fp_rate: float = 0.3
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Seeded random ground truth (0..max_boxes boxes per image, 10..200 px, inside [0, size - 250]) and detections: a jittered copy
    of ~70 % of the boxes plus false positives; every score is distinct."""
    rng = np.random.default_rng(seed)
    images, anns, dets = [], [], []
    ann_id = 1
    for i in range(1, n_images + 1):
        images.append(image(i, size, size))
        for _ in range(int(rng.integers(0, max_boxes + 1))):
            x, y = (float(v) for v in rng.integers(0, size - 250, size=2))
            w, h = (float(v) for v in rng.integers(10, 200, size=2))
            c = int(rng.integers(1, n_classes + 1))
            anns.append(annotation(ann_id, i, c, [x, y, w, h]))
            ann_id += 1
            if rng.random() < 0.7:
                jx, jy = rng.normal(0.0, 0.05 * w), rng.normal(0.0, 0.05 * h)
                dets.append(
                    detection(
                        i, c, [x + jx, y + jy, w * float(rng.uniform(0.9, 1.1)), h * float(rng.uniform(0.9, 1.1))], 0.0
                    )
                )
            if rng.random() < fp_rate:
                fx, fy = (float(v) for v in rng.integers(0, size - 250, size=2))
                dets.append(
                    detection(
                        i,
                        int(rng.integers(1, n_classes + 1)),
                        [fx, fy, float(rng.integers(10, 200)), float(rng.integers(10, 200))],
                        0.0,
                    )
                )
    scores = (rng.permutation(len(dets)) + 1.0) / (len(dets) + 1.0)  # distinct, in (0, 1)
    for d, s in zip(dets, scores, strict=True):
        d["score"] = float(s)
    return gt_doc(images, anns), dets


def rle_of(mask: np.ndarray) -> dict[str, Any]:
    from pycocotools import mask as mask_utils

    rle = mask_utils.encode(np.asfortranarray(mask.astype(np.uint8)))
    rle["counts"] = rle["counts"].decode("ascii")
    return rle


def ref_eval(
    gt: dict[str, Any], dets: list[dict[str, Any]], iou_type: str = "bbox"
) -> dict[int, tuple[float | None, float | None]]:
    """Per category id: (AP50, AP50:95) from pycocotools COCOeval (None where the class has no ground truth)."""
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval

    with contextlib.redirect_stdout(io.StringIO()):
        coco_gt = COCO()
        coco_gt.dataset = copy.deepcopy(gt)
        coco_gt.createIndex()
        if not dets:
            return {
                c["id"]: (0.0, 0.0) if any(a["category_id"] == c["id"] for a in gt["annotations"]) else (None, None)
                for c in gt["categories"]
            }
        coco_dt = coco_gt.loadRes(copy.deepcopy(dets))
        ev = COCOeval(coco_gt, coco_dt, iou_type)
        ev.params.maxDets = [1, 10, 100]
        ev.evaluate()
        ev.accumulate()
    precision = ev.eval["precision"]  # [T, R, K, A, M]
    out: dict[int, tuple[float | None, float | None]] = {}
    for k, cid in enumerate(ev.params.catIds):
        p50 = precision[0, :, k, 0, 2]
        pall = precision[:, :, k, 0, 2]
        out[cid] = (
            float(p50[p50 > -1].mean()) if (p50 > -1).any() else None,
            float(pall[pall > -1].mean()) if (pall > -1).any() else None,
        )
    return out


def box_iou(a: Sequence[float], b: Sequence[float]) -> float:
    """IoU of two xywh boxes (hand formula)."""
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0
