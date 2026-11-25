# Bulk flow, DEM and MPM

> How broken rock flows: discrete-element contact physics, continuum granular models in the material point method,
> the angle of repose, hopper discharge, conveyor capacity and power, and blending variance. · Part of:
> [Theory](README.md) · Related: [Loading and terramechanics](loading-and-terramechanics.md),
> [M7 GPU granular physics](../methods/m07-gpu-granular-physics.md), [M8 GNS surrogate](../methods/m08-gns-surrogate.md),
> [Warp](../frameworks/warp.md)

## What and why

Every tonne in a mine is dumped, stockpiled, pushed through chutes, fed to crushers and carried on belts. Bulk flow
fails in expensive ways: chutes block and spill, stockpiles segregate, boulders jam crushers. DEM is used in industry to
compare an existing and an improved transfer chute for downtime, spillage and maintenance [29], and a published
physical-AI example cites boulders that jam crushers causing seven-minute delays that cost up to USD 650,000 a year [30].

Two GPU pictures describe the same material at different scales:

- **DEM** (discrete element method): every fragment is a body with contact forces. Accurate at the scale of a bucket
  or chute, expensive at the scale of a stockpile.
- **MPM** (material point method): the pile is an elasto-plastic continuum carried by particles on a background grid.
  It handles large deformation (dumping, slumping, digging) at much larger scale.

Both run offline in the studio and are baked for the web. The browser gets small WGSL twins and a learned surrogate
([M8](../methods/m08-gns-surrogate.md)). The analytical results on this page (repose geometry, Beverloo, conveyor
power, blending) run live.

## 1. DEM: soft-sphere contact

DEM is an explicit, contact-by-contact and particle-by-particle scheme for assemblies of discs and spheres [1]. Each
particle $i$ obeys Newton's laws with the sum of its contact forces:

$$
m_i\,\dot{\mathbf v}_i = m_i\,\mathbf g + \sum_j \big(\mathbf F_{n,ij} + \mathbf F_{t,ij}\big), \qquad
I_i\,\dot{\boldsymbol\omega}_i = \sum_j \big(R_i\,\mathbf n_{ij}\times\mathbf F_{t,ij} + \mathbf M_{r,ij}\big)
$$

![DEM soft-sphere contact: Hertz–Mindlin with rolling resistance](../assets/diagrams/dem-contact-model.svg)

*Two overlapping spheres, the rheological elements of the contact and the equations, with the Rayleigh time-step
limit.*

**Hertz–Mindlin (no-slip).** Normal force from Hertz, tangential force from Mindlin and Deresiewicz [2], damping
after Tsuji et al. [3], in the standard form (the reference implementation's documentation shows its formulas only as
images [4], so this transcription is UNVERIFIED — pinned at specification):

$$
F_n = \tfrac43\,E^{\ast}\sqrt{R^{\ast}}\,\delta_n^{3/2}, \qquad
F_n^{d} = -2\sqrt{\tfrac56}\,\beta\,\sqrt{S_n\,m^{\ast}}\;v_n^{\text{rel}}, \qquad
S_n = 2E^{\ast}\sqrt{R^{\ast}\delta_n}
$$

$$
F_t = -S_t\,\delta_t, \qquad S_t = 8\,G^{\ast}\sqrt{R^{\ast}\delta_n}, \qquad \lvert F_t\rvert \le \mu_s\,F_n,
\qquad \beta = \frac{\ln e}{\sqrt{\ln^2 e + \pi^2}}
$$

$$
\frac{1}{E^{\ast}} = \frac{1-\nu_1^2}{E_1} + \frac{1-\nu_2^2}{E_2}, \qquad
\frac{1}{R^{\ast}} = \frac{1}{R_1} + \frac{1}{R_2}, \qquad
\frac{1}{m^{\ast}} = \frac{1}{m_1} + \frac{1}{m_2}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $\delta_n$, $\delta_t$ | normal overlap, accumulated tangential displacement | m |
| $E$, $\nu$, $G^{\ast}$ | Young's modulus, Poisson's ratio, effective shear modulus (definition pinned at specification) | Pa, –, Pa |
| $R$, $m$ | particle radius and mass | m, kg |
| $v_n^{\text{rel}}$ | normal relative velocity | m/s |
| $e$ | coefficient of restitution | – |
| $\mu_s$, $\mu_r$ | sliding and rolling friction coefficients | – |

**Rolling resistance** stands in for particle shape and angularity on spheres. Ai et al. compare rolling-resistance
model types; the elastic–plastic spring–dashpot type, with the torque capped at $\mu_r R^{\ast} F_n$, is the common
choice for packing and repose [5] (UNVERIFIED — pinned at specification).

*Worked example 1* (illustrative: two equal spheres, $R$ = 5 mm, $E$ = 50 MPa, $\nu$ = 0.25, rock density
2,650 kg/m³): $E^{\ast}$ = 26.7 MPa, $R^{\ast}$ = 2.5 mm; an overlap of 1 % of $R$ gives $F_n$ = 0.63 N, about 46
times the weight of one sphere (0.014 N). Resting contacts therefore sit at much smaller overlaps. With $e = 0.5$ the
damping ratio is $\beta = -0.215$.

**Time step.** Explicit DEM is stable only for steps below the Rayleigh-wave limit (transcription UNVERIFIED — pinned
at specification):

$$
\Delta t_R = \frac{\pi\,R\,\sqrt{\rho/G}}{0.1631\,\nu + 0.8766}
$$

*Worked example 1, continued:* with $G = E/(2(1+\nu))$ = 20 MPa, $\Delta t_R$ = 0.197 ms, and a fraction of it is used
per step. Real rock stiffness ($E$ = 50 GPa) shrinks it to 6.2 µs, 31.6 times smaller, because
$\Delta t \propto R\sqrt{\rho/E}$. Standard practice is a documented, reduced Young's modulus, with a check that the
repose and discharge targets still hold.

**Calibration** is the crux. Bulk tests (angle of repose, shear cell, draw-down) are matched by tuning
micro-parameters, and the parameter sets are often non-unique [6]. Recent work moves from a single repose angle to the
full heap profile [7]. Warp's shipped DEM example uses a linear spring–dashpot with Coulomb friction (65,536 particles),
not Hertz–Mindlin and not a calibrated material [8]; PitStudio writes its own kernel.

**Scale (estimates, to be measured).** About 180 bytes per sphere including about six history contacts puts 5 M
spheres near 0.9 GB, so on a 16 GB GPU the binding limit is the time step, not memory.

## 2. MPM: the granular continuum

MPM carries mass, velocity and deformation on particles and solves momentum on a background grid each step: transfer
particles to grid (P2G), update grid velocities with stresses and boundary conditions, transfer back (G2P) and update
each particle's deformation and stress. Two variants matter here:

- **Explicit MLS-MPM.** The moving-least-squares discretisation makes MPM about two times faster and supports two-way
  rigid coupling with displacement discontinuities [9]. PitStudio's own explicit kernel is the reference twin of the
  browser WGSL kernel, so the same algorithm runs on both sides.
- **Implicit MPM.** Newton's `SolverImplicitMPM` steps unconditionally stably, with pressure-dependent Drucker–Prager
  yield (friction coefficient, viscosity, dilatancy, hardening and softening), a coupling interface for rigid bodies,
  sparse or dense grids and APIC/PIC transfer [12]; its method reference is the semi-implicit granular MPM of Daviet and
  Bertails-Descoubes [11]. It is the production path for piles, slumps and bucket digging.

**Drucker–Prager.** For a cohesionless material the yield condition caps the shear stress by the pressure (standard
form; pinned at specification):

$$
\tau \le \mu\,p, \qquad p = -\tfrac13\operatorname{tr}\boldsymbol\sigma, \qquad
\tau = \frac{\lVert\operatorname{dev}\boldsymbol\sigma\rVert}{\sqrt 2}
$$

Klár et al. formulate Drucker–Prager elastoplasticity for sand in MPM [10]. If $\mu$ is read as $\tan\phi$, Newton's
granular example default $\mu = 0.68$ [13] corresponds to $\phi \approx 34.2°$ (arithmetic); whether that equals the
simulated repose angle is UNVERIFIED and is exactly what calibration checks.

**μ(I) rheology.** Dense granular flow has a rate-dependent friction, written in terms of the inertial number
$I = \dot\gamma\,d/\sqrt{p/\rho_s}$ as $\mu(I) = \mu_s + (\mu_2 - \mu_s)/(I_0/I + 1)$ (form transcribed from the
standard literature; UNVERIFIED — pinned at specification). Dunatunga and Kamrin use MPM with μ(I) and reproduce
Beverloo scaling in silos and the power-law run-out scaling of granular column collapse [14]: the
engineering-validation precedent for using MPM on bulk flow.

**Column collapse benchmark.** For a column of initial radius $R_i$ and height $H_i$ (aspect ratio $a = H_i/R_i$), the
normalised run-out $(R_\infty - R_i)/R_i$ grows as $a$ for low aspect ratios and as $a^{1/2}$ for high ones, with the
transition near $a \approx 1.7$ [19]. The prefactors of the original experiments [17][18] are UNVERIFIED (closed
access) and are pinned at specification before they become test oracles.

**Scale.** Published GPU MPM runs up to ten million particles at under a minute per frame [15]; browser WebGPU MLS-MPM
reaches about 100 k particles on integrated graphics and about 300 k on discrete GPUs, using fixed-point atomics
because WGSL atomics are integer-only [16].

## 3. Angle of repose and stockpile geometry

The angle of repose is the standard calibration target [6]. Handbook values: crushed-stone gravel about 45°, natural
gravel with sand 25–30°, granite 35–40°, dry sand 34° [20]; measurement methods and their influences are reviewed in
[21]. Per-ore values must come from tests, not handbooks.

Away from the toe and the crest, a stockpile under a stacker is a cone or a ridge at the repose angle $\phi_r$, so
its volume is arithmetic:

$$
V_{\text{cone}} = \frac{\pi}{3}\,r^3\tan\phi_r, \qquad A_{\text{ridge}} = r^2\tan\phi_r \ \ \text{(cross-section per metre)}
$$

*Illustrative:* a conical pile of base radius 30 m at 37° is 22.6 m high and holds 21,300 m³. This is why the browser
can show stockpile volume live while the flow itself is a baked DEM or MPM replay.

## 4. Hopper and chute discharge: Beverloo

The mass discharge rate of a granular material through an orifice does not depend on the fill height, unlike a fluid
[22]:

$$
Q = C\,\rho_b\,\sqrt g\,\big(D - k\,d\big)^{5/2}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $Q$ | mass discharge rate | kg/s |
| $\rho_b$ | bulk density | kg/m³ |
| $D$, $d$ | orifice diameter, particle diameter | m |
| $C$, $k$ | discharge and empty-annulus coefficients | – |

The 5/2 exponent follows from dimensional analysis: outflow velocity scales as $\sqrt{gD}$ and the flowing area as
$D^2$. A Hertz–Mindlin DEM of 4 × 10⁵ spheres reproduces the law with the exponent fixed at 5/2 and a fitted
$C = 0.56$ [23], but that fit uses the **particle** density ($\rho$ = 3,000 kg/m³ in place of $\rho_b$, eqs. 1 and 6),
so its $C$ is not interchangeable with the bulk-density $C$ of the form above. The textbook bulk-density ranges
$C \approx 0.55$–0.65 and $k \approx 1.4$–1.5 are UNVERIFIED — pinned at specification; Mankoc et al. extend the law to
small orifices [24].

*Worked example 2* (illustrative: $C$ = 0.56 used as a bulk-density coefficient, $\rho_b$ = 1,600 kg/m³, $d$ = 20 mm,
$k$ = 1.5): a 0.3 m orifice
discharges 106 kg/s (383 t/h); halving it to 0.15 m gives 14 kg/s, and doubling it to 0.6 m gives 688 kg/s. The steep
$D^{5/2}$ dependence is why chute and feeder openings are sized with margin.

## 5. Conveyors: capacity and power

**Capacity** is continuity (arithmetic): $\dot m = \rho_b\,A\,v$, with $A$ the load cross-section (m²), which depends on
the belt width and on the troughing and surcharge angles through the tables of the CEMA handbook [25] (tables not
reproduced; pinned at specification). *Illustrative:* $A$ = 0.25 m², $v$ = 4 m/s and $\rho_b$ = 1,600 kg/m³ give
5,760 t/h.

**Power.** The CEMA effective-tension method (7th edition) [25] and ISO 5048 [26] build the drive force from
resistances (UNVERIFIED transcriptions — pinned at specification; both standards are paywalled):

$$
T_e = L\,K_t\,(K_x + K_y W_b + 0.015\,W_b) + W_m\,(L\,K_y + H) + T_p + T_{am} + T_{ac}, \qquad P = T_e\,V
$$

$$
F_U = C\,f\,L\,g\,\big[q_{RO} + q_{RU} + (2q_B + q_G)\cos\delta\big] + q_G\,H\,g + F_{S1} + F_{S2}, \qquad P_A = F_U\,v
$$

with $L$ the length, $H$ the lift, $W_b$ and $W_m$ the belt and material weight per length, $K_t$, $K_x$, $K_y$ the
temperature, idler and flexure factors, $T_p$, $T_{am}$, $T_{ac}$ the pulley, material-acceleration and accessory
tensions; and, in the ISO form, $f$ the artificial friction factor, $C$ the length coefficient, $q$ the masses per
metre of the idlers, belt and goods, and $F_{S1}$, $F_{S2}$ special resistances. DIN 22101 extends the resistance
calculation and defines start-up and braking factors [27]. Units follow each standard. A physics floor is the lift
power $\dot m\,g\,H$: 2,000 t/h lifted 30 m needs at least 164 kW before friction and drive losses (arithmetic).

## 6. Sampling and blending (Gy)

Gy derived the output variance of chevron and windrow stockpiles from the theory of sampling, with a full-scale
experimental check [28]. In the idealised limit of uncorrelated input reclaimed over $N$ layers in full cross-section,
$\sigma^2_{\text{out}} \approx \sigma^2_{\text{in}}/N$ (simplification UNVERIFIED — pinned at specification). Real ore
grades are autocorrelated. For layers whose grades follow a first-order autoregressive series with lag-one correlation
$\rho$, the variance of their mean is (arithmetic)

$$
\sigma^2_{\text{out}} = \frac{\sigma^2_{\text{in}}}{N}\Big[1 + 2\sum_{k=1}^{N-1}\Big(1 - \frac kN\Big)\rho^{k}\Big],
\qquad VRR = \frac{\sigma^2_{\text{in}}}{\sigma^2_{\text{out}}}
$$

*Illustrative:* with $N$ = 100 layers, the variance reduction ratio is 100 for independent layers but only 5.8 at
$\rho = 0.9$. Blending performance must therefore come from a variogram-based Monte Carlo of the real grade series,
not from the $1/N$ rule.

Sampling has its own error floor. Gy's fundamental sampling error is usually written
$\sigma^2_{FSE} = (1/M_S - 1/M_L)\,c\,f\,g\,\ell\,d^3$ with sample and lot masses $M_S$, $M_L$, top size $d$ and
mineralogical, shape, granulometric and liberation factors $c$, $f$, $g$, $\ell$ (transcription UNVERIFIED — pinned at
specification; PitStudio ships no default factor values).

## Assumptions and limits

- **Spheres stand in for rocks.** Rolling resistance approximates shape; clumps and polyhedra are not used.
- **Softened stiffness.** Reduced moduli are documented and checked against repose and discharge targets.
- **Calibration is non-unique.** A matched repose angle does not identify a unique parameter set [6].
- **Animation-grade particles are not physics.** Position-based particle systems used for visual effects are not
  calibrated Hertz–Mindlin or Drucker–Prager models and are never used for PitStudio's numbers.
- **Standards.** CEMA, ISO 5048 and DIN 22101 are paywalled; PitStudio implements the public equation forms only and
  cannot redistribute their tables.
- **Parity, not identity.** Browser kernels cannot match GPU float atomics bit for bit, so parity compares observables
  (repose angle, run-out, discharge, mass drift) within tolerances fixed at specification.

## In PitStudio

| Where | What | Lane |
|---|---|---|
| `minephys.bulk` | Beverloo, repose geometry, CEMA capacity and power, Gy blending | live |
| `studio/src/pitstudio_studio/physics/` (`st50_physics`) | own Warp DEM (Hertz–Mindlin + rolling resistance, HashGrid, deterministic reference runs); Newton implicit MPM; own explicit MLS-MPM reference twin | precompute → replay |
| [M7](../methods/m07-gpu-granular-physics.md) | GPU granular physics; live WGSL twin up to 2 × 10⁴ particles | replay + live |
| [M8](../methods/m08-gns-surrogate.md) | GNS surrogate of DEM/MPM rollouts, live in the browser | precompute → live |
| [M9](../methods/m09-differentiable-dem-calibration.md) | differentiable DEM calibration (Warp tape) vs CMA-ES | precompute |
| Cases | [A3](../cases/a3-loading-payload-variance.md) bucket–pile, [D1](../cases/d1-blast-muck-pile.md) muck pile | — |

**Status: Not yet run** — produced in the data-and-models phase; the GPU capability probes are written but not yet
run on the reference machine. Pre-registered acceptance (from the plan): the GNS surrogate holds the repose angle
within ±1.5° and the run-out within ±5 % on held-out geometries; the DEM calibration's 95 % confidence interval covers
the synthetic true parameter in at least 90 % of trials.

## References

1. Cundall, Strack (1979). A discrete numerical model for granular assemblies. *Géotechnique* 29(1), 47–65.
   https://doi.org/10.1680/geot.1979.29.1.47
2. Mindlin, Deresiewicz (1953). Elastic spheres in contact under varying oblique forces. *J. Appl. Mech.* 20(3),
   327–344. https://doi.org/10.1115/1.4010702
3. Tsuji, Tanaka, Ishida (1992). Lagrangian numerical simulation of plug flow of cohesionless particles in a horizontal
   pipe. *Powder Technol.* 71(3), 239–250. https://doi.org/10.1016/0032-5910(92)88030-L
4. LIGGGHTS documentation: Hertz granular model. https://www.cfdem.com/media/DEM/docu/gran_model_hertz.html
5. Ai, Chen, Rotter, Ooi (2011). Assessment of rolling resistance models in discrete element simulations. *Powder
   Technol.* 206(3), 269–282. https://doi.org/10.1016/j.powtec.2010.09.030
6. Coetzee (2017). Review: Calibration of the discrete element method. *Powder Technol.* 310, 104–142.
   https://doi.org/10.1016/j.powtec.2017.01.015
7. arXiv listing on DEM calibration from repose and heap morphology (2605.09371 and related).
   http://export.arxiv.org/api/query?search_query=all:DEM%20AND%20all:calibration%20AND%20all:repose&max_results=8
8. Warp core example `example_dem.py` (linear spring–dashpot, 65,536 particles).
   https://raw.githubusercontent.com/NVIDIA/warp/main/warp/examples/core/example_dem.py
9. Hu, Fang, Ge, Qu, et al. (2018). A moving least squares material point method with displacement discontinuity and
   two-way rigid body coupling. *ACM Trans. Graph.* 37(4). https://doi.org/10.1145/3197517.3201293
10. Klár, Gast, Pradhana, Fu, et al. (2016). Drucker–Prager elastoplasticity for sand animation. *ACM Trans. Graph.*
    35(4). https://doi.org/10.1145/2897824.2925906
11. Daviet, Bertails-Descoubes (2016). A semi-implicit material point method for the continuum simulation of granular
    materials. *ACM Trans. Graph.* 35(4). https://doi.org/10.1145/2897824.2925877
12. Newton documentation: `SolverImplicitMPM`.
    https://newton-physics.github.io/newton/latest/api/_generated/newton.solvers.SolverImplicitMPM.html
13. Newton example `example_mpm_granular.py` (defaults: voxel 0.1, friction 0.68).
    https://raw.githubusercontent.com/newton-physics/newton/main/newton/examples/mpm/example_mpm_granular.py
14. Dunatunga, Kamrin (2015). Continuum modelling and simulation of granular flows through their many phases. *J.
    Fluid Mech.* 779, 483–513. https://doi.org/10.1017/jfm.2015.383
15. Gao et al. (2018). GPU optimization of material point methods. *ACM Trans. Graph.* 37(6).
    https://doi.org/10.1145/3272127.3275044
16. WebGPU-Ocean: MLS-MPM in the browser (MIT). https://github.com/matsuoka-601/WebGPU-Ocean
17. Lube, Huppert, Sparks, Hallworth (2004). Axisymmetric collapses of granular columns. *J. Fluid Mech.* 508,
    175–199. https://doi.org/10.1017/S0022112004009036
18. Lajeunesse, Mangeney-Castelnau, Vilotte (2004). Spreading of a granular mass on a horizontal plane. *Phys.
    Fluids* 16(7), 2371–2381. https://doi.org/10.1063/1.1736611
19. Deposition morphology of granular column collapses (run-out scaling and transition). arXiv:2002.02146.
    https://arxiv.org/html/2002.02146v3
20. Angle of repose (table citing Glover, *Pocket Ref*). https://en.wikipedia.org/wiki/Angle_of_repose
21. Beakawi Al-Hashemi, Baghabra Al-Amoudi (2018). A review on the angle of repose of granular materials. *Powder
    Technol.* 330, 397–417. https://doi.org/10.1016/j.powtec.2018.02.003
22. Beverloo, Leniger, van de Velde (1961). The flow of granular solids through orifices. *Chem. Eng. Sci.* 15(3–4),
    260–269. https://doi.org/10.1016/0009-2509(61)85030-6
23. DEM validation of the Beverloo law with Hertz–Mindlin contacts (4 × 10⁵ spheres, C = 0.56). arXiv:2512.03698.
    https://arxiv.org/html/2512.03698v1
24. Mankoc et al. (2007). arXiv:0707.4550: orifice flow-rate law extended to small orifices.
    https://arxiv.org/abs/0707.4550
25. CEMA. *Belt Conveyors for Bulk Materials*, 7th ed., errata summary pages (as of Feb 2015).
    https://www.cemanet.org/wp-content/uploads/2015/04/BBK-7th-Edition-Errata-Summary-Pages-as-of-Feb1-2015-SEC.pdf
26. ISO 5048:1989 (ed. 2): operating power and tensile forces of belt conveyors with carrying idlers.
    https://www.iso.org/standard/11069.html (UNVERIFIED — source unreachable)
27. DIN 22101:2011: belt conveyors for bulk materials, basis for calculation.
    https://webstore.ansi.org/standards/din/din221012011
28. Gy (1981). A new theory of bed-blending derived from the theory of sampling — development and full-scale
    experimental check. *Int. J. Miner. Process.* 8(3), 201–238. https://doi.org/10.1016/0301-7516(81)90013-2
29. Mason (2016). Improved transfer chute design using DEM software. University of Southern Queensland.
    https://sear.unisq.edu.au/31438/
30. NVIDIA blog (2025-10-29). Scaling physical AI with synthetic data (crusher-boulder example).
    https://blogs.nvidia.com/blog/scaling-physical-ai-omniverse/
