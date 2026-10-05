# M09 — Differentiable DEM calibration (Warp tape) vs CMA-ES

> Granular friction parameters are recovered from a target angle of repose and discharge rate by differentiating
> through the GPU DEM with Warp's tape, compared against the gradient-free CMA-ES, and judged by whether the reported
> confidence interval actually covers the truth. · Part of: [Methods](README.md) · Related:
> [M07 GPU granular physics](m07-gpu-granular-physics.md) · [Bulk flow theory](../theory/bulk-flow-dem-mpm.md) ·
> [DEM calibration card](../models/dem-calibration.md) · [Case A3](../cases/a3-loading-payload-variance.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Beyond-SOTA | no (optimisation, not a trained model) | precompute | [A3](../cases/a3-loading-payload-variance.md) | Warp 1.17.0 autodiff (`wp.Tape`, Apache-2.0) in `studio/`; CMA-ES baseline | not yet implemented |

## What and why

Every DEM run is only as credible as its micro-parameters, and calibration is the crux: bulk tests such as the angle
of repose, shear cells or draw-down are matched by tuning parameters, and the parameter sets are often non-unique [1].
Recent work moves from single-angle to full-field heap-profile calibration, still with non-differentiable DEM [2].
Differentiable granular inverse problems exist for learned surrogates [3] but have not been applied to bulk-material
handling with a GPU DEM.

M09 tests whether gradients through PitStudio's own Warp DEM ([M07](m07-gpu-granular-physics.md)) calibrate faster
and as reliably as a strong gradient-free optimiser, and — more importantly — whether the uncertainty it reports is
honest. Differentiable simulation has a known reliability problem: GPU many-to-one sums depend on thread scheduling and
in one documented case flipped the sign of a gradient; finite-difference checks become unreliable when run-to-run
variance dominates; and the way the loss is constructed changes the outcome [4]. M09 adopts those findings as its
protocol.

Newton's implicit MPM is not differentiable (its solver capability matrix marks it so) [5], so MPM materials are
calibrated gradient-free only; the differentiable path uses PitStudio's own Warp kernels.

## The algorithm

### Parameters and loss

Parameters $\theta = (\mu_s, \mu_r, e, \dots)$ — sliding friction, rolling friction, restitution, 3–6 values in total.
A target experiment (a heap formed by pouring, and a flat-bottom hopper discharge) gives target observables. The loss
is

$$
\mathcal{L}(\theta) = w_\alpha \big(\alpha_{\text{sim}}(\theta) - \alpha^{\ast}\big)^2
+ w_Q \Big(\frac{Q_{\text{sim}}(\theta) - Q^{\ast}}{Q^{\ast}}\Big)^2
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $\alpha_{\text{sim}}$, $\alpha^{\ast}$ | simulated and target angle of repose | ° |
| $Q_{\text{sim}}$, $Q^{\ast}$ | simulated and target discharge rate | kg/s |
| $w_\alpha$, $w_Q$ | loss weights | 1/°², – |

To make $\alpha_{\text{sim}}$ differentiable, the heap surface is a smooth upper envelope of particle heights per
radial bin, and the angle is the arctangent of the least-squares slope of that envelope (planned construction, fixed in
the spec). Both terms and their weights are reported with every result, as [4] recommends.

### Gradient path: Warp tape

`wp.Tape` records the forward kernels and replays their adjoints [6]. Three documented constraints shape the design
[6]:

- intermediate states must be stored, so long rollouts cost memory → differentiate over **short windows** of
  500–2,000 steps after a non-differentiated settling phase;
- writing the same array element more than once in a kernel gives wrong gradients → contact forces are accumulated
  into per-contact buffers, then reduced;
- dynamic loops are not replayed in the backward pass → fixed iteration counts.

Accumulation uses Warp's deterministic atomic mode so gradients are reproducible run to run [7]. Memory estimate:
$2\times10^4$ particles × 24 B (position and velocity, fp32) ≈ 0.5 MB per step, so 2,000 steps ≈ 1 GB plus contact
buffers — within 16 GB (ESTIMATE).

```text
calibrate_gradient(theta0, targets):
    theta = theta0
    for it in 1..K:
        state = settle(theta)                          # not recorded
        with wp.Tape() as tape:
            obs = run_window(state, theta, steps=W)    # deterministic accumulation
            loss = L(obs, targets)
        tape.backward(loss)
        check: |grad - fd_grad| vs run-to-run spread   # reliability gate (see below)
        theta = adam_step(theta, theta.grad)
    return theta, uncertainty(theta)
```

### Baseline: CMA-ES

CMA-ES samples candidate parameter vectors from a multivariate normal distribution, evaluates the loss by running the
simulator (no gradients), and adapts the mean, step size and covariance from the ranked candidates [8]. It is robust to
the noisy, non-smooth losses that contact mechanics produces, which is exactly why it is the right yardstick.

### Reliability protocol

1. **Deterministic accumulation** for every gradient run [4][7].
2. **Finite-difference check against run-to-run variance:** a gradient component is trusted only if its
   finite-difference estimate is resolved above the spread of repeated runs [4].
3. **Transparent loss reporting:** the loss terms, weights and windows are published with the result [4].

### Uncertainty and coverage

Each calibration reports a 95 % confidence interval for every recovered parameter (method fixed in the spec, for
example bootstrap over initial packings and seeds). The interval is tested on **synthetic truth**: pick $\theta^{\ast}$,
simulate its observables, calibrate from a different start, and record whether $\theta^{\ast}$ falls inside the
interval. Repeating this gives an empirical coverage.

## Baseline and comparison

- **Gradient (Warp tape) vs CMA-ES** on the same synthetic-truth trials: recovered-parameter error, coverage, number
  of simulator calls and wall time to reach a fixed loss.
- **Against literature targets:** the calibrated material reproduces handbook repose angles (crushed gravel, sand;
  see [M07](m07-gpu-granular-physics.md#physics-benchmarks)) — these are the real-world anchor, while synthetic truth
  is the correctness test.
- Any "faster" or "more accurate" claim follows the [decision rule](README.md#how-methods-are-compared), paired over
  the same trials.

## Acceptance criterion (pre-registered)

- **The 95 % CI of the recovered parameter covers the synthetic truth in ≥ 90 % of trials** (for both methods).
- Every reported gradient passes the reliability protocol above.

**Results: Not yet run** — produced in the data-and-models phase. Reported: coverage, parameter error, calls and wall
time per method; the baked loss landscape around the optimum; the calibrated parameter set used by
[M07](m07-gpu-granular-physics.md) and the MPM evaluation tier of [M21](m21-isaac-lab-policies.md).

## Lane and web delivery

**Precompute.** Each calibration takes about 0.2–2 GPU-hours (estimate) in the `studio/` environment. The web shows
the baked loss landscape, the optimiser paths (gradient vs CMA-ES) and the fitted heap profile as a TypeScript replay.

## Assumptions and limits

- Non-uniqueness is real [1]: two targets (repose and discharge) constrain at most two independent parameters well;
  the remaining ones are reported as weakly identified, not "calibrated".
- Short differentiable windows capture local sensitivity; very slow processes (creep of a stockpile) are out of reach.
- Synthetic-truth coverage proves the method, not the material: real-ore parameters still need real lab targets.

## In PitStudio

- **Cases:** [A3](../cases/a3-loading-payload-variance.md) (calibrated material for bucket filling and the MPM
  evaluation of the digging policy).
- **Code (planned):** `studio/` environment, `pitstudio_studio.physics` (calibration driver next to the DEM kernels),
  stage `st50_physics`; baked results published with `studio publish`. Card:
  [DEM calibration](../models/dem-calibration.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Coetzee, C. J. (2017). Review: Calibration of the discrete element method. Powder Technology 310:104–142.
   https://doi.org/10.1016/j.powtec.2017.01.015
2. arXiv listing: heap-morphology DEM calibration (2605.09371) and related work.
   http://export.arxiv.org/api/query?search_query=all:DEM%20AND%20all:calibration%20AND%20all:repose&max_results=8
3. Choi, Y. & Kumar, K. (2024). *Inverse analysis of granular flows using differentiable graph neural network
   simulator*. https://arxiv.org/abs/2401.13695
4. Yang et al. (2026). *On the Numerical Reliability of Differentiable Physics-Based Optimization*.
   https://arxiv.org/abs/2609.34666
5. Newton solver documentation — differentiability matrix (implicit MPM not differentiable).
   https://newton-physics.github.io/newton/stable/solvers/index.html
6. NVIDIA Warp — differentiability (Tape, stored intermediates, overwrites, dynamic loops).
   https://nvidia.github.io/warp/stable/user_guide/differentiability.html
7. NVIDIA Warp releases — deterministic atomic modes (1.15). https://github.com/NVIDIA/warp/releases
8. Hansen, N. (2016). *The CMA Evolution Strategy: A Tutorial*. https://arxiv.org/abs/1604.00772
