# Drill and blast

> Fragmentation from blast design (Kuz-Ram, KCO and the Swebrec function), powder factor, ground vibration by scaled
> distance and flyrock range, with every symbol and its validity range. · Part of: [Theory](README.md) · Related:
> [Comminution](comminution.md), [Loading and terramechanics](loading-and-terramechanics.md),
> [M12 blast fragmentation models](../methods/m12-blast-fragmentation-models.md), [Case D1](../cases/d1-blast-muck-pile.md)

## What and why

A blast design trades explosive cost against what the blast does downstream: the size distribution of the broken
rock (oversize that stalls loaders and crushers, fines that feed the mill), ground vibration at neighbours, flyrock and
the shape of the muck pile. The prediction equations used in practice are empirical regressions that have been
refined for decades [6]. The safety stakes are concrete: flyrock and lack of blast-area security caused more than
two-thirds of all blasting-related injuries in US surface coal, metal and nonmetal mines over 1978–2002 [10].

Fragmentation is the start of the mine-to-mill chain: it sets the loader fill factor
([Loading and terramechanics](loading-and-terramechanics.md)) and the feed of the crusher and mills
([Comminution](comminution.md)).

![Blast fragmentation chain](../assets/diagrams/blast-fragmentation-chain.svg)

*Inputs → Kuz-Ram mean size → uniformity → Swebrec passing curve → P80, oversize and fines; the same inputs drive the
vibration and flyrock models. Numbers are the illustrative worked example of this page.*

## 1. Design quantities

$$
Q = \rho_e\,\frac{\pi}{4}\,d^2\,L_c, \qquad K = \frac{Q}{B\,S\,H}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $Q$ | explosive charge per hole | kg |
| $\rho_e$ | explosive density | kg/m³ |
| $d$ | hole diameter | m (mm in the uniformity formula) |
| $L_c$ | charge length | m |
| $B$, $S$, $H$ | burden, spacing, bench height | m |
| $K$ | powder factor (specific charge) | kg/m³ |

*Worked example 1* (illustrative: $\rho_e$ = 850 kg/m³, $d$ = 250 mm, $L_c$ = 7.2 m, $B$ = 6 m, $S$ = 7 m, $H$ = 12 m):
$Q = 850 \times 0.0491 \times 7.2 = 300$ kg per hole, the rock volume per hole is 504 m³ and $K = 0.596$ kg/m³. The
convention here divides by the bench volume (subdrill excluded); every PitStudio output states which convention it
uses.

## 2. Kuz-Ram

**Mean fragment size (Kuznetsov).** The median size of the muck pile follows [1], in the form shown in [4][5]:

$$
x_{50} = A\,K^{-0.8}\,Q^{1/6}\left(\frac{115}{RWS}\right)^{19/30}
$$

with $x_{50}$ in **cm**, $K$ in kg/m³, $Q$ in kg, $RWS$ the weight strength of the explosive relative to ANFO (ANFO =
100) and $A$ the rock factor (–). The rock factor is built from rock-mass description, joint, density and hardness
ratings, $A = 0.06\,(RMD + JF + RDI + HF)$ in Cunningham's adaptation of Lilly's blastability index; the 0.06 and the
$HF$ term are UNVERIFIED — pinned at specification, while a fetched open-access paper lists $A$ from $RMD$, $JF$ and
$RDI$ [4].

**Which version.** Two explosive-strength exponents circulate.

| Version | Exponent of $115/RWS$ | Used here? |
|---|---|---|
| Kuznetsov (1973) [1], Cunningham (1983/1987) | 19/30 | **default** (this page's worked example) |
| Cunningham (2005) "20 years on" [2] | 19/20 | option |

- For $RWS = 100$ (ANFO), $(115/100)^{19/30} = 1.093$ while $(115/100)^{19/20} = 1.142$, so the two $x_{50}$ differ by
  about 4.5 %. The gap grows as $RWS$ moves away from 115.
- Reviews of the Kuz-Ram/KCO family discuss these revisions [6][11].
- The `minephys` blasting module implements the 1983/1987 form by default and the 2005 exponent as a named option.
- The choice and its source pages are pinned in the blasting specification.

**Size distribution (Rosin–Rammler, Cunningham form).** Retained fraction $R(x)$ and passing fraction $P(x)$:

$$
R(x) = \exp\!\Big[-\ln 2\,\Big(\frac{x}{x_{50}}\Big)^{n}\Big], \qquad P(x) = 1 - R(x)
$$

The $\ln 2 = 0.693$ makes $x_{50}$ the median; a variant without it circulates [5] (transcription UNVERIFIED — pinned
at specification). Inverting gives any percentile (arithmetic):
$x_P = x_{50}\,\big[\ln\tfrac{1}{1-P} / \ln 2\big]^{1/n}$, so $x_{80} = x_{50}\,(\ln 5/\ln 2)^{1/n}$.

**Uniformity index (Cunningham 1987).** In the standard form

$$
n = \Big(2.2 - 14\,\frac{B}{d}\Big)\sqrt{\frac{1 + S/B}{2}}\;\Big(1 - \frac{W}{B}\Big)\Big(\frac{\lvert BCL - CCL\rvert}{L} + 0.1\Big)^{0.1}\,\frac{L}{H}
$$

with $W$ the standard deviation of drilling accuracy (m), $BCL$ and $CCL$ the bottom and column charge lengths (m), $L$
the total charge length (m), $B$, $S$, $L$, $H$, $W$ in metres and $d$ in millimetres. The parameter list and a typical
range $n \approx 0.8$–1.5 are associated with this equation in the literature, but the exact transcription (including
the units) is UNVERIFIED — pinned at specification [2][6]. Cunningham's 2005 update adds terms for delay-timing
scatter and blastability [2].

*Worked example 1, continued:* with an illustrative rock factor $A = 7$ and $RWS = 100$,
$x_{50} = 7 \times 0.596^{-0.8} \times 300^{1/6} \times 1.15^{19/30} = 29.9$ cm. With an illustrative drilling
deviation $W$ = 0.3 m and a single column charge ($BCL = L$, $CCL = 0$), the transcribed formula gives $n \approx 1.12$.

**Limitation.** The Rosin–Rammler form under-predicts fines, which matter for mill throughput and dust. That is why
the Swebrec function replaced it in the KCO model.

## 3. The Swebrec function and the KCO model

Ouchterlony's Swebrec function has three parameters [3]:

$$
P(x) = \frac{1}{1 + \left[\dfrac{\ln(x_{\max}/x)}{\ln(x_{\max}/x_{50})}\right]^{b}}, \qquad 0 < x \le x_{\max}
$$

with $x_{\max}$ the largest fragment (m), limited by the in-situ block size or by the burden and spacing, and $b$ the
undulation exponent (–). It is reported to fit hundreds of sieved blast and crusher datasets with $r^2 > 0.995$ over
two to three orders of magnitude of size (UNVERIFIED — pinned at specification) [3]. In the
Kuznetsov–Cunningham–Ouchterlony (KCO) model, $x_{50}$ comes from Kuznetsov and $b$ from the Kuz-Ram uniformity [4][6].

**Linking b to n.** Requiring the Swebrec and Rosin–Rammler curves to have the same slope in log-size at the median
gives a closed form (derived here):

$$
\left.\frac{dP_{RR}}{d\ln x}\right|_{x_{50}} = \frac{n\ln 2}{2}, \quad
\left.\frac{dP_{Sw}}{d\ln x}\right|_{x_{50}} = \frac{b}{4\ln(x_{\max}/x_{50})}
\quad\Rightarrow\quad b = 2\ln 2\;\ln\!\Big(\frac{x_{\max}}{x_{50}}\Big)\,n
$$

The published KCO relation is pinned against [3] at specification. **Percentiles** invert in closed form
(arithmetic): $x_P = x_{\max}\,(x_{50}/x_{\max})^{u_P}$ with $u_P = \big((1-P)/P\big)^{1/b}$; for $P = 0.8$,
$u = 0.25^{1/b}$.

*Worked example 1, continued* (illustrative $x_{\max}$ = 1.5 m): $\ln(1.5/0.299) = 1.611$, so
$b = 2 \times 0.693 \times 1.611 \times 1.12 = 2.49$.

| Output | Swebrec ($b$ = 2.49) | Rosin–Rammler ($n$ = 1.12) |
|---|---|---|
| $x_{50}$ (m) | 0.299 | 0.299 |
| $x_{80}$ (m) | 0.595 | 0.637 |
| Oversize > 1 m (%) | 3.1 | 7.0 |
| Fines < 5 cm (%) | 13.4 | 9.0 |

The two curves agree at the median and differ in both tails: Swebrec puts more mass in the fines and less in the
oversize. The step beyond KCO is crush-zone fines modelling and the xP-frag family of prediction equations reviewed by
Ouchterlony and Sanchidrián [6].

## 4. Ground vibration: peak particle velocity

The site attenuation law in square-root scaled distance is

$$
PPV = K_s\left(\frac{D}{\sqrt{W}}\right)^{-\beta}
$$

with $PPV$ the peak particle velocity (mm/s), $D$ the distance from the blast (m), $W$ the maximum charge per delay
(kg) and $K_s$, $\beta$ site constants fitted by regression to monitored blasts. Typical constant ranges are UNVERIFIED
and are never defaults: every site fits its own.

Thresholds come from two primary sources:

- **USBM RI 8507** measured the response of 76 homes over 219 production blasts. Safe levels range from 0.5 to
  2.0 in/s (12.7–50.8 mm/s) depending on frequency and construction; low frequencies are the most damaging [7].
- **30 CFR § 816.67** (US surface coal mining) caps PPV at 1.25 in/s up to 300 ft, 1.00 in/s at 301–5,000 ft and
  0.75 in/s beyond 5,001 ft. The equivalent scaled-distance rule uses factors $D_s$ = 50, 55 and 65 with
  $W = (D/D_s)^2$ in lb per 8 ms delay. Airblast is capped at 134, 133 and 129 dB peak (0.1, 2 and 6 Hz systems) or
  105 dBC. Flyrock must not travel beyond half the distance to the nearest dwelling or beyond the permit or
  control-area boundary [8].

*Worked example 2.* At 1,000 ft (304.8 m) the regulation's factor is $D_s = 55$, so the charge per 8 ms delay may not
exceed $(1000/55)^2 = 331$ lb (150 kg). With an **illustrative** site law $K_s$ = 1,000 mm/s, $\beta$ = 1.6, the same
150 kg at 300 m gives $D/\sqrt{W} = 24.5$ m/kg^½ and $PPV = 1000 \times 24.5^{-1.6} = 6.0$ mm/s (0.24 in/s), below the
lowest RI 8507 level. The regulatory and the site-law calculations answer different questions: the first is a legal
limit, the second is a prediction that is only as good as the site regression.

## 5. Flyrock

Empirical flyrock-range correlations (Lundborg; Richards and Moore) are not transcribed here (UNVERIFIED). A 2023
open-access review shows that correlation models cannot capture the launch velocity and that trajectory models often
ignore aerodynamic drag; it argues that ballistic trajectories with drag, driven by launch velocity, are the most
promising predictor [9]:

$$
m\,\dot{\mathbf v} = -m\,g\,\hat{\mathbf z} - \tfrac12\,\rho_a\,C_D\,A\,\lvert\mathbf v\rvert\,\mathbf v, \qquad
R_{\text{vac}} = \frac{v_0^2\,\sin 2\theta_0}{g}
$$

with $m$ the fragment mass (kg), $A$ its frontal area (m²), $C_D$ its drag coefficient (–), $\rho_a$ the air density
(kg/m³), $v_0$ and $\theta_0$ the launch speed (m/s) and angle (rad). The drag-free range $R_{\text{vac}}$ is an upper
bound for a given launch.

*Worked example 3* (illustrative: $v_0$ = 40 m/s at 45°, spheres of rock density 2,650 kg/m³, $C_D$ = 0.47,
$\rho_a$ = 1.2 kg/m³, launch and landing at the same level, time step 0.1 ms):

| Fragment diameter (m) | 0.05 | 0.1 | 0.2 | 0.5 | drag-free |
|---|---|---|---|---|---|
| Range (m) | 118 | 136 | 148 | 157 | 163 |

Small fragments lose most range to drag; large ones approach the drag-free bound. The open problem is the launch
velocity itself, which depends on burden, stemming and the face condition, and which no empirical correlation
captures [9].

## 6. Validity ranges

| Model | Valid where | Status |
|---|---|---|
| Kuznetsov $x_{50}$ | within the calibration of the rock factor $A$; $RWS$ relative to ANFO | form fetched [4][5]; $A$ constants UNVERIFIED |
| Cunningham $n$ | typical $n \approx 0.8$–1.5; burden, spacing and accuracy terms in their tested ranges | transcription UNVERIFIED |
| Swebrec / KCO | sieved blast and crusher data, $0 < x \le x_{\max}$ | form fetched [3][4]; fit-quality claim UNVERIFIED |
| PPV law | distances and charges inside the site's regression data | site constants only |
| RI 8507 levels | residential structures; frequency-dependent | fetched [7] |
| 30 CFR § 816.67 | US surface coal regulation; legal limits, not physics | fetched [8] |
| Drag ballistics | needs the launch velocity; sphere drag, no tumbling | fetched [9] |

## Assumptions and limits

- **Regressions, not mechanics.** Kuz-Ram, KCO and the PPV law are empirical. They extrapolate badly outside their
  calibration, and the rock factor and site constants vary by site.
- **No rock-fracture simulation.** Blast-scale fracture mechanics is out of scope for real-time GPU physics; visual
  destruction toolkits are not calibrated rock fragmentation and are used, if at all, only for visuals.
- **Illustrative numbers.** Every worked example uses teaching inputs, labelled as such.
- **Educational, not design software.** Blast designs, vibration limits and exclusion zones need site monitoring and a
  qualified blaster; PitStudio's outputs carry their validity ranges and are not for regulatory use.

## In PitStudio

| Where | What | Lane |
|---|---|---|
| `minephys.blasting` | Kuz-Ram, KCO, Swebrec, PPV, flyrock | live (TypeScript port + Pyodide button) |
| [M12](../methods/m12-blast-fragmentation-models.md) | the analytical chain of this page | live |
| [M11](../methods/m11-fragmentation-segmentation.md) | image fragmentation: watershed + Swebrec fit vs a U-Net trained on synthetic muck piles with exact PSD | live (int8 U-Net) |
| [M7](../methods/m07-gpu-granular-physics.md) | Warp DEM muck-pile throw | replay |
| [Case D1](../cases/d1-blast-muck-pile.md) | P80, % oversize, PPV, flyrock radius, measured sim-to-real | — |
| [Case D2](../cases/d2-mine-to-mill.md) | feeds the comminution chain | — |

The real images for D1 are the CC BY 4.0 rock-fragment dataset
([card](../data-contract/dataset-cards/mendeley-rock-fragments.md)): 960 labelled 512 × 512 images that are 240
originals × 4 flips or rotations, single class, with no physical scale. PSD comparisons on that data are in pixels or
relative (for example $x_{80}/x_{50}$ and curve shape); any conversion to metres states its scale assumption.

**Status: Not yet run** — produced in the data-and-models phase. Pre-registered acceptance (from the plan): synthetic
held-out $x_{50}$ relative error ≤ 15 %; on the real test split, train-synthetic-test-real ≥ 0.90 × train-real-test-real
(IoU); "the U-Net beats watershed + Swebrec" only if the paired 95 % confidence interval of the difference in $x_{50}$
error excludes 0. See [Sim-to-real](sim-to-real.md).

## References

1. Kuznetsov (1973). The mean diameter of the fragments formed by blasting rock. *Soviet Mining Science* 9(2),
   144–148. https://doi.org/10.1007/BF02506177
2. Cunningham (2005). The Kuz-Ram fragmentation model — 20 years on. *Proc. EFEE Brighton*, 201–210.
   https://www.scirp.org/reference/referencespapers?referenceid=4120306 (bibliographic record; full text UNVERIFIED —
   source unreachable)
3. Ouchterlony (2005). The Swebrec function: linking fragmentation by blasting and crushing. *Mining Technology*
   114(1), 29–44. https://doi.org/10.1179/037178405X44539
4. Mutinda, Alunda, Maina, Kasomo (2021). Prediction of rock fragmentation using the
   Kuznetsov–Cunningham–Ouchterlony model. *J. South. Afr. Inst. Min. Metall.* 121(3), 107–112.
   https://doi.org/10.17159/2411-9717/1401/2021
5. Rock fragmentation model calculator (secondary source for the Kuznetsov 19/30 form). https://ilyfei.com/fragments/
6. Ouchterlony, Sanchidrián (2019). A review of development of better prediction equations for blast
   fragmentation. *J. Rock Mech. Geotech. Eng.* 11(5), 1094–1109. https://doi.org/10.1016/j.jrmge.2019.03.001
7. Siskind, Stagg, Kopp, Dowding (1980). *USBM Report of Investigations 8507*: structure response to
   surface-mine blast vibration (76 homes, 219 blasts). https://www.osti.gov/biblio/6777883
8. 30 CFR § 816.67 — Use of explosives: control of adverse effects. https://www.law.cornell.edu/cfr/text/30/816.67
9. Szendrei, Tose (2023). Flyrock in surface mining — limitations of current predictive models and a better
   alternative through modelling the aerodynamics of flyrock trajectory. *J. South. Afr. Inst. Min. Metall.* 122(12),
   725–732. https://doi.org/10.17159/2411-9717/1873/2022
10. Bajpayee, Lobb, Verakis (2004). *An analysis and prevention of flyrock accidents in surface
    blasting operations.* NIOSH. https://stacks.cdc.gov/view/cdc/220760
11. Sanchidrián, Ouchterlony (2017). A distribution-free description of fragmentation by blasting based on
    dimensional analysis. *Rock Mechanics and Rock Engineering* 50, 781–806. https://doi.org/10.1007/s00603-016-1131-9
