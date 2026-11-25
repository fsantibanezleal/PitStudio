"""Image-quality measures and the gate of the `st55_sdg` exposure calibration (FR-009-02, FR-009-05, FR-009-08).

Pure NumPy, no Isaac Sim: the GPU probes, the gate run and the unit tests share these functions, so a number in a report
is the number the tests check. Definitions (brief sdg-exposure-2026-11-22):

- flat frame: rgb standard deviation below 1.0 over all pixels and channels of the 8-bit image;
- clipped pixel: Rec. 709 luminance of the 8-bit sRGB values at or below 2 or at or above 253;
- haze-limited frame: transmittance exp(-sigma * d_med) below 0.1, sigma the row's dust extinction (1/m), d_med the
  median finite depth of the frame (m); such a frame is physics (FR-009-05), kept and counted apart;
- history independence: the same row after two different predecessor rows gives a mean luminance within 2.0 levels and
  an rgb std within 2.0.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

REC709 = (0.2126, 0.7152, 0.0722)
CLIP_LOW, CLIP_HIGH = 2.0, 253.0
HAZE_TRANSMITTANCE = 0.1
FLAT_STD = 1.0
HISTORY_TOLERANCE = 2.0
GATE = {
    "clipped_frame_fraction": 0.25,  # a frame is "clipped" above this share of clipped pixels
    "clipped_frames_share": 0.05,  # at most this share of frames may be clipped
    "rgb_std_median": 25.0,
    "rgb_std_p10": 10.0,
    "annotated_share": 0.78,
}


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec. 709 luminance of an (H, W, 3) 8-bit image, as float on the 0 to 255 scale."""
    arr = np.asarray(rgb, dtype=np.float64)[..., :3]
    return arr @ np.asarray(REC709)


def clipped_fraction(rgb: np.ndarray) -> float:
    """Share of pixels whose luminance is at or below 2 or at or above 253."""
    lum = luminance(rgb)
    return float(((lum <= CLIP_LOW) | (lum >= CLIP_HIGH)).mean())


def transmittance(sigma_per_km: float, distance_m: float) -> float:
    """Beer-Lambert transmittance exp(-sigma * d) of an extinction in 1/km over a distance in m."""
    return math.exp(-float(sigma_per_km) / 1000.0 * float(distance_m))


def haze_limited(sigma_per_km: float, median_depth_m: float) -> bool:
    """True when the transmittance at the frame's median depth is below 0.1 (False for a NaN depth)."""
    if math.isnan(median_depth_m):
        return False
    return transmittance(sigma_per_km, median_depth_m) < HAZE_TRANSMITTANCE


def median_finite_depth(depth: np.ndarray) -> float:
    """Median of the finite depth pixels (m); NaN when none is finite."""
    finite = np.asarray(depth, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    return float(np.median(finite)) if finite.size else float("nan")


def transmittance_from_colours(rendered: Sequence[float], fog: Sequence[float], clear: Sequence[float]) -> float:
    """Transmittance t of the blend `rendered = t * clear + (1 - t) * fog` (least squares over the colour channels)."""
    r, f, c = (np.asarray(v, dtype=np.float64) for v in (rendered, fog, clear))
    span = c - f
    denom = float(span @ span)
    if denom < 1e-9:
        raise ValueError("the fog colour and the unfogged colour differ by nothing: the transmittance is undefined")
    return float((r - f) @ span / denom)


def stratified_indices(values: Sequence[float], n: int) -> list[int]:
    """Indices (into `values`) of the `n` values at the midpoint quantiles (i + 0.5) / n of the sorted values."""
    if n > len(values):
        raise ValueError(f"cannot take {n} samples from only {len(values)} values")
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    return [order[int((k + 0.5) / n * len(values))] for k in range(n)]


def stratified_sample(rows: Sequence[Mapping[str, Any]], key_a: str, key_b: str, n_bins: int, per_bin: int) -> list:
    """Rows spread over two `dr` parameters: `n_bins` equal-count bins of `key_a`, in each `per_bin` rows at the
    midpoint quantiles of `key_b` (quantile-stratified, no repeats, deterministic)."""
    by_a = sorted(rows, key=lambda r: (r["dr"][key_a], r["record_id"]))
    chosen: list[Mapping[str, Any]] = []
    for b in range(n_bins):
        lo, hi = b * len(by_a) // n_bins, (b + 1) * len(by_a) // n_bins
        part = by_a[lo:hi]
        picks = stratified_indices([r["dr"][key_b] for r in part], per_bin)
        chosen.extend(part[i] for i in picks)
    return chosen


def history_independent(means: Sequence[float], stds: Sequence[float]) -> bool:
    """True when a row rendered after different predecessors keeps its mean luminance and rgb std within 2.0."""
    return (max(means) - min(means)) <= HISTORY_TOLERANCE and (max(stds) - min(stds)) <= HISTORY_TOLERANCE


def _check(value: float, limit: float, passed: bool) -> dict[str, Any]:
    return {"value": value, "limit": limit, "passed": bool(passed)}


def evaluate_gate(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Every gate threshold on a list of frame measures (`rgb_std`, `clipped_fraction`, `annotations`, `haze_limited`).

    Haze-limited frames are excluded only where the physics explains the number (flat frames, the rgb std quantiles);
    the clipped and annotated shares are judged on every frame, and the haze-limited ones are counted apart.
    """
    n = len(frames)
    clear = [f for f in frames if not f["haze_limited"]]
    stds = np.asarray([f["rgb_std"] for f in clear], dtype=np.float64)
    flat = sum(1 for f in clear if f["rgb_std"] < FLAT_STD)
    clipped = sum(1 for f in frames if f["clipped_fraction"] > GATE["clipped_frame_fraction"])
    annotated = sum(1 for f in frames if int(f["annotations"]) > 0)
    median = float(np.median(stds)) if stds.size else 0.0
    p10 = float(np.quantile(stds, 0.1)) if stds.size else 0.0
    thresholds = {
        "flat_not_haze": _check(flat, 0, flat == 0),
        "clipped_over_25pct": _check(
            clipped / n, GATE["clipped_frames_share"], clipped / n <= GATE["clipped_frames_share"]
        ),
        "rgb_std_median": _check(median, GATE["rgb_std_median"], median >= GATE["rgb_std_median"]),
        "rgb_std_p10": _check(p10, GATE["rgb_std_p10"], p10 >= GATE["rgb_std_p10"]),
        "annotated": _check(annotated / n, GATE["annotated_share"], annotated / n >= GATE["annotated_share"]),
        "haze_limited": {"value": n - len(clear), "listed_apart": True, "passed": True},
    }
    return {"frames": n, "thresholds": thresholds, "passed": all(t["passed"] for t in thresholds.values())}
