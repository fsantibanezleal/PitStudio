# B1 — Autonomous–manned traffic and proximity

> When autonomous haul trucks share a real road network with manned light vehicles, how close do they get, how
> often, and what do the trucks' lidar and radar actually see in dust and rain? · Part of: [Cases](README.md) ·
> Related: [M20 Traffic and TTC](../methods/m20-traffic-ttc.md) · [RTX sensor physics](../theory/rtx-sensor-physics.md) ·
> [M22 Cosmos tasks](../methods/m22-cosmos-vlm-tasks.md) · [B2](b2-synthetic-perception.md)

## What and why

**The question.** A safety manager or autonomy integrator plans a mixed fleet: autonomous trucks, manned dozers and
light vehicles, and people on foot near the haul roads. They ask: for a given traffic mix, speed limits and
right-of-way rules, what is the distribution of minimum time-to-collision (TTC), how many near-misses occur per
1,000 operating hours, and how much range and point density do the trucks' sensors lose in dust and rain? A third,
frontier question: can a vision-language model answer simple hazard questions about a pit scene correctly when the
answer is known exactly?

**Why it matters.**

- In 2025, powered haulage caused 13 of 33 US mining fatalities (39 %) and 426 of 4,792 non-fatal injuries (9 %) [1].
- Mobile equipment was the most common cause of fatalities among ICMM members in 2021–2024 (26 %), and 67 % of
  fatalities were linked to ineffective critical-control execution [2]; in 2024 alone, 9 of 42 member fatalities
  related to mobile equipment and transport [3].
- The US regulator published a final rule on safety programmes for surface mobile equipment on 2023-12-20 [4].
- Dust degrades lidar: field measurements show dust starts to affect lidar ranging when atmospheric transmittance
  drops below 71–74 %, while retroreflective targets are still ranged at transmittance as low as 2 % [5].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| Road geometry, intersections, ramps | **real** geometry | USGS 3DEP Bingham Canyon, public domain [6] | [bingham-3dep](../data-contract/dataset-cards/bingham-3dep.md) |
| Agent traffic (trucks from the A1 DES schedule, light vehicles, dozers) | **synthetic** | M2 + M20 agents; CC-BY-4.0 | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| Lidar clouds, radar detections, camera frames with exact labels | **synthetic** | ovrtx and Isaac Sim renders of our own scenes and CC0 materials | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md), [textures-cc0](../data-contract/dataset-cards/textures-cc0.md) |
| People in scenes | **synthetic** | MakeHuman CC0 exports | [makehuman-people](../data-contract/dataset-cards/makehuman-people.md) |
| Hazard questions with exact answers | **synthetic** | answers computed from USD prims | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| Fatality and injury statistics | real, aggregate | MSHA and ICMM publications [1][2][3] (context only, not model inputs) | — |

There is no open record of proximity events or near-misses between haul trucks and light vehicles. Traffic and sensor
data are **"calibrated synthetic — not validated against real data"**.

## Methods and baseline

| Rung | Method | Role in B1 |
|---|---|---|
| Classical / SOTA | [M20 Agent traffic + TTC + rigid-body vehicles](../methods/m20-traffic-ttc.md) | Right-of-way rules and proximity envelopes on the road graph; Rapier in the browser; PhysX vehicles in Isaac Sim as the visual twin |
| Classical | [M2 Haulage DES](../methods/m02-haulage-des.md) | Truck schedules and road loading from A1 |
| SOTA | [M23 RTX sensor simulation](../methods/m23-rtx-sensor-simulation.md) | S1 truck lidar with our Beer–Lambert dust model (calibrated to [5]) and rain; S4a 77 GHz proximity radar |
| Frontier (learned, zero-shot) | [M22 Cosmos Reason 2, task A](../methods/m22-cosmos-vlm-tasks.md) | Hazard questions scored against exact USD ground truth |

**TTC.** For two agents at separation $d$ (m) closing at speed $\dot d < 0$ (m/s), $\text{TTC} = d / (-\dot d)$ (s);
it is undefined when they are not closing. A **near-miss** is an encounter whose TTC falls below a threshold
$\tau$ (s), a documented input pinned at specification (the IL-1 acceptance criterion in
[A2](a2-haul-road-electrification.md) uses 3 s).

**Baselines.** Traffic scenarios are compared with each other (fleet mix, speed limits, separation rules), never
against a real mine. For the hazard questions, Cosmos Reason 2 is compared with its base model Qwen3-VL-2B [7][8] and
with our detector + geometric rule; "Cosmos beats Qwen base" only if a paired McNemar test gives p < 0.05.

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Minimum TTC | s | Per encounter, the lowest TTC; reported as a distribution and its lower percentiles |
| Near-miss rate | events per 1,000 h | Encounters with TTC < $\tau$ ÷ simulated vehicle-hours × 1,000 |
| Lidar degradation | % points retained; max range (m) | Clean RTX cloud vs Beer–Lambert-attenuated cloud as a function of dust transmittance |
| Hazard-question accuracy | balanced accuracy per question type (–, with CI) | Answers vs exact USD truth; Q8_0 vs BF16 agreement on binary questions |

## Studio tools and artefacts

| Tool | Artefacts it produces for B1 |
|---|---|
| [ovrtx](../frameworks/ovrtx.md) (`studio/rtx/`, `st53_sensors`) | S1 lidar frames and S4a radar detections with Doppler; point-cloud shards ≤ 10 MB; per-frame point-count guard |
| [Isaac Sim](../frameworks/isaac-sim-replicator.md) (`st54_vehicles`, `st57_rain_lidar`) | PhysX vehicle visual-twin clips; rain lidar |
| [Cosmos Reason 2](../frameworks/cosmos-reason-2.md) (`st59a_vqa`) | Hazard-question answers and scores (text only) |
| [NVENC / FFmpeg](../frameworks/nvenc-ffmpeg.md) | Clip pairs (AV1 + H.264) |
| [minephys](../frameworks/minephys.md) `environment` | Beer–Lambert dust attenuation for lidar |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Bingham roads with live agents and proximity envelopes | LIVE | Rapier WASM; target 60 Hz for ≤ 40 vehicles |
| Simulate | Traffic-mix and speed-limit controls; TTC histogram | LIVE | TS agents + Rapier |
| Simulate | Dust-transmittance slider on a baked lidar frame | LIVE | baked cloud + own Beer–Lambert model in a TS worker |
| Studio replay | Isaac Sim vehicle clips; ovrtx lidar/radar/RGB comparison frames | REPLAY | AV1 + H.264; shards |
| Studio replay | Hazard questions and answers | REPLAY (display-only) | precomputed text, "Built on NVIDIA Cosmos" |
| Charts | Near-misses per 1,000 h by scenario; lidar retention vs transmittance; VLM accuracy with CIs | REPLAY | baked tables |
| Context | Question, impact, honesty notes | STATIC | — |

## Assumptions and limits

- **Model-based rates.** Near-miss rates describe the simulated rules and envelopes, not any real operation.
- **Sensor gaps.** ovrtx has no dust model; dust is our add-on. Radar is assumed unaffected by dust at mm-wave — a
  stated assumption, UNVERIFIED (no source read). Sensor renders are not validated against real sensors.
- **Cosmos.** Optional and never a headline KPI. As published, the 2B model card lists a 24 GB minimum [7]; a Q8_0
  GGUF of the official revision runs locally via llama.cpp, with fit and quality measured, not assumed. Outputs are
  display-only and carry "Built on NVIDIA Cosmos".
- Equipment/people perception sim-to-real is not measured here (see [B2](b2-synthetic-perception.md)).
- Not a safety system and not a substitute for a site's collision-avoidance assessment.
- Performance data of ovrtx and Isaac Sim stay local-only. PitStudio is not affiliated with or endorsed by NVIDIA.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/b1.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/b1.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

Cosmos steps need the maintainer's acceptance of the gated model terms; without it, the hazard-question tab shows
"not run" ([Cosmos tasks](../guides/cosmos-tasks.md)).

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- Min-TTC distributions and near-misses per 1,000 h for each traffic scenario, with seed CIs.
- Lidar point retention and range vs dust transmittance; rain-lidar comparison.
- Cosmos task A on about 6.5k hazard queries. **Acceptance:** Q8_0 vs BF16 agreement ≥ 95 % on binary questions;
  per-type balanced accuracy with CI; "Cosmos beats Qwen base" only if McNemar p < 0.05.

## In PitStudio

- Recipe `studio/recipes/cases/b1.yaml`; route `/cases/B1`; model card [Cosmos Reason 2](../models/cosmos-reason-2.md).
- VLM decision: [DEC-0009](../architecture/decisions/DEC-0009-vlm-llamacpp-gguf.md).

## References

1. US MSHA. *Powered Haulage Safety*. https://www.msha.gov/safety-and-health/safety-and-health-initiatives/powered-haulage-safety
2. ICMM (2025). *2020–2024 Safety Performance: Insights*.
   https://www.icmm.com/en-gb/research/health-safety/2025/insights-2020-2024-safety-data
3. ICMM (2025). *2024 safety performance*. https://www.icmm.com/en-gb/news/2025/2024-safety-performance
4. US MSHA (2023). *Safety Program for Surface Mobile Equipment*, final rule, FR doc 2023-27640.
   https://www.federalregister.gov/documents/2023/12/20/2023-27640/safety-program-for-surface-mobile-equipment
5. Phillips, Guenther, McAree (2017). *When the Dust Settles …*. J. Field Robotics 34(5):985–1009. DOI
   10.1002/rob.21701
6. USGS. *About 3DEP Products & Services*. https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
7. NVIDIA. *Cosmos-Reason2-2B* model card. https://huggingface.co/nvidia/Cosmos-Reason2-2B
8. Qwen. *Qwen3-VL-2B-Instruct* (Apache-2.0). https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct
