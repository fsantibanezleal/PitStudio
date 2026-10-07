# M13 — Slope stability: limit equilibrium (Bishop, Spencer) with Hoek–Brown and Monte-Carlo probability of failure

> The pit-wall factor of safety is computed live with the method of slices, rock-mass strength comes from the
> generalised Hoek–Brown criterion, and uncertain inputs are sampled to give a probability of failure with its
> confidence interval. · Part of: [Methods](README.md) · Related:
> [Slopes and monitoring theory](../theory/slopes-and-monitoring.md) · [M14 forecasting](m14-slope-forecasting.md) ·
> [M23 slope radar](m23-rtx-sensor-simulation.md) · [Case C1](../cases/c1-slope-time-of-failure.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical | no | live | [C1](../cases/c1-slope-time-of-failure.md) | `minephys.geotech` (Apache-2.0) + TypeScript port; pySlope (MIT) as oracle | not yet implemented |

## What and why

Open-pit slopes are designed against two numbers: the **factor of safety** (FoS), the ratio of available shear
strength to mobilised shear stress on the critical slip surface, and the **probability of failure** (PoF) when the
inputs are uncertain. Limit-equilibrium methods (LEM) remain the industry baseline for both; FEM strength reduction is
the heavier cross-check and is outside this method. Acceptance criteria differ by slope scale (bench, inter-ramp,
overall) and consequence of failure [6], so PitStudio shows them as **configurable inputs**, not facts: the commonly
quoted values are UNVERIFIED — pinned at specification.

M13 provides case C1's static picture — how stable the wall is and how uncertain that is — before
[M14](m14-slope-forecasting.md) and the slope radar of [M23](m23-rtx-sensor-simulation.md) add the dynamic picture of
a wall that is already moving.

## The algorithm

### Bishop's simplified method (circular surfaces)

The sliding mass above a trial circle is cut into vertical slices. Bishop's simplified method satisfies moment
equilibrium about the circle centre and neglects interslice shear [1]†:

$$
F = \frac{\displaystyle\sum_i \big[c' b_i + (W_i - u_i b_i)\tan\phi'\big] / m_{\alpha,i}}{\displaystyle\sum_i W_i \sin\alpha_i},
\qquad
m_{\alpha,i} = \cos\alpha_i\left(1 + \frac{\tan\alpha_i \tan\phi'}{F}\right)
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $F$ | factor of safety | – |
| $c'$, $\phi'$ | effective cohesion and friction angle | kPa, ° |
| $b_i$ | slice width | m |
| $W_i$ | slice weight per metre of slope | kN/m |
| $u_i$ | pore pressure at the slice base | kPa |
| $\alpha_i$ | inclination of the slice base | ° |

$F$ appears on both sides, so it is found by fixed-point iteration, and the minimum over trial circles is reported.

### Spencer's method (any surface, full equilibrium)

Spencer assumes parallel interslice resultants at a constant inclination $\theta$ and satisfies **both** force and
moment equilibrium; it reduces to Bishop when $\theta = 0$, whereas Bishop satisfies moment but not horizontal force
equilibrium and Janbu force but not moment equilibrium [2][3]. Numerically, for each trial $\theta$ the force-equilibrium
and moment-equilibrium factors $F_f(\theta)$ and $F_m(\theta)$ are computed, and the solution is the $\theta$ at which
they coincide. pySlope implements Bishop only, so Spencer is written in house [7].

### Rock-mass strength: generalised Hoek–Brown

$$
\sigma_1 = \sigma_3 + \sigma_{ci}\left(m_b\frac{\sigma_3}{\sigma_{ci}} + s\right)^{a},\quad
m_b = m_i\,e^{\frac{GSI-100}{28-14D}},\quad
s = e^{\frac{GSI-100}{9-3D}},\quad
a = \tfrac12 + \tfrac16\big(e^{-GSI/15} - e^{-20/3}\big)
$$

$\sigma_1, \sigma_3$ are the major and minor principal stresses (MPa), $\sigma_{ci}$ the intact uniaxial compressive
strength (MPa), $m_i$ the intact material constant (–), $GSI$ the Geological Strength Index (–) and $D \in [0, 1]$ the
blast-damage and stress-relief disturbance factor [4][5]. For LEM, the curved envelope is converted per slice into an
equivalent cohesion and friction angle at the slice-base normal stress (standard practice; equations pinned at
specification). Guidance values of $D$ for open pits are UNVERIFIED — pinned at specification.

### Monte-Carlo probability of failure

```text
pof(slope, distributions, N, seed):
    rng = CounterPRNG(seed)
    fails = 0
    repeat N times:
        sample c', phi', GSI, sigma_ci, pore-pressure ratio from their distributions
        F = min over trial surfaces of bishop_or_spencer(slope, sample)
        fails += (F < 1)
    p = fails / N
    return p, wilson_interval(fails, N)
```

The PoF estimate $\hat p = k/N$ carries a Wilson 95 % interval [8]:
$\big(\hat p + \tfrac{z^2}{2N} \pm z\sqrt{\tfrac{\hat p(1-\hat p)}{N} + \tfrac{z^2}{4N^2}}\big) / \big(1 + \tfrac{z^2}{N}\big)$
with $z = 1.96$.

### Worked examples (illustrative inputs)

**Bishop iteration.** Three slices, $c' = 10$ kPa, $\phi' = 30°$, dry ($u = 0$), $b = 5$ m each; weights 500, 800 and
400 kN/m at base angles 40°, 20° and −5°. The driving sum is $\sum W\sin\alpha = 560.1$ kN/m. Starting from $F = 1$,
the iteration gives 1.866 → 2.018 → 2.034 → 2.035 → 2.035, so $F \approx 2.04$ (a geometrically consistent slope is
generated by the code; these numbers only exercise the fixed point).

**Hoek–Brown parameters.** $GSI = 50$, $m_i = 10$, $D = 0.7$: $m_b = 10\,e^{-50/18.2} = 0.641$,
$s = e^{-50/6.9} = 7.13 \times 10^{-4}$, $a = 0.5 + (e^{-3.333} - e^{-6.667})/6 = 0.506$.

**PoF interval.** 230 failures in 10,000 samples give $\hat p = 2.30\,\%$ with a Wilson 95 % interval of
2.02–2.61 %.

## Baseline and comparison

- **Oracle:** pySlope 1.4.0 (MIT), whose Bishop implementation is validated against Slide v6 and Hyrcan [7]; PitStudio's
  Bishop must match it on shared cases.
- **Internal consistency:** Spencer at $\theta = 0$ must equal Bishop on circular surfaces.
- **Between designs:** steeper vs flatter inter-ramp angles, drained vs undrained, are contrasted side by side on FoS
  and PoF with their intervals. A claim that design A has a lower PoF than design B follows the
  [decision rule](README.md#how-methods-are-compared) on paired samples (same random inputs for both designs).

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)):

- worked examples from primary sources (the † transcriptions and all UNVERIFIED constants pinned first);
- pySlope agreement on shared Bishop cases (tolerance in `specs/000-foundation/thresholds.yaml`);
- at least three metamorphic relations, for example: FoS increases with $c'$ and with $\phi'$; FoS decreases as pore
  pressure rises; Spencer with $\theta = 0$ equals Bishop; PoF is non-increasing in the mean strength;
- TypeScript port parity in the exact class on golden vectors.

**Results: Not yet run** — produced in the data-and-models phase. Reported: C1 FoS and PoF tables with intervals for
the case slopes.

## Lane and web delivery

**Live.** Bishop, Spencer, Hoek–Brown and a Monte-Carlo run of a few thousand samples fit the analytical-model gate
(under 50 KB of JavaScript, 1–50 ms per evaluation for single solves; estimates, measured when the web is built).
Fallback: baked FoS/PoF grids. The `minephys.geotech` wheel in Pyodide provides the reference check.

## Assumptions and limits

- Two-dimensional plane-strain sections; 3-D effects and structurally controlled (kinematic) failures are not covered
  by LEM.
- LEM gives no deformations: it cannot say *when* a slope fails — that is [M14](m14-slope-forecasting.md).
- Input distributions are assumptions; PoF is only as good as them.
- **Educational, not design or regulatory software**, with validity ranges stated per input.

## In PitStudio

- **Cases:** [C1](../cases/c1-slope-time-of-failure.md) (FoS, PoF).
- **Code (planned):** `minephys.geotech` (Hoek–Brown, LEM, inverse velocity, Bayesian TTF, slope-radar model);
  TypeScript port in a `web/` worker; pySlope as a test-only oracle.
- **Status:** not yet implemented — built test-first in the build phase.

† Standard form; the transcription is checked against the primary source by a worked-example test at specification.

## References

1. Bishop, A. W. (1955). The use of the slip circle in the stability analysis of slopes. Géotechnique 5(1):7–17.
   https://doi.org/10.1680/geot.1955.5.1.7
2. Spencer, E. (1967). A method of analysis of the stability of embankments assuming parallel inter-slice forces.
   Géotechnique 17(1):11–26. https://doi.org/10.1680/geot.1967.17.1.11
3. Spencer method of slices (educational; equilibrium comparison of Bishop, Janbu and Spencer).
   https://www.geoengineer.org/education/slope-stability/slope-stability-the-spencer-method-of-slices
4. Itasca — Hoek–Brown model documentation ($m_b$, $s$, $a$ from GSI and D).
   https://docs.itascacg.com/itasca900/common/models/hoek/doc/modelhoek.html
5. Hoek, E. & Brown, E. T. (2019). The Hoek–Brown failure criterion and GSI — 2018 edition. JRMGE 11(3):445–463.
   https://doi.org/10.1016/j.jrmge.2018.08.001
6. Read, J. & Stacey, P. (2009). *Guidelines for Open Pit Slope Design*. CSIRO.
   https://ebooks.publish.csiro.au/content/guidelines-open-pit-slope-design
7. pySlope 1.4.0 (MIT) — Bishop's method validated against Slide v6 and Hyrcan. https://pypi.org/project/pyslope/
8. *Binomial proportion confidence interval* — Wilson score interval.
   https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval
