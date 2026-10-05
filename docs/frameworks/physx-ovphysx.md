# PhysX and ovphysx

> NVIDIA's rigid-body and vehicle engine, used in two narrow roles: the PhysX vehicle visual twin inside Isaac Sim, and
> a Kit-less rigid-body cross-check of Newton through ovphysx. · Part of: [Frameworks](README.md) · Related:
> [Isaac Sim + Replicator](isaac-sim-replicator.md) · [ovrtx](ovrtx.md) · [Newton](newton.md) ·
> [B1 traffic and proximity](../cases/b1-traffic-proximity.md)

## What and why

**PhysX 5** is NVIDIA's physics SDK: rigid bodies, articulations, vehicles, particles and deformables, with GPU
pipelines for many of them [1][2]. **ovphysx** wraps it as a standalone library: "a standalone library for USD-based
physics simulation, offering a C API with Python bindings", which runs without Kit, reads our USD stage through
ovstage and returns state as Warp arrays or DLPack tensors [3][4].

PitStudio keeps PhysX in a **supporting** role:

- **Visual vehicle twin.** Isaac Sim's PhysX vehicles drive the haul trucks in RTX clips for case B1 (`st54_vehicles`).
  The numbers of B1 come from the agent traffic model and Rapier, not from these clips.
- **Cross-engine check.** The same USD rigid-body benchmark (rock fall, boulder tumbling) runs in ovphysx and in
  Newton, and the differences are reported against stated tolerances. Two engines agreeing on our scene is evidence
  that the scene, not one solver, sets the result.

Rejected uses:

| Use | Why not |
|---|---|
| PhysX particles as the granular model | Position-based dynamics are animation-grade, with no calibrated Hertz–Mindlin or Drucker–Prager model; the Kit particle schema is "not finalized" [5] |
| ovphysx for haul-truck vehicles | "Vehicles are CPU-only, so these have no device path" [6] |
| A shared ovstage between ovphysx and ovrtx as the core loop | Still opt-in upstream because of cold binding and stage-update cost [7] |

## Identity

| Item | Value |
|---|---|
| ovphysx | 0.6.3, pinned in `studio/rtx/uv.lock` from the explicit `pypi.nvidia.com` index; uploaded 2026-09-16 [8] |
| Bundled engine | PhysX SDK 5.11 [9] |
| Pins it brings | `ovstage==0.2.0.377349`, `warp-lang<2,>=1.16`, `packaging<24` [8] |
| PhysX in Isaac Sim | inside `isaacsim` 6.1.0.0 (`studio/isaac/uv.lock`) |
| Licence | conflicting labels (below) · treated as **reference-only** |
| Ring | Trial (scoped to `studio/rtx/`) |
| Environment | `studio/rtx/` and `studio/isaac/` (Python 3.12) |
| CPU | needs AVX [8] |

## Licence and redistribution

The licence labels disagree, so PitStudio takes the strictest reading:

- The ovphysx 0.6.3 release note calls it "a full open source release" under Apache 2.0, and the 0.6.2 changelog says
  ovphysx and the bundled PhysX SDK moved from BSD-3-Clause to Apache 2.0 [9][6].
- The ovphysx README says the **source** is Apache 2.0 but the **pre-built binaries** (SDK packages and Python wheels)
  are under the NVIDIA Omniverse License [10].
- PyPI labels the wheel `LicenseRef-NVIDIA-Omniverse` [8], and the repo-root licence of the PhysX repository is still
  BSD-3-Clause [11].

PitStudio installs the pre-built wheel, so it classifies ovphysx as **reference-only**: never redistributed, never a
hard dependency of the open lane. PhysX inside Isaac Sim falls under Isaac Sim's licence
([Isaac Sim + Replicator](isaac-sim-replicator.md)). Performance numbers of these runtimes stay local where their
licence restricts them ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

## How PitStudio uses it

| Stage | Environment | Case | Output |
|---|---|---|---|
| `st54_vehicles` (PhysX visual twin) | `studio/isaac/` | B1 | RTX clips of trucks and light vehicles on real ramp geometry |
| ovphysx rigid-body cross-check | `studio/rtx/` | B1 | A cross-engine table: same USD, two solvers, stated tolerances |

The poses that drive sensor scenes are kinematic (from the haulage DES or Newton): sensor realism does not need PhysX
in the loop ([ovrtx](ovrtx.md)).

## Assumptions and limits

- Pre-release: "Parts of the API are still being completed and may change before 1.0" [9]. Exact pins and a thin
  adapter keep breakage in one file.
- PhysX GPU rigid bodies pay off with "several thousand active actors"; the default memory configuration is about
  10,000 bodies; GPU convex hulls are limited to 64 vertices; CCD and triggers are CPU-only [2].
- PhysX Vehicle2 is a component SDK (tyre, suspension, drivetrain) whose documentation does not state a GPU path [12].
- GPU determinism settings of PhysX are **UNVERIFIED**; the cross-check compares observables with tolerances.

## In PitStudio

- Status: **not yet run** — produced in the data-and-models phase. The `studio/rtx/` lock resolves ovphysx 0.6.3; no PhysX scene has run.
- Tool matrix entry: [B1](../cases/b1-traffic-proximity.md), method [M20](../methods/m20-traffic-ttc.md).

## References

1. NVIDIA. *PhysX repository* (SDK 5.11, licence, ovphysx). https://github.com/NVIDIA-Omniverse/PhysX
2. NVIDIA. *PhysX GPU rigid bodies* (5.6.1 docs). https://nvidia-omniverse.github.io/PhysX/physx/5.6.1/docs/GPURigidBodies.html
3. NVIDIA. *ovphysx* (standalone USD physics, licence split, CPU support).
   https://github.com/NVIDIA-Omniverse/PhysX/tree/main/ovphysx
4. NVIDIA. *ovphysx 0.6.3 documentation*. https://nvidia-omniverse.github.io/PhysX/ovphysx/0.6.3/index.html
5. NVIDIA. *Omni Physics particles*. https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/particles/particles.html
6. NVIDIA. *ovphysx changelog* (0.6.1 CPU-only vehicles; 0.6.2 Apache 2.0).
   https://nvidia-omniverse.github.io/PhysX/ovphysx/latest/changelog.html
7. Isaac Lab. *Pull request #8279* (opt-in shared OVStage physics and rendering). https://github.com/isaac-sim/IsaacLab/pull/8279
8. Python Package Index. *ovphysx* 0.6.3. https://pypi.org/pypi/ovphysx/json
9. NVIDIA. *ovphysx 0.6.3 release*. https://api.github.com/repos/NVIDIA-Omniverse/PhysX/releases/tags/ovphysx-0.6.3
10. NVIDIA. *ovphysx README*. https://raw.githubusercontent.com/NVIDIA-Omniverse/PhysX/main/ovphysx/README.md
11. NVIDIA. *PhysX repository LICENSE.md*. https://github.com/NVIDIA-Omniverse/PhysX/blob/main/LICENSE.md
12. NVIDIA. *PhysX Vehicles* (5.6.1 docs). https://nvidia-omniverse.github.io/PhysX/physx/5.6.1/docs/Vehicles.html
