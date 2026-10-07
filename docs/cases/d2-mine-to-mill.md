# D2 — Mine-to-mill throughput and kWh/t

> How does the fragmentation a blast produces carry through crushing and grinding to plant throughput, specific energy
> and cost per tonne — and can a learned meta-model answer that chain instantly? · Part of: [Cases](README.md) ·
> Related: [Comminution theory](../theory/comminution.md) ·
> [M17 Comminution and mine-to-mill](../methods/m17-comminution-mine-to-mill.md) ·
> [Mine-to-mill meta-model](../models/mine-to-mill-meta-model.md) · [D1](d1-blast-muck-pile.md)

## What and why

**The question.** A mine-to-mill team weighs more explosive (cost in the pit) against finer feed (savings at the mill).
They ask: for a blast design and its fragmentation curve, what feed size reaches the mill, what specific energy
(kWh/t) does grinding need, what throughput (t/h) can the installed mill power deliver, and what is the total cost per
tonne across blasting, crushing and grinding?

**Why it matters.**

- Grinding is about 40 % of mining energy [1].
- In a 2025 costing study of an open-pit copper operation, milling cost 6.18 USD/t (59.1 % of total operating cost)
  and crushing 1.15 USD/t (11 %) [2].
- Mine-to-mill optimisation has been studied since the 1990s, linking blast design to SAG-mill throughput [3]; a 2026
  study trained meta-models on more than three million simulator scenarios (> 90 % predictive accuracy) and found
  that finer fragmentation lowers total comminution cost despite higher explosive cost [4].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| Fragmentation curve (x50, x80, Swebrec parameters) | **synthetic**, from D1 | [D1](d1-blast-muck-pile.md) design models | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| Circuit parameters: Bond work index, Morrell parameters, crusher setting, mill power, unit costs | cited parameters | literature tables in `minephys` knowledge files, each row with citation and verification status; typical ranges UNVERIFIED until pinned | — |
| Training sweeps for the meta-model | **synthetic** | `minephys` analytical chain evaluated over parameter grids; CC-BY-4.0 | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |

No public comminution test dataset was found [5], so D2 is **"calibrated synthetic — not validated against real
data"**: it is a model of a generic circuit, not of a plant.

## Methods and baseline

| Rung | Method | Role in D2 |
|---|---|---|
| Classical | [M12 Kuz-Ram / Swebrec](../methods/m12-blast-fragmentation-models.md) | Blast → run-of-mine size distribution (from D1) |
| Classical | [M17 Bond / Morrell + population balance](../methods/m17-comminution-mine-to-mill.md) | Crusher and mill energy–size relations; PBM for the product distribution |
| Learned | [M17 Mine-to-mill meta-model](../methods/m17-comminution-mine-to-mill.md) | GBM / MLP trained on sweeps of the analytical chain, exported to ONNX |

**Energy–size relations.**

- Bond's third law: $W = 10\,W_i\,(1/\sqrt{P_{80}} - 1/\sqrt{F_{80}})$ (kWh/t), with work index $W_i$ (kWh/t) and the
  80 % passing sizes of product $P_{80}$ and feed $F_{80}$ (µm) [6].
- Morrell's alternative relation for whole circuits [7] and Austin's population-balance model,
  $dm_i/dt = -S_i m_i + \sum_{j<i} b_{ij} S_j m_j$, with selection function $S_i$ (1/min) and breakage distribution
  $b_{ij}$ (–) per size class $i$ [8].

**Baseline.** The meta-model's reference is the analytical chain itself on held-out sweeps; a meta-model never
replaces the chain in a claim, it only answers faster.

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Specific energy | kWh/t | Bond (or Morrell) energy from $F_{80}$ to the target $P_{80}$, summed over crushing and grinding stages |
| Throughput | t/h | Installed mill power (kW) ÷ specific energy (kWh/t), with the circuit's efficiency factors |
| Cost per tonne | USD/t | Explosive + crushing + grinding energy and consumables per tonne; unit costs are documented inputs |
| Meta-model fit | R² (–) | Meta-model vs analytical chain on held-out sweeps |

## Studio tools and artefacts

| Tool | Artefacts it produces for D2 |
|---|---|
| [PyTorch](../frameworks/pytorch.md) (`pipeline/`) | Meta-model (< 1 MB ONNX) and its evaluation on held-out sweeps |
| [minephys](../frameworks/minephys.md) `comminution`, `blasting` | Bond, Morrell, PBM and Klimpel models; sweep generator |
| [ONNX Runtime](../frameworks/onnx-runtime.md) | Meta-model in the browser with parity report |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Pit-to-plant schematic linked to the D1 bench | STATIC / LIVE | three.js / R3F |
| Simulate | Blast → crusher → mill chain with design sliders | LIVE | TS port of `minephys.comminution`; Pyodide button |
| Simulate | Meta-model answer for the same inputs, side by side | LIVE | ORT-web (< 1 MB) |
| Studio replay | Sweep tables behind the meta-model | REPLAY | Parquet |
| Charts | kWh/t vs x50; t/h vs P80; cost breakdown by stage | LIVE | — |
| Context | Question, impact, honesty notes | STATIC | — |

## Assumptions and limits

- **Generic circuit.** Parameters are literature values, not a plant survey; results are comparative, not
  predictions for any operation.
- **Energy–size laws have ranges.** Bond's law and Morrell's relation are calibrated on standard tests over specific
  size ranges; outside them the energy is an extrapolation.
- **Meta-model scope.** Valid only within the sweep ranges it was trained on; it adds speed, not knowledge.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/d2.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/d2.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

D2 needs no NVIDIA runtime; the sweeps and the meta-model run in minutes.

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- kWh/t, t/h and cost/t across blast designs, with the analytical chain checked against worked examples from the
  primary sources.
- Meta-model on held-out sweeps. **Acceptance:** R² ≥ 0.95 vs the analytical chain; ONNX and in-browser parity.

## In PitStudio

- Recipe `studio/recipes/cases/d2.yaml`; route `/cases/D2`; model card [Mine-to-mill meta-model](../models/mine-to-mill-meta-model.md).

## References

1. IntechOpen. *Improve Energy Efficiency in Surface Mines Using Artificial Intelligence*. DOI
   10.5772/intechopen.101493. https://www.intechopen.com/chapters/79641
2. Mboyo et al. (2025). *Distribution of Operating Costs Along the Value Chain of an Open-Pit Copper Mine*. Applied
   Sciences, CC BY. DOI 10.3390/app15031602
3. Kanchibotla, Morrell, Valery, O'Loughlin (1998). *Exploring the effect of blast design on SAG mill throughput*.
   Mine-to-Mill Conference, AusIMM.
   https://www.ausimm.com/publications/conference-proceedings/mine-to-mill-conference-brisbane-qld-october-1998/exploring-the-effect-of-blast-design-on-sag-mill-throughput-at-kcgm/
4. Nobahar, Xu, Dowd (2026). *Cost-Integrated AI Meta-Models for Mine-to-Mill Optimisation*. Minerals, CC BY. DOI
   10.3390/min16010073
5. Zenodo dataset search "bond work index" (no public comminution test dataset).
   https://zenodo.org/api/records?q=%22bond%20work%20index%22&type=dataset&size=20
6. Bond (1952). *The third theory of comminution*. Trans. AIME 193:484–494 (bibliographic record).
   https://www.scirp.org/reference/referencespapers?referenceid=3600515
7. Morrell (2004). *An alternative energy–size relationship to that proposed by Bond*. Int. J. Miner. Process.
   74:133–141. DOI 10.1016/j.minpro.2003.10.002
8. Austin (1971). *Introduction to the mathematical description of grinding as a rate process*. Powder Technol.
   5:1–17. DOI 10.1016/0032-5910(71)80064-5
