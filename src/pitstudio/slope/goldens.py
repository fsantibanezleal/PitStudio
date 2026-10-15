"""C1 golden scenarios for the ``geotech`` parity fixture of spec 018 (T-010-018, DC-018-04).

``build_geotech_goldens(seed)`` returns one parity-fixture document per engine function: ``bishop_fos``,
``spencer_fos``,
``hoek_brown_mohr_coulomb``, ``search_min_fos`` (all analytical-iterative, >= 200 vectors, both exact ends of every
validity range present) and ``pof_monte_carlo`` (monte-carlo-count: the recorded PCG64 sample matrix, the per-sample
minimum factor and the failing count; no factor within 1e-9 of 1, so no sample can flip on rounding in another engine).
Everything is deterministic in ``seed``. In ``search_min_fos`` the circles tied with the minimum (a cohesionless
straight
slope makes every circle of one radius ratio similar, hence equal in F) are one class, and ``second_fos`` is the lowest
factor that differs from ``fos`` by at least 1e-9 F.

The reference named in each document is the owner of the per-circle numerics in the spec (``minephys``); the values are
produced by ``pitstudio.slope`` (the same formulas, section 7 of spec 010) until ``minephys.geotech`` is pinned by this
repository; no ``callable`` is claimed.
"""

from __future__ import annotations

import math
from importlib import metadata
from typing import Any

import numpy as np

from pitstudio.slope import lem, pof
from pitstudio.slope import section as _section

SOLVER_TOL = 1e-9
RTOL = 1e-8
ATOL_SCALE = 1e-12
MIN_CASES = 210
SLICE_RANGE = (10, 500)
POF_CASES = 6
POF_SAMPLES = 400

BISHOP_RANGES: dict[str, tuple[float, float]] = {
    "height_m": (5.0, 200.0),
    "face_angle_deg": (20.0, 80.0),
    "unit_weight_kn_per_m3": (16.0, 28.0),
    "cohesion_kpa": (0.0, 200.0),
    "friction_angle_deg": (5.0, 50.0),
    "pore_pressure_ratio": (0.0, 0.5),
}
HB_RANGES: dict[str, tuple[float, float]] = {
    "gsi": (0.0, 100.0),
    "m_i": (1.0, 35.0),
    "sigma_ci_mpa": (1.0, 250.0),
    "disturbance_d": (0.0, 1.0),
}
SEARCH_GRID = {"entry_points": 10, "exit_points": 10, "radius_ratios": 4, "rho_min": 1.1, "rho_max": 4.0}
SEARCH_SLICES = 50


def planar_section(inputs: dict[str, Any], *, search: dict[str, Any] | None = None) -> dict[str, Any]:
    """The straight-ground section the flat golden inputs describe: crest at x = 0, toe at x = H / tan(face)."""
    h, face = float(inputs["height_m"]), float(inputs["face_angle_deg"])
    t = math.tan(math.radians(face))
    x_c, x_t = 0.0, h / t
    x_left, x_right = x_c - 3.0 * h, x_t + 2.0 * h
    return {
        "schema_version": "1.0",
        "section_id": "c1-golden",
        "source": {"kind": "fixture"},
        "ground": [[x_left, h - (x_left - x_c) * t], [x_right, h - (x_right - x_c) * t]],
        "crest_x_m": x_c,
        "toe_x_m": x_t,
        "materials": [
            {
                "id": "fill",
                "model": "mohr-coulomb",
                "unit_weight_kn_per_m3": float(inputs["unit_weight_kn_per_m3"]),
                "cohesion_kpa": float(inputs["cohesion_kpa"]),
                "friction_angle_deg": float(inputs["friction_angle_deg"]),
            }
        ],
        "pore_pressure_ratio": float(inputs["pore_pressure_ratio"]),
        "analysis": {
            "mode": "baked",
            "methods": ["bishop", "spencer"],
            "slices": int(inputs.get("slices", SEARCH_SLICES)),
            "search": search
            or {"entry_points": 40, "exit_points": 40, "radius_ratios": 8, "rho_min": 1.02, "rho_max": 4.0},
        },
    }


def _draw_section_inputs(rng: np.random.Generator, pinned: dict[str, float] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {k: float(rng.uniform(lo, hi)) for k, (lo, hi) in BISHOP_RANGES.items()}
    out.update(pinned or {})
    return out


def _draw_circle(rng: np.random.Generator, inputs: dict[str, Any]) -> dict[str, float]:
    h, t = float(inputs["height_m"]), math.tan(math.radians(float(inputs["face_angle_deg"])))
    x_t = h / t
    mid = 0.5 * x_t
    entry = float(rng.uniform(-2.0 * h, mid))
    exit_ = float(rng.uniform(mid, x_t + h))
    rho = float(math.exp(rng.uniform(math.log(1.02), math.log(4.0))))
    return {"entry_x_m": entry, "exit_x_m": exit_, "rho": rho}


def _circle_of(section: dict[str, Any], c: dict[str, float]) -> lem.Circle:
    prep = _section.prepare(section)
    ee, xx, cx, cz, rad = lem._circles_through(
        prep, np.asarray([c["entry_x_m"]]), np.asarray([c["exit_x_m"]]), np.asarray([c["rho"]])
    )
    return lem.Circle(float(ee[0]), float(xx[0]), float(cx[0]), float(cz[0]), float(rad[0]))


def _pinned_plans(
    ranges: dict[str, tuple[float, float]], extra: dict[str, tuple[float, float]]
) -> list[dict[str, float]]:
    plans: list[dict[str, float]] = []
    for key, (lo, hi) in {**ranges, **extra}.items():
        plans.append({key: lo})
        plans.append({key: hi})
    return plans


def _tolerance() -> dict[str, Any]:
    return {"class": "analytical-iterative", "rtol": RTOL, "atol_scale": ATOL_SCALE, "solver_tol": SOLVER_TOL}


def _reference() -> dict[str, str]:
    try:
        version = metadata.version("minephys")
    except metadata.PackageNotFoundError:
        version = "0.0.0"
    return {"name": "minephys", "version": version}


def _document(name: str, tolerance: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "engine": "geotech",
        "fixture": f"c1-{name.replace('_', '-')}",
        "function": name,
        "reference": _reference(),
        "tolerance": tolerance,
        "cases": cases,
    }


# ----------------------------------------------------------------------------------------------------------------------
# per-circle functions


def _circle_cases(rng: np.random.Generator, method: str) -> list[dict[str, Any]]:
    plans = _pinned_plans(BISHOP_RANGES, {})
    slice_plans = [{"slices": float(SLICE_RANGE[0])}, {"slices": float(SLICE_RANGE[1])}]
    cases: list[dict[str, Any]] = []
    index = 0
    while len(cases) < MIN_CASES:
        plan = plans[index] if index < len(plans) else {}
        slice_plan = slice_plans[index - len(plans)] if len(plans) <= index < len(plans) + 2 else {}
        index += 1
        for _attempt in range(400):
            inputs = _draw_section_inputs(rng, plan)
            slices = int(slice_plan["slices"]) if slice_plan else int(rng.integers(10, 201))
            inputs["slices"] = slices
            circle = _draw_circle(rng, inputs)
            section = planar_section(inputs)
            try:
                if method == "bishop":
                    res = lem.bishop_fos(section, _circle_of(section, circle), slices=slices)
                else:
                    res = lem.spencer_fos(section, _circle_of(section, circle), slices=slices)
            except lem.CircleRejected:
                continue
            if not 0.05 < res.fos < 1000.0:
                continue
            output: dict[str, Any] = {"fos": float(res.fos)}
            if method == "spencer":
                output["theta_deg"] = float(res.theta_deg)  # type: ignore[arg-type]
            cases.append({"input": {**inputs, **circle}, "output": output})
            break
        else:  # pragma: no cover - the ranges always admit a valid circle
            raise RuntimeError(f"no valid {method} golden for the plan {plan}")
    return cases


# ----------------------------------------------------------------------------------------------------------------------
# Hoek-Brown conversion


def _hb_cases(rng: np.random.Generator) -> list[dict[str, Any]]:
    plans = _pinned_plans(HB_RANGES, {})
    cases = []
    for i in range(MIN_CASES):
        plan = plans[i] if i < len(plans) else {}
        inputs = {k: float(rng.uniform(lo, hi)) for k, (lo, hi) in HB_RANGES.items()}
        inputs.update(plan)
        inputs["sigma_n_kpa"] = float(math.exp(rng.uniform(math.log(1.0), math.log(5000.0))))
        c, phi = lem.hoek_brown_to_mohr_coulomb(
            inputs["gsi"], inputs["m_i"], inputs["sigma_ci_mpa"], inputs["disturbance_d"], inputs["sigma_n_kpa"]
        )
        cases.append({"input": inputs, "output": {"cohesion_kpa": float(c), "friction_angle_deg": float(phi)}})
    return cases


# ----------------------------------------------------------------------------------------------------------------------
# search


def _search_cases(rng: np.random.Generator) -> list[dict[str, Any]]:
    plans = _pinned_plans(BISHOP_RANGES, {})
    cases: list[dict[str, Any]] = []
    index = 0
    while len(cases) < MIN_CASES:
        plan = plans[index] if index < len(plans) else {}
        index += 1
        for _attempt in range(400):
            inputs = _draw_section_inputs(rng, plan)
            inputs["slices"] = SEARCH_SLICES
            section = planar_section(inputs, search=SEARCH_GRID)
            prep = _section.prepare(section)
            f, _, status = lem._bishop_batch(prep, lem._grid_arrays(prep), SEARCH_SLICES, 1e-9, 100)
            valid = np.sort(f[(status == lem._OK) & (f > 0.05)])
            if valid.size < 2 or valid[0] >= 1000.0:
                continue
            # circles tied with the minimum (c' = 0 on straight ground makes every circle of one radius ratio similar,
            # hence equal in F) are one class: second_fos is the lowest factor that differs from fos by >= 1e-9 F
            apart = valid[valid >= valid[0] * (1.0 + 1e-9)]
            if apart.size == 0 or valid[0] >= 1000.0:
                continue
            cases.append(
                {"input": {**inputs, **SEARCH_GRID}, "output": {"fos": float(valid[0]), "second_fos": float(apart[0])}}
            )
            break
        else:  # pragma: no cover
            raise RuntimeError(f"no tie-free search golden for the plan {plan}")
    return cases


# ----------------------------------------------------------------------------------------------------------------------
# Monte-Carlo PoF


def _pof_cases(seed: int, rng: np.random.Generator) -> list[dict[str, Any]]:
    cases = []
    columns = ["cohesion_kpa", "friction_angle_deg"]
    for index in range(POF_CASES):
        for _attempt in range(100):
            inputs = _draw_section_inputs(rng)
            inputs["height_m"] = float(rng.uniform(10.0, 60.0))
            inputs["cohesion_kpa"] = float(rng.uniform(5.0, 60.0))
            inputs["friction_angle_deg"] = float(rng.uniform(15.0, 40.0))
            inputs["pore_pressure_ratio"] = float(rng.uniform(0.0, 0.3))
            inputs["slices"] = SEARCH_SLICES
            candidates = 8
            section = planar_section(inputs, search=SEARCH_GRID)
            dists = [
                {
                    "material_id": "fill",
                    "parameter": "cohesion_kpa",
                    "distribution": "normal",
                    "mean": inputs["cohesion_kpa"],
                    "sd": 0.25 * inputs["cohesion_kpa"],
                    "truncate_lower": 0.0,
                },
                {
                    "material_id": "fill",
                    "parameter": "friction_angle_deg",
                    "distribution": "normal",
                    "mean": inputs["friction_angle_deg"],
                    "sd": 3.0,
                    "truncate_lower": 5.0,
                    "truncate_upper": 60.0,
                },
            ]
            entropy, spawn_key = seed, [index]
            gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy, spawn_key=tuple(spawn_key))))
            draws = {pof.sample_key(d): pof._draw(d, gen.random(POF_SAMPLES)) for d in dists}
            prep = _section.prepare(section)
            minimum = pof.minimum_factors(prep, draws, POF_SAMPLES, candidates)
            if not np.all(np.isfinite(minimum)) or np.any(np.abs(minimum - 1.0) < 1e-9):
                continue
            failing = int(np.sum(minimum < 1.0))
            matrix = [[float(draws["fill." + c][i]) for c in columns] for i in range(POF_SAMPLES)]
            cases.append(
                {
                    "name": f"pof-{index}",
                    "input": {**inputs, **SEARCH_GRID, "candidates": candidates, "columns": columns},
                    "output": {
                        "failing_samples": failing,
                        "pof": failing / POF_SAMPLES,
                        "factors": [float(v) for v in minimum],
                    },
                    "variates": {
                        "generator": "pcg64",
                        "entropy": str(entropy),
                        "spawn_key": spawn_key,
                        "samples": matrix,
                    },
                }
            )
            break
        else:  # pragma: no cover
            raise RuntimeError("no Monte-Carlo golden away from F = 1")
    return cases


def build_geotech_goldens(seed: int) -> dict[str, dict[str, Any]]:
    """The parity-fixture documents of the ``geotech`` engine for the C1 functions, deterministic in ``seed``."""
    rng = np.random.default_rng(seed)
    bishop = _circle_cases(rng, "bishop")
    spencer = _circle_cases(rng, "spencer")
    return {
        "bishop_fos": _document("bishop_fos", _tolerance(), bishop),
        "spencer_fos": _document("spencer_fos", _tolerance(), spencer),
        "hoek_brown_mohr_coulomb": _document("hoek_brown_mohr_coulomb", _tolerance(), _hb_cases(rng)),
        "search_min_fos": _document("search_min_fos", _tolerance(), _search_cases(rng)),
        "pof_monte_carlo": _document("pof_monte_carlo", {"class": "monte-carlo-count"}, _pof_cases(seed, rng)),
    }
