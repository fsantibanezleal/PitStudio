# Isaac Lab policies — IL-1 haul truck, IL-2 excavator, IL-3 loader (optional)

> Small reinforcement-learning policies for articulated mining machines, trained in Isaac Lab 3.0 on the Newton physics
> backend and shown live in the browser on lightweight twins, with the sim-to-sim gap reported. · Part of:
> [Models](README.md) · Related: [M21 Isaac Lab policies](../methods/m21-isaac-lab-policies.md) ·
> [Isaac Lab](../frameworks/isaac-lab.md) · [Robot learning](../theory/robot-learning.md) ·
> [Case A3](../cases/a3-loading-payload-variance.md)

## What and why

Isaac Lab is worth its cost where **articulation, contact, sensors and domain randomisation** matter: a truck on a
real ramp and a bucket in soil. Published precedents exist for both. Gruetter et al. trained a boulder-excavation policy
in an Isaac Lab environment with an earth-moving force model and reached 70 % field success against 83 % for human
operators [1]; Egli et al. trained soil-adaptive excavation on heavily randomised soil and ran it on a 12 t excavator
[2]; Xia et al. report RL path tracking for mining trucks with under 0.05 m mean lateral error in simulation and 0.22 m
maximum in the field [3]. Isaac Lab itself is a GPU-parallel robot-learning framework with a manager-based task API
[4]. Isaac Lab ships no vehicle, excavator or mining task, so every task here is ours. This is an **optional lane**: it
never carries a headline KPI and may end as "evaluated, not adopted".

## Model card

### Intended use

- **IL-1** — haul truck on a real ramp: path following, grade-appropriate speed, light-vehicle avoidance (cases A2, B1).
- **IL-2** — excavator digging in soil modelled by the Fundamental Equation of Earth-Moving (FEE), plus a zero-shot
  check of the same policy in Newton implicit MPM (case A3). **IL-3** (optional) — wheel-loader approach to the truck.
- Live browser demos on TS twins, labelled "sim-to-sim".

### Out of scope

- Controlling real machines or any field claim; results are relative to classical controllers in the same simulator.
- Camera-observation RL: 1,024 camera envs need 16.7 GB VRAM in NVIDIA's own benchmark [5]; observations are ray casts
  and heightmaps. Fleet dispatch (see [dispatch policies](dispatch-policies.md)) and drone survey planning.

### Architecture

Actor–critic MLPs (e.g. two hidden layers of 256, the Gruetter precedent [1]) trained with **rsl_rl PPO** (BSD-3) [6];
the clipped PPO objective is given in the [dispatch card](dispatch-policies.md). Environments use Isaac Lab 3.0
**kit-less on Newton** (MuJoCo-Warp backend), without Isaac Sim [7]. Task designs (fixed in the robot-learning spec):

| | IL-1 haul truck | IL-2 excavator (FEE) |
|---|---|---|
| Scene | Bingham DEM ramp segments; procedural rigid-frame truck (chassis, 6 wheels, steering); 0–3 light vehicles | Procedural excavator (swing, boom, stick, bucket); FEE soil with heavily randomised parameters [2] |
| Observations | speed, yaw rate, pitch; lateral and heading error; next 10 path points; payload; 32-beam ray scan; nearest light vehicle and its TTC (≈ 60–90-D) | joint positions, velocities, torques; bucket pose; 30-sample terrain profile; fill estimate |
| Actions | steering rate; throttle/retarder in [−1, 1] | 4 joint velocities |
| Reward | progress; −lateral/heading error; grade speed limit from `minephys` envelopes; jerk; collision or TTC < 3 s penalty; energy | fill gain; target fill; stall, lift-off, joint-limit and action-rate penalties; cycle time |
| Randomisation | payload 0–100 %, rolling resistance 2–8 %, wet/dry μ, actuator delay, sensor noise | soil parameters |
| Baseline | pure pursuit + PID speed control | scripted dig trajectory |

**FEE** (Reece) gives the soil reaction on a tool [8]:

$$
F=\big(\gamma g\,d^{2}N_\gamma+c\,d\,N_c+c_a\,d\,N_a+q\,d\,N_q\big)\,w
$$

$F$ force (N), $d$ tool depth (m), $w$ width (m), $\gamma$ bulk density (kg/m³), $g$ gravity (m/s²), $c$ cohesion (Pa),
$c_a$ soil–tool adhesion (Pa), $q$ surcharge (Pa), and $N$ dimensionless factors set by rake angle and friction.

**Pure pursuit** steers toward a goal point at look-ahead distance $l$ (m) on the path with curvature
$\kappa = 2x/l^{2}$ (1/m), $x$ being the goal point's lateral offset in the vehicle frame (m) [9]; steering angle
$\delta=\arctan(L\kappa)$ for wheelbase $L$ (m). **Time to collision** with a light vehicle at distance $r$ (m) closing
at $-\dot r>0$ (m/s) is $\mathrm{TTC}=r/(-\dot r)$ (s).

**IL-2b — MPM evaluation tier.** The IL-2 policy runs zero-shot in Newton implicit MPM coupled to the rigid bucket
(16–64 envs), with a dry-sand material from [DEM calibration](dem-calibration.md). Coupled rigid–MPM is experimental in
Isaac Lab (contrib, beta) and an open MPM tuning PR reports a regression (2/20 vs 64/64 successes) [10], so MPM is an
evaluation tier only. **IL-3** follows the loader-approach precedent of Borngrund et al. [11].

### Training data

None collected: all experience is simulated. Inputs are our procedural MJCF/USD machines (code Apache-2.0, geometry
CC-BY-4.0, dimensions from published academic sources) and USGS 3DEP terrain (public domain). No NVIDIA asset is used;
Isaac Lab's licensed assets cover robots only [12].

### Budget (estimate)

| Policy | GPU-h | VRAM | Basis |
|---|---|---|---|
| IL-1 | **1–4** | **≤ 5 GB** | ~2,048 envs, 0.2–0.5 B steps |
| IL-2 | **2–8** | **≤ 6 GB** | 2–4k FEE envs |
| IL-3 (optional) | **+2–3** | — | shares IL-2 dig code |

NVIDIA's own table (RTX 4090, backend not stated) shows 3.3 GB for 4,096 Cartpole envs and 6.1 GB for a humanoid [5];
our laptop numbers are unmeasured. The runner probe `studio bench` and Isaac Lab's `benchmark` command measure them
before any long run; the GPU probes are written but not yet run on the reference machine.

### Export and web lane

- Isaac Lab's `export_policy_as_onnx` does not document its opset [13], so the checkpoint is handed (file-only,
  schema-validated) to `pipeline/` `s60_export`: **opset 17** (an MLP needs only Gemm and element-wise ops), IR version
  **pinned to 10**, `verify=True`, observation normaliser exported with the policy; parity rtol 1e-3 / atol 1e-5 /
  max abs 1e-4 on ≥ 200 golden observations.
- **< 1 MB → LIVE** on TS twins: a bicycle-model truck twin (IL-1) and a TS port of the FEE force with 2-D arm
  kinematics (IL-2), labelled "sim-to-sim"; Newton/Isaac Lab rollouts are REPLAY.
- **TensorRT relevance — none expected** at batch 1 (launch-bound MLP); included in the bench for completeness.

### Pre-registered acceptance criteria

- **IL-1:** ≥ 95 % route success without collision over 100 seeded episodes; RMS lateral error ≤ 0.5 m; min TTC ≥ 3 s
  in ≥ 99 % of episodes; "beats pure pursuit + PID" only by the decision rule; sim-to-sim gap vs the TS twin reported.
- **IL-2:** fill factor ≥ 0.8 in ≥ 80 % of FEE episodes; stalls ≤ 5 %; FEE → MPM fill gap reported with 95 % CI;
  "beats scripted dig" only by the decision rule on fill × cycle time.
- Decision rule: paired 95 % CI of the difference excludes 0
  ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

### Evaluation protocol

- 100 seeded episodes per policy and baseline, the same seeds for both (paired). Worked example: 95 successes in 100
  episodes have a Wilson 95 % interval of [0.89, 0.98] [14] — the criterion is on the observed rate, the interval is
  reported with it. "≥ 99 % of episodes" allows at most one episode of 100 with min TTC below 3 s.
- Fill factor = loaded volume / rated heaped bucket volume (–); a stall = joint torque at its limit for longer than a
  threshold fixed in the spec.
- Sim-to-sim: the IL-1 policy runs on the TS truck twin with the same seeds; the IL-2 policy runs in MPM; gaps are
  reported with 95 % CIs, never hidden.

### Licence of weights

Isaac Lab is BSD-3 [15]; rsl_rl is BSD-3 [6]; Newton is Apache-2.0. Isaac Sim (proprietary) is not installed in this
kit-less lane. Our task code, machine models and terrain are Apache-2.0 / CC-BY-4.0 / public domain → policies
**Apache-2.0 + attribution**. Training throughput is recorded in the manifest; publication follows the performance-data
rule ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

## Assumptions and limits

- Kit-less Isaac Lab on Windows is untested by us; the v3.0.0-EA API changes before GA (e.g. quaternions now `xyzw`)
  [7]. If the smoke test fails, the lane ends "evaluated, not adopted" and nothing else is blocked.
- Tyre–road contact at haul speeds (MuJoCo-Warp soft contacts) is unvalidated; results are relative to the classical controller on
  the same simulator, never absolute field claims.
- MPM materials have no validated presets upstream; our dry sand comes from our own calibration.
- Simulation-grade twin, not a live digital twin.

## In PitStudio

- **Cases:** [A2](../cases/a2-haul-road-electrification.md) and [B1](../cases/b1-traffic-proximity.md) (IL-1),
  [A3](../cases/a3-loading-payload-variance.md) (IL-2, IL-3). **Method:** [M21](../methods/m21-isaac-lab-policies.md).
- **Env:** `studio/isaaclab/` — Python 3.12, Isaac Lab pinned to the v3.0.0-EA tag (BSD-3), local-only, never in CI.
- **Stages:** `st60_il_train` (IL-1, IL-2, IL-3) → `st61_il_mpm_eval` → `pipeline/` `s50_evaluate` → `s60_export` →
  `pipeline/accel/` `s62_accel` / `s64_bench`. Guide: [Isaac Lab task](../guides/isaac-lab-task.md).
- **Artefacts:** `models/onnx/` (< 1 MB each), `models/cards/`; replays of rollouts as glTF/shards.

## Results

**Not yet trained** — produced in the data-and-models phase. Will be reported: IL-1 route success, RMS and max lateral
error, min-TTC distribution, energy per t·km, paired comparison with pure pursuit + PID, and the TS-twin gap; IL-2 fill
factor distribution, stall rate, cycle time, paired comparison with the scripted dig, and the FEE → MPM fill gap with
95 % CI; IL-3 only if run; ONNX parity. Or "evaluated, not adopted" with the reason.

## References

1. Gruetter et al. (2025). Boulder excavation with RL trained in Isaac Lab (FEE, PPO 2×256, 70 % vs 83 %).
   https://arxiv.org/abs/2509.17683
2. Egli, P. et al. (2022). Soil-adaptive excavation using reinforcement learning. IEEE RA-L.
   https://doi.org/10.1109/LRA.2022.3189834
3. Xia et al. (2025). RL path tracking for mining trucks. IEEE Trans. Veh. Technol.
   https://doi.org/10.1109/TVT.2025.3546647
4. Mittal, M. et al. (2025). *Isaac Lab: A GPU-Accelerated Simulation Framework for Multi-Modal Robot Learning*.
   https://doi.org/10.48550/arXiv.2511.04831
5. Isaac Lab performance benchmarks (RAM/VRAM per env count).
   https://isaac-sim.github.io/IsaacLab/main/source/overview/reinforcement-learning/performance_benchmarks.html
6. `rsl-rl-lib` on PyPI (BSD-3, PPO). https://pypi.org/pypi/rsl-rl-lib/json
7. Isaac Lab v3.0.0-EA release note (kit-less Newton, backends, GA target).
   https://api.github.com/repos/isaac-sim/IsaacLab/releases/tags/v3.0.0-EA
8. Reece, A. R. (1964). The fundamental equation of earth-moving mechanics. Proc. IMechE 179(6).
   https://doi.org/10.1243/PIME_CONF_1964_179_134_02
9. Coulter, R. C. (1992). *Implementation of the Pure Pursuit Path Tracking Algorithm*. CMU-RI-TR-92-01.
   https://publications.ri.cmu.edu/implementation-of-the-pure-pursuit-path-tracking-algorithm/
10. Isaac Lab PR #8106 (MPM task tuning, open regression). https://github.com/isaac-sim/IsaacLab/pull/8106
11. Borngrund et al. (2024). Loader approach RL with direct sim-to-real transfer. https://arxiv.org/abs/2406.13366
12. Isaac Lab asset licence files (robots only).
    https://api.github.com/repos/isaac-sim/IsaacLab/contents/docs/licenses/assets?ref=develop
13. `isaaclab_rl` API (`export_policy_as_onnx`). https://isaac-sim.github.io/IsaacLab/main/source/api/lab_rl/isaaclab_rl.html
14. Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. JASA 22(158):209–212.
    https://doi.org/10.1080/01621459.1927.10502953
15. Isaac Lab LICENSE (BSD-3-Clause). https://github.com/isaac-sim/IsaacLab/blob/develop/LICENSE
