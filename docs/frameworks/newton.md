# Newton

> The open, GPU physics engine on Warp that gives PitStudio an implicit material-point solver for granular piles and
> bucket fill, plus rigid and articulated bodies. · Part of: [Frameworks](README.md) · Related: [Warp](warp.md) ·
> [MuJoCo-Warp](mujoco-warp.md) · [Isaac Lab](isaac-lab.md) · [Bulk flow, DEM and MPM](../theory/bulk-flow-dem-mpm.md)

## What and why

Newton is a GPU-accelerated physics engine built on Warp. It is a Linux Foundation project started by Disney Research,
Google DeepMind and NVIDIA, with Apache-2.0 code and CC-BY-4.0 docs [1]. It succeeds Warp's removed `warp.sim`.

PitStudio uses Newton for what it does that our own kernels do not:

- **`SolverImplicitMPM`**: an implicit material point method for granular and elasto-plastic materials, with
  pressure-dependent Drucker–Prager yield (friction, dilatancy, hardening), and a `CouplingInterface` for two-way
  coupling with rigid bodies [2]. It is based on Daviet & Bertails-Descoubes 2016 (DOI 10.1145/2897824.2925877) [2].
  Implicit stepping is stable at large time steps, which suits stockpiles, muck piles and a bucket pushing into a
  pile.
- **Rigid and articulated bodies** through XPBD, VBD, Featherstone and the MuJoCo-Warp backend [3].
- **USD in and out**: `add_usd()` imports our scene; `ViewerUSD` writes time-sampled USD that Kit and Isaac Sim can
  replay [4].

Why not only Newton: our Warp DEM is the calibrated reference for discrete flows (chutes, dumps), and the M9
calibration needs gradients that Newton's implicit MPM does not provide. The split is recorded in
[DEC-0012](../architecture/decisions/DEC-0012-granular-physics-warp-newton.md).

## Identity

| Item | Value |
|---|---|
| Package | `newton` 1.6.0 with the `sim` extra, pinned in `studio/uv.lock` |
| Release | 2026-09-10 [5] |
| Pulls in | `mujoco` 3.12.0 and `mujoco-warp` 3.12.0 (the extra pins `~=3.12`), `warp-lang` ≥ 1.17 [5] |
| Licence | Apache-2.0 (code), CC-BY-4.0 (docs) · open |
| Ring | Trial |
| Environment | `studio/` (Python 3.14) |
| Note | Isaac Sim 6.1 ships its own Newton 1.5.0; that copy lives in `studio/isaac/` and is not used for the science [6] |

Newton's classifiers list Python 3.10–3.13 only, but `newton[sim]` 1.6.0 with `usd-core` 26.8 installed and ran a
GPU step on Python 3.14 in a local smoke during research. That is why the open studio needs no 3.12 environment.

## How PitStudio uses it

| Use | Solver | Case / method | What is checked |
|---|---|---|---|
| Stockpile and muck-pile formation, dump slumps | `SolverImplicitMPM` | A3, D1 · M7 | Repose angle; column-collapse run-out scaling (∝ a for low aspect ratio, ∝ a^1/2 for high, transition near a ≈ 1.7) [7] |
| Bucket penetration and fill | ImplicitMPM + rigid bucket via `CouplingInterface` | A3 · M7, M21 | Momentum balance of the reaction wrench; swept-volume conservation |
| Zero-shot check of the excavator policy | ImplicitMPM, 16–64 envs | IL-2b · `st61_il_mpm_eval` | FEE → MPM fill gap with a 95 % CI ([Isaac Lab](isaac-lab.md)) |
| Rigid trucks on ramps | XPBD / VBD / MuJoCo-Warp | B1 · M20 | Cross-engine rigid-body benchmark against ovphysx |
| Training data for the GNS surrogate | ImplicitMPM rollouts | A3 · M8 | Held-out repose ±1.5°, run-out ±5 % |

The granular example that ships with Newton uses a 0.1 voxel, friction coefficient μ = 0.68 and can load its scene from
USD [8]; our recipes set every material parameter explicitly from the calibration (M9).

Artefacts it will produce: MPM particle replays and aggregates (height field, run-out curve), time-sampled USD for Kit
renders, and GNS training rollouts. Stages: `st50_physics` under the `gpu0.compute` lock.

## Licence and redistribution

Apache-2.0: PitStudio may depend on it, cite it and publish its outputs freely.

## Assumptions and limits

- Newton 1.6 releases are frequent (1.3.0 in June, 1.6.0 in September 2026) [5]. The lock pins one version; upgrades
  are deliberate and re-run the physics benchmarks.
- Run-to-run determinism of the implicit MPM is **UNVERIFIED**. MPM stages are declared `statistical`: a re-run is
  compared on observables within the thresholds file, never bit for bit.
- The mapping from μ to an angle of repose is not established; calibration fixes it per material.
- Newton has no RTX-class lidar or radar: a `SensorLidar` exists only as an unmerged draft pull request [9].

## In PitStudio

- Probe: `probe_warp_newton.py` runs 64 particles for 240 XPBD steps and checks they fell and stayed above the ground
  ([Capabilities probe](../studio/capabilities-probe.md)). **Not yet run** on the reference machine.
- Status of the MPM runs: **not yet run** — produced in the data-and-models phase. Reported then: repose and run-out
  against the benchmarks above, and the FEE → MPM fill gap with its 95 % CI.
- Methods: [M07](../methods/m07-gpu-granular-physics.md), [M08](../methods/m08-gns-surrogate.md),
  [M21](../methods/m21-isaac-lab-policies.md).

## References

1. Newton Physics. *Newton README* (licence, governance, platforms). https://github.com/newton-physics/newton
2. Newton Physics. *SolverImplicitMPM*.
   https://newton-physics.github.io/newton/latest/api/_generated/newton.solvers.SolverImplicitMPM.html
3. Newton Physics. *Solvers API*. https://newton-physics.github.io/newton/latest/api/newton_solvers.html
4. Newton Physics. *Visualization (ViewerUSD)*. https://newton-physics.github.io/newton/latest/guide/visualization.html
5. Python Package Index. *newton* 1.6.0. https://pypi.org/pypi/newton/json
6. NVIDIA. *Isaac Sim release notes* (6.1.0: Kit 110.3.0, Newton 1.5.0).
   https://docs.isaacsim.omniverse.nvidia.com/latest/overview/release_notes.html
7. *Deposition morphology of granular column collapses* (arXiv 2002.02146). https://arxiv.org/html/2002.02146v3
8. Newton Physics. *Granular MPM example*.
   https://raw.githubusercontent.com/newton-physics/newton/main/newton/examples/mpm/example_mpm_granular.py
9. Newton Physics. *Pull request #3347 (SensorLidar draft)*. https://github.com/newton-physics/newton/pull/3347
