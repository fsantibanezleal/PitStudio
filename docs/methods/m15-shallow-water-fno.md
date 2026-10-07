# M15 — GPU shallow water with Bingham rheology, and a Fourier neural operator surrogate

> A depth-averaged finite-volume solver in Warp floods real pit terrain with water or Bingham tailings; a Fourier
> neural operator, built only from matrix multiplications so it runs on WebGPU, learns those fields and replays new
> breach scenarios live in the browser. · Part of: [Methods](README.md) · Related:
> [Tailings theory](../theory/tailings.md) · [Dust theory](../theory/dust.md) · [FNO card](../models/fno-fields.md) ·
> [Case C2](../cases/c2-tailings-breach.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| SOTA + learned | **yes** (FNO) | precompute → live | [C2](../cases/c2-tailings-breach.md) | own Warp solver (Warp 1.17.0, Apache-2.0) in `studio/`; DFT-matmul FNO in PyTorch (`pipeline/`) → ONNX | not yet implemented |

## What and why

Tailings dam failures are rare and catastrophic, and pit flooding is a slower cousin of the same physics: a fluid —
water, or tailings that behave like a Bingham plastic — flows over real terrain. Run-out distance, arrival time and
inundated area are the questions (case C2). A published breach case (Miraí) reports a 3.8 Mm³ release from a 34 m
dam with a peak outflow of 422 m³/s and arrival times of 2.5–4 h downstream [10]: the scale of what a model must
represent.

M15 has two halves:

1. a **GPU shallow-water solver** in Warp [4] on the pit's own DEM, with a Bingham basal-resistance option, validated on
   dam-break benchmarks;
2. a **Fourier neural operator (FNO)** trained on that solver's runs. FNO learns mappings between function spaces and
   reports speed-ups of up to three orders of magnitude over traditional PDE solvers [5]. A surrogate makes
   "move the breach, change the yield stress, see the flood" interactive in a browser. The same architecture is
   trained on the dust concentration fields of [M16](m16-dust-dispersion.md).

PINNs were rejected: a critical assessment shows geotechnical PINNs failing outside the sampled domain at very high
training cost, and recommends classical solvers plus learned surrogates for repeated, interpolative queries [8].

## The algorithm

### Depth-averaged shallow-water equations

With depth $h$ (m), depth-averaged velocity $(u, v)$ (m/s), bed elevation $z_b$ (m) and basal shear stress
$\boldsymbol\tau_b$ (Pa), mass and momentum read [1]†:

$$
\frac{\partial h}{\partial t} + \frac{\partial (hu)}{\partial x} + \frac{\partial (hv)}{\partial y} = 0
$$

$$
\frac{\partial (hu)}{\partial t} + \frac{\partial}{\partial x}\Big(hu^2 + \tfrac12 g h^2\Big) + \frac{\partial (huv)}{\partial y}
= -g h \frac{\partial z_b}{\partial x} - \frac{\tau_{b,x}}{\rho}
$$

$$
\frac{\partial (hv)}{\partial t} + \frac{\partial (huv)}{\partial x} + \frac{\partial}{\partial y}\Big(hv^2 + \tfrac12 g h^2\Big)
= -g h \frac{\partial z_b}{\partial y} - \frac{\tau_{b,y}}{\rho}
$$

$\rho$ is the fluid density (kg/m³). The left-hand side is the conservative form for a horizontal bed [1]; the bed-slope
and basal-stress source terms are the standard Saint-Venant additions†.

**Bingham rheology.** A Bingham plastic does not shear below its yield stress $\tau_0$ and shears at a rate
proportional to the excess stress above it, $\dot\gamma = (\tau - \tau_0)/\mu_B$ for $\tau \ge \tau_0$, with plastic
viscosity $\mu_B$ (Pa·s) [2]. In the depth-averaged solver this becomes a basal stress that resists motion with at
least $\tau_0$ and grows with velocity; where the driving stress $\rho g h \lvert\nabla(z_b + h)\rvert$ falls below
$\tau_0$ the flow stops (the "plug"), which is how tailings deposits stop on slopes. The exact depth-averaged closure
is pinned at specification.

### Numerical scheme

Finite volumes on the DEM grid (a 1 m DEM from the scene pipeline, resampled per case), an HLL or Rusanov interface
flux, wet/dry front handling, and a time step limited by the wave speed (the standard CFL condition):

$$
\Delta t \le C_{\text{CFL}}\,\frac{\Delta x}{\max\big(\lvert\mathbf u\rvert + \sqrt{g h}\big)}
$$

For example, with $\Delta x = 2$ m, $h = 10$ m and $\lvert\mathbf u\rvert = 5$ m/s, the fastest wave is
$5 + \sqrt{98.1} = 14.9$ m/s, so $C_{\text{CFL}} = 0.5$ allows $\Delta t \le 0.067$ s. Warp ships a shallow-water
example in `warp.fem` that serves as a scaffold [3]; the production kernels are PitStudio's own.

```text
step(h, hu, hv, z_b, dt):
    for each cell face (parallel on the GPU):
        UL, UR = reconstruct(left), reconstruct(right)           # wet/dry aware
        F_face = rusanov(UL, UR, g)                               # or HLL
    for each cell:
        U_new = U - dt/dx * (sum of face fluxes) + dt * S_bed(h, z_b) + dt * S_bingham(h, u, v)
        if driving_stress < tau_0: momentum = 0                   # Bingham plug
```

### Fourier neural operator

An FNO lifts the input field to a wider channel space, applies $L$ Fourier layers and projects back [5]:

$$
v_0 = P(a), \qquad
v_{l+1}(x) = \sigma\Big(W v_l(x) + \mathcal F^{-1}\big(R_l \cdot (\mathcal F v_l)\big)(x)\Big), \qquad
u = Q(v_L)
$$

$P$ and $Q$ are pointwise (1×1) layers, $W$ a pointwise linear map, $\sigma$ a non-linearity, $\mathcal F$ the Fourier
transform truncated to the lowest $K$ modes and $R_l$ learned complex weights per mode. **Inputs** $a(x)$: bed
elevation, initial depth (breach geometry and volume) and rheology parameters as constant channels. **Outputs** $u(x)$:
flow depth (and velocity) at the next output time, rolled out autoregressively (horizon fixed in the spec).
**Loss:** relative $L^2$ error, $\lVert \hat u - u\rVert_2 / \lVert u\rVert_2$, as in [5].

![FNO: lift, Fourier layers built from DFT matrix multiplications, projection](../assets/diagrams/fno-architecture.svg)

*Each Fourier layer adds a spectral branch (forward DFT as MatMul, per-mode weights, inverse DFT as MatMul) to a
pointwise branch before the activation; lift and projection are pointwise.*

### DFT as matrix multiplication (why it runs on WebGPU)

`torch.fft.rfft` does not export cleanly to ONNX: an open PyTorch issue reports that the DFT export breaks shape
inference [6], and complex-tensor export has failed historically [7]. Because an FNO keeps only $K$ low modes, the
spectral layer is written with **precomputed real cosine and sine bases**. Along one axis of length $N$:

$$
\operatorname{Re}\hat a_k = \sum_{n=0}^{N-1} a_n \cos\frac{2\pi k n}{N}, \qquad
\operatorname{Im}\hat a_k = -\sum_{n=0}^{N-1} a_n \sin\frac{2\pi k n}{N}, \qquad k = 0, \dots, K-1
$$

the complex weights act as two real products,

$$
\operatorname{Re}\hat b = R^{r}\operatorname{Re}\hat a - R^{i}\operatorname{Im}\hat a, \qquad
\operatorname{Im}\hat b = R^{r}\operatorname{Im}\hat a + R^{i}\operatorname{Re}\hat a
$$

and the truncated inverse for a real signal is

$$
b_n = \frac1N\left[\operatorname{Re}\hat b_0 + 2\sum_{k=1}^{K-1}\Big(\operatorname{Re}\hat b_k\cos\frac{2\pi kn}{N}
- \operatorname{Im}\hat b_k\sin\frac{2\pi kn}{N}\Big)\right]
$$

(for $K \le N/2$; the imaginary part of the zero mode is dropped, exactly as a real inverse FFT does). In 2-D the
transform is applied along both axes, one-sided along the last axis and two-sided along the other. The whole layer is
`MatMul` only — exact for the kept modes, supported by ONNX Runtime's WebGPU and WASM providers and by TensorRT. Parity
against the reference `neuraloperator` implementation (MIT) [9] is checked at export.

### Data and budget

- **Data:** Warp shallow-water runs on crops of the Bingham terrain (public-domain 3DEP DEMs) with randomised breach
  location, volume and Bingham parameters; terrains are split so the test set contains **terrains never seen** in
  training.
- **Budget:** 0.5–2 GPU-hours (estimate); the engineering sketch is a 64² grid, width 32 and 12 modes (about 2–3 M
  parameters, ESTIMATE).

## Baseline and comparison

- **Solver vs benchmarks:** the dam-break collapse of a liquid column (Martin and Moyce) [11] and the 3-D dam break with
  an obstacle (SPHERIC Test 2, Kleefsman et al.) as a front-position reference [12]; exact mass conservation. The
  run-out-versus-release regression of Larrauri and Lall [13] is cited for scale; its coefficients are UNVERIFIED —
  pinned at specification.
- **FNO vs solver:** the Warp solver is ground truth on held-out terrains; relative $L^2$ per field and per rollout
  step, plus arrival time and inundated area errors.
- **Speed:** surrogate ms per step in the browser vs solver time in the studio (reported with hardware and tier).

## Acceptance criterion (pre-registered)

- **FNO: relative $L^2 \le 5\,\%$ on held-out terrains.**
- Solver: the dam-break, conservation and metamorphic tests of the validation rules (for example: higher yield stress
  never increases run-out; zero yield stress and viscosity recover the water case; mirroring the terrain mirrors the
  flood) — thresholds in `specs/000-foundation/thresholds.yaml`.
- Export parity: fp32 rtol 1e-3 / atol 1e-5 against PyTorch (and against `neuraloperator` for the spectral layer).

**Results: Not yet run** — produced in the data-and-models phase. Reported: benchmark plots, relative $L^2$ on
held-out terrains, C2 arrival-time, depth and area maps, and surrogate speed per tier.

## Lane and web delivery

**Precompute → live.** Solver runs are precomputed in the studio and baked as fields (16-bit PNG or float tiles).
The FNO (about 5 MB) runs in ONNX Runtime Web; the lane gate requires ≤ 25 MB and ≤ 50 ms per step (estimates). A WGSL
shallow-water kernel is also among the browser's compute engines for small live demonstrations. A path-traced "hero"
clip of the C2 flood is rendered with USD Composer (Kit); Kit performance data stay local-only. Fallback: baked fields.

## Assumptions and limits

- Depth-averaged flow: no vertical structure, no erosion or entrainment of the bed, no dam-breach mechanics (the breach
  is a prescribed initial condition).
- Bingham parameters for tailings vary widely; results are sensitivity studies, not predictions for any facility.
- The FNO is trained on one terrain family and one grid resolution; zero-shot super-resolution is not claimed.
- **Educational, not regulatory software.** Not a dam-breach study under any tailings standard.

## In PitStudio

- **Cases:** [C2](../cases/c2-tailings-breach.md) (arrival time, depth, area); the FNO also serves the dust fields of
  [C3](../cases/c3-dust.md) via [M16](m16-dust-dispersion.md).
- **Code (planned):** solver in `studio/` (`pitstudio_studio.physics`, stage `st50_physics`); FNO in `pipeline/`
  (`s30_train`, `s50_evaluate`, `s60_export`); live engines in `web/`. Card: [FNO fields](../models/fno-fields.md).
- **Status:** not yet implemented — built test-first in the build phase.

† Standard form; the transcription is checked against the primary source by a worked-example test at specification.

## References

1. *Shallow water equations* — conservative form. https://en.wikipedia.org/wiki/Shallow_water_equations
2. *Bingham plastic* — yield stress and plastic viscosity. https://en.wikipedia.org/wiki/Bingham_plastic
3. NVIDIA Warp `warp.fem` examples (shallow water, Navier–Stokes scaffolds).
   https://github.com/NVIDIA/warp/tree/main/warp/examples/fem
4. NVIDIA Warp 1.17.0 (Apache-2.0). https://pypi.org/project/warp-lang/
5. Li, Z. et al. (2021). *Fourier Neural Operator for Parametric Partial Differential Equations*. ICLR.
   https://arxiv.org/abs/2010.08895
6. PyTorch issue #155997 — rfft→DFT export breaks shape inference. https://github.com/pytorch/pytorch/issues/155997
7. PyTorch issue #126972 — complex tensors in ONNX export. https://github.com/pytorch/pytorch/issues/126972
8. Kumar, K. *A Critical Assessment of PINNs and Operator Learning for Geotechnical Engineering*.
   https://arxiv.org/abs/2512.24365
9. `neuraloperator` 2.0.0 (MIT). https://pypi.org/project/neuraloperator/
10. Silva & Eleutério (2023). Miraí tailings-breach case: 3.8 Mm³, 34 m, 422 m³/s, 2.5–4 h. NHESS.
    https://nhess.copernicus.org/articles/23/3095/2023/
11. Martin, J. C. & Moyce, W. J. (1952). Collapse of liquid columns. Phil. Trans. R. Soc. A.
    https://api.semanticscholar.org/graph/v1/paper/DOI:10.1098/rsta.1952.0006
12. SPHERIC Test 2 — 3-D dam break with obstacle (measurement package); Kleefsman et al. (2005), J. Comput. Phys.
    https://www.spheric-sph.org/tests/test-02 · https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.jcp.2004.12.007
13. Larrauri & Lall (2018). Tailings release volume and run-out regression (update of Rico et al. 2008).
    Environments 5(2):28. https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/environments5020028
