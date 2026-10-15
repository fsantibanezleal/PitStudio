"""S1 dust metrics and the lidar-versus-radar comparison (FR-013-36, FR-013-37, FR-013-42).

`s1_metrics` bins labelled frames by target range and transmittance level and reports the probability of detection, the
points on target, the false dust returns and the time-to-collision margin at the detection range. `compare_sensors`
applies the decision rule: a sensor is better only when the paired 95 % interval of the mean score difference
excludes 0.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

RADAR_LABEL = "radar dust immunity assumed (UNVERIFIED)"
PD_THRESHOLD = 0.9
# two-sided 95 % Student-t quantiles for 1 .. 30 degrees of freedom (standard table values)
_T975 = (
    12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120,
    2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042,
)  # fmt: skip


def _t_quantile(df: int) -> float:
    if df <= len(_T975):
        return _T975[df - 1]
    z = 1.959963984540054  # Cornish-Fisher expansion for df > 30
    return z + (z**3 + z) / (4 * df) + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)


def _finite_positive(value: Any) -> bool:
    return bool(isinstance(value, (int, float, np.integer, np.floating)) and math.isfinite(value) and value > 0)


def _check_options(k_min: Any, levels: Sequence[Any], range_bin_m: Any, speeds: Sequence[Any]) -> None:
    if not isinstance(k_min, (int, np.integer)) or isinstance(k_min, bool) or k_min < 1:
        raise ValueError(f"k_min must be an integer >= 1, got {k_min!r}")
    if not len(levels):
        raise ValueError("levels must not be empty")
    if not _finite_positive(range_bin_m):
        raise ValueError(f"range_bin_m must be finite and positive, got {range_bin_m!r}")
    if not len(speeds) or not all(_finite_positive(v) for v in speeds):
        raise ValueError(f"speeds_km_h must be finite and positive, got {tuple(speeds)!r}")


def _check_frame(frame: Mapping[str, Any], index: int, target_ids: Mapping[str, int], levels: Sequence[Any]) -> int:
    where = f"frame {index}"
    target = frame["target"]
    if target not in target_ids:
        raise ValueError(f"{where}: target {target!r} is not in target_ids")
    if frame["level"] not in levels:
        raise ValueError(f"{where}: level {frame['level']!r} is not in levels")
    r = frame["target_range_m"]
    if not isinstance(r, (int, float, np.integer, np.floating)) or not math.isfinite(r) or r < 0:
        raise ValueError(f"{where}: target_range_m must be finite and non-negative, got {r!r}")
    if not _finite_positive(frame["beams_emitted"]):
        raise ValueError(f"{where}: beams_emitted must be positive, got {frame['beams_emitted']!r}")
    if len(frame["object_id"]) != len(frame["material_class"]):
        raise ValueError(f"{where}: object_id and material_class must have the same length")
    return int(target_ids[target])


def s1_metrics(
    observations: Sequence[Mapping[str, Any]],
    *,
    target_ids: Mapping[str, int],
    levels: Sequence[Any],
    k_min: int = 3,
    range_bin_m: float = 5.0,
    speeds_km_h: Sequence[float] = (30, 40, 50),
    margin_s: float = 3.0,
) -> dict[str, list[dict[str, Any]]]:
    """Bin frames by target range and level; see the module docstring. Hostile input raises `ValueError`."""
    _check_options(k_min, levels, range_bin_m, speeds_km_h)
    groups: dict[tuple[str, Any, int], list[tuple[int, int, int]]] = defaultdict(list)
    for index, frame in enumerate(observations):
        tid = _check_frame(frame, index, target_ids, levels)
        ids = np.asarray(frame["object_id"])
        cls = np.asarray(frame["material_class"])
        dust = cls == "dust"
        on_target = int(np.count_nonzero((ids == tid) & ~dust))
        bin_index = math.floor(frame["target_range_m"] / range_bin_m)
        groups[(frame["target"], frame["level"], bin_index)].append(
            (on_target, int(dust.sum()), int(frame["beams_emitted"]))
        )

    def level_key(level: Any) -> int:
        return next(i for i, candidate in enumerate(levels) if candidate == level)

    bins: list[dict[str, Any]] = []
    for (target, level, bin_index), rows in sorted(
        groups.items(), key=lambda kv: (kv[0][0], level_key(kv[0][1]), kv[0][2])
    ):
        frames = len(rows)
        detected = sum(1 for on, _, _ in rows if on >= k_min)
        beams = sum(b for _, _, b in rows)
        bins.append(
            {
                "target": target,
                "level": level,
                "bin_lo_m": bin_index * range_bin_m,
                "bin_hi_m": (bin_index + 1) * range_bin_m,
                "frames": frames,
                "p_d": detected / frames,
                "points_on_target_mean": sum(on for on, _, _ in rows) / frames,
                "false_dust_per_1e4_beams": sum(d for _, d, _ in rows) / beams * 1e4,
            }
        )
    detection: list[dict[str, Any]] = []
    seen: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in bins:
        seen[(row["target"], row["level"])].append(row)
    for (target, level), level_rows in seen.items():
        good = [r["bin_lo_m"] for r in level_rows if r["p_d"] >= PD_THRESHOLD]
        r_det = max(good) if good else None
        detection.append(
            {
                "target": target,
                "level": level,
                "r_det_m": r_det,
                "ttc_margin_s": {
                    float(v): (None if r_det is None else r_det / (float(v) / 3.6) - margin_s) for v in speeds_km_h
                },
            }
        )
    return {"bins": bins, "detection": detection}


def compare_sensors(a: Any, b: Any, *, a_name: str = "lidar", b_name: str = "radar") -> dict[str, Any]:
    """Paired comparison of per-frame scores: a sensor is better only when the 95 % interval of a - b excludes 0."""
    xa, xb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if xa.shape != xb.shape or xa.ndim != 1:
        raise ValueError("a and b must be paired one-dimensional scores of equal length")
    if len(xa) < 2:
        raise ValueError("at least 2 paired scores are required")
    if not (np.all(np.isfinite(xa)) and np.all(np.isfinite(xb))):
        raise ValueError("scores must be finite")
    d = xa - xb
    n = len(d)
    mean = float(d.mean())
    sd = float(d.std(ddof=1))
    half = _t_quantile(n - 1) * sd / math.sqrt(n)
    low, high = mean - half, mean + half
    verdict = f"{a_name} better" if low > 0 else (f"{b_name} better" if high < 0 else "no significant difference")
    return {
        "verdict": verdict,
        "mean_diff": mean,
        "ci_low": low,
        "ci_high": high,
        "n": n,
        "label": RADAR_LABEL if "radar" in (a_name, b_name) else None,
    }
