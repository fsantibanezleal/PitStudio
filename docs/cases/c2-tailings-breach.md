# C2 — Tailings breach run-out and pit flooding

> If a tailings dam breaches on real terrain, when does the flow arrive downstream, how deep does it get and how much
> ground does it cover — and can a neural operator answer the same what-if instantly in a browser? ·
> Part of: [Cases](README.md) · Related: [Tailings theory](../theory/tailings.md) ·
> [M15 Shallow water + FNO](../methods/m15-shallow-water-fno.md) · [FNO fields](../models/fno-fields.md) ·
> [Composer review](../guides/composer-review.md)

## What and why

**The question.** A tailings engineer preparing a dam-breach assessment, or an emergency planner, asks: for a given
release volume, breach and material rheology, how long until the flow front reaches a point downstream (warning
time), how deep it gets, and which area is inundated? The same solver answers a variant: how fast does rainfall or
inflow flood the pit floor? A modelling team asks the second question: can a learned surrogate reproduce the solver
closely enough to explore what-ifs interactively?

**Why it matters.**

- The 2019 Brumadinho failure released nearly 10 million m³ and cost over 270 lives; upstream-raised dams are
  over-represented in failure statistics [1][2].
- The Global Industry Standard on Tailings Management launched on 5 August 2020 with 15 principles and 77 auditable
  requirements, including consequence classification [3].
- Warning time is decisive: in the 2007 Miraí failure (3.8 Mm³ released from a 34 m dam, peak breach flow 422 m³/s)
  the flood reached the town in about 2.5–4 h; about 1,033 people were exposed and there were no deaths [4].
- Practice uses depth-averaged non-Newtonian solvers; a 2026 metamodel study found breach parameters dominate near the
  dam and yield stress dominates downstream [5].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| Terrain downstream of a hypothetical facility | **real** terrain | USGS 3DEP Bingham Canyon 1 m DEM, public domain [6] | [bingham-3dep](../data-contract/dataset-cards/bingham-3dep.md) |
| Breach scenarios (volume, breach width and time, yield stress, viscosity) and solver runs | **synthetic** | own GPU shallow-water solver; parameter ranges from published cases [4][5]; CC-BY-4.0 | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| Verification problems | analytical | dam-break and mass-conservation benchmarks of the physics test suite | — |

The facility is **hypothetical**: PitStudio places an illustrative dam on public terrain and never recreates an
identifiable community at risk. There is no real flood record for this terrain, so the fields are **"calibrated
synthetic — not validated against real data"**.

## Methods and baseline

| Rung | Method | Role in C2 |
|---|---|---|
| SOTA | [M15 GPU shallow water with Bingham rheology](../methods/m15-shallow-water-fno.md) | 2-D depth-averaged mass and momentum on the DEM with a yield-stress (Bingham) friction term; own Warp solver |
| Learned | [M15 FNO surrogate](../methods/m15-shallow-water-fno.md) | Fourier neural operator [7] (DFT-matmul form, ONNX-friendly) trained on solver runs over many terrains and parameters |

**Baseline.** The FNO is judged against the solver it imitates on **held-out terrains**; the solver is judged against
analytical dam-break solutions and exact mass conservation. A pit-flooding variant reuses the same solver with inflow
sources on the pit floor.

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Arrival time | min | First time the depth at a receptor cell exceeds a threshold $h_{\min}$ (m; a documented input) |
| Maximum depth | m | Maximum depth over the run, per cell and at receptors |
| Inundated area | km² | Count of cells whose maximum depth exceeds $h_{\min}$ × cell area |
| FNO error | % | Relative L2 error of the FNO depth field vs the solver on held-out terrains |

## Studio tools and artefacts

| Tool | Artefacts it produces for C2 |
|---|---|
| [Warp](../frameworks/warp.md) (`st50_physics`) | Depth and velocity fields (Zarr), arrival-time maps, receptor hydrographs (Parquet) |
| [USD Composer](../frameworks/kit-usd-composer-explorer.md) (`st58_kit_capture`) | Path-traced hero clip of the breach on the pit terrain, from our own extension and waypoints |
| [NVENC / FFmpeg](../frameworks/nvenc-ffmpeg.md) (`st56_encode`) | AV1 1080p + H.264 720p clip pair, VMAF-targeted, ≤ 25 MB |
| [PyTorch](../frameworks/pytorch.md) / [ONNX Runtime](../frameworks/onnx-runtime.md) | FNO-2D (~5 MB) with parity reports |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Terrain with flood-depth and arrival-time overlays | LIVE | three.js / R3F; SimClock |
| Simulate | Small-grid shallow-water twin with breach controls | LIVE | WGSL compute (T1); baked aggregates on T0 |
| Simulate | FNO what-if: change volume or yield stress, get the depth field | LIVE | ORT-web, ≤ 50 ms/step target |
| Studio replay | Warp field replay; Composer hero clip | REPLAY | Zarr shards ≤ 10 MB; AV1 + H.264 |
| Charts | Arrival time vs distance; receptor hydrographs; FNO error map | REPLAY | baked tables |
| Context | Question, impact, ethics and honesty notes | STATIC | — |

## Assumptions and limits

- **Educational, not regulatory.** C2 is illustration and warning-time analysis, not an engineering breach study or a
  GISTM consequence classification.
- **Depth-averaged 2-D flow.** No vertical structure, erosion or entrainment; breach growth is a scenario input,
  not a modelled mechanism.
- **Rheology.** Single-phase Bingham; yield stress and viscosity are scenario inputs.
- **Surrogate scope.** The FNO is valid only inside the terrain and parameter distribution it was trained on.
- Kit performance data stay local-only; the Composer clip is a render of our scene, never of NVIDIA application UI.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/c2.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/c2.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

The Composer capture needs the kit-app-template licence prompt answered by the maintainer; otherwise the Composer
tool page shows "not run" and C2 keeps its Warp field replay, which carries every KPI
([Maintainer acts and licences](../studio/owner-acts-and-licences.md)).

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- Arrival time, maximum depth and inundated area for the reference breach scenarios, with solver verification
  (dam-break benchmark, mass conservation).
- FNO-2D on held-out terrains. **Acceptance:** relative L2 ≤ 5 %; ONNX and in-browser parity.

## In PitStudio

- Recipe `studio/recipes/cases/c2.yaml`; route `/cases/C2`; model card [FNO fields](../models/fno-fields.md).

## References

1. NGI / ScienceNorway. *This determines how dangerous a dam failure can be* (summary of Piciullo et al. 2022).
   https://partner.sciencenorway.no/geology-natural-sciences-ngi/this-determines-how-dangerous-a-dam-failure-can-be/2568663
2. Piciullo et al. (2022). *A new look at the statistics of tailings dam failures*. Engineering Geology 303. DOI
   10.1016/j.enggeo.2022.106657
3. ICMM. *Global Industry Standard on Tailings Management*.
   https://www.icmm.com/en-gb/our-principles/tailings/global-industry-standard-on-tailings-management
4. Silva, Eleutério (2023). Miraí tailings-dam failure reproduced with HEC-RAS and HEC-LifeSim. NHESS 23:3095. DOI
   10.5194/nhess-23-3095-2023
5. Sáo, Maciel, Eleutério (2026). *Metamodel-based … sensitivity analysis of tailings dam-breach flows*.
   https://arxiv.org/abs/2607.19296
6. USGS. *About 3DEP Products & Services*. https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
7. Li et al. (2021). *Fourier Neural Operator for Parametric Partial Differential Equations*. ICLR.
   https://arxiv.org/abs/2010.08895
