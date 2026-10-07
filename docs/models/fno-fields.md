# FNO-2D field surrogate (tailings and dust)

> A Fourier Neural Operator, built from plain matrix multiplications, that maps terrain and initial conditions to
> tailings-flow and dust fields fast enough to drive interactive what-ifs in the browser. · Part of:
> [Models](README.md) · Related: [M15 Shallow water + FNO](../methods/m15-shallow-water-fno.md) ·
> [Case C2](../cases/c2-tailings-breach.md) · [Case C3](../cases/c3-dust.md) · [Tailings theory](../theory/tailings.md)

## What and why

Cases C2 (tailings breach run-out) and C3 (haul-road dust) need full 2-D fields — flow depth, arrival time,
concentration — for many scenarios. PitStudio's own Warp shallow-water solver (with Bingham rheology) and dust model
produce them on the GPU, offline. A Fourier Neural Operator (FNO) learns the map from input fields to output fields; its
authors report it "up to three orders of magnitude faster" than traditional PDE solvers [1]. PitStudio trains a small
2-D FNO on its own solver runs so a visitor can move a breach point or a wind direction and see a field immediately,
with the solver's baked run shown for comparison.

## Model card

### Intended use

- Live surrogate of the studio's shallow-water (tailings) and dust fields on terrains and parameters inside the
  training envelope.
- Batched scenario sweeps in the studio (Monte-Carlo envelopes of arrival time and depth), which the web replays.

### Out of scope

- Dam-safety or regulatory run-out studies; the solver and the surrogate are educational, with stated validity ranges.
- Terrains, rheologies or grid resolutions outside the training distribution.
- Replacing the solver: the Warp solver stays the reference and the source of every acceptance number.

### Architecture

An FNO lifts the input channels to a width-$d$ latent with a pointwise map $P$, applies $L$ Fourier layers, and
projects back with $Q$ [1]:

$$
v_{l+1}(x)=\sigma\big(W_l\,v_l(x)+(\mathcal K_l v_l)(x)\big),\qquad
(\mathcal K_l v)(x)=\mathcal F^{-1}\big(R_l\cdot(\mathcal F v)\big)(x)
$$

$v_l(x)\in\mathbb R^{d}$ is the latent at grid point $x$, $W_l$ a pointwise linear map, $\sigma$ a nonlinearity,
$\mathcal F$ the 2-D Fourier transform, and $R_l$ a learned complex weight per **kept** mode: only the lowest $m$ modes
per axis are kept, which is what makes the operator resolution-independent and cheap [1]. Planned size (estimate): a
64 × 64 grid, width $d = 32$, $m = 12$ modes, about 2–3 M parameters.

**Spectral layer as truncated-DFT matrix products.** Exporting `torch.fft.rfft` through the dynamo exporter hits an open
bug (a `DFT` node with `dft_length=1` breaks shape inference) [2], and complex tensors have a history of failed
exports [3]. Because only $m$ modes survive, the transform is written as real matrix products with precomputed bases.
For an $n\times n$ field $V$ and kept frequencies $k_1\in\{0,\dots,m-1\}\cup\{n-m,\dots,n-1\}$, $k_2\in\{0,\dots,m-1\}$:

$$
(C_a)_{k,x}=\cos\frac{2\pi kx}{n},\quad (S_a)_{k,x}=\sin\frac{2\pi kx}{n},\qquad
\hat V=(C_1-iS_1)\,V\,(C_2-iS_2)^{\mathsf T}
$$

The real and imaginary parts are four real `MatMul`s; the per-mode channel mixing by $R_l$ is a batched `MatMul`; the
inverse uses the transposed bases with weight 1 for $k_2=0$ and 2 for $k_2>0$ (Hermitian symmetry of a real field,
$m<n/2$) and a $1/n^2$ factor. The result equals the FFT version at the kept modes up to floating-point rounding, which
the build phase verifies against `neuraloperator` 2.0.0 (MIT) [4]. Worked cost at $n = 64$, $m = 12$: about 0.27
million multiply–adds per channel per forward transform ($2\cdot 24\cdot 64\cdot 64 + 4\cdot 24\cdot 64\cdot 12$) —
small enough that the matmul form costs nothing noticeable on WebGPU.

### Training data

Runs of PitStudio's Warp shallow-water solver on terrain patches derived from USGS 3DEP Bingham Canyon (public domain)
with breach location, volume and Bingham parameters varied, and dust fields from the studio's dust model on the same
terrains; the solver itself is validated on dam-break benchmarks in the physics feature spec. All runs are ours,
CC-BY-4.0. **Held-out terrains**: splits are grouped by terrain patch, so no test terrain is seen in training. The exact
input/output pairing (direct map to a target time or next-step rollout) is fixed in the surrogates spec.

### Budget (estimate)

**0.5–2 GPU-h**, about 2–4 GB VRAM. Measured by the runner probe `studio bench` before any long run; the GPU probes are
written but not yet run on the reference machine.

### Export and web lane

- **Opset 19**: the graph is `MatMul`-only, so the opset does not change web coverage, and 19 keeps an FP8 Q/DQ variant
  possible in the TensorRT lane [5]. `Einsum` is avoided because its WebGPU registration in the ORT 1.30.0 tag was not
  confirmed (UNVERIFIED) [6]. IR version **pinned to 10**; dynamo export with `verify=True`; onnxslim.
- Parity: ONNX Runtime CPU fp32 vs PyTorch fp32 on ≥ 200 golden fields (rtol 1e-3 / atol 1e-5 / max abs 1e-4); fp16
  accepted only if the relative L2 error moves by ≤ 1 pp.
- Size: about 10 MB fp32 / **~5 MB fp16 → LIVE** (ORT-web WebGPU, WASM fallback); gate ≤ 25 MB and ≤ 50 ms per
  evaluation (estimate, measured in the web phase).
- **TensorRT relevance — low risk, modest gain** (2–4× over eager, estimate). TensorRT's native `DFT` runs on a cuFFT
  plugin with restrictions (transform axis −2, power-of-two lengths for FP16/BF16) [7]; the matmul design keeps the
  same graph as the web. The gain shortens studio sweeps; the browser is unaffected. Per-engine parity applies
  ([DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)).

### Pre-registered acceptance criteria

- **Relative L2 ≤ 5 % on held-out terrains**:

$$
e_{L2}=\frac{\lVert \hat u-u\rVert_2}{\lVert u\rVert_2}\le 0.05
$$

  where $u$ is the solver field and $\hat u$ the FNO field on the same grid (–). Whether the bound applies per terrain
  or to the mean is fixed in the surrogates spec; both are reported.
- Any "better than" claim only by the decision rule
  ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

### Evaluation protocol

- Per held-out terrain: $e_{L2}$ of each output field, plus the case KPIs derived from it — arrival time, maximum depth
  and inundated area for C2; receptor concentration for C3 — against the solver.
- Timing: solver vs surrogate per scenario on the studio GPU, and surrogate in the browser.

### Licence of weights

Own implementation (Apache-2.0); inputs are public-domain terrain and our CC-BY-4.0 solver runs → weights
**Apache-2.0 + attribution**. `neuraloperator` (MIT) is a parity reference only.

## Assumptions and limits

- The surrogate inherits every limit of the solver (shallow-water assumptions, Bingham rheology, grid resolution) and
  adds its own approximation error.
- Truncation to $m$ modes smooths sharp fronts; arrival-time error at the front is reported separately for that reason.
- Valid only inside the trained ranges of terrain, breach volume and rheology; outside them results are extrapolation.
- Simulation-grade twin, not a live digital twin; not dam-safety software.

## In PitStudio

- **Cases:** [C2](../cases/c2-tailings-breach.md) (tailings breach run-out), [C3](../cases/c3-dust.md) (dust fields).
- **Methods:** [M15](../methods/m15-shallow-water-fno.md), [M16](../methods/m16-dust-dispersion.md).
- **Env and stages:** `studio/` `st50_physics` (Warp shallow water, dust) → `pipeline/` `s10_preprocess` →
  `s30_train` → `s40_infer` → `s50_evaluate` → `s60_export` → `pipeline/accel/` `s62_accel` / `s64_bench`.
- **Artefacts:** `models/onnx/` (fp16, live), `models/cards/`; web lane LIVE with baked solver fields as the T0
  fallback. Recipes: [training recipes](training-recipes.md).

## Results

**Not yet trained** — produced in the data-and-models phase. Will be reported: relative L2 per held-out terrain and
field (acceptance ≤ 5 %), KPI errors (arrival time, depth, area, receptor concentration), solver vs surrogate timing, ONNX/fp16 parity, in-browser parity, and TensorRT per-engine parity (rejected engines listed).

## References

1. Li, Z., Kovachki, N., Azizzadenesheli, K., Liu, B., Bhattacharya, K., Stuart, A., Anandkumar, A. (2020). *Fourier
   Neural Operator for Parametric Partial Differential Equations*. ICLR 2021. https://arxiv.org/abs/2010.08895
2. PyTorch issue #155997 (`rfft` → `DFT` `dft_length` export bug; fix pending in onnxscript #2991).
   https://github.com/pytorch/pytorch/issues/155997
3. PyTorch issue #126972 (complex tensors in ONNX export). https://github.com/pytorch/pytorch/issues/126972
4. `neuraloperator` 2.0.0 (MIT, 2025-10-22). https://pypi.org/pypi/neuraloperator/json
5. NVIDIA Model Optimizer, Windows examples (FP8 Q/DQ needs opset ≥ 19).
   https://raw.githubusercontent.com/NVIDIA/Model-Optimizer/main/examples/windows/README.md
6. ONNX Runtime WebGPU kernel registries, tag v1.30.0 and `main`.
   https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/core/providers/webgpu/webgpu_execution_provider.cc
   and https://raw.githubusercontent.com/microsoft/onnxruntime/main/onnxruntime/core/providers/webgpu/webgpu_execution_provider.cc
7. onnx-tensorrt operator support (TensorRT 11.3; `DFT`, `Einsum`, `MatMul`).
   https://raw.githubusercontent.com/onnx/onnx-tensorrt/main/docs/operators.md
