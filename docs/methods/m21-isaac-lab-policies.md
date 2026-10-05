# M21 — Isaac Lab policies: haul-truck ramp driving and excavator digging, with sim-to-sim gaps

> Robot-learning policies for a haul truck on a real ramp (with light-vehicle avoidance) and an excavator digging
> randomised soil are trained in Isaac Lab on the Newton physics backend, exported as tiny ONNX networks that drive
> TypeScript twins in the browser, and judged against classical controllers and across simulators. · Part of:
> [Methods](README.md) · Related: [Robot learning theory](../theory/robot-learning.md) ·
> [Loading and terramechanics theory](../theory/loading-and-terramechanics.md) · [Isaac Lab](../frameworks/isaac-lab.md) ·
> [Isaac Lab policy cards](../models/isaac-lab-policies.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| SOTA → beyond-SOTA (sim-to-sim gap reported) | **yes** | precompute → live (TS twins) | [A2](../cases/a2-haul-road-electrification.md) (IL-1), [A3](../cases/a3-loading-payload-variance.md) (IL-2) | Isaac Lab 3.0 (BSD-3) kit-less on Newton; `rsl_rl` PPO (BSD-3); ONNX MLP | not yet implemented |

NVIDIA and Isaac Lab are named nominatively. PitStudio is not affiliated with or endorsed by NVIDIA and never
redistributes NVIDIA binaries or assets; only our own procedural machines and our own trained policies are published.

## What and why

Earthmoving is where reinforcement learning has crossed into the field. An excavator policy trained against the
Fundamental Equation of Earth-Moving (FEE) with heavily randomised soil parameters ran on a 12-tonne excavator in
different soils [1]. A boulder-excavation policy trained in Isaac Lab with a quasi-static 2-D FEE force model reached
70 % field success against 83 % for human operators [2]. A policy trained in a GPU MPM soil simulation built a 42 m ×
2.1 m embankment with an 11.5 t excavator in 45 minutes [3]. For mining trucks, RL path tracking with a safety layer
reported a maximum lateral error of 0.22 m in the field [4].

Isaac Lab (BSD-3 [13]) earns its place only where **articulation, contact, sensors and domain randomisation** matter, so
M21 uses it for exactly two tasks and leaves dispatch to the cheaper custom environment of
[M04](m04-ppo-dispatch.md):

- **IL-1 `Pit-HaulTruck-Ramp`** (case A2): a rigid-frame haul truck drives a real ramp from the Bingham terrain,
  tracking speed limits per grade and avoiding light vehicles;
- **IL-2 `Pit-Excavator-Dig-FEE`** (case A3): an excavator digs FEE soil with randomised parameters; its policy is then
  checked **zero-shot in Newton's implicit MPM** to measure the FEE → MPM gap;
- **IL-3 (optional)** loader approach and V-cycle, sharing IL-2's dig code.

Isaac Lab ships no mining asset or mining task [5], so the machines (procedural MJCF/USD from academic dimensions)
and the tasks are PitStudio's own.

## The algorithm

### Platform

Isaac Lab 3.0 runs **kit-less on Newton** (MuJoCo-Warp backend), without installing or launching Isaac Sim [6]. It
provides the manager-based task API (observations, rewards, terminations, randomisation), vectorised resets, ray-cast
sensors and policy export [7]. The Python 3.12 environment `studio/isaaclab/` is pinned to the `v3.0.0-EA` tag and moves
to the GA tag when it ships (targeted for the end of October 2026) [6]. A Windows kit-less smoke test gates the lane;
if it fails, the lane ends as "evaluated, not adopted".

Published memory figures (desktop GPU, backend not stated): rigid-body tasks at 4,096 environments take 3.3–6.1 GB of
VRAM, while camera-in-the-loop RL at 1,024 environments takes 16.7 GB [8] — so PitStudio's tasks use ray-cast and
height-map observations, with cameras only for small evaluation runs.

### IL-1 — haul truck on a real ramp

- **Scene:** ramp segments of the Bingham terrain mesh; a procedural rigid-frame truck (chassis, six wheels, steering);
  zero to three light vehicles as kinematic bodies.
- **Observations** (about 60–90 values): speed, yaw rate, pitch; lateral and heading errors and the next 10 path points
  in the body frame; payload; a 32-beam ray-cast scan; nearest light vehicle's relative position, velocity and TTC
  ([M20](m20-traffic-ttc.md)).
- **Actions:** steering rate and throttle/retarder command in $[-1, 1]$.
- **Reward:** progress along the path; $-\lvert e_{\text{lat}}\rvert$ and $-\lvert e_{\psi}\rvert$; tracking of the
  speed limit per grade from the `minephys` rimpull/retarder envelopes ([M06](m06-haul-road-energy-routing.md)); a jerk
  penalty; a large penalty on collision or TTC below 3 s; an energy term $-\int P\,dt$.
- **Domain randomisation:** payload 0–100 %, rolling resistance, tyre–road friction, actuator delay, sensor noise.

### IL-2 — excavator digging with FEE soil

The soil reaction on the bucket follows the FEE (Reece) [9]†:

$$
F = \big(\gamma\, g\, d^2 N_\gamma + c\, d\, N_c + c_a\, d\, N_a + q\, d\, N_q\big)\, w
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $F$ | soil cutting force | N |
| $\gamma$ | bulk density | kg/m³ |
| $d$, $w$ | tool depth and width | m |
| $c$, $c_a$ | soil cohesion, soil–tool adhesion | Pa |
| $q$ | surcharge pressure | Pa |
| $N_\gamma, N_c, N_a, N_q$ | dimensionless factors from rake angle, soil friction and soil–tool friction (McKyes and Ali [10]) | – |

- **Observations:** joint positions, velocities and torques; bucket pose; a 30-sample terrain profile (as in [3]);
  fill estimate.
- **Actions:** four joint velocities (swing, boom, stick, bucket).
- **Reward:** fill-volume gain; target fill reached; penalties for stall (torque at limit), machine lift-off, joint
  limits and action rate; a cycle-time term.
- **IL-2b evaluation tier:** the trained policy runs **zero-shot** in Newton's implicit MPM coupled to the rigid bucket,
  16–64 environments, with the dry-sand material calibrated by [M09](m09-differentiable-dem-calibration.md). Coupled
  rigid–MPM in Isaac Lab is experimental, its MPM tasks were regressing at the time of writing, and no validated soil
  presets exist [11] — hence evaluation only, never training.

### Training

PPO from `rsl_rl` (Isaac Lab's default library) with the clipped objective [12], about two hidden layers of 256 units as
in the boulder-excavation precedent [2].

```text
train(task):
    env = isaaclab.make(task, physics="newton_mjwarp", num_envs=N)     # kit-less
    runner = rsl_rl.OnPolicyRunner(env, ppo_cfg)                        # PPO, 2x256 MLP
    runner.learn(iterations)
    export: our s60_export (opset 17–19, IR pinned, parity gate)        # not the built-in exporter's undocumented opset
```

Budgets (estimates; measured by the `studio bench` probe first): IL-1 1–4 GPU-hours at ≤ 5 GB; IL-2 2–8 GPU-hours at
≤ 6 GB; IL-3 a further 2–3 GPU-hours.

### TypeScript twins

Each policy also drives a light TypeScript twin in the browser: a dynamic bicycle model with the `minephys` rimpull and
retarder curves for IL-1, and the FEE force with 2-D arm kinematics for IL-2. The gap between the policy's behaviour in
Isaac Lab and in its twin is the **sim-to-sim gap**, reported and labelled as such.

## Baseline and comparison

| Task | Classical baseline | Paired unit | Metric for "better" |
|---|---|---|---|
| IL-1 | pure-pursuit steering + PID speed control | seeded episode | route success, lateral error, min TTC, energy |
| IL-2 | scripted dig trajectory | seeded episode | fill × cycle time |

Every "beats" claim follows the [decision rule](README.md#how-methods-are-compared). Sim-to-sim gaps (IL-1: Isaac Lab
vs TS twin; IL-2: FEE vs MPM) are reported with 95 % CIs, not tested for superiority. Field results from the
literature [1]–[4] are context, not targets: PitStudio's machines are generic and nothing is deployed.

## Acceptance criterion (pre-registered)

- **IL-1:** ≥ 95 % route success without collision over 100 seeded episodes; RMS lateral error ≤ 0.5 m; minimum TTC ≥ 3
  s in ≥ 99 % of episodes; "beats pure pursuit + PID" only by the decision rule; sim-to-sim gap vs the TS twin
  reported.
- **IL-2:** fill factor ≥ 0.8 in ≥ 80 % of FEE episodes; stalls ≤ 5 %; FEE → MPM fill gap reported with a 95 % CI;
  "beats scripted dig" only by the decision rule on fill × cycle time.
- Export parity for every policy (fp32 rtol 1e-3 / atol 1e-5).

**Results: Not yet run** — produced in the data-and-models phase. Reported: the acceptance metrics per task with CIs,
baseline comparisons, sim-to-sim gaps, rollout replays.

## Lane and web delivery

**Precompute → live (TS twins).** Training and Isaac Lab rollouts are precomputed; rollouts are replayed (Newton writes
time-sampled USD, converted to glTF animation and particle shards). The policies (< 1 MB each) run live in ONNX Runtime
Web driving the TypeScript twins, labelled "sim-to-sim". RTX videos of trained policies come from the Isaac Sim lane.
Fallback: replays.

## Assumptions and limits

- The FEE is quasi-static and continuum: it does not describe blocky blasted rock, which is why the MPM evaluation tier
  and [M07](m07-gpu-granular-physics.md) exist.
- MuJoCo-Warp soft-contact wheels at haul speeds are not validated; results are relative to the classical controller
  on the same simulator, with no absolute field claim.
- Isaac Lab 3.0 is early access: API churn is expected until GA; the lane is optional and droppable without affecting
  any headline KPI.
- **Educational, not autonomy software.**

## In PitStudio

- **Cases:** [A2](../cases/a2-haul-road-electrification.md) (IL-1), [A3](../cases/a3-loading-payload-variance.md)
  (IL-2, IL-2b, optional IL-3).
- **Code (planned):** `studio/isaaclab/` (task package `pitstudio_isaaclab`), stages `st60_il_train` and
  `st61_il_mpm_eval`; machines from `st30_assets`; export through `pipeline/` `s60_export`; TS twins in `web/`. Cards:
  [Isaac Lab policies](../models/isaac-lab-policies.md).
- **Status:** not yet implemented — built test-first in the build phase.

† Standard form; the transcription is checked against the primary source by a worked-example test at specification.

## References

1. Egli, P. et al. (2022). Soil-adaptive excavation using reinforcement learning. IEEE RA-L.
   https://doi.org/10.1109/LRA.2022.3189834
2. Gruetter et al. (2025). Boulder excavation with RL in Isaac Lab (PPO 2×256; 70 % field success vs 83 % human).
   https://arxiv.org/html/2509.17683
3. Werner et al. (2026). Excavator soil manipulation with RL in a GPU MPM (Warp), 42 m × 2.1 m embankment in 45 min.
   https://arxiv.org/html/2609.12677
4. Xia et al. (2025). RL path tracking for mining trucks with a safety layer (0.22 m field maximum lateral error). IEEE
   T-VT. https://doi.org/10.1109/TVT.2025.3546647
5. Isaac Lab — available environments (no vehicle, excavator or granular tasks).
   https://isaac-sim.github.io/IsaacLab/main/source/overview/environments.html
6. Isaac Lab v3.0.0-EA release note (kit-less Newton, backends, GA target).
   https://api.github.com/repos/isaac-sim/IsaacLab/releases/tags/v3.0.0-EA
7. Isaac Lab RL API (`export_policy_as_onnx`, wrappers). https://isaac-sim.github.io/IsaacLab/main/source/api/lab_rl/isaaclab_rl.html
8. Isaac Lab performance benchmarks (VRAM per environment count).
   https://isaac-sim.github.io/IsaacLab/main/source/overview/reinforcement-learning/performance_benchmarks.html
9. Reece, A. R. (1964). The fundamental equation of earth-moving mechanics. Proc. IMechE 179(6):16–22.
   https://doi.org/10.1243/PIME_CONF_1964_179_134_02
10. McKyes, E. & Ali, O. S. (1977). The cutting of soil by narrow blades. Journal of Terramechanics 14:43–58.
    https://doi.org/10.1016/0022-4898(77)90001-5
11. Isaac Lab issue #8236 — tuned and validated Newton MPM material presets; PR #8106 — MPM task regression.
    https://github.com/isaac-sim/IsaacLab/issues/8236 · https://github.com/isaac-sim/IsaacLab/pull/8106
12. Schulman, J. et al. (2017). *Proximal Policy Optimization Algorithms*. https://arxiv.org/abs/1707.06347
13. Isaac Lab repository licence (BSD-3-Clause). https://github.com/isaac-sim/IsaacLab/blob/develop/LICENSE
