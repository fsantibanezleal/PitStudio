# SPDX-License-Identifier: Apache-2.0
"""Statistical re-run check of a sensor stage (FR-013-34): point count, Chamfer distance, image PSNR.

The renderer is not bit-reproducible, so a re-run is compared by statistics, never by hash: the valid-point count of
every lidar frame differs by at most 1 %, every cloud is within 3 range accuracies in symmetric mean Chamfer
distance, and every image has a PSNR of at least 40 dB. NumPy only; the thresholds default to the `sensors`
section of `specs/000-foundation/thresholds.yaml`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

_THRESHOLDS = Path(__file__).resolve().parents[4] / "specs" / "000-foundation" / "thresholds.yaml"
_KEYS = ("rerun_point_count_rel_max", "rerun_chamfer_over_range_accuracy_max", "rerun_psnr_db_min")
_CHUNK = 512
_WINDOW = 32


def default_thresholds() -> dict[str, float]:
    """The three re-run thresholds read from `specs/000-foundation/thresholds.yaml` (section `sensors`)."""
    import yaml

    doc = yaml.safe_load(_THRESHOLDS.read_text(encoding="utf-8"))["sensors"]
    return {k: float(doc[k]) for k in _KEYS}


def _cloud(points: Any, name: str) -> np.ndarray:
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError(f"{name} must have shape (n, 3), got {arr.shape}")
    if arr.shape[0] == 0:
        raise ValueError(f"{name} holds no point")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} holds a non-finite coordinate")
    return arr


def _one_way(a: np.ndarray, b: np.ndarray) -> float:
    """Mean over `a` of the distance to the nearest point of `b`: exact, by a sorted-x window search.

    `b` is sorted by x. For a chunk of queries (also sorted by x) a first bound comes from the 2 * `_WINDOW` nearest
    neighbours in x order; the exact nearest neighbours then lie within that bound in x, so only that slice of `b` is
    searched by brute force.
    """
    b = b[np.argsort(b[:, 0], kind="stable")]
    a = a[np.argsort(a[:, 0], kind="stable")]
    total = 0.0
    for start in range(0, len(a), _CHUNK):
        q = a[start : start + _CHUNK]
        pos = np.searchsorted(b[:, 0], q[:, 0])
        offsets = np.arange(-_WINDOW, _WINDOW)
        idx = np.clip(pos[:, None] + offsets[None, :], 0, len(b) - 1)
        bound = np.linalg.norm(b[idx] - q[:, None, :], axis=2).min(axis=1)
        reach = float(bound.max())
        lo = int(np.searchsorted(b[:, 0], q[0, 0] - reach, side="left"))
        hi = int(np.searchsorted(b[:, 0], q[-1, 0] + reach, side="right"))
        cand = b[lo:hi]
        d2 = ((q[:, None, :] - cand[None, :, :]) ** 2).sum(axis=2)
        total += float(np.sqrt(d2.min(axis=1)).sum())
    return total / len(a)


def chamfer(a: Any, b: Any) -> float:
    """Symmetric mean Chamfer distance: 0.5 * (mean nearest-neighbour distance a to b + b to a). Empty input raises."""
    pa, pb = _cloud(a, "a"), _cloud(b, "b")
    return 0.5 * (_one_way(pa, pb) + _one_way(pb, pa))


def psnr_db(a: Any, b: Any, peak: float = 255.0) -> float:
    """PSNR (dB) of two equal-shape arrays: 10 log10(peak^2 / MSE); `math.inf` when they are identical."""
    x, y = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError(f"image shapes differ: {x.shape} and {y.shape}")
    mse = float(np.mean((x - y) ** 2))
    return math.inf if mse == 0.0 else 10.0 * math.log10(peak * peak / mse)


def _fail(measure: str, index: int, value: float) -> dict[str, Any]:
    return {
        "class": "statistical",
        "rerun_check": "fail",
        "failing": {"measure": measure, "index": index, "value": value},
    }


def rerun_check(
    original: Mapping[str, Any],
    rerun: Mapping[str, Any],
    *,
    range_accuracy_m: float,
    thresholds: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Compare a re-run with the original, frames and images pairwise in order; see the module docstring.

    `original` and `rerun` hold `lidar` (per-frame dicts with `points`, the (n, 3) valid returns) and `images` (uint8
    arrays). Returns `{"class": "statistical", "rerun_check": "pass" | "fail", "failing": None | {...}}`.
    """
    if not (isinstance(range_accuracy_m, (int, float)) and math.isfinite(range_accuracy_m) and range_accuracy_m > 0):
        raise ValueError(f"range_accuracy_m must be finite and positive, got {range_accuracy_m!r}")
    limits = {**default_thresholds(), **(dict(thresholds) if thresholds else {})}
    frames_a, frames_b = _seq(original, "lidar"), _seq(rerun, "lidar")
    images_a, images_b = _seq(original, "images"), _seq(rerun, "images")
    if len(frames_a) != len(frames_b) or len(images_a) != len(images_b):
        raise ValueError("the original and the re-run hold different numbers of frames or images")
    for i, (fa, fb) in enumerate(zip(frames_a, frames_b, strict=True)):
        pa, pb = _cloud(fa["points"], f"original frame {i}"), _cloud(fb["points"], f"re-run frame {i}")
        rel = abs(len(pb) - len(pa)) / len(pa)
        if rel > limits["rerun_point_count_rel_max"]:
            return _fail("point_count", i, rel)
        dist = chamfer(pa, pb)
        if dist > limits["rerun_chamfer_over_range_accuracy_max"] * range_accuracy_m:
            return _fail("chamfer", i, dist)
    for i, (ia, ib) in enumerate(zip(images_a, images_b, strict=True)):
        value = psnr_db(ia, ib)
        if value < limits["rerun_psnr_db_min"]:
            return _fail("psnr", i, value)
    return {"class": "statistical", "rerun_check": "pass", "failing": None}


def _seq(side: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = side.get(key, [])
    if not isinstance(value, Sequence):
        raise ValueError(f"{key} must be a list")
    return value
