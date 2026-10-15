# SPDX-License-Identifier: Apache-2.0
"""MPM evaluation tier of the IL-2 policy (FR-014-22, FR-014-23).

The tier logic is torch-free: it pairs the first n FEE evaluation episodes (same seeds, same initial profiles), runs them in
batches of at most ``envs`` through a backend (the real one is Newton's implicit MPM coupled to the rigid bucket, in the
Isaac Lab package), and turns the particle mass inside the bucket into the fill factor
k_f = mass / (V_h rho_loose). Anything that prevents a trustworthy result ends as "not run" with a reason, never a fake row.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pitstudio.robots.config import validate_task_params

__all__ = ["MIN_EPISODES", "MpmBackend", "MpmResult", "run_mpm_tier"]

MIN_EPISODES = 16


class MpmBackend(Protocol):
    def smoke(self) -> bool: ...

    def run(
        self, policy: Any, profiles: Sequence[Any], seeds: Sequence[int], material: Any, num_envs: int
    ) -> list[dict[str, Any] | None]: ...


@dataclass(frozen=True)
class MpmResult:
    status: str  # "complete" | "not run"
    reason: str | None
    rows: list[dict[str, Any]]
    seeds: list[int]
    manifest: dict[str, Any]


def _positive(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {value!r}")
    return float(value)


def run_mpm_tier(
    params: Mapping[str, Any],
    backend: MpmBackend,
    policy: Any,
    *,
    fee_seeds: Sequence[int],
    profiles: Sequence[Any],
    material: Mapping[str, Any] | None,
    v_heaped: float,
) -> MpmResult:
    """Run the trained IL-2 policy unchanged in the MPM backend on the first n paired FEE episodes."""
    validate_task_params(params)
    if params.get("policy") != "IL-2" or params.get("stage") != "st61_il_mpm_eval" or "mpm" not in params:
        raise ValueError("params must be an IL-2 task document of stage st61_il_mpm_eval with an mpm block")
    n = int(params["mpm"]["episodes"])
    envs = int(params["mpm"]["envs"])
    vh = _positive("v_heaped", v_heaped)
    if len(fee_seeds) < n:
        raise ValueError(f"fee_seeds holds {len(fee_seeds)} seeds, fewer than the {n} MPM episodes")
    if len(profiles) < n or len(profiles) != len(fee_seeds):
        raise ValueError(f"profiles ({len(profiles)}) must match fee_seeds ({len(fee_seeds)}) and cover {n} episodes")
    manifest: dict[str, Any] = {"n_requested": n, "n_completed": 0, "envs": envs}

    def not_run(reason: str) -> MpmResult:
        return MpmResult("not run", reason, [], [], manifest)

    rho_loose = 0.0
    if material is not None:
        if material.get("id") != params["mpm"]["material"]:
            raise ValueError(f"material {material.get('id')!r} is not the task material {params['mpm']['material']!r}")
        rho_loose = _positive("material rho_loose_kg_m3", material.get("rho_loose_kg_m3"))
    if material is None:
        return not_run("calibrated material artefact is missing (material)")
    if not backend.smoke():
        return not_run("the coupled rigid-MPM smoke failed (smoke)")

    seeds = [int(s) for s in fee_seeds[:n]]
    rows: list[dict[str, Any]] = []
    for lo in range(0, n, envs):
        batch_seeds = seeds[lo : lo + envs]
        batch_profiles = list(profiles[lo : min(lo + envs, n)])
        results = backend.run(policy, batch_profiles, batch_seeds, material, envs)
        if len(results) != len(batch_seeds):
            raise ValueError(f"backend returned {len(results)} results for {len(batch_seeds)} episodes")
        for seed, result in zip(batch_seeds, results, strict=True):
            if result is None:
                continue
            mass = result.get("particle_mass_kg")
            if isinstance(mass, bool) or not isinstance(mass, int | float) or not math.isfinite(mass) or mass < 0:
                raise ValueError(f"particle_mass_kg must be finite and >= 0, got {mass!r}")
            cycle = _positive("cycle_time_s", result.get("cycle_time_s"))
            k_f = float(mass) / (vh * rho_loose)
            rows.append(
                {
                    "seed": seed,
                    "termination": "completed",
                    "fill_factor": k_f,
                    "cycle_time_s": cycle,
                    "productivity_per_s": k_f / cycle,
                    "stalled": bool(result.get("stalled", False)),
                    "lift_off": bool(result.get("lift_off", False)),
                }
            )
    manifest["n_completed"] = len(rows)
    if len(rows) < MIN_EPISODES:
        return not_run(f"fewer than {MIN_EPISODES} MPM episodes completed ({len(rows)} of {n})")
    return MpmResult("complete", None, rows, [r["seed"] for r in rows], manifest)
