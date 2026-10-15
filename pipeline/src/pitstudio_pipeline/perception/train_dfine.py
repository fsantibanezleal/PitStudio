"""Fine-tuning of D-FINE-N and D-FINE-S on the synthetic training split (FR-009-18, FR-009-20, FR-009-21).

The model, the criterion and the optimiser groups are the upstream ones (see `dfine`); the loop is `train_loop`:
per-epoch
checkpoints, the out-of-memory ladder and the closed-form cosine learning rate. bf16 autocast covers the model
forward, the
criterion runs in float32 as upstream does, no FP8. Labels are the COCO category ids minus one (0..4); boxes are
letterboxed to 640 x 640 and given to the criterion as normalised cx, cy, w, h.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_pipeline.perception import dfine
from pitstudio_pipeline.perception.train_loop import LoopConfig, MicroBatch, run_training_loop

SIZE = dfine.INPUT_SIZE
NUM_CLASSES = 5
MAX_NORM = 0.1  # upstream clip_max_norm


def letterbox(image: np.ndarray, boxes_xywh: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Resize to SIZE x SIZE keeping the aspect ratio (grey 114 padding); boxes follow in pixels of the new image."""
    from PIL import Image

    h, w = image.shape[:2]
    scale = SIZE / max(h, w)
    nh, nw = round(h * scale), round(w * scale)
    canvas = np.full((SIZE, SIZE, 3), 114, dtype=np.uint8)
    top, left = (SIZE - nh) // 2, (SIZE - nw) // 2
    canvas[top : top + nh, left : left + nw] = np.asarray(Image.fromarray(image).resize((nw, nh), Image.BILINEAR))
    out = boxes_xywh.astype(np.float64) * scale
    out[:, 0] += left
    out[:, 1] += top
    return canvas, out


class RecordDataset:
    """Training records as (image tensor, upstream target) pairs; the COCO file of a record holds its annotations."""

    def __init__(self, records: Sequence[Mapping[str, Any]], root: Path, seed: int) -> None:
        self.records, self.root, self.seed = list(records), Path(root), seed
        self._coco: dict[str, dict[int, list[dict[str, Any]]]] = {}

    def _annotations(self, record: Mapping[str, Any]) -> list[dict[str, Any]]:
        path = record["coco"]["path"]
        if path not in self._coco:
            doc = json.loads((self.root / path).read_text(encoding="utf-8"))
            by_image: dict[int, list[dict[str, Any]]] = {}
            for a in doc["annotations"]:
                by_image.setdefault(int(a["image_id"]), []).append(a)
            self._coco[path] = by_image
        return self._coco[path].get(int(record["coco_image_id"]), [])

    def __len__(self) -> int:
        return len(self.records)

    def get(self, index: int, epoch: int) -> tuple[Any, dict[str, Any]]:
        import torch
        from PIL import Image

        record = self.records[index]
        image = np.asarray(Image.open(self.root / record["image"]["path"]).convert("RGB"))
        anns = self._annotations(record)
        boxes = np.array([a["bbox"] for a in anns], dtype=np.float64).reshape(-1, 4)
        labels = np.array([int(a["category_id"]) - 1 for a in anns], dtype=np.int64)
        canvas, boxes = letterbox(image, boxes)
        if np.random.default_rng([self.seed, epoch, index]).random() < 0.5:  # horizontal flip, seeded per sample
            canvas = canvas[:, ::-1]
            boxes[:, 0] = SIZE - boxes[:, 0] - boxes[:, 2]
        cxcywh = (
            np.stack([boxes[:, 0] + boxes[:, 2] / 2, boxes[:, 1] + boxes[:, 3] / 2, boxes[:, 2], boxes[:, 3]], axis=1)
            / SIZE
        )
        tensor = torch.from_numpy(np.ascontiguousarray(canvas)).permute(2, 0, 1).float() / 255.0
        return tensor, {"boxes": torch.from_numpy(cxcywh).float(), "labels": torch.from_numpy(labels)}


class _Store:
    """Per-epoch checkpoint file; `save` writes the weights and the loop state atomically."""

    def __init__(self, out_dir: Path, get_state: Callable[[], dict[str, Any]]) -> None:
        self.out_dir, self.get_state = out_dir, get_state
        self.last: Path | None = None

    def _state_path(self) -> Path:
        return self.out_dir / "loop_state.json"

    def load(self) -> dict[str, Any] | None:
        p = self._state_path()
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def save(self, state: dict[str, Any]) -> None:
        import torch

        epoch = int(state["epochs_done"])
        ckpt = self.out_dir / f"checkpoint_epoch{epoch:03d}.pth"
        tmp = ckpt.with_suffix(".tmp")
        torch.save({"model": self.get_state(), "loop": state}, tmp)
        tmp.replace(ckpt)
        sp = self._state_path()
        sp.with_suffix(".tmp").write_text(json.dumps({**state, "checkpoint": ckpt.name}), encoding="utf-8")
        sp.with_suffix(".tmp").replace(sp)
        self.last = ckpt


def train_dfine(
    *,
    model_name: str,
    base_checkpoint: Path,
    records: Sequence[Mapping[str, Any]],
    root: Path,
    out_dir: Path,
    epochs: int,
    seed: int,
    batch_size: int = 16,
    max_steps: int | None = None,
    guard: Any = None,
) -> tuple[Path, list[float]]:
    """Fine-tune and return the last checkpoint path and the loss of every optimiser step (needs CUDA)."""
    import torch

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = dfine.make_config(model_name, num_classes=NUM_CLASSES)
    model, criterion = cfg.model, cfg.criterion
    loaded, skipped = dfine.load_matched(model, dfine.read_state(base_checkpoint))
    (out / "load_report.json").write_text(json.dumps({"loaded": loaded, "re_initialised": skipped}), encoding="utf-8")
    device = torch.device("cuda")
    model.to(device).train()
    criterion.to(device).train()
    optimiser = cfg.optimizer
    base_lrs = [g["lr"] for g in optimiser.param_groups]
    top_lr = float(cfg.yaml_cfg["optimizer"]["lr"])
    data = RecordDataset(records, Path(root), seed)
    n = len(data)
    n_use = (n // batch_size) * batch_size
    if n_use == 0:
        raise ValueError(f"{n} training records are fewer than one batch of {batch_size}")
    loop_cfg = LoopConfig(
        n_samples=n_use, epochs=epochs, batch_size=batch_size, accum_steps=1, seed=seed, base_lr=top_lr
    )
    losses: list[float] = []
    pending: list[Any] = []
    steps = {"done": 0}
    store = _Store(out, lambda: {k: v.detach().cpu() for k, v in model.state_dict().items()})

    def restore(state: dict[str, Any] | None) -> None:
        if state is None:
            return
        blob = torch.load(str(out / state["checkpoint"]), map_location="cpu", weights_only=False)
        model.load_state_dict(blob["model"])
        optimiser.zero_grad()
        pending.clear()

    def step_fn(mb: MicroBatch) -> None:
        if guard is not None:
            guard.check()
        samples = [data.get(i, mb.epoch) for i in mb.sample_indices]
        x = torch.stack([s[0] for s in samples]).to(device)
        targets = [{k: v.to(device) for k, v in s[1].items()} for s in samples]
        for g, base in zip(optimiser.param_groups, base_lrs, strict=True):
            g["lr"] = base * mb.lr / top_lr
        metas = {
            "epoch": mb.epoch,
            "step": mb.optimiser_step,
            "global_step": mb.optimiser_step,
            "epoch_step": loop_cfg.steps_per_epoch,
        }
        loss_dict = forward_loss(model, criterion, x, targets, metas, "cuda")
        loss = sum(loss_dict.values()) / mb.accum_steps
        loss.backward()
        pending.append(float(loss.detach()) * mb.accum_steps)
        if mb.micro_index == mb.accum_steps - 1:
            torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_NORM)
            optimiser.step()
            optimiser.zero_grad()
            value = sum(pending) / len(pending)
            if not math.isfinite(value):
                raise FloatingPointError(f"non-finite loss {value} at optimiser step {mb.optimiser_step}")
            losses.append(value)
            pending.clear()
            steps["done"] += 1
            if max_steps is not None and steps["done"] >= max_steps:
                raise _StopAfterSteps

    try:
        run_training_loop(loop_cfg, step_fn, store, restore=restore)
    except _StopAfterSteps:
        store.save(
            {
                "epochs_done": 0,
                "optimiser_step": steps["done"],
                "batch_size": batch_size,
                "accum_steps": 1,
                "seed": seed,
            }
        )
    if store.last is None:
        raise RuntimeError("no checkpoint was written")
    return store.last, losses


def forward_loss(
    model: Any, criterion: Any, x: Any, targets: list[dict[str, Any]], metas: dict[str, int], device_type: str
) -> Any:
    """Loss terms of one micro-batch: bf16 autocast for the model forward, float32 for the criterion (as upstream)."""
    import torch

    with torch.autocast(device_type=device_type, dtype=torch.bfloat16):
        outputs = model(x, targets=targets)
    with torch.autocast(device_type=device_type, enabled=False):
        return criterion(outputs, targets, **metas)


def smoke_step(
    model_name: str,
    base_checkpoint: Path,
    records: Sequence[Mapping[str, Any]],
    root: Path,
    seed: int,
    device: str = "cpu",
) -> float:
    """One real optimiser step on `device` over the first records (the dry-run of the training path); the loss."""
    import torch

    cfg = dfine.make_config(model_name, num_classes=NUM_CLASSES)
    model, criterion = cfg.model, cfg.criterion
    dfine.load_matched(model, dfine.read_state(base_checkpoint))
    model.to(device).train()
    criterion.to(device).train()
    optimiser = cfg.optimizer
    data = RecordDataset(records, Path(root), seed)
    items = [data.get(i, 0) for i in range(min(2, len(data)))]
    x = torch.stack([i[0] for i in items]).to(device)
    targets = [{k: v.to(device) for k, v in i[1].items()} for i in items]
    loss_dict = forward_loss(
        model, criterion, x, targets, {"epoch": 0, "step": 0, "global_step": 0, "epoch_step": 1}, device
    )
    loss = sum(loss_dict.values())
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_NORM)
    optimiser.step()
    value = float(loss.detach())
    if not math.isfinite(value):
        raise FloatingPointError(f"non-finite loss {value} in the smoke step")
    return value


class _StopAfterSteps(Exception):
    """Smoke runs stop after `max_steps` optimiser steps."""
