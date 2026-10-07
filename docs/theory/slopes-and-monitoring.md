# Slopes and monitoring

> Is a pit wall stable, how likely is it to fail, and if it is already moving, when will it fail: limit equilibrium,
> Hoek–Brown rock-mass strength, Monte-Carlo probability of failure, slope radar and inverse-velocity forecasting. ·
> Part of: [Theory](README.md) · Related: [RTX sensor physics](rtx-sensor-physics.md),
> [M13 slope stability (LEM)](../methods/m13-slope-stability-lem.md), [M14 slope forecasting](../methods/m14-slope-forecasting.md),
> [Case C1](../cases/c1-slope-time-of-failure.md)

## What and why

Pit walls fail, and monitoring is what turns a failure into a production loss instead of a disaster. On 10 April 2013
a slide at a large US copper mine moved 165 million tons. Radar had measured the wall every six to eight minutes;
movement reached two inches per day before failure; workers were evacuated the morning of the slide and none of the
roughly 500 workers was injured, but refined-copper output was expected to fall by 50 % [15]. Fall of ground was the
second named fatality cause among ICMM members in 2024: 5 of the 42 fatalities [16].

Two questions, two toolkits:

1. **Design question: is the wall stable?** Limit-equilibrium methods give a factor of safety (FoS) on a trial slip
   surface. Rock-mass strength comes from the generalised Hoek–Brown criterion. Uncertain inputs turn the FoS into a
   probability of failure (PoF).
2. **Operations question: it is moving; when will it fail?** Slope radar measures displacement; accelerating creep
   theory turns velocity into a time-of-failure (TTF) forecast.

## 1. Limit equilibrium: the method of slices

The factor of safety on a trial surface is the available shear strength over the mobilised shear stress, minimised
over all trial surfaces. The sliding mass is cut into vertical slices; each slice $i$ has width $b_i$ (m), weight
$W_i$ (kN/m), base inclination $\alpha_i$ (rad), base length $l_i = b_i/\cos\alpha_i$ (m) and pore pressure $u_i$
(kPa) on its base. The mobilised base shear follows Mohr–Coulomb with effective cohesion $c'$ (kPa) and friction angle
$\phi'$ (rad):

$$
S_i = \frac{c'\,l_i + (N_i - u_i\,l_i)\tan\phi'}{F}
$$

The interslice forces (normal $E$, shear $X$) make the problem statically indeterminate, and each method closes it with
an assumption:

| Method | Interslice assumption | Equilibrium satisfied | Surface |
|---|---|---|---|
| Bishop simplified [1] | $X = 0$ (horizontal interslice forces) | moment (and vertical force per slice) | circular |
| Janbu simplified | $X = 0$, correction factor $f_0$ | force only | any |
| Spencer [2] | resultant of $E$, $X$ parallel, at a constant angle $\theta$ | moment **and** force | any |

Bishop satisfies moment but not horizontal-force equilibrium; Janbu satisfies force but not moment equilibrium;
Spencer satisfies both [3].

![Method of slices on a circular slip surface](../assets/diagrams/slope-lem-slices.svg)

*The illustrative slope with its critical toe circle cut into ten slices, the forces on one slice and the worked
results.*

**Bishop simplified.** Vertical equilibrium of each slice plus moment equilibrium about the circle centre give [1]

$$
F = \frac{\sum_i \big[c' b_i + (W_i - u_i b_i)\tan\phi'\big]/m_{\alpha,i}}{\sum_i W_i \sin\alpha_i},
\qquad m_{\alpha,i} = \cos\alpha_i\Big(1 + \frac{\tan\alpha_i\tan\phi'}{F}\Big)
$$

$F$ appears on both sides, so it is solved by fixed-point iteration from $F_0 = 1$ (standard form; transcription
UNVERIFIED — pinned at specification).

**Janbu simplified** uses force equilibrium only, $F = f_0\,F_0$ with
$F_0 = \sum_i [c' b_i + (W_i - u_i b_i)\tan\phi'] / (\cos\alpha_i\,m_{\alpha,i}) \big/ \sum_i W_i\tan\alpha_i$ and an
empirical correction $f_0$ for interslice shear (form and $f_0$ curves UNVERIFIED — pinned at specification).

**Spencer.** The net interslice force on slice $i$ is a resultant $Q_i$ inclined at $\theta$. Equilibrium normal and
parallel to the base gives [2][3]

$$
Q_i = \frac{\dfrac{c' l_i}{F} + \dfrac{(W_i\cos\alpha_i - u_i l_i)\tan\phi'}{F} - W_i\sin\alpha_i}
{\cos(\alpha_i - \theta)\Big[1 + \dfrac{\tan(\alpha_i - \theta)\tan\phi'}{F}\Big]}
$$

and the pair $(F, \theta)$ solves force and moment equilibrium of the whole mass (moment about the circle centre for a
circular surface):

$$
\sum_i Q_i = 0, \qquad \sum_i Q_i\cos(\alpha_i - \theta) = 0
$$

With $\theta = 0$ the moment equation alone reproduces Bishop's $F$, which is a built-in test identity.

**Worked example 1** (illustrative: 20 m high slope with a 45° face, unit weight 20 kN/m³, $c'$ = 20 kPa,
$\phi'$ = 30°, dry; critical toe circle found by a 0.5 m grid search over centres; ten slices):

| Method | $F$ |
|---|---|
| Ordinary method (no interslice forces; reference only) | 1.136 |
| Bishop simplified | 1.202 |
| Spencer ($\theta$ = 34.2°) | 1.195 |
| Spencer moment equation with $\theta$ = 0 | 1.202 (= Bishop) |

The Spencer and Bishop values differ by under 1 %, the usual outcome for circular surfaces; the method choice matters
more for non-circular surfaces through weak layers. The search here covers toe circles only; a production search also
covers non-toe and non-circular surfaces.

## 2. Rock-mass strength: generalised Hoek–Brown

For rock masses the strength envelope is non-linear [4][6][7]:

$$
\sigma_1 = \sigma_3 + \sigma_{ci}\Big(m_b\,\frac{\sigma_3}{\sigma_{ci}} + s\Big)^{a}
$$

$$
m_b = m_i\,\exp\!\Big(\frac{GSI - 100}{28 - 14D}\Big), \qquad
s = \exp\!\Big(\frac{GSI - 100}{9 - 3D}\Big), \qquad
a = \frac12 + \frac16\Big(e^{-GSI/15} - e^{-20/3}\Big)
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $\sigma_1$, $\sigma_3$ | major and minor effective principal stresses at failure | MPa |
| $\sigma_{ci}$ | uniaxial compressive strength of the intact rock | MPa |
| $m_i$ | intact-rock material constant | – |
| $GSI$ | Geological Strength Index (0–100) | – |
| $D$ | disturbance factor for blast damage and stress relief, 0–1 | – |

The disturbance factor was introduced in the 2002 edition [5]. Guidance values for open pits (around 1.0 for large
production blasting, around 0.7 for mechanical excavation) are UNVERIFIED — pinned at specification.

**Worked example 2** (illustrative: $GSI$ = 50, $m_i$ = 10, $\sigma_{ci}$ = 50 MPa):

| $D$ | $m_b$ | $s$ | $a$ | $\sigma_1$ at $\sigma_3$ = 1 MPa (MPa) | uniaxial $\sigma_{ci}\,s^a$ (MPa) |
|---|---|---|---|---|---|
| 0 | 1.677 | 0.00387 | 0.506 | 10.49 | 3.01 |
| 0.7 | 0.641 | 0.00071 | 0.506 | 6.67 | 1.28 |
| 1.0 | 0.281 | 0.00024 | 0.506 | 4.72 | 0.74 |

Blast damage alone more than halves the confined strength in this example. Limit equilibrium needs $(c', \phi')$ on
each slice base, so Hoek–Brown is converted to equivalent Mohr–Coulomb parameters at the slice-base normal stress; the
conversion is standard practice and is fixed, with its equations, at specification.

## 3. Probability of failure by Monte Carlo

Treat uncertain inputs (strength, unit weight, water level) as random variables, sample them $N$ times and recompute
$F$ each time. The PoF and its standard error are binomial statistics (arithmetic):

$$
\widehat{PoF} = \frac1N\sum_{k=1}^{N}\mathbb{1}[F_k < 1], \qquad
SE = \sqrt{\frac{\widehat{PoF}\,(1 - \widehat{PoF})}{N}}, \qquad
N \approx \frac{1 - PoF}{PoF\,\varepsilon^2}
$$

where $\varepsilon$ is the target relative error. A 5 % PoF known to ±10 % needs about 1,900 samples.

**Worked example 3** (worked example 1 with $c' \sim \mathcal N(20, 4)$ kPa truncated at 0 and
$\phi' \sim \mathcal N(30°, 3°)$, independent, $N$ = 20,000, fixed seed, Bishop on the fixed critical surface):
mean $F$ = 1.204, standard deviation 0.126, $\widehat{PoF}$ = 5.2 % ± 0.16 % (one standard error). Two caveats: a fixed
surface underestimates PoF (each sample has its own critical surface), and correlated $c'$ and $\phi'$ change the
answer.

**Acceptance criteria.** Read and Stacey set FoS and PoF acceptance criteria by slope scale (bench, inter-ramp,
overall) and consequence of failure [8]. The commonly quoted values (bench FoS about 1.1, inter-ramp 1.15–1.3, overall
1.2–1.5, PoF 5–50 % depending on scale and consequence) are UNVERIFIED — pinned at specification, so PitStudio shows
them as configurable inputs, never as facts.

## 4. Slope monitoring radar

Ground-based synthetic-aperture radar interferometry (GB-InSAR) measures the displacement of the wall along the
radar's line of sight (LOS) from the phase change between repeated acquisitions [13][14]. For a displacement vector
$\mathbf u$ (mm) and a unit LOS vector $\hat{\mathbf e}$ from the radar to the pixel, and a two-way phase change
$\Delta\varphi$ (rad) at wavelength $\lambda$ (mm):

$$
d_{\text{LOS}} = \mathbf u\cdot\hat{\mathbf e}, \qquad d_{\text{LOS}} = -\frac{\lambda}{4\pi}\,\Delta\varphi
$$

(the second relation is the standard two-way interferometric conversion; its sign convention is pinned at
specification). Movement across the LOS is invisible, so radar placement matters. Claims of sub-millimetre accuracy
were seen only in a search snippet and are UNVERIFIED. The sensor side, including noise and atmospheric phase, is on
[RTX sensor physics](rtx-sensor-physics.md).

In open-pit practice the radar series feeds trigger action response plans. Dick et al. systematise TTF analysis on
slope-stability-radar data: a "percent deformation" pixel-selection method, filtering guidance, and inverse-velocity
and slope-gradient (SLO) methods tied to alarm levels [11].

## 5. Accelerating creep and inverse velocity

Voight's relation describes the terminal stage of failure under roughly constant stress and temperature, for rock and
soil [9]:

$$
\ddot\Omega = A\,\dot\Omega^{\alpha}
$$

with $\Omega$ a displacement (mm), $v = \dot\Omega$ its rate (mm/day) and $A$, $\alpha$ empirical constants. For
$\alpha > 1$, separate variables, $v^{-\alpha}\,dv = A\,dt$, integrate, and let $v \to \infty$ at the failure time
$t_f$:

$$
\frac1v = \big[A\,(\alpha - 1)\,(t_f - t)\big]^{1/(\alpha - 1)}
\quad\xrightarrow{\ \alpha = 2\ }\quad \frac1v = A\,(t_f - t)
$$

For $\alpha = 2$ the inverse velocity falls linearly to zero, and $t_f$ is the time-axis intercept of a straight-line
fit: Fukuzono's inverse-velocity method from large-scale landslide tests, whose curves may also be concave or convex
[10]. Rose and Hungr applied it to forecast rock-slope failures in open-pit mines [10]. Carlà et al. give guidelines on
smoothing and on automatic alarm thresholds [12].

![Inverse-velocity time-of-failure forecast](../assets/diagrams/inverse-velocity.svg)

*Synthetic observations over six days, the straight-line extrapolation, the synthetic truth and the Bayesian interval.*

**Worked example 4** (synthetic, by construction: $1/v = 0.01\,(10 - t)$ day/mm, so the true $t_f$ is 10 days; 10 %
multiplicative Gaussian noise, fixed seed; observations on days 0–6). Ordinary least squares gives
$1/v = 0.0997 - 0.01054\,t$ and $\hat t_f = 9.46$ days. At day 6 the remaining lead time is 4 days and the error is
0.54 days, 13.5 % of the lead: noise alone moves a forecast by more than the plan's 10 % target.

## 6. Bayesian time to failure

A Bayesian version keeps the uncertainty. With $y_i = 1/v_i$, design rows $\mathbf x_i = (1, t_i)$ and Gaussian noise of
variance $\sigma^2$, a Gaussian prior $\boldsymbol\beta \sim \mathcal N(\boldsymbol\mu_0, \Sigma_0)$ gives the
conjugate posterior

$$
\Sigma_N = \big(\Sigma_0^{-1} + X^{\top}X/\sigma^2\big)^{-1}, \qquad
\boldsymbol\mu_N = \Sigma_N\big(\Sigma_0^{-1}\boldsymbol\mu_0 + X^{\top}\mathbf y/\sigma^2\big)
$$

and the TTF distribution follows by sampling: draw $(\beta_0, \beta_1)$ from the posterior, keep draws with
$\beta_1 < 0$ (an accelerating wall), and set $t_f = -\beta_0/\beta_1$. The ratio makes the distribution skewed and
heavy-tailed, so PitStudio reports the median and an interval, not a mean. Each new reading updates the posterior,
which becomes the next prior. This is a standard construction; no fetched primary source specific to slope TTF was
found, so its citation is pinned at specification.

*Worked example 4, continued* (vague prior $\mathcal N(\mathbf 0, 10^2 I)$, $\sigma$ plugged in from the residuals,
0.0032 day/mm): posterior median $t_f$ = 9.45 days, 90 % interval 8.88–10.15 days. The interval covers the true 10
days even though the point estimate is early.

**Learned forecasters.** Sequence models can be trained on many synthetic Voight events and compared against inverse
velocity. A 2026 hybrid deep-learning study targets open-pit slope displacement and TTF [19] (method details
UNVERIFIED). Physics-informed neural networks are not used: a critical assessment shows that geotechnical PINNs fail
outside the sampled domain and cost far more than classical solvers [20].

## Assumptions and limits

- **2-D limit equilibrium.** Plane-strain sections, rigid sliding blocks, a single slip surface. Finite-element
  strength reduction [18] is not run in the browser.
- **Water.** The worked examples are dry; pore pressures enter through $u$ and must be specified, not guessed.
- **Strength conversion.** Hoek–Brown to Mohr–Coulomb per slice is an approximation; the conversion is fixed at
  specification.
- **Creep model.** Inverse velocity assumes the terminal, accelerating stage with $\alpha \approx 2$. Regressive
  movement, non-linear phases and noisy or badly chosen pixels break it [11][12].
- **One real event.** The open real series ([de Wit](../data-contract/dataset-cards/dewit-slope-failure.md),
  CC BY 4.0) is a single failure: it supports descriptive error, not significance tests or train/test claims.
- **Educational, not design or regulatory software.** FoS and PoF acceptance criteria are inputs; slope designs and
  evacuation decisions need site data and qualified engineers.

## In PitStudio

| Where | What | Lane |
|---|---|---|
| `minephys.geotech` | Hoek–Brown, LEM (Bishop, Spencer), Monte-Carlo PoF, inverse velocity, Bayesian TTF, GB-InSAR slope-radar LOS model | live (TypeScript port + Pyodide button) |
| [M13](../methods/m13-slope-stability-lem.md) | LEM + Hoek–Brown + PoF; Bishop cross-checked against pySlope 1.4.0 (MIT) [17] | live |
| [M14](../methods/m14-slope-forecasting.md) | inverse velocity + Bayesian TTF vs TCN, PatchTST and Chronos-Bolt | live (ONNX) |
| [M23](../methods/m23-rtx-sensor-simulation.md) | analytical slope-radar model: LOS projection of the creep field + noise matched to the real series | live |
| [Case C1](../cases/c1-slope-time-of-failure.md) | FoS, PoF, forecast error, lead time | — |

**Status: Not yet run** — produced in the data-and-models phase. Pre-registered acceptance (from the plan): on many
seeded synthetic Voight events, TTF error ≤ 10 % of the lead time at the observed signal-to-noise ratio, and "better
than inverse velocity" only if the paired 95 % confidence interval of the difference (pairs = seeded events) excludes
zero. On the real de Wit event (n = 1), the TTF error at the 50 % and 80 % record cut-offs is reported descriptively,
and the UI says "single real event — no significance test".

## References

1. Bishop (1955). The use of the slip circle in the stability analysis of slopes. *Géotechnique* 5(1), 7–17.
   https://doi.org/10.1680/geot.1955.5.1.7
2. Spencer (1967). A method of analysis of the stability of embankments assuming parallel inter-slice forces.
   *Géotechnique* 17(1), 11–26. https://doi.org/10.1680/geot.1967.17.1.11
3. Slope stability: the Spencer method of slices (educational page; slice equations and the Bishop–Janbu–Spencer
   comparison). https://www.geoengineer.org/education/slope-stability/slope-stability-the-spencer-method-of-slices
4. Hoek, Brown (2019). The Hoek–Brown failure criterion and GSI — 2018 edition. *J. Rock Mech. Geotech.
   Eng.* 11(3), 445–463. https://doi.org/10.1016/j.jrmge.2018.08.001
5. Hoek, Carranza-Torres, Corkum (2002). Hoek–Brown failure criterion — 2002 edition. *NARMS-TAC*.
   https://www.semanticscholar.org/paper/HOEK-BROWN-FAILURE-CRITERION-2002-EDITION-Hoek-Carranza-Torres/e44829e6d2c1484d25efe6be2db830e16c8f9d89
6. Itasca. Hoek–Brown constitutive model (generalised criterion with $m_b$, $s$, $a$).
   https://docs.itascacg.com/itasca900/common/models/hoek/doc/modelhoek.html
7. OpenGeoSys. Hoek–Brown yield criterion benchmark.
   https://www.opengeosys.org/6.5.6/docs/benchmarks/small-deformations/hoekbrownyieldcriterion/
8. Read, Stacey (2009). *Guidelines for Open Pit Slope Design.* CSIRO Publishing.
   https://ebooks.publish.csiro.au/content/guidelines-open-pit-slope-design
9. Voight (1989). A relation to describe rate-dependent material failure. *Science* 243(4888), 200–203.
   https://doi.org/10.1126/science.243.4888.200
10. Rose, Hungr (2007). Forecasting potential rock slope failure in open pit mines using the
    inverse-velocity method. *Int. J. Rock Mech. Min. Sci.* 44(2), 308–320 (cites Fukuzono 1985, Proc. 4th Int.
    Conf. and Field Workshop on Landslides, Tokyo). https://doi.org/10.1016/j.ijrmms.2006.07.014
11. Dick, Eberhardt, Cabrejo-Liévano, Stead, Rose (2015). Development of an early-warning
    time-of-failure analysis methodology for open-pit mine slopes utilizing ground-based slope stability radar
    monitoring data. *Can. Geotech. J.* 52(4), 515–529. https://doi.org/10.1139/cgj-2014-0028
12. Carlà, Intrieri, Di Traglia, Nolesini, et al. (2017). Guidelines on the use of inverse velocity
    method as a tool for setting alarm thresholds and forecasting landslides and structure collapses. *Landslides*
    14(2), 517–534. https://doi.org/10.1007/s10346-016-0731-5
13. Monserrat, Crosetto, Luzi (2014). A review of ground-based SAR interferometry for deformation
    measurement. *ISPRS J. Photogramm. Remote Sens.* 93, 40–48. https://doi.org/10.1016/j.isprsjprs.2014.04.001
14. Le Roux, Sepehri, Khaksar, Murray (2025). Slope stability monitoring methods and technologies for
    open-pit mining: a systematic review. *Mining* 5(2), 32. https://doi.org/10.3390/mining5020032
15. High Country News (2013). How technology detected a huge mine landslide before it happened.
    https://www.hcn.org/issues/45-8/how-technology-detected-a-huge-mine-landslide-before-it-happened/
16. International Council on Mining and Metals (2025). 2024 safety performance.
    https://www.icmm.com/en-gb/news/2025/2024-safety-performance
17. pySlope 1.4.0 (MIT), Python Package Index. https://pypi.org/project/pyslope/
18. Griffiths, Lane (1999). Slope stability analysis by finite elements. *Géotechnique* 49(3), 387–403.
    https://doi.org/10.1680/geot.1999.49.3.387
19. Wang et al. (2026). *Bull. Eng. Geol. Environ.* 85(7): hybrid deep-learning model for open-pit slope
    displacement and time to failure (Crossref record; method details UNVERIFIED). https://doi.org/10.1007/s10064-026-05048-1
20. Kumar (2025). A critical assessment of PINNs and operator learning for geotechnical engineering.
    arXiv:2512.24365. https://arxiv.org/abs/2512.24365
