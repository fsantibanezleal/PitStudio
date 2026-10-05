# Comminution

> Size reduction from the muck pile to the flotation feed: Bond's law, the Morrell SMC model, population-balance
> grinding, Klimpel flotation kinetics and the mine-to-mill link to fragmentation. · Part of: [Theory](README.md) ·
> Related: [Drill and blast](drill-and-blast.md), [M17 comminution and mine-to-mill](../methods/m17-comminution-mine-to-mill.md),
> [Case D2](../cases/d2-mine-to-mill.md), [Mine-to-mill meta-model](../models/mine-to-mill-meta-model.md)

## What and why

Comminution is where most of a mine's energy and much of its cost goes. Grinding is about 40 % of mining energy
(diesel materials handling about 17 %) [10]. In a 2025 costing study of an open-pit copper operation, milling was
6.18 USD/t, 59.1 % of total operating cost, and crushing 1.15 USD/t, 11 % [9]. Haulage is the main cost lever inside
the pit ([Haulage](haulage.md)); comminution is the main lever across the whole mine-to-mill chain.

The chain starts in the pit. Blasting decides the feed size distribution, and fragmentation changes the energy split
between explosives and mills. A 1998 mine-to-mill study linked blast design to SAG-mill throughput [11]. A 2026 study
trained random-forest meta-models on more than three million simulator scenarios (over 90 % predictive accuracy) and
found that finer fragmentation lowers total comminution cost despite the higher explosive cost [8].

![Comminution circuit with its energy models and the mine-to-mill link](../assets/diagrams/comminution-circuit.svg)

*The muck-pile size distribution feeds a crusher, a SAG mill, a ball mill closed by a cyclone and flotation; each
stage carries its energy or recovery model, and the worked example shows that blasting acts mainly through fines.*

## 1. Bond's law

Bond's third theory makes the specific energy proportional to the new crack length, which scales as the inverse square
root of particle size [1]:

$$
W = 10\,W_i\left(\frac{1}{\sqrt{P_{80}}} - \frac{1}{\sqrt{F_{80}}}\right)
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $W$ | specific grinding energy | kWh/t |
| $W_i$ | Bond work index of the ore | kWh/t |
| $F_{80}$, $P_{80}$ | 80 % passing size of feed and product | µm |

The factor 10 is the definition of $W_i$: it is the energy that reduces the ore from an infinitely large feed to
$P_{80} = 100$ µm, because $10/\sqrt{100} = 1$ (arithmetic). Mill power is $P = W\,\dot m$, times efficiency and
correction factors that are pinned at specification. Typical work indices of about 7–25 kWh/t are UNVERIFIED and are
never defaults.

*Worked example 1* (illustrative: $W_i$ = 15 kWh/t, $F_{80}$ = 2,000 µm, $P_{80}$ = 150 µm):
$W = 150 \times (0.0816 - 0.0224) = 8.89$ kWh/t, so a 1,000 t/h circuit needs about 8.9 MW before correction factors.
With $F_{80}$ = 1,500 µm the energy falls to 8.37 kWh/t; with 3,000 µm it rises to 9.51 kWh/t.

## 2. The Morrell SMC model

Morrell's alternative energy–size relation lets the exponent vary with size, and applies to whole circuits (SAG,
HPGR, ball mills) through material indices from the SMC test [2]:

$$
W_i = M_i \cdot 4\,\big(x_2^{\,f(x_2)} - x_1^{\,f(x_1)}\big), \qquad f(x) = -\Big(0.295 + \frac{x}{10^6}\Big)
$$

with $x_1$ and $x_2$ the 80 % passing sizes of feed and product (µm) and $M_i$ (kWh/t) the index for the relevant
circuit section. The constants 4 and 0.295 and the $10^6$ scale are UNVERIFIED — pinned at specification. At 2,000 µm
the exponent is about −0.297, much shallower than Bond's fixed −0.5, which is the point of the model.

*Illustrative:* $M_i$ = 20 kWh/t over the same sizes gives 9.86 kWh/t. This number is not comparable with worked
example 1: $M_i$ and $W_i$ are different indices measured by different tests.

## 3. Population balance model

Grinding is a rate process [3]. Split the size range into classes $i = 1 \dots n$ from coarse to fine, with mass
$m_i$ (t) in each:

$$
\frac{dm_i}{dt} = -S_i\,m_i + \sum_{j<i} b_{ij}\,S_j\,m_j
$$

with $S_i$ the selection function, the breakage rate of class $i$ (1/min), and $b_{ij}$ the breakage distribution, the
fraction of broken class-$j$ material that lands in class $i$ (–). Mass conservation requires
$\sum_{i>j} b_{ij} = 1$ for every class that breaks. In matrix form $\dot{\mathbf m} = A\,\mathbf m$, so batch
grinding is $\mathbf m(t) = e^{At}\,\mathbf m(0)$. For a perfectly mixed continuous mill with mean residence time
$\tau$ at steady state, $\mathbf m_{\text{out}} = (I - \tau A)^{-1}\,\mathbf m_{\text{in}}$ (both arithmetic); real
mills add a measured residence-time distribution. Crushers are commonly modelled with classification–breakage
matrices (attribution UNVERIFIED — pinned at specification).

*Worked example 2* (illustrative three-class batch mill: $S$ = (0.5, 0.3, 0) /min, $b_{21}$ = 0.6, $b_{31}$ = 0.4,
$b_{32}$ = 1, all mass starting in class 1):

| Time (min) | Class 1 | Class 2 | Class 3 | Sum |
|---|---|---|---|---|
| 1 | 0.607 | 0.201 | 0.192 | 1.000 |
| 2 | 0.368 | 0.271 | 0.361 | 1.000 |
| 5 | 0.082 | 0.212 | 0.706 | 1.000 |

Two properties make good tests: total mass stays at 1, and the coarsest class decays exactly as $e^{-S_1 t}$
($e^{-0.5} = 0.607$).

**Classification.** The ball mill runs in closed circuit with a cyclone: the coarse underflow returns to the mill and
the fine overflow, at $P_{80}$, goes to flotation. The circulating load is underflow over new feed (arithmetic
definition). The cyclone's partition curve model is pinned at specification.

## 4. Flotation kinetics and the mass balance

Flotation recovery $R(t)$ (–) over flotation time $t$ (min) follows first-order kinetics with rate constant $k$
(1/min) and ultimate recovery $R_\infty$ (–). Klimpel's model assumes the rate constants are spread uniformly over
$[0, k]$. A perfectly mixed continuous cell with mean residence time $\tau$ averages the first-order result over an
exponential residence-time distribution [4]:

$$
R_{\text{1st}} = R_\infty\big(1 - e^{-kt}\big), \qquad
R_{\text{Klimpel}} = R_\infty\Big[1 - \frac{1 - e^{-kt}}{k\,t}\Big], \qquad
R_{\text{cell}} = R_\infty\,\frac{k\tau}{1 + k\tau}
$$

The transcription in [4] is UNVERIFIED, but both forms follow from the first-order law (derived here): averaging
$1 - e^{-k't}$ over $k' \in [0, k]$ gives the Klimpel bracket, and integrating it against
$e^{-t/\tau}/\tau$ gives the cell form.

*Illustrative* ($k$ = 1 /min, $R_\infty$ = 0.9): after 5 min, first-order kinetics give 0.894, Klimpel 0.721, and a
single perfectly mixed cell with $\tau$ = 5 min 0.75. A spread of rate constants or back-mixing costs recovery that a
single first-order constant hides.

**Two-product formula.** With feed, concentrate and tail grades $f$, $c$, $t$ (%), the mass and component balances
give the yield and recovery [5]:

$$
\frac{C}{F} = \frac{f - t}{c - t}, \qquad R = \frac{c\,(f - t)}{f\,(c - t)}
$$

*Illustrative:* $f$ = 1.0 %, $c$ = 25 %, $t$ = 0.1 % give a yield of 3.6 % and a recovery of 90.4 %. Multi-stream
reconciliation is a least-squares adjustment; its formulation is pinned at specification.

## 5. Mine-to-mill coupling

The Swebrec function links the blast and crusher size distributions [6], so the chain is: blast design → KCO
parameters ($x_{50}$, $b$, $x_{\max}$; see [Drill and blast](drill-and-blast.md)) → run-of-mine size distribution →
crusher → SAG feed size and fines → SAG throughput and energy → ball mill → $P_{80}$ → flotation recovery. A 2022
review covers fragment-size reduction from mining to processing [7].

*Worked example 3* (the drill-and-blast worked example as the feed). The two fragmentation curves give
$x_{80}$ = 0.595 m (Swebrec) and 0.637 m (Rosin–Rammler), so $1/\sqrt{F_{80}}$ is 0.00130 or 0.00125 µm^−½. Against
$1/\sqrt{P_{80}}$ = 0.0816 at 150 µm, the difference changes Bond's $W$ by well under 1 %: Bond's law, applied to
the whole chain, cannot see the blast. The blast acts through the fines, 13.4 % below 5 cm with Swebrec against
9.0 % with Rosin–Rammler, which drive SAG throughput. That is why the coupling needs the Morrell model, the population
balance and a meta-model trained on the whole chain [8].

## Assumptions and limits

- **Empirical energy laws.** Bond and Morrell are lab-calibrated regressions. Their indices must be measured on the
  ore, and the correction factors are pinned at specification.
- **First-order breakage.** The population balance uses time-invariant, linear selection and breakage functions; mill
  filling, slurry rheology and non-first-order breakage are out of scope.
- **Flotation kinetics only.** No froth, entrainment or reagent chemistry.
- **No plant data.** Survey-based mass balances are generally confidential. Every index on this page is illustrative,
  and D2 uses cited circuit parameters plus D1 outputs.
- **Educational, not design software.** The chain shows sensitivities; it does not size equipment.

## In PitStudio

| Where | What | Lane |
|---|---|---|
| `minephys.comminution` | Bond, Morrell, population balance, Klimpel, two-product balance | live (TypeScript port + Pyodide button) |
| [M17](../methods/m17-comminution-mine-to-mill.md) | the analytical chain plus the mine-to-mill meta-model (GBM or MLP → ONNX) | live |
| [Mine-to-mill meta-model](../models/mine-to-mill-meta-model.md) | surrogate of the chain trained on `minephys` sweeps | live |
| [Case D2](../cases/d2-mine-to-mill.md) | t/h, kWh/t, cost/t from D1 fragmentation | — |

**Status: Not yet run** — produced in the data-and-models phase. Pre-registered acceptance (from the plan): the
meta-model reaches R² ≥ 0.95 against the analytical chain on held-out sweeps.

## References

1. Bond (1952). The third theory of comminution. *Trans. AIME* 193, 484–494.
   https://www.scirp.org/reference/referencespapers?referenceid=3600515 (bibliographic record)
2. Morrell (2004). An alternative energy–size relationship to that proposed by Bond for the design and optimisation of
   grinding circuits. *Int. J. Miner. Process.* 74(1–4), 133–141. https://doi.org/10.1016/j.minpro.2003.10.002
3. Austin (1971). Introduction to the mathematical description of grinding as a rate process. *Powder Technol.* 5(1),
   1–17. https://doi.org/10.1016/0032-5910(71)80064-5
4. Gharai, Venugopal (2016). Modeling of flotation process — an overview of different approaches. *Miner. Process.
   Extr. Metall. Rev.* https://doi.org/10.1080/08827508.2015.1115991
5. *Wills' Mineral Processing Technology*, 8th ed. (2016). Elsevier. https://doi.org/10.1016/C2010-0-65478-2
6. Ouchterlony (2005). The Swebrec function: linking fragmentation by blasting and crushing. *Mining Technology*
   114(1), 29–44. https://doi.org/10.1179/037178405X44539
7. Zhang, Sanchidrián, Ouchterlony, Luukkanen (2022). Reduction of fragment size from mining to mineral processing: a
   review. *Rock Mech. Rock Eng.* 56(1), 747–778. https://doi.org/10.1007/s00603-022-03068-3
8. Nobahar, Xu, Dowd (2026). Cost-integrated AI meta-models for mine-to-mill optimisation: linking fragmentation,
   throughput, and operating costs across the value chain. *Minerals* 16(1), 73. https://doi.org/10.3390/min16010073
9. Losaladjome Mboyo, Huo, Mulenga, Mabe Fogang (2025). Distribution of operating costs along the value chain of an
   open-pit copper mine. *Appl. Sci.* 15(3), 1602. https://doi.org/10.3390/app15031602
10. Soofastaei, Fouladgar (2022). Improve energy efficiency in surface mines using artificial intelligence. In
    *Alternative Energies and Efficiency Evaluation*, IntechOpen. https://doi.org/10.5772/intechopen.101493
11. Kanchibotla, Morrell, Valery, O'Loughlin (1998). Exploring the effect of blast design on SAG mill throughput at
    KCGM. *Mine-to-Mill Conference*, AusIMM.
    https://www.ausimm.com/publications/conference-proceedings/mine-to-mill-conference-brisbane-qld-october-1998/exploring-the-effect-of-blast-design-on-sag-mill-throughput-at-kcgm/
