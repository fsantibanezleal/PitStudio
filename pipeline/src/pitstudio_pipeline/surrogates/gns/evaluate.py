"""GNS held-out evaluation (s50_evaluate; FR-011-06, FR-011-10, FR-011-12, FR-011-13, SC-011-01, FR-011-49, FR-011-50).

For each held-out geometry the surrogate is rolled out from the initial packing of each of 3 at-rest reference packings
to
T_end; the means over the 3 packings of the repose angle and the run-out are compared with the reference means by the
one
observable function of `pitstudio.granular.observables`; the verdict is the SC-011-01 limits of `thresholds.yaml`. The
report
also carries the reference packing spread, the position error growth per step, the particle count per step and the
overflow count. A diverged rollout fails its geometry; a geometry without 3 at-rest reference packings fails with a
reason.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from pitstudio.granular.observables import FAMILIES, observables
from pitstudio_pipeline.surrogates.fixture import is_fixture, stamp
from pitstudio_pipeline.surrogates.thresholds import model_threshold

N_PACKINGS = 3
NOT_RUN = "not run (absent)"
REST_FRACTION = 0.01  # a packing is at rest when its maximum speed is below 0.01 sqrt(g d) (FR-011-10)


def at_rest(positions: np.ndarray, *, d: float, dt: float, g: float = 9.81) -> bool:
    """True iff the maximum particle speed over the last frame interval is below 0.01 sqrt(g d)."""
    speed = np.linalg.norm(positions[-1].astype(np.float64) - positions[-2].astype(np.float64), axis=1).max() / dt
    return bool(speed < REST_FRACTION * math.sqrt(g * d))


def _spread(values: Sequence[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    return {"range": float(arr.max() - arr.min()), "sd": float(arr.std(ddof=1)) if arr.size > 1 else 0.0}


def _check_geometry(geometry: Mapping[str, Any]) -> None:
    gid = geometry.get("geometry_id")
    if geometry.get("family") not in FAMILIES:
        raise ValueError(f"geometry {gid!r}: unknown family {geometry.get('family')!r}")
    refs = geometry.get("references", [])
    if len(refs) < N_PACKINGS:
        raise ValueError(f"geometry {gid!r}: needs at least {N_PACKINGS} reference packings, got {len(refs)}")
    for ref in refs:
        pos = np.asarray(ref["positions"])
        if pos.ndim != 3 or pos.shape[2] != 2 or pos.shape[0] < 2:
            raise ValueError(f"geometry {gid!r}, seed {ref['seed']}: positions must have shape [T >= 2, N, 2]")
        if not np.isfinite(pos).all():
            raise ValueError(f"geometry {gid!r}, seed {ref['seed']}: positions contain a non-finite value")


def evaluate_held_out(
    geometries: Sequence[Mapping[str, Any]],
    surrogate: Callable[[dict[str, Any], int], Any],
    *,
    expected: Sequence[Mapping[str, str]] | None = None,
    dataset_manifest: Mapping[str, Any] | None = None,
    g: float = 9.81,
) -> dict[str, Any]:
    """Score `surrogate` on the held-out geometries; the report layout is documented in the module docstring and the
    tests."""
    fixture = is_fixture(dataset_manifest)  # a non-boolean flag stops the stage before any work
    if not geometries:
        raise ValueError("no held-out geometry to evaluate")
    repose_limit = float(model_threshold("gns_repose_abs_deg_max"))
    runout_limit = float(model_threshold("gns_runout_rel_max"))
    present_ids = [geometry["geometry_id"] for geometry in geometries]
    if expected is not None:
        expected_ids = {e["geometry_id"] for e in expected}
        unexpected = [i for i in present_ids if i not in expected_ids]
        if unexpected:
            raise ValueError(f"geometry {unexpected[0]!r} is not among the expected held-out geometries")
    for geometry in geometries:
        _check_geometry(geometry)

    records = [_evaluate_geometry(geometry, surrogate, repose_limit, runout_limit, g) for geometry in geometries]

    missing: list[dict[str, str]] = []
    families_not_run: list[str] = []
    if expected is not None:
        have = set(present_ids)
        missing = [
            {"geometry_id": e["geometry_id"], "family": e["family"], "status": NOT_RUN}
            for e in expected
            if e["geometry_id"] not in have
        ]
        present_families = {geometry["family"] for geometry in geometries}
        families_not_run = sorted({e["family"] for e in expected} - present_families)
    complete = not missing
    all_pass = all(r["pass"] for r in records)
    report: dict[str, Any] = {
        "geometries": records,
        "replacements_total": sum(r["replacements"] for r in records),
        "n_geometries": len(records),
        "all_pass": all_pass if complete else None,
        "sc_011_01": ("pass" if all_pass else "fail") if complete else None,
        "status": "complete" if complete else "partial",
        "missing": missing,
        "families_not_run": families_not_run,
        "limits": {"repose_abs_deg_max": repose_limit, "runout_rel_max": runout_limit},
    }
    return stamp(report, dataset_manifest) if fixture else report


def _evaluate_geometry(
    geometry: Mapping[str, Any],
    surrogate: Callable[[dict[str, Any], int], Any],
    repose_limit: float,
    runout_limit: float,
    g: float,
) -> dict[str, Any]:
    d, dt = float(geometry["d"]), float(geometry["dt"])
    family, params = geometry["family"], geometry["geometry"]
    used: list[Mapping[str, Any]] = []
    replacements = 0
    for ref in geometry["references"]:
        if len(used) == N_PACKINGS:
            break
        if at_rest(np.asarray(ref["positions"]), d=d, dt=dt, g=g):
            used.append(ref)
        else:
            replacements += 1
    record: dict[str, Any] = {
        "geometry_id": geometry["geometry_id"],
        "family": family,
        "used_seeds": [int(r["seed"]) for r in used],
        "replacements": replacements,
        "reference_repose_deg": None,
        "reference_runout_m": None,
        "surrogate_repose_deg": None,
        "surrogate_runout_m": None,
        "delta_repose_deg": None,
        "delta_runout_rel": None,
        "pass": False,
        "reference_spread": None,
        "position_error_growth": [],
        "particle_count_per_step": [],
        "overflow_count": 0,
        "neighbour_overflow": False,
        "diverged": False,
        "diverged_at_step": None,
        "reason": None,
    }
    if len(used) < N_PACKINGS:
        record["reason"] = f"fewer than {N_PACKINGS} reference packings at rest ({len(used)} found)"
        return record

    try:
        ref_obs = [observables(np.asarray(r["positions"])[-1], d=d, family=family, geometry=params) for r in used]
    except ValueError as exc:
        record["reason"] = f"reference observables could not be extracted: {exc}"
        return record
    ref_repose = [o["repose_deg"] for o in ref_obs]
    ref_runout = [o["run_out_m"] for o in ref_obs]
    record["reference_repose_deg"] = float(np.mean(ref_repose))
    record["reference_runout_m"] = float(np.mean(ref_runout))
    record["reference_spread"] = {"repose_deg": _spread(ref_repose), "runout_m": _spread(ref_runout)}

    results = []
    for ref in used:
        frames = np.asarray(ref["positions"])
        n = frames.shape[1]
        state = {
            "geometry_id": geometry["geometry_id"],
            "seed": int(ref["seed"]),
            "positions": frames[0],
            "velocities": np.zeros((n, 5, 2), dtype=np.float32),
            "particle_type": np.asarray(ref["particle_types"]),
            "bounds": np.asarray(geometry["bounds"], dtype=np.float32),
            "d": d,
            "dt": dt,
        }
        result = surrogate(state, frames.shape[0] - 1)
        out = np.asarray(result.positions)
        if out.ndim != 3 or out.shape[1] != n or out.shape[2] != 2:
            raise ValueError(
                f"geometry {geometry['geometry_id']!r}, seed {ref['seed']}: the surrogate changed the particle count "
                f"or the state shape (reference {n} particles, got {list(out.shape)})"
            )
        results.append((ref, out, result))

    record["overflow_count"] = int(sum(sum(int(c) for c in r.overflow_counts) for _, _, r in results))
    record["neighbour_overflow"] = record["overflow_count"] > 0
    shortest = min(out.shape[0] for _, out, _ in results)
    record["particle_count_per_step"] = [int(results[0][1][t].shape[0]) for t in range(shortest)]
    growth = []
    for t in range(shortest):
        errs = [
            float(
                np.linalg.norm(
                    out[t].astype(np.float64) - np.asarray(ref["positions"])[t].astype(np.float64), axis=1
                ).mean()
            )
            for ref, out, _ in results
        ]
        growth.append(float(np.mean(errs)))
    record["position_error_growth"] = growth
    diverged = [r for _, _, r in results if r.status != "ok"]
    if diverged:
        step = diverged[0].diverged_at_step
        record["diverged"] = True
        record["diverged_at_step"] = step
        record["reason"] = f"diverged at step {step}"
        return record
    try:
        sur_obs = [observables(out[-1], d=d, family=family, geometry=params) for _, out, _ in results]
    except ValueError as exc:
        record["reason"] = f"surrogate observables could not be extracted: {exc}"
        return record
    record["surrogate_repose_deg"] = float(np.mean([o["repose_deg"] for o in sur_obs]))
    record["surrogate_runout_m"] = float(np.mean([o["run_out_m"] for o in sur_obs]))
    record["delta_repose_deg"] = abs(record["surrogate_repose_deg"] - record["reference_repose_deg"])
    record["delta_runout_rel"] = abs(record["surrogate_runout_m"] - record["reference_runout_m"]) / abs(
        record["reference_runout_m"]
    )
    record["pass"] = bool(record["delta_repose_deg"] <= repose_limit and record["delta_runout_rel"] <= runout_limit)
    return record
