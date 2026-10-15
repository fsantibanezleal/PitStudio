"""`s40_infer` and the evaluation input of `s50_evaluate` on the held-out test split of the SDG index (FR-009-22).

Test records are the pit-family records of the split `test`, sorted by `record_id`; their evaluation image ids are
1..N in
that order (the `coco_image_id` of a record is only unique inside its shard). `build_test_gt` merges the COCO files of
the
records into one ground-truth document, `predict_dfine` and `predict_rfdetr` write detections for the same images (boxes
`[x, y, w, h]` in the original image, `category_id` 1..5; RF-DETR adds RLE masks). Inference is fp32; the
reduced-precision
variants and their parity are spec 016.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_pipeline.perception import dfine
from pitstudio_pipeline.perception.classes import CLASSES


def test_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Pit-family test records sorted by `record_id`; the position (from 1) is the evaluation image id."""
    return sorted(
        (dict(r) for r in records if r["split"] == "test" and r["family"] == "pit"), key=lambda r: r["record_id"]
    )


def build_test_gt(
    records: Sequence[Mapping[str, Any]], root: Path
) -> tuple[dict[str, Any], dict[int, str], dict[int, int]]:
    """(merged COCO ground truth, image family, image cluster) of the test records; clusters are scenario seeds."""
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    cache: dict[str, dict[int, list[dict[str, Any]]]] = {}
    family: dict[int, str] = {}
    cluster: dict[int, int] = {}
    for k, rec in enumerate(test_records(records), start=1):
        images.append(
            {
                "id": k,
                "file_name": rec["image"]["path"],
                "width": rec["image"]["width_px"],
                "height": rec["image"]["height_px"],
            }
        )
        path = rec["coco"]["path"]
        if path not in cache:
            doc = json.loads((Path(root) / path).read_text(encoding="utf-8"))
            by_image: dict[int, list[dict[str, Any]]] = {}
            for a in doc["annotations"]:
                by_image.setdefault(int(a["image_id"]), []).append(a)
            cache[path] = by_image
        for a in cache[path].get(int(rec["coco_image_id"]), []):
            annotations.append({**a, "id": len(annotations) + 1, "image_id": k})
        family[k] = rec["family"]
        cluster[k] = int(rec["scenario_seed"])
    categories = [{"id": cid, "name": name} for cid, name in CLASSES]
    return {"images": images, "annotations": annotations, "categories": categories}, family, cluster


def _load_rgb(root: Path, rec: Mapping[str, Any]) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(Path(root) / rec["image"]["path"]).convert("RGB"))


def predict_dfine(
    checkpoint: Path, records: Sequence[Mapping[str, Any]], root: Path, *, batch_size: int = 16, guard: Any = None
) -> list[dict[str, Any]]:
    """fp32 detections of a fine-tuned D-FINE checkpoint (a `{"model": state}` file of `train_dfine`) on `records`."""
    import torch

    from pitstudio_pipeline.perception.train_dfine import NUM_CLASSES, SIZE, letterbox

    blob = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
    state = blob["model"]
    name, n_classes = dfine.infer_variant(state)
    if n_classes != NUM_CLASSES:
        raise ValueError(f"the checkpoint has {n_classes} classes, expected {NUM_CLASSES}")
    cfg = dfine.make_config(name, num_classes=n_classes)
    cfg.model.load_state_dict(state)
    device = torch.device("cuda")
    model, post = cfg.model.deploy().to(device), cfg.postprocessor.deploy().to(device)
    detections: list[dict[str, Any]] = []
    recs = test_records(records)
    for start in range(0, len(recs), batch_size):
        if guard is not None:
            guard.check()
        chunk = recs[start : start + batch_size]
        tensors, metas = [], []
        for rec in chunk:
            image = _load_rgb(root, rec)
            h, w = image.shape[:2]
            canvas, _ = letterbox(image, np.zeros((0, 4)))
            scale = SIZE / max(h, w)
            metas.append((scale, (SIZE - round(h * scale)) // 2, (SIZE - round(w * scale)) // 2, w, h))
            tensors.append(torch.from_numpy(np.ascontiguousarray(canvas)).permute(2, 0, 1).float() / 255.0)
        x = torch.stack(tensors).to(device)
        sizes = torch.tensor([[SIZE, SIZE]] * len(chunk), device=device)
        with torch.no_grad():
            labels, boxes, scores = post(model(x), sizes)
        for j, (scale, top, left, w, h) in enumerate(metas):
            for lab, box, sc in zip(labels[j].tolist(), boxes[j].tolist(), scores[j].tolist(), strict=True):
                x0, y0 = max((box[0] - left) / scale, 0.0), max((box[1] - top) / scale, 0.0)
                x1, y1 = min((box[2] - left) / scale, float(w)), min((box[3] - top) / scale, float(h))
                if x1 - x0 <= 0.0 or y1 - y0 <= 0.0:
                    continue
                detections.append(
                    {
                        "image_id": start + j + 1,
                        "category_id": int(lab) + 1,
                        "bbox": [x0, y0, x1 - x0, y1 - y0],
                        "score": float(sc),
                    }
                )
    return detections


def predict_rfdetr(
    checkpoint: Path, records: Sequence[Mapping[str, Any]], root: Path, *, guard: Any = None
) -> list[dict[str, Any]]:
    """fp32 box and mask detections of a fine-tuned RF-DETR-Seg-N checkpoint (masks as RLE, counts as text)."""
    from PIL import Image
    from pycocotools import mask as mask_utils
    from rfdetr import RFDETRSegNano

    model = RFDETRSegNano(pretrain_weights=str(checkpoint), num_classes=5, trust_checkpoint=True)
    detections: list[dict[str, Any]] = []
    for k, rec in enumerate(test_records(records), start=1):
        if guard is not None:
            guard.check()
        found = model.predict(Image.open(Path(root) / rec["image"]["path"]).convert("RGB"), threshold=0.001)
        for i in range(len(found.xyxy)):
            cat = int(found.class_id[i])
            if cat not in range(1, 6):
                continue
            x0, y0, x1, y1 = (float(v) for v in found.xyxy[i])
            rle = mask_utils.encode(np.asfortranarray(found.mask[i].astype(np.uint8)))
            rle["counts"] = rle["counts"].decode("ascii")
            detections.append(
                {
                    "image_id": k,
                    "category_id": cat,
                    "bbox": [x0, y0, x1 - x0, y1 - y0],
                    "score": float(found.confidence[i]),
                    "segmentation": rle,
                }
            )
    return detections
