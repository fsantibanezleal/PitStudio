"""Fine-tuning of RF-DETR-Seg-N on the pit-family training split with the `rfdetr` 1.11.1 trainer (FR-009-18,
FR-009-20).

The upstream trainer owns its loop and writes one checkpoint per epoch (`checkpoint_interval=1`); this module builds
its COCO
dataset folder from the index records, runs it with bf16 autocast and the upstream default loss coefficients (never
overridden)
and applies the out-of-memory ladder of FR-009-20 around it: batch halved, accumulation doubled, restart from the last
checkpoint, `oom-exhausted` below a batch of 1.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pitstudio_pipeline.perception.train_loop import TrainLoopError, is_cuda_oom

CLASS_NAMES = ["haul_truck", "shovel", "light_vehicle", "person", "boulder"]


def build_dataset(records: Sequence[Mapping[str, Any]], root: Path, out: Path) -> Path:
    """A COCO folder (`train/` with `_annotations.coco.json`, and a one-image `valid/`) from the training records."""
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    cache: dict[str, dict[int, list[dict[str, Any]]]] = {}
    train = out / "train"
    train.mkdir(parents=True, exist_ok=True)
    for k, rec in enumerate(records, start=1):
        src = Path(root) / rec["image"]["path"]
        name = f"{k:06d}.png"
        try:
            os.link(src, train / name)
        except OSError:
            shutil.copyfile(src, train / name)
        images.append(
            {"id": k, "file_name": name, "width": rec["image"]["width_px"], "height": rec["image"]["height_px"]}
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
    categories = [{"id": i + 1, "name": n} for i, n in enumerate(CLASS_NAMES)]
    doc = {"images": images, "annotations": annotations, "categories": categories}
    (train / "_annotations.coco.json").write_text(json.dumps(doc), encoding="utf-8")
    valid = out / "valid"
    valid.mkdir(exist_ok=True)
    first = images[0]
    shutil.copyfile(train / first["file_name"], valid / first["file_name"])
    keep = [a for a in annotations if a["image_id"] == first["id"]]
    (valid / "_annotations.coco.json").write_text(
        json.dumps({"images": [first], "annotations": keep, "categories": categories}), encoding="utf-8"
    )
    return out


def train_rfdetr(
    *,
    base_checkpoint: Path,
    records: Sequence[Mapping[str, Any]],
    root: Path,
    out_dir: Path,
    epochs: int,
    seed: int,
    batch_size: int = 8,
    effective_batch: int = 16,
) -> Path:
    """Fine-tune RF-DETR-Seg-N and return the path of its last checkpoint (needs CUDA)."""
    from rfdetr import RFDETRSegNano

    out = Path(out_dir)
    dataset = build_dataset(records, Path(root), out / "dataset")
    attempts: list[tuple[int, int]] = []
    accum = max(1, effective_batch // batch_size)
    while True:
        attempts.append((batch_size, accum))
        resume = sorted(out.glob("checkpoint*.pth"))
        try:
            model = RFDETRSegNano(
                pretrain_weights=str(base_checkpoint), num_classes=len(CLASS_NAMES), trust_checkpoint=True
            )
            model.train(
                dataset_dir=str(dataset),
                epochs=epochs,
                batch_size=batch_size,
                grad_accum_steps=accum,
                output_dir=str(out),
                checkpoint_interval=1,
                amp_dtype="bfloat16",
                seed=seed,
                resume=str(resume[-1]) if resume else None,
            )
            break
        except Exception as exc:
            if not is_cuda_oom(exc):
                raise
            if batch_size < 2 or batch_size % 2:
                raise TrainLoopError("oom-exhausted", f"out of memory at batch {batch_size}", attempts) from exc
            batch_size, accum = batch_size // 2, accum * 2
    checkpoints = sorted(out.glob("checkpoint*.pth"))
    if not checkpoints:
        raise RuntimeError("rfdetr wrote no checkpoint")
    return checkpoints[-1]
