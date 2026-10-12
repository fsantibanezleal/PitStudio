"""The optional labelled real probe: aggregate metrics, inter-annotator agreement and hostile probe inputs (FR-009-33,
FR-009-34).

The probe is at most 200 real images with a per-file licence from a fixed list and boxes from two labellers. Detectors are
scored against labeller A (AP50 per class with an image-bootstrap interval); labeller B gives a sensitivity mAP50 and the
per-class box F1 between the two labellers measures their agreement. Only aggregate metrics are published: no file name and no
image id leaves this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pitstudio_pipeline.perception import evaluate as ev
from pitstudio_pipeline.perception.classes import CLASSES

ALLOWED_LICENCES: frozenset[str] = frozenset({"CC0-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0", "public domain"})
PROBE_CLASSES: tuple[int, ...] = (1, 2, 3, 4)  # haul_truck, shovel, light_vehicle, person; boulder has no probe
MAX_IMAGES = 200
_NAMES = dict(CLASSES)
_IOU_THRESHOLD = 0.5


class ProbeError(Exception):
    """The probe is refused (`probe-invalid`)."""

    code = "probe-invalid"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.code}: {reason}")


@dataclass(frozen=True)
class ProbeSelection:
    """The probe images that may be used (input order) and the excluded ones as (file name, reason)."""

    included: tuple[dict[str, Any], ...]
    excluded: tuple[tuple[str, str], ...]


def load_probe(
    images: Sequence[Mapping[str, Any]], licence_records: Mapping[str, Mapping[str, Any]], *, annotations_b: object
) -> ProbeSelection:
    """Select the probe images with an allowed per-file licence; refuse the probe (`probe-invalid`) when more than 200
    images are supplied, the second labeller's file is missing or the image list is malformed."""
    if not isinstance(images, list) or not all(isinstance(i, Mapping) for i in images):
        raise ProbeError("images must be a list of {id, file_name} objects")
    ids: set[int] = set()
    for img in images:
        iid, name = img.get("id"), img.get("file_name")
        if not isinstance(iid, int) or isinstance(iid, bool) or not isinstance(name, str) or not name:
            raise ProbeError("every image needs an int id and a non-empty file_name")
        if iid in ids:
            raise ProbeError(f"image id {iid} occurs twice")
        ids.add(iid)
    if len(images) > MAX_IMAGES:
        raise ProbeError(f"{len(images)} images supplied, at most {MAX_IMAGES} are allowed")
    if annotations_b is None:
        raise ProbeError("the second labeller's file is missing")
    included: list[dict[str, Any]] = []
    excluded: list[tuple[str, str]] = []
    for img in images:
        name = img["file_name"]
        record = licence_records.get(name)
        spdx = record.get("spdx") if isinstance(record, Mapping) else None
        if record is None:
            excluded.append((name, "no licence record"))
        elif not isinstance(spdx, str) or spdx not in ALLOWED_LICENCES:
            excluded.append((name, f"licence {spdx!r} is not in the allowed list"))
        else:
            included.append(dict(img))
    return ProbeSelection(tuple(included), tuple(excluded))


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    iw = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def agreement_f1(
    boxes_a: Sequence[Mapping[str, Any]], boxes_b: Sequence[Mapping[str, Any]], *, iou_threshold: float = _IOU_THRESHOLD
) -> dict[int, float | None]:
    """Per category with boxes: F1 = 2 TP / (n_A + n_B), greedy one-to-one matching by descending IoU within an image."""
    categories = sorted({int(b["category_id"]) for b in boxes_a} | {int(b["category_id"]) for b in boxes_b})
    out: dict[int, float | None] = {}
    for cat in categories:
        a = [b for b in boxes_a if int(b["category_id"]) == cat]
        b = [x for x in boxes_b if int(x["category_id"]) == cat]
        pairs = sorted(
            (
                (-_iou(p["bbox"], q["bbox"]), i, j)
                for i, p in enumerate(a)
                for j, q in enumerate(b)
                if p["image_id"] == q["image_id"]
            )
        )
        used_a: set[int] = set()
        used_b: set[int] = set()
        tp = 0
        for neg_iou, i, j in pairs:
            if -neg_iou < iou_threshold:
                break
            if i in used_a or j in used_b:
                continue
            used_a.add(i)
            used_b.add(j)
            tp += 1
        total = len(a) + len(b)
        out[cat] = None if total == 0 else 2.0 * tp / total
    return out


def _gt_doc(images: Sequence[Mapping[str, Any]], annotations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "images": [{"id": int(i["id"]), "file_name": str(i["file_name"]), "width": 1, "height": 1} for i in images],
        "annotations": [
            {
                "id": k + 1,
                "image_id": int(a["image_id"]),
                "category_id": int(a["category_id"]),
                "bbox": [float(v) for v in a["bbox"]],
                "area": float(a["bbox"][2]) * float(a["bbox"][3]),
                "iscrowd": 0,
            }
            for k, a in enumerate(annotations)
        ],
        "categories": [{"id": cid, "name": name} for cid, name in CLASSES],
    }


def _check_categories(rows: Sequence[Mapping[str, Any]], where: str) -> None:
    for r in rows:
        if int(r["category_id"]) not in PROBE_CLASSES:
            raise ValueError(f"category_id {r['category_id']} in {where} is not one of the probe classes {PROBE_CLASSES}")


def evaluate_probe(
    *,
    images: Sequence[Mapping[str, Any]],
    annotations_a: Sequence[Mapping[str, Any]],
    annotations_b: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, Sequence[Mapping[str, Any]]],
    seed: int,
    excluded_images: int = 0,
    resamples: int = 2000,
) -> dict[str, Any]:
    """The `real_probe` block of DC-009-05: aggregate metrics only (no file name, no image id)."""
    if not isinstance(resamples, int) or isinstance(resamples, bool) or resamples < 1:
        raise ValueError(f"resamples must be an int >= 1, got {resamples!r}")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError(f"seed must be an int, got {seed!r}")
    _check_categories(annotations_a, "annotations_a")
    _check_categories(annotations_b, "annotations_b")
    for model, dets in predictions.items():
        _check_categories(dets, f"the predictions of {model}")
    gt_a = _gt_doc(images, annotations_a)
    gt_b = _gt_doc(images, annotations_b)
    cluster = {int(i["id"]): int(i["id"]) for i in images}  # image-level bootstrap: every image is its own cluster
    per_class: list[dict[str, Any]] = []
    labeller_b: list[dict[str, Any]] = []
    for model in sorted(predictions):
        dets = list(predictions[model])
        point = ev.evaluate_boxes(gt_a, dets, min_support=1)
        boot = ev.bootstrap_intervals(gt_a, dets, cluster, resamples=resamples, seed=seed, min_support=1)
        for cid in PROBE_CLASSES:
            m = point.per_class[cid]
            if m.support > 0:
                lo, hi = boot.per_class[cid]["ap50"]
                per_class.append(
                    {
                        "model": model,
                        "class": _NAMES[cid],
                        "support": m.support,
                        "ap50": m.ap50,
                        "ap50_interval": {"lower": lo, "upper": hi},
                    }
                )
        point_b = ev.evaluate_boxes(gt_b, dets, min_support=1)
        if point_b.map50 is not None:
            labeller_b.append({"model": model, "map50": point_b.map50})
    f1 = agreement_f1(
        [{**a} for a in annotations_a], [{**b} for b in annotations_b], iou_threshold=_IOU_THRESHOLD
    )
    agreement = [
        {"class": _NAMES[cid], "box_f1": value, "iou_threshold": _IOU_THRESHOLD}
        for cid, value in sorted(f1.items())
        if value is not None
    ]
    return {
        "images": len(images),
        "excluded_images": int(excluded_images),
        "ground_truth": "labeller-a",
        "per_class": per_class,
        "labeller_b_map50": labeller_b,
        "agreement": agreement,
        "bootstrap": {"resamples": resamples, "method": "image-percentile", "level": 0.95, "seed": seed},
        "aggregate_only": True,
    }
