# Theory

> The science behind PitStudio: governing equations from primary sources, derivations, worked examples, validity
> ranges and limits, one page per phenomenon. · Part of: [Documentation](../README.md) · Related:
> [Methods](../methods/README.md), [Cases](../cases/README.md), [Knowledge base](../knowledge/README.md)

## Map

| Page | Phenomena and core equations | Methods | Cases |
|---|---|---|---|
| [Haulage](haulage.md) | rolling + grade resistance, rimpull and retarder curves, travel-time integration, energy, fuel and CO₂ per t·km, trolley and battery-electric haulage, match factor, M/M/c and finite-source queues, mean-value analysis, DES | [M1](../methods/m01-match-factor-queueing.md), [M2](../methods/m02-haulage-des.md), [M3](../methods/m03-lp-dispatch.md), [M6](../methods/m06-haul-road-energy-routing.md) | A1, A2, A3 |
| [Loading and terramechanics](loading-and-terramechanics.md) | bucket fill, passes per truck, payload variance, fundamental earthmoving equation with the wedge derivation | [M7](../methods/m07-gpu-granular-physics.md), [M21](../methods/m21-isaac-lab-policies.md) | A3 |
| [Drill and blast](drill-and-blast.md) | powder factor, Kuz-Ram, KCO and Swebrec size distributions, PPV scaled-distance law, flyrock ballistics, validity ranges | [M11](../methods/m11-fragmentation-segmentation.md), [M12](../methods/m12-blast-fragmentation-models.md) | D1, D2 |
| [Slopes and monitoring](slopes-and-monitoring.md) | Bishop, Janbu and Spencer limit equilibrium, generalised Hoek–Brown, Monte-Carlo probability of failure, slope radar, Voight/Fukuzono inverse velocity, Bayesian time to failure | [M13](../methods/m13-slope-stability-lem.md), [M14](../methods/m14-slope-forecasting.md) | C1 |
| [Bulk flow, DEM and MPM](bulk-flow-dem-mpm.md) | Hertz–Mindlin contact with rolling resistance, DEM time step, MPM with Drucker–Prager and μ(I), angle of repose, Beverloo discharge, CEMA conveyors, Gy blending and sampling | [M7](../methods/m07-gpu-granular-physics.md), [M8](../methods/m08-gns-surrogate.md), [M9](../methods/m09-differentiable-dem-calibration.md) | A3, D1 |
| [Comminution](comminution.md) | Bond's law, Morrell SMC model, population balance, Klimpel flotation kinetics, two-product balance, mine-to-mill coupling | [M17](../methods/m17-comminution-mine-to-mill.md) | D2 |
| [Dust](dust.md) | AP-42 §13.2.2 unpaved-road emission factor with coefficients and validity ranges, watering control efficiency, Gaussian plume, Lagrangian particles, Beer–Lambert attenuation | [M16](../methods/m16-dust-dispersion.md), [M15](../methods/m15-shallow-water-fno.md) | C3 |
| [Tailings](tailings.md) | depth-averaged shallow-water equations with a Bingham bed stress, dam-break verification, empirical run-out regressions, pit flooding | [M15](../methods/m15-shallow-water-fno.md) | C2 |
| [Planning](planning.md) | block economic value, ultimate pit as a maximum closure solved by minimum cut, nested shells and pushbacks, Lane cut-off grade, time-indexed MILP scheduling | [M18](../methods/m18-pit-optimisation-scheduling.md), [M6](../methods/m06-haul-road-energy-routing.md) | E1 |
| [RTX sensor physics](rtx-sensor-physics.md) | lidar range equation, Beer–Lambert extinction in dust and rain, camera exposure and haze, 77 GHz radar range and Doppler, ground-based interferometric slope radar | [M23](../methods/m23-rtx-sensor-simulation.md), [M10](../methods/m10-synthetic-data-detector.md) | B1, B2, C1, C3, E2 |
| [Robot learning](robot-learning.md) | Markov decision processes, PPO with generalised advantage estimation, domain randomisation, haul-truck and excavator task design, vectorised training, sim-to-sim gap | [M4](../methods/m04-ppo-dispatch.md), [M5](../methods/m05-attention-fleet-policy.md), [M21](../methods/m21-isaac-lab-policies.md) | A1, A2, A3 |
| [Vision-language reasoning](vision-language-reasoning.md) | vision-language models, quantisation checks against the full-precision original, hazard questions scored against exact scene truth, plausibility tests, caption hallucination, McNemar's test | [M22](../methods/m22-cosmos-vlm-tasks.md) | B1, B2 |
| [Sim-to-real](sim-to-real.md) | classifier two-sample tests, train-synthetic/test-real vs train-real/test-real, embedding tests, corruption robustness, the honesty rule for data without a real reference, the pre-registered decision rule | [M10](../methods/m10-synthetic-data-detector.md), [M11](../methods/m11-fragmentation-segmentation.md), [M21](../methods/m21-isaac-lab-policies.md) | B2, D1 |

Case pages: [A1](../cases/a1-truck-shovel-dispatch.md), [A2](../cases/a2-haul-road-electrification.md),
[A3](../cases/a3-loading-payload-variance.md), [B1](../cases/b1-traffic-proximity.md),
[B2](../cases/b2-synthetic-perception.md), [C1](../cases/c1-slope-time-of-failure.md),
[C2](../cases/c2-tailings-breach.md), [C3](../cases/c3-dust.md), [D1](../cases/d1-blast-muck-pile.md),
[D2](../cases/d2-mine-to-mill.md), [E1](../cases/e1-pit-shell-pushbacks.md), [E2](../cases/e2-survey-reconciliation.md).

## Reading paths

- **Haulage and energy:** [Haulage](haulage.md) → [Loading and terramechanics](loading-and-terramechanics.md) →
  [Robot learning](robot-learning.md).
- **Drill-blast-to-mill:** [Drill and blast](drill-and-blast.md) → [Bulk flow, DEM and MPM](bulk-flow-dem-mpm.md) →
  [Comminution](comminution.md).
- **Geotechnical and environmental risk:** [Slopes and monitoring](slopes-and-monitoring.md) →
  [Tailings](tailings.md) → [Dust](dust.md).
- **Physical AI:** [RTX sensor physics](rtx-sensor-physics.md) → [Robot learning](robot-learning.md) →
  [Vision-language reasoning](vision-language-reasoning.md) → [Sim-to-real](sim-to-real.md).
- **Planning:** [Planning](planning.md) → [Haulage](haulage.md) (haul distance and lift per period).

## Conventions on every page

- **Sources.** Every equation carries its primary source as a numbered reference with a DOI or URL. Where the primary
  text could not be read when the page was written, the transcription is tagged *(UNVERIFIED — pinned at
  specification)*: the specification phase pins it against the primary source or a worked example before it becomes a
  constant in `minephys`, and the web UI flags unverified table rows.
- **Derivations** are marked *derived here* or *arithmetic* when they follow from the stated equations rather than from
  a source.
- **Worked examples** use numbers from the cited sources or inputs labelled *illustrative*. Illustrative inputs are
  teaching values, never data about a real operation.
- **Units** are SI unless a source defines a quantity in US customary units (AP-42, 30 CFR); then both are given.
- **Limits.** PitStudio is a simulation-grade twin, not a live digital twin of an operation, and it is educational,
  not design or regulatory software. Each page lists its assumptions and validity ranges.
- **Status.** Nothing has been trained or rendered yet. The "In PitStudio" section of each page says where the theory
  is implemented, in which compute lane, and which pre-registered acceptance criteria will be reported in the
  data-and-models phase.

The cited parameter tables and equations are also published as code in the companion library
[minephys](../frameworks/minephys.md); the [knowledge base](../knowledge/README.md) is generated from it.
Third-party product names (for example Warp, Newton, Isaac Lab and Cosmos) are used nominatively; PitStudio is not
affiliated with or endorsed by NVIDIA or any other vendor named here.
