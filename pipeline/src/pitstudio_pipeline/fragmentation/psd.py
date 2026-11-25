"""Image particle-size distribution and its Swebrec fit (spec 012, FR-012-24 to FR-012-27, Q-1).

Size basis: every instance k of area A_k (pixels) has the equivalent-circle diameter d_k = 2 sqrt(A_k / pi) in pixels of
the 512 x 512 image; the passing fraction at size x is the area of all instances with d <= x over the total instance
area (area-weighted, equal sizes merged). The pixel scale of the real images is not recorded, so every size of this
module is in pixels unless the caller converts it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from minephys import blasting
from scipy.optimize import least_squares

MIN_INSTANCES = 3
B_BOUNDS = (0.05, 50.0)
X50_REL_BOUNDS = (1e-6, 1.0 - 1e-6)
SIGNIFICANT_PASSING = (0.2, 0.5, 0.8)


@dataclass(frozen=True)
class Psd:
    """Area-weighted passing points: distinct ascending sizes (px) and their cumulative area fractions."""

    sizes: np.ndarray
    passing: np.ndarray
    n_instances: int
    total_area_px: float


@dataclass(frozen=True)
class SwebrecFit:
    """Result of the Swebrec fit: status "ok" with x50, b and x_max, or "no-fit" with x50 = None."""

    status: str
    x50: float | None
    b: float | None
    x_max: float | None
    rmse: float | None


def instance_areas(instances: np.ndarray) -> np.ndarray:
    """Pixel area of each instance id 1..max of a label image (0 = background); empty ids are dropped."""
    labels = np.asarray(instances)
    if labels.ndim != 2 or not np.issubdtype(labels.dtype, np.integer) or labels.min(initial=0) < 0:
        raise ValueError("instances must be a 2-D non-negative integer label image")
    counts = np.bincount(labels.ravel())[1:]
    return counts[counts > 0].astype(np.float64)


def image_psd(areas: Sequence[float] | np.ndarray) -> Psd:
    """FR-012-24: the area-weighted passing points of instance areas (px). ValueError for a bad area."""
    a = np.asarray(areas, dtype=np.float64)
    if a.ndim != 1 or a.size == 0 or not np.all(np.isfinite(a)) or np.any(a <= 0):
        raise ValueError("areas must be a non-empty 1-D array of finite positive values")
    d = 2.0 * np.sqrt(a / math.pi)
    sizes, inverse = np.unique(d, return_inverse=True)
    weight = np.bincount(inverse, weights=a)
    passing = np.cumsum(weight) / weight.sum()
    passing[-1] = 1.0
    return Psd(sizes, passing, int(a.size), float(a.sum()))


def weighted_quantile(psd: Psd, q: float) -> float:
    """Q-1: x_1 if F_1 >= q, else the linear interpolation between (F_{j-1}, x_{j-1}) and (F_j, x_j), first F_j >= q."""
    if not 0.0 < q < 1.0:
        raise ValueError(f"q must lie in (0, 1), got {q!r}")
    f, x = psd.passing, psd.sizes
    j = int(np.argmax(f >= q))
    if j == 0:
        return float(x[0])
    return float(x[j - 1] + (q - f[j - 1]) / (f[j] - f[j - 1]) * (x[j] - x[j - 1]))


def oversize_share(psd: Psd, limit: float) -> float:
    """Area share of instances larger than `limit` (px): 1 - P(limit) with the step passing function."""
    if not (math.isfinite(limit) and limit > 0):
        raise ValueError(f"limit must be finite and positive, got {limit!r}")
    below = psd.sizes <= limit
    return float(1.0 - (psd.passing[below][-1] if below.any() else 0.0))


def _check_fit_inputs(sizes: np.ndarray, passing: np.ndarray) -> None:
    if sizes.ndim != 1 or passing.ndim != 1 or sizes.size != passing.size:
        raise ValueError("arguments sizes and passing must be 1-D arrays of the same length")
    if sizes.size < MIN_INSTANCES:
        raise ValueError(f"argument sizes needs at least {MIN_INSTANCES} points, got {sizes.size}")
    if not np.all(np.isfinite(sizes)) or np.any(sizes <= 0) or np.any(np.diff(sizes) <= 0):
        raise ValueError("argument sizes must be finite, positive and strictly increasing")
    if not np.all(np.isfinite(passing)) or np.any(passing < 0) or np.any(passing > 1) or np.any(np.diff(passing) < 0):
        raise ValueError("argument passing must lie in [0, 1] and not decrease")


def fit_swebrec(sizes: Sequence[float] | np.ndarray, passing: Sequence[float] | np.ndarray) -> SwebrecFit:
    """FR-012-26: least-squares (x50, b) of the Swebrec function with x_max = the largest size; status "no-fit" when the
    optimiser does not converge. ValueError (FR-012-27) names the offending argument."""
    x = np.asarray(sizes, dtype=np.float64)
    p = np.asarray(passing, dtype=np.float64)
    _check_fit_inputs(x, p)
    x_max = float(x[-1])
    start = weighted_quantile(Psd(x, p, int(x.size), 1.0), 0.5) if p[0] < 0.5 else float(x[0])
    start = min(max(start, X50_REL_BOUNDS[0] * x_max), X50_REL_BOUNDS[1] * x_max)
    xs, ps = x[:-1], p[:-1]

    def residual(theta: np.ndarray) -> np.ndarray:
        return np.asarray(blasting.swebrec_passing(xs, theta[0], x_max, theta[1])) - ps

    try:
        result = least_squares(
            residual,
            x0=[start, 2.0],
            bounds=([X50_REL_BOUNDS[0] * x_max, B_BOUNDS[0]], [X50_REL_BOUNDS[1] * x_max, B_BOUNDS[1]]),
            method="trf",
            xtol=1e-12,
            ftol=1e-12,
            gtol=1e-12,
        )
    except ValueError:
        return SwebrecFit("no-fit", None, None, None, None)
    if not result.success or not np.all(np.isfinite(result.x)):
        return SwebrecFit("no-fit", None, None, None, None)
    return SwebrecFit("ok", float(result.x[0]), float(result.x[1]), x_max, float(math.sqrt(np.mean(result.fun**2))))


def fit_instances(areas: Sequence[float] | np.ndarray) -> tuple[Psd | None, SwebrecFit]:
    """The PSD and the fit of an instance set; fewer than 3 instances or a bad area gives `no-fit` (FR-012-25)."""
    a = np.asarray(areas, dtype=np.float64)
    if a.ndim != 1 or a.size < MIN_INSTANCES or not np.all(np.isfinite(a)) or np.any(a <= 0):
        return None, SwebrecFit("no-fit", None, None, None, None)
    psd = image_psd(a)
    if psd.sizes.size < MIN_INSTANCES:
        return psd, SwebrecFit("no-fit", None, None, None, None)
    return psd, fit_swebrec(psd.sizes, psd.passing)
