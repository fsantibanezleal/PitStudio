# Robot learning for haul trucks and excavators

> How PitStudio trains driving and digging policies: the Markov decision process, the PPO objective with generalised
> advantage estimation, domain randomisation, observation, action and reward design for a haul truck and an
> excavator, Isaac Lab-style vectorised training, and the sim-to-sim gap, set against field precedents with their
> reported numbers. · Part of: [Theory](README.md) · Related:
> [M21 Isaac Lab policies](../methods/m21-isaac-lab-policies.md) · [Isaac Lab](../frameworks/isaac-lab.md) ·
> [Isaac Lab policy cards](../models/isaac-lab-policies.md) ·
> [loading and terramechanics](loading-and-terramechanics.md)

## What and why

Earthmoving is one of the few heavy-industry domains where learned controllers have been tested on full-size machines.
A policy trained in simulation dug with a 12-t excavator in different soils [8]; another removed boulders with 70 %
field success against 83 % for human operators [9]; a third built a 42 m × 2.1 m embankment in 45 minutes with an
11.5-t excavator [10]. A learned path tracker drove mining trucks with a 0.22 m maximum lateral error in the field
[11]. None of these used a public mining task: Isaac Lab ships quadcopter and navigation tasks but **no wheeled-vehicle,
excavator, loader or granular task** [6]. Everything mining-specific is written by the project.

PitStudio trains two policies (plus an optional third) and treats them as **measured experiments**: each is compared
with a classical controller on the same simulator, and each is transferred to a second simulator to report a
sim-to-sim gap. No field claim is made.

## The Markov decision process

A control task is a Markov decision process (MDP) $(\mathcal{S}, \mathcal{A}, P, r, \gamma, \rho_0)$: states
$s \in \mathcal{S}$, actions $a \in \mathcal{A}$, transition law $P(s' \mid s, a)$, reward $r(s, a, s')$, discount
$\gamma \in [0, 1)$ and initial-state distribution $\rho_0$ (citation UNVERIFIED — pinned at specification). The agent
sees an observation $o_t$ (a partial, noisy view of $s_t$, which makes the problem partially observable) and samples
an action from a stochastic policy $\pi_\theta(a \mid o)$ with parameters $\theta$. It maximises the expected
discounted return

$$
J(\theta) = \mathbb{E}_{\tau \sim \pi_\theta}\Big[\sum_{t=0}^{H-1} \gamma^t r_t\Big]
$$

over episodes $\tau$ of horizon $H$ steps. The value function $V^\pi(s) = \mathbb{E}[\sum_k \gamma^k r_{t+k} \mid s_t = s]$
estimates how good a state is under the current policy; the advantage $A^\pi(s,a) = Q^\pi(s,a) - V^\pi(s)$ says how
much better action $a$ is than the policy's average.

## PPO: the clipped surrogate objective

Proximal Policy Optimization (PPO) improves the policy with stochastic gradient ascent on data from the previous policy
$\pi_{\theta_{\mathrm{old}}}$, while keeping each update small [1]. With the probability ratio

$$
\rho_t(\theta) = \frac{\pi_\theta(a_t \mid o_t)}{\pi_{\theta_{\mathrm{old}}}(a_t \mid o_t)}
$$

and an advantage estimate $\hat A_t$, the clipped surrogate is [1]:

$$
L^{\mathrm{CLIP}}(\theta) = \hat{\mathbb{E}}_t\Big[\min\big(\rho_t(\theta)\, \hat A_t,\; \mathrm{clip}(\rho_t(\theta), 1 - \epsilon, 1 + \epsilon)\, \hat A_t\big)\Big]
$$

and the full objective adds a value-function loss and an entropy bonus [1]:

$$
L(\theta) = \hat{\mathbb{E}}_t\Big[L^{\mathrm{CLIP}}_t(\theta) - c_1 \big(V_\theta(o_t) - V_t^{\mathrm{targ}}\big)^2 + c_2\, \mathcal{H}\big[\pi_\theta(\cdot \mid o_t)\big]\Big]
$$

with clip range $\epsilon$ (–), loss weights $c_1, c_2$ (–) and policy entropy $\mathcal{H}$. The clip removes the
incentive to move the ratio outside $[1-\epsilon, 1+\epsilon]$: for a good action ($\hat A_t > 0$) the objective stops
growing once $\rho_t > 1 + \epsilon$, and for a bad one ($\hat A_t < 0$) once $\rho_t < 1 - \epsilon$. The $\min$ keeps
the objective a pessimistic bound, so a large step that would make things worse is still penalised.

PitStudio uses the RSL-RL PPO implementation that Isaac Lab installs by default [3][19].

## Generalised advantage estimation (GAE)

PPO needs $\hat A_t$. GAE blends one-step temporal-difference errors with an exponential weight $\lambda \in [0, 1]$
(Schulman et al. 2015; citation UNVERIFIED — pinned at specification):

$$
\delta_t = r_t + \gamma\, (1 - d_{t+1})\, V(o_{t+1}) - V(o_t), \qquad
\hat A_t = \sum_{l=0}^{\infty} (\gamma\lambda)^l\, \delta_{t+l}
$$

computed backwards with $\hat A_t = \delta_t + \gamma\lambda\,(1 - d_{t+1})\,\hat A_{t+1}$, where $d_{t+1} = 1$ if the
episode ended. $\lambda = 0$ gives the low-variance, biased one-step estimate; $\lambda = 1$ gives the unbiased,
high-variance Monte-Carlo return. The value target is $V_t^{\mathrm{targ}} = \hat A_t + V(o_t)$.

**Worked example.** Rewards $r = (1, 0, 2)$ over three steps that end the episode, values
$V = (0.5, 0.4, 0.6)$, $\gamma = 0.99$, $\lambda = 0.95$ (so $\gamma\lambda = 0.9405$):

| $t$ | $\delta_t$ | $\hat A_t$ |
|---|---|---|
| 2 | $2 + 0 - 0.6 = 1.400$ | $1.400$ |
| 1 | $0 + 0.99 \times 0.6 - 0.4 = 0.194$ | $0.194 + 0.9405 \times 1.400 = 1.511$ |
| 0 | $1 + 0.99 \times 0.4 - 0.5 = 0.896$ | $0.896 + 0.9405 \times 1.511 = 2.317$ |

The first action is credited with most of the later reward, discounted by $\gamma\lambda$ per step.

## Vectorised training, Isaac Lab style

Isaac Lab presents itself as the successor to Isaac Gym: GPU-parallel physics, sensors, actuator models and domain
randomisation, with thousands of environments stepped in lockstep on one GPU [2]. Each PPO iteration collects $T$
steps from each of $N$ environments, so the batch is

$$
B = N \cdot T \quad \text{transitions per update}
$$

split into mini-batches and reused for a few epochs. Environments reset independently when an episode ends, so the
batch always holds a mix of early and late episode states.

**Worked example.** The boulder-excavation policy of Gruetter et al. used an MLP with two hidden layers of 256 units,
9,000 iterations with 24 steps per environment per update, "thousands of parallel environments" and about "8 years of
experience in simulation" [9]. PitStudio's IL-1 budget is 2,048 environments: at 24 steps per update that is
$2{,}048 \times 24 = 49{,}152$ transitions per update, so the planned 0.2–0.5 billion steps correspond to about
4,000–10,000 updates.

**Memory decides the observation type.** Isaac Lab's published benchmarks list 3.3 GB of GPU memory for 4,096
Cartpole environments, but **16.7 GB for 1,024 Cartpole environments with an RGB camera** [5]. A 16 GB GPU cannot
afford camera-in-the-loop RL, so PitStudio's policies observe **ray casts, height profiles and proprioception**;
cameras are only used to film trained policies.

Isaac Lab 3.0 can run **kit-less** on the Newton physics engine, without installing or launching Isaac Sim [3]. Its
Newton backend is beta; MuJoCo-Warp (MJWarp) is the primary validated path, with MPM among the other solvers, and
"task and component coverage is narrower and task-specific" [4]. Trained policies export to ONNX with their
observation normaliser through `export_policy_as_onnx(policy, path, normalizer=…)`; the opset is not documented [7], so
PitStudio's own export stage sets it and runs the parity check.

![Vectorised environments, policy, Newton physics, rewards, PPO update, ONNX export and the TypeScript twin](../assets/diagrams/isaac-lab-task-loop.svg)

*The Isaac Lab task loop as PitStudio uses it: N environments on the GPU, PPO updates, ONNX export and a live browser
twin.*

## Observation and action design

Design rules that both tasks follow:

- **Body-frame, normalised inputs.** Positions and path points are expressed relative to the machine, so the policy
  generalises across the pit.
- **Proprioception plus a cheap exteroceptive sensor.** A ray-cast scan or terrain profile instead of images (memory,
  above).
- **Rate-type actions in $[-1, 1]$.** Steering rate and joint velocities are smooth by construction and map onto real
  hydraulic and drive interfaces; Egli et al.'s policy output "joint velocity commands, which can be directly applied
  to the standard proportional valves" [8].

### IL-1 haul truck on a real ramp (`Pit-HaulTruck-Ramp`)

Scene: ramp segments of the real Bingham Canyon terrain, a procedural rigid-frame truck (chassis, six wheels,
steering) and up to three light vehicles moving kinematically.

| Observation group | Content | Size (–) |
|---|---|---|
| Motion | speed, yaw rate, pitch (grade) | 3 |
| Path tracking | lateral error, heading error | 2 |
| Preview | next 10 path points in the body frame (x, y) | 20 |
| Load | payload mass | 1 |
| Perception | 32-beam ray-cast scan | 32 |
| Traffic | nearest light vehicle: relative position (2), relative velocity (2), time-to-collision | 5 |
| **Total** | indicative; fixed in the IL-1 specification (planned range ≈ 60–90) | **63** |

Actions: steering rate and a combined throttle/retarder command, both in $[-1, 1]$. Time-to-collision for a closing
pair at distance $d$ (m) with range rate $\dot d < 0$ (m/s) is $\mathrm{TTC} = d / (-\dot d)$ (s); see the traffic
method [M20](../methods/m20-traffic-ttc.md).

### IL-2 excavator digging (`Pit-Excavator-Dig-FEE`)

Scene: a procedural excavator with swing, boom, stick and bucket; the soil is the **Fundamental Earthmoving Equation**
(FEE) with heavily randomised parameters, the recipe of Egli et al. and Gruetter et al. [8][9]. The FEE gives the
quasi-static resistance on a blade of width $w$ at depth $d$ (Reece 1964 [18]; search excerpt, transcription pinned at
specification):

$$
F = \big(\gamma\, g\, d^2 N_\gamma + c\, d\, N_c + c_a\, d\, N_a + q\, d\, N_q\big)\, w
$$

with bulk density $\gamma$ (kg/m³), cohesion $c$ (Pa), adhesion $c_a$ (Pa), surcharge $q$ (Pa) and dimensionless
factors $N$ that depend on rake angle and friction angles; details on the
[loading and terramechanics](loading-and-terramechanics.md) page.

| Observation group | Content |
|---|---|
| Proprioception | joint positions, velocities and torques (4 joints) |
| Tool | bucket pose |
| Terrain | 30-sample terrain profile ahead of the bucket (as in [10]) |
| Task | fill estimate |

Actions: four joint velocities. The bucket **fill factor** is $k_f$ = payload volume / rated heaped volume (–).

An evaluation tier (IL-2b) runs the trained IL-2 policy **zero-shot** in Newton's implicit MPM soil coupled to the
rigid bucket (16–64 environments). An optional IL-3 task covers a wheel loader's approach to the truck and its V-cycle,
following Borngrund et al. [14].

## Reward shaping

Dense shaping terms make the task learnable; penalties encode constraints. Gruetter et al. used six dense shaping
terms, sparse terminal rewards and seven penalty terms [9]. PitStudio's reward terms:

| Task | Shaping terms | Penalties |
|---|---|---|
| IL-1 | progress along the path; $-\lvert e_{\mathrm{lat}} \rvert$ and $-\lvert e_\psi \rvert$; speed-limit tracking per grade from the `minephys` rimpull/retarder envelopes; energy proxy $-\int P\, dt$ | jerk; large penalty on collision or TTC < 3 s |
| IL-2 | fill-volume gain; target fill reached; cycle-time term | stall (torque at its limit), machine lift-off, joint limits, action rate |

**Potential-based shaping.** A shaping term of the form $F(s, s') = \gamma\,\Phi(s') - \Phi(s)$ for any potential
$\Phi$ leaves the optimal policy unchanged (Ng, Harada & Russell 1999; citation UNVERIFIED — pinned at
specification). The progress term is of this kind with $\Phi$ = arc length travelled along the path: it speeds up
learning without changing what "optimal" means. The penalties are deliberately **not** potential-based: they change
the optimum toward safe behaviour, which is what a constraint should do.

## Domain randomisation

A policy trained on one exact simulator overfits its quirks. Domain randomisation trains on a distribution of
simulators instead, maximising $\mathbb{E}_{\xi \sim p(\xi)}\big[J(\pi_\theta; \xi)\big]$ over physical parameters
$\xi$:

- Tobin et al. (2017) transferred a network trained only on randomised simulated images to a real robot, at about
  1.5 cm accuracy [16].
- Structured domain randomisation, which samples from context-aware distributions instead of uniform noise, beat
  plain randomisation on a real benchmark [17].
- Egli et al.'s excavation policy adapts "solely from proprioceptive observations" after training on heavily
  randomised soil [8].

| Task | Randomised parameter | Range |
|---|---|---|
| IL-1 | payload | 0–100 % of rated |
| IL-1 | rolling resistance | 2–8 % |
| IL-1 | tyre–road friction | wet / dry |
| IL-1 | actuator delay, sensor noise | set in the IL-1 specification |
| IL-2 | FEE soil parameters ($\gamma$, $c$, $c_a$, friction angles) | set in the IL-2 specification |

These are PitStudio design ranges, not measured site values.

## Sim-to-sim gap

A sim-to-real gap needs a real machine; PitStudio has none. It measures a **sim-to-sim** gap instead: the same policy,
unchanged, evaluated in a second simulator with different physics. For a metric $m$ and paired evaluation seeds
$j = 1 \dots n$:

$$
\Delta_j = m_{\mathrm{target},j} - m_{\mathrm{source},j}, \qquad
\bar\Delta \pm t_{0.975,\,n-1}\, \frac{s_\Delta}{\sqrt n}
$$

| Policy | Source simulator | Target simulator | Metric |
|---|---|---|---|
| IL-1 | Isaac Lab on Newton (MJWarp articulated truck) | TypeScript twin (bicycle model with `minephys` drive envelopes) | route success, lateral error, min TTC |
| IL-2 | Isaac Lab with FEE soil | Newton implicit MPM soil (IL-2b) | fill factor |

The gap is reported with its 95 % confidence interval, never hidden. For scale, a wheel-loader study found a
sim-to-real gap of about 10 %, and a force-feedback controller lost 5 % of performance despite a domain gap of about
15 % [13].

## Field precedents

The numbers below come from different machines, simulators and metrics; they set expectations and are **not
comparable** with each other or with PitStudio's simulated results.

| Study | Machine / task | Simulator and method | Reported result | Source |
|---|---|---|---|---|
| Egli et al. 2022 | Excavation | FEE soil, heavily randomised; joint-velocity actions | Tested on a 12-t excavator in different soils | [8] |
| Gruetter et al. 2025 | Boulder excavation | Isaac Lab, quasi-static 2-D FEE; PPO 2 × 256 | 70 % field success vs 83 % for human operators | [9] |
| Werner et al. 2026 | Embankment building | Custom 2-D explicit MPM in Warp; 4,000 envs × 7,000 particles; ≈ 533× real time with 1,500 envs on one GH200; ≈ 3 h on four GH200 | 11.5-t excavator built a 42 m × 2.1 m embankment in 45 min | [10] |
| Xia et al. 2025 | Mining-truck path tracking | RL with adaptive preview and a safety layer | Simulation: mean lateral error < 0.05 m, < 10 ms; field: max lateral error 0.22 m, < 20 ms | [11] |
| Backman et al. 2021 | Loader bucket filling | Soft actor-critic, energy penalty | 75 % of maximum bucket capacity | [12] |
| Aoshima & Servin 2024 | Wheel loader | DEM soil | Sim-to-real gap ≈ 10 %; controller −5 % at ≈ 15 % domain gap | [13] |
| Borngrund et al. 2024 | Loader approach to the truck | 3-D simulation, direct transfer | Real loader "exhibits the correct behaviour" | [14] |
| Zhao et al. 2026 | Scaled excavator | Terrain-aware target selection + RL/IL | 6.52 kg vs 2.68 kg mean payload per cycle | [15] |

Two lessons carry over. First, FEE-based training with randomised soil is the proven route for digging [8][9].
Second, MPM-in-the-loop training at field scale costs multi-GPU hours [10], which a 16 GB laptop cannot afford; hence
MPM only as an evaluation tier.

## Assumptions and limits

- **Simulation only.** No real truck or excavator; results are simulation-grade and compared with classical baselines
  on the same simulator. Not a certified autonomy evaluation.
- **Vehicle fidelity.** MJWarp soft-contact wheels at haul speeds are unvalidated (UNVERIFIED); results are relative to
  the pure-pursuit + PID baseline, not absolute.
- **FEE validity.** The FEE is quasi-static and assumes continuum soil; it does not describe blasted rock with large
  fragments. The MPM tier probes that gap; it does not close it.
- **Bleeding-edge tooling.** Isaac Lab 3.0 is an early-access release with API churn; its coupled rigid–MPM support is
  contrib/beta, one MPM manipulation task shows an open regression (2/20 vs 64/64 successes) and no validated MPM
  material presets exist [20]. Kit-less operation on Windows is untested by the project.
- **16 GB is the floor.** Environment counts are measured before long runs; the planned budgets are estimates.

## In PitStudio

| Item | Where | Status |
|---|---|---|
| Method | [M21 Isaac Lab policies](../methods/m21-isaac-lab-policies.md): IL-1 haul truck, IL-2 excavator (+ IL-2b MPM check), IL-3 loader (optional) | Specified in the plan |
| Environment | `studio/isaaclab/` (Python 3.12), Isaac Lab pinned to the v3.0.0-EA tag in `studio/isaaclab/pyproject.toml`; kit-less on Newton | Locked; kit-less smoke test not yet run on the reference machine |
| Stages | `st60_il_train` (IL-1, IL-2, IL-3), `st61_il_mpm_eval` (IL-2b) | Build phase |
| Export | ONNX MLP policies (< 1 MB each) through `s60_export` with the parity check | Build phase |
| Web | Policies run live on TypeScript twins (IL-2 on a TypeScript FEE force and 2-D arm kinematics; IL-1 on the truck twin), labelled "sim-to-sim"; rollouts replayed | Build phase |
| Licences | Isaac Lab is BSD-3; only PitStudio's own procedural machine models are used, no NVIDIA assets; NVIDIA names are nominative and PitStudio is not affiliated with or endorsed by NVIDIA | Policy |
| Dispatch | Fleet dispatch is **not** an Isaac Lab task: [M4 PPO dispatch](../methods/m04-ppo-dispatch.md) uses PitStudio's own vectorised PyTorch environment, because dispatch has no contact physics | Specified in the plan |

**Results: Not yet run — produced in the data-and-models phase.** Pre-registered acceptance criteria from the plan:

| Policy | Criterion | Budget (estimate) |
|---|---|---|
| IL-1 | ≥ 95 % route success without collision over 100 seeded episodes; RMS lateral error ≤ 0.5 m; min TTC ≥ 3 s in ≥ 99 % of episodes; "beats pure pursuit + PID" only by the decision rule; sim-to-sim gap against the TypeScript twin reported | 1–4 GPU-h, ≤ 5 GB |
| IL-2 | Fill factor ≥ 0.8 in ≥ 80 % of FEE episodes; stalls ≤ 5 %; FEE → MPM fill gap reported with its 95 % CI; "beats scripted dig" only by the decision rule on fill × cycle time | 2–8 GPU-h, ≤ 6 GB |
| IL-3 (optional) | Same reporting as IL-2 | 2–3 GPU-h |

The decision rule is [DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md): "better" only if
the paired 95 % confidence interval of the difference excludes 0; see [sim-to-real](sim-to-real.md).

## References

1. Schulman et al. (2017). Proximal Policy Optimization Algorithms. URL: https://arxiv.org/abs/1707.06347
2. Mittal et al. (2025). Isaac Lab: A GPU-Accelerated Simulation Framework for Multi-Modal Robot Learning.
   DOI: 10.48550/arXiv.2511.04831
3. Isaac Lab v3.0.0-EA release note (kit-less Newton workflows, bundled RL libraries). URL:
   https://github.com/isaac-sim/IsaacLab/releases/tag/v3.0.0-EA
4. Isaac Lab documentation: physics backends. URL:
   https://isaac-sim.github.io/IsaacLab/develop/source/concepts/physics_backends.html
5. Isaac Lab documentation: performance benchmarks (memory per environment count). URL:
   https://isaac-sim.github.io/IsaacLab/main/source/overview/reinforcement-learning/performance_benchmarks.html
6. Isaac Lab documentation: available environments. URL:
   https://isaac-sim.github.io/IsaacLab/main/source/overview/environments.html
7. Isaac Lab documentation: `isaaclab_rl` API (policy export). URL:
   https://isaac-sim.github.io/IsaacLab/main/source/api/lab_rl/isaaclab_rl.html
8. Egli et al. (2022). Soil-Adaptive Excavation Using Reinforcement Learning. *IEEE Robotics and Automation Letters*.
   DOI: 10.1109/LRA.2022.3189834
9. Gruetter et al. (2025). Boulder excavation with reinforcement learning in Isaac Lab (descriptive title).
   URL: https://arxiv.org/abs/2509.17683
10. Werner et al. (2026). GPU-parallel MPM reinforcement learning for excavator soil manipulation, transferred to an
    11.5-t excavator (descriptive title). URL: https://arxiv.org/abs/2609.12677
11. Xia et al. (2025). Reinforcement-learning path tracking for mining trucks (descriptive title). *IEEE Transactions on
    Vehicular Technology*. DOI: 10.1109/TVT.2025.3546647
12. Backman et al. (2021). Reinforcement learning for loader bucket filling (descriptive title).
    URL: https://arxiv.org/abs/2103.01283
13. Aoshima, Servin (2024). Wheel-loader control and its simulation-to-reality gap (descriptive title).
    URL: https://arxiv.org/abs/2310.05765
14. Borngrund et al. (2024). Reinforcement learning for the loader's approach to the dump truck (descriptive title).
    URL: https://arxiv.org/abs/2406.13366
15. Zhao et al. (2026). Terrain-aware target selection with RL/IL for excavation (descriptive title).
    URL: https://arxiv.org/abs/2609.29750
16. Tobin et al. (2017). Domain randomization for transferring deep neural networks from simulation to the real world.
    URL: https://arxiv.org/abs/1703.06907
17. Prakash et al. (2019). Structured Domain Randomization. ICRA 2019. URL: https://arxiv.org/abs/1810.10093
18. Reece (1964). The fundamental equation of earth-moving mechanics. *Proc. IMechE* 179(6):16–22 (search excerpt).
    DOI: 10.1243/PIME_CONF_1964_179_134_02
19. `rsl-rl-lib` on PyPI (BSD-3, PPO). URL: https://pypi.org/pypi/rsl-rl-lib/json
20. Isaac Lab PR #8106 (MPM task regression, open) and issue #8236 (no validated MPM material presets). URLs:
    https://github.com/isaac-sim/IsaacLab/pull/8106 · https://github.com/isaac-sim/IsaacLab/issues/8236

Classical sources cited by name only, **not yet verified** against their primary texts (pinned at specification): the
MDP formulation (standard textbooks); Schulman et al. (2015) for generalised advantage estimation; Ng, Harada & Russell
(1999) for potential-based reward shaping.
