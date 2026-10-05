# Loading and terramechanics

> How a bucket fills, how many passes a truck needs, why payload varies, and the fundamental earthmoving equation
> for the force a tool needs to cut soil. · Part of: [Theory](README.md) · Related: [Haulage](haulage.md),
> [Bulk flow, DEM and MPM](bulk-flow-dem-mpm.md), [Robot learning](robot-learning.md),
> [Case A3](../cases/a3-loading-payload-variance.md)

## What and why

Loading sets the first term of every haul cycle and the payload that every downstream number is divided by. It is
also where blasting meets haulage: bucket fill depends on fragmentation, and payload scatter costs fuel. Reducing
payload variance (over a 0–30 % range tested) can cut haul-truck fuel by up to 35 % at an open-cut coal mine [3].

Two physical pictures are needed, and they apply to different materials:

- **Continuum soil cutting.** For soil and weak, fine material, the force on a blade or bucket edge follows from a
  failing soil wedge: the fundamental earthmoving equation (FEE) [1][2]. It is analytical, quasi-static and cheap. In
  PitStudio it drives the excavator dig task.
- **Granular rock.** A blasted muck pile has fragments comparable to the bucket. It is a granular medium, simulated
  with the discrete element method (DEM) or the material point method (MPM), see
  [Bulk flow, DEM and MPM](bulk-flow-dem-mpm.md).

## 1. Bucket fill, passes and loading time

$$
n_p = \left\lceil \frac{M_{\text{target}}}{V_b\, k_f\, \rho_{\text{loose}}} \right\rceil, \qquad
\rho_{\text{loose}} = \frac{\rho_{\text{bank}}}{1 + s_w}, \qquad
t_{\text{load}} = n_p\, t_{\text{sc}}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $n_p$ | passes per truck | – |
| $M_{\text{target}}$ | target payload | t |
| $V_b$ | heaped (rated) bucket volume | m³ |
| $k_f$ | fill factor: payload volume / rated heaped volume | – |
| $\rho_{\text{bank}}$, $\rho_{\text{loose}}$ | in-situ and loose bulk density | t/m³ |
| $s_w$ | swell (loose volume / bank volume − 1) | – |
| $t_{\text{sc}}$ | loader swing cycle: dig, swing loaded, dump, swing back | s |

These relations are geometry and bookkeeping (arithmetic). The **fill factor** is controlled by fragmentation (the
median size $x_{50}$ and the uniformity of the muck pile), by how loose the pile is and by operator skill. A typical
published range of about 0.8–1.1 for well-blasted material, lower for blocky or tight digging, is UNVERIFIED — pinned
at specification; no open dataset of measured fill factors was found.

**Worked example 1** (illustrative inputs: 220 t target payload, 40 m³ bucket, $k_f$ = 0.9, $\rho_{\text{bank}}$ =
2.7 t/m³, swell 40 %, 35 s swing cycle):

- $\rho_{\text{loose}} = 2.7 / 1.4 = 1.93$ t/m³, so one full pass carries $40 \times 0.9 \times 1.93 = 69.4$ t.
- $M_{\text{target}}$ is 3.17 pass-equivalents. Three full passes give 208.3 t, 5.3 % under target. Four passes need a
  part-filled last bucket. The ceiling in $n_p$ is the source of the trade-off between under-loading and slow,
  error-prone partial passes.
- With four passes, $t_{\text{load}} = 4 \times 35 = 140$ s.

## 2. Payload variance

A payload is a sum of pass masses, $M = \sum_{i=1}^{n_p} m_i$. With independent, identically distributed passes of
mean $\mu_p$ and standard deviation $\sigma_p$:

$$
\mathbb{E}[M] = n_p\,\mu_p, \qquad \sigma_M^2 = n_p\,\sigma_p^2, \qquad CV_M = \frac{CV_p}{\sqrt{n_p}}
$$

This idealisation is not validated against field data (UNVERIFIED for real operations). Passes taken from the same
face by the same operator are correlated. With a common pairwise correlation $r$ between passes (arithmetic):

$$
\sigma_M^2 = n_p\,\sigma_p^2\,\big[1 + (n_p - 1)\,r\big]
$$

*Illustrative:* with a 10 % pass CV and four passes, the payload CV is 5.0 % for independent passes, 7.9 % at
$r = 0.5$ and 10 % at $r = 1$. Correlation removes the averaging that extra passes seem to buy.

Payload scatter matters downstream because fuel per tonne depends on gross vehicle weight and total resistance
([Haulage](haulage.md), §4): under-loaded trucks burn fuel moving empty mass, and over-loaded trucks run slower and
wear tyres and roads. The case KPIs are payload CV, passes per truck and fuel per tonne.

## 3. The fundamental earthmoving equation

![Fundamental earthmoving equation: the soil wedge in front of a blade](../assets/diagrams/terramechanics-fee.svg)

*A blade at rake angle α cuts to depth d; the wedge fails along a plane at angle β and is held by its weight, the
blade force, the soil reaction, cohesion, adhesion and surcharge.*

Reece's fundamental earthmoving equation writes the force on a cutting tool as a sum of four terms, each a soil
property times a dimensionless factor [1]:

$$
F = \big(\rho\, g\, d^2 N_\gamma + c\, d\, N_c + c_a\, d\, N_a + q\, d\, N_q\big)\, w
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $F$ | total soil force on the tool | N |
| $\rho$ | soil bulk density | kg/m³ |
| $d$, $w$ | tool depth and width | m |
| $c$ | soil cohesion | Pa |
| $c_a$ | soil–tool adhesion | Pa |
| $q$ | surcharge on the soil surface | Pa |
| $N_\gamma$, $N_c$, $N_a$, $N_q$ | wedge factors | – |
| $\alpha$ | rake angle of the tool from the horizontal | rad |
| $\beta$ | failure-plane angle from the horizontal | rad |
| $\phi$, $\delta$ | soil friction angle, soil–tool friction angle | rad |

### Derivation of the 2-D wedge factors

Take a wide blade (no side effects) with its tip at depth $d$. The soil in front of it fails as a rigid triangular
wedge bounded by the blade face, the soil surface and a straight failure plane through the tip. This is the
construction McKyes and Ali use for narrow blades, without their side wedges [2]. Per unit width:

- weight $W = \tfrac12 \rho g d^2 (\cot\alpha + \cot\beta)$, acting down;
- blade force $P$ on the soil, inclined at $\delta$ to the blade normal because the soil slides up the blade:
  direction $(\sin(\alpha+\delta),\ \cos(\alpha+\delta))$ in (forward, up) components;
- reaction $R$ from the undisturbed soil, inclined at $\phi$ to the failure-plane normal:
  direction $(-\sin(\beta+\phi),\ \cos(\beta+\phi))$;
- cohesion $c\,d/\sin\beta$ along the failure plane, adhesion $c_a\,d/\sin\alpha$ along the blade, and surcharge
  $q\,d(\cot\alpha + \cot\beta)$ on the top.

Horizontal and vertical equilibrium of the wedge:

$$
P\sin(\alpha+\delta) - R\sin(\beta+\phi) - c\,d\cot\beta + c_a\,d\cot\alpha = 0
$$

$$
P\cos(\alpha+\delta) + R\cos(\beta+\phi) = W + c\,d + c_a\,d + q\,d(\cot\alpha + \cot\beta)
$$

Eliminating $R$ with the first equation and writing $D = \cos(\alpha+\delta) + \sin(\alpha+\delta)\cot(\beta+\phi)$
gives the FEE with

$$
N_\gamma = \frac{\cot\alpha + \cot\beta}{2D}, \qquad
N_c = \frac{1 + \cot\beta\,\cot(\beta+\phi)}{D}, \qquad
N_a = \frac{1 - \cot\alpha\,\cot(\beta+\phi)}{D}, \qquad
N_q = \frac{\cot\alpha + \cot\beta}{D}
$$

The soil fails on the plane of least resistance, so $\beta$ is the value that minimises $F$. The construction is
valid while $D > 0$, that is $\alpha + \delta + \beta + \phi < 180°$. The force on the tool splits into a draft
$H = F\sin(\alpha+\delta)$ against the direction of travel and a vertical component $V = F\cos(\alpha+\delta)$;
$V > 0$ pulls the tool into the ground, and $V < 0$ pushes it out.

For **narrow tools** ($w/d$ small), McKyes and Ali add two side crescents to the central wedge, which raises every
factor as $w/d$ falls [2]. Their 3-D expressions are not transcribed here (UNVERIFIED — pinned at specification).

### Worked example 2

Illustrative inputs: $\alpha$ = 60°, $\delta$ = 20°, $\phi$ = 35°, $d$ = 0.5 m, $w$ = 1 m, $\rho$ = 1,800 kg/m³.

- Cohesionless, no surcharge ($c = c_a = q = 0$): the minimum is at $\beta^\ast \approx 28.1°$ with
  $N_\gamma \approx 1.82$, so $F = 1800 \times 9.81 \times 0.25 \times 1.82 \approx 8.0$ kN, with draft
  $H \approx 7.9$ kN and $V \approx 1.4$ kN. Solving the two equilibrium equations directly at the same $\beta$ gives
  the same $F$ (the check the tests will reuse).
- Adding $c$ = 10 kPa and $c_a$ = 5 kPa: $\beta^\ast \approx 28.2°$ and $F \approx 25.1$ kN. Cohesion dominates
  shallow cuts because its term scales with $d$ while the weight term scales with $d^2$.

The rake angle matters as much as the soil (same inputs, cohesionless):

| Rake $\alpha$ (°) | $\beta^\ast$ (°) | $N_\gamma$ (–) | $F$ (kN) | $H$ (kN) | $V$ (kN) |
|---|---|---|---|---|---|
| 30 | 35.6 | 1.71 | 7.6 | 5.8 | 4.9 |
| 45 | 32.8 | 1.61 | 7.1 | 6.4 | 3.0 |
| 60 | 28.1 | 1.82 | 8.0 | 7.9 | 1.4 |
| 75 | 22.4 | 2.45 | 10.8 | 10.8 | −0.9 |
| 90 | 16.2 | 4.16 | 18.4 | 17.3 | −6.3 |

Steep blades need far more draft and are pushed up out of the cut; low rake angles cut cheaply and pull the tool in.

## 4. From soil cutting to blasted rock

The FEE assumes a continuum soil and a quasi-static, rigid wedge. It does not describe blasted rock with fragments
comparable to the bucket, where interlocking, segregation and particle jamming govern. Those need particle or
continuum-granular simulation:

- **DEM** resolves every fragment as a contacting sphere or clump with Hertz–Mindlin contact laws; it is the
  reference for bucket–pile interaction but its micro-parameters must be calibrated to bulk tests such as the angle of
  repose [10].
- **MPM** treats the pile as an elasto-plastic continuum carried by particles. The moving-least-squares MPM was
  designed for tool–material interaction with displacement discontinuities and two-way rigid coupling [4]. Newton's
  implicit MPM solver couples rigid bodies to granular material through a coupling interface [5][6].
- **Precedent for learning on MPM.** Excavator soil-manipulation policies trained in a GPU-parallel MPM simulation
  were transferred to an 11.5 t excavator that built a 42 m × 2.1 m embankment in 45 min over 201 strokes without
  failure [7].
- **Validation data are scarce.** MPM excavation has been validated against robotic excavation data [8], but no open
  dataset of measured fill factors or dig forces for mining buckets was identified.

For vehicles on soft ground (as opposed to tools cutting it), the classical model is Bekker–Wong pressure–sinkage
terramechanics [9]. On haul roads its effect collapses into the rolling-resistance term of [Haulage](haulage.md).

## Assumptions and limits

- **2-D, rigid wedge, plane failure surface.** The FEE factors above are exact for that construction only. Curved
  failure surfaces, side effects and dynamic (rate) effects are not included.
- **Quasi-static.** No inertia of the soil being accelerated; fast cuts need an acceleration term.
- **Continuum soil only.** Do not apply the FEE to blocky blasted rock; use DEM or MPM.
- **Illustrative numbers.** The worked examples use teaching inputs, not measured soil or bucket data. Fill factors and
  the independence of passes are UNVERIFIED for field conditions.
- **Educational, not design software.** Results are not a substitute for OEM bucket ratings or site trials.

## In PitStudio

| Where | What | Lane |
|---|---|---|
| `studio/isaaclab/` (IL-2) | excavator dig task with FEE soil forces on the bucket; zero-shot check of the same policy in Newton implicit MPM (`st61_il_mpm_eval`) | precompute → live TS twin |
| `minephys.haulage` | passes, payload and cycle-time bookkeeping that feed the haul cycle | live |
| [M7](../methods/m07-gpu-granular-physics.md), [M8](../methods/m08-gns-surrogate.md), [M9](../methods/m09-differentiable-dem-calibration.md) | GPU DEM/MPM bucket–pile rollouts, the learned granular surrogate, friction calibration from repose | replay + live surrogate |
| [M21](../methods/m21-isaac-lab-policies.md) | Isaac Lab dig policy (IL-2) and optional loader (IL-3) | precompute → live |
| [Case A3](../cases/a3-loading-payload-variance.md) | payload CV, passes per truck, fuel per tonne | — |

**Status: Not yet run** — produced in the data-and-models phase. Pre-registered acceptance for IL-2 (from the plan):
fill factor ≥ 0.8 in ≥ 80 % of FEE episodes; stalls ≤ 5 %; the FEE → MPM fill gap reported with a 95 % confidence
interval; "beats the scripted dig" claimed only if the paired 95 % confidence interval of the difference in fill ×
cycle time excludes 0. The FEE → MPM gap is a sim-to-sim gap, not a sim-to-real one; see [Sim-to-real](sim-to-real.md).

## References

1. Reece (1964). The fundamental equation of earth-moving mechanics. *Proc. IMechE, Conference Proceedings*
   179(6), 16–22. https://doi.org/10.1243/PIME_CONF_1964_179_134_02
2. McKyes, Ali (1977). The cutting of soil by narrow blades. *J. Terramechanics* 14(2), 43–58.
   https://doi.org/10.1016/0022-4898(77)90001-5
3. International Mining (2016). Mining3 project looks at effect of payload variance on haul truck fuel consumption.
   https://im-mining.com/2016/12/07/mining3-project-looks-effect-payload-variance-haul-truck-fuel-consumption/
4. Hu, Fang, Ge, Qu, et al. (2018). A moving least squares material point method with displacement
   discontinuity and two-way rigid body coupling. *ACM Trans. Graph.* 37(4). https://doi.org/10.1145/3197517.3201293
5. Newton documentation: `SolverImplicitMPM`.
   https://newton-physics.github.io/newton/latest/api/_generated/newton.solvers.SolverImplicitMPM.html
6. Newton example: two-way MPM–rigid coupling.
   https://raw.githubusercontent.com/newton-physics/newton/main/newton/examples/mpm/example_mpm_twoway_coupling.py
7. Werner et al. (2026). arXiv:2609.12677: material-state-conditioned RL policies for excavator soil manipulation,
   trained in a GPU-parallel MPM simulation (abstract). https://arxiv.org/abs/2609.12677
8. Haeri, Skonieczny MPM excavation validated against robotic excavation data, arXiv:2111.01523 (via arXiv
   listing). http://export.arxiv.org/api/query?search_query=abs:excavation%20AND%20(abs:MPM%20OR%20abs:%22material%20point%22)&max_results=15
9. Wong (2024). *Terramechanics and Off-Road Vehicle Engineering* (Bekker–Wong pressure–sinkage parameters).
   https://doi.org/10.1016/b978-0-443-15614-4.00004-7
10. Coetzee (2017). Review: Calibration of the discrete element method. *Powder Technol.* 310, 104–142.
    https://doi.org/10.1016/j.powtec.2017.01.015
