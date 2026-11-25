"""Dust post-model of a lidar cloud: optical depth, the detection rule and leading-edge dust returns (FR-013-11 .. 15).

The one-way transmittance of a beam to its target is `exp(-tau)` with `tau` the integral of the extinction profile
(linear between samples); the intensity is attenuated two-way, `I = I0 exp(-2 tau)` (Beer-Lambert, built on
`minephys.environment`). A return is kept or dropped by the calibrated rule of Phillips, Guenther and McAree (2017):
kept for `tau <= tau_on`, dropped above the material floor, and in between kept when the beam hash `u` satisfies
`u (floor - tau_on) < floor - tau`. A lost return leaves one dust return at the leading edge of the cloud.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from minephys.environment import beer_lambert_transmittance

from pitstudio.sensors.beamhash import beam_value_array

TAU_ON = 0.3216  # onset: one-way transmittance 0.725
TAU_FLOOR = {"retro": 3.9120, "diffuse": 2.8134}  # -ln 0.02 and -ln 0.06
EDGE_BETA = 1.0e-6  # m^-1: the dust cloud starts at the first sample above this extinction
MAX_SPACING_M = 0.5
MATERIALS = ("retro", "diffuse")


@dataclass
class DustResult:
    """Row-aligned arrays of the rule and the output cloud (kept returns, then dust returns, in input order)."""

    tau: np.ndarray
    u: np.ndarray
    kept: np.ndarray
    intensity: np.ndarray
    emit_dust: np.ndarray
    r_edge: np.ndarray
    cloud: dict[str, np.ndarray]


def _check_spacing(spacing: float) -> float:
    spacing = float(spacing)
    if not math.isfinite(spacing) or spacing <= 0.0 or spacing > MAX_SPACING_M:
        raise ValueError(f"the profile spacing must satisfy 0 < spacing <= {MAX_SPACING_M} m, got {spacing!r}")
    return spacing


def _profile_rows(beta: Any, n: int, beams: np.ndarray | None) -> np.ndarray:
    """`beta` as a float64 array (m,) or (n, m); every sample finite and non-negative, naming the beam of a bad row."""
    b = np.asarray(beta, dtype=np.float64)
    if b.ndim not in (1, 2):
        raise ValueError("the extinction profile must have shape (m,) or (n, m)")
    if b.ndim == 2 and b.shape[0] != n:
        raise ValueError(f"{b.shape[0]} extinction profiles for {n} returns")
    if b.shape[-1] < 2:
        raise ValueError("an extinction profile needs at least two samples")
    bad = ~(np.isfinite(b) & (b >= 0.0))
    if bad.any():
        if b.ndim == 2:
            row = int(np.flatnonzero(bad.any(axis=1))[0])
            who = f"beam {int(beams[row])}" if beams is not None else f"row {row}"
        else:
            who = "the shared profile"
        raise ValueError(f"{who}: the extinction profile has a negative or non-finite sample")
    return b


def _optical_depth(b: np.ndarray, spacing: float, ranges: np.ndarray) -> np.ndarray:
    m = b.shape[-1]
    s = np.arange(m) * spacing
    k = np.searchsorted(s, ranges, side="right") - 1  # last sample at or before each range
    k = np.clip(k, 0, m - 1)
    cumulative = np.concatenate(
        [np.zeros((*b.shape[:-1], 1)), np.cumsum(0.5 * (b[..., :-1] + b[..., 1:]) * spacing, axis=-1)], axis=-1
    )
    rows = np.arange(len(ranges))
    shared = b.ndim == 1
    base = cumulative[k] if shared else cumulative[rows, k]
    b_k = b[k] if shared else b[rows, k]
    k_next = np.minimum(k + 1, m - 1)
    b_next = b[k_next] if shared else b[rows, k_next]
    remainder = np.clip(ranges - s[k], 0.0, None)
    b_r = b_k + (b_next - b_k) * (remainder / spacing)
    return base + 0.5 * (b_k + b_r) * remainder


def optical_depth(beta: Any, spacing: float, ranges: Any) -> np.ndarray:
    """The integral of the extinction profile from 0 to each range (m), linear between samples; zero for range 0."""
    spacing = _check_spacing(spacing)
    r = np.atleast_1d(np.asarray(ranges, dtype=np.float64))
    b = _profile_rows(beta, len(r), None)
    if not np.all(np.isfinite(r)) or np.any(r < 0.0):
        raise ValueError("ranges must be finite and non-negative")
    if np.any((b.shape[-1] - 1) * spacing < r):
        raise ValueError("the extinction profile does not reach the largest range")
    return _optical_depth(b, spacing, r)


def _leading_edge(b: np.ndarray, spacing: float, ranges: np.ndarray, rows: np.ndarray) -> np.ndarray:
    s = np.arange(b.shape[-1]) * spacing
    edge = np.full(len(ranges), np.nan)
    for i in rows:
        profile = b if b.ndim == 1 else b[i]
        hit = np.flatnonzero((profile > EDGE_BETA) & (s < ranges[i]))
        if hit.size:
            edge[i] = s[hit[0]]
    return edge


def classify(tau: Any, u: Any, retro: Any) -> np.ndarray:
    """The keep rule of FR-013-12 on baked inputs: a return is kept when `tau <= 0.3216`, or when `tau` is within the
    material floor and the beam value `u` is below the linear drop probability (`tau` and `u` float64, `retro` bool)."""
    tau, u = np.asarray(tau, dtype=np.float64), np.asarray(u, dtype=np.float64)
    floor = np.where(np.asarray(retro, dtype=bool), TAU_FLOOR["retro"], TAU_FLOOR["diffuse"])
    return (tau <= TAU_ON) | ((tau <= floor) & (u * (floor - TAU_ON) < floor - tau))


def emit_dust(tau: Any, kept: Any, max_returns: int) -> np.ndarray:
    """The dust-return rule of FR-013-13: `tau > 0.3216` and the return was dropped, or `max_returns >= 2`."""
    return (np.asarray(tau, dtype=np.float64) > TAU_ON) & (~np.asarray(kept, dtype=bool) | (max_returns >= 2))


def apply_dust(
    beam: Any,
    range_m: Any,
    material: Any,
    intensity: Any,
    xyz: Any,
    beta: Any,
    spacing: float,
    *,
    frame: int,
    seed: int,
    dust_return_intensity: float,
    max_returns: int = 1,
) -> DustResult:
    """Attenuate a lidar cloud through dust, drop returns by the calibrated rule and add leading-edge dust returns.

    Raises `ValueError` (naming the beam index of a defective return) before anything is returned (FR-013-15).
    """
    spacing = _check_spacing(spacing)
    beams = np.asarray(beam)
    r = np.asarray(range_m, dtype=np.float64)
    mat = np.asarray(material)
    i0 = np.asarray(intensity, dtype=np.float64)
    pts = np.asarray(xyz, dtype=np.float64)
    n = len(r)
    if not (len(beams) == len(mat) == len(i0) == len(pts) == n) or pts.shape != (n, 3):
        raise ValueError("beam, range_m, material, intensity and xyz must have the same length n (xyz shape (n, 3))")
    b = _profile_rows(beta, n, beams)
    for i in range(n):
        who = f"beam {int(beams[i])}"
        if not math.isfinite(r[i]) or r[i] <= 0.0:
            raise ValueError(f"{who}: the range must be finite and positive, got {r[i]!r}")
        if str(mat[i]) not in MATERIALS:
            raise ValueError(f"{who}: the material class must be 'retro' or 'diffuse', got {mat[i]!r}")
        if (b.shape[-1] - 1) * spacing < r[i]:
            raise ValueError(
                f"{who}: the extinction profile reaches {(b.shape[-1] - 1) * spacing} m, short of the range {r[i]}"
            )
    tau = _optical_depth(b, spacing, r)
    u = beam_value_array(frame, beams.astype(np.uint32), seed)
    kept = classify(tau, u, mat == "retro")
    emit = emit_dust(tau, kept, max_returns)
    edge = _leading_edge(b, spacing, r, np.flatnonzero(emit))
    emit &= np.isfinite(edge)
    edge = np.where(emit, edge, np.nan)
    transmittance = np.asarray(beer_lambert_transmittance(tau, 1.0), dtype=np.float64)  # exp(-tau)
    attenuated = i0 * transmittance * transmittance  # two-way: exp(-2 tau)
    scale = np.where(emit, edge / r, 0.0)[:, None]
    dust_xyz = pts[emit] * scale[emit]
    cloud = {
        "beam": np.concatenate([beams[kept], beams[emit]]),
        "x": np.concatenate([pts[kept, 0], dust_xyz[:, 0]]),
        "y": np.concatenate([pts[kept, 1], dust_xyz[:, 1]]),
        "z": np.concatenate([pts[kept, 2], dust_xyz[:, 2]]),
        "range_m": np.concatenate([r[kept], edge[emit]]),
        "intensity": np.concatenate([attenuated[kept], np.full(int(emit.sum()), float(dust_return_intensity))]),
        "material_class": np.concatenate([mat[kept].astype("<U7"), np.full(int(emit.sum()), "dust", dtype="<U7")]),
    }
    return DustResult(tau=tau, u=u, kept=kept, intensity=attenuated, emit_dust=emit, r_edge=edge, cloud=cloud)
