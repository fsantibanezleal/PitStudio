# M04 — PPO dispatch policy in a GPU-vectorised haulage environment

> A truck-dispatch policy trained with proximal policy optimisation in thousands of parallel, GPU-resident haulage
> simulations, exported to ONNX and run live inside the browser's DES, judged against SPTF and LP dispatch on paired
> seeds. · Part of: [Methods](README.md) · Related: [Robot learning theory](../theory/robot-learning.md) ·
> [M02 DES](m02-haulage-des.md) · [M05 attention policy](m05-attention-fleet-policy.md) ·
> [Dispatch policy cards](../models/dispatch-policies.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| SOTA | **yes** | precompute → live | [A1](../cases/a1-truck-shovel-dispatch.md) | PyTorch cu130 (BSD-style) in `pipeline/`; ONNX MLP | not yet implemented |

## What and why

Reinforcement-learning dispatch is published but not reproducible across simulators. Zhang et al. report a 5.56 %
productivity gain over an industry baseline with an experience-sharing DQN in an event-based simulator calibrated on
real operations [3]; Meng, Tian and Zhang report about 10 % over plain PPO with curriculum-guided, time-delta-aware
PPO on the open OpenMines simulator [4]; Noriega, Pourrahimian and Askari-Nasab train a DDQN inside a DES [6] (their
headline figures are UNVERIFIED — source unreachable). Each paper uses its own simulator and its own baseline, and none
publishes a policy that a reader can run.

M04 closes that gap honestly:

- the environment is a **batched PyTorch tensor version of the haulage cycle**, so thousands of mines train in
  parallel on one GPU without any robotics stack;
- the policy is evaluated in an **independent** engine — the `minehaulsim` DES of [M02](m02-haulage-des.md) — so it
  cannot overfit the training simulator's quirks;
- it must beat **SPTF and two-stage LP dispatch** ([M03](m03-lp-dispatch.md)) under the pre-registered decision rule,
  or the site says "no significant difference";
- the trained policy is small enough to run **live** in the browser, inside the same TypeScript DES the visitor is
  watching.

![Vectorised dispatch environment, PPO and attention policies, baselines and the paired-seed decision rule](../assets/diagrams/dispatch-policy-env.svg)

*Training happens in the GPU-vectorised environment; evaluation happens in the independent DES on paired seeds
against SPTF and LP; the exported ONNX policy also runs live in the browser DES.*

## The algorithm

### Environment

The training environment is a batched tensor environment written in the repository (no robotics stack):

- **Batch:** $B$ parallel mines, each with up to 40 trucks, a few shovels and dumps; padded to 40 trucks with a mask.
- **Time:** event-stepped with a fixed decision tick $\Delta t$; between ticks the haul cycle advances in closed form
  on the GPU.
- **Decision:** every truck that becomes free at a tick chooses "which shovel (or dump) next" from a **masked**
  discrete action set (unreachable or closed targets masked out).
- **Observation per truck** (planned): its state and location, payload, expected travel time to each target, queue
  length and expected start-of-loading time at each shovel, plus pooled shovel and dump features. The exact feature
  list is fixed in the spec.
- **Reward** (planned): tonnes delivered since the last decision, so that the return is proportional to the A1 KPI,
  tonnes per hour.

### PPO objective

PPO maximises the clipped surrogate objective [1]:

$$
L^{\text{CLIP}}(\theta) = \mathbb{E}_k\!\left[\min\!\Big(r_k(\theta)\,\hat A_k,\;
\operatorname{clip}\big(r_k(\theta),\,1-\epsilon,\,1+\epsilon\big)\,\hat A_k\Big)\right],
\qquad r_k(\theta) = \frac{\pi_\theta(a_k \mid s_k)}{\pi_{\theta_{\text{old}}}(a_k \mid s_k)}
$$

plus a value-function loss and an entropy bonus. Here $\pi_\theta$ is the policy (a distribution over the masked
action set), $a_k, s_k$ the action and observation at decision $k$, $\hat A_k$ the advantage estimate and $\epsilon$
the clip range (dimensionless; value fixed in the training recipe).

Dispatch decisions are **unevenly spaced in time**, so the discount is applied per elapsed time, as in the
time-delta-aware TD/GAE of Meng et al. [4], on top of generalised advantage estimation [2]:

$$
\delta_k = r_k + \gamma^{\Delta t_k} V(s_{k+1}) - V(s_k), \qquad
\hat A_k = \sum_{l \ge 0} \Big(\prod_{j=0}^{l-1} (\gamma\lambda)^{\Delta t_{k+j}}\Big)\, \delta_{k+l}
$$

with $\Delta t_k$ the time between decisions $k$ and $k+1$ (in ticks), $\gamma$ the per-tick discount, $\lambda$ the
GAE parameter and $V$ the learned value function.

### Policy network

A **parameter-shared MLP** scores each (truck, target) pair from the truck's features and the target's features, and
a masked softmax over targets gives $\pi_\theta$. Sharing the parameters across trucks lets one network serve fleets
of 10–40 trucks. The size-invariant attention variant is [M05](m05-attention-fleet-policy.md). The trainer follows the
single-file PPO style of CleanRL [7].

```text
for iteration in 1..I:
    rollouts = env.step_batched(policy, B envs, T ticks)      # GPU tensors, no Python loop per truck
    adv, ret = time_delta_gae(rollouts, gamma, lam)
    for epoch in 1..E, minibatch in shuffle(rollouts):
        loss = -L_clip + c_v * value_loss + -c_e * entropy
        step(optimizer, loss)
    every N iterations: evaluate in minehaulsim on validation seeds (never the test seeds)
```

### Training data and budget

No external data: the environment generates experience. **Budget (estimate, measured by the `studio bench` probe
before any long run):** 1–5 GPU-hours and 2–4 GB of VRAM for PPO and attention together. The engineering estimate
behind it is 4,096 environments × 40 trucks with a 2×256 MLP at roughly 0.2–1 M decisions/s, so 100–300 M decisions
take about 1–4 h (ESTIMATE, not measured). The GPU capability probes are written but not yet run on the reference
machine.

### Export

- `torch.onnx` export at **opset 17–19** with the **ONNX IR version pinned** to what ONNX Runtime 1.30 (Python and
  web) and TensorRT read: `onnx` 1.23.1 writes IR 14 by default while ORT 1.30 reads at most IR 13, so the export
  pins it explicitly ([export, parity and acceleration](../models/export-parity-acceleration.md)).
- The graph contains Gemm/MatMul/Softmax only, which run on the WASM and WebGPU execution providers [8]. The mask
  and the arg-max are applied in JavaScript.
- Size: under 2 MB.

## Baseline and comparison

- **Baselines:** SPTF (the strongest classical rule in the open dispatch benchmarks [5]) and two-stage LP dispatch
  ([M03](m03-lp-dispatch.md)). Fixed allocation and nearest-shovel are reported for context.
- **Engine:** the `minehaulsim` DES ([M02](m02-haulage-des.md)), not the training environment.
- **Pairing:** at least 30 seeds; on seed $i$ every dispatcher sees the same breakdowns, loading-time variates and
  travel noise (common random numbers). The paired difference is
  $d_i = \text{t/h}_{\text{policy},i} - \text{t/h}_{\text{baseline},i}$.
- **Interval:** the paired $t$ interval [9]
  $\bar d \pm t_{0.975,\,n-1}\, s_d/\sqrt{n}$, with $\bar d$ the mean and $s_d$ the standard deviation of the
  $d_i$ (t/h), and $n$ the number of seeds. The [decision rule](README.md#how-methods-are-compared) calls the
  policy better only if the whole interval is above 0.

**Worked example (illustrative numbers).** With $n = 30$, $t_{0.975,29} \approx 2.045$ and $s_d = 110$ t/h, the
half-width is $2.045 \times 110/\sqrt{30} = 41.1$ t/h. A mean gain of 45 t/h gives [3.9, 86.1] t/h → "better". A mean
gain of 30 t/h gives [−11.1, 71.1] t/h → "no significant difference", even though the point estimate is positive.

## Acceptance criterion (pre-registered)

- **At least 30 paired seeds.**
- **"Beats SPTF / LP" only by the decision rule on t/h**: the paired 95 % CI of the difference must exclude 0;
  otherwise the UI says "no significant difference".
- Export: ONNX vs PyTorch parity on a golden set (fp32: rtol 1e-3 / atol 1e-5), and action agreement reported for
  every reduced-precision or TensorRT variant; failing variants are reported as rejected
  ([DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)).

**Results: Not yet run** — produced in the data-and-models phase. Reported: t/h, queue time and shovel idle for the
policy and each baseline with paired 95 % CIs; training curves; the TensorRT acceleration row. At batch 1 inside a DES
a 0.1–0.5 M-parameter MLP is launch-bound, so "no material TensorRT gain" is the expected and publishable finding
(estimate).

## Lane and web delivery

**Precompute → live.** Training and the paired-seed evaluation are precomputed. The exported policy (< 2 MB) runs in
ONNX Runtime Web inside the TypeScript DES worker, so a visitor can switch the dispatcher of the running simulation
from SPTF to the learned policy. Gate: policies < 2 MB and one shift ≈ $10^4$ events in < 1 s (estimates, measured
when the web is built). Fallback: baked traces.

## Assumptions and limits

- The policy is optimal only for the simulated mine family it was trained on (generator ranges, fleet sizes up to 40).
- The training environment's event tick approximates continuous-time dispatch; the independent DES evaluation exists
  to catch the resulting bias.
- No claim of field performance: there is no haul telemetry to validate against. Published percentage gains [3][4]
  come from other simulators and baselines and are not comparable.
- Isaac Lab is deliberately not used here: dispatch has no contact physics, so its value does not apply
  ([M21](m21-isaac-lab-policies.md) explains where it does).

## In PitStudio

- **Cases:** [A1](../cases/a1-truck-shovel-dispatch.md).
- **Code (planned):** the vectorised environment and PPO trainer in `pipeline/` (stage `s30_train`), evaluation in
  `s50_evaluate` against `minehaulsim`, export in `s60_export`, optional TensorRT rows in `pipeline/accel/`
  (`s62_accel`, `s64_bench`); live inference in the `web/` DES worker. Model card:
  [dispatch policies](../models/dispatch-policies.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Schulman, J., Wolski, F., Dhariwal, P., Radford, A. & Klimov, O. (2017). *Proximal Policy Optimization
   Algorithms*. https://arxiv.org/abs/1707.06347
2. Schulman, J., Moritz, P., Levine, S., Jordan, M. & Abbeel, P. (2016). *High-Dimensional Continuous Control Using
   Generalized Advantage Estimation*. ICLR. https://arxiv.org/abs/1506.02438
3. Zhang et al. (2020). *Dynamic Dispatching for Large-Scale Heterogeneous Fleet via Multi-agent Deep Reinforcement
   Learning*. https://arxiv.org/abs/2008.10713
4. Meng, Tian & Zhang (2025). Curriculum-guided PPO with time-delta-aware TD/GAE for truck dispatching on OpenMines.
   https://arxiv.org/abs/2502.20845
5. OpenMines — open-pit dispatch simulator with baseline dispatchers (Nearest, FixedGroup, SPTF, SQ), MIT.
   https://github.com/370025263/openmines
6. Noriega, Pourrahimian & Askari-Nasab (2025). DDQN dispatch trained in a DES. Computers & Operations Research
   (headline figures UNVERIFIED — source unreachable). https://doi.org/10.1016/j.cor.2024.106815
7. CleanRL — single-file PPO reference implementations (MIT). https://github.com/vwxyzjn/cleanrl
8. ONNX Runtime 1.30.0 WebGPU execution-provider kernel registry.
   https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/core/providers/webgpu/webgpu_execution_provider.cc
9. *Student's t-test* — dependent (paired) samples. https://en.wikipedia.org/wiki/Student%27s_t-test
