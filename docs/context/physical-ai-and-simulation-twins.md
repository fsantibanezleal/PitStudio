# Physical AI and simulation twins

> What "digital twin", "simulation-grade twin" and "physical AI" mean, the closed loop PitStudio runs (scene → labels →
> model → validation with a stated gap), what the literature says about that gap, and what the Omniverse-class platform
> offers on one workstation in October 2026. · Part of: [context](README.md) · Related:
> [sim-to-real theory](../theory/sim-to-real.md) · [prior art](prior-art-and-positioning.md) ·
> [B2 synthetic perception](../cases/b2-synthetic-perception.md) · [studio](../studio/README.md)

## What and why

Mining is a hard place to collect labelled data. Haul trucks, people and boulders under dust, night and rain are rare,
dangerous or commercially sensitive to photograph; field trials of autonomous machines are expensive. Physical AI
proposes to move part of that work into simulation: build a physically and visually faithful scene, render sensor data
with exact labels, train models on it, and check them in simulation before the field. The promise is only as good as
the measured gap between simulation and reality. PitStudio's contribution is to run the whole loop in the open for
open-pit mining and to **state the gap wherever it can be measured, and say "not measured" wherever it cannot**.

## Three terms that are often confused

| Term | Meaning | Does PitStudio claim it? |
|---|---|---|
| Digital twin | A virtual counterpart linked to a physical system across its lifecycle, synchronised with its operational data [1] [2]. ISO 23247-1:2021 gives a framework for digital twins of observable manufacturing elements (people, equipment, materials, processes, facilities, environment) [3]; mining is outside its stated scope, so it applies here only by analogy | **No.** There is no live data feed from a real operation |
| Simulation-grade twin | PitStudio's term: real geometry from public lidar, governing physics, simulated operations and simulated sensors, validated against analytical results and published or public real data | **Yes**, and every page and web view says so |
| Physical AI | A vendor's term for autonomous systems that perceive, understand, reason and act in the physical world, built by training on real and synthetic data, simulating in 3D, augmenting data and validating in simulation before deployment [4] | **As a method**, applied to mining with the gaps measured |

A 2023 review of digital twins in the minerals industry found slow adoption (geological uncertainty, legacy systems,
cost, skills, cybersecurity, missing standards) and noted that the term is often misused [5]. That is the reason for
the careful wording above.

## The loop

![The physical-AI loop: scene, labels, model, validation](../assets/diagrams/physical-ai-loop.svg)

*The closed loop as PitStudio implements it, with the studio stages and environments of each step; real data enters
only at validation.*

1. **Sensor-realistic scene.** An OpenUSD stage of the pit, built from USGS 3DEP terrain with UsdPhysics bodies and
   UsdSemantics labels, is rendered by RTX camera, lidar and radar models (`studio/rtx` with ovrtx, `studio/isaac` with
   Isaac Sim). Dust attenuation for lidar uses PitStudio's own Beer–Lambert model in `minephys.environment`, calibrated
   to a published mining dust study (see [RTX sensor physics](../theory/rtx-sensor-physics.md)).
2. **Synthetic labels.** Because the scene is known exactly, labels are exact: COCO boxes, instance masks and depth from
   Replicator (`st55_sdg`), point clouds and radar detections from ovrtx (`st53_sensors`), the exact particle-size
   distribution of each synthetic muck pile, and hazard answers computed from USD prims. Domain randomisation comes in
   two arms, structured and unstructured, so its effect can be measured.
3. **Trained model.** The pipeline (`pipeline/`, `s30_train` → `s60_export`) trains detectors, a fragmentation U-Net,
   granular and field surrogates and policies, exports ONNX and checks parity. Cosmos Reason 2 is evaluated zero-shot,
   not trained.
4. **Validation with a stated gap.** `s50_evaluate` scores every model on held-out synthetic data and, where a real
   labelled set exists, on a real test split. The gap report feeds back into the scene and the randomisation ranges.

### Measuring the gap

Two quantities carry the sim-to-real claim. The **TSTR/TRTR ratio** compares a model *trained on synthetic, tested on
real* (TSTR) with the same architecture *trained on real, tested on real* (TRTR), on the same real test split:

$$
\rho = \frac{m_\text{real}(\theta_\text{syn})}{m_\text{real}(\theta_\text{real})}
$$

where $m_\text{real}(\theta)$ is the task metric (for fragmentation, foreground IoU, –) of parameters $\theta$ on the real
test split. PitStudio's pre-registered criterion for fragmentation is $\rho \ge 0.90$. The **classifier two-sample test
(C2ST)** trains a classifier to tell real from synthetic samples; its area under the ROC curve (AUC, –) is 0.5 when the
two are indistinguishable. The thresholds (AUC ≤ 0.60 for tabular data; for images, an AUC gap of at most 0.10 over a
real-vs-real baseline) live in `specs/000-foundation/thresholds.yaml`, and their rationale is on
[sim-to-real](../theory/sim-to-real.md).

## What the literature says about the gap

| Study | Domain | What was validated | Gap or result |
|---|---|---|---|
| Egli et al. 2022 [6] | Excavation | Policy trained in simulation with an analytical soil model and heavily randomised soil parameters, tested on a real 12 t excavator in several soils | Adapts online from proprioception alone |
| Gruetter et al. 2025 [7] | Boulder excavation | Rigid-body plus analytical soil simulation, field trials on a 12 t excavator with 0.4–0.7 m rocks | 70 % success versus 83 % for human operators |
| Aoshima and Servin 2024 [8] | Wheel-loader digging | DEM soil at several resolutions against field tests | About 10 % gap; a simulation-trained controller lost about 5 % on transfer |
| Servin et al. 2021 [9] | Real-time earthmoving | Multiscale terrain model against a high-resolution reference | Within 10–25 % on digging resistance, more than 1000× faster |
| Salas et al. 2024 [10] | Ore-pile loading | Low-cost FEE-based simulation, then a scaled LHD and muck pile | Fill factors of 71–94 % |
| Kilian et al. 2024 [11] | Mining perception | Synthetic segmentation data (329 images) tested on real underground images | Real IoU 34.15 and PQ 32.41, versus 39.35 and 49.16 on synthetic |

The pattern is clear. **Earthmoving control transfers from simulation with measured gaps of roughly 5–25 %**
[6]–[10]. **Synthetic-only perception for mining is under-explored and weak on real images** [11]. PitStudio therefore
measures sim-to-real only where it has real labels and reports sim-to-sim gaps where it does not (for example, an
excavator policy trained on an analytical soil model and checked zero-shot in a GPU material-point model).

## The Omniverse-class platform in October 2026

"Omniverse" is now a set of libraries rather than a launcher-installed suite. NVIDIA's product page lists OpenUSD,
ovrtx (RTX rendering and sensor simulation), ovphysx (physics), SimReady (asset validation) and agent skills [12]. The
Omniverse Launcher and Nucleus Workstation were deprecated on 1 October 2025; USD Composer and USD Explorer remain
supported as apps built from kit-app-template [13]. Omniverse became free for production use and redistribution
"under the same terms": the licensing change was effective May 2026 and announced on 1 July 2026 [14] [15].

Versions below are read from PitStudio's lock files.

| Tool | Version | Role in PitStudio | Environment | Licence class |
|---|---|---|---|---|
| OpenUSD (`usd-core`) | 26.8 | Pit scenes from real lidar | `studio/` (3.14) | dependency licence TOST-1.0 (not OSI) |
| Warp | 1.17.0 | Own DEM, shallow water, dust particles, differentiable calibration | `studio/` | open (Apache-2.0) |
| Newton (+ MuJoCo-Warp) | 1.6.0 (+ 3.12.0) | Implicit MPM granular flow, rigid trucks, articulated machines | `studio/` | open (Apache-2.0) |
| Isaac Sim + Replicator | 6.1.0.0 | RTX renders, synthetic data, PhysX vehicle visual twin | `studio/isaac` (3.12) | reference-only |
| ovrtx / ovstage / ovphysx | 0.5.0.377615 / 0.2.0.377349 / 0.6.3 | Kit-less RTX camera, lidar, radar | `studio/rtx` (3.12) | reference-only |
| Isaac Lab | 3.0.0-EA (git tag) | Robot learning for haul trucks and excavators | `studio/isaaclab` (3.12) | open (BSD-3) |
| USD Composer / Explorer (Kit 110.3) | generated outside the repo | Scene review, path-traced media | `studio/kit` (our extension only) | reference-only |
| Cosmos Reason 2 (2B) | official revision, own Q8_0 conversion | Vision-language safety questions | `studio/reason` (llama.cpp) | weights never redistributed |
| PyTorch | 2.14.1 (cu130) | Training | `pipeline/` (3.14) | open |
| TensorRT | 11.3.0.99 | Accelerated inference of our models | `pipeline/accel` (3.14) | reference-only |

Two NVIDIA world models do not fit the reference machine: Cosmos-Predict2.5-2B lists 32.54 GB of GPU memory and Linux
only [16], and the Cosmos-Reason2-2B model card lists 24 GB and Linux [17]. A quantised Cosmos-Reason2-2B (Q8_0 GGUF
through llama.cpp) is listed for an 8 GB Jetson Orin Nano [18], which is why PitStudio runs its own quantised conversion
natively on Windows; its fit and its agreement with the BF16 reference are measured, not assumed
([DEC-0009](../architecture/decisions/DEC-0009-vlm-llamacpp-gguf.md)). Cosmos Predict and Transfer are documented as
[evaluated, not adopted](../frameworks/not-adopted-cosmos-predict-transfer.md).

## Honesty rules PitStudio applies to the loop

- **Measured sim-to-real only where real labels exist.** The fragmentation U-Net is trained on synthetic muck piles and
  on real labelled rock-fragment images (Mendeley Data, CC BY 4.0) and tested on the same real split. The real set is
  960 images that are 240 originals × 4 augmentations, so it is split by source group (231 groups after conservatively
  merging 9 visually similar originals) and evaluated on the originals only; see the
  [dataset card](../data-contract/dataset-cards/mendeley-rock-fragments.md).
- **"Not measured" where no real labels exist.** Equipment and people detection is trained on synthetic data only. Its
  real-domain gap is reported as **not measured** unless the optional real probe (at most 200 licence-clean images,
  labelled by two people) is created.
- **One real event is one data point.** The de Wit slope-failure radar series is a single real event ($n = 1$). It is
  used for a descriptive time-of-failure error, never for TSTR/TRTR or a significance test.
- **Calibrated synthetic is labelled.** A data type with no real reference (dust fields, haul telemetry, equipment
  images without the probe) is shown as "calibrated synthetic — not validated against real data".
- **"Better" needs a confidence interval.** A learned model is called better than its classical baseline only if the
  paired 95 % confidence interval of the difference excludes zero
  ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).
- **Model outputs with attribution duties stay display-only.** Cosmos answers carry "Built on NVIDIA Cosmos" and the
  licence notice, and are never a headline KPI.

## Assumptions and limits

- The loop is closed in simulation and opened to reality only through public real data. Without a real labelled set,
  a sim-to-real claim is not made.
- Domain randomisation ranges are design choices; the ablation measures their effect on synthetic held-out data, not
  on the real world.
- Platform facts (versions, VRAM, deprecations, licences) are dated October 2026 and pinned in lock files; NVIDIA's
  pre-release libraries (ovrtx, ovphysx, Isaac Lab EA) may change their APIs.

## In PitStudio

- **Cases.** [B2](../cases/b2-synthetic-perception.md) runs the full perception loop; [D1](../cases/d1-blast-muck-pile.md)
  is the one case with a measured sim-to-real ratio; [A3](../cases/a3-loading-payload-variance.md) and
  [M21](../methods/m21-isaac-lab-policies.md) report sim-to-sim gaps; [M22](../methods/m22-cosmos-vlm-tasks.md) scores a
  vision-language model against exact scene truth.
- **Status: Not yet run** — produced in the data-and-models phase. What will be reported, with the criteria fixed in
  advance:
  - fragmentation U-Net: synthetic held-out $x_{50}$ relative error ≤ 15 %; real test split $\rho \ge 0.90$ (IoU);
  - detectors: synthetic held-out mAP50 ≥ 0.80 (D-FINE-S) and ≥ 0.70 (D-FINE-N); relative drop ≤ 10 percentage points
    at corruption severity ≤ 2; "structured randomisation is better" only by the decision rule;
  - Cosmos Reason 2: Q8_0 versus BF16 agreement ≥ 95 % on binary questions; "better than the Qwen3-VL base" only if
    McNemar $p < 0.05$.

## References

1. Grieves, M., Vickers, J. (2017). Digital twin: mitigating unpredictable, undesirable emergent behavior in complex
   systems. https://doi.org/10.1007/978-3-319-38756-7_4
2. Fuller, A. et al. (2020). Digital twin: enabling technologies, challenges and open research. *IEEE Access.*
   https://doi.org/10.1109/access.2020.2998358
3. ISO 23247-1:2021. Automation systems and integration — Digital twin framework for manufacturing — Part 1: Overview
   and general principles. https://www.sis.se/en/produkter/manufacturing-engineering/industrial-automation-systems/industrial-process-measurement-and-control/iso-23247-12021/
4. NVIDIA. Glossary: generative physical AI. https://www.nvidia.com/en-us/glossary/generative-physical-ai/
5. Qu, Kizil, Yahyaei, Knights (2023). Digital twins in the minerals industry – a comprehensive review. *Mining
   Technology.* https://doi.org/10.1080/25726668.2023.2257479
6. Egli, P. et al. (2022). Soil-adaptive excavation using reinforcement learning. *IEEE Robotics and Automation
   Letters.* https://doi.org/10.1109/LRA.2022.3189834
7. Gruetter, Terenzi, Egli, Hutter (2025). Towards learning boulder excavation …. https://arxiv.org/abs/2509.17683
8. Aoshima, K., Servin, M. (2024). Examining the sim-to-reality gap of a wheel loader digging …. *Multibody System Dynamics.* https://doi.org/10.1007/s11044-024-10005-5
9. Servin, M., Berglund, T., Nystedt, S. (2021). Multiscale model of terrain dynamics for real-time earthmoving. *Advanced Modeling and Simulation in Engineering Sciences.* https://doi.org/10.1186/s40323-021-00196-3
10. Salas, Leiva, Ruiz-del-Solar (2024). Autonomous loading of ore piles with LHD using DRL. https://arxiv.org/abs/2409.07449
11. Kilian et al. (2024). Synthetic segmentation dataset generator … mining. *Frontiers in Artificial Intelligence.*
    https://doi.org/10.3389/frai.2024.1453931
12. NVIDIA. Omniverse product page. https://www.nvidia.com/en-us/omniverse/
13. NVIDIA. Omniverse legacy tools. https://developer.nvidia.com/omniverse/legacy-tools
14. NVIDIA Developer Forums (2026-07-01). NVIDIA Omniverse licensing change.
    https://forums.developer.nvidia.com/t/nvidia-omniverse-licensing-change/375138
15. NVIDIA Developer Forums, thread 377476 (2026-07-24), staff quote of the licensing page.
    https://forums.developer.nvidia.com/t/clarification-on-charging-customers-for-software-built-with-omniverse/377476
16. NVIDIA. Cosmos-Predict2.5-2B model card. https://huggingface.co/nvidia/Cosmos-Predict2.5-2B
17. NVIDIA. Cosmos-Reason2-2B model card. https://huggingface.co/nvidia/Cosmos-Reason2-2B
18. NVIDIA Jetson AI Lab. Cosmos-Reason2-2B. https://www.jetson-ai-lab.com/models/cosmos-reason2-2b/
