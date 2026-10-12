"""TSTR and TRTR arm configuration and batched augmentation (spec 012, FR-012-22, NFR-012-03).

The six arms (one TSTR, five TRTR folds) share every field except the data and epoch fields in ARM_SPECIFIC_KEYS, so a
budget change lands on all arms at once. Augmentation runs as batched tensor ops with per-sample factors drawn from a
seeded generator: the eight dihedral maps are applied per (flip, k) group, never per sample.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import torch

ARM_SPECIFIC_KEYS = frozenset(
    {"arm", "fold", "train_data", "validation_data", "steps_per_epoch", "checkpoint_every_steps"}
)
N_FOLDS = 5
MAX_SEGMENT_SECONDS = 8 * 3600  # NFR-012-03: a resume segment is at most 8 h
WARMUP_STEPS = 300
WEIGHT_DECAY = 1e-4
LEARNING_RATE = 3e-4
_RGB_TO_YIQ = torch.tensor([[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]])
_YIQ_TO_RGB = torch.linalg.inv(_RGB_TO_YIQ)
COLOUR_JITTER = {"brightness": 0.2, "contrast": 0.2, "saturation": 0.2, "hue": 0.02}


def build_arm_configs(*, steps: int, seed: int, batch_size: int, train_tiles: Mapping[str, int]) -> list[dict]:
    """Six configurations in the order tstr, trtr-0 .. trtr-4; train_tiles holds the training tiles of each arm."""
    if steps <= 0 or batch_size <= 0:
        raise ValueError(f"steps and batch_size must be positive, got {steps} and {batch_size}")
    arms = [("tstr", None), *(("trtr", f) for f in range(N_FOLDS))]
    shared = {
        "architecture": "Unet",
        "encoder": "resnet18.a1_in1k",
        "classes": 3,
        "optimizer": "AdamW",
        "learning_rate": LEARNING_RATE,
        "weight_decay": WEIGHT_DECAY,
        "lr_schedule": {"kind": "linear-warmup-cosine", "warmup_steps": WARMUP_STEPS},
        "steps": steps,
        "batch_size": batch_size,
        "augmentation": {"dihedral_maps": 8, "colour_jitter": dict(COLOUR_JITTER)},
        "seed": seed,
        "max_segment_seconds": MAX_SEGMENT_SECONDS,
    }
    configs = []
    for arm, fold in arms:
        key = "tstr" if arm == "tstr" else f"trtr-{fold}"
        steps_per_epoch = math.ceil(train_tiles[key] / batch_size)
        data = "synthetic" if arm == "tstr" else f"real/fold-{fold}"
        configs.append(
            {
                **shared,
                "arm": arm,
                "fold": fold,
                "train_data": f"{data}/train",
                "validation_data": f"{data}/validation",
                "steps_per_epoch": steps_per_epoch,
                "checkpoint_every_steps": steps_per_epoch,  # one checkpoint per epoch
            }
        )
    return configs


def lr_factor(step: int, steps: int, warmup: int = WARMUP_STEPS) -> float:
    """Linear warm-up then cosine decay to 0, as a multiplier of the base learning rate."""
    if step < warmup:
        return (step + 1) / warmup
    return 0.5 * (1.0 + math.cos(math.pi * (step - warmup) / max(1, steps - warmup)))


def dihedral_batch(tensors: list[torch.Tensor], flips: torch.Tensor, ks: torch.Tensor) -> list[torch.Tensor]:
    """Apply the dihedral map (horizontal flip if flips[i], then ks[i] quarter turns) to sample i of every
    [N, ..., H, W] tensor. Samples sharing one (flip, k) are transformed in a single call."""
    outs = [t.clone() for t in tensors]
    for flip in (0, 1):
        for k in range(4):
            idx = ((flips == flip) & (ks == k)).nonzero(as_tuple=True)[0]
            if idx.numel() == 0 or (flip == 0 and k == 0):
                continue
            for out, src in zip(outs, tensors, strict=True):
                part = src[idx]
                if flip:
                    part = part.flip(-1)
                if k:
                    part = torch.rot90(part, k, (-2, -1))
                out[idx] = part
    return outs


def colour_jitter_batch(
    x: torch.Tensor, factors: torch.Tensor, jitter: Mapping[str, float] = COLOUR_JITTER
) -> torch.Tensor:
    """Batched colour jitter on float RGB in [0, 1], x [N, 3, H, W], factors [N, 4] in [-1, 1].

    Brightness and contrast scale per sample, saturation blends with luma, hue rotates the YIQ chroma plane.
    """
    b, c, s, h = (factors[:, i].view(-1, 1, 1, 1) for i in range(4))
    x = x * (1.0 + jitter["brightness"] * b)
    mean = x.mean(dim=(1, 2, 3), keepdim=True)
    x = (x - mean) * (1.0 + jitter["contrast"] * c) + mean
    r, g, bl = x[:, 0:1], x[:, 1:2], x[:, 2:3]
    luma = 0.299 * r + 0.587 * g + 0.114 * bl
    x = (x - luma) * (1.0 + jitter["saturation"] * s) + luma
    # hue: rotate (I, Q) by theta = 2 pi * hue shift; the inverse matrix is exact, so a zero shift is the identity
    theta = 2.0 * math.pi * jitter["hue"] * h
    yiq = torch.einsum("ij,njhw->nihw", _RGB_TO_YIQ.to(x), x)
    i2 = yiq[:, 1:2] * torch.cos(theta) - yiq[:, 2:3] * torch.sin(theta)
    q2 = yiq[:, 1:2] * torch.sin(theta) + yiq[:, 2:3] * torch.cos(theta)
    rgb = torch.einsum("ij,njhw->nihw", _YIQ_TO_RGB.to(x), torch.cat([yiq[:, 0:1], i2, q2], dim=1))
    return rgb.clamp(0.0, 1.0)


def augment_batch(
    x: torch.Tensor, target: torch.Tensor, weight: torch.Tensor, generator: torch.Generator
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """FR-012-22 augmentation: 8 dihedral maps (images, targets, weights) and colour jitter (images only).

    x is float RGB in [0, 1], [N, 3, H, W]; every draw comes from `generator`, so a seeded run is reproducible.
    """
    n = x.shape[0]
    ks = torch.randint(0, 4, (n,), generator=generator)
    flips = torch.randint(0, 2, (n,), generator=generator)
    factors = torch.rand((n, 4), generator=generator) * 2.0 - 1.0
    ks, flips, factors = ks.to(x.device), flips.to(x.device), factors.to(x.device)
    x, target, weight = dihedral_batch([x, target, weight], flips, ks)
    return colour_jitter_batch(x, factors), target, weight
