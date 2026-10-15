"""Layer-1 parity comparator (FR-016-04, FR-016-39): fail closed, numpy only."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ComparisonResult:
    verdict: str
    reason: str | None
    max_abs_error: float | None = None
    mismatch_fraction: float | None = None
    argmax_rows: int | None = None
    argmax_rows_small_gap: int | None = None
    argmax_agreement: float | None = None


def _kind(a: np.ndarray) -> str:
    if a.dtype.kind in "fc":
        return "float"
    if a.dtype.kind in "iu":
        return "int"
    return a.dtype.kind


def _fail(reason: str, **kw: float | int | None) -> ComparisonResult:
    return ComparisonResult("fail", reason, **kw)  # type: ignore[arg-type]


def compare(
    reference: Sequence[np.ndarray],
    candidate: Sequence[np.ndarray],
    *,
    rtol: float = 1e-3,
    atol: float = 1e-5,
    max_abs: float = 1e-4,
    class_scores: Sequence[int] = (),
    argmax_gap: float = 2e-4,
) -> ComparisonResult:
    """Compare candidate outputs with the reference outputs; never raises, returns `fail` with the reason."""
    if len(reference) != len(candidate):
        return _fail(f"output count differs: reference {len(reference)}, candidate {len(candidate)}")
    refs = [np.asarray(r) for r in reference]
    cands = [np.asarray(c) for c in candidate]
    for i, (r, c) in enumerate(zip(refs, cands, strict=True)):
        if r.shape != c.shape:
            return _fail(f"output {i}: shape differs: reference {r.shape}, candidate {c.shape}")
        if _kind(r) != _kind(c):
            return _fail(f"output {i}: dtype class differs: reference {r.dtype}, candidate {c.dtype}")
        if r.dtype.kind in "fc":
            bad = np.isfinite(r) & ~np.isfinite(c)
            if bad.any():
                return _fail(f"output {i}: non-finite candidate value where the reference is finite")

    max_err = 0.0
    total = 0
    mismatched = 0
    for r, c in zip(refs, cands, strict=True):
        if r.size == 0:
            continue
        rf = r.astype(np.float64)
        cf = c.astype(np.float64)
        both = np.isfinite(rf) & np.isfinite(cf)
        diff = np.where(both, np.abs(cf - rf), 0.0)
        max_err = max(max_err, float(diff.max()))
        bound = atol + rtol * np.abs(np.where(np.isfinite(rf), rf, 0.0))
        viol = both & (diff > bound)
        # a non-finite reference must be reproduced exactly (same non-finite value or NaN position)
        viol |= ~np.isfinite(rf) & ~((rf == cf) | (np.isnan(rf) & np.isnan(cf)))
        mismatched += int(viol.sum())
        total += r.size
    fraction = mismatched / total if total else 0.0

    rows = small = agree_rows = checked = 0
    for idx in class_scores:
        r = refs[idx].astype(np.float64)
        c = cands[idx].astype(np.float64)
        r2 = r.reshape(-1, r.shape[-1])
        c2 = c.reshape(-1, c.shape[-1])
        rows += r2.shape[0]
        if r2.shape[-1] < 2:
            continue
        top2 = np.sort(r2, axis=-1)[:, -2:]
        gap = top2[:, 1] - top2[:, 0]
        large = gap > argmax_gap
        small += int((~large).sum())
        checked += int(large.sum())
        agree_rows += int((large & (np.argmax(r2, axis=-1) == np.argmax(c2, axis=-1))).sum())
    agreement = agree_rows / checked if checked else 1.0

    common = {
        "max_abs_error": max_err,
        "mismatch_fraction": fraction,
        "argmax_rows": rows,
        "argmax_rows_small_gap": small,
        "argmax_agreement": agreement,
    }
    if mismatched:
        return _fail(f"{mismatched} element(s) outside the tolerance atol + rtol |y|", **common)
    if not (max_err <= max_abs) or math.isnan(max_err):
        return _fail(f"max_abs error {max_err:.3g} exceeds {max_abs:.3g}", **common)
    if agreement != 1.0:
        return _fail(f"argmax agreement {agreement:.4f} below 1.0 on rows with a top-2 gap above {argmax_gap}", **common)
    return ComparisonResult("pass", None, **common)
