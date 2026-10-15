"""Analytical slope-radar (GB-InSAR, sensor S4b) series builder for case C1 (FR-010-34 to FR-010-37, FR-010-41,
FR-010-42).

Units: positions in m, displacements and wavelength in mm, time in h, the scan interval in min.

Sign convention (product-wide, the one of ``minephys``): line-of-sight displacement is positive away from the radar
(range
increasing), ``d = u . e`` with ``e`` the unit vector from the radar position to the pixel; a view that shows motion
toward
the radar shows ``-d`` and says so.

Per pixel: the wall displacement ``u(t)`` is projected on ``e``; the noise is white Gaussian of sd
``|d_end - d_0| / SNR`` plus, in the atmospheric stratum, an AR(1) term of the same marginal sd; the phase is
``wrap_(-pi, pi)[(4 pi / lambda) (d - d_0 + n)]`` and the measured series ``(lambda / 4 pi) numpy.unwrap(phase)``. Every
standard normal comes from a counter-based generator (``numpy.random.Philox``) keyed by (run seed, stream, pixel id) and
indexed by the scan, so the value at scan k never depends on the series length or on any other pixel. A pixel whose true
increment between two scans reaches lambda / 4 is flagged ambiguous (phase wrapping) from that scan on and excluded
from TTF
evaluation.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

SIGN_CONVENTION = "positive = away from the radar"
SIGMA_W_M = 30.0
MIN_RANGE_M = 1e-6
MAX_PIXELS = 1_000_000
WAVELENGTH_RANGE_MM = (1.0, 1000.0)  # exclusive (FR-010-42)
AMBIGUOUS = "ambiguous (phase wrapping)"
_TWO53 = float(2**53)


class InvalidRadarConfigError(ValueError):
    """A radar configuration or input rejected before projecting (FR-010-37, FR-010-42); ``field`` names it."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


@dataclass(frozen=True)
class PixelSeries:
    """The series of one pixel: the ``radar-pixel`` record and its arrays."""

    record: dict[str, Any]
    d_mm: np.ndarray
    measured_mm: np.ndarray
    phase: np.ndarray
    noise_mm: np.ndarray
    evaluable: bool


# ----------------------------------------------------------------------------------------------------------------------
# geometry


def los_unit_vectors(radar_position_m: Any, pixel_positions_m: Any) -> np.ndarray:
    """The unit vector from the radar to each pixel, shape (N, 3)."""
    r = np.asarray(radar_position_m, dtype=float)
    p = np.atleast_2d(np.asarray(pixel_positions_m, dtype=float))
    diff = p - r
    return diff / np.linalg.norm(diff, axis=-1, keepdims=True)


def project_los(displacement_mm: Any, radar_position_m: Any, pixel_positions_m: Any) -> np.ndarray:
    """Line-of-sight displacement ``u . e`` (positive = away from the radar); (N, 3) -> (N,), (N, T, 3) -> (N, T)."""
    u = np.asarray(displacement_mm, dtype=float)
    e = los_unit_vectors(radar_position_m, pixel_positions_m)
    if u.ndim == 2:
        return np.einsum("nc,nc->n", u, e)
    return np.einsum("ntc,nc->nt", u, e)


def gaussian_weight(pixel_positions_m: Any, peak_position_m: Any, sigma_w_m: float = SIGMA_W_M) -> np.ndarray:
    """Spatial weight ``exp(-|x - x_peak|^2 / (2 sigma_w^2))`` of each pixel, peak 1."""
    p = np.atleast_2d(np.asarray(pixel_positions_m, dtype=float))
    d2 = ((p - np.asarray(peak_position_m, dtype=float)) ** 2).sum(axis=-1)
    return np.exp(-d2 / (2.0 * sigma_w_m**2))


def wall_displacement_field(
    omega_mm: Any, pixel_positions_m: Any, peak_position_m: Any, dip_vectors: Any, sigma_w_m: float = SIGMA_W_M
) -> np.ndarray:
    """Event displacement times the Gaussian weight along each facet's unit down-dip vector; shape (N, T, 3)."""
    dip = np.atleast_2d(np.asarray(dip_vectors, dtype=float))
    norm = np.linalg.norm(dip, axis=-1)
    for i, n in enumerate(norm):
        if not (math.isfinite(float(n)) and n > 0.0):
            raise InvalidRadarConfigError(f"dip_vectors/{i}", "a facet normal must have finite, non-zero length")
    unit = dip / norm[:, None]
    weight = gaussian_weight(pixel_positions_m, peak_position_m, sigma_w_m)
    omega = np.asarray(omega_mm, dtype=float)
    return weight[:, None, None] * omega[None, :, None] * unit[:, None, :]


# ----------------------------------------------------------------------------------------------------------------------
# phase


def first_ambiguous_scan(d_mm: Any, wavelength_mm: float) -> int | None:
    """First scan k >= 1 whose increment ``|d_k - d_k-1|`` reaches lambda / 4, or None."""
    d = np.asarray(d_mm, dtype=float)
    hits = np.flatnonzero(np.abs(np.diff(d)) >= wavelength_mm / 4.0)
    return int(hits[0]) + 1 if hits.size else None


def wrapped_phase(d_mm: Any, wavelength_mm: float) -> np.ndarray:
    """``wrap_(-pi, pi)[(4 pi / lambda) d]`` for the displacement ``d`` relative to the first scan."""
    x = 4.0 * math.pi / wavelength_mm * np.asarray(d_mm, dtype=float)
    return (x + math.pi) % (2.0 * math.pi) - math.pi


def unwrap_phase(phase: Any, wavelength_mm: float) -> np.ndarray:
    """``(lambda / 4 pi) numpy.unwrap(phase)``: the measured displacement along time."""
    return wavelength_mm / (4.0 * math.pi) * np.unwrap(np.asarray(phase, dtype=float))


# ----------------------------------------------------------------------------------------------------------------------
# keyed noise


def _normals(run_seed: int, pixel_id: int, n: int, stream: int) -> np.ndarray:
    """Standard normals w_0 .. w_n-1, w_k from the k-th pair of words of the Philox stream keyed by the triple."""
    key = np.array([int(run_seed), (int(stream) << 32) | int(pixel_id)], dtype=np.uint64)  # a 128-bit key of two words
    raw = np.random.Philox(key=key).random_raw(2 * n)
    u1 = ((raw[0::2] >> np.uint64(11)).astype(float) + 0.5) / _TWO53
    u2 = (raw[1::2] >> np.uint64(11)).astype(float) / _TWO53
    return np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * math.pi * u2)


def noise_series(run_seed: int, pixel_id: int, n_scans: int, sd_mm: float, rho: float | None = None) -> np.ndarray:
    """White noise (rho None) or a stationary AR(1) series (lag-1 correlation rho, marginal sd ``sd_mm``) of ``n_scans``
    scans, drawn from a counter-based generator keyed by (run seed, stream, pixel id)."""
    if not (isinstance(sd_mm, int | float | np.floating) and math.isfinite(sd_mm) and sd_mm >= 0.0):
        raise InvalidRadarConfigError("sd_mm", f"the noise standard deviation must be finite and >= 0, got {sd_mm!r}")
    if rho is not None and not (math.isfinite(rho) and abs(rho) < 1.0):
        raise InvalidRadarConfigError("rho", f"the AR(1) coefficient must satisfy |rho| < 1, got {rho!r}")
    if rho is None:
        return sd_mm * _normals(run_seed, pixel_id, n_scans, 0)
    w = _normals(run_seed, pixel_id, n_scans, 1)
    scale = math.sqrt(1.0 - rho * rho)
    out = np.empty(n_scans)
    prev = float(w[0])
    out[0] = prev
    for k in range(1, n_scans):
        prev = rho * prev + scale * float(w[k])
        out[k] = prev
    return sd_mm * out


# ----------------------------------------------------------------------------------------------------------------------
# the builder


def _finite_array(value: Any, field: str, shape: tuple[int, ...] | None = None) -> np.ndarray:
    try:
        arr = np.asarray(value, dtype=float)
    except TypeError, ValueError:
        raise InvalidRadarConfigError(field, "must be numeric") from None
    if shape is not None and arr.shape != shape:
        raise InvalidRadarConfigError(field, f"must have shape {shape}, got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise InvalidRadarConfigError(field, "contains a non-finite value")
    return arr


def _validate(
    t_h: Any, radar: Mapping[str, Any], pixels: Sequence[Mapping[str, Any]], snr: float | None, ar1_rho: float | None
) -> tuple[np.ndarray, np.ndarray, float, list[tuple[int, np.ndarray, np.ndarray]]]:
    count = len(pixels)  # the size is read before any pixel is touched
    if count < 1:
        raise InvalidRadarConfigError("pixels", "the pixel set is empty")
    if count > MAX_PIXELS:
        raise InvalidRadarConfigError("pixels", f"{count} pixels exceed the limit of {MAX_PIXELS}")
    radar_pos = _finite_array(radar.get("position_m"), "radar/position_m", (3,))
    lam = radar.get("wavelength_mm")
    lo, hi = WAVELENGTH_RANGE_MM
    if not (isinstance(lam, int | float | np.floating) and math.isfinite(lam) and lo < lam < hi):
        raise InvalidRadarConfigError(
            "radar/wavelength_mm", f"the wavelength must lie in ({lo:g}, {hi:g}) mm, got {lam!r}"
        )
    scan = radar.get("scan_interval_min")
    if not (isinstance(scan, int | float | np.floating) and math.isfinite(scan) and scan > 0.0):
        raise InvalidRadarConfigError(
            "radar/scan_interval_min", f"the scan interval must be finite and > 0, got {scan!r}"
        )
    t = _finite_array(t_h, "t_h")
    if t.ndim != 1 or t.size < 2 or not np.all(np.diff(t) > 0.0):
        raise InvalidRadarConfigError("t_h", "the scan times must be a strictly increasing sequence of at least 2")
    if snr is not None and not (isinstance(snr, int | float | np.floating) and math.isfinite(snr) and snr > 0.0):
        raise InvalidRadarConfigError("snr", f"the SNR must be finite and > 0 (or None for no noise), got {snr!r}")
    if ar1_rho is not None and not (math.isfinite(ar1_rho) and abs(ar1_rho) < 1.0):
        raise InvalidRadarConfigError("ar1_rho", f"the AR(1) coefficient must satisfy |rho| < 1, got {ar1_rho!r}")
    seen: set[int] = set()
    checked: list[tuple[int, np.ndarray, np.ndarray]] = []
    for i, p in enumerate(pixels):
        pid = p["pixel_id"]
        if isinstance(pid, bool) or not isinstance(pid, int | np.integer) or not 0 <= pid <= 999_999 or pid in seen:
            raise InvalidRadarConfigError(f"pixels/{i}/pixel_id", "must be a unique integer in [0, 999999]")
        seen.add(int(pid))
        pos = _finite_array(p["position_m"], f"pixels/{i}/position_m", (3,))
        if float(np.linalg.norm(pos - radar_pos)) < MIN_RANGE_M:
            raise InvalidRadarConfigError(f"pixels/{i}", "the radar is within 1e-6 m of the pixel")
        disp = _finite_array(p["displacement_mm"], f"pixels/{i}/displacement_mm", (t.size, 3))
        checked.append((int(pid), pos, disp))
    return radar_pos, t, float(lam), checked


def build_radar_series(
    *,
    event_id: str,
    t_h: Any,
    radar: Mapping[str, Any],
    pixels: Sequence[Mapping[str, Any]],
    snr: float | None,
    run_seed: int,
    ar1_rho: float | None = None,
    stratum: str = "snr_obs",
    sink: Callable[[PixelSeries], None] | None = None,
) -> dict[int, PixelSeries]:
    """Line-of-sight series of every pixel (see the module docstring); the whole input is validated first."""
    radar_pos, t, lam, checked = _validate(t_h, radar, pixels, snr, ar1_rho)
    n = t.size
    out: dict[int, PixelSeries] = {}
    for pid, pos, disp in checked:
        d = project_los(disp[None, :, :], radar_pos, pos[None, :])[0]
        sigma = 0.0 if snr is None else abs(float(d[-1] - d[0])) / float(snr)
        noise = noise_series(run_seed, pid, n, sigma)
        if ar1_rho is not None:
            noise = noise + noise_series(run_seed, pid, n, sigma, rho=ar1_rho)
        phase = wrapped_phase(d - d[0] + noise, lam)
        measured = unwrap_phase(phase, lam)
        first = first_ambiguous_scan(d, lam)
        flags = [False] * n if first is None else [False] * first + [True] * (n - first)
        e = los_unit_vectors(radar_pos, pos[None, :])[0]
        u_end = disp[-1]
        norm = float(np.linalg.norm(u_end))
        psi = 0.0 if norm == 0.0 else math.degrees(math.acos(max(-1.0, min(1.0, float(u_end @ e) / norm))))
        record: dict[str, Any] = {
            "kind": "radar-pixel",
            "synthetic": True,
            "event_id": event_id,
            "stratum": stratum,
            "pixel_id": pid,
            "pixel_position_m": [float(x) for x in pos],
            "radar": {
                "position_m": [float(x) for x in radar_pos],
                "wavelength_mm": lam,
                "scan_interval_min": float(radar["scan_interval_min"]),
            },
            "psi_deg": psi,
            "sign_convention": SIGN_CONVENTION,
            "run_seed": int(run_seed),
            "status": "ok" if first is None else AMBIGUOUS,
            "t_h": [float(x) for x in t],
            "los_displacement_mm": [float(x) for x in d],
            "measured_los_displacement_mm": [float(x) for x in measured],
            "wrap_flags": flags,
        }
        if first is not None:
            record["ambiguous_from_scan"] = first
        series = PixelSeries(record, d, measured, phase, noise, first is None)
        out[pid] = series
        if sink is not None:
            sink(series)
    return out


def build_radar_map(series: Mapping[int, PixelSeries], scan_index: int) -> dict[str, Any]:
    """A ``radar-map`` document at one scan: the LOS displacement of every pixel and the count of ambiguous ones."""
    first = next(iter(series.values())).record
    pixels = []
    for pid, s in sorted(series.items()):
        pixels.append(
            {
                "pixel_id": pid,
                "position_m": list(s.record["pixel_position_m"]),
                "los_displacement_mm": float(s.d_mm[scan_index]),
                "status": s.record["status"],
            }
        )
    return {
        "kind": "radar-map",
        "synthetic": True,
        "event_id": first["event_id"],
        "radar": dict(first["radar"]),
        "sign_convention": SIGN_CONVENTION,
        "scan_index": scan_index,
        "t_h": float(first["t_h"][scan_index]),
        "ambiguous_pixels": sum(1 for s in series.values() if not s.evaluable),
        "pixels": pixels,
    }
