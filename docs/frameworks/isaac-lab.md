# Isaac Lab

> The open robot-learning framework on Newton, used in an optional lane for two mining policies: a haul truck driving
> a real ramp and an excavator digging. · Part of: [Frameworks](README.md) · Related: [Newton](newton.md) ·
> [MuJoCo-Warp](mujoco-warp.md) · [M21 Isaac Lab policies](../methods/m21-isaac-lab-policies.md) ·
> [Isaac Lab policies model card](../models/isaac-lab-policies.md)

## What and why

Isaac Lab is a GPU-parallel framework for robot learning, the successor of Isaac Gym: a task API with managers for
observations, rewards, terminations, events and curricula, terrains, sensors, domain randomisation, wrappers for four
RL libraries and policy export [1]. Version 3.0 adds "one task API across multiple physics, rendering, and
visualization backends; kit-less execution", so many workflows run "without installing or launching Isaac Sim", on
Newton [2].

Why PitStudio uses it, and only for two tasks:

- Isaac Lab earns its place where **articulation, contact, sensors and domain randomisation** all matter: an excavator
  digging and a truck on real terrain with ray-cast perception.
- There is a published precedent: a boulder-excavation policy trained in Isaac Lab with a Fundamental Equation of
  Earth-Moving (FEE) soil model reached 70 % field success against 83 % for human operators [3]. Soil-adaptive
  excavation with FEE and randomised soil was field-tested on a 12 t excavator (Egli et al. 2022, DOI
  10.1109/LRA.2022.3189834) [4].

Rejected uses: fleet dispatch (no physics; our batched PyTorch environment does it), drone survey planning (Isaac
Lab's quadcopter tasks are thrust-level control), and camera-observation RL, because 1,024 camera environments need
16.7 GB of VRAM in NVIDIA's own benchmark [5]. Isaac Lab ships no mining task and no mining asset; everything mining
is ours [6].

## Identity

| Item | Value |
|---|---|
| Source | GitHub tag **v3.0.0-EA** (2026-09-16), commit `ae37b02`, pinned in `studio/isaaclab/uv.lock` [7] |
| Packages in the lock | `isaaclab` 17.0.2, `isaaclab-newton` 5.4.1, `isaaclab-rl` 0.16.3, `isaaclab-assets` 0.7.1 (+ `isaaclab-contrib`, `isaaclab-physx`, `isaaclab-tasks`) |
| Torch and runtime | the tag's tested stack, mirrored from upstream's root `pyproject.toml`: torch 2.11.0+cu128, Warp 1.16.0, Newton 1.5.2, MuJoCo / MuJoCo-Warp 3.11.0, rsl-rl-lib 5.4.1, usd-exchange 2.3.0 (168 locked packages) |
| Licence | BSD-3-Clause; `isaaclab_mimic` Apache-2.0 [8] |
| Class | open (full Isaac Sim workflows pull proprietary components; the kit-less lane does not) |
| Ring | Assess (optional lane) |
| Environment | `studio/isaaclab/` (Python 3.12, uv-managed), separate from `studio/isaac/` |
| GA | targeted for the end of October 2026 [2] |
| PyPI `isaaclab` | 2.3.2.post1 (Python 3.11, proprietary label) is superseded and **not used** [9] |

## How PitStudio uses it

| Task | Scene and model | Acceptance (pre-registered) |
|---|---|---|
| **IL-1** haul truck on a real ramp with light-vehicle avoidance | Bingham ramp mesh as terrain; our procedural rigid-frame truck (chassis, 6 wheels, steering); 0–3 kinematic light vehicles; 32-beam ray-cast scan | ≥ 95 % route success without collision over 100 seeded episodes; RMS lateral error ≤ 0.5 m; min time-to-collision ≥ 3 s in ≥ 99 % of episodes; "beats pure pursuit + PID" only by the decision rule; sim-to-sim gap vs the TS twin reported |
| **IL-2** excavator dig (FEE soil) + zero-shot MPM check | Our procedural excavator; FEE force model with randomised soil; 30-sample terrain profile | fill factor ≥ 0.8 in ≥ 80 % of FEE episodes; stalls ≤ 5 %; FEE → MPM fill gap with a 95 % CI; "beats scripted dig" only by the decision rule |
| **IL-3** loader short-loading (optional) | shares the dig code | — |

Training uses rsl_rl PPO on the `newton_mjwarp` backend, in stage `st60_il_train`; the MPM check is
`st61_il_mpm_eval` on Newton's implicit MPM ([Newton](newton.md)). Budgets are estimates: IL-1 1–4 GPU-hours at
≤ 5 GB, IL-2 2–8 GPU-hours at ≤ 6 GB. Policies are small MLPs exported to ONNX by our own `s60_export` with the
opset pinned and the parity gate, because `export_policy_as_onnx` does not document its opset [10]. In the browser
they run **live** on TS twins of the truck and the arm, labelled "sim-to-sim".

## Licence and redistribution

BSD-3-Clause for Isaac Lab; our tasks are Apache-2.0 code in our repo, with no copied Isaac Lab source. Isaac Lab's
hosted assets cover only a few robots (ANYmal, Franka, Kinova, Robotiq, Unitree, Valkyrie) [11]; we use none of them.
OEM-named open machine models are used, at most, as dimension references.

## Assumptions and limits

- **Pins drift between the tag and the branch.** The EA tag was "built for Isaac Sim 6.1, Python 3.12, PyTorch 2.11,
  NVIDIA Warp 1.16, and Newton 1.5.2" [2]; the moving `release/3.0.0` branch later pinned torch 2.12, Warp 1.17 and
  Newton 1.6 [12]. Isaac Lab's packages declare no third-party dependencies: upstream keeps them in its
  repository-root `pyproject.toml`, which a git subdirectory install never reads. PitStudio therefore mirrors that
  list and its tested overrides (torch 2.11.0 from the cu128 index on Windows, Warp 1.16.0, Newton 1.5.2) in
  `studio/isaaclab/pyproject.toml`; the lock now holds that set. The kit-less smoke validates it before any task code;
  if it fails, the lane ends as "evaluated, not adopted".
- **Kit-less on Windows is untested by us**; the only documented Windows gap is Pink IK, which we do not use [2].
- 16 GB of VRAM is the stated floor, not headroom [13]. Multi-GPU training is Linux-only because of NCCL [14].
- Coupled rigid–MPM is beta, in `isaaclab_contrib`, and one of its MPM tasks shows an open regression; no validated soil
  presets exist [15][16]. MPM stays an evaluation tier.
- EA API churn (for example quaternions moved to `xyzw`) [17].

## In PitStudio

- Probe: Isaac Lab kit-less smoke after the GPU hold ([Capabilities probe](../studio/capabilities-probe.md)).
- Guide: [Isaac Lab task](../guides/isaac-lab-task.md). Case: [A2](../cases/a2-haul-road-electrification.md),
  [A3](../cases/a3-loading-payload-variance.md).
- Status: **not yet run** — produced in the data-and-models phase. Reported then: the acceptance criteria in the table above,
  each with its 95 % CI.

## References

1. Mittal, M. et al. (2025). *Isaac Lab: A GPU-Accelerated Simulation Framework for Multi-Modal Robot Learning*. DOI
   10.48550/arXiv.2511.04831
2. Isaac Lab. *v3.0.0-EA release note*. https://api.github.com/repos/isaac-sim/IsaacLab/releases/tags/v3.0.0-EA
3. Gruetter et al. (2025). arXiv 2509.17683 (boulder excavation; training environment in Isaac Lab).
   https://arxiv.org/html/2509.17683
4. Egli, P. et al. (2022). *Soil-Adaptive Excavation Using Reinforcement Learning*. IEEE RA-L. DOI 10.1109/LRA.2022.3189834
5. Isaac Lab. *Performance benchmarks*. https://isaac-sim.github.io/IsaacLab/main/source/overview/reinforcement-learning/performance_benchmarks.html
6. Isaac Lab. *Available environments*. https://isaac-sim.github.io/IsaacLab/main/source/overview/environments.html
7. Isaac Lab. *Releases (API)*. https://api.github.com/repos/isaac-sim/IsaacLab/releases?per_page=8
8. Isaac Lab. *LICENSE*. https://github.com/isaac-sim/IsaacLab/blob/develop/LICENSE
9. Python Package Index. *isaaclab*. https://pypi.org/project/isaaclab/
10. Isaac Lab. *isaaclab_rl API* (policy export). https://isaac-sim.github.io/IsaacLab/main/source/api/lab_rl/isaaclab_rl.html
11. Isaac Lab. *Asset licences*. https://api.github.com/repos/isaac-sim/IsaacLab/contents/docs/licenses/assets?ref=develop
12. Isaac Lab. *release/3.0.0 pyproject.toml*. https://raw.githubusercontent.com/isaac-sim/IsaacLab/release/3.0.0/pyproject.toml
13. Isaac Lab. *Installation (develop)*. https://isaac-sim.github.io/IsaacLab/develop/source/setup/installation/index.html
14. Isaac Lab. *Multi-GPU training*. https://isaac-sim.github.io/IsaacLab/main/source/features/multi_gpu.html
15. Isaac Lab. *Pull request #8106 (MPM pour/push tuning)*. https://github.com/isaac-sim/IsaacLab/pull/8106
16. Isaac Lab. *Issue #8236 (validated MPM material presets)*. https://github.com/isaac-sim/IsaacLab/issues/8236
17. Isaac Lab. *Newton integration, beta 2*. https://isaac-sim.github.io/IsaacLab/main/source/experimental-features/newton-physics-integration/isaaclab_newton-beta-2.html
