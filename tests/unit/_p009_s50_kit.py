# ruff: noqa: E501
"""Shared builders for the `s50_evaluate` tests of spec 009 (T-009-033 and later). Holds no test; imports numpy and `_p009_ap_kit` only.

Imported with `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))`. Locked with T-009-033.

The fixture family is a FRACTION fixture whose AP is known in closed form: every test image holds one 10 x 10 px box of each class that
the builder lists (positions fixed per class, so boxes never overlap), a model detects the first `detected` images perfectly (IoU 1, a
distinct score each, no false positive) and misses the rest. For a class with n ground-truth instances of which d are detected, the
precision is 1 up to recall d / n and there is no further detection, so the 101-point AP50 (and AP50:95, IoU 1 matches at every
threshold) is the number of recall points r_k = k / 100 with r_k <= d / n divided by 101:  AP = (floor(100 d / n) + 1) / 101  (hand
calculation, confirmed against `pycocotools`). Examples: d = n = 100 -> 1.0; d = 85 of 100 -> 86 / 101 = 0.851485; d = 80 of 100 -> 81 / 101
= 0.801980; d = 79 of 100 -> 80 / 101 = 0.792079.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

import _p009_ap_kit as apkit  # same folder: the importing test puts tests/unit on sys.path
import numpy as np

SIZE = 64
CLASS_X = {1: 4, 2: 16, 3: 28, 4: 40, 5: 52}  # x of the 10 x 10 box of each class; y is 20


def box_of(class_id: int) -> tuple[float, float, float, float]:
    return (float(CLASS_X[class_id]), 20.0, 10.0, 10.0)


def ap_of_fraction(detected: int, n: int) -> float:
    """AP of the fraction fixture: grid points of np.linspace(0, 1, 101) not above d / n, over 101 (see the module docstring)."""
    return float((np.linspace(0.0, 1.0, 101) <= detected / n).sum()) / 101.0


def fraction_gt(
    n_pit: int = 100,
    n_crusher: int = 100,
    *,
    classes: Sequence[int] = (1, 2, 3, 4, 5),
    class_limit: Mapping[int, int] | None = None,
    images_per_seed: int = 10,
) -> tuple[dict[str, Any], dict[int, str], dict[int, int]]:
    """Pooled held-out ground truth: images 1..n_pit are the pit family, the next n_crusher the crusher family; each image holds one box
    of every class in `classes`; `class_limit[c]` keeps class c only in the first `class_limit[c]` images (to make a class scarce).
    Returns (gt, image_family, image_cluster); clusters are scenario seeds 1000 + (id - 1) // images_per_seed."""
    n = n_pit + n_crusher
    images = [apkit.image(i, SIZE, SIZE) for i in range(1, n + 1)]
    anns: list[dict[str, Any]] = []
    aid = 0
    for i in range(1, n + 1):
        for c in classes:
            if class_limit and c in class_limit and i > class_limit[c]:
                continue
            aid += 1
            anns.append(apkit.annotation(aid, i, c, box_of(c)))
    family = {i: ("pit" if i <= n_pit else "crusher") for i in range(1, n + 1)}
    cluster = {i: 1000 + (i - 1) // images_per_seed for i in range(1, n + 1)}
    return apkit.gt_doc(images, anns), family, cluster


def perfect_detections(
    gt: Mapping[str, Any], detected_images: set[int], *, score_base: float = 0.5, masks: bool = False
) -> list[dict[str, Any]]:
    """A perfect detection (IoU 1) of every ground-truth box whose image is in `detected_images`; distinct scores; no false positive.
    With `masks` each detection also carries its binary mask (SIZE x SIZE uint8) as "segmentation"."""
    dets = []
    for k, a in enumerate(gt["annotations"]):
        if a["image_id"] not in detected_images:
            continue
        d = apkit.detection(a["image_id"], a["category_id"], a["bbox"], score_base + (k + 1) / 1e6)
        if masks:
            x, y, w, h = (int(v) for v in a["bbox"])
            m = np.zeros((SIZE, SIZE), dtype=np.uint8)
            m[y : y + h, x : x + w] = 1
            d["segmentation"] = m
        dets.append(d)
    return dets


def prediction(
    model: str, precision: str, arm: str, detections: list[dict[str, Any]], gt: Mapping[str, Any], **extra: Any
) -> dict[str, Any]:
    """One prediction set as s50_evaluate takes it: model, precision, arm, detections and the image ids it covers (all test images)."""
    return {
        "model": model,
        "precision": precision,
        "arm": arm,
        "image_ids": [im["id"] for im in gt["images"]],
        "detections": detections,
        **extra,
    }


def spec(
    gt: Mapping[str, Any],
    family: Mapping[int, str],
    cluster: Mapping[int, int],
    predictions: list[dict[str, Any]],
    **over: Any,
) -> dict[str, Any]:
    """An s50_evaluate spec with a small bootstrap (resamples 6) so unit tests stay fast."""
    base = {
        "run_id": "20261012T100000Z-s50",
        "gt": copy.deepcopy(dict(gt)),
        "image_family": dict(family),
        "image_cluster": dict(cluster),
        "predictions": predictions,
        "bootstrap": {"seed": 90210, "resamples": 6},
    }
    base.update(over)
    return base


def find_rows(report: Mapping[str, Any], **keys: Any) -> list[dict[str, Any]]:
    """Rows of report["per_class"] whose fields equal `keys` (e.g. model="d-fine-s", family="pit", task="box")."""
    return [r for r in report["per_class"] if all(r.get(k) == v for k, v in keys.items())]


def summary_row(report: Mapping[str, Any], **keys: Any) -> dict[str, Any]:
    rows = [r for r in report["summary"] if all(r.get(k) == v for k, v in keys.items())]
    assert len(rows) == 1, (keys, len(rows))
    return rows[0]


def acceptance_row(report: Mapping[str, Any], criterion: str, **keys: Any) -> dict[str, Any]:
    rows = [
        r for r in report["acceptance"] if r["criterion"] == criterion and all(r.get(k) == v for k, v in keys.items())
    ]
    assert len(rows) == 1, (criterion, keys, len(rows))
    return rows[0]
