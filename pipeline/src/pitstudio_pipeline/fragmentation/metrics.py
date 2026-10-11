"""Fragmentation metrics (spec 012): foreground IoU, per-fold TSTR/TRTR ratios, relative x50 error.

FR-012-29, FR-012-30, FR-012-45, P-012-06.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def _check_mask(name: str, mask: np.ndarray) -> np.ndarray:
    mask = np.asarray(mask)
    if mask.dtype != np.bool_:
        raise ValueError(f"{name} must be a boolean mask, got dtype {mask.dtype}")
    return mask


def foreground_iou(pred: np.ndarray, truth: np.ndarray) -> float:
    """FR-012-29: |pred & truth| / |pred | truth| over two boolean masks of one shape; 1.0 when both are empty."""
    pred = _check_mask("pred", pred)
    truth = _check_mask("truth", truth)
    if pred.shape != truth.shape:
        raise ValueError(f"pred and truth must have the same shape, got {pred.shape} and {truth.shape} (truth vs pred)")
    union = int(np.count_nonzero(pred | truth))
    if union == 0:
        return 1.0
    return int(np.count_nonzero(pred & truth)) / union


def fold_score(preds: Sequence[np.ndarray], truths: Sequence[np.ndarray]) -> float:
    """Mean foreground IoU over the test originals of one fold."""
    if len(preds) != len(truths) or len(preds) == 0:
        raise ValueError(
            f"pred and truth must be non-empty sequences of equal length, got {len(preds)} and {len(truths)}"
        )
    return float(np.mean([foreground_iou(p, t) for p, t in zip(preds, truths, strict=True)]))


def tstr_trtr_ratios(iou_tstr: Sequence[float], iou_trtr: Sequence[float]) -> dict:
    """FR-012-30: rho_f = IoU_TSTR(f) / IoU_TRTR(f) per fold, with the mean, the minimum and the population std."""
    tstr = np.asarray(iou_tstr, dtype=np.float64)
    trtr = np.asarray(iou_trtr, dtype=np.float64)
    if tstr.shape != trtr.shape or tstr.ndim != 1 or tstr.size == 0:
        raise ValueError(f"iou_tstr and iou_trtr must be 1-D of equal length, got {tstr.shape} and {trtr.shape}")
    if not np.isfinite(tstr).all():
        raise ValueError("iou_tstr must be finite")
    if not np.isfinite(trtr).all() or (trtr <= 0).any():
        raise ValueError("iou_trtr must be finite and > 0 (the ratio is undefined for IoU_TRTR = 0)")
    rho = tstr / trtr
    return {"rho": rho.tolist(), "mean": float(rho.mean()), "min": float(rho.min()), "std": float(rho.std())}


def relative_x50_error(x50_hat: float, x50_ref: float) -> float:
    """|x50_hat - x50_ref| / x50_ref; x50_ref must be finite and > 0 (FR-012-45)."""
    if not math.isfinite(x50_ref) or x50_ref <= 0:
        raise ValueError(f"x50_ref must be finite and > 0, got {x50_ref}")
    return abs(x50_hat - x50_ref) / x50_ref
