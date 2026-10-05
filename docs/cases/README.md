# Cases

> Twelve operational questions in five categories, each answered on one real open pit with physics, classical
> baselines and learned models, and each delivered as a web workbench. · Part of: [Docs home](../README.md) ·
> Related: [Coverage matrix](coverage-matrix.md) · [Tool matrix](tool-matrix.md) ·
> [Scenario impact](../context/scenario-impact.md) · [Reproduce a case](../guides/reproduce-a-case.md)

## What and why

A case is the unit of value in PitStudio. It starts from a question that a mining engineer, a safety manager, a
planner or an AI practitioner actually asks, and it binds four things to that question:

1. **real data** where open data exist, and labelled synthetic data where they do not;
2. a **method ladder**: a classical baseline, then state-of-the-art and learned methods
   ([M1–M23](../methods/README.md)), compared under one pre-registered decision rule;
3. the **studio tools** that produce its artefacts (physics runs, sensor renders, trained models, videos);
4. a **web workbench** at `/cases/:id` that explains, runs live where it can, and replays the rest.

The twelve cases were selected by impact × simulability × validation data × web value × genuine GPU use. The
cost, safety and energy evidence behind the selection is on [Scenario impact](../context/scenario-impact.md).

![Case catalogue: 12 cases in 5 category bands with their KPIs](../assets/diagrams/case-catalogue.svg)

*The 12 cases in their 5 categories, each with its headline KPIs, its real data anchor and its main honesty caveat.*

## Catalogue

| # | Case | Category | KPIs (units) | Real data | Synthetic data |
|---|---|---|---|---|---|
| A1 | [Truck–shovel cycle, dispatch and fleet sizing](a1-truck-shovel-dispatch.md) | A Haulage and energy | t/h, queue time (min), match factor (–), cost/t (USD/t) | Bingham road network (3DEP) | Calibrated DES cycles |
| A2 | [Haul-road physics and electrification](a2-haul-road-electrification.md) | A | L/(t·km), kWh/t, CO₂e/t (kg/t) | Bingham pit profile (3DEP) | Generic truck from academic sources; Isaac Lab rollouts |
| A3 | [Loading and payload variance](a3-loading-payload-variance.md) | A | payload CV (%), passes/truck, fuel/t (L/t) | Literature repose targets | GPU DEM/MPM rollouts; Isaac Lab dig episodes |
| B1 | [Autonomous–manned traffic and proximity](b1-traffic-proximity.md) | B Safety and autonomy | min TTC (s), near-misses per 1,000 h | Bingham road geometry; MSHA/ICMM statistics (context) | Agent traffic; RTX lidar/radar |
| B2 | [Synthetic-data perception and crusher oversize](b2-synthetic-perception.md) | B | synthetic held-out mAP50, DR ablation, corruption drop (pp) | none by default (optional real probe) | Replicator + ovrtx images, MakeHuman CC0 people |
| C1 | [Slope monitoring → time of failure](c1-slope-time-of-failure.md) | C Geotech and environment | FoS (–), PoF (%), forecast error (h), lead time (h) | de Wit slope-failure series (one event); Hambach EGMS (optional) | Voight creep series |
| C2 | [Tailings breach run-out and pit flooding](c2-tailings-breach.md) | C | arrival time (min), max depth (m), inundated area (km²) | Bingham terrain (3DEP) | GPU shallow-water runs |
| C3 | [Haul-road and blast dust, water trucks](c3-dust.md) | C | PM10 (kg/VKT), receptor concentration (µg/m³), water use (m³/shift) | ERA5 or GHCNh wind; AP-42 factors | A1 traffic; plume and particle fields |
| D1 | [Blast design and muck pile](d1-blast-muck-pile.md) | D Drill-blast-to-mill | P80, % oversize, PPV (mm/s), flyrock radius (m); TSTR/TRTR IoU ratio | Mendeley labelled fragment images | Exact-PSD muck piles |
| D2 | [Mine-to-mill throughput and kWh/t](d2-mine-to-mill.md) | D | t/h, kWh/t, cost/t (USD/t) | Cited circuit parameters | `minephys` sweeps; D1 outputs |
| E1 | [Pit shell and pushbacks → LOM haul distance](e1-pit-shell-pushbacks.md) | E Planning and survey | NPV (USD), strip ratio (–), haul km and lift (m) per period | MineLib `marvin` (optional, CC BY-SA) | `oreblocks` deposits |
| E2 | [Survey → volumetric reconciliation](e2-survey-reconciliation.md) | E | volume error (%), real excavated volume (m³) | Bingham DEMs 2018 → 2023 | RTX drone flight over a known-volume scene |

Where the categories carry the story:

- **A and D** carry cost and energy. Haulage is up to 60 % of open-pit operating cost [1]; grinding is about 40 % of
  mining energy [2].
- **B and C** carry safety. Powered haulage caused 13 of 33 US mining fatalities in 2025 [3]; mobile equipment caused
  26 % of the fatalities reported by ICMM members in 2021–2024 [4]; wall failures and tailings breaches are the
  catastrophic tail.
- **E** carries the twin's geometry, with the strongest validation: ground truth by construction and public
  multi-epoch terrain.

## Default real site

**Bingham Canyon, Utah, from USGS 3DEP** is the default site of every case that needs terrain: 1 m bare-earth DEMs from
2013 (partial), 2018 and 2023 and 69 lidar tiles, all public domain [5][6]. See the
[Bingham 3DEP card](../data-contract/dataset-cards/bingham-3dep.md). Two other open sites complement it:

- **McKinley Mine** (CC BY 4.0, optional OpenTopography key) supplies close-up haul-road geometry and textures
  ([card](../data-contract/dataset-cards/mckinley-lidar.md)). Without the key, scenes use Bingham only plus CC0
  textures.
- **Hambach** (NRW DGM1, dl-de/zero-2.0) plus **EGMS** InSAR supply slope deformation for C1
  ([NRW card](../data-contract/dataset-cards/hambach-nrw.md),
  [EGMS card](../data-contract/dataset-cards/egms-hambach.md)).

Benches in coarse scenes are regenerated by design code and labelled as such in the scene. The site is
named only as a public-domain terrain source; nothing in PitStudio models or implies the operator's actual practice.

## How a case is delivered on the web

`/cases` shows this catalogue plus the [coverage](coverage-matrix.md) and [tool](tool-matrix.md) matrices. Each
`/cases/:id` route has five sub-tabs:

| Sub-tab | What it shows | Typical lane |
|---|---|---|
| **Scene** | The 3D pit (Bingham LOD-0, glTF / 3D Tiles) with the case's layers: roads, agents, fields, shells | live render of static assets |
| **Simulate (live)** | Engines that run in the browser: TS workers (DES, analytical models, min-cut), WGSL compute, Rapier, ORT-web models, the `minephys` Pyodide button | live |
| **Studio replay** | Baked artefacts of GPU work: particle and field shards, RTX renders, sensor clouds, Isaac Lab rollouts, Kit captures, AV1 + H.264 clips | replay / precompute |
| **Charts** | KPIs with units, baselines, paired 95 % confidence intervals and acceptance verdicts | live or replay |
| **Context** | The operational question, impact evidence, theory and method links, honesty notes, licences | static |

Every element carries a **lane badge** (LIVE / REPLAY / STATIC) and the page shows the compute **tier** (T1 WebGPU,
T2 WASM, T0 baked). The lane rule is measured, not declared: LIVE only if the element is web-drivable, its asset is
≤ 25 MB, an interaction takes ≤ 16 ms or a run ≤ 1 s on T2, and its trace is ≤ 10 MB
([Compute lanes](../pipelines/compute-lanes.md), [Compute tiers](../web/compute-tiers.md)). A shared `SimClock`,
paused by default, keeps the 3D scene, charts and videos in step.

### "Reproduce this"

Every case page and every `/cases/:id` route ends with a **Reproduce this** block: the runner commands that rebuild
the case's artefacts from a clean checkout, the recipe they read and the manifest they write. A case recipe is a
YAML DAG (schema-validated) over the studio and pipeline stages; the runner caches stages by content hash in the
studio store (`PITSTUDIO_STORE`, default `C:\ps` on Windows) and reads data from `PITSTUDIO_DATA`, models from
`PITSTUDIO_MODELS` and scratch from `PITSTUDIO_TMP` (defaults: git-ignored folders in the repo). See
[Runner](../studio/runner.md) and [Reproduce a case](../guides/reproduce-a-case.md).

```bash run
uv sync
```

```bash run deferred=P6
uv run studio plan studio/recipes/cases/a1.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/a1.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

## Rules every case follows

- **Decision rule.** "Better than" means the paired 95 % confidence interval of the difference excludes 0; otherwise
  the UI says "no significant difference" ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).
- **Honest status.** Nothing has been trained, rendered or baked yet. Each Results section says **Not yet run** and
  lists exactly what will be reported, with its pre-registered acceptance criterion. The GPU capability probes are
  written but not yet run on the reference machine.
- **Honest data.** A data type with no real reference is labelled "calibrated synthetic — not validated against real
  data" and gets no C2ST/TSTR claim. Measured sim-to-real exists only where a real labelled set exists:
  fragmentation (D1). Equipment and people detection (B2) is "not measured" unless the optional real probe is
  labelled. The single real slope-failure series (C1) is descriptive only.
- **Scope.** PitStudio is a simulation-grade twin, not a live digital twin (it has no telemetry feed). Slope,
  tailings and blasting outputs are educational, not design or regulatory software, and each case states its validity
  range.
- **Licences.** NVIDIA tools are named nominatively; PitStudio is not affiliated with or endorsed by NVIDIA and never
  redistributes NVIDIA binaries, assets, engines or caches. Performance data of Isaac Sim, Kit, Replicator, ovrtx and
  TensorRT for RTX stay local-only; regular TensorRT numbers of our own models are published
  ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

## In PitStudio

- First end-to-end slice: **A1 and C1** on the open lane (DES, LEM, inverse velocity, Bingham terrain) → baked
  artefacts → working `/cases/A1` and `/cases/C1` routes, before any NVIDIA-runtime work.
- The case registry (one entry per case: category, data, KPIs, methods, tools, lanes) generates the web catalogue
  and both matrices. Every method and every studio tool must appear in at least one case.
- Pages: [A1](a1-truck-shovel-dispatch.md) · [A2](a2-haul-road-electrification.md) ·
  [A3](a3-loading-payload-variance.md) · [B1](b1-traffic-proximity.md) · [B2](b2-synthetic-perception.md) ·
  [C1](c1-slope-time-of-failure.md) · [C2](c2-tailings-breach.md) · [C3](c3-dust.md) · [D1](d1-blast-muck-pile.md) ·
  [D2](d2-mine-to-mill.md) · [E1](e1-pit-shell-pushbacks.md) · [E2](e2-survey-reconciliation.md).

## References

1. May, M. A. (2013). *Applications of Queuing Theory for Open-Pit Truck/Shovel Haulage Systems*. Virginia Tech
   thesis. https://vtechworks.lib.vt.edu/items/fecf61c3-860b-4671-91ed-09549ddad265
2. IntechOpen. *Improve Energy Efficiency in Surface Mines Using Artificial Intelligence*. DOI
   10.5772/intechopen.101493. https://www.intechopen.com/chapters/79641
3. US Mine Safety and Health Administration. *Powered Haulage Safety* (2025 statistics).
   https://www.msha.gov/safety-and-health/safety-and-health-initiatives/powered-haulage-safety
4. ICMM (2025). *2020–2024 Safety Performance: Insights*.
   https://www.icmm.com/en-gb/research/health-safety/2025/insights-2020-2024-safety-data
5. USGS. *About 3DEP Products & Services*. https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
6. USGS. The National Map Access API, 1 m DEM and LPC products over Bingham Canyon.
   https://tnmaccess.nationalmap.gov/api/v1/products?bbox=-112.17,40.50,-112.12,40.54&datasets=Digital%20Elevation%20Model%20(DEM)%201%20meter&max=10
