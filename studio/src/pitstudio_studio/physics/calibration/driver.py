"""Calibration driver: requests, one DC-011-04 document per arm, interval, gradient checks, OOM fallback, literature
targets.

`calibrate(request, simulator)` validates the request (FR-011-30, before any simulation), runs one arm (the gradient
arm of
`tape.run_gradient_arm` or the CMA-ES arm of `cmaes.run_cmaes_arm`), then forms the 95 % seed-ensemble interval of
FR-011-22 at the best
evaluated mu_hat and, for the gradient arm, checks the tape gradient at the first and the final iterate against a 4 + 4
run finite
difference (FR-011-23, outside the budget); the result is a document of `calibration-result.schema.json` (FR-011-26).

Simulator protocol (see tests/_calib_fake.py): `solver`, `differentiable`, `particle_count`, `free_device_memory_bytes`,
`theta(mu, seed)` (smooth repose angle, deg), `hard_theta(mu, seed)` (hard observable of the same simulation, no extra
run),
`theta_and_grad(mu, seed)`, and for the optional secondary arm `observables(mu_s, mu_r, seed) -> (theta_deg,
discharge_kg_per_s)`.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pitstudio.calibration.errors import InvalidCalibrationError
from pitstudio.calibration.gradient_gate import check_gradient
from pitstudio.calibration.interval import IntervalResult, seed_ensemble_interval
from pitstudio.surrogate_manifests import LABEL
from pitstudio.surrogate_runtime import run_with_oom_fallback
from pitstudio_studio.physics.calibration import cmaes, tape

NOT_DIFFERENTIABLE = "not differentiable — gradient-free only"
REQUIRED_LITERATURE_MATERIALS = ("crushed-gravel", "dry-sand")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ROW_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MU_RANGE = (0.05, 2.0)
SEED_MAX = 2**32 - 1
MEMORY_FRACTION = 0.8
H_FRACTION = 0.05
SIGMA0 = 0.1
LOSS_TOLERANCE_DEG = 0.1
REPOSE_SCALE_DEG = 1.0  # secondary arm: (theta - theta*)^2 / (1 deg)^2
DISCHARGE_SCALE = 0.05  # ((Q - Q*) / Q*)^2 / 0.05^2
SYNTHETIC_MAX_PARTICLES = 5000
LITERATURE_MAX_PARTICLES = 20000
SEED_ROLES = ("target", "optimisation", "interval", "gradient_check")


@dataclass
class CalibrationRun:
    results: list[dict[str, Any]] = field(default_factory=list)
    refusals: list[dict[str, str]] = field(default_factory=list)


# ------------------------------------------------------------------ request validation (FR-011-30)


def _fail(key: str, reason: str) -> InvalidCalibrationError:
    return InvalidCalibrationError(f"{key}: {reason}")


def _number(value: Any) -> bool:
    return (
        isinstance(value, int | float | np.floating | np.integer)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _integer(value: Any) -> bool:
    return isinstance(value, int | np.integer) and not isinstance(value, bool)


def _check_range(key: str, value: Any, lo: float, hi: float) -> float:
    if not _number(value) or not lo <= value <= hi:
        raise _fail(key, f"must be a finite number in [{lo:g}, {hi:g}], got {value!r}")
    return float(value)


def _check_bounds(key: str, bounds: Any) -> tuple[float, float]:
    if not isinstance(bounds, Sequence) or isinstance(bounds, str) or len(bounds) != 2:
        raise _fail(key, f"must be [lower, upper], got {bounds!r}")
    lo, hi = bounds
    if not (_number(lo) and _number(hi)) or not MU_RANGE[0] <= lo < hi <= MU_RANGE[1]:
        raise _fail(key, f"must satisfy {MU_RANGE[0]} <= lower < upper <= {MU_RANGE[1]}, got {list(bounds)}")
    return float(lo), float(hi)


def validate_request(request: Mapping[str, Any], simulator: Any) -> dict[str, Any]:
    """Return a normalised copy of the request or raise InvalidCalibrationError naming the key, before any
    simulation."""
    req = dict(request)
    if req.get("kind") not in ("synthetic-trial", "literature-target"):
        raise _fail("kind", f"must be 'synthetic-trial' or 'literature-target', got {req.get('kind')!r}")
    if req.get("arm") not in ("gradient", "cma-es"):
        raise _fail("arm", f"must be 'gradient' or 'cma-es', got {req.get('arm')!r}")
    if not isinstance(req.get("trial_id"), str) or not SLUG.fullmatch(req["trial_id"]):
        raise _fail(
            "trial_id", f"must be a slug of lower-case letters, digits and hyphens, got {req.get('trial_id')!r}"
        )
    target = req.get("target")
    if not isinstance(target, Mapping):
        raise _fail("target", "must be an object with theta_deg")
    _check_range("theta_deg", target.get("theta_deg"), 5.0, 60.0)
    req["mu0"] = _check_range("mu0", req.get("mu0"), *MU_RANGE)
    lo, hi = _check_bounds("bounds", req.get("bounds"))
    req["bounds"] = [lo, hi]
    if not lo <= req["mu0"] <= hi:
        raise _fail("mu0", f"must lie inside bounds {[lo, hi]}, got {req['mu0']}")
    if not _integer(req.get("budget")) or not 1 <= req["budget"] <= 10_000:
        raise _fail("budget", f"must be an integer in [1, 10000], got {req.get('budget')!r}")
    if not _integer(req.get("window_steps")) or not 100 <= req["window_steps"] <= 5000:
        raise _fail("window_steps", f"must be an integer in [100, 5000], got {req.get('window_steps')!r}")
    if not _integer(req.get("settling_steps")) or req["settling_steps"] < 0:
        raise _fail("settling_steps", f"must be a non-negative integer, got {req.get('settling_steps')!r}")
    for key in ("packing_seeds", "interval_runs"):
        if not _integer(req.get(key)) or req[key] < 2:
            raise _fail(key, f"must be an integer >= 2, got {req.get(key)!r}")
    limit = SYNTHETIC_MAX_PARTICLES if req["kind"] == "synthetic-trial" else LITERATURE_MAX_PARTICLES
    if not _integer(req.get("particle_count")) or not 1 <= req["particle_count"] <= limit:
        raise _fail(
            "particle_count",
            f"must be an integer in [1, {limit}] for a {req['kind']}, got {req.get('particle_count')!r}",
        )
    seeds = _check_seeds(req)
    req["seeds"] = seeds
    if getattr(simulator, "solver", None) not in ("warp-dem", "newton-mpm"):
        raise _fail("solver", f"the simulator must name its solver, got {getattr(simulator, 'solver', None)!r}")
    if req.get("secondary_arm"):
        _check_secondary(req)
    if req["kind"] == "synthetic-trial":
        truth = req.get("truth")
        if not isinstance(truth, Mapping) or "sliding_friction" not in truth:
            raise _fail("truth", "a synthetic trial needs truth.sliding_friction")
        _check_range("truth.sliding_friction", truth["sliding_friction"], *MU_RANGE)
    if req["arm"] == "gradient":
        if not getattr(simulator, "differentiable", False):
            raise InvalidCalibrationError(NOT_DIFFERENTIABLE)
        estimate = tape.tape_memory_bytes(req["particle_count"], req["window_steps"])
        free = float(simulator.free_device_memory_bytes)
        if estimate > MEMORY_FRACTION * free:
            raise _fail(
                "memory",
                f"the estimated tape memory {estimate} B exceeds {MEMORY_FRACTION:.0%} of the free device memory "
                f"({free:.0f} B)",
            )
        req["adam_lr"] = _check_range("adam_lr", req.get("adam_lr", 0.02), 1e-6, 10.0)
    return req


def _check_seeds(req: Mapping[str, Any]) -> dict[str, list[int]]:
    seeds = req.get("seeds")
    if not isinstance(seeds, Mapping):
        raise _fail("seeds", "must map target, optimisation, interval (and gradient_check) to lists of integers")
    out: dict[str, list[int]] = {}
    for role in SEED_ROLES:
        values = seeds.get(role)
        if values is None and role == "gradient_check":
            if req["arm"] == "gradient":
                raise _fail("seeds.gradient_check", "the gradient arm needs 4 gradient-check seeds")
            continue
        if not isinstance(values, Sequence) or isinstance(values, str) or len(values) == 0:
            raise _fail(f"seeds.{role}", "must be a non-empty list of integers")
        if not all(_integer(v) and 0 <= v <= SEED_MAX for v in values):
            raise _fail(f"seeds.{role}", f"every seed must be an integer in [0, {SEED_MAX}], got {list(values)}")
        out[role] = [int(v) for v in values]
    flat = [s for role in out for s in out[role]]
    if len(flat) != len(set(flat)):
        raise _fail("seeds", "the seed sets must be pairwise disjoint and free of repeats")
    if len(out["optimisation"]) != req["packing_seeds"]:
        raise _fail(
            "seeds.optimisation", f"needs {req['packing_seeds']} seeds (packing_seeds), got {len(out['optimisation'])}"
        )
    if len(out["interval"]) != req["interval_runs"]:
        raise _fail("seeds.interval", f"needs {req['interval_runs']} seeds (interval_runs), got {len(out['interval'])}")
    if req["arm"] == "gradient" and len(out.get("gradient_check", [])) != 4:
        raise _fail("seeds.gradient_check", "the gradient arm needs exactly 4 gradient-check seeds")
    return out


def _check_secondary(req: dict[str, Any]) -> None:
    if req["arm"] != "cma-es":
        raise _fail("arm", "the secondary (sliding, rolling) arm is gradient-free: use 'cma-es'")
    q = req["target"].get("discharge_rate_kg_per_s")
    if not _number(q) or q <= 0:
        raise _fail("discharge_rate_kg_per_s", f"the secondary arm needs a positive finite discharge target, got {q!r}")
    lo, hi = _check_bounds("rolling_bounds", req.get("rolling_bounds"))
    req["rolling_bounds"] = [lo, hi]
    req["mu0_rolling"] = _check_range("mu0_rolling", req.get("mu0_rolling"), lo, hi)
    if req["kind"] == "synthetic-trial":
        truth = req.get("truth")
        if not isinstance(truth, Mapping) or "rolling_friction" not in truth:
            raise _fail("truth", "the secondary arm of a synthetic trial needs truth.rolling_friction")
        _check_range("truth.rolling_friction", truth["rolling_friction"], *MU_RANGE)


# ------------------------------------------------------------------ the documents


def _interval_block(iv: IntervalResult) -> dict[str, Any]:
    return {
        "level": 0.95,
        "lower": iv.lower,
        "upper": iv.upper,
        "t_quantile": iv.t_quantile,
        "sigma_theta_deg": iv.sigma_theta_deg,
        "slope_deg_per_unit": iv.slope_deg_per_unit,
        "slope_interval_deg_per_unit": [float(v) for v in iv.slope_interval_deg_per_unit],
    }


def _parameter(
    name: str,
    req: Mapping[str, Any],
    *,
    start: float,
    bounds: Sequence[float],
    estimate: float,
    iv: IntervalResult,
    truth: float | None,
    cover_ok: bool,
) -> dict[str, Any]:
    width = (iv.upper - iv.lower) if iv.identified and iv.lower is not None and iv.upper is not None else None
    if not iv.identified:
        identification = "not-identified"
    elif width is not None and width > 0.5 * (bounds[1] - bounds[0]):
        identification = "weakly-identified"
    else:
        identification = "identified"
    out: dict[str, Any] = {
        "name": name,
        "start": float(start),
        "bounds": [float(bounds[0]), float(bounds[1])],
        "estimate": float(estimate),
        "fd_step": float(iv.h),
        "interval": _interval_block(iv),
        "identification": identification,
    }
    if req["kind"] == "synthetic-trial" and truth is not None:
        out["truth"] = float(truth)
        out["covers_truth"] = bool(cover_ok and iv.covers(truth))
    return out


def _target_block(req: Mapping[str, Any]) -> dict[str, Any]:
    target = req["target"]
    keys = ("theta_deg", "packing_seed", "discharge_rate_kg_per_s", "material", "knowledge_row", "verification")
    return {k: target[k] for k in keys if k in target}


def _base_document(
    req: Mapping[str, Any],
    simulator: Any,
    *,
    parameters: list[dict[str, Any]],
    loss: dict[str, Any],
    run: Mapping[str, Any],
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "kind": req["kind"],
        "arm": req["arm"],
        "trial_id": req["trial_id"],
        "solver": simulator.solver,
        "solver_version": str(req.get("solver_version", "unspecified")),
        "secondary_arm": bool(req.get("secondary_arm", False)),
        "particle_count": int(req["particle_count"]),
        "oom_fallback": False,
        "target": _target_block(req),
        "parameters": parameters,
        "loss": loss,
        "window_steps": int(req["window_steps"]),
        "settling_steps": int(req["settling_steps"]),
        "packing_seeds": int(req["packing_seeds"]),
        "interval_runs": int(req["interval_runs"]),
        "seeds": {k: list(v) for k, v in req["seeds"].items()},
        "budget_simulations": int(req["budget"]),
        "simulations": int(run["simulations"]),
        "interval_simulations": int(run["interval_simulations"]),
        "check_simulations": int(run["check_simulations"]),
        "stop_reason": run["stop_reason"],
        "wall_time_s": float(run["wall_time_s"]),
        "deterministic_accumulation": bool(run["deterministic"]),
        "label": LABEL,
    }
    if req.get("fixture") is True:
        doc["fixture"] = True
    return doc


def calibrate(request: Mapping[str, Any], simulator: Any) -> dict[str, Any]:
    """Run one calibration (one arm) and return its DC-011-04 document; the request is not modified."""
    req = validate_request(request, simulator)
    started = time.perf_counter()
    if req.get("secondary_arm"):
        return _calibrate_secondary(req, simulator, started)
    seeds = req["seeds"]
    theta_star = float(req["target"]["theta_deg"])
    bounds = (req["bounds"][0], req["bounds"][1])
    if req["arm"] == "cma-es":
        arm = cmaes.run_cmaes_arm(
            simulator,
            theta_star=theta_star,
            packing_seeds=seeds["optimisation"],
            mu0=req["mu0"],
            bounds=bounds,
            budget=req["budget"],
            sigma0=SIGMA0,
            rng_seed=int(req.get("cma_seed", 0)),
            loss_tolerance_deg=LOSS_TOLERANCE_DEG,
        )
    else:
        arm = tape.run_gradient_arm(
            simulator,
            theta_star=theta_star,
            packing_seeds=seeds["optimisation"],
            mu0=req["mu0"],
            bounds=bounds,
            budget=req["budget"],
            adam_lr=req["adam_lr"],
            loss_tolerance_deg=LOSS_TOLERANCE_DEG,
        )
    mu_hat = arm.mu_hat
    thetas = arm.thetas[mu_hat]
    smooth = float(np.mean(thetas))
    hard = float(np.mean([simulator.hard_theta(mu_hat, s) for s in seeds["optimisation"]]))
    checks: list[dict[str, Any]] = []
    check_simulations = 0
    if req["arm"] == "gradient":
        for label, mu_i, tape_gradient in (
            ("first", arm.path[0], arm.gradients[0]),
            ("final", arm.path[-1], arm.gradients[-1]),
        ):
            record = _gradient_check(simulator, label, mu_i, tape_gradient, seeds["gradient_check"], theta_star)
            checks.append(record)
            check_simulations += 2 * len(seeds["gradient_check"])
    unreliable = any(not c["trusted"] for c in checks)
    iv = seed_ensemble_interval(
        simulator.theta, mu_hat, interval_seeds=seeds["interval"], n_packing_seeds=req["packing_seeds"]
    )
    truth = req["truth"]["sliding_friction"] if req["kind"] == "synthetic-trial" else None
    parameter = _parameter(
        "sliding_friction",
        req,
        start=req["mu0"],
        bounds=req["bounds"],
        estimate=mu_hat,
        iv=iv,
        truth=truth,
        cover_ok=not unreliable,
    )
    loss = {
        "observable": "smooth-envelope",
        "softmax_beta_per_d": 10,
        "bin_width_d": 2,
        "bin_range_pct": [20, 80],
        "terms": [{"name": "repose", "weight": 1.0, "value": float(arm.best_loss)}],
        "total": float(arm.best_loss),
        "smooth_theta_deg": smooth,
        "hard_theta_deg": hard,
    }
    run = {
        "simulations": arm.simulations,
        "interval_simulations": iv.simulations,
        "check_simulations": check_simulations,
        "stop_reason": arm.stop_reason,
        "wall_time_s": time.perf_counter() - started,
        "deterministic": req["arm"] == "gradient" or bool(getattr(simulator, "deterministic_accumulation", False)),
    }
    doc = _base_document(req, simulator, parameters=[parameter], loss=loss, run=run)
    if req["arm"] == "gradient":
        doc["gradient_check"] = checks
        doc["gradient_status"] = "unreliable" if unreliable else "reliable"
    else:
        doc["cmaes"] = {"sigma0": SIGMA0, "population": arm.population, "cma_version": _cma_version()}
    return doc


def _cma_version() -> str:
    try:
        import cma

        return str(cma.__version__)
    except Exception:  # pragma: no cover - cma is a locked dependency of the studio
        return "unknown"


def _gradient_check(
    simulator: Any, label: str, mu: float, tape_gradient: float, check_seeds: Sequence[int], theta_star: float
) -> dict[str, Any]:
    """FR-011-23: 4 runs at mu + h and 4 at mu - h on the gradient-check seeds against the tape gradient."""
    h = H_FRACTION * mu
    plus = [(float(simulator.theta(mu + h, s)) - theta_star) ** 2 for s in check_seeds]
    minus = [(float(simulator.theta(mu - h, s)) - theta_star) ** 2 for s in check_seeds]
    gate = check_gradient(tape_gradient, plus, minus, h)
    return {
        "iterate": label,
        "parameter": "sliding_friction",
        "mu": float(mu),
        "tape_gradient": float(tape_gradient),
        "fd_gradient": float(gate.fd_gradient),
        "se_fd": float(gate.se_fd),
        "runs_per_side": gate.runs_per_side,
        "dof": gate.dof,
        "trusted": gate.trusted,
        "failure": gate.failure,
    }


# ------------------------------------------------------------------ the optional secondary arm (FR-011-27)


def _calibrate_secondary(req: dict[str, Any], simulator: Any, started: float) -> dict[str, Any]:
    seeds = req["seeds"]
    theta_star = float(req["target"]["theta_deg"])
    q_star = float(req["target"]["discharge_rate_kg_per_s"])
    opt = seeds["optimisation"]
    w_repose = 1.0 / REPOSE_SCALE_DEG**2
    w_discharge = 1.0 / DISCHARGE_SCALE**2

    def terms(mu_s: float, mu_r: float) -> tuple[float, float, float]:
        obs = [simulator.observables(mu_s, mu_r, s) for s in opt]
        repose = float(np.mean([(t - theta_star) ** 2 for t, _ in obs]))
        discharge = float(((np.mean([q for _, q in obs]) - q_star) / q_star) ** 2)
        return repose, discharge, float(np.mean([t for t, _ in obs]))

    def objective(x: Sequence[float]) -> float:
        repose, discharge, _ = terms(float(x[0]), float(x[1]))
        return w_repose * repose + w_discharge * discharge

    lo_s, hi_s = req["bounds"]
    lo_r, hi_r = req["rolling_bounds"]
    best, _, evaluations, reason, population = cmaes.minimise_cmaes(
        objective,
        [req["mu0"], req["mu0_rolling"]],
        ([lo_s, lo_r], [hi_s, hi_r]),
        sigma0=SIGMA0,
        rng_seed=int(req.get("cma_seed", 0)),
        max_evaluations=req["budget"] // len(opt),
        tolerance=LOSS_TOLERANCE_DEG**2,
    )
    mu_s, mu_r = best
    repose, discharge, smooth = terms(mu_s, mu_r)
    iv_s = seed_ensemble_interval(
        lambda x, s: simulator.observables(x, mu_r, s)[0],
        mu_s,
        interval_seeds=seeds["interval"],
        n_packing_seeds=req["packing_seeds"],
    )
    iv_r = seed_ensemble_interval(
        lambda x, s: simulator.observables(mu_s, x, s)[0],
        mu_r,
        interval_seeds=seeds["interval"],
        n_packing_seeds=req["packing_seeds"],
    )
    synthetic = req["kind"] == "synthetic-trial"
    truth = req.get("truth", {})
    parameters = [
        _parameter(
            "sliding_friction",
            req,
            start=req["mu0"],
            bounds=req["bounds"],
            estimate=mu_s,
            iv=iv_s,
            truth=truth.get("sliding_friction") if synthetic else None,
            cover_ok=True,
        ),
        _parameter(
            "rolling_friction",
            req,
            start=req["mu0_rolling"],
            bounds=req["rolling_bounds"],
            estimate=mu_r,
            iv=iv_r,
            truth=truth.get("rolling_friction") if synthetic else None,
            cover_ok=True,
        ),
    ]
    hard = (
        float(getattr(simulator, "hard_theta", lambda m, s: smooth)(mu_s, opt[0]))
        if hasattr(simulator, "hard_theta")
        else smooth
    )
    loss = {
        "observable": "smooth-envelope",
        "softmax_beta_per_d": 10,
        "bin_width_d": 2,
        "bin_range_pct": [20, 80],
        "terms": [
            {"name": "repose", "weight": w_repose, "value": repose},
            {"name": "discharge", "weight": w_discharge, "value": discharge},
        ],
        "total": w_repose * repose + w_discharge * discharge,
        "smooth_theta_deg": smooth,
        "hard_theta_deg": hard,
    }
    run = {
        "simulations": evaluations * len(opt),
        "interval_simulations": iv_s.simulations + iv_r.simulations,
        "check_simulations": 0,
        "stop_reason": reason,
        "wall_time_s": time.perf_counter() - started,
        "deterministic": bool(getattr(simulator, "deterministic_accumulation", False)),
    }
    doc = _base_document(req, simulator, parameters=parameters, loss=loss, run=run)
    doc["cmaes"] = {"sigma0": SIGMA0, "population": population, "cma_version": _cma_version()}
    return doc


# ------------------------------------------------------------------ both arms, OOM fallback, literature targets


def calibrate_arms(
    request: Mapping[str, Any], simulator: Any, arms: Sequence[str] = ("gradient", "cma-es")
) -> CalibrationRun:
    """Run the requested arms on the same request; a non-differentiable solver refuses the gradient arm (FR-011-29)."""
    run = CalibrationRun()
    for arm in arms:
        if arm == "gradient" and not getattr(simulator, "differentiable", False):
            run.refusals.append({"arm": "gradient", "reason": NOT_DIFFERENTIABLE})
            continue
        run.results.append(calibrate({**request, "arm": arm}, simulator))
    return run


def calibrate_with_oom_fallback(
    request: Mapping[str, Any], simulator_factory: Callable[[int], Any], *, manifest: dict[str, Any]
) -> dict[str, Any]:
    """`calibrate` with the declared fallback: the particle count is halved once after a CUDA out-of-memory error
    (FR-011-44)."""

    def attempt(params: dict[str, Any]) -> dict[str, Any]:
        simulator = simulator_factory(params["particle_count"])
        return calibrate({**request, "particle_count": params["particle_count"]}, simulator)

    doc = run_with_oom_fallback(
        "calibration", {"particle_count": int(request["particle_count"])}, attempt, manifest=manifest
    )
    doc["oom_fallback"] = bool(manifest.get("oom_fallback", False))
    return doc


def _check_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise _fail("rows", "at least one literature row is needed")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        where = f"rows[{i}]"
        if not isinstance(row.get("material"), str) or not SLUG.fullmatch(row["material"]):
            raise _fail(f"{where}.material", f"must be a slug, got {row.get('material')!r}")
        if not isinstance(row.get("knowledge_row"), str) or not ROW_ID.fullmatch(row["knowledge_row"]):
            raise _fail(f"{where}.knowledge_row", f"must be a knowledge-table row id, got {row.get('knowledge_row')!r}")
        _check_range(f"{where}.theta_deg", row.get("theta_deg"), 5.0, 60.0)
        if row.get("verification") not in ("verified", "UNVERIFIED"):
            raise _fail(f"{where}.verification", f"must be 'verified' or 'UNVERIFIED', got {row.get('verification')!r}")
        if row["material"] in seen:
            raise _fail(f"{where}.material", f"duplicate material {row['material']!r}")
        seen.add(row["material"])
    for material in REQUIRED_LITERATURE_MATERIALS:
        if material not in seen:
            raise _fail("rows", f"the required material {material!r} is missing")


def calibrate_literature_targets(
    rows: Sequence[Mapping[str, Any]],
    simulator_factory: Callable[[Mapping[str, Any]], Any],
    *,
    arm: str = "cma-es",
    budget: int = 60,
    seed_base: int = 100_000,
) -> list[dict[str, Any]]:
    """Calibrate the sliding friction at full scale against each cited literature repose target (FR-011-28).

    No coverage claim: the documents carry no truth. Each row gets its own trial id and disjoint seeds; the target
    keeps the
    knowledge-table row and its verification status (UNVERIFIED is propagated, never upgraded).
    """
    _check_rows(rows)
    results = []
    for index, row in enumerate(rows):
        base = seed_base + index * 100
        request = {
            "kind": "literature-target",
            "arm": arm,
            "trial_id": f"lit{index:02d}-{row['material']}"[:64].rstrip("-"),
            "target": {
                "theta_deg": float(row["theta_deg"]),
                "material": row["material"],
                "knowledge_row": row["knowledge_row"],
                "verification": row["verification"],
            },
            "mu0": 0.55,
            "bounds": [0.1, 1.0],
            "budget": budget,
            "window_steps": 1000,
            "settling_steps": 20000,
            "packing_seeds": 2,
            "interval_runs": 8,
            "seeds": {
                "target": [base],
                "optimisation": [base + 1, base + 2],
                "interval": [base + 3 + k for k in range(8)],
                "gradient_check": [base + 11 + k for k in range(4)],
            },
            "particle_count": LITERATURE_MAX_PARTICLES,
            "adam_lr": 0.02,
            "cma_seed": index,
            "secondary_arm": False,
            "solver_version": "unspecified",
        }
        simulator = simulator_factory(row)
        request["solver_version"] = str(getattr(simulator, "solver_version", "unspecified"))
        results.append(calibrate(request, simulator))
    return results


def publish_calibrated_set(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The calibrated friction of each literature material as a DC-011-01 `material_value` record with provenance."""
    materials: dict[str, Any] = {}
    for doc in results:
        if doc.get("kind") != "literature-target":
            continue
        material = doc["target"]["material"]
        if material in materials:
            continue
        materials[material] = {
            "sliding_friction": {
                "value": doc["parameters"][0]["estimate"],
                "source": "calibration",
                "ref": doc["trial_id"],
                "verification": doc["target"]["verification"],
            }
        }
    return {"materials": materials}
