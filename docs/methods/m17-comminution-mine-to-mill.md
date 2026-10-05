# M17 — Comminution chain (Bond, Morrell, population balance) and a mine-to-mill meta-model

> Blast fragmentation is carried through crushing and grinding with classical energy–size laws and a population
> balance to kWh/t and t/h, and a small learned meta-model of that chain makes thousands of what-if scenarios instant.
> · Part of: [Methods](README.md) · Related: [Comminution theory](../theory/comminution.md) ·
> [M12 blast models](m12-blast-fragmentation-models.md) · [Meta-model card](../models/mine-to-mill-meta-model.md) ·
> [Case D2](../cases/d2-mine-to-mill.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical + learned | **yes** (meta-model) | live | [D2](../cases/d2-mine-to-mill.md) | `minephys.comminution` (Apache-2.0); GBM or MLP in `pipeline/` (scikit-learn 1.9.1 / PyTorch) → ONNX | not yet implemented |

## What and why

Grinding is about 40 % of mining energy [7], and in one open-pit copper operation milling and crushing were 59.1 % and
11 % of operating cost [8]. "Mine-to-mill" is the idea that a finer, better-controlled blast moves energy from the mill
to the explosive and raises mill throughput [6]; the classic study at one operation (KCGM) linked blast design to
SAG-mill throughput [9], and a 2026 study trained random-forest meta-models on more than 3 million simulator scenarios with
over 90 % accuracy, finding that finer fragmentation lowers total cost [10].

M17 builds the open, inspectable version of that chain for case D2:

- **classical:** the Swebrec PSD [4] from [M12](m12-blast-fragmentation-models.md) enters a crusher and mill model built
  from Bond's law, Morrell's energy–size relation and a population-balance model;
- **learned:** a meta-model trained on sweeps of that chain answers "what blast and circuit settings maximise t/h at
  acceptable kWh/t" instantly, and its error against the exact analytical chain is measured.

Because the analytical chain is the ground truth, M17 is the cleanest learned-vs-classical comparison in the suite:
there is no measurement noise, only approximation error.

## The algorithm

### Energy–size laws

**Bond's third theory** [1]†:

$$
W = 10\,W_i\left(\frac{1}{\sqrt{P_{80}}} - \frac{1}{\sqrt{F_{80}}}\right)
$$

with specific energy $W$ (kWh/t), Bond work index $W_i$ (kWh/t), and 80 % passing sizes of product and feed $P_{80}$,
$F_{80}$ (µm). Mill power follows as $P = W\,\dot m$ (kW, with $\dot m$ in t/h) before efficiency and correction
factors; at a fixed installed power, throughput is $\dot m = P/W$. Typical $W_i$ ranges are UNVERIFIED — pinned at
specification, so $W_i$ is an input.

**Morrell's relation** for whole circuits (SAG, HPGR, ball), based on the SMC test [2]:

$$
W = M_i \cdot 4\left(x_2^{\,f(x_2)} - x_1^{\,f(x_1)}\right), \qquad f(x) = -\left(0.295 + \frac{x}{10^6}\right)
$$

with $M_i$ the Morrell work index (kWh/t) and $x_1$, $x_2$ the feed and product 80 % passing sizes (µm). The constants
0.295 and $10^6$ are UNVERIFIED — pinned at specification (the original text was not read).

### Population balance

Grinding as a rate process [3] (see also the standard reference text [5]):

$$
\frac{dm_i}{dt} = -S_i\,m_i + \sum_{j<i} b_{ij}\,S_j\,m_j
$$

with $m_i$ the mass fraction in size class $i$ (–), $S_i$ the selection (breakage-rate) function (1/min) and $b_{ij}$
the breakage distribution (fraction of class $j$ breaking into class $i$). With about 30 size classes this is a small
linear ODE system, solved exactly with a matrix exponential or by stepping; a residence-time distribution turns batch
kinetics into a continuous mill. Crushers use a classification–breakage matrix model (citation pinned at
specification).

```text
chain(blast_design, ore, circuit):
    psd_blast  = swebrec(kuz_ram(blast_design, ore))           # M12
    psd_crush  = crusher(psd_blast, circuit.css)                # classification-breakage
    F80        = p80(psd_crush)
    W          = bond(ore.Wi, F80, circuit.P80)   or   morrell(ore.Mi, F80, circuit.P80)
    psd_mill   = pbm(psd_crush, S(ore), b(ore), rtd(circuit))
    tph        = circuit.mill_power / W
    return {kWh_per_t: W, t_per_h: tph, cost_per_t: cost(blast_design, W, tph)}
```

### Worked example (illustrative inputs)

$W_i = 14$ kWh/t, $F_{80} = 2{,}000$ µm, $P_{80} = 150$ µm:
$W = 140\,(1/\sqrt{150} - 1/\sqrt{2000}) = 140\,(0.08165 - 0.02236) = 8.30$ kWh/t. A 10 MW mill then treats $10{,}000/8.30 = 1{,}205$ t/h. A finer crusher product,
$F_{80} = 1{,}500$ µm, lowers $W$ to 7.82 kWh/t and raises throughput to 1,279 t/h (+6.2 %) — the mine-to-mill lever
in one line of arithmetic.

### Meta-model

- **Inputs:** blast design (burden, spacing, powder factor), ore properties ($W_i$ or $M_i$, rock factor), circuit
  settings (crusher closed-side setting, target $P_{80}$, installed power).
- **Outputs:** kWh/t and t/h (and cost/t).
- **Model:** a gradient-boosted tree ensemble or a small MLP (the choice, with its reason, is fixed in the spec),
  trained on `minephys` sweeps over the stated input ranges, with held-out sweeps for testing.
- **Loss:** mean squared error on standardised outputs.
- **Metric:** coefficient of determination on held-out sweeps,
  $R^2 = 1 - \sum (y - \hat y)^2 / \sum (y - \bar y)^2$, per output.
- **Budget:** minutes of compute; ONNX under 1 MB.

## Baseline and comparison

- **Baseline:** the analytical chain itself (exact ground truth for the meta-model).
- **Use comparison:** for case D2's optimisation question ("which blast and circuit settings maximise t/h within a kWh/t
  cap"), the meta-model's optimum is checked by re-running the analytical chain at that point; the gap is reported.
- **Literature:** the published meta-model study [10] is cited for scale only.

## Acceptance criterion (pre-registered)

- **Meta-model: $R^2 \ge 0.95$ vs the analytical chain on held-out sweeps.**
- Analytical chain: worked examples from primary sources (with the † and UNVERIFIED items pinned first) and at least
  three metamorphic relations — finer feed lowers $W$; a higher work index raises $W$; at fixed power, throughput is
  inversely proportional to $W$; the PBM conserves mass exactly.
- Export parity: fp32 rtol 1e-3 / atol 1e-5.

**Results: Not yet run** — produced in the data-and-models phase. Reported: $R^2$ per output, residual plots, and the
D2 scenario tables (kWh/t, t/h, cost/t) from both the chain and the meta-model.

## Lane and web delivery

**Live.** The analytical chain runs in a TypeScript worker and in the `minephys` wheel under Pyodide; the meta-model
runs in ONNX Runtime Web (< 1 MB) to sweep hundreds of scenarios per second for interactive optimisation plots.
Fallback: baked grids.

## Assumptions and limits

- Energy–size laws are empirical; work indices come from standardised lab tests that are not open data for the case
  pits, so ore properties are illustrative inputs.
- The chain is steady state; no circuit dynamics, recirculating-load control or liner wear.
- The meta-model is valid only inside its training ranges; extrapolation is flagged in the UI.
- Educational, not a plant-design tool.

## In PitStudio

- **Cases:** [D2](../cases/d2-mine-to-mill.md) (t/h, kWh/t, cost/t), fed by [D1](../cases/d1-blast-muck-pile.md).
- **Code (planned):** `minephys.comminution` (Bond, Morrell, PBM, Klimpel flotation kinetics); sweeps in `pipeline/`
  `s05_synthesize`; meta-model `s30_train`, `s50_evaluate`, `s60_export`; live engines in `web/`. Card:
  [mine-to-mill meta-model](../models/mine-to-mill-meta-model.md).
- **Status:** not yet implemented — built test-first in the build phase.

† Standard form; the transcription is checked against the primary source by a worked-example test at specification.

## References

1. Bond, F. C. (1952). The third theory of comminution. Trans. AIME 193:484–494.
   https://www.scirp.org/reference/referencespapers?referenceid=3600515
2. Morrell, S. (2004). An alternative energy–size relationship to that proposed by Bond. International Journal of
   Mineral Processing 74(1–4):133–141.
   https://doi.org/10.1016/j.minpro.2003.10.002
3. Austin, L. G. (1971). Introduction to the mathematical description of grinding as a rate process. Powder Technology
   5:1–17. https://doi.org/10.1016/0032-5910(71)80064-5
4. Ouchterlony, F. (2005). The Swebrec function: linking fragmentation by blasting and crushing. Mining Technology
   114(1):29–44. https://doi.org/10.1179/037178405X44539
5. Wills' Mineral Processing Technology (8th ed., 2016). https://doi.org/10.1016/C2010-0-65478-2
6. Zhang et al. (2022). Reduction of fragment size from mining to mineral processing: a review. Rock Mechanics and Rock
   Engineering. https://doi.org/10.1007/s00603-022-03068-3
7. *Improve Energy Efficiency in Surface Mines Using Artificial Intelligence* (grinding 40 % of mining energy).
   https://doi.org/10.5772/intechopen.101493
8. Mboyo et al. (2025). Distribution of operating costs along the value chain of an open-pit copper mine. Applied
   Sciences (CC BY). https://doi.org/10.3390/app15031602
9. Kanchibotla, Morrell, Valery & O'Loughlin (1998). Exploring the effect of blast design on SAG mill throughput at
   KCGM. Mine-to-Mill conference.
   https://www.ausimm.com/publications/conference-proceedings/mine-to-mill-conference-brisbane-qld-october-1998/exploring-the-effect-of-blast-design-on-sag-mill-throughput-at-kcgm/
10. Nobahar, Xu & Dowd (2026). Cost-integrated AI meta-models for mine-to-mill optimisation. Minerals (CC BY).
    https://doi.org/10.3390/min16010073
