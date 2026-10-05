# MuJoCo-Warp

> The GPU port of the MuJoCo rigid-body solver, used inside Newton for articulated mining machines and batched
> vehicle rollouts. · Part of: [Frameworks](README.md) · Related: [Newton](newton.md) · [Isaac Lab](isaac-lab.md) ·
> [Loading and terramechanics](../theory/loading-and-terramechanics.md) · [M21 Isaac Lab policies](../methods/m21-isaac-lab-policies.md)

## What and why

MuJoCo is a rigid-body and articulated-system simulator; **MuJoCo Warp** reimplements its pipeline on NVIDIA Warp so
thousands of worlds step in parallel on one GPU. It is maintained by Google DeepMind and NVIDIA and is Newton's rigid
backend (`SolverMuJoCo`) [1][2].

PitStudio needs it for the parts of a mine that are machines rather than material:

- **Articulated kinematics and dynamics** of a rope or hydraulic shovel, an excavator and a wheel loader (swing, boom,
  stick, bucket joints with limits and drives).
- **Batched vehicle rollouts**: many haul trucks on a ramp segment at once, for robot-learning tasks and for
  cross-checks of the reduced-order truck model.
- **Isaac Lab's default kit-less backend.** In Isaac Lab 3.0, MuJoCo-Warp under Newton (`physics=newton_mjwarp`) is
  the primary validated path [3].

It is not a granular or fluid engine: MuJoCo has no DEM, MPM or SPH. Material in the bucket comes from Warp or Newton's
MPM ([Newton](newton.md)).

Rejected alternatives:

| Alternative | Why not |
|---|---|
| MJX / Brax (JAX) | JAX has no NVIDIA GPU support on native Windows; WSL2 is experimental [4] |
| Hand-pinning the newest MuJoCo-Warp | Newton pins `mujoco-warp ~=3.12`; the pair is resolved together, never hand-pinned [5] |
| PhysX vehicles as the training simulator | PhysX Vehicle2 is CPU-focused; it stays the Isaac Sim visual twin ([PhysX / ovphysx](physx-ovphysx.md)) |

## Identity

| Item | Value |
|---|---|
| Package | `mujoco-warp` 3.12.0 and `mujoco` 3.12.0, pinned in `studio/uv.lock` through `newton[sim]` |
| Release of the pinned pair | 2026-08-20 (MuJoCo 3.12.0) [6] |
| Newest upstream at research time | 3.14.0 (2026-09-22) [2] |
| Licence | Apache-2.0 · open |
| Status upstream | "Alpha" classifier [2] |
| Ring | Trial |
| Environment | `studio/` (Python 3.14); a separate 3.11.0 copy comes with Isaac Sim in `studio/isaac/` |

## How PitStudio uses it

| Use | Case / method | Notes |
|---|---|---|
| Articulated shovel and loader cycle clips | A3 · M7 | Joint trajectories drive the bucket against MPM soil through Newton's coupling |
| Batched truck rollouts on a ramp | A1, A2 · M4, M21 | Truck as about 7–10 bodies (chassis, wheels, steering), the class of task that fits thousands of envs on 16 GB [3] |
| Isaac Lab IL-1 haul truck, IL-2 excavator | A2, A3 · M21 | Kit-less training on `newton_mjwarp` |

Artefacts it will produce: articulated cycle clips (replayed through glTF animation), batched-rollout throughput in
environments × steps per second, and policy rollouts that the TS twins replay in the browser.

## Licence and redistribution

Apache-2.0. Machine models are our own procedural MJCF/USD with dimensions from published academic sources; no OEM
meshes and no NVIDIA assets are used ([Isaac Lab](isaac-lab.md) explains why).

## Assumptions and limits

- MuJoCo Warp excludes the `IMPLICITFAST` integrator, the PGS and no-slip solvers and plugin actuators; flex
  deformables are experimental [1].
- Its README states no Windows restriction and it is pure Python on Warp, but native Windows behaviour was not
  documented upstream; the studio smoke runs it before any task code.
- **Tyre fidelity at haul-truck speeds is UNVERIFIED** with soft-contact wheels. Learned truck controllers are
  reported relative to a classical controller on the same simulator, never as absolute field claims.
- Upgrades follow Newton's pin. Moving to 3.14 means moving Newton and re-running the rigid-body benchmarks.

## In PitStudio

- Status: **not yet run** — produced in the data-and-models phase. The pair is locked and imported by the Warp/Newton probe; no articulated scene exists yet.
- Pages: [Isaac Lab](isaac-lab.md), [M21](../methods/m21-isaac-lab-policies.md),
  [Robot learning](../theory/robot-learning.md).

## References

1. Google DeepMind and NVIDIA. *MuJoCo Warp README*. https://github.com/google-deepmind/mujoco_warp
2. Python Package Index. *mujoco-warp* 3.14.0. https://pypi.org/pypi/mujoco-warp/json
3. Isaac Lab. *Physics backends* (Newton beta, MJWarp primary path).
   https://isaac-sim.github.io/IsaacLab/develop/source/concepts/physics_backends.html
4. JAX. *Installation* (no Windows-native NVIDIA GPU support). https://docs.jax.dev/en/latest/installation.html
5. Python Package Index. *newton* 1.6.0 (requires `mujoco-warp~=3.12.0`). https://pypi.org/pypi/newton/json
6. Google DeepMind. *MuJoCo releases* (3.12.0 on 2026-08-20). https://github.com/google-deepmind/mujoco/releases
