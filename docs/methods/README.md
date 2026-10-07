# Methods

> The method ladder of PitStudio: 23 methods from classical engineering models through the state of the art to
> beyond-state-of-the-art physical-AI builds, each compared against a classical baseline under one pre-registered
> decision rule. · Part of: [Documentation](../README.md) · Related: [Theory](../theory/README.md) ·
> [Cases](../cases/README.md) · [Models](../models/README.md) · [Compute lanes](../pipelines/compute-lanes.md)

Every page follows the same order: what and why → the algorithm (equations or pseudo-code; for learned methods the
architecture, inputs and outputs, loss, data, budget and export) → the baseline and how it is compared → the
pre-registered acceptance criterion → lane and web delivery → assumptions and limits → where it lives in PitStudio →
references. Derivations live on the [theory pages](../theory/README.md); model details live on the
[model cards](../models/README.md).

**Status of every method: not yet implemented — built test-first in the build phase.** No model has been trained and
nothing has been rendered yet; every results section says "Not yet run" and lists what will be reported.

![Method ladder: 23 methods by tier and delivery lane, learned methods marked](../assets/diagrams/method-ladder.svg)

*Rows are tiers (classical, SOTA, beyond-SOTA and frontier), columns are delivery lanes; a dot marks the 11 learned
methods.*

## The ladder

| # | Method | Tier | Learned | Lane | Cases | Page |
|---|---|---|---|---|---|---|
| M01 | Match factor + finite-source queue / MVA | Classical | no | live | A1 | [m01](m01-match-factor-queueing.md) |
| M02 | Haulage DES with classical dispatchers | Classical | no | live + precompute | A1, A2, B1, C3 | [m02](m02-haulage-des.md) |
| M03 | Two-stage LP dispatch | Classical / industry SOTA | no | live (small) + precompute | A1 | [m03](m03-lp-dispatch.md) |
| M04 | PPO dispatch in a GPU-vectorised environment | SOTA | **yes** | precompute → live | A1 | [m04](m04-ppo-dispatch.md) |
| M05 | Attention fleet policy | Beyond-SOTA | **yes** | precompute → live | A1 | [m05](m05-attention-fleet-policy.md) |
| M06 | Haul-road energy + grade-constrained routing (diesel / trolley / BEV) | Classical | no | live | A2, E1 | [m06](m06-haul-road-energy-routing.md) |
| M07 | GPU granular physics: Warp DEM + Newton implicit MPM | SOTA | no | replay + live WGSL twin | A3, D1 | [m07](m07-gpu-granular-physics.md) |
| M08 | GNS granular surrogate, live in the browser | Beyond-SOTA | **yes** | precompute → live | A3 | [m08](m08-gns-surrogate.md) |
| M09 | Differentiable DEM calibration (Warp tape) vs CMA-ES | Beyond-SOTA | no | precompute | A3 | [m09](m09-differentiable-dem-calibration.md) |
| M10 | Synthetic-data detector + DR ablation | SOTA | **yes** | precompute → live (ORT-web) | B2 | [m10](m10-synthetic-data-detector.md) |
| M11 | Fragmentation: watershed + Swebrec vs U-Net on synthetic exact-PSD muck piles | Classical vs beyond-SOTA | **yes** | live | D1 | [m11](m11-fragmentation-segmentation.md) |
| M12 | Kuz-Ram/KCO + Swebrec + PPV + flyrock | Classical | no | live | D1, D2 | [m12](m12-blast-fragmentation-models.md) |
| M13 | LEM (Bishop, Spencer) + Hoek–Brown + Monte-Carlo PoF | Classical | no | live | C1 | [m13](m13-slope-stability-lem.md) |
| M14 | Inverse velocity + Bayesian TTF vs TCN / PatchTST / Chronos-Bolt | Classical vs SOTA | **yes** | live | C1 | [m14](m14-slope-forecasting.md) |
| M15 | GPU shallow water (Bingham) + FNO surrogate | SOTA + learned | **yes** | precompute → live | C2 | [m15](m15-shallow-water-fno.md) |
| M16 | AP-42 + Gaussian plume + Lagrangian dust | Classical / SOTA | no | live + precompute | C3 | [m16](m16-dust-dispersion.md) |
| M17 | Bond/Morrell + PBM + mine-to-mill meta-model | Classical + learned | **yes** | live | D2 | [m17](m17-comminution-mine-to-mill.md) |
| M18 | Min-cut ultimate pit + nested shells + MILP scheduling | Classical / SOTA | no | live + precompute | E1 | [m18](m18-pit-optimisation-scheduling.md) |
| M19 | COLMAP → 3D Gaussian splatting → volume vs DEM differencing | SOTA | **yes** (per-scene reconstruction) | precompute → view + live volume | E2 | [m19](m19-gaussian-splat-survey.md) |
| M20 | Agent-based traffic + TTC + rigid-body vehicles | Classical / SOTA | no | live + replay | B1 | [m20](m20-traffic-ttc.md) |
| M21 | Isaac Lab policies: IL-1 haul truck, IL-2 excavator (+ MPM check), IL-3 loader (optional) | SOTA → beyond-SOTA | **yes** | precompute → live (TS twins) | A2, A3 | [m21](m21-isaac-lab-policies.md) |
| M22 | Cosmos Reason 2 VLM tasks (hazard VQA, plausibility, captions) | Frontier | **yes** (zero-shot) | precompute (display-only) | B1, B2 | [m22](m22-cosmos-vlm-tasks.md) |
| M23 | RTX sensor simulation (lidar in dust/rain, survey and crusher cameras, radar, slope radar) | SOTA | no | precompute; live dust slider | B1, B2, C1, E2 | [m23](m23-rtx-sensor-simulation.md) |

23 methods, 11 learned. Every method is exercised by at least one case; the generated
[coverage matrix](../cases/coverage-matrix.md) and [tool matrix](../cases/tool-matrix.md) show the full mapping. No
headline KPI depends on the optional frontier pieces (Cosmos, the Isaac Lab MPM tier); each has a fallback that the
open lane reproduces.

## How methods are compared

### A classical baseline for every learned method

| Learned method | Baseline(s) | Metric for "better" | Pair unit |
|---|---|---|---|
| [M04](m04-ppo-dispatch.md) PPO dispatch | SPTF, two-stage LP ([M03](m03-lp-dispatch.md)) | t/h in the independent DES | seed (≥ 30) |
| [M05](m05-attention-fleet-policy.md) attention policy | SPTF, LP, and M04 | t/h | seed (≥ 30) |
| [M08](m08-gns-surrogate.md) GNS | the GPU solver ([M07](m07-gpu-granular-physics.md)) | repose and run-out on held-out geometries | geometry |
| [M10](m10-synthetic-data-detector.md) detector | unstructured-DR arm | mAP50 (synthetic held-out) | fixed in the spec |
| [M11](m11-fragmentation-segmentation.md) U-Net | watershed + Swebrec | x50 error | test image |
| [M14](m14-slope-forecasting.md) forecasters | inverse velocity, Bayesian TTF | TTF error / lead time | seeded synthetic event |
| [M15](m15-shallow-water-fno.md) FNO | the Warp solver | relative $L^2$ on held-out terrains | terrain |
| [M17](m17-comminution-mine-to-mill.md) meta-model | the analytical chain | $R^2$ on held-out sweeps | sweep point |
| [M19](m19-gaussian-splat-survey.md) splat survey | DEM differencing, exact synthetic volume | volume error (reported) | flight |
| [M21](m21-isaac-lab-policies.md) Isaac Lab policies | pure pursuit + PID; scripted dig | success, lateral error, TTC; fill × cycle time | seeded episode |
| [M22](m22-cosmos-vlm-tasks.md) Cosmos tasks | Qwen3-VL-2B base, detector + rule, majority | balanced accuracy | query (McNemar) |

### The pre-registered decision rule

A result is called **better** only if the paired 95 % confidence interval of the difference excludes 0; otherwise the
UI says **"no significant difference"**
([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)). The rule is unit-tested in the build
phase and checked again on the real artefacts before the web shows them.

For paired units $i = 1 \dots n$ (seeds, events, images), with $d_i$ the difference in the metric between challenger
and baseline on unit $i$, the default interval is the paired $t$ interval
$\bar d \pm t_{0.975,\,n-1}\, s_d/\sqrt n$, where $\bar d$ and $s_d$ are the mean and standard deviation of the $d_i$
([Student's t-test, paired samples](https://en.wikipedia.org/wiki/Student%27s_t-test)); metrics that are not
approximately normal use a paired bootstrap, chosen per metric in the spec. Pairing (common random numbers: the same
seed gives every method the same variates) removes most of the noise that would otherwise hide real differences.

Two pre-registered exceptions:

- **One real slope failure ($n = 1$).** The de Wit series is reported descriptively at fixed record cut-offs; the UI
  says "single real event — no significance test" ([M14](m14-slope-forecasting.md)).
- **Paired classification answers.** "Cosmos beats the Qwen base model" requires McNemar $p < 0.05$
  ([M22](m22-cosmos-vlm-tasks.md)).

Results are always reported on several axes together (for dispatch: t/h, queue time, shovel idle, cost/t), never as one
number.

### Parity gates

A method only reaches the browser if its web implementation agrees with its reference:

| Layer | Parity class | Check |
|---|---|---|
| Analytical `minephys` ↔ TypeScript port | exact | golden vectors to floating-point tolerance |
| DES Python ↔ TypeScript twin | exact | identical event traces ([M02](m02-haulage-des.md)) |
| Rapier rigid bodies | exact (same version) | snapshot hash ([M20](m20-traffic-ttc.md)) |
| Warp ↔ WGSL granular kernels | statistical | observables, not bits ([M07](m07-gpu-granular-physics.md)) |
| PyTorch ↔ ONNX (CPU, WebGPU, WASM) | numerical | fp32 rtol 1e-3 / atol 1e-5; reduced precision Δ ≤ 1 pp |
| ONNX ↔ TensorRT engines | numerical, per engine | same thresholds on every TensorRT version and execution provider; failing variants reported as rejected ([DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)) |

### The lane gate

A capability is **live** only if it is web-drivable, its asset is ≤ 25 MB, an interaction takes ≤ 16 ms (or a run
≤ 1 s on the WASM tier), and its trace is ≤ 10 MB; otherwise it is **precompute** or **replay**. The lane is measured,
recorded in the artefact manifest, and CI fails on a mislabel. The gate numbers on each method page are estimates
until they are measured when the web is built. See [compute lanes](../pipelines/compute-lanes.md) and
[web compute tiers](../web/compute-tiers.md).

### Honesty rules that apply to every page

- **Not yet run** until the data-and-models phase produces the result; budgets are estimates until the `studio bench`
  capability probe measures them (the probes are written but not yet run on the reference machine).
- Synthetic data without a real reference is labelled "calibrated synthetic — not validated against real data".
- Performance data of Isaac Sim, Kit, Replicator, ovrtx and TensorRT for RTX stay local-only (NVIDIA SLA §8.9,
  TensorRT-RTX SLA §2.13); regular TensorRT numbers of PitStudio's own models are publishable
  ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).
- PitStudio is a simulation-grade twin, not a live digital twin, and its slope, tailings and blasting outputs are
  educational, not design or regulatory software.

## Pages

[m01](m01-match-factor-queueing.md) · [m02](m02-haulage-des.md) · [m03](m03-lp-dispatch.md) ·
[m04](m04-ppo-dispatch.md) · [m05](m05-attention-fleet-policy.md) · [m06](m06-haul-road-energy-routing.md) ·
[m07](m07-gpu-granular-physics.md) · [m08](m08-gns-surrogate.md) · [m09](m09-differentiable-dem-calibration.md) ·
[m10](m10-synthetic-data-detector.md) · [m11](m11-fragmentation-segmentation.md) ·
[m12](m12-blast-fragmentation-models.md) · [m13](m13-slope-stability-lem.md) · [m14](m14-slope-forecasting.md) ·
[m15](m15-shallow-water-fno.md) · [m16](m16-dust-dispersion.md) · [m17](m17-comminution-mine-to-mill.md) ·
[m18](m18-pit-optimisation-scheduling.md) · [m19](m19-gaussian-splat-survey.md) · [m20](m20-traffic-ttc.md) ·
[m21](m21-isaac-lab-policies.md) · [m22](m22-cosmos-vlm-tasks.md) · [m23](m23-rtx-sensor-simulation.md)
