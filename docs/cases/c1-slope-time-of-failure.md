# C1 — Slope monitoring → time of failure

> How stable is a pit wall, and once radar shows it accelerating, when will it fail and how much warning is there —
> classical inverse velocity against learned forecasters, on many synthetic events and one real one. ·
> Part of: [Cases](README.md) · Related: [Slopes and monitoring](../theory/slopes-and-monitoring.md) ·
> [M14 Slope forecasting](../methods/m14-slope-forecasting.md) · [Slope forecasters](../models/slope-forecasters.md) ·
> [de Wit dataset card](../data-contract/dataset-cards/dewit-slope-failure.md)

## What and why

**The question.** A geotechnical engineer has two questions about a pit wall. Before it moves: what are its factor
of safety (FoS) and probability of failure (PoF) for a given geometry and rock mass? Once slope radar shows
accelerating displacement: when will it fail, how wide is the uncertainty, and how much lead time does the alarm give
for evacuation? A data scientist adds a third: does a learned sequence model forecast the failure time better than
the classical inverse-velocity method?

**Why it matters.**

- In April 2013 a wall failure at a large US copper pit moved about 165 million tons. Radar had measured the wall
  every six to eight minutes; movement reached two inches per day before the failure; workers were evacuated the
  morning of the slide and none of about 500 was injured, but refined-copper output was expected to fall by 50 % [1].
  No public radar data release exists for that event, so it is context only.
- Fall of ground caused 5 of 42 fatalities among ICMM members in 2024 [2].
- Inverse velocity is standard practice for radar-based time-of-failure forecasts in open pits [3][4][5].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| Real open-pit slope failure: velocity changes, seismic events, weather and radar-derived surface deformation | **real**, **one event (n = 1)** | de Wit (2025), Zenodo record 15003054, CC BY 4.0, 8.9 MB; the mine is not named [6] | [dewit-slope-failure](../data-contract/dataset-cards/dewit-slope-failure.md) |
| InSAR deformation over the Hambach pit (optional) | real, derived-only | EGMS via EGMS Explorer (manual access) [7]; fallback: de Wit + synthetic only | [egms-hambach](../data-contract/dataset-cards/egms-hambach.md) |
| Wall geometry for LEM sections | real terrain | Bingham 3DEP or Hambach NRW DGM1 | [bingham-3dep](../data-contract/dataset-cards/bingham-3dep.md), [hambach-nrw](../data-contract/dataset-cards/hambach-nrw.md) |
| Many seeded accelerating-creep series with known failure time | **synthetic** | Voight creep + radar noise matched to the de Wit series | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |

**The de Wit series is a single real event.** It is used for a descriptive time-of-failure error only: never for
TSTR/TRTR, never for C2ST and never for a significance claim. All "better than" claims come from the synthetic
events, where the failure time is known by construction.

## Methods and baseline

| Rung | Method | Role in C1 |
|---|---|---|
| Classical | [M13 LEM + Hoek–Brown + Monte-Carlo PoF](../methods/m13-slope-stability-lem.md) | Bishop simplified [8] and Spencer [9] slices with generalised Hoek–Brown strength [10]; pySlope as an oracle [11] |
| Classical vs SOTA (learned) | [M14 Inverse velocity + Bayesian TTF vs TCN / PatchTST / Chronos-Bolt](../methods/m14-slope-forecasting.md) | Forecast the failure time from displacement series [12][13][14] |
| SOTA | [M23 analytical GB-InSAR slope-radar model (S4b)](../methods/m23-rtx-sensor-simulation.md) | Line-of-sight projection of the creep field plus phase/atmospheric noise; RTX radar has no phase output, so this sensor is analytical [15] |

**Inverse velocity.** Voight's rate law $\ddot\Omega = A\,\dot\Omega^{\alpha}$ [16] integrates, for $\alpha = 2$, to a
straight line in inverse velocity, $1/v = A\,(t_f - t)$, with $\Omega$ the displacement (mm), $v = \dot\Omega$ its
rate (mm/h), $t$ the time (h), $A$ a fitted constant (mm⁻¹) and $t_f$ the failure time (h) at the time-axis
intercept [3].

**Baseline comparison.** On the synthetic events, a learned forecaster is called better than inverse velocity only
if the paired 95 % CI of the error difference excludes 0, with pairs = seeded events
([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)). On the real event, both methods
are shown side by side with **no** comparison claim.

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Factor of safety | – | Minimum over trial surfaces of available ÷ mobilised shear (Bishop, Spencer) |
| Probability of failure | % | Fraction of Monte-Carlo realisations of strength parameters with FoS < 1 |
| Forecast error | h, and % of lead time | $\lvert \hat t_f - t_f \rvert$ at a record cut-off; ÷ lead time for the synthetic criterion |
| Lead time | h | $t_f - t_{\text{alarm}}$, where the alarm is the first forecast inside a configured threshold |

FoS and PoF acceptance levels by slope scale exist in the design literature [17], but their values could not be read
from a primary copy; they are configurable inputs, not facts.

## Studio tools and artefacts

| Tool | Artefacts it produces for C1 |
|---|---|
| [minephys](../frameworks/minephys.md) `geotech` | LEM, Hoek–Brown, inverse velocity, Bayesian TTF and the GB-InSAR LOS model |
| [PyTorch](../frameworks/pytorch.md) (`pipeline/`) | TCN and PatchTST forecasters (< 4 MB); Chronos-Bolt-tiny export (~18 MB) [14]; training curves |
| [ONNX Runtime](../frameworks/onnx-runtime.md) | Forecasters in the browser with parity reports |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Wall sector on the pit model with a synthetic LOS displacement map | LIVE | three.js / R3F |
| Simulate | Section editor: Bishop / Spencer FoS and Monte-Carlo PoF | LIVE | TS port of `minephys.geotech`; Pyodide button |
| Simulate | Inverse-velocity fit with a record cut-off slider; Bayesian TTF band | LIVE | TS |
| Simulate | Learned forecasts at the same cut-off | LIVE | ORT-web (TCN / PatchTST < 4 MB; Chronos-Bolt ~18 MB) |
| Charts | 1/v plots; forecast vs truth over seeded events with CIs; the real event at 50 % and 80 % cut-offs labelled "single real event — no significance test" | LIVE / REPLAY | baked tables |
| Context | Question, impact, honesty notes | STATIC | — |

## Assumptions and limits

- **Educational, not design software.** FoS and PoF illustrate the methods; they are not a slope design or a
  trigger-action response plan.
- **n = 1 real event.** The real series cannot support statistical claims.
- **Inverse velocity is linear only for α ≈ 2.** Noise in 1/v, filtering lag, regressive vs progressive phases and
  multi-pixel aggregation all affect forecasts [4].
- **EGMS is optional.** Its licence wording conflicts between pages, so it is derived-only; if access is not set up,
  C1 uses de Wit + synthetic only.
- **Radar model.** The slope radar is an analytical LOS model, not a rendered sensor.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/c1.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/c1.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

C1 runs on the open lane only and is part of the first end-to-end slice with A1.

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- FoS and PoF for the reference sections, with LEM checked against the pySlope oracle.
- Synthetic events (many seeded Voight events). **Acceptance:** TTF error ≤ 10 % of lead time at the observed SNR,
  and "better than inverse velocity" only by the decision rule (pairs = seeded events).
- Real de Wit series. **Reported descriptively:** TTF error of each method at the 50 % and 80 % record cut-offs; no
  "better than" claim; the UI says "single real event — no significance test".

## In PitStudio

- Recipe `studio/recipes/cases/c1.yaml`; route `/cases/C1`; model card [Slope forecasters](../models/slope-forecasters.md).

## References

1. High Country News. *How technology detected a huge mine landslide before it happened*.
   https://www.hcn.org/issues/45-8/how-technology-detected-a-huge-mine-landslide-before-it-happened/
2. ICMM (2025). *2024 safety performance*. https://www.icmm.com/en-gb/news/2025/2024-safety-performance
3. Rose, Hungr (2007). *Forecasting potential rock slope failure in open pit mines using the inverse-velocity method*.
   IJRMMS 44(2):308–320. DOI 10.1016/j.ijrmms.2006.07.014
4. Carlà et al. (2017). *Guidelines on the use of inverse velocity method …*. Landslides 14(2):517–534. DOI
   10.1007/s10346-016-0731-5
5. Dick, Eberhardt, Cabrejo-Liévano, Stead, Rose (2015). Early-warning time-of-failure methodology using slope
   stability radar. Can. Geotech. J. 52(4):515–529. DOI 10.1139/cgj-2014-0028
6. de Wit (2025). *Data used for the study of time-lapse velocity variations during an open-pit mine slope failure
   using seismic noise interferometry*. Zenodo, CC BY 4.0. https://zenodo.org/records/15003054
7. Copernicus Land Monitoring Service. *European Ground Motion Service*.
   https://land.copernicus.eu/en/products/european-ground-motion-service
8. Bishop (1955). *The use of the slip circle in the stability analysis of slopes*. Géotechnique 5(1):7–17. DOI
   10.1680/geot.1955.5.1.7
9. Spencer (1967). *A method of analysis of the stability of embankments assuming parallel inter-slice forces*.
   Géotechnique 17(1):11–26. DOI 10.1680/geot.1967.17.1.11
10. Hoek, Brown (2019). *The Hoek–Brown failure criterion and GSI — 2018 edition*. JRMGE 11(3):445–463. DOI
    10.1016/j.jrmge.2018.08.001
11. pySlope 1.4.0 (MIT). https://pypi.org/project/pyslope/
12. Bai, Kolter, Koltun (2018). *An Empirical Evaluation of Generic Convolutional and Recurrent Networks for Sequence
    Modeling* (TCN). https://arxiv.org/abs/1803.01271
13. Nie et al. (2023). PatchTST. ICLR. https://arxiv.org/abs/2211.14730
14. Amazon. *chronos-bolt-tiny* (Apache-2.0). https://huggingface.co/amazon/chronos-bolt-tiny
15. Le Roux et al. (2025). *Slope Stability Monitoring Methods and Technologies for Open-Pit Mining: A Systematic
    Review*. Mining 5(2):32. DOI 10.3390/mining5020032
16. Voight (1989). *A relation to describe rate-dependent material failure*. Science 243:200–203. DOI
    10.1126/science.243.4888.200
17. Read, Stacey (2009). *Guidelines for Open Pit Slope Design*. CSIRO.
    https://ebooks.publish.csiro.au/content/guidelines-open-pit-slope-design
