"""The corruption ladder of the robustness suite: dust, night and rain at five pre-registered severities (FR-009-25 to
FR-009-29, Table C of spec 009).

Every operation is defined in linear RGB (IEC 61966-2-1 transfer function) and the result is re-encoded: a uint8 image
gives a
uint8 image with round-half-to-even (the 8-bit value of an sRGB value v is `numpy.rint(255 v)`), a float image in [0,
1] gives
a float64 image. Severity 0 is the identity. The functions are pure: inputs are never modified and a failed check
returns no
image. The design values are fixed before any result; they follow the five-severity layout of Hendrycks and Dietterich
2019
(https://arxiv.org/abs/1903.12261): dust plays the role of fog, night of brightness, rain of snow plus contrast.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

CORRUPTIONS: tuple[str, ...] = ("dust", "night", "rain")
SEVERITIES: tuple[int, ...] = (0, 1, 2, 3, 4, 5)

# ---- Table C (design choices, pre-registered)
SIGMA_KM: dict[int, float] = {1: 0.75, 2: 1.5, 3: 3.0, 4: 6.0, 5: 12.0}  # dust extinction, 1/km
AIRLIGHT: tuple[float, float, float] = (0.58, 0.46, 0.31)  # linear RGB
D_REF_M = 100.0  # reference depth of an image without a depth map (FR-009-28)
EXPOSURE_K: dict[int, float] = {1: 0.5, 2: 0.25, 3: 0.125, 4: 0.0625, 5: 0.03125}  # night, 2^-s
SIGMA_N: dict[int, float] = {1: 0.002, 2: 0.004, 3: 0.006, 4: 0.008, 5: 0.010}  # night noise, linear units
RAIN_C: dict[int, float] = {1: 0.9, 2: 0.8, 3: 0.7, 4: 0.6, 5: 0.5}  # rain contrast factor
RAIN_RHO: dict[int, float] = {1: 0.005, 2: 0.01, 3: 0.02, 4: 0.03, 5: 0.05}  # streak coverage, fraction of pixels
RAIN_LEN_PX: dict[int, float] = {1: 8.0, 2: 12.0, 3: 16.0, 4: 20.0, 5: 24.0}  # streak length at 1,280 px width
L_R = 0.85  # rain light, linear
_ANGLE_MAX_DEG = 15.0  # image angle from the vertical, U(-15, 15)
_JITTER_DEG = 2.0  # per-streak jitter, U(-2, 2)
_STREAK_REFERENCE_WIDTH = 1280.0


@dataclass(frozen=True)
class CorruptionResult:
    """The corrupted image and the record of what was applied."""

    image: np.ndarray
    record: dict[str, Any]


# ----------------------------------------------------------------------------------------------------------------
# sRGB transfer function (IEC 61966-2-1)
# ----------------------------------------------------------------------------------------------------------------
def srgb_decode(v: np.ndarray) -> np.ndarray:
    """sRGB-encoded values in [0, 1] to linear light, float64, elementwise."""
    v = np.asarray(v, dtype=np.float64)
    return np.where(v <= 0.04045, v / 12.92, np.power(np.maximum((v + 0.055) / 1.055, 0.0), 2.4))  # type: ignore[no-any-return]


def srgb_encode(x: np.ndarray) -> np.ndarray:
    """Linear light to sRGB-encoded values, float64, elementwise; `x` is clipped to [0, 1] first."""
    x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)  # type: ignore[no-any-return]


def decode_u8(codes: np.ndarray) -> np.ndarray:
    """8-bit sRGB codes to linear float64: `srgb_decode(codes / 255)`."""
    return srgb_decode(np.asarray(codes, dtype=np.float64) / 255.0)


def quantize_u8(v: np.ndarray) -> np.ndarray:
    """8-bit codes of sRGB values in [0, 1]: `numpy.rint(255 v)` (round half to even), clipped to 0..255."""
    return np.clip(np.rint(255.0 * np.asarray(v, dtype=np.float64)), 0, 255).astype(np.uint8)  # type: ignore[no-any-return]


def encode_u8(x: np.ndarray) -> np.ndarray:
    """Linear light to 8-bit sRGB codes."""
    return quantize_u8(srgb_encode(x))


# ----------------------------------------------------------------------------------------------------------------
# argument checks (FR-009-29): ValueError naming the argument, nothing returned
# ----------------------------------------------------------------------------------------------------------------
def _check_severity(severity: object) -> int:
    if type(severity) is not int or severity not in SEVERITIES:
        raise ValueError(f"severity must be an int in {SEVERITIES}, got {severity!r}")
    return severity


def _check_image(image: object) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 1:
        raise ValueError("image must be a numpy array of shape (H, W, 3) with H, W >= 1")
    if image.dtype not in (np.uint8, np.float32, np.float64):
        raise ValueError(f"image dtype must be uint8, float32 or float64, got {image.dtype}")
    if image.dtype != np.uint8 and (not np.isfinite(image).all() or image.min() < 0.0 or image.max() > 1.0):
        raise ValueError("a float image must be finite and within [0, 1]")
    return image


def _check_depth(depth_m: object, shape: tuple[int, int]) -> np.ndarray:
    if not isinstance(depth_m, np.ndarray) or depth_m.dtype.kind != "f" or depth_m.shape != shape:
        raise ValueError(f"depth_m must be a float numpy array of the image's shape {shape}")
    if not np.isfinite(depth_m).all() or depth_m.min() < 0.0:
        raise ValueError("depth_m must be finite and >= 0")
    return depth_m


def _check_seed(seed: object) -> int:
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError(f"seed must be an int >= 0, got {seed!r}")
    return seed


def _to_linear(image: np.ndarray) -> np.ndarray:
    return decode_u8(image) if image.dtype == np.uint8 else srgb_decode(image.astype(np.float64))


def _from_linear(lin: np.ndarray, like: np.ndarray) -> np.ndarray:
    return encode_u8(lin) if like.dtype == np.uint8 else srgb_encode(lin)


# ----------------------------------------------------------------------------------------------------------------
# dust (FR-009-25, FR-009-28)
# ----------------------------------------------------------------------------------------------------------------
def transmittance(depth_m: np.ndarray, severity: int) -> np.ndarray:
    """Beer-Lambert transmittance t = exp(-sigma_s d / 1000) for depth `d` in metres and sigma_s from Table C."""
    return np.exp(-SIGMA_KM[_check_severity_nonzero(severity)] * np.asarray(depth_m, dtype=np.float64) / 1000.0)  # type: ignore[no-any-return]


def _check_severity_nonzero(severity: object) -> int:
    s = _check_severity(severity)
    if s == 0:
        raise ValueError("severity 0 has no Table C parameter")
    return s


def dust_linear(lin: np.ndarray, depth_m: np.ndarray, severity: int) -> np.ndarray:
    """Koschmieder haze in linear RGB: t I + (1 - t) A with t = exp(-sigma_s d / 1000); severity 0 returns a copy."""
    severity = _check_severity(severity)
    if severity == 0:
        return np.array(lin, dtype=np.float64, copy=True)
    t = transmittance(depth_m, severity)[..., None]
    return t * np.asarray(lin, dtype=np.float64) + (1.0 - t) * np.asarray(AIRLIGHT)  # type: ignore[no-any-return]


def dust(image: np.ndarray, depth_m: np.ndarray | None, severity: int) -> CorruptionResult:
    """Dust haze on an sRGB image (uint8 or float in [0, 1]) with the depth in metres, or the reference depth."""
    severity = _check_severity(severity)
    image = _check_image(image)
    assumed = depth_m is None
    depth = np.full(image.shape[:2], D_REF_M) if assumed else _check_depth(depth_m, image.shape[:2])
    record = {"corruption": "dust", "severity": severity, "depth_assumed": assumed}
    if severity == 0:
        return CorruptionResult(image.copy(), record)
    return CorruptionResult(_from_linear(dust_linear(_to_linear(image), depth, severity), image), record)


# ----------------------------------------------------------------------------------------------------------------
# night (FR-009-26)
# ----------------------------------------------------------------------------------------------------------------
def apply_exposure(lin: np.ndarray, k: float) -> np.ndarray:
    """Exposure factor `k` on linear light, no clipping, float64."""
    return float(k) * np.asarray(lin, dtype=np.float64)  # type: ignore[no-any-return]


def night_linear(lin: np.ndarray, severity: int, *, seed: int, sigma_n: float | None = None) -> np.ndarray:
    """clip(k_s I + n, 0, 1) with n ~ N(0, sigma^2) per pixel and channel from a counter-based generator (Philox) keyed
    by `seed` and drawn in C order, so the noise of an element depends on the seed and its flat index only."""
    severity = _check_severity(severity)
    seed = _check_seed(seed)
    lin = np.asarray(lin, dtype=np.float64)
    if severity == 0:
        return lin.copy()
    sigma = SIGMA_N[severity] if sigma_n is None else float(sigma_n)
    if not math.isfinite(sigma) or sigma < 0:
        raise ValueError(f"sigma_n must be finite and >= 0, got {sigma_n!r}")
    out = apply_exposure(lin, EXPOSURE_K[severity])
    if sigma > 0.0:
        out = out + sigma * np.random.Generator(np.random.Philox(key=seed)).standard_normal(lin.shape)
    return np.clip(out, 0.0, 1.0)  # type: ignore[no-any-return]


def night(image: np.ndarray, severity: int, *, seed: int, sigma_n: float | None = None) -> CorruptionResult:
    """Night exposure and noise on an sRGB image."""
    severity = _check_severity(severity)
    image = _check_image(image)
    seed = _check_seed(seed)
    record = {"corruption": "night", "severity": severity, "seed": seed}
    if severity == 0:
        return CorruptionResult(image.copy(), record)
    return CorruptionResult(
        _from_linear(night_linear(_to_linear(image), severity, seed=seed, sigma_n=sigma_n), image), record
    )


# ----------------------------------------------------------------------------------------------------------------
# rain (FR-009-27)
# ----------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Streak:
    """A straight rain streak from (x0, y0) to (x1, y1) in pixel coordinates (x to the right, y downwards)."""

    x0: float
    y0: float
    x1: float
    y1: float


def _streak_pixels(s: Streak, height: int, width: int) -> np.ndarray:
    """Flat indices of the 1-px-wide digital line of a streak, clipped to the image.

    Points are taken from the start in steps of one pixel along the major axis (floor(major extent) + 1 of them, so a
    streak
    adds at most its length plus one pixel); each point is rounded to its pixel (pixel centres at integer
    coordinates), and
    consecutive points differ by at most one pixel in each axis, so the line is 8-connected.
    """
    dx, dy = s.x1 - s.x0, s.y1 - s.y0
    major = max(abs(dx), abs(dy))
    if major == 0.0:
        steps = np.zeros(1)
        ux = uy = 0.0
    else:
        steps = np.arange(0, math.floor(major) + 1, dtype=np.float64)
        ux, uy = dx / major, dy / major
    xs = np.rint(s.x0 + steps * ux).astype(np.int64)
    ys = np.rint(s.y0 + steps * uy).astype(np.int64)
    keep = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
    return ys[keep] * width + xs[keep]  # type: ignore[no-any-return]


def rasterise(streaks: Sequence[Streak], height: int, width: int) -> np.ndarray:
    """Boolean (height, width) mask: the union of the 1-px-wide lines of `streaks`, clipped to the image."""
    flat = np.zeros(height * width, dtype=bool)
    for s in streaks:
        flat[_streak_pixels(s, height, width)] = True
    return flat.reshape(height, width)


def rain_streaks(height: int, width: int, severity: int, *, seed: int) -> list[Streak]:
    """The streaks of one image, in drawing order, added until the covered fraction first reaches rho_s.

    Starts are uniform over the image, the length is l_s W / 1280 px, the angle from the vertical is one image angle
    theta ~ U(-15, 15) degrees plus a per-streak jitter ~ U(-2, 2) degrees.
    """
    severity = _check_severity(severity)
    seed = _check_seed(seed)
    if severity == 0:
        return []
    rng = np.random.Generator(np.random.Philox(key=seed))
    theta = float(rng.uniform(-_ANGLE_MAX_DEG, _ANGLE_MAX_DEG))
    length = RAIN_LEN_PX[severity] * width / _STREAK_REFERENCE_WIDTH
    target = RAIN_RHO[severity] * height * width
    covered = np.zeros(height * width, dtype=bool)
    count = 0
    streaks: list[Streak] = []
    for _ in range(100 * int(target) + 1000):  # a bound that is never reached: every streak covers new pixels
        x0, y0 = float(rng.uniform(0.0, width)), float(rng.uniform(0.0, height))
        angle = math.radians(theta + float(rng.uniform(-_JITTER_DEG, _JITTER_DEG)))
        s = Streak(x0, y0, x0 + length * math.sin(angle), y0 + length * math.cos(angle))
        idx = _streak_pixels(s, height, width)
        count += int(np.count_nonzero(~covered[idx]))
        covered[idx] = True
        streaks.append(s)
        if count >= target:
            return streaks
    raise RuntimeError("the rain streaks did not reach their coverage")  # pragma: no cover


def rain_mask(height: int, width: int, severity: int, *, seed: int) -> np.ndarray:
    """`rasterise(rain_streaks(...), height, width)`."""
    return rasterise(rain_streaks(height, width, severity, seed=seed), height, width)


def rain_linear(lin: np.ndarray, severity: int, *, seed: int) -> np.ndarray:
    """(1 - m) [c_s I + (1 - c_s) mean(I)] + m L_r in linear RGB; severity 0 returns a copy."""
    severity = _check_severity(severity)
    seed = _check_seed(seed)
    lin = np.asarray(lin, dtype=np.float64)
    if severity == 0:
        return lin.copy()
    m = rain_mask(lin.shape[0], lin.shape[1], severity, seed=seed)[..., None].astype(np.float64)
    mean = lin.mean(axis=(0, 1))
    c = RAIN_C[severity]
    return (1 - m) * (c * lin + (1 - c) * mean) + m * L_R  # type: ignore[no-any-return]


def rain(image: np.ndarray, severity: int, *, seed: int) -> CorruptionResult:
    """Rain streaks and contrast loss on an sRGB image."""
    severity = _check_severity(severity)
    image = _check_image(image)
    seed = _check_seed(seed)
    record = {"corruption": "rain", "severity": severity, "seed": seed}
    if severity == 0:
        return CorruptionResult(image.copy(), record)
    return CorruptionResult(_from_linear(rain_linear(_to_linear(image), severity, seed=seed), image), record)


# ----------------------------------------------------------------------------------------------------------------
# dispatcher
# ----------------------------------------------------------------------------------------------------------------
def apply_corruption(
    name: str, image: np.ndarray, severity: int, *, depth_m: np.ndarray | None = None, seed: int = 0
) -> CorruptionResult:
    """Apply the corruption `name` (dust, night or rain); `depth_m` is used by dust only, `seed` by night and rain."""
    if not isinstance(name, str) or name not in CORRUPTIONS:
        raise ValueError(f"corruption must be one of {CORRUPTIONS}, got {name!r}")
    if name == "dust":
        return dust(image, depth_m, severity)
    if name == "night":
        return night(image, severity, seed=seed)
    return rain(image, severity, seed=seed)
