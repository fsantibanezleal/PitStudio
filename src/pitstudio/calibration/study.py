"""Coverage study of the calibration arms, paired comparisons and gradient-reliability accounting (FR-011-24, FR-011-25,
SC-011-02, SC-011-05, SC-011-06, FR-011-50).

The study runs 50 synthetic-truth trials per arm: the truth mu_dagger of each trial is drawn once (uniform in [0.3, 0.8], seeded)
and the target theta* comes from a packing seed disjoint from every other seed; every arm receives the same trial. For each
arm the 95 % interval of FR-011-22 is formed at the arm's estimate, the coverage is reported with its Wilson interval, and
"better / faster / narrower" statements about two arms come only from the paired percentile bootstrap of the per-trial
differences (the decision rule of FR-000-05): otherwise "no significant difference".
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio.calibration.errors import InvalidCalibrationError
from pitstudio.calibration.interval import seed_ensemble_interval
from pitstudio.calibration.stats import wilson_interval as _wilson

COVERAGE_MIN = 0.90  # thresholds.yaml models.dem_calibration_coverage_min (SC-011-02)
TRUTH_RANGE = (0.3, 0.8)
SENTINEL = "no significant difference"


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval of k covering trials out of n."""
    if n < 1 or k < 0 or k > n:
        raise InvalidCalibrationError(f"need 0 <= k <= n and n >= 1, got k = {k}, n = {n}")
    z = statistics.NormalDist().inv_cdf(0.5 + confidence / 2.0)
    return _wilson(k, n, z=z)


def draw_truths(n: int, seed: int) -> np.ndarray:
    """n sliding-friction truths uniform in [0.3, 0.8] from a seeded generator."""
    return np.random.default_rng(seed).uniform(TRUTH_RANGE[0], TRUTH_RANGE[1], n)


@dataclass(frozen=True)
class BootstrapResult:
    mean_diff: float
    ci_lower: float
    ci_upper: float
    resamples: int


def _pairs(a: Sequence[float], b: Sequence[float]) -> np.ndarray:
    x, y = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if x.ndim != 1 or x.shape != y.shape:
        raise InvalidCalibrationError(f"paired samples must have the same length, got {x.shape} and {y.shape}")
    if x.size < 2:
        raise InvalidCalibrationError("at least 2 pairs are needed for a paired comparison")
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise InvalidCalibrationError("paired samples contain a non-finite value")
    return x - y


def paired_bootstrap(
    a: Sequence[float], b: Sequence[float], *, resamples: int = 10_000, seed: int, indices: np.ndarray | None = None
) -> BootstrapResult:
    """Percentile bootstrap (2.5th and 97.5th percentiles of the resampled means) of the paired differences a - b."""
    d = _pairs(a, b)
    if indices is None:
        if resamples < 1:
            raise InvalidCalibrationError("resamples must be at least 1")
        indices = np.random.default_rng(seed).integers(0, d.size, size=(resamples, d.size))
    means = d[np.asarray(indices)].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return BootstrapResult(mean_diff=float(d.mean()), ci_lower=float(lo), ci_upper=float(hi), resamples=int(means.size))


def compare_arms(
    a: Sequence[float],
    b: Sequence[float],
    *,
    name_a: str,
    name_b: str,
    metric: str,
    lower_is_better: bool = True,
    resamples: int = 10_000,
    seed: int,
) -> dict[str, Any]:
    """Decision rule: `a` (or `b`) is better only when the paired 95 % interval of a - b excludes 0 on its side."""
    res = paired_bootstrap(a, b, resamples=resamples, seed=seed)
    ci = (res.ci_lower, res.ci_upper)
    if lower_is_better:
        a_wins, b_wins = ci[1] < 0.0, ci[0] > 0.0
    else:
        a_wins, b_wins = ci[0] > 0.0, ci[1] < 0.0
    detail = f"paired difference {name_a} - {name_b} = {res.mean_diff:.4g}, 95 % percentile interval [{ci[0]:.4g}, {ci[1]:.4g}]"
    if a_wins or b_wins:
        winner, loser = (name_a, name_b) if a_wins else (name_b, name_a)
        sense = "lower" if lower_is_better else "higher"
        verdict = "a" if a_wins else "b"
        statement = f"{winner} has a {sense} {metric} than {loser}: {detail}."
    else:
        verdict = SENTINEL
        statement = f"{metric}: {SENTINEL} between {name_a} and {name_b}: {detail}."
    return {"verdict": verdict, "mean_diff": res.mean_diff, "ci": ci, "statement": statement}


def _stats(values: Sequence[float]) -> dict[str, float] | None:
    if not values:
        return None
    arr = np.asarray(values, dtype=np.float64)
    return {"mean": float(arr.mean()), "median": float(np.median(arr)), "max": float(arr.max())}


def summarise_arm(trials: Sequence[Mapping[str, Any]], *, parameter: int = 0, expected_trials: int | None = None) -> dict[str, Any]:
    """Coverage, counts and statistics of one arm's DC-011-04 documents; a partial set gives no coverage claim (FR-011-50)."""
    n = len(trials)
    if n == 0:
        raise InvalidCalibrationError("no trial to summarise")
    expected = n if expected_trials is None else expected_trials
    if n > expected:
        raise InvalidCalibrationError(f"{n} trials were given but the study names {expected}")
    params = [t["parameters"][parameter] for t in trials]
    covering = sum(1 for p in params if p.get("covers_truth") is True)
    errors = [abs(p["estimate"] - p["truth"]) for p in params if "truth" in p]
    widths = [
        p["interval"]["upper"] - p["interval"]["lower"]
        for p in params
        if p["interval"].get("lower") is not None and p["interval"].get("upper") is not None
    ]
    sims = [t["simulations"] for t in trials]
    walls = [t["wall_time_s"] for t in trials]
    complete = n == expected
    coverage = covering / n if complete else None
    return {
        "status": "complete" if complete else "partial",
        "missing": expected - n,
        "n_trials": n,
        "covering": covering,
        "coverage": coverage,
        "wilson": wilson_interval(covering, n) if complete else None,
        "not_identified": sum(1 for p in params if p.get("identification") == "not-identified"),
        "gradient_unreliable": sum(1 for t in trials if t.get("gradient_status") == "unreliable"),
        "abs_error": _stats(errors),
        "interval_width": _stats(widths),
        "simulations": {"mean": float(np.mean(sims)), "total": sum(sims)},
        "wall_time_s": {"mean": float(np.mean(walls)), "total": float(sum(walls))},
        "sc_011_02": (("pass" if covering / n >= COVERAGE_MIN else "fail") if complete else None),
    }


def gradient_reliability(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count the gradient-arm documents by gradient status and list every failed check (SC-011-06)."""
    docs = [d for d in results if d.get("arm") == "gradient"]
    failures = [
        {"trial_id": d["trial_id"], "iterate": c["iterate"], "failure": c["failure"]}
        for d in docs
        for c in d.get("gradient_check", [])
        if c.get("trusted") is not True
    ]
    reliable = [d for d in docs if d.get("gradient_status") == "reliable"]
    return {
        "trials": len(docs),
        "reliable": len(reliable),
        "unreliable": sum(1 for d in docs if d.get("gradient_status") == "unreliable"),
        "untrusted_used": sum(1 for d in reliable if any(c.get("trusted") is not True for c in d.get("gradient_check", []))),
        "failures": failures,
    }


# ------------------------------------------------------------------ the study driver


def _trial_seeds(index: int, offset: int, packing_seeds: int, interval_runs: int) -> dict[str, list[int]]:
    base = offset + index * 64
    cursor = iter(range(base, base + 64))
    return {
        "target": [next(cursor)],
        "optimisation": [next(cursor) for _ in range(packing_seeds)],
        "interval": [next(cursor) for _ in range(interval_runs)],
    }


def run_coverage_study(
    simulator: Any,
    arms: Mapping[str, Callable[[Any, dict[str, Any]], dict[str, Any]]],
    *,
    n_trials: int = 50,
    seed: int,
    packing_seeds: int = 2,
    interval_runs: int = 8,
) -> dict[str, Any]:
    """Run every arm on the same synthetic-truth trials and summarise each arm; see the module docstring."""
    if n_trials < 2:
        raise InvalidCalibrationError(f"a study needs at least 2 trials, got {n_trials}")
    if 2 + packing_seeds + interval_runs > 64:
        raise InvalidCalibrationError("too many seeds per trial")
    truths = draw_truths(n_trials, seed)
    offset = (seed % 1_000_000) * 4_000
    trials = []
    for j in range(n_trials):
        seeds = _trial_seeds(j, offset, packing_seeds, interval_runs)
        mu_true = float(truths[j])
        trials.append(
            {
                "index": j,
                "mu_true": mu_true,
                "theta_star": float(simulator.theta(mu_true, seeds["target"][0])),
                "seeds": seeds,
            }
        )
    out: dict[str, Any] = {"truths": [float(t) for t in truths], "arms": {}}
    for name, arm in arms.items():
        records = []
        for trial in trials:
            result = arm(simulator, trial)
            records.append(_record(name, simulator, trial, result, packing_seeds))
        out["arms"][name] = {"trials": records, "summary": summarise_arm(records, expected_trials=n_trials)}
    return out


def _record(arm: str, simulator: Any, trial: Mapping[str, Any], result: Mapping[str, Any], packing_seeds: int) -> dict[str, Any]:
    mu_hat = float(result["mu_hat"])
    iv = seed_ensemble_interval(
        simulator.theta, mu_hat, interval_seeds=trial["seeds"]["interval"], n_packing_seeds=packing_seeds
    )
    unreliable = result.get("gradient_status") == "unreliable"
    param = {
        "name": "sliding_friction",
        "truth": trial["mu_true"],
        "estimate": mu_hat,
        "identification": "identified" if iv.identified else "not-identified",
        "covers_truth": bool(iv.covers(trial["mu_true"]) and not unreliable),
        "interval": {
            "level": 0.95,
            "lower": iv.lower,
            "upper": iv.upper,
            "t_quantile": iv.t_quantile,
            "sigma_theta_deg": iv.sigma_theta_deg,
            "slope_deg_per_unit": iv.slope_deg_per_unit,
            "slope_interval_deg_per_unit": list(iv.slope_interval_deg_per_unit),
        },
    }
    record: dict[str, Any] = {
        "trial_id": f"{arm}-{trial['index']:03d}",
        "arm": arm,
        "simulations": int(result["simulations"]),
        "wall_time_s": float(result["wall_time_s"]),
        "parameters": [param],
    }
    if "gradient_status" in result:
        record["gradient_status"] = result["gradient_status"]
    return record


__all__ = [
    "BootstrapResult",
    "compare_arms",
    "draw_truths",
    "gradient_reliability",
    "paired_bootstrap",
    "run_coverage_study",
    "summarise_arm",
    "wilson_interval",
]
