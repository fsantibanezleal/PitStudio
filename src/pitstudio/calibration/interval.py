"""Seed-ensemble delta interval of a calibrated parameter (FR-011-22, P-011-09).

Both optimisers form the same 95 % interval: R forward simulations at mu_hat - h, mu_hat and mu_hat + h (h = 0.05 mu_hat), one
per interval seed (seeds disjoint from the target and optimisation seeds). sigma_hat is the sample standard deviation (R - 1
degrees of freedom) of the repose angle at mu_hat, g_hat the central-difference slope of the seed means, and

    CI = mu_hat +/- t_{0.975, R-1} * sigma_hat * sqrt(1 + 1/S) / |g_hat|.

The slope is judged on the paired per-seed slopes g_r = (theta_r(mu_hat + h) - theta_r(mu_hat - h)) / (2 h) (the same packing
seed at both ends): when g_hat +/- t * sd(g_r) / sqrt(R) contains 0 the parameter is "not identified", the interval has no
bounds and it never covers (a non-identified trial counts against coverage).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from pitstudio.calibration.errors import InvalidCalibrationError
from pitstudio.calibration.stats import student_t_quantile

H_FRACTION = 0.05


@dataclass(frozen=True)
class IntervalResult:
    mu_hat: float
    h: float
    sigma_theta_deg: float
    slope_deg_per_unit: float
    slope_interval_deg_per_unit: tuple[float, float]
    t_quantile: float
    half_width: float
    lower: float | None
    upper: float | None
    identified: bool
    simulations: int

    def covers(self, truth: float) -> bool:
        """True iff the interval is bounded (identified) and contains `truth`."""
        return self.identified and self.lower is not None and self.upper is not None and self.lower <= truth <= self.upper


def seed_ensemble_interval(
    simulate: Callable[[float, int], float],
    mu_hat: float,
    *,
    interval_seeds: Sequence[int],
    n_packing_seeds: int,
) -> IntervalResult:
    """Run the 3 R forward simulations and form the interval; see the module docstring."""
    seeds = list(interval_seeds)
    if len(seeds) < 2:
        raise InvalidCalibrationError(f"at least 2 interval seeds are needed, got {len(seeds)}")
    if len(set(seeds)) != len(seeds):
        raise InvalidCalibrationError("interval seeds must be distinct")
    if not isinstance(mu_hat, int | float | np.floating) or not math.isfinite(mu_hat) or mu_hat <= 0:
        raise InvalidCalibrationError(f"mu_hat must be a positive finite number, got {mu_hat!r}")
    if not isinstance(n_packing_seeds, int | np.integer) or n_packing_seeds < 1:
        raise InvalidCalibrationError(f"n_packing_seeds must be at least 1, got {n_packing_seeds!r}")
    h = H_FRACTION * float(mu_hat)
    columns: dict[str, list[float]] = {"minus": [], "centre": [], "plus": []}
    for key, mu in (("minus", mu_hat - h), ("centre", float(mu_hat)), ("plus", mu_hat + h)):
        for seed in seeds:
            value = float(simulate(mu, seed))
            if not math.isfinite(value):
                raise InvalidCalibrationError(f"the simulator returned a non-finite repose angle (mu = {mu}, seed = {seed})")
            columns[key].append(value)
    minus, centre, plus = (np.asarray(columns[k]) for k in ("minus", "centre", "plus"))
    r = len(seeds)
    sigma = float(np.std(centre, ddof=1))
    paired = (plus - minus) / (2.0 * h)
    slope = float((plus.mean() - minus.mean()) / (2.0 * h))
    t = student_t_quantile(0.975, r - 1)
    slope_half = t * float(np.std(paired, ddof=1)) / math.sqrt(r)
    slope_interval = (slope - slope_half, slope + slope_half)
    identified = not (slope_interval[0] <= 0.0 <= slope_interval[1])
    if identified:
        half = t * sigma * math.sqrt(1.0 + 1.0 / n_packing_seeds) / abs(slope)
        lower, upper = float(mu_hat) - half, float(mu_hat) + half
    else:
        half, lower, upper = math.inf, None, None
    return IntervalResult(
        mu_hat=float(mu_hat),
        h=h,
        sigma_theta_deg=sigma,
        slope_deg_per_unit=slope,
        slope_interval_deg_per_unit=slope_interval,
        t_quantile=t,
        half_width=half,
        lower=lower,
        upper=upper,
        identified=identified,
        simulations=3 * r,
    )
