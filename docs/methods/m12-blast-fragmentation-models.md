# M12 — Blast models: Kuz-Ram/KCO + Swebrec, PPV and flyrock

> Closed-form blast engineering: from burden, spacing, hole and explosive to median fragment size and a Swebrec size
> curve, ground vibration at a receiver and a drag-free flyrock bound — live in the browser with cited, checkable
> equations. · Part of: [Methods](README.md) · Related: [Drill and blast theory](../theory/drill-and-blast.md) ·
> [M11 fragmentation](m11-fragmentation-segmentation.md) · [M17 mine-to-mill](m17-comminution-mine-to-mill.md) ·
> [Case D1](../cases/d1-blast-muck-pile.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical | no | live | [D1](../cases/d1-blast-muck-pile.md), [D2](../cases/d2-mine-to-mill.md) | `minephys.blasting` (Apache-2.0) + TypeScript port | not yet implemented |

## What and why

Blast design trades explosive cost against fragmentation (oversize and fines), ground vibration, airblast and flyrock.
Flyrock and blast-area security account for more than two thirds of surface-blasting injuries in 1978–2002 [10], and
fragmentation drives every downstream step to the mill. The classical empirical models are the engineer's first tool:

- **Kuz-Ram** predicts the median fragment size from rock, explosive and powder factor, with a Rosin–Rammler curve
  [1][2];
- **KCO** replaces Rosin–Rammler, which under-predicts fines, with the three-parameter **Swebrec** function, which fits
  sieved blast and crusher data over two to three orders of magnitude of size [4][5];
- **PPV** (peak particle velocity) at a receiver follows a square-root scaled-distance law with site constants, and US
  regulation fixes limits and scaled-distance factors [7][8];
- **flyrock** range is best treated as a ballistic trajectory with drag driven by launch velocity, not by correlation
  models [9].

M12 makes these live and inspectable, provides the PSD that [M11](m11-fragmentation-segmentation.md) measures from
images and that [M17](m17-comminution-mine-to-mill.md) feeds to the mill, and labels every empirical constant with its
verification status.

## The algorithm

### Design quantities

$$
q = \frac{Q_{\text{hole}}}{B\,S\,H}, \qquad Q_{\text{hole}} = \rho_e\,\frac{\pi}{4}\,d^2\,L_c
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $q$ | powder factor (also $K$ below) | kg/m³ |
| $Q_{\text{hole}}$ | explosive mass per hole | kg |
| $B$, $S$, $H$ | burden, spacing, bench height | m |
| $\rho_e$ | explosive density | kg/m³ |
| $d$, $L_c$ | hole diameter, charge length | m |

### Kuznetsov median size and Rosin–Rammler (Kuz-Ram)

$$
x_{50} = A\,K^{-0.8}\,Q^{1/6}\left(\frac{115}{RWS}\right)^{19/30} \quad [\text{cm}]
$$

with $A$ the rock factor (–), $K$ the powder factor (kg/m³), $Q$ the charge per hole (kg) and $RWS$ the weight
strength relative to ANFO (= 100) [1][3]†. The rock factor is built from blastability-index terms (rock-mass
description, joint factor, density influence) [3]; its scaling constant is UNVERIFIED — pinned at specification.

The Kuz-Ram size curve is Rosin–Rammler in Cunningham's form, with $\ln 2 = 0.693$ making $x_{50}$ the median†:

$$
R(x) = \exp\!\left[-0.693\left(\frac{x}{x_{50}}\right)^{n}\right], \qquad P(x) = 1 - R(x)
$$

where $R$ is the fraction retained and $n$ the uniformity index, computed from Cunningham's relation in $B/d$,
$S/B$, drilling deviation, charge lengths and bench height [2]†:

$$
n = \left(2.2 - 14\frac{B}{d}\right)\sqrt{\frac{1 + S/B}{2}}\left(1 - \frac{W}{B}\right)
\left(\frac{\lvert BCL - CCL\rvert}{L} + 0.1\right)^{0.1}\frac{L}{H}
$$

with $W$ the drilling-accuracy standard deviation (m), $BCL$ and $CCL$ the bottom and column charge lengths (m) and $L$
the total charge length (m). Typical ranges of $n$ quoted in the literature are UNVERIFIED — pinned at specification.

### KCO: Swebrec

$$
P(x) = \frac{1}{1 + \left[\dfrac{\ln(x_{\max}/x)}{\ln(x_{\max}/x_{50})}\right]^{b}}, \qquad 0 < x \le x_{\max}
$$

In KCO, $x_{50}$ comes from Kuznetsov, $x_{\max}$ is bounded by the in-situ block size or by burden and spacing, and
the undulation $b$ is linked to the Kuz-Ram $n$ [4][5]; the exact $b(n)$ relation is UNVERIFIED — pinned at
specification. The Swebrec form itself is verified [5][6].

### Ground vibration and regulatory limits

$$
PPV = K_s\left(\frac{D}{\sqrt{W}}\right)^{-\beta}
$$

with $D$ the distance to the receiver, $W$ the maximum charge per delay, and $K_s$, $\beta$ site constants fitted by
regression (no generic values are claimed). Two regulatory anchors:

- The USBM study RI 8507 measured responses in 76 homes over 219 production blasts and gives safe levels of 0.5–2.0
  in/s PPV depending on frequency, low frequencies being most damaging [7].
- US rule 30 CFR 816.67 limits PPV to 1.25 in/s at 0–300 ft, 1.00 in/s at 301–5,000 ft and 0.75 in/s beyond
  5,001 ft, with scaled-distance factors $D_s$ = 50, 55 and 65 and the charge rule $W = (D/D_s)^2$ in lb per 8 ms
  delay; airblast limits are 134/133/129 dB peak at 0.1/2/6 Hz (or 105 dBC); flyrock must stay within half the
  distance to the nearest dwelling and inside the permit or control-area boundary [8].

### Flyrock

$$
m\,\dot{\mathbf v} = -m g\,\hat{\mathbf z} - \tfrac12\rho_a C_D A_f\,\lvert\mathbf v\rvert\,\mathbf v,
\qquad R_{\text{vac}} = \frac{v_0^{2}\sin 2\theta_0}{g}
$$

The trajectory with drag is integrated numerically from a launch velocity $v_0$ (m/s) and angle $\theta_0$; $\rho_a$ is
air density (kg/m³), $C_D$ the drag coefficient and $A_f$ the fragment's frontal area (m²). The drag-free range
$R_{\text{vac}}$ is an upper bound [9].

### Worked example (illustrative inputs)

Burden 5 m, spacing 6 m, bench 12 m, hole 0.25 m with 8 m of charge at 850 kg/m³ (ANFO-like, $RWS = 100$), rock factor
$A = 7$:

- $Q_{\text{hole}} = 850 \times \frac{\pi}{4} \times 0.25^2 \times 8 = 333.8$ kg; volume per hole
  $5 \times 6 \times 12 = 360$ m³; powder factor $q = 0.927$ kg/m³.
- $x_{50} = 7 \times 0.927^{-0.8} \times 333.8^{1/6} \times 1.15^{19/30}$
  $= 7 \times 1.0625 \times 2.6338 \times 1.0926 = 21.4$ cm.
- **Vibration (US rule):** one hole per delay is $W = 333.8$ kg $= 735.9$ lb. At 1,000 ft ($D_s = 55$) the rule allows
  $(1000/55)^2 = 330.6$ lb per delay, so this design needs at least $D = 55\sqrt{735.9} = 1{,}492$ ft (455 m) to the
  nearest structure — or fewer kilograms per delay.
- **Flyrock bound:** a fragment launched at 30 m/s and 45° cannot travel more than $30^2/9.81 = 91.7$ m in vacuum; with
  drag it travels less.

## Baseline and comparison

M12 is the classical reference itself:

- its Swebrec PSD is the "predicted" curve that [M11](m11-fragmentation-segmentation.md) compares with the curve
  measured from images;
- in case D1, design scenarios (burden, spacing, explosive) are contrasted side by side on P80, % oversize, PPV and
  flyrock radius; no stochastic "better" claim is made.

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)):

- worked examples from the primary sources for every function (the transcriptions marked † and every UNVERIFIED
  constant are pinned before they become spec constants);
- at least three metamorphic relations, for example: a larger burden gives a coarser $x_{50}$; a higher powder factor
  gives a finer $x_{50}$; PPV falls monotonically with distance; doubling the charge per delay never lowers PPV;
  $P(x_{50}) = 0.5$ for both size curves;
- unit-safe code (US customary units in the regulatory functions, SI elsewhere), and TypeScript parity in the exact
  class on golden vectors.

**Results: Not yet run** — produced in the data-and-models phase. Reported: D1 design tables and curves.

## Lane and web delivery

**Live.** All functions are closed form; analytical models stay under 50 KB of JavaScript and 1–50 ms per evaluation
(estimates; [compute lanes](../pipelines/compute-lanes.md)). Fallback: baked grids. The Pyodide button runs the same
`minephys.blasting` functions as a reference check.

## Assumptions and limits

- Kuz-Ram/KCO, PPV laws and flyrock correlations are **empirical regressions**: site constants and rock factors vary
  by site, and extrapolation outside the calibration range is unsafe.
- Rosin–Rammler under-predicts fines; Swebrec is preferred but still empirical.
- Regulatory values are US federal surface-coal rules, shown as an example, not as advice for any jurisdiction.
- **Educational, not design or regulatory software.** Blast designs from this page must not be used in the field.

## In PitStudio

- **Cases:** [D1](../cases/d1-blast-muck-pile.md) (P80, % oversize, PPV, flyrock radius),
  [D2](../cases/d2-mine-to-mill.md) (PSD into the mill).
- **Code (planned):** `minephys.blasting` (Kuz-Ram, KCO, Swebrec, PPV, flyrock) with cited parameter tables in
  `minephys/knowledge/`; TypeScript port in a `web/` worker.
- **Status:** not yet implemented — built test-first in the build phase.

† Standard form; the transcription is checked against the primary source by a worked-example test at specification.

## References

1. Kuznetsov, V. M. (1973). The mean diameter of the fragments formed by blasting rock. Soviet Mining Science
   9:144–148. https://doi.org/10.1007/BF02506177
2. Cunningham, C. V. B. (2005). The Kuz-Ram fragmentation model — 20 years on. EFEE, Brighton, 201–210.
   https://www.scirp.org/reference/referencespapers?referenceid=4120306
3. Mutinda et al. (2021). Prediction of rock fragmentation using the KCO model. JSAIMM 121(3).
   https://doi.org/10.17159/2411-9717/1401/2021
4. Ouchterlony, F. & Sanchidrián, J. A. (2019). A review of development of better prediction equations for blast
   fragmentation. JRMGE 11(5):1094–1109 (CC BY-NC-ND). https://doi.org/10.1016/j.jrmge.2019.03.001
5. Ouchterlony, F. (2005). The Swebrec function: linking fragmentation by blasting and crushing. Mining Technology
   114(1):29–44. https://doi.org/10.1179/037178405X44539
6. Rock fragmentation model calculator (secondary; Kuznetsov 19/30 exponent and Swebrec forms).
   https://ilyfei.com/fragments/
7. Siskind, D. E., Stagg, M. S., Kopp, J. W. & Dowding, C. H. (1980). USBM RI 8507.
   https://www.osti.gov/biblio/6777883
8. 30 CFR § 816.67 — Use of explosives: control of adverse effects. https://www.law.cornell.edu/cfr/text/30/816.67
9. Szendrei, T. & Tose, S. (2023). Flyrock in surface mining — limitations of predictive models. JSAIMM
   122(12):725–732 (CC BY). https://doi.org/10.17159/2411-9717/1873/2022
10. Bajpayee, T. S., Lobb, T. E. & Verakis, H. C. (2004). An analysis and prevention of flyrock accidents in surface
    blasting operations (NIOSH). https://stacks.cdc.gov/view/cdc/220760
