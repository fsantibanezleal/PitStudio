"""CMA-ES calibration arm (FR-011-20, FR-011-21): gradient-free minimisation of the repose loss on the common budget.

Minimises L(mu) = mean over the S optimisation seeds of (theta(mu, seed) - theta*)^2 with the `cma` package (pycma,
BSD-3-Clause):
start mu0, sigma0 = 0.1, the default population of one dimension (4 + floor(3 ln 1) = 4), the box bounds of FR-011-17.
A generation
costs population x S forward simulations; the arm stops when L <= (0.1 deg)^2 or when another generation would exceed
the budget
of 60 forward-equivalent simulations (the budget is never exceeded), and returns the best evaluated candidate.
"""

from __future__ import annotations

import time
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # pycma warns that matplotlib is absent (plotting is not used)
    import cma

from pitstudio.calibration.errors import InvalidCalibrationError

SIGMA0 = 0.1


@dataclass
class ArmResult:
    mu_hat: float
    best_loss: float
    simulations: int
    wall_time_s: float
    stop_reason: str  # "loss-tolerance" | "budget"
    path: list[float]
    evaluations: list[tuple[float, float]]
    population: int = 0
    sigma0: float = SIGMA0
    gradients: list[float] = field(default_factory=list)
    thetas: dict[float, list[float]] = field(default_factory=dict)  # per evaluated mu: theta of each optimisation seed


def run_cmaes_arm(
    simulator: Any,
    *,
    theta_star: float,
    packing_seeds: Sequence[int],
    mu0: float = 0.55,
    bounds: tuple[float, float] = (0.1, 1.0),
    budget: int = 60,
    sigma0: float = SIGMA0,
    rng_seed: int = 0,
    loss_tolerance_deg: float = 0.1,
) -> ArmResult:
    """Run the arm on `simulator.theta(mu, seed)`; see the module docstring."""
    seeds = list(packing_seeds)
    if not seeds:
        raise InvalidCalibrationError("at least one optimisation seed is needed")
    started = time.perf_counter()
    lo, hi = float(bounds[0]), float(bounds[1])
    options: dict[str, Any] = {
        "bounds": [[lo], [hi]],
        "seed": int(rng_seed) + 1,  # pycma treats a seed of 0 as "time-based"; the arm must be reproducible
        "verbose": -9,
        "verb_log": 0,
        "maxiter": 10**9,
        # pycma 4.5.0 raises "not yet initialized (dimension needed)" in one dimension as soon as the bounded search
        # tries to cap its standard deviation at 0.3 of the range; the cap is switched off, the box bounds stay.
        "maxstd": float("inf"),
    }
    es = cma.CMAEvolutionStrategy([float(mu0)], float(sigma0), options)
    population = int(es.popsize)
    if budget < population * len(seeds):
        raise InvalidCalibrationError(
            f"budget {budget} cannot pay one generation ({population} candidates x {len(seeds)} seeds)"
        )
    tolerance = loss_tolerance_deg**2
    evaluations: list[tuple[float, float]] = []
    thetas: dict[float, list[float]] = {}
    path = [float(mu0)]
    simulations = 0
    stop_reason = "budget"
    while simulations + population * len(seeds) <= budget:
        candidates = es.ask()
        losses = []
        for x in candidates:
            mu = float(x[0])
            values = [float(simulator.theta(mu, s)) for s in seeds]
            simulations += len(seeds)
            loss = float(np.mean([(v - theta_star) ** 2 for v in values]))
            evaluations.append((mu, loss))
            thetas[mu] = values
            losses.append(loss)
        es.tell(candidates, losses)
        path.append(float(es.result.xfavorite[0]))
        if min(losses) <= tolerance:
            stop_reason = "loss-tolerance"
            break
    best_mu, best_loss = min(evaluations, key=lambda e: e[1])
    return ArmResult(
        mu_hat=best_mu,
        best_loss=best_loss,
        simulations=simulations,
        wall_time_s=float(time.perf_counter() - started),
        stop_reason=stop_reason,
        path=path,
        evaluations=evaluations,
        population=population,
        sigma0=float(sigma0),
        thetas=thetas,
    )


Objective = Callable[[Sequence[float]], float]


def minimise_cmaes(
    objective: Objective,
    x0: Sequence[float],
    bounds: tuple[Sequence[float], Sequence[float]],
    *,
    sigma0: float,
    rng_seed: int,
    max_evaluations: int,
    tolerance: float,
) -> tuple[list[float], float, int, str, int]:
    """CMA-ES in any dimension: returns (best x, best loss, evaluations, stop reason, population)."""
    es = cma.CMAEvolutionStrategy(
        list(x0),
        float(sigma0),
        {
            "bounds": [list(bounds[0]), list(bounds[1])],
            "seed": int(rng_seed) + 1,
            "verbose": -9,
            "verb_log": 0,
            "maxiter": 10**9,
        },
    )
    population = int(es.popsize)
    evaluations = 0
    best_x: list[float] = list(x0)
    best_loss = float("inf")
    reason = "budget"
    while evaluations + population <= max_evaluations:
        candidates = es.ask()
        losses = [float(objective(x)) for x in candidates]
        evaluations += population
        for x, loss in zip(candidates, losses, strict=True):
            if loss < best_loss:
                best_x, best_loss = [float(v) for v in x], loss
        es.tell(candidates, losses)
        if best_loss <= tolerance:
            reason = "loss-tolerance"
            break
    return best_x, best_loss, evaluations, reason, population
