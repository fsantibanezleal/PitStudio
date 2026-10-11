# Spec 014 — Robot learning (M21): Isaac Lab haul-truck and excavator policies with sim-to-sim gaps
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Earthmoving is one of the few heavy-industry domains where learned controllers have been tested on full-size machines.
This feature trains two policies, plus an optional third, as **measured experiments**. Each is compared with a
classical controller on the same simulator and transferred unchanged to a second simulator, so that a **sim-to-sim
gap** can be reported. The policies are trained in Isaac Lab 3.0 run **kit-less on Newton** (MuJoCo-Warp backend) in
`studio/isaaclab/`. That environment is locked to the v3.0.0-EA tested stack: torch 2.11.0 cu128, Warp 1.16.0, Newton
1.5.2, rsl-rl 5.4.1.

- **IL-1 `Pit-HaulTruck-Ramp`.** A procedural haul truck drives a real Bingham ramp and avoids light vehicles.
  Baseline: pure pursuit + PID. Twin: a dynamic-bicycle TypeScript model.
- **IL-2 `Pit-Excavator-Dig-FEE`.** A procedural excavator digs soil modelled by the fundamental earthmoving equation
  (FEE). The same policy is then checked zero-shot in Newton's implicit MPM (IL-2b). Baseline: a scripted dig.
- **IL-3** (optional). A loader that shares IL-2's dig code.

Policies are small ONNX MLPs (< 1 MB) that drive TypeScript twins live in the browser. The lane is optional: if the
kit-less smoke fails on Windows, it ends as "evaluated, not adopted" and no headline KPI is affected.

**Who benefits:** automation teams and students asking whether simulation-trained controllers drive a ramp or fill a
bucket reliably; reviewers who need paired, pre-registered comparisons.

**Out of scope:**
- controlling real machines, or any field claim;
- camera-observation RL (VRAM);
- fleet dispatch (spec 007);
- MPM-in-the-loop training (evaluation tier only);
- Isaac Sim (not installed in this lane);
- NVIDIA or Isaac Lab robot assets.

## 2. User stories

| ID | Priority | Story | Independent test |
|---|---|---|---|
| US-014-1 | P1 | As an automation engineer, I want a haul-truck policy evaluated on 100 seeded ramp episodes against pure pursuit + PID, with route success, lateral error, minimum TTC and energy and their confidence intervals, so that I can judge it against a classical controller. | The evaluation module reproduces hand-calculated verdicts on synthetic paired episode tables. |
| US-014-2 | P1 | As a loading supervisor, I want an excavator dig policy scored on fill factor, stalls and productivity against a scripted dig, and its fill gap when the soil model changes to MPM, so that I know how robust the result is. | The FEE core matches its worked example and equilibrium oracle; gap statistics match hand calculation. |
| US-014-3 | P1 | As the maintainer, I want the lane gated by a kit-less smoke test and locked to the tested stack, ending as "evaluated, not adopted" if it fails, so that an early-access framework never blocks the product. | A failing probe fixture produces skipped stages, an `evaluated-not-adopted` registry entry and the web state. |
| US-014-4 | P2 | As a web visitor, I want each policy to drive a light twin live in my browser, labelled "sim-to-sim", so that I can see the behaviour and understand the gap. | TS twins match the Python twins on goldens; the ONNX policy runs within the ORT-web tolerance. |
| US-014-5 | P3 | As an automation engineer, I want an optional loader policy reported with IL-2's metrics, or "not run". | The IL-3 panel shows metrics or "not run". |

## 3. Functional requirements (EARS)

### 3.1 Lane gating and environment

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-01 | Ubiquitous | `studio/isaaclab/uv.lock` shall pin the Isaac Lab packages to tag v3.0.0-EA at a commit beginning `ae37b02`, torch 2.11.0 and torchvision 0.26.0 from the cu128 index, warp-lang 1.16.0, newton 1.5.2, mujoco and mujoco-warp 3.11.x and rsl-rl-lib 5.4.1, and every IL stage manifest shall report these versions read from the lock. | contract (lock parser, CI) |
| FR-014-02 | Event | When the `isaaclab` capability probe runs, it shall train Isaac Lab's stock Cartpole direct task kit-less on the `newton_mjwarp` physics backend for ≥ 10 PPO iterations with Isaac Sim absent, and record `pass` only if training finishes with finite losses, plus the versions read from the lock. | contract + gpu (local) |
| FR-014-03 | Unwanted | If the `isaaclab` probe status in `studio/capabilities.json` is not `pass` (fail, skip, missing entry or invalid file), then `studio plan` shall mark `st60_il_train` and `st61_il_mpm_eval` as skipped with the reason, the `isaaclab` entry of `studio/tools.yaml` shall be set to `evaluated-not-adopted` with the recorded reason, no IL artefact shall be published, and the Isaac Lab tool page and the A2/A3 policy panels shall show "evaluated, not adopted" with the reason. | unit (fake capabilities) + E2E |
| FR-014-04 | Ubiquitous | IL stages shall import no Isaac Sim or Kit module, the lock shall contain no `isaacsim*` package, and each IL stage manifest shall carry `performance: public` unless the lock contains a package covered by NVIDIA SLA §8.9 (`isaacsim*`, `omni*`, `ovrtx`, `ovstage`, `ovphysx`), in which case it shall carry `local-only`. | contract |

### 3.2 Machine models

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-05 | Ubiquitous | The truck generator shall write an MJCF model with one chassis body, six wheels (two steered front, four driven rear) and a steering joint, from a parameter file of published academic dimensions (`contracts/machine-params.schema.json`), whose total mass, wheelbase and track width equal the parameter file within 0.1 %. | unit (XML parse) + gpu (local: MuJoCo compiles) |
| FR-014-06 | Ubiquitous | The excavator generator shall write an MJCF model with four revolute joints (swing, boom, stick, bucket) whose limits, torque limits τ_max, bucket width w and rated heaped volume V_h equal the parameter file exactly. | unit (XML parse) |
| FR-014-07 | Unwanted | If a machine parameter file is invalid against its schema — non-finite or non-positive mass or dimension, joint lower limit ≥ upper limit, torque limit ≤ 0, unknown key, or a mesh reference outside the generated asset folder (URL, absolute path or `..`) — then the generator shall raise `ValueError` naming the JSON pointer and write no model. | unit (hostile) |

### 3.3 IL-1 haul truck on a real ramp

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-08 | Ubiquitous | The IL-1 observation shall be a 63-element body-frame vector: speed, yaw rate, pitch (3); signed lateral error (left positive) and heading error wrapped to (−π, π] (2); the next 10 path points at 5 m arc-length spacing as (x, y) (20); payload fraction of rated (1); 32 ray-cast ranges over ±90° of the heading, clipped to 60 m (32); the nearest light vehicle's relative position (2) and velocity (2) and its TTC clipped to [0, 30] s (1). | unit (fake states) |
| FR-014-09 | Ubiquitous | The IL-1 action shall be two values in [−1, 1], clipped: steering rate as a fraction of the maximum steering rate, and a combined command whose positive part is the fraction of maximum rimpull and whose negative part is the fraction of maximum retarder force; the policy acts at 20 Hz. | unit |
| FR-014-10 | Unwanted | If an observation or action contains a NaN or infinite value, then the environment shall terminate that episode with reason `invalid_value` and count it as a failure. | unit (hostile) |
| FR-014-11 | Ubiquitous | The IL-1 reward shall be the weighted sum, with weights fixed in the task configuration, of: potential-based progress γΦ(s′) − Φ(s), with Φ the arc length along the route; −|e_lat|; −|e_ψ|; −max(0, v − v_lim), with v_lim(grade, payload) from the `minephys.haulage` rimpull/retarder envelopes capped at the site limit (default 40 km/h); −|jerk|; a collision penalty; a penalty while TTC < 3 s; and −P_trac · Δt (energy). | unit |
| FR-014-12 | Ubiquitous | An IL-1 episode shall end as **success** when the truck reaches arc length ≥ L_route − 2 m with no collision; it shall end as a failure on a collision (contact between any truck link and a light vehicle, or between a non-wheel truck link and terrain or a berm), on |e_lat| > 5 m, or at the time limit T_max = 2 · L_route / v̄_lim. | unit |
| FR-014-13 | Ubiquitous | IL-1 domain randomisation shall sample per episode, from the derived seed: payload U[0, 1] of rated; rolling resistance U[2, 8] %; tyre–road friction dry U[0.55, 0.75] or wet U[0.25, 0.45] with probability 0.5 each; actuator delay U{0, 1, 2, 3} control steps; ray noise N(0, (0.02 m + 0.01 r)²); speed noise N(0, 0.1² m²/s²); heading noise N(0, (0.5°)²). | unit (property) |
| FR-014-14 | Ubiquitous | IL-1 shall place 0–3 kinematic light vehicles at 20–40 km/h on paths that conflict with the route at least once (crossing or oncoming at a junction); the evaluation seed set shall hold exactly 25 episodes each with 0, 1, 2 and 3 light vehicles. | unit |

### 3.4 IL-2 excavator dig with FEE soil

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-15 | Ubiquitous | The IL-2 observation shall be a 46-element vector: joint positions, velocities and torques of swing, boom, stick and bucket (12); bucket tip position (x, z) and lip pitch in the machine frame (3); 30 terrain heights ahead of the bucket tip at 0.1 m spacing (30); fill estimate V_fill / V_h (1). | unit |
| FR-014-16 | Ubiquitous | The IL-2 action shall be four joint-velocity commands in [−1, 1], clipped and scaled by each joint's maximum velocity; FR-014-10 applies to IL-2. | unit |
| FR-014-17 | Ubiquitous | While the bucket tip is below the terrain surface (depth d > 0) and moves into the soil, the soil model shall apply to the bucket lip the FEE force F = (ρ g d² N_γ + c d N_c + c_a d N_a + q d N_q) · w of the 2-D wedge (factors as in `docs/theory/loading-and-terramechanics.md`, §3), with the failure angle β* minimising F over (0, min(π/2, π − α − δ − φ)), rake α from the lip pose clamped to [5°, 90°], draft H = F sin(α + δ) opposing the tip's horizontal motion and vertical V = F cos(α + δ); otherwise the FEE force shall be zero. The bucket also carries the weight of its fill. | unit (analytical) + parity |
| FR-014-18 | Ubiquitous | While cutting (FR-014-17 active), the fill model shall add w · d · |Δs_tip| per step to V_fill, capped at 1.15 V_h, and lower the terrain profile by the removed cross-section; the fill factor is k_f = V_fill / V_h. | unit |
| FR-014-19 | Ubiquitous | IL-2 domain randomisation shall sample per episode: bulk density ρ U[1,500, 2,100] kg/m³; cohesion c U[0, 20] kPa; adhesion c_a U[0, 0.5 c]; friction angle φ U[25°, 40°]; soil–tool friction δ U[10°, min(25°, φ)]; surcharge q = 0; initial face profile from the A3 bench geometry with ±0.3 m height noise. | unit (property) |
| FR-014-20 | Ubiquitous | A stall event shall be any interval of ≥ 1.0 s in which a joint holds |τ| ≥ 0.99 τ_max; an episode with at least one stall event is a stalled episode. | unit |
| FR-014-21 | Unwanted | If the FEE reference receives a non-finite or negative ρ, c, c_a, q, d or w, angles outside α ∈ (0, π/2], φ ∈ (0, π/2), δ ∈ [0, φ], or inputs for which D = cos(α + δ) + sin(α + δ) cot(β + φ) ≤ 0 for every admissible β, then it shall raise `ValueError` naming the input. | unit (hostile) |

### 3.5 MPM evaluation tier and optional loader

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-22 | Optional | Where the coupled rigid–MPM smoke passes (through Isaac Lab or Newton directly, whichever passes), `st61_il_mpm_eval` shall run the trained IL-2 policy unchanged in Newton's implicit MPM coupled to the rigid bucket, in 16–64 environments, with the dry-sand material of the DEM calibration artefact (spec 011) and the same initial profiles and seeds as the first n FEE evaluation episodes, and measure k_f = (particle mass inside the bucket volume) / (V_h · ρ_loose). | unit (fake) + gpu (local) |
| FR-014-23 | Unwanted | If the coupled MPM smoke fails, the calibrated material artefact is missing, or fewer than 16 MPM episodes complete, then IL-2b shall be reported "not run" with the reason and no FEE → MPM gap shall be published. | unit |
| FR-014-24 | Optional | Where IL-3 is trained, it shall be evaluated and published with IL-2's metrics and protocol; otherwise its panel shall show "not run". | unit + E2E |

### 3.6 Training and export

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-25 | Ubiquitous | `st60_il_train` shall train with rsl_rl PPO using actor and critic MLPs of two hidden layers of 256 units, γ = 0.99, λ = 0.95, clip ratio 0.2 and 24 steps per environment per update, with the number of environments set from the bench measurement within the VRAM budget (NFR-014-01); it shall save a checkpoint every 100 iterations, and `--resume` shall continue from the last checkpoint with the same iteration count, optimiser state and normaliser statistics. | unit (fake trainer) + gpu (local) |
| FR-014-26 | Unwanted | If a CUDA out-of-memory error occurs during training, then the stage shall retry once with the number of environments halved (the recipe's declared `oom_fallback`), resuming from the last checkpoint, and record the fallback in the manifest; a second out-of-memory error shall fail the stage. | unit (fake trainer) |
| FR-014-27 | Event | When training ends, `st60_il_train` shall write a policy handoff valid against `contracts/il-policy-handoff.schema.json` (checkpoint id and SHA-256, observation and action sizes, observation layout hash, normaliser mean and variance), and `s60_export` (spec 016) shall export it as ONNX opset 17 with IR version 10, with the normaliser inside the graph and a file size < 1 MB, with parity against PyTorch of rtol 1e-3, atol 1e-5 and max abs 1e-4 on ≥ 200 golden observations drawn from the evaluation rollouts. | contract + pipeline |
| FR-014-28 | Unwanted | If a policy handoff fails its schema or SHA-256, declares an observation size other than 63 (IL-1) or 46 (IL-2/IL-3), or holds a non-finite normaliser value or a variance ≤ 0, then `s60_export` shall reject it and export nothing. | unit (hostile) |

### 3.7 Baselines

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-29 | Ubiquitous | The IL-1 baseline shall steer by pure pursuit — curvature κ = 2x/l² toward the path point at look-ahead l, with x its lateral offset in the vehicle frame, and steering angle δ = arctan(L κ) for wheelbase L — with l = clamp(l₀ + k_v v, l_min, l_max), and control speed by a discrete PID on v_lim with output clamping and anti-windup; all gains are fixed in the task configuration before evaluation, and its outputs pass through the same action limits as the policy. | unit (hand calculation) |
| FR-014-30 | Ubiquitous | The IL-2 baseline shall be a scripted joint-space dig (penetrate, drag, curl, lift) parameterised by the initial terrain profile, tuned once on 20 training seeds disjoint from the evaluation seeds and frozen before any policy evaluation. | unit |
| FR-014-31 | Unwanted | If the pure-pursuit look-ahead is ≤ 0 or non-finite, the path has fewer than two points, or no path point lies beyond the look-ahead, then the controller shall use the path end as the goal point when the path is valid, and raise `ValueError` otherwise. | unit (hostile) |

### 3.8 Evaluation (pipeline `s50_evaluate`)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-32 | Ubiquitous | Each task shall be evaluated on 100 seeded episodes whose seeds are disjoint from the training and tuning seeds, with the same seeds (initial state, randomisation sample and light-vehicle scenario) for the policy and its baseline (paired), and with deterministic policy actions (the mean action). | unit |
| FR-014-33 | Ubiquitous | For IL-1 the evaluation shall compute per episode: success, collision, per-episode RMS and maximum lateral error, minimum TTC (+∞ if never closing; clipped at 30 s for statistics), energy per gross tonne-kilometre (kWh/(t·km)) and the fraction of steps within v_lim; and over the 100 episodes: the success rate with its Wilson 95 % interval, the RMS lateral error pooled over all control steps, and the fraction of episodes with minimum TTC ≥ 3 s. | unit |
| FR-014-34 | Ubiquitous | TTC between two agents shall be r / (−ṙ) when ṙ < 0 and +∞ otherwise, with r (m) the gap between their oriented 2-D footprints (0 at contact) and ṙ the relative velocity projected on the unit vector between the closest points. | unit (analytical) |
| FR-014-35 | Ubiquitous | For IL-2 the evaluation shall compute per episode: the fill factor k_f at dig completion (bucket lifted ≥ 0.5 m above the local terrain after cutting) or at the 30 s time limit, the cycle time t_c from episode start to dig completion (30 s if not completed), the productivity P = k_f / t_c (1/s), the stall flag and the lift-off flag; and over the episodes: the fraction with k_f ≥ 0.8 and the fraction stalled, each with a Wilson 95 % interval. | unit |
| FR-014-36 | Ubiquitous | Each policy-versus-baseline comparison shall give a per-metric verdict by the decision rule of FR-000-05, with differences oriented so that positive means the policy is better: for continuous metrics (IL-1 per-episode RMS lateral error, minimum TTC, energy; IL-2 productivity P), the paired Student-t 95 % interval of the mean difference over the 100 episodes; for binary metrics (IL-1 success, IL-2 k_f ≥ 0.8), the exact Clopper–Pearson 95 % interval of b / (b + c) over the discordant episodes, where "better" requires its lower bound > 0.5; otherwise "no significant difference". No composite verdict shall be computed. | unit (reference implementation) |
| FR-014-37 | Ubiquitous | The IL-1 sim-to-sim gap shall run the exported policy on the Python reference twin (FR-014-40) with the same 100 seeds, and report for success, per-episode RMS lateral error and minimum TTC the mean paired difference Δ = twin − Isaac Lab with its paired 95 % t-interval, labelled "sim-to-sim gap" and never tested for superiority. | unit |
| FR-014-38 | Ubiquitous | The FEE → MPM gap shall be the mean of Δ_j = k_f,MPM,j − k_f,FEE,j over the n paired MPM episodes (16 ≤ n ≤ 64) with the 95 % interval Δ̄ ± t₀.₉₇₅,ₙ₋₁ s_Δ / √n, labelled "sim-to-sim gap". | unit |
| FR-014-39 | Unwanted | If an episode table is invalid against `contracts/il-episodes.schema.json`, contains a duplicated seed within an arm, seed sets that differ between paired arms, a NaN metric, or fewer than 100 episodes for an acceptance verdict, then `s50_evaluate` shall compute no verdict and report "incomplete evaluation" with the failing check. | unit (hostile) |

### 3.9 Twins and web

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-40 | Ubiquitous | The IL-1 twin shall be a dynamic bicycle model — states x, y, ψ, v_x, v_y, r, δ; linear lateral tyre forces with per-axle cornering stiffness; longitudinal force from the `minephys.haulage` rimpull and retarder envelopes minus rolling and grade resistance; semi-implicit Euler at Δt = 0.01 s, switching to the kinematic bicycle below 1 m/s — implemented as a NumPy float64 reference and a TypeScript port, with parameters mapped from the machine parameter file. | unit + parity |
| FR-014-41 | Ubiquitous | The IL-2 twin shall be a planar kinematic arm (boom, stick, bucket; swing fixed) with joint limits, the FEE force of FR-014-17 and the fill model of FR-014-18, where joint velocities are scaled down whenever the joint torque Jᵀ F would exceed τ_max (so stalls are reproduced), implemented as a NumPy float64 reference and a TypeScript port. | unit + parity |
| FR-014-42 | Ubiquitous | On golden action sequences of 2,000 steps, each TypeScript twin shall match its Python reference with a maximum absolute state difference ≤ 1 × 10⁻⁶ (m, rad, m/s); closed-loop with the ONNX policy in ORT-web WASM, the actions of the first 200 steps shall match ONNX Runtime CPU within 1 × 10⁻⁴ (`web.wasm_fp32_max_abs`). | parity (web) |
| FR-014-43 | Event | When a visitor opens the A2 or A3 policy panel, the web app shall run the policy live on its TypeScript twin with a LIVE badge and the label "sim-to-sim", offer the Isaac Lab rollouts as REPLAY, and fall back to the replay if ORT-web cannot initialise (FR-000-02). | E2E |
| FR-014-44 | Unwanted | If a visitor sets a twin input (payload, light-vehicle speed, soil cohesion or friction angle) to a non-finite or out-of-range value, then the panel shall clamp it to its randomisation range and show "clamped to the training range"; and if the ONNX file fails its SHA-256, then the panel shall not load it and shall show the replay. | web unit + E2E (hostile) |
| FR-014-45 | Ubiquitous | Every IL result card and panel shall state "simulation only — compared with a classical controller on the same simulator; no field claim", and field results from the literature shall appear only as context, never as comparison targets. | E2E |

### 3.10 Hostile inputs of the task configuration and shared cores

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-014-46 | Unwanted | If the IL task parameters are invalid against `contracts/il-task.schema.json` — an unknown key, a randomisation range with lower > upper bound or outside the FR-014-13 / FR-014-19 limits, a non-finite reward weight, an observation layout that does not sum to 63 (IL-1) or 46 (IL-2), or evaluation seeds overlapping training seeds — or `--resume` names a checkpoint whose task-configuration hash differs from the current one, then the IL stage shall exit with code 2 before any GPU work and name the field. | unit (hostile) |
| FR-014-47 | Unwanted | If the TTC function, a twin step or the fill model receives a non-finite position, velocity, action or state, a footprint with a non-positive side, a time step ≤ 0, or a bucket width ≤ 0, then it shall raise `ValueError` naming the input. | unit (hostile) |

## 4. Correctness properties

Numerical cores and their metamorphic relations (MR): FEE (P-014-01 to P-014-06), pure pursuit (P-014-07), TTC
(P-014-08), observation builder (P-014-09), reward (P-014-10), evaluation statistics (P-014-11), IL-1 twin (P-014-12),
fill model (P-014-13).

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-014-01 | FEE MR width: F(k w) = k F(w) and β* is unchanged. | k ∈ [0.1, 10]; soil in the FR-014-19 ranges; α ∈ [5°, 90°]; d ∈ [0.01, 2] m | rtol 1e-9 (F); atol 1e-8 rad (β*) |
| P-014-02 | FEE MR homogeneity: scaling ρ, c, c_a and q by the same k > 0 scales F by k and leaves β* unchanged. | as P-014-01 | rtol 1e-9; atol 1e-8 rad |
| P-014-03 | FEE MR depth: with c = c_a = q = 0, F(k d) = k² F(d). | as P-014-01 | rtol 1e-9 |
| P-014-04 | FEE oracle: at any admissible β, the factor form equals the blade force P from solving the two wedge equilibrium equations directly (2 × 2 linear system). | Hypothesis over the admissible domain | rtol 1e-10 |
| P-014-05 | FEE MR monotonicity: F is non-decreasing in ρ and in q (their factors N_γ, N_q ≥ 0 for every admissible β). | as P-014-01 | exact ordering |
| P-014-06 | FEE worked examples (α = 60°, δ = 20°, φ = 35°, d = 0.5 m, w = 1 m, ρ = 1,800 kg/m³, g = 9.81 m/s²): cohesionless β* = 28.105°, N_γ = 1.8196, F = 8.0327 kN, H = 7.9107 kN, V = 1.3949 kN; with c = 10 kPa, c_a = 5 kPa: β* = 28.206°, F = 25.141 kN; the rake table for α = 30°, 45°, 75°, 90° (spec §7). | fixed inputs | rtol 1e-3 (β*: atol 0.01°) |
| P-014-07 | Pure pursuit MRs: (MR1) mirroring the goal (x → −x) negates κ and δ; (MR2) x = 0 gives κ = 0; (MR3) scaling x and l by k scales κ by 1/k; hand calculation l = 20 m, x = 1 m, L = 6 m → κ = 0.005 m⁻¹, δ = 1.7184°. | x ∈ [−20, 20] m, l ∈ [2, 60] m | rtol 1e-12 |
| P-014-08 | TTC MRs: (MR1) a common rigid motion of both agents leaves TTC unchanged; (MR2) scaling all positions and velocities by the same k leaves TTC unchanged; (MR3) scaling velocities only by k divides TTC by k; (MR4) swapping the agents leaves TTC unchanged; non-closing pairs give +∞. | footprints 2–15 m, speeds 0–20 m/s | rtol 1e-12 |
| P-014-09 | Observation MRs: (MR1) a common SE(2) motion and height offset of truck, route, terrain and light vehicles leaves the 63-element observation unchanged; (MR2) mirroring the world about the truck's longitudinal axis negates e_lat, e_ψ, yaw rate, the path and light-vehicle y components and reverses the ray order, and leaves TTC unchanged; (MR3) permuting light vehicles leaves it unchanged. | Hypothesis scenes | atol 1e-6 (float32) |
| P-014-10 | Reward MRs: (MR1) the progress terms telescope, Σₜ γᵗ Fₜ = γᵀ Φ(s_T) − Φ(s₀); (MR2) a stationary truck at γ = 1 earns zero progress reward; (MR3) mirroring the world (P-014-09 MR2) leaves every reward term unchanged. | Hypothesis trajectories | rtol 1e-9 (float64) |
| P-014-11 | Statistics: (MR1) Wilson(k, n) mirrors Wilson(n − k, n) as [1 − U, 1 − L]; (MR2) swapping arms negates the paired t-interval; (MR3) adding a constant to both arms' metric leaves the difference interval unchanged; (MR4) permuting episodes leaves every statistic unchanged; hand calculation Wilson(95, 100) = [0.8882, 0.9785], t₀.₉₇₅,₉₉ = 1.9842. | n ∈ [1, 10⁴] | rtol 1e-9 |
| P-014-12 | IL-1 twin MRs: (MR1) zero steering and zero net longitudinal force on flat ground keep a straight line at constant speed; (MR2) mirrored steering inputs give mirrored trajectories; (MR3) at constant δ and v the yaw rate converges to v δ / (L + K_us v²); (MR4) an uphill run spends at least m g Δh of traction energy. | v ∈ [1, 15] m/s, δ ∈ [−0.3, 0.3] rad, grades 0–12 % | atol 1e-9 (MR1, MR2); rtol 1e-2 (MR3); exact inequality (MR4) |
| P-014-13 | Fill-model MRs: (MR1) V_fill is non-decreasing while cutting and never exceeds 1.15 V_h; (MR2) below the cap, the volume removed from the terrain profile times w equals the increase of V_fill (conservation); (MR3) doubling w doubles the fill gain. | Hypothesis tip paths | rtol 1e-9 |
| P-014-14 | Randomisation: every sample lies in its FR-014-13 or FR-014-19 range; the same (seed, episode) reproduces the same sample; samples of distinct episodes pass a Kolmogorov–Smirnov test against their target distribution (p > 0.001, 10⁴ samples). | seeds 0–2³²−1 | exact; statistical |
| P-014-15 | Task–reference parity: the vectorised FEE force and fill model used in the Isaac Lab task (float32, torch) match the NumPy float64 reference. | 10⁴ random admissible states | rtol 1e-5 |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-014-01 | Device-peak VRAM during training (open stack, publishable) | IL-1 ≤ 5 GB; IL-2 ≤ 6 GB; the number of environments is reduced until it fits | NVML telemetry in the manifest |
| NFR-014-02 | GPU time (plan estimates: IL-1 1–4 h, IL-2 2–8 h, IL-3 2–3 h) | recorded per run; a run that exceeds 2 × its upper estimate is stopped and recorded as such | runner telemetry |
| NFR-014-03 | Exported policy size | < 1 MB each | CI budget check |
| NFR-014-04 | Live twin step on T2 (5 physics substeps + one ONNX inference per frame) | ≤ 16 ms per animation frame | Playwright timing |
| NFR-014-05 | Provenance of task code | Apache-2.0 SPDX header on every file; no copied Isaac Lab source; no NVIDIA or Isaac Lab asset referenced by any task or recipe | CI repository scan |
| SC-014-01 | IL-1 route success | ≥ 95 % route success without collision over 100 seeded episodes (observed rate; Wilson interval reported with it) | `s50_evaluate` IL-1 table |
| SC-014-02 | IL-1 lateral error | RMS lateral error ≤ 0.5 m (pooled over the 100 episodes) | `s50_evaluate` |
| SC-014-03 | IL-1 time to collision | minimum TTC ≥ 3 s in ≥ 99 % of episodes (at most 1 of 100 below 3 s) | `s50_evaluate` |
| SC-014-04 | IL-1 versus pure pursuit + PID | "beats pure pursuit + PID" only by the decision rule (per metric, FR-014-36) | `s50_evaluate` + UI verdict text |
| SC-014-05 | IL-1 sim-to-sim | sim-to-sim gap against the TS twin reported with its 95 % CI (FR-014-37) | `s50_evaluate` |
| SC-014-06 | IL-2 fill | fill factor ≥ 0.8 in ≥ 80 % of FEE episodes | `s50_evaluate` IL-2 table |
| SC-014-07 | IL-2 stalls | stalls ≤ 5 % of episodes | `s50_evaluate` |
| SC-014-08 | IL-2 FEE → MPM | FEE → MPM fill gap reported with a 95 % CI (or "not run", FR-014-23) | `s50_evaluate` |
| SC-014-09 | IL-2 versus scripted dig | "beats scripted dig" only by the decision rule on fill × cycle time, evaluated as the per-episode productivity P = k_f / t_c | `s50_evaluate` + UI verdict text |
| SC-014-10 | Export parity | fp32 rtol 1e-3 / atol 1e-5 for every exported policy | `s60_export` parity report |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-014-01 | IL task parameters (recipe `params` of `st60_il_train`, `st61_il_mpm_eval`): observation layout, reward weights, randomisation ranges, seeds, budgets | `specs/014-robot-learning/contracts/il-task.schema.json` (draft; promoted to `contracts/il-task.schema.json` by T-014-001) | maintainer → IL stages |
| DC-014-02 | machine parameter files (truck, excavator, loader) | `specs/014-robot-learning/contracts/machine-params.schema.json` (draft; promoted to `contracts/machine-params.schema.json` by T-014-001) | maintainer (published academic dimensions) → generators, twins |
| DC-014-03 | policy handoff | `specs/014-robot-learning/contracts/il-policy-handoff.schema.json` (draft; promoted to `contracts/il-policy-handoff.schema.json` by T-014-001) | `st60_il_train` → `s60_export` |
| DC-014-04 | episode tables (Parquet columns + JSON sidecar) | `specs/014-robot-learning/contracts/il-episodes.schema.json` (draft, row column sets in `$defs/il1_episode`, `$defs/dig_episode`; promoted to `contracts/il-episodes.schema.json` by T-014-001) | `st60_il_train` (evaluation mode), `st61_il_mpm_eval`, twin runner → `s50_evaluate` |
| DC-014-05 | web twin bundle (twin parameters, policy asset id and SHA-256, golden sequences) | `specs/014-robot-learning/contracts/il-twin.schema.json` (draft; promoted to `contracts/il-twin.schema.json` by T-014-001) | `s60_export` → web |
| DC-014-06 | run and asset manifests | `contracts/manifest.schema.json` (spec 001) | IL stages → web, CI |
| DC-014-07 | probe `isaaclab` in `studio/capabilities.json` | `contracts/capabilities.schema.json` (DC-000-02) | `studio/bench/run_bench.py` → planner |

## 7. Edge cases and assumptions

**Pinned at specification (read 2026-10-06/07):**
- Pure pursuit: Coulter, R. C. (1992), *Implementation of the Pure Pursuit Path Tracking Algorithm*, CMU-RI-TR-92-01,
  §2, printed pp. 5–6 (eqs. 2.1–2.2): the curvature is "related to the x offset of the goal point from the origin by
  the inverse square of the lookahead distance l … the gain is 2 times the inverse square of l", i.e. κ = 2x/l².
- GAE (inside rsl_rl, not re-implemented here): Schulman et al., ICLR 2016 (arXiv 1506.02438), eq. (16), p. 4,
  Â_t = Σₗ (γλ)ˡ δ_{t+l}. This fixes the meaning of λ = 0.95 in FR-014-25.
- FEE rake-angle table (hand-calculated from the wedge equilibrium in `docs/theory/loading-and-terramechanics.md` §3,
  cohesionless, same inputs as P-014-06):

  | α (°) | β* (°) | N_γ (–) | F (kN) | H (kN) | V (kN) |
  |---|---|---|---|---|---|
  | 30 | 35.589 | 1.7143 | 7.5679 | 5.7973 | 4.8646 |
  | 45 | 32.826 | 1.6100 | 7.1071 | 6.4413 | 3.0036 |
  | 60 | 28.105 | 1.8196 | 8.0327 | 7.9107 | 1.3949 |
  | 75 | 22.423 | 2.4495 | 10.8133 | 10.7721 | −0.9424 |
  | 90 | 16.174 | 4.1619 | 18.3728 | 17.2648 | −6.2839 |

**UNVERIFIED (kept with analytical or hand-calculated oracles that do not depend on them):**
- Reece (1964), Proc. IMechE 179(6):16–22, DOI 10.1243/PIME_CONF_1964_179_134_02: the primary text is not readable
  (no abstract in the Crossref record). The FEE form is checked against the first-principles wedge equilibrium
  (P-014-04), not against the primary transcription. McKyes & Ali's narrow-blade side terms are not used (2-D wedge
  only).
- Potential-based shaping leaves the optimal policy unchanged (Ng, Harada & Russell 1999): not read. P-014-10 tests
  only the algebraic telescoping identity.
- MuJoCo-Warp soft-contact wheels at haul speeds are not validated; results are relative to the baseline on the same
  simulator.
- The tyre friction, actuator delay, noise and soil ranges (FR-014-13, FR-014-19), the fill cap 1.15 and the stall
  thresholds are PitStudio design values, not measured site values. They are labelled as such.
- Kit-less Isaac Lab on Windows has no upstream test evidence (FR-014-02 decides).

**Edge cases:**
- Episodes without a light vehicle have minimum TTC = +∞ and count as ≥ 3 s. The 25/25/25/25 scenario mix keeps
  SC-014-03 informative.
- If b + c = 0 (no discordant episodes), the binary verdict is "no significant difference".
- The evaluation uses the same ramps as training with disjoint seeds; generalisation to unseen ramps is not claimed.
- Field precedents (0.22 m maximum lateral error; 70 % against 83 % field success) are context only.

**Tolerances and their justification:**
- FEE MRs, rtol 1e-9: β* comes from a bounded scalar minimiser with x-tolerance 1e-10 rad. At the minimum,
  ∂F/∂β = 0, so a β error δβ changes F by O(δβ²).
- Worked-example values, rtol 1e-3: they are printed to 4–5 significant digits.
- Task parity, rtol 1e-5: float32 (ε = 1.19 × 10⁻⁷) times a condition number of about 10² for the factor
  expressions.
- Twin parity, 1e-6 over 2,000 steps: same float64 operation order; the only differences are 1-ulp differences in
  `sin`, `cos` and `atan` between V8 and NumPy, in a stable (non-chaotic) system.
- ORT-web, 1e-4: foundation `web.wasm_fp32_max_abs`.

## 8. Clarifications log

- Resolved: "beats scripted dig only by the decision rule on fill × cycle time". A literal product k_f × t_c would
  reward slower cycles. It is evaluated as the per-episode productivity P = k_f / t_c (fill factor per second of
  cycle); this is recorded in SC-014-09.
- Resolved: "beats pure pursuit + PID" is a per-metric verdict on route success, lateral error, minimum TTC and
  energy. There is no composite verdict (several axes, never one number).
- Resolved: interval methods per comparison: paired t for continuous metrics; exact Clopper–Pearson on discordant
  episodes for binary metrics; Wilson for reported rates; paired t for the sim-to-sim gaps (reported, not tested).
- Resolved: the stall definition (the docs leave the threshold to the specification) is |τ| ≥ 0.99 τ_max for ≥ 1.0 s.
- Resolved: the observation sizes are fixed at 63 (IL-1, within the documented 60–90 range) and 46 (IL-2).
- Resolved: the number of IL-2 evaluation episodes is 100 (the model card's protocol), and the MPM tier uses
  16 ≤ n ≤ 64 paired episodes.
- Resolved: the sim-to-sim gap is measured on the Python reference twin, which the TypeScript twin matches by parity
  (FR-014-42), so the gap stands for the TS twin while running in the 3.14 pipeline.
- Resolved: ONNX export of the policies uses opset 17 and IR 10 (model card; within plan §4's opset 17–19 range).
- Resolved: the energy metric is per gross tonne-kilometre, because payload is randomised down to 0.
- Integration 2026-10-07: draft schema written for DC-014-01 … DC-014-05 (`specs/014-robot-learning/contracts/`, valid
  and hostile examples indexed in `examples/index.json`). Resolved, stricter reading chosen: the IL task parameters are
  one closed record per task family (IL-1 haul truck; IL-2 / IL-3 dig) carrying a `stage` field (IL-1 and IL-3 train
  only; the MPM stage needs its `mpm` block); the spec's fixed values are constants (PPO settings of FR-014-25,
  observation sizes 63 / 46, action sizes 2 / 4, IL-1 at 20 Hz, 100 evaluation episodes with deterministic actions, 20
  tuning seeds, the 25/25/25/25 light-vehicle mix, the 30 s dig limit, surcharge 0, wet probability 0.5); randomisation
  ranges may narrow but never exceed the FR-014-13 / FR-014-19 limits and the noise sigmas stay at or below their
  stated values; reward weights are ≥ 0 because every term is already signed; budgets are capped at the NFR-014-01 VRAM
  limits and at 2 × the upper GPU-hour estimate (IL-1 8 h, IL-2 16 h, IL-3 6 h); the IL-3 task id is
  `Pit-Loader-Dig-FEE` with 46 observations and 4 actions, and IL-3 has no MPM tier or twin; every numeric field of a
  machine parameter file names its source (`published` or `derived`), each source has a DOI or an https URL, joint
  limits are in degrees and meshes are relative paths inside the generated asset folder; the handoff's layout and
  task-configuration hashes are SHA-256 of RFC 8785 canonical JSON and it lists ≥ 200 golden observations; episode
  tables are Parquet with a JSON sidecar, minimum TTC is stored as +∞ when never closing (no upper bound), the fill
  factor is bounded by 3 (MPM may exceed the FEE cap of 1.15), each IL-1 row keeps its step count and sum of squared
  lateral errors for the pooled RMS, and an MPM table holds 16–64 rows; "< 1 MB" for the ONNX policy is ≤ 999,999
  bytes, and the twin bundle pins the "sim-to-sim" label, the FR-014-45 statement, the 2,000-step goldens and the IL-1
  twin step of 0.01 s (the IL-2 arm step, unspecified, is ≤ 0.05 s).

## 9. Changes (only for features that modify earlier behaviour)

### ADDED Requirements
- (none — new feature)

### MODIFIED Requirements
- (none)

### REMOVED Requirements
- (none)
