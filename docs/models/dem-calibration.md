# DEM calibration — differentiable Warp tape vs CMA-ES

> Recovers the friction parameters of a GPU DEM model from a target angle of repose, once by differentiating through the
> simulation with Warp's tape and once with the gradient-free CMA-ES, and checks that the recovered intervals cover a
> known synthetic truth. · Part of: [Models](README.md) · Related:
> [M9 Differentiable DEM calibration](../methods/m09-differentiable-dem-calibration.md) ·
> [Bulk flow, DEM and MPM](../theory/bulk-flow-dem-mpm.md) · [Warp](../frameworks/warp.md) ·
> [Case A3](../cases/a3-loading-payload-variance.md)

## What and why

Every DEM result depends on micro-parameters — sliding friction, rolling resistance, restitution — that cannot be
measured on a grain and are instead tuned until a bulk test such as the angle of repose matches; the parameter sets
found this way are often non-unique [1]. Calibration is usually a grid or black-box search over many full runs.
Warp kernels are differentiable, so the loss gradient can be taken through the simulation itself [2]. PitStudio's
beyond-SOTA question is whether that gradient path recovers parameters as reliably as a strong gradient-free baseline,
**with honest uncertainty**: not one best fit, but an interval that must cover the truth. There are no network weights
here; the "model" is a calibrated parameter set with its interval.

## Model card

### Intended use

- Calibrate the friction parameters of the studio's Warp DEM (and the dry-sand material used by the Newton MPM runs)
  against literature angle-of-repose targets, for cases A3 and D1 and for the GNS training data.
- Compare differentiable and gradient-free calibration on synthetic targets with known truth.

### Out of scope

- Site-specific material characterisation (no lab tests of a real ore are available).
- Gradient calibration of Newton's implicit MPM: that solver is **not differentiable**, so MPM calibration is
  gradient-free only [3].

### Architecture

**Forward model.** A soft-sphere DEM kernel in Warp: Hertz normal contact
$F_n=\tfrac43E^{\ast}\sqrt{R^{\ast}}\,\delta_n^{3/2}$, Coulomb sliding $|F_t|\le\mu_s F_n$ and a rolling-resistance torque
capped at $\mu_r R^{\ast}F_n$ [4][5]. $E^\ast$ effective Young's modulus (Pa), $R^\ast$ effective radius (m),
$\delta_n$ overlap (m), $\mu_s$ sliding and $\mu_r$ rolling friction coefficients (–). (The Hertz transcription is
UNVERIFIED against the primary text until pinned at specification.)

**Observable and loss.** The repose angle of the settled heap, $\theta_r(\boldsymbol\mu)$ (°), is the arctangent of the
least-squares slope of the heap's free surface — a smooth function of particle positions, so it can be differentiated.
For a target $\theta^\ast$:

$$
\mathcal L(\boldsymbol\mu)=\big(\theta_r(\boldsymbol\mu)-\theta^\ast\big)^2
$$

**Path 1 — Warp tape.** `wp.Tape` records the forward kernels and replays their adjoints to give
$\partial\mathcal L/\partial\boldsymbol\mu$ [2]. Gradients are taken over short windows (500–2,000 steps). Memory
grows with the window because intermediate states are stored: at 24 B per particle and step (fp32 position + velocity)
and 20,000 particles that is about 0.48 MB per step, so 2,000 steps ≈ 1 GB plus contact buffers — it fits 16 GB.
Warp's own rules apply: an array element written more than once in a recorded kernel gives wrong gradients, and
dynamic loops are not replayed in the backward pass [2].

**Path 2 — CMA-ES.** Each generation samples $\lambda$ candidates
$\boldsymbol\mu_k=\mathbf m+\sigma\,\mathbf y_k$, $\mathbf y_k\sim\mathcal N(\mathbf 0,\mathbf C)$, ranks them by
$\mathcal L$, moves the mean $\mathbf m$ to a weighted average of the best, and adapts the covariance $\mathbf C$ and step
size $\sigma$ [6]. It needs no gradient, so it works on any solver.

**Interval.** Each method reports a 95 % interval for the recovered parameter; how it is formed (for example over
repeated runs with different particle-packing seeds) is fixed in the surrogates spec, identically for both methods.

### Training data

- **Synthetic truth:** heaps simulated with a known $\boldsymbol\mu^\dagger$ give a target $\theta^\ast$; the calibration
  must recover $\boldsymbol\mu^\dagger$. Ours, CC-BY-4.0.
- **Literature targets:** published angle-of-repose values for granular materials, cited with their source and
  verification status in the `minephys` knowledge tables (values UNVERIFIED — pinned at specification) [1].
- Repose alone constrains a combination of $\mu_s$ and $\mu_r$; the spec fixes which parameter is calibrated and which
  are held at cited values, so the problem is identifiable.

### Budget (estimate)

**0.2–2 GPU-h per calibration** (each method, each target), 1–4 GB VRAM. Runs in `studio/` (Python 3.14, Warp 1.17,
Newton 1.6). Measured by the runner probe `studio bench`; the GPU probes are written but not yet run on the reference
machine.

### Export and web lane

- **Baked**: no ONNX. Outputs are parameter sets, intervals and calibration curves (loss vs iteration, $\theta_r$ vs
  $\mu$), shown as REPLAY with the heap rollouts; a TS replay of the curves is the web view.
- **TensorRT relevance — none** (no network).

### Pre-registered acceptance criteria

- **The 95 % CI of the recovered parameter covers the synthetic truth in ≥ 90 % of trials.**
- Comparisons between the two methods (interval width, wall time, loss evaluations) use the decision rule for any
  "better than" claim ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

Worked numbers: a perfectly calibrated 95 % interval covers the truth in 95 % of trials on average, yet with 50 trials
it would still fall below 45 hits (the ≥ 90 % bar) with probability about 3.8 %, and with 100 trials below 90 hits with
probability about 1.1 % (binomial arithmetic). The number of trials is fixed in the spec with this in mind.

### Evaluation protocol

- Trials: draw $\boldsymbol\mu^\dagger$ across the plausible range, simulate $\theta^\ast$, run both calibrations from the
  same starting point, record the estimate, the interval and coverage.
- Gradient reliability checks, which recent work shows are necessary for long-horizon differentiable physics:
  deterministic accumulation in contact sums (GPU many-to-one sums depend on thread order and once flipped a gradient's
  sign), finite-difference checks compared against run-to-run variance, and the loss construction reported in full [7].
- Literature targets: recovered parameters reported with intervals; no truth exists, so no coverage claim.

### Licence of weights

No weights. Calibrated parameter sets and curves are our data (CC-BY-4.0); code Apache-2.0; Warp and Newton are
Apache-2.0 [2][3]; literature targets are cited facts.

## Assumptions and limits

- Spheres with rolling resistance stand in for angular rock; the calibrated values are effective, model-specific
  parameters, not material constants [5].
- Contact gradients are noisy; short windows trade bias for memory. A failure of the gradient path is a reported
  result, not hidden.
- One bulk test (repose) cannot identify all micro-parameters [1].
- Simulation-grade twin; educational.

## In PitStudio

- **Cases:** [A3](../cases/a3-loading-payload-variance.md) (bucket and truck-bed material),
  [D1](../cases/d1-blast-muck-pile.md) (muck-pile DEM).
- **Methods:** [M9](../methods/m09-differentiable-dem-calibration.md), feeding [M7](../methods/m07-gpu-granular-physics.md),
  the [GNS surrogate](gns-granular.md) and the Isaac Lab MPM evaluation tier ([Isaac Lab policies](isaac-lab-policies.md)).
- **Env and stages:** `studio/` `st50_physics` (calibration runs) → `studio publish <run>` (baked curves and run card).
  Engine decision: [DEC-0012](../architecture/decisions/DEC-0012-granular-physics-warp-newton.md).

## Results

**Not yet run** — produced in the data-and-models phase. Will be reported: coverage of the synthetic truth by each
method's 95 % CI (acceptance ≥ 90 % of trials), interval widths, wall time and number of simulations per calibration,
gradient-check outcomes, and the recovered parameters with intervals for each literature target.

## References

1. Coetzee, C. J. (2017). Review: Calibration of the discrete element method. Powder Technol. 310:104–142.
   https://doi.org/10.1016/j.powtec.2017.01.015
2. NVIDIA Warp documentation — differentiability (`wp.Tape`, stored intermediates, overwrite and loop caveats).
   https://nvidia.github.io/warp/stable/user_guide/differentiability.html
3. Newton solvers (differentiability matrix: `SolverImplicitMPM` not differentiable).
   https://newton-physics.github.io/newton/stable/solvers/index.html
4. Cundall, P. A., Strack, O. D. L. (1979). A discrete numerical model for granular assemblies. Géotechnique
   29(1):47–65. https://doi.org/10.1680/geot.1979.29.1.47
5. Ai, J., Chen, J.-F., Rotter, J. M., Ooi, J. Y. (2011). Assessment of rolling resistance models in DEM. Powder
   Technol. 206:269–282. https://doi.org/10.1016/j.powtec.2010.09.030
6. Hansen, N. (2016). *The CMA Evolution Strategy: A Tutorial*. https://arxiv.org/abs/1604.00772
7. Yang et al. (2026). On the numerical reliability of differentiable physics-based optimization.
   https://arxiv.org/abs/2609.34666
