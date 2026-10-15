"""Camera post-models: S3 haze, S3 component boxes, S2 exposure, noise and vignetting, pinhole intrinsics (FR-013-16
.. 20).

NumPy only (plus the dust optical depth). Every function validates its inputs and raises `ValueError` naming the
offending parameter; nothing is returned for a hostile input.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from pitstudio.sensors import dust

BOX_NOTE = "boxes from semantic components; touching instances merge"
AIRLIGHT_MAX = 1.0e6


def _positive(name: str, value: Any, *, allow_zero: bool = False) -> float:
    if (
        not isinstance(value, (int, float, np.integer, np.floating))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'non-negative' if allow_zero else 'positive'}, got {value!r}")
    return float(value)


# ----------------------------------------------------------------------------------------------------------- haze
def haze(
    radiance: Any,
    distance: Any,
    airlight: Any,
    *,
    beta: Any,
    spacing: float | None = None,
    exit_distance: Any = None,
) -> np.ndarray:
    """Haze `I = J t + A (1 - t)` with `t = exp(-tau_c)`, per channel; float32 (h, w, 3) (FR-013-16).

    `beta` is a uniform extinction (m^-1) or an (h, w, m) profile along each ray sampled every `spacing` m. A pixel
    without a hit (non-finite distance) integrates to `exit_distance` (a float or an (h, w) array).
    """
    j = np.asarray(radiance)
    if j.ndim != 3 or j.shape[2] != 3:
        raise ValueError(f"radiance must have shape (h, w, 3), got {j.shape}")
    j = j.astype(np.float32)
    if not np.all(np.isfinite(j)):
        raise ValueError("radiance holds a non-finite value")
    d = np.asarray(distance, dtype=np.float64)
    if d.shape != j.shape[:2]:
        raise ValueError(f"distance must have shape {j.shape[:2]} like radiance, got {d.shape}")
    a = np.asarray(airlight, dtype=np.float64)
    if a.shape != (3,) or not np.all(np.isfinite(a)) or np.any(a < 0.0) or np.any(a > AIRLIGHT_MAX):
        raise ValueError("airlight must be 3 finite linear-RGB components in [0, 10^6]")
    hit = np.isfinite(d)
    if np.any(d[hit] <= 0.0):
        raise ValueError("distance must be positive where it is finite")
    if not hit.all():
        if exit_distance is None:
            raise ValueError("exit_distance is required for pixels without a hit")
        exit_d = np.broadcast_to(np.asarray(exit_distance, dtype=np.float64), d.shape)
        if not np.all(np.isfinite(exit_d)) or np.any(exit_d <= 0.0):
            raise ValueError("exit_distance must be finite and positive")
        d = np.where(hit, d, exit_d)
    b = np.asarray(beta, dtype=np.float64)
    if b.ndim == 0:
        beta_value = _positive("beta", float(b), allow_zero=True)
        tau = beta_value * d
    else:
        if spacing is None or b.ndim != 3 or b.shape[:2] != d.shape:
            raise ValueError("a beta profile needs shape (h, w, m) and a spacing")
        tau = dust.optical_depth(b.reshape(-1, b.shape[-1]), spacing, d.reshape(-1)).reshape(d.shape)
    t = np.exp(-tau)[..., None]
    return (j.astype(np.float64) * t + a[None, None, :] * (1.0 - t)).astype(np.float32)


# ----------------------------------------------------------------------------------------------- component boxes
def component_boxes(semantic: Any, min_area_px: int = 16) -> list[dict[str, int]]:
    """One box per 8-connected component of each semantic id with at least `min_area_px` pixels (FR-013-17)."""
    img = np.asarray(semantic)
    if img.ndim != 2 or img.dtype.kind not in "iu":
        raise ValueError("semantic must be a 2-D integer array")
    if not isinstance(min_area_px, (int, np.integer)) or min_area_px < 1:
        raise ValueError(f"min_area_px must be an integer >= 1, got {min_area_px!r}")
    h, w = img.shape
    seen = np.zeros(img.shape, dtype=bool)
    flat = img.tolist()
    boxes: list[dict[str, int]] = []
    for y0 in range(h):
        for x0 in range(w):
            if seen[y0, x0]:
                continue
            cls = flat[y0][x0]
            seen[y0, x0] = True
            queue = deque([(y0, x0)])
            x_min = x_max = x0
            y_min = y_max = y0
            area = 0
            while queue:
                y, x = queue.popleft()
                area += 1
                x_min, x_max, y_min, y_max = min(x_min, x), max(x_max, x), min(y_min, y), max(y_max, y)
                for yy in range(max(y - 1, 0), min(y + 2, h)):
                    for xx in range(max(x - 1, 0), min(x + 2, w)):
                        if not seen[yy, xx] and flat[yy][xx] == cls:
                            seen[yy, xx] = True
                            queue.append((yy, xx))
            if area >= min_area_px:
                boxes.append(
                    {"class_id": int(cls), "x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max, "area": area}
                )
    return sorted(boxes, key=lambda b: (b["class_id"], b["y_min"], b["x_min"]))


# ------------------------------------------------------------------------------------------------------ exposure
def _check_exposure(exposure_time_s: Any, f_number: Any, kappa: Any) -> tuple[float, float, float]:
    return (
        _positive("exposure_time_s", exposure_time_s),
        _positive("f_number", f_number),
        _positive("kappa", kappa),
    )


def signal_electrons(
    L: Any, *, exposure_time_s: float, f_number: float, kappa: float, cos4: Any = None
) -> np.ndarray | np.float64:
    """The signal `S = kappa L t_e / N^2` in electrons, times `cos4` when given (FR-013-18)."""
    t, n, k = _check_exposure(exposure_time_s, f_number, kappa)
    s = np.asarray(L, dtype=np.float64) * (k * t / n**2)
    if cos4 is not None:
        s = s * np.asarray(cos4, dtype=np.float64)
    return s if s.ndim else np.float64(s)


def vignette_cos4(width_px: int, height_px: int, fx_px: float, fy_px: float, cx_px: float, cy_px: float) -> np.ndarray:
    """`cos^4` of the angle between each pixel ray (pixel centre at col + 0.5, row + 0.5) and the optical axis."""
    u = (np.arange(width_px) + 0.5 - cx_px) / fx_px
    v = (np.arange(height_px) + 0.5 - cy_px) / fy_px
    return 1.0 / (1.0 + u[None, :] ** 2 + v[:, None] ** 2) ** 2


_M64 = np.uint64(0xFFFFFFFFFFFFFFFF)


def _splitmix(x: Any) -> Any:
    with np.errstate(over="ignore"):
        x = x + np.uint64(0x9E3779B97F4A7C15)
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return x ^ (x >> np.uint64(31))


def noisy_electrons(
    signal: Any, *, read_noise_e: float, seed: int, image_index: int, first_pixel: int = 0
) -> np.ndarray:
    """`S + n`, `n` zero-mean Gaussian with variance `S + read_noise_e^2`, counter-based in (seed, image, pixel).

    The pixel index of the i-th element (C order) is `first_pixel + i`; a pixel's draw never depends on the rest of the
    array. Two splitmix64 streams feed a Box-Muller transform.
    """
    s = np.asarray(signal, dtype=np.float64)
    sigma_read = _positive("read_noise_e", read_noise_e, allow_zero=True)
    flat = s.reshape(-1)
    pixel = np.arange(len(flat), dtype=np.uint64) + np.uint64(first_pixel)
    with np.errstate(over="ignore"):
        key = _splitmix(np.uint64(int(seed) & 0xFFFFFFFF) * np.uint64(0x2545F4914F6CDD1D) + np.uint64(int(image_index)))
        h1 = _splitmix(key ^ _splitmix(pixel))
        h2 = _splitmix(h1 ^ np.uint64(0xD1B54A32D192ED03))
    u1 = 1.0 - (h1 >> np.uint64(11)).astype(np.float64) * 2.0**-53  # in (0, 1]
    u2 = (h2 >> np.uint64(11)).astype(np.float64) * 2.0**-53
    z = np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)
    sigma = np.sqrt(np.clip(flat, 0.0, None) + sigma_read**2)
    return (flat + sigma * z).reshape(s.shape)


def expose(
    L: Any,
    *,
    exposure_time_s: float,
    f_number: float,
    kappa: float,
    gain: float,
    read_noise_e: float,
    dn_max: int,
    vignetting: bool,
    intrinsics: Mapping[str, float],
    seed: int,
    image_index: int,
    noise: bool = True,
) -> np.ndarray:
    """Digital numbers `DN = clip(round(G (S + n)), 0, DN_max)` of an (h, w) radiance image, uint16 (FR-013-18)."""
    img = np.asarray(L, dtype=np.float64)
    if img.ndim != 2:
        raise ValueError(f"L (radiance) must be a 2-D image, got shape {img.shape}")
    if not np.all(np.isfinite(img)):
        raise ValueError("L (radiance) holds a non-finite value")
    t, n, k = _check_exposure(exposure_time_s, f_number, kappa)
    g = _positive("gain", gain)
    _positive("read_noise_e", read_noise_e, allow_zero=True)
    if not isinstance(dn_max, (int, np.integer)) or isinstance(dn_max, bool) or not 1 <= dn_max <= 65535:
        raise ValueError(f"dn_max must be an integer in [1, 65535], got {dn_max!r}")
    h, w = img.shape
    cos4 = None
    if vignetting:
        cos4 = vignette_cos4(w, h, intrinsics["fx_px"], intrinsics["fy_px"], intrinsics["cx_px"], intrinsics["cy_px"])
    s = signal_electrons(img, exposure_time_s=t, f_number=n, kappa=k, cos4=cos4)
    if noise:
        s = noisy_electrons(s, read_noise_e=read_noise_e, seed=seed, image_index=image_index)
    return np.clip(np.rint(g * s), 0, dn_max).astype(np.uint16)


# -------------------------------------------------------------------------------------------------- pinhole model
def intrinsics(
    focal_length_m: float, pixel_pitch_m: float, width_px: int, height_px: int, principal_point_px: Sequence[float]
) -> np.ndarray:
    """The pinhole matrix `K = [[f/p, 0, cx], [0, f/p, cy], [0, 0, 1]]` (float64)."""
    f = _positive("focal_length_m", focal_length_m)
    p = _positive("pixel_pitch_m", pixel_pitch_m)
    cx, cy = (float(v) for v in principal_point_px)
    return np.array([[f / p, 0.0, cx], [0.0, f / p, cy], [0.0, 0.0, 1.0]], dtype=np.float64)


def gsd_m(pixel_pitch_m: float, h_agl_m: float, focal_length_m: float) -> float:
    """Ground sample distance `p H / f` (m)."""
    return float(
        _positive("pixel_pitch_m", pixel_pitch_m)
        * _positive("h_agl_m", h_agl_m)
        / _positive("focal_length_m", focal_length_m)
    )


def project(k: Any, world_from_camera: Any, points_world: Any) -> tuple[np.ndarray, np.ndarray]:
    """Pixels `(n, 2)` and depths `(n,)` of world points; camera axes x right, y down, z forward (OpenCV)."""
    pose = np.asarray(world_from_camera, dtype=np.float64)
    pts = np.asarray(points_world, dtype=np.float64).reshape(-1, 3)
    cam = (pose[:3, :3].T @ (pts - pose[:3, 3]).T).T
    depth = cam[:, 2]
    if np.any(depth <= 0.0):
        raise ValueError("a point is at or behind the camera (depth <= 0)")
    kk = np.asarray(k, dtype=np.float64)
    px = np.column_stack([kk[0, 0] * cam[:, 0] / depth + kk[0, 2], kk[1, 1] * cam[:, 1] / depth + kk[1, 2]])
    return px, depth


def backproject(k: Any, world_from_camera: Any, pixels: Any, depth: Any) -> np.ndarray:
    """World points of pixels at the given camera-axis depths."""
    pose = np.asarray(world_from_camera, dtype=np.float64)
    kk = np.asarray(k, dtype=np.float64)
    px = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    z = np.asarray(depth, dtype=np.float64).reshape(-1)
    cam = np.column_stack([(px[:, 0] - kk[0, 2]) / kk[0, 0] * z, (px[:, 1] - kk[1, 2]) / kk[1, 1] * z, z])
    return (pose[:3, :3] @ cam.T).T + pose[:3, 3]
