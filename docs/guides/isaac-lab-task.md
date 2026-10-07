# Isaac Lab task

> Train and evaluate PitStudio's Isaac Lab policies — IL-1 haul truck on a real ramp with light-vehicle avoidance, IL-2
> excavator digging with a zero-shot check in a granular MPM model, IL-3 loader (optional) — kit-less on Newton, then
> export them as small ONNX policies that run in the browser through TypeScript twins. · Part of: [Guides](README.md) ·
> Related: [Isaac Lab](../frameworks/isaac-lab.md) · [M21 Isaac Lab policies](../methods/m21-isaac-lab-policies.md) ·
> [robot learning](../theory/robot-learning.md) · [Isaac Lab policy cards](../models/isaac-lab-policies.md)

## What and why

**Goal:** learn control policies for two mining machines in GPU-vectorised simulation and measure, honestly, how far
they transfer between simulators. Reinforcement learning for earthmoving has field-validated precedents: soil-adaptive
excavation trained with randomised soil in a Fundamental-Earthmoving-Equation model [1], a boulder-excavation policy
trained in Isaac Lab that reached 70 % field success against 83 % for a human operator [2], and RL path tracking for
mining trucks with 0.05 m error in simulation and 0.22 m in the field [3]. PitStudio reproduces the *method* on its own
procedural machines and reports **sim-to-sim** gaps (FEE → MPM; Isaac Lab → TypeScript twin); it has no real machine,
so it makes no sim-to-real claim.

**Status:** an optional lane. The environment `studio/isaaclab/` is locked; the tasks, recipes and stages
`st60_il_train` / `st61_il_mpm_eval` are written in the build phase. Isaac Lab kit-less on Windows has no upstream test
evidence yet, so the first step is a smoke run; if the lane does not run, its tool page says "evaluated, not adopted"
with the reason, and no headline KPI depends on it.

## Prerequisites

- [Set up the studio](set-up-the-studio.md): `studio/isaaclab/` synced on a uv-managed Python 3.12. It pins Isaac Lab to
  the `v3.0.0-EA` tag, which brings its own pins (PyTorch 2.11, Warp 1.16, Newton 1.5.2) [4]; it moves to the GA tag
  when that ships.
- Isaac Lab's documented floor: 32 GB RAM and 16 GB VRAM; Windows driver 581.42 recommended (CUDA 13 PyTorch needs
  580.88 or newer); Windows long paths enabled before cloning [5].
- Kit-less means **no Isaac Sim**: "Kit-less Newton workflows do not require Isaac Sim" [6]. The Newton backend is in
  beta, MuJoCo-Warp is its primary validated path, and its coverage is "narrower and task-specific" [7].
- Scene inputs from the open lane: the Bingham ramp profile (`st10_terrain`, `st20_pit_design`).

## The tasks

| Task | Machine and goal | Observations | Acceptance (pre-registered) | Budget (estimate) |
|---|---|---|---|---|
| IL-1 | Procedural haul truck drives a real Bingham ramp and avoids a light vehicle | ray caster / heightmap + state | ≥ 95 % route success without collision over 100 seeded episodes; RMS lateral error ≤ 0.5 m; minimum TTC ≥ 3 s in ≥ 99 % of episodes; "beats pure pursuit + PID" only by the decision rule; sim-to-sim gap vs the TS twin reported | 1–4 GPU-h, ≤ 5 GB |
| IL-2 | Procedural excavator digs FEE soil; then a zero-shot check in Newton MPM | joint state + soil heightmap | fill factor ≥ 0.8 in ≥ 80 % of FEE episodes; stalls ≤ 5 %; FEE → MPM fill gap reported with a 95 % CI; "beats scripted dig" only by the decision rule on fill × cycle time | 2–8 GPU-h, ≤ 6 GB |
| IL-3 (optional) | Loader | as IL-2 | as IL-2 | 2–3 GPU-h |

**No cameras in the training loop.** NVIDIA's own figures show 1,024 camera environments of a cart-pole task using
16.7 GB of VRAM, against 3.3 GB for 4,096 state-only environments [8]; on a 16 GB GPU, observations are ray casts and
heightmaps, and cameras are used only for small-N evaluation and videos.

## Steps

1. **Smoke-test the lane** with Isaac Lab's own example before any PitStudio task. The upstream documentation shows this
   form on Windows (illustrative; run inside the Isaac Lab project):

   ```bash
   uv run isaaclab train --rl_library rsl_rl --task Isaac-Cartpole-Direct physics=newton_mjwarp
   ```

   The capability probe wraps the same check once its `isaaclab` probe script exists:

   ```bash run deferred=P6
   uv run --extra runner python studio/bench/run_bench.py isaaclab
   ```

2. **Train IL-1** with RSL-RL PPO under the GPU lock. The recipe fixes the seeds, the number of environments and the
   iterations.

   ```bash run deferred=P6
   uv run --extra runner studio run studio/recipes/cases/a2.yaml --stage st60_il_train
   ```

3. **Train IL-2** on FEE soil, then run the zero-shot MPM evaluation. Newton's MPM material parameters are not
   validated upstream (an open issue asks for tuned presets [9]), so the MPM soil uses the parameters recovered by
   PitStudio's DEM calibration ([M9](../methods/m09-differentiable-dem-calibration.md)).

   ```bash run deferred=P6
   uv run --extra runner studio run studio/recipes/cases/a3.yaml --stage st60_il_train
   uv run --extra runner studio run studio/recipes/cases/a3.yaml --stage st61_il_mpm_eval
   ```

4. **Export and check parity.** Isaac Lab exports a policy with `export_policy_as_onnx(...)`; its opset is not
   documented [10], so PitStudio's export stage sets opset 17–19 and runs the parity gate against PyTorch, then the TS
   twin is checked against the exported policy.

   ```bash run deferred=P6
   scripts/run_pipeline.sh --stage s60_export
   ```

5. **Publish** the learning curves, evaluation tables and rollout videos.

   ```bash run deferred=P6
   uv run --extra runner studio publish <run_id>
   ```

## Expected output

- Per task: checkpoints in `PITSTUDIO_MODELS`, an ONNX MLP below 1 MB, evaluation tables over the seeded episodes with
  confidence intervals, rollout videos (encoded as in [encode videos](encode-videos.md)) and the run manifest.
- On the web: the Isaac Lab tool page with learning curves and rollouts (REPLAY), and the policies driving TS twins
  live on the A2 and A3 case pages (LIVE).
- Today: **Not yet run** — produced in the data-and-models phase.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Quaternion signs look wrong after an upgrade | Isaac Lab 3.0 returns quaternions in `xyzw` order (a breaking change) [11] | pin one commit; convert at the adapter |
| Out of memory | too many environments or camera observations | reduce environments; no cameras in the loop |
| A Linux-only feature is missing | Pink IK tasks are Linux-only [4]; multi-GPU training is Linux-only because of NCCL [12] | not needed by these tasks; multi-GPU belongs to a Linux host |
| The kit-less run fails on Windows | untested upstream | record the failure; the tool page becomes "evaluated, not adopted" |

## Assumptions and limits

- Machines are procedural, with generic parameters from academic sources, not any manufacturer's machine.
- FEE soil is quasi-static and continuum; it does not describe blocky blasted rock. The MPM check measures the gap, it
  does not close it.
- Results are sim-to-sim only. They are educational and not a basis for operating real equipment.

## In PitStudio

- Cases [A2](../cases/a2-haul-road-electrification.md) (IL-1) and [A3](../cases/a3-loading-payload-variance.md) (IL-2,
  IL-3); method [M21](../methods/m21-isaac-lab-policies.md); spec `014-robot-learning`.

## References

1. Egli, P. et al. (2022), "Soil-Adaptive Excavation Using Reinforcement Learning", IEEE Robotics and Automation Letters. https://doi.org/10.1109/LRA.2022.3189834
2. Gruetter, et al. (2025), boulder excavation with an Isaac Lab–trained policy — 70 % field success vs 83 % human. https://arxiv.org/html/2509.17683
3. Xia, et al. (2025), RL path tracking for mining trucks, IEEE Transactions on Vehicular Technology — 0.05 m simulated, 0.22 m field error. https://doi.org/10.1109/TVT.2025.3546647
4. Isaac Lab, v3.0.0-EA release note — kit-less execution, pins, Pink IK Linux-only, `isaaclab.sh` deprecated, GA end of October 2026. https://api.github.com/repos/isaac-sim/IsaacLab/releases/tags/v3.0.0-EA
5. Isaac Lab, "Installation" (develop) — Python 3.12, 32 GB RAM / 16 GB VRAM, drivers, long paths, kit-less commands. https://isaac-sim.github.io/IsaacLab/develop/source/setup/installation/index.html
6. Isaac Lab, README — BSD-3-Clause; "Kit-less Newton workflows do not require Isaac Sim". https://github.com/isaac-sim/IsaacLab
7. Isaac Lab, "Physics backends" — Newton (beta; MJWarp, Kamino, VBD, MPM), OVPhysX experimental. https://isaac-sim.github.io/IsaacLab/develop/source/concepts/physics_backends.html
8. Isaac Lab, published environment memory and throughput figures (Cartpole state vs RGB camera). https://isaac-sim.github.io/IsaacLab/main/source/overview/reinforcement-learning/performance_benchmarks.html
9. Isaac Lab issue #8236, "Tuned and validated Newton MPM material presets" (opened 2026-10-01). https://github.com/isaac-sim/IsaacLab/issues/8236
10. Isaac Lab, RL wrappers and policy export (`export_policy_as_onnx`). https://isaac-sim.github.io/IsaacLab/main/source/api/lab_rl/isaaclab_rl.html
11. Isaac Lab, "Newton physics integration (beta 2)" — `xyzw` quaternion convention. https://isaac-sim.github.io/IsaacLab/main/source/experimental-features/newton-physics-integration/isaaclab_newton-beta-2.html
12. Isaac Lab, "Multi-GPU and multi-node training" — Linux-only (NCCL). https://isaac-sim.github.io/IsaacLab/main/source/features/multi_gpu.html
