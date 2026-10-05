# A2 — Haul-road physics and electrification

> What do grade, rolling resistance and the drive system (diesel, trolley assist, battery-electric) do to fuel,
> energy and CO₂e per tonne on a real pit ramp — and can a learned truck controller drive that ramp safely? ·
> Part of: [Cases](README.md) · Related: [Haulage theory](../theory/haulage.md) ·
> [M6 Haul-road energy and routing](../methods/m06-haul-road-energy-routing.md) ·
> [M21 Isaac Lab policies](../methods/m21-isaac-lab-policies.md) · [A1](a1-truck-shovel-dispatch.md)

## What and why

**The question.** A mine planner or decarbonisation lead compares ramp designs and drive systems. For a haul profile
from the pit floor to the crusher they ask: litres per tonne-kilometre, kWh per tonne and kg CO₂e per tonne for
diesel, trolley-assisted and battery-electric trucks; which grade-constrained route minimises energy; and how cycle
time changes. A second, autonomy-oriented question rides on the same ramp: can a policy trained in simulation follow
the ramp, hold speed on grade and avoid a light vehicle (IL-1)?

**Why it matters.**

- Diesel materials handling is about 17 % of mining energy, second only to grinding [1].
- A Swedish copper mine's trolley assist saved 830,000 L of diesel per year (2018); a Canadian pilot saved 79 kg CO₂e
  per truck cycle on the trolley section and more than doubled ramp speed [2].
- A modelling study on real copper-mine coordinates reports 44 % higher uphill speed, 16 % shorter cycle travel time
  and 85 % fuel saving over each up–down cycle with trolley assist [3]; drive-cycle simulations find battery-electric
  haul trucks charged from trolley lines feasible and cheaper than diesel-electric under stated assumptions [4].
- Field precedent for learned truck control exists: RL path tracking on mining trucks reached a maximum lateral error
  of 0.22 m in field tests [5].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| Ramp and bench profile (grade, length, curvature per segment) | **real** geometry | USGS 3DEP Bingham Canyon 1 m DEM, public domain [6] | [bingham-3dep](../data-contract/dataset-cards/bingham-3dep.md) |
| Generic truck (mass, payload, power, retarder, trolley and battery parameters) | **calibrated synthetic** | academic model parameters [3][4]; never an OEM rimpull chart | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| Cycle times per segment | **synthetic** | A1 DES ([M2](../methods/m02-haulage-des.md)) | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| IL-1 training and evaluation episodes | **synthetic** | Isaac Lab env on Newton, procedural truck | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |

## Methods and baseline

| Rung | Method | Role in A2 |
|---|---|---|
| Classical | [M6 Haul-road energy + grade-constrained routing](../methods/m06-haul-road-energy-routing.md) | Rimpull / retarder balance per segment, energy per cycle, A* route search on the DEM under a grade limit |
| Classical | [M2 Haulage DES](../methods/m02-haulage-des.md) | Cycle times and queueing that turn per-cycle energy into per-shift totals |
| SOTA → beyond-SOTA (learned) | [M21 IL-1 haul truck](../methods/m21-isaac-lab-policies.md) | Ramp driving with light-vehicle avoidance; Isaac Lab kit-less on Newton, rsl_rl PPO, ONNX MLP |

**Physics core.** Total resistance is rolling plus grade resistance, $TR = RR + GR$ (%) [7]. The steady speed on a
segment solves $F_{\text{rim}}(v) = m g\,TR/100$ (N), with $m$ the gross vehicle mass (kg) and $g$ = 9.81 m/s²;
downhill, the retarder must dissipate $P_{\text{ret}} = m g\,\tfrac{GR-RR}{100}\,v$ (W), which is the energy that
trolley or battery-electric trucks can regenerate. Lifting 1 t through 100 m needs $m g h$ = 0.273 kWh at the wheels,
a physics bound every energy result must respect.

**Baselines.** Electrified options are reported against the diesel case on the same route. IL-1 is compared with a
**pure pursuit + PID** controller over 100 seeded episodes; "beats pure pursuit + PID" only by the decision rule
([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Fuel intensity | L/(t·km) | Diesel litres per cycle ÷ (payload t × loaded haul km), from engine energy ÷ (efficiency × diesel energy density) |
| Energy intensity | kWh/t | $\int F_{\text{req}}\,v\,dt / \eta$ over the cycle, minus regenerated energy, ÷ payload |
| Emissions | kg CO₂e/t | Diesel litres × 2.70 kg CO₂/L (from 10.21 kg CO₂ per US gallon [8]; UNVERIFIED — pinned at specification) + grid kWh × grid factor (user input) |
| Cycle time | min | Segment times from the speed–grade balance plus DES queue and service times |
| IL-1 route success | % of episodes | Episodes that finish the route without collision ÷ 100 seeded episodes |
| IL-1 lateral error | m (RMS) | Distance from the reference path, sampled per control step |
| IL-1 minimum TTC | s | Lowest time-to-collision with the light vehicle per episode |

Rolling-resistance defaults by surface type come from OEM guidance that could not be read from a primary copy; they
are user inputs marked "UNVERIFIED — pinned at specification" until a primary source is fixed.

## Studio tools and artefacts

| Tool | Artefacts it produces for A2 |
|---|---|
| [Isaac Lab](../frameworks/isaac-lab.md) (`studio/isaaclab/`, `st60_il_train`) | IL-1 policy (ONNX MLP < 1 MB), 100-episode evaluation table, rollout clips, sim-to-sim gap vs the TS twin |
| [Newton](../frameworks/newton.md) | Kit-less physics backend of the IL-1 environment |
| [NVENC / FFmpeg](../frameworks/nvenc-ffmpeg.md) (`st56_encode`) | Rollout clip pair (AV1 + H.264) |
| [minephys](../frameworks/minephys.md) `haulage` | Rimpull/retarder, resistance, energy, CO₂, trolley and battery models |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Bingham pit with candidate ramp routes and electrified segments | LIVE | three.js / R3F |
| Simulate | Per-segment energy calculator; drive-system and trolley-length sliders | LIVE | TS port of `minephys.haulage`; Pyodide button |
| Simulate | Grade-constrained A* routing on the DEM | LIVE | TS worker |
| Simulate | IL-1 policy driving the ramp | LIVE | TS twin + ORT-web (< 1 MB) |
| Studio replay | Isaac Lab rollout clips | REPLAY | AV1 + H.264 |
| Charts | Speed vs grade; kWh/t, L/(t·km), CO₂e/t by drive system; IL-1 success, lateral error and TTC with CIs | LIVE / REPLAY | baked tables |
| Context | Question, impact, honesty notes | STATIC | — |

## Assumptions and limits

- **Generic truck.** The truck is a documented parameter set from academic models, not any manufacturer's machine.
- **Emission factors.** The diesel factor is UNVERIFIED until pinned against the primary EPA table; the grid factor is
  a user input with no default claim.
- **Sim-to-sim, not sim-to-real.** IL-1 reports a gap between Isaac Lab and the TS twin. No real truck is driven, and
  tyre fidelity at haul speeds is not validated.
- Validity range: quasi-steady longitudinal dynamics per segment; no tyre wear, road roughness or weather effects.
- Educational comparison of options, not an electrification feasibility study.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/a2.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/a2.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

Isaac Lab steps run in `studio/isaaclab/` (Python 3.12) and hand off ONNX and episode tables by file; see
[Isaac Lab task](../guides/isaac-lab-task.md).

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- kWh/t, L/(t·km) and CO₂e/t for diesel, trolley-assist and battery-electric on the reference ramp, with the energy
  model checked against worked examples and the $m g h$ bound.
- IL-1 over 100 seeded episodes. **Acceptance:** ≥ 95 % route success without collision; RMS lateral error ≤ 0.5 m;
  min TTC ≥ 3 s in ≥ 99 % of episodes; "beats pure pursuit + PID" only by the decision rule; sim-to-sim gap vs the TS
  twin reported.

## In PitStudio

- Recipe `studio/recipes/cases/a2.yaml`; route `/cases/A2`; model card [Isaac Lab policies](../models/isaac-lab-policies.md).
- Shares the haul model with [A1](a1-truck-shovel-dispatch.md) and the routing with [E1](e1-pit-shell-pushbacks.md).

## References

1. IntechOpen. *Improve Energy Efficiency in Surface Mines Using Artificial Intelligence*. DOI
   10.5772/intechopen.101493. https://www.intechopen.com/chapters/79641
2. CIM Magazine. *All in on trolley assist*. https://magazine.cim.org/en/net-zero-challenge/all-in-on-trolley-assist-en/
3. Valenzuela Cruzat, Valenzuela (2018). *Modeling and evaluation of benefits of trolley assist system for mining
   trucks*. IEEE Trans. Ind. Appl. 54(4):3971–3981. DOI 10.1109/tia.2018.2823261
4. Lindgren, Grauers, Ranggård, Mäki (2022). *Drive-cycle simulations of battery-electric large haul trucks with
   electric roads*. Energies 15(13). DOI 10.3390/en15134871
5. Xia et al. (2025). RL path tracking for mining trucks. IEEE Trans. Veh. Technol. DOI 10.1109/TVT.2025.3546647
6. USGS. *About 3DEP Products & Services*. https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
7. Soofastaei et al. (2016). MLP ANN model for haul-truck energy consumption. IJMST 26(2):285–293. DOI
   10.1016/j.ijmst.2015.12.015
8. US EPA (2025). *GHG Emission Factors Hub*. https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf
