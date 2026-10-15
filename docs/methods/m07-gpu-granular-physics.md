# M07 — GPU granular physics: Warp DEM and Newton implicit MPM

> Broken rock is simulated on the GPU twice: grain by grain with an own soft-sphere DEM in Warp, and as a
> continuum with Newton's implicit material point method; both are checked against granular benchmarks and replayed
> in the browser next to a live WebGPU twin. · Part of: [Methods](README.md) · Related:
> [Bulk flow, DEM and MPM theory](../theory/bulk-flow-dem-mpm.md) · [Warp](../frameworks/warp.md) ·
> [Newton](../frameworks/newton.md) · [DEC-0012](../architecture/decisions/DEC-0012-granular-physics-warp-newton.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| SOTA | no | replay + live WGSL twin | [A3](../cases/a3-loading-payload-variance.md), [D1](../cases/d1-blast-muck-pile.md) | Warp 1.17.0 and Newton 1.6.0 (Apache-2.0), MuJoCo-Warp 3.12.0 for rigid machines | not yet implemented |

## What and why

Muck piles, truck dumping, bucket filling, stockpiles and bench slumps are granular flows. They have no closed form,
and they matter: bucket fill drives payload variance (case A3), and the shape and size distribution of a blasted pile
is the ground truth that PitStudio's fragmentation models are trained on (case D1).

Two complementary GPU methods cover the range:

- **Discrete element method (DEM)** follows every particle and contact. It is the standard tool for repose,
  discharge and transfer flows, and its parameters are calibrated against bulk tests such as the angle of repose
  [6]. PitStudio writes its own soft-sphere DEM in Warp, because the Warp DEM example is a linear spring–dashpot toy
  with no calibrated material model [2].
- **Material point method (MPM)** treats the pile as an elasto-plastic continuum carried by particles. Newton
  (Apache-2.0, a Linux Foundation project built on Warp [5]) ships `SolverImplicitMPM`, an implicit, unconditionally stable MPM for granular and elasto-plastic materials with
  pressure-dependent Drucker–Prager yield, dilatancy and two-way rigid-body coupling [3]. It handles large volumes
  (truck dumps, bench collapse, bucket–soil interaction) at time steps DEM cannot afford.

PhysX particles were rejected: position-based-dynamics particles are an animation-grade model, not a calibrated
constitutive model ([DEC-0012](../architecture/decisions/DEC-0012-granular-physics-warp-newton.md)).

## The algorithm

### Soft-sphere DEM (Warp)

Contacts are found with Warp's hash grid. For two spheres in contact with overlap $\delta_n$, the Hertz–Mindlin
(no-slip) model with Tsuji-type damping gives†:

$$
F_n = \tfrac43 E^\ast \sqrt{R^\ast}\,\delta_n^{3/2}, \qquad
F_n^{d} = -2\sqrt{\tfrac56}\,\beta\sqrt{S_n m^\ast}\, v_n^{\text{rel}}, \qquad
S_n = 2E^\ast\sqrt{R^\ast \delta_n}
$$

$$
F_t = -S_t\,\delta_t, \quad S_t = 8 G^\ast \sqrt{R^\ast\delta_n}, \quad \lvert F_t\rvert \le \mu_s F_n, \qquad
\beta = \frac{\ln e}{\sqrt{\ln^2 e + \pi^2}}
$$

with $1/E^\ast = (1-\nu_1^2)/E_1 + (1-\nu_2^2)/E_2$, $1/R^\ast = 1/R_1 + 1/R_2$, $1/m^\ast = 1/m_1 + 1/m_2$.

| Symbol | Meaning | Unit |
|---|---|---|
| $E_k$, $\nu_k$, $G^\ast$ | Young's modulus, Poisson ratio, effective shear modulus | Pa, –, Pa |
| $R^\ast$, $m^\ast$ | effective radius and mass | m, kg |
| $\delta_n$, $\delta_t$ | normal overlap, accumulated tangential displacement | m |
| $v_n^{\text{rel}}$ | relative normal velocity | m/s |
| $\mu_s$ | sliding friction coefficient | – |
| $e$ | coefficient of restitution | – |

A rolling-resistance torque capped at $\mu_r R^\ast F_n$ stands in for particle shape on spheres (elastic–plastic
spring-dashpot type) [7]. The stable time step scales with the Rayleigh time
$\Delta t_R = \pi R \sqrt{\rho/G}/(0.1631\nu + 0.8766)$†, so real rock stiffness forces tiny steps; the standard
practice is a reduced Young's modulus, documented, with a check that repose and discharge targets still hold [6].
Reference runs use Warp's deterministic atomic modes (`RUN_TO_RUN`) [1] so they are bit-reproducible on one machine.

### Implicit MPM (Newton) and the explicit reference twin

Newton's implicit MPM follows the semi-implicit granular MPM of Daviet and Bertails-Descoubes [3][8]. For the browser
twin, PitStudio also writes an explicit **MLS-MPM** in Warp with Drucker–Prager sand plasticity, following Klár et al.
[9] and Hu et al. [10]; the same algorithm is written in WGSL so parity can be tested.

```text
mls_mpm_step(particles, grid, dt):
    grid.clear()
    for p in particles:                                  # particle -> grid (APIC)
        for i in stencil(p):  w = bspline2(x_i - x_p)
            m_i  += w * m_p
            mv_i += w * m_p * (v_p + C_p @ (x_i - x_p))
            mv_i += dt * w * (-V0_p * 4/dx² * P(F_p) @ F_pᵀ @ (x_i - x_p))   # MLS stress term
    for i in grid: v_i = mv_i / m_i + dt * g;  apply colliders and boundaries
    for p in particles:                                  # grid -> particle
        v_p = Σ w v_i ;  C_p = 4/dx² Σ w v_i (x_i - x_p)ᵀ
        x_p += dt * v_p ;  F_p = (I + dt C_p) @ F_p
        F_p = drucker_prager_return_map(F_p, friction, cohesion)   # sand plasticity
```

Here $F_p$ is the deformation gradient, $C_p$ the affine velocity matrix, $V^0_p$ the initial volume, $P(F)$ the first
Piola–Kirchhoff stress and $dx$ the grid spacing. The Drucker–Prager yield surface (standard form
$\sqrt{J_2} + \alpha I_1 - k \le 0$, with $I_1$ the first stress invariant and $J_2$ the second deviatoric invariant)
is enforced by the return map of [9]. Newton's granular example defaults to a friction coefficient of 0.68 [4]; its
mapping to a repose angle is UNVERIFIED — pinned at specification, which is exactly what [M09](m09-differentiable-dem-calibration.md)
calibrates.

### Physics benchmarks

| Benchmark | Observable | Published reference | Status |
|---|---|---|---|
| Static pile | angle of repose (°) | crushed-stone gravel ≈ 45°, natural gravel with sand 25–30°, granite 35–40°, dry sand 34° [11] | handbook-grade; per-material targets come from lab data |
| Hopper / chute discharge | mass flow rate $Q$ (kg/s) | Beverloo $Q = C\rho_b\sqrt{g}\,(D - kd)^{5/2}$; Hertz–Mindlin DEM reproduces the 5/2 exponent with fitted $C = 0.56$ for $4\times10^5$ spheres, fitted with the particle density, not $\rho_b$ [12]; original law [13] | textbook ranges of $C$ and $k$ are UNVERIFIED — pinned at specification |
| Granular column collapse | normalised run-out $(R_\infty - R_i)/R_i$ | $\propto a$ for low aspect ratio $a = H_i/R_i$, $\propto a^{1/2}$ for high $a$, transition near $a \approx 1.7$ [14]; experiments [15][16] | prefactors UNVERIFIED — pinned at specification |
| Conservation | total mass / volume drift (%) | exact | – |

In the Beverloo law $\rho_b$ is the bulk density (kg/m³), $D$ the orifice diameter (m), $d$ the particle diameter (m)
and $k$ a dimensionless correction. MPM with a $\mu(I)$ rheology has reproduced both Beverloo scaling and the
column-collapse power laws [17], which is the precedent for using MPM at mining scale.

### Scale on a 16 GB GPU (estimates)

- Published, other hardware: GPU MPM with up to ten million particles at under one minute per frame [18].
- Arithmetic, to be measured: MPM stores about 27 floats per particle ($\approx 110$ B), so $10^7$ particles take
  about 1.1 GB plus the grid — memory is not the binding limit, step time is. DEM needs about 180 B per sphere with
  six history contacts, so $5\times10^6$ spheres take about 0.9 GB.
- Planning rate: 1–2 scenarios per hour in the `st50_physics` stage (estimate, recorded by the runner).

The GPU capability probes are written but not yet run on the reference machine.

## Baseline and comparison

- **Against published benchmarks** (table above): every solver must reproduce repose, Beverloo discharge and
  column-collapse scaling before its rollouts are used anywhere.
- **DEM vs MPM:** the same dump or pile scenario in both solvers; differences in run-out and repose are reported, not
  hidden.
- **Warp vs WGSL twin:** compared on **observables, not bits**, because float atomics differ and WGSL needs
  fixed-point scatter (WGSL atomics are 32-bit integers) [19]. Proposed tolerances, ratified at specification: repose
  within ±1.5°, run-out within ±5 %, Beverloo $Q$ within ±5 %, mass drift under 0.5 %.

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)): the
physics benchmarks (Beverloo, repose, column collapse, mass conservation) are locked
as failing tests before the kernels are written, each numerical core has at least three metamorphic relations (for
example: higher friction never lowers the repose angle; a larger orifice never lowers discharge; doubling the
particle count at fixed geometry leaves the repose angle within tolerance), and the browser twin meets the parity
tolerances above. Thresholds live in `specs/000-foundation/thresholds.yaml`.

**Results: Not yet run** — produced in the data-and-models phase. Reported: benchmark tables per solver, A3 bucket-fill
and payload statistics, D1 muck-pile PSDs, and parity results.

## Lane and web delivery

**Replay + live WGSL twin.**

- **Replay:** particle positions are decimated, quantised to 16-bit integers per axis inside the scene bounding box,
  and written as frame shards of at most 10 MB with a manifest (units, bounds, fps, solver version, seed, SHA-256).
  As a size check, $2\times10^4$ particles × 3 × 2 bytes = 120 KB per frame, so 200 frames are about 24 MB — three
  shards (arithmetic). Raw replay of $10^5$ particles is not viable; aggregates (pile height field, discharge
  $Q(t)$) are baked instead.
- **Live:** a WGSL compute twin runs up to $2\times10^4$ particles at a target of at least 30 fps on the WebGPU tier
  (gate estimates, measured when the web is built). An open WebGPU MLS-MPM shows 100–300 k particles are feasible in
  browsers [19].
- **Fallback:** baked aggregates. See [web compute tiers](../web/compute-tiers.md).

## Assumptions and limits

- Spheres with rolling resistance approximate angular rock; MPM approximates the pile as a continuum and cannot
  represent individual boulders.
- DEM calibration is non-unique: several parameter sets reproduce the same repose angle [6]; [M09](m09-differentiable-dem-calibration.md)
  reports the uncertainty.
- Reduced stiffness changes contact durations; dynamic loads (for example impact on a truck tray) are indicative
  only.
- Simulation-grade, educational output, not equipment-design software.

## In PitStudio

- **Cases:** [A3](../cases/a3-loading-payload-variance.md) (bucket fill, payload variance; also feeds
  [M08](m08-gns-surrogate.md) and [M21](m21-isaac-lab-policies.md)), [D1](../cases/d1-blast-muck-pile.md) (muck piles
  with exact PSD for [M11](m11-fragmentation-segmentation.md)).
- **Code (planned):** `studio/` environment (Python 3.14; `warp-lang` 1.17.0, `newton` 1.6.0, `mujoco-warp` 3.12.0 in
  `studio/uv.lock`), package `pitstudio_studio.physics`, stage `st50_physics`; WGSL twin in a `web/` engine;
  benchmark fixtures in the test suite.
- **Status:** not yet implemented — built test-first in the build phase.

† Standard textbook form (the reference documentation shows the formulas only as images); the transcription is
checked by a worked-example test at specification.

## References

1. NVIDIA Warp releases — deterministic atomic modes (1.15), hash grid, `warp.sim` removed in 1.10.
   https://github.com/NVIDIA/warp/releases
2. Warp DEM example — linear spring–dashpot, 65,536 particles, hash grid.
   https://raw.githubusercontent.com/NVIDIA/warp/main/warp/examples/core/example_dem.py
3. Newton `SolverImplicitMPM` — implicit MPM, Drucker–Prager, dilatancy, coupling interface.
   https://newton-physics.github.io/newton/latest/api/_generated/newton.solvers.SolverImplicitMPM.html
4. Newton granular MPM example (defaults: voxel 0.1, friction 0.68).
   https://raw.githubusercontent.com/newton-physics/newton/main/newton/examples/mpm/example_mpm_granular.py
5. Newton repository (Apache-2.0, Linux Foundation project). https://github.com/newton-physics/newton
6. Coetzee, C. J. (2017). Review: Calibration of the discrete element method. Powder Technology 310:104–142.
   https://doi.org/10.1016/j.powtec.2017.01.015
7. Ai, J., Chen, J.-F., Rotter, J. M. & Ooi, J. Y. (2011). Assessment of rolling resistance models in DEM. Powder
   Technology 206:269–282. https://doi.org/10.1016/j.powtec.2010.09.030
8. Daviet, G. & Bertails-Descoubes, F. (2016). A semi-implicit material point method for the continuum simulation of
   granular materials. ACM TOG 35(4) (UNVERIFIED — source unreachable; identified via search index).
   https://dl.acm.org/doi/10.1145/2897824.2925877
9. Klár, G. et al. (2016). Drucker–Prager elastoplasticity for sand animation. ACM TOG 35(4).
   https://api.crossref.org/works/10.1145/2897824.2925906
10. Hu, Y. et al. (2018). A moving least squares material point method with displacement discontinuity and two-way
    rigid body coupling. ACM TOG 37(4). https://doi.org/10.1145/3197517.3201293
11. *Angle of repose* (table citing Glover, *Pocket Ref*). https://en.wikipedia.org/wiki/Angle_of_repose
12. DEM validation of the Beverloo law (Hertz–Mindlin, $4\times10^5$ spheres, $C = 0.56$).
    https://arxiv.org/html/2512.03698v1
13. Beverloo, Leniger & van de Velde (1961). Chemical Engineering Science.
    https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/0009-2509(61)85030-6
14. Deposition morphology of granular column collapses (run-out scaling, transition near 1.7).
    https://arxiv.org/html/2002.02146v3
15. Lube, G. et al. (2004). Journal of Fluid Mechanics 508:175–199. https://api.crossref.org/works/10.1017/S0022112004009036
16. Lajeunesse, E. et al. (2004). Physics of Fluids 16:2371–2381. https://api.crossref.org/works/10.1063/1.1736611
17. Dunatunga, S. & Kamrin, K. — MPM with $\mu(I)$ rheology reproducing Beverloo and column-collapse scaling. Journal of
    Fluid Mechanics. https://api.semanticscholar.org/graph/v1/paper/DOI:10.1017/jfm.2015.383
18. Gao, M. et al. (2018). GPU MPM — up to ten million particles at under one minute per frame.
    https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/3272127.3275044
19. WebGPU-Ocean — browser MLS-MPM (~100 k particles on integrated GPUs, ~300 k on discrete GPUs), fixed-point
    atomics, MIT. https://github.com/matsuoka-601/WebGPU-Ocean
