# Tailings breach run-out and pit flooding

> Depth-averaged shallow-water equations with a viscoplastic (Bingham) bed stress, verified on dam-break solutions and
> read against empirical run-out regressions, give arrival-time and depth maps for a tailings breach or a flooding
> pit. · Part of: [Theory](README.md) · Related: [M15 shallow water + FNO](../methods/m15-shallow-water-fno.md) ·
> [C2 tailings breach](../cases/c2-tailings-breach.md) · [Warp](../frameworks/warp.md) ·
> [FNO field surrogates](../models/fno-fields.md)

## What and why

A tailings storage facility (TSF) holds the fine, water-saturated residue of mineral processing behind an engineered
dam. TSF failures are rare but extreme. The 2019 Brumadinho failure released nearly 10 million m³ and cost over 270
lives; upstream-raised dams are "clearly overrepresented in the accident statistics" [1][2]. The industry answer is the
Global Industry Standard on Tailings Management (GISTM), launched on 5 August 2020 with 15 principles and 77 auditable
requirements [3]. A public inventory, the Global Tailings Portal, lists 1,805 TSFs at 692 mine sites [12].

The questions a breach study answers are geometric and temporal: **how far** the flow travels, **how fast** the front
arrives at a point, and **how deep** it gets. Practice answers them with depth-averaged non-Newtonian solvers. Two
published examples set the scale:

| Study | Released volume (m³) | Dam height (m) | Peak breach flow (m³/s) | Arrival at town (h) | Source |
|---|---|---|---|---|---|
| Miraí 2007 (Brazil), HEC-RAS + HEC-LifeSim reconstruction | 3.8 × 10⁶ | 34 | 422 | ≈ 2.5–4 | [4] |

The same reconstruction counts about 1,033 people exposed and no deaths [4]. A 2026 metamodel study on HEC-RAS 6.6
found that **breach parameters dominate the result near the dam, while the yield stress dominates downstream** [5]. That
finding drives the structure of this page: the breach is an input hydrograph, and the rheology is the physics that
decides the run-out.

A flooding pit (rainfall or groundwater filling the pit floor) is the same mathematics with different sources: water
instead of tailings, rain and pumps instead of a breach. PitStudio keeps it as a variant of the tailings case, because
no verified industry impact figures were found for it.

![Breach hydrograph feeds a shallow-water solver on the terrain grid, which produces arrival-time and depth maps](../assets/diagrams/tailings-shallow-water.svg)

*Breach → hydrograph → shallow-water solver on the DEM → arrival-time and depth maps → FNO surrogate.*

## Governing equations

The classical results in this section (the shallow-water system, the CFL condition, the Ritter and Stoker dam-break
solutions and the Bingham sheet-flow relation) are standard textbook forms. Their primary texts are **not yet among the
project's verified sources**; each is tagged "citation UNVERIFIED — pinned at specification", and the specification
phase fixes it to its primary text with a worked example before it becomes a test oracle.

### Shallow-water equations (de Saint-Venant system)

Integrating the mass and momentum balances over the flow depth, under hydrostatic pressure and a long-wave assumption
(depth ≪ horizontal length), gives the 2-D shallow-water equations in conservative form (citation UNVERIFIED — pinned
at specification; the implementation scaffold is the Warp `warp.fem` shallow-water example [6]):

$$
\frac{\partial h}{\partial t} + \frac{\partial (hu)}{\partial x} + \frac{\partial (hv)}{\partial y} = S_h
$$

$$
\frac{\partial (hu)}{\partial t} + \frac{\partial}{\partial x}\Big(hu^2 + \tfrac{1}{2} g h^2\Big) + \frac{\partial (huv)}{\partial y}
= -g h \frac{\partial z_b}{\partial x} - \frac{\tau_{b,x}}{\rho}
$$

$$
\frac{\partial (hv)}{\partial t} + \frac{\partial (huv)}{\partial x} + \frac{\partial}{\partial y}\Big(hv^2 + \tfrac{1}{2} g h^2\Big)
= -g h \frac{\partial z_b}{\partial y} - \frac{\tau_{b,y}}{\rho}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $h(x,y,t)$ | flow depth | m |
| $u, v$ | depth-averaged velocity components | m/s |
| $z_b(x,y)$ | bed elevation, from the terrain DEM | m |
| $g$ | gravitational acceleration, 9.81 | m/s² |
| $\rho$ | bulk density of the flowing mixture | kg/m³ |
| $\tau_{b,x}, \tau_{b,y}$ | bed shear stress components (the rheology enters here) | Pa |
| $S_h$ | volumetric source per unit area: breach inflow, rain; negative for pumps | m/s |

The system is hyperbolic. Small disturbances travel at $u \pm c$ with the gravity-wave celerity $c = \sqrt{g h}$ (m/s),
and the Froude number $\mathrm{Fr} = |\mathbf{u}|/\sqrt{gh}$ separates sub-critical ($\mathrm{Fr} < 1$) from
super-critical flow.

### Finite-volume discretisation

PitStudio's solver is a finite-volume scheme on the terrain height field with an HLL or Rusanov interface flux, written
as Warp kernels [6]. With the conserved vector $\mathbf{U} = (h, hu, hv)$ and cell size $\Delta x$ (m), the Rusanov
(local Lax–Friedrichs) flux between a left state L and a right state R is (citation UNVERIFIED — pinned at
specification):

$$
\mathbf{F}^{*} = \tfrac{1}{2}\big(\mathbf{F}(\mathbf{U}_L) + \mathbf{F}(\mathbf{U}_R)\big)
- \tfrac{1}{2}\, a_{\max}\, (\mathbf{U}_R - \mathbf{U}_L),
\qquad a_{\max} = \max\big(|u_L| + c_L,\; |u_R| + c_R\big)
$$

The explicit time step obeys a CFL condition (citation UNVERIFIED — pinned at specification):

$$
\Delta t \le C_{\mathrm{CFL}}\, \frac{\Delta x}{\max_{\text{cells}}\big(|\mathbf{u}| + \sqrt{g h}\big)}, \qquad 0 < C_{\mathrm{CFL}} \le 1
$$

Three numerical properties matter for tailings and pits:

1. **Positivity and wet/dry fronts.** A breach front advances over dry ground ($h = 0$). The scheme must keep
   $h \ge 0$, and cells below a small depth are treated as dry.
2. **Still water on uneven terrain.** A pit lake at rest must stay at rest. A scheme whose flux and bed-slope source do
   not balance produces spurious currents on a still pond; the specification decides how the solver meets this and
   adds a test for it.
3. **Mass conservation.** Total volume changes only through $S_h$. The physics test suite checks the drift.

**Worked example (CFL).** On the 1 m Bingham DEM ($\Delta x = 1$ m), a front 5 m deep moving at 10 m/s has
$|u| + \sqrt{gh} = 10 + 7.0 = 17.0$ m/s, so $\Delta t \le 0.059$ s at $C_{\mathrm{CFL}} = 1$. A 2-hour event then needs
at least about 1.2 × 10⁵ steps; coarsening to 4 m cells cuts the count by 4 and the cell count by 16. (Illustrative
inputs, not sourced values.)

### Bed stress: Bingham viscoplastic rheology

Water obeys a turbulent friction law. Concentrated tailings behave as a **viscoplastic** material: they do not flow
until the shear stress exceeds a yield stress, and above it the stress grows with the shear rate. The Bingham model is
the simplest such law (citation UNVERIFIED — pinned at specification):

$$
\tau = \tau_y + \mu_B\, \dot{\gamma} \quad \text{for } |\tau| > \tau_y, \qquad \dot\gamma = 0 \text{ otherwise}
$$

with yield stress $\tau_y$ (Pa), plastic viscosity $\mu_B$ (Pa·s) and shear rate $\dot\gamma$ (1/s).

For steady laminar sheet flow of a Bingham layer of depth $h$, the mean velocity $U$ (m/s) and the bed stress $\tau_b$
satisfy the Buckingham–Reiner relation (citation UNVERIFIED — pinned at specification):

$$
U = \frac{\tau_b\, h}{3 \mu_B}\left[1 - \frac{3}{2}\frac{\tau_y}{\tau_b} + \frac{1}{2}\left(\frac{\tau_y}{\tau_b}\right)^3\right],
\qquad \tau_b \ge \tau_y
$$

Two checks follow directly:

- With $\tau_y = 0$ it reduces to the Newtonian laminar law $\tau_b = 3\mu_B U / h$.
- Expanding to first order in $\tau_y/\tau_b$ gives the explicit approximation used by many depth-averaged codes:

$$
\tau_b \approx \tfrac{3}{2}\,\tau_y + \frac{3 \mu_B U}{h}
$$

The solver applies $\tau_b$ opposite to the velocity, $\boldsymbol{\tau}_b = \tau_b\, \mathbf{u}/|\mathbf{u}|$, and
treats a cell as **arrested** when the driving stress cannot exceed the yield stress. On a uniform slope of angle
$\theta$ the arrest depth is

$$
h_{\mathrm{stop}} = \frac{\tau_y}{\rho\, g \sin\theta}
$$

This is why a Bingham flow stops with a finite deposit, while a water flood keeps spreading: the yield stress sets the
run-out. It is also why the downstream result is so sensitive to $\tau_y$ [5].

A Voellmy-type law (Coulomb friction plus a velocity-squared term) is the alternative for coarse or granular flows
(citation UNVERIFIED — pinned at specification):

$$
\tau_b = \mu\, \rho g h \cos\theta + \frac{\rho g\, U^2}{\xi}
$$

with friction coefficient $\mu$ (–) and turbulence coefficient $\xi$ (m/s²).

**Parameter values.** No tailings values of $\tau_y$, $\mu_B$, $\mu$ or $\xi$ are verified in the project's sources
yet. They are inputs of the case recipe, every published value enters the knowledge tables with its citation, and the
UI flags them UNVERIFIED until the specification pins them.

## Breach hydrograph

PitStudio prescribes the breach outflow $Q(t)$ (m³/s) as a boundary source; it does not simulate breach erosion. A
triangular hydrograph with released volume $V$ (m³) and peak $Q_p$ (m³/s) has a base duration

$$
T = \frac{2V}{Q_p}
$$

**Worked example (Miraí, [4]).** With $V = 3.8 \times 10^6$ m³ and $Q_p = 422$ m³/s, a triangular hydrograph lasts
$T = 2 \times 3.8 \times 10^6 / 422 \approx 1.8 \times 10^4$ s ≈ 5.0 h. The triangular shape is an assumption used here
only to show the arithmetic; the published reconstruction used its own breach model [4].

## Dam-break benchmarks (code verification)

### Ritter: dam break on a dry bed

An infinitely long reservoir of depth $h_0$ (m) at $x < 0$ is released at $t = 0$ onto a dry, flat, frictionless bed.
With $c_0 = \sqrt{g h_0}$ the self-similar solution is (Ritter 1892; citation UNVERIFIED — pinned at specification):

$$
h(x,t) =
\begin{cases}
h_0, & x \le -c_0 t \\
\dfrac{1}{9g}\left(2c_0 - \dfrac{x}{t}\right)^2, & -c_0 t < x < 2c_0 t \\
0, & x \ge 2 c_0 t
\end{cases}
\qquad
u(x,t) = \frac{2}{3}\left(c_0 + \frac{x}{t}\right) \text{ in the fan}
$$

At the dam site ($x = 0$) the depth is $4h_0/9$ and the velocity $2c_0/3$, so the unit discharge is

$$
q_0 = \frac{8}{27}\sqrt{g}\; h_0^{3/2} \quad (\mathrm{m^2/s})
$$

**Worked example.** For $h_0 = 34$ m (the Miraí dam height [4]): $c_0 = 18.3$ m/s, the frictionless front speed is
$2c_0 = 36.5$ m/s, the depth at the dam is 15.1 m and $q_0 \approx 184$ m²/s. Real tailings fronts are far slower
because friction, rheology and the finite breach dominate; the Ritter solution is used **only** to verify the solver
(front position, depth profile, convergence under grid refinement), never as a run-out estimate.

### Stoker: dam break onto a wet bed

With still water of depth $h_1 < h_0$ downstream, the solution has a left-moving rarefaction, a constant middle state
$(h_2, u_2)$ and a right-moving bore of speed $s$ (Stoker 1957; citation UNVERIFIED — pinned at specification). The
middle state solves three conditions:

$$
u_2 + 2\sqrt{g h_2} = 2\sqrt{g h_0} \quad \text{(Riemann invariant across the rarefaction)}
$$

$$
\frac{h_2}{h_1} = \frac{1}{2}\left(\sqrt{1 + \frac{8 s^2}{g h_1}} - 1\right),
\qquad
u_2 = s\left(1 - \frac{h_1}{h_2}\right) \quad \text{(momentum and mass across the bore)}
$$

Eliminating $h_2$ and $u_2$ leaves one nonlinear equation in $s$, solved to machine precision by bisection. The Stoker
case tests the shock-capturing part of the scheme; the Ritter case tests the wet/dry front.

### Laboratory data

- **Martin & Moyce (1952)** measured the collapse of liquid columns [7]: front position against time.
- **SPHERIC Test 2** is a 3-D dam break with an obstacle, with MARIN measurements in a 2.5 MB data package [8], described
  by Kleefsman et al. (2005) [9].

The front-position series are in the cited sources and were not yet extracted; the specification transcribes them
before they become tolerances.

## Empirical run-out relations

Field-scale tailings run-out is commonly checked against regressions fitted to past failures. Rico et al. (2008)
related the maximum run-out distance $D_{\max}$ to the dam and release geometry. Concha Larrauri & Lall (2018) updated
it with a regression of $D_{\max}$ on a predictor based on the released volume's potential energy [10]. Both have the
power-law form

$$
D_{\max} = a\, X^{b}
$$

with $X$ an energy- or volume-based predictor. **The coefficients $a$, $b$ and the exact definition of $X$ are
UNVERIFIED (publisher page unreachable) — pinned at specification.** Until then the C2 page reports simulated run-out
without placing it on the regression line. The Rico et al. (2008) primary text is not among the verified sources; it is
cited here through [10].

How the two kinds of estimate relate:

| Estimate | What it uses | What it gives | Weakness |
|---|---|---|---|
| Empirical regression [10] | Released volume, dam height | One distance, with scatter | No terrain, no timing |
| Depth-averaged solver (this page) | Terrain, hydrograph, rheology | Arrival time, depth and extent per cell | Rheology parameters uncertain [5] |

## Pit flooding

The pit variant runs the same solver on the pit DEM with $S_h$ = rainfall intensity (m/s) on the catchment minus
pump sinks. Two derived quantities explain most results:

- **Stage–volume curve.** The volume stored below water level $z$ is
  $V(z) = \sum_{\text{cells}} \max(0, z - z_b)\, \Delta A$, with cell area $\Delta A$ (m²). It comes straight from the
  DEM.
- **Dewatering time.** With constant inflow $Q_{\mathrm{in}}$ and pump capacity $Q_{\mathrm{pump}} > Q_{\mathrm{in}}$
  (m³/s), a stored volume $V$ is removed in $t = V / (Q_{\mathrm{pump}} - Q_{\mathrm{in}})$.

**Worked example (illustrative inputs).** A pit-floor pond of 2 × 10⁵ m³ with 0.5 m³/s of inflow and 1.5 m³/s of
pumping takes $2 \times 10^5 / 1.0 = 2 \times 10^5$ s ≈ 2.3 days to dewater.

## Outputs: arrival time, depth, area

For a depth threshold $h_{\mathrm{thr}}$ (m) set in the recipe, the solver output $h(\mathbf{x}, t)$ reduces to three
maps and one number:

$$
t_{\mathrm{arr}}(\mathbf{x}) = \min\{\, t : h(\mathbf{x}, t) > h_{\mathrm{thr}} \,\}, \qquad
h_{\max}(\mathbf{x}) = \max_t h(\mathbf{x}, t), \qquad
v_{\max}(\mathbf{x}) = \max_t |\mathbf{u}(\mathbf{x}, t)|
$$

$$
A_{\mathrm{inund}} = \big|\{\, \mathbf{x} : h_{\max}(\mathbf{x}) > h_{\mathrm{thr}} \,\}\big| \quad (\mathrm{m^2})
$$

These are the C2 KPIs: arrival time, depth and area.

## Learned surrogate (FNO)

A full solver run takes minutes on the GPU; the web needs an answer in milliseconds. A Fourier neural operator (FNO)
learns the map from inputs (terrain patch, breach parameters, rheology) to output fields ($h_{\max}$, $t_{\mathrm{arr}}$).
Each FNO layer is [11]:

$$
v_{l+1}(\mathbf{x}) = \sigma\Big( W v_l(\mathbf{x}) + \mathcal{F}^{-1}\big\{ R_\phi \cdot (\mathcal{F} v_l) \big\} (\mathbf{x}) \Big)
$$

with a pointwise linear map $W$, learnable spectral weights $R_\phi$ applied to the lowest $k_{\max}$ Fourier modes,
and a nonlinearity $\sigma$. Li et al. report speed-ups of up to three orders of magnitude over classical solvers [11].
PitStudio implements the truncated transform as DFT matrix multiplications, so the spectral layers export as `MatMul`
only; the export checks the graph against an operator whitelist that excludes `DFT`, `Einsum` and complex tensors. Accuracy is the relative L2 error on held-out terrains:

$$
\varepsilon_{L2} = \frac{\lVert \hat h_{\max} - h_{\max} \rVert_2}{\lVert h_{\max} \rVert_2}
$$

Arrival-time fields are discontinuous at the edge of the inundated area, which is hard for a low-mode spectral model;
the error is therefore reported per field, not pooled.

## Assumptions and limits

- **Educational, not design or regulatory software.** C2 is not a dam-safety assessment, not a GISTM consequence
  classification and not an emergency plan. The facility is hypothetical, placed on real terrain.
- **Simulation-grade twin, not a live digital twin.** No piezometer, survey or telemetry feed drives the model.
- **Validity range.** Depth-averaged and hydrostatic: valid where depth ≪ horizontal extent and bed slopes are moderate.
  Not valid for the near-field collapse of the dam body, for vertical accelerations or for steep pit walls where flow
  becomes a free fall.
- **Single-phase rheology.** One Bingham (or Voellmy) mixture: no settling, consolidation, entrainment of bed material
  or change of solids concentration along the path.
- **Prescribed breach.** The hydrograph is an input; breach formation, liquefaction triggers and erosion are not
  modelled. The metamodel study shows these dominate near the dam [5].
- **Unverified parameters.** Rheology values and the run-out regression coefficients stay UNVERIFIED until pinned.
- **Terrain resolution.** Results are tied to the 1 m DEM and to the chosen cell size; the grid study is part of the
  verification.

## In PitStudio

| Item | Where | Status |
|---|---|---|
| Case | [C2 tailings breach run-out & pit flooding](../cases/c2-tailings-breach.md): KPIs arrival time, depth, area | Not yet run |
| Method | [M15 GPU shallow water (Bingham) + FNO surrogate](../methods/m15-shallow-water-fno.md) | Specified in the plan |
| Terrain | `st10_terrain` from the USGS 3DEP Bingham Canyon DEM ([dataset card](../data-contract/dataset-cards/bingham-3dep.md)) | Data fetched by `s00_download` |
| Solver | Own Warp kernels in the `studio/` environment (Python 3.14; `warp-lang` 1.17.0 in `studio/uv.lock`), stage `st50_physics`; fields written as Zarr | Build phase |
| Verification | Dam break (Ritter, Stoker) and mass conservation in the physics test suite | Build phase |
| Surrogate | FNO-2D trained in `pipeline/` (`s30_train`), exported by `s60_export` to ONNX (~5 MB), live in the browser through ONNX Runtime Web; budget 0.5–2 GPU-h | Data-and-models phase |
| Live twin | WGSL shallow-water kernel in the web app with a parity test against the Warp reference | Build phase |
| Media | Path-traced hero clip of the breach (Composer, `st58_kit_capture`), encoded by `st56_encode` | Data-and-models phase |

**Results: Not yet run — produced in the data-and-models phase.** What will be reported:

- Ritter and Stoker verification errors under grid refinement, and the total-volume drift of each run.
- Arrival-time, maximum-depth and inundated-area maps for the C2 breach scenarios and the pit-flooding variant.
- FNO accuracy. Pre-registered acceptance criterion from the plan: **relative L2 ≤ 5 % on held-out terrains**.

## References

1. NGI / ScienceNorway (summary of Piciullo et al. 2022), "This determines how dangerous a dam failure can be". URL:
   https://partner.sciencenorway.no/geology-natural-sciences-ngi/this-determines-how-dangerous-a-dam-failure-can-be/2568663
2. Piciullo et al. (2022). A new look at the statistics of tailings dam failures. *Engineering Geology* 303.
   DOI: 10.1016/j.enggeo.2022.106657
3. ICMM. Global Industry Standard on Tailings Management (launched 2020-08-05). URL:
   https://www.icmm.com/en-gb/our-principles/tailings/global-industry-standard-on-tailings-management
4. Silva, Eleutério (2023). Reconstruction of the 2007 Miraí tailings-dam breach with HEC-RAS and HEC-LifeSim
   (descriptive title). *Natural Hazards and Earth System Sciences* 23, 3095. DOI: 10.5194/nhess-23-3095-2023
5. Sáo, Maciel, Eleutério (2026). Metamodel-based … sensitivity analysis of tailings dam-breach flows. arXiv:2607.19296.
   URL: https://arxiv.org/abs/2607.19296
6. NVIDIA. Warp `warp.fem` examples (shallow water, APIC fluid, Navier–Stokes). URL:
   https://github.com/NVIDIA/warp/tree/main/warp/examples/fem
7. Martin, Moyce (1952). Part IV. An experimental study of the collapse of liquid columns on a rigid
   horizontal plane. *Phil. Trans. R. Soc. A* 244(882):312–324. DOI: 10.1098/rsta.1952.0006
8. SPHERIC. Test 2: 3-D dam break with obstacle (data package). URL: https://www.spheric-sph.org/tests/test-02
9. Kleefsman, Fekken, Veldman, Iwanowski, Buchner (2005). A Volume-of-Fluid based
   simulation method for wave impact problems. *J. Comput. Phys.* 206(1):363–393. DOI: 10.1016/j.jcp.2004.12.007
10. Concha Larrauri, Lall (2018). Updated statistical model of tailings release volume and run-out distance
    (descriptive title; regression coefficients UNVERIFIED, publisher page unreachable). *Environments* 5(2):28.
    DOI: 10.3390/environments5020028
11. Li et al. (2021). Fourier Neural Operator for Parametric Partial Differential Equations. ICLR 2021.
    URL: https://arxiv.org/abs/2010.08895
12. Global Tailings Portal (inventory of 1,805 TSFs at 692 mine sites; data licence not stated on the page). URL:
    https://tailing.grida.no/

Classical sources cited by name only, **not yet verified** against their primary texts (pinned at specification): de
Saint-Venant (1871) for the shallow-water system; Ritter (1892) and Stoker (1957) for the dam-break solutions; the
Bingham model and the Buckingham–Reiner sheet-flow relation; the Rusanov flux and the CFL condition; the Voellmy law;
Rico et al. (2008) for the run-out regression.
