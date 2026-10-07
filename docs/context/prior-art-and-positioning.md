# Prior art and positioning

> What already exists for mining simulation and physical AI (commercial tools, open-source projects, academic results,
> NVIDIA's own mining references), the gap PitStudio fills, and what it reuses instead of rewriting. · Part of:
> [context](README.md) · Related: [physical AI and simulation twins](physical-ai-and-simulation-twins.md) ·
> [frameworks](../frameworks/README.md) · [minehaulsim](../frameworks/minehaulsim.md) · [sim-to-real](../theory/sim-to-real.md)

## What and why

A public research product should not rebuild what already exists, and should say plainly where it cannot compete. This
page surveys five kinds of prior art, as of October 2026: uses of the NVIDIA stack in mining, commercial mining
simulators, open-source projects, academic results, and web explainers. It ends with the gap analysis and the
positioning statement that shaped the plan.

The survey has a known weakness: coverage of fleet-management vendors, generic discrete-event-simulation vendors and
slope-radar vendors other than one is thin, and several vendor capability claims could not be read on a primary page.
Those claims are not repeated here.

## The NVIDIA stack applied to mining

- NVIDIA's October 2025 physical-AI blog covers Cosmos Predict 2.5, Cosmos Transfer 2.5, Isaac Sim, Isaac Lab, NuRec,
  OpenUSD and Replicator. Its only mining example is a community member who uses synthetic data to detect boulders that
  jam crushers, described as preventing about USD 650,000 in annual losses; no code or dataset is linked [1].
- The Omniverse product page presents the platform as "libraries, APIs, and services" and has no mining content [2].
- The only full mining digital twin on Omniverse found is a 2022 proprietary product built on custom Omniverse
  extensions and USD, with drone and lidar reality capture synchronised to site telemetry [3].
- A January 2026 equipment-maker announcement describes factory digital twins "built on NVIDIA Omniverse libraries and
  OpenUSD" and an in-cab assistant, without mine-site or haul-truck simulation details [4]. The GTC 2026 announcements
  name warehouse, factory and robotics industries, not mining [5].
- Open Isaac Sim and Isaac Lab excavator repositories exist but are tiny. The most complete one trains dig-and-lift
  policies for a 36 t excavator on Isaac Sim 5.1 and Isaac Lab 2.3.2 with an analytical Fundamental Earthmoving
  Equation (FEE) soil model; its own licence is unclear [6].
- A GitHub repository search for "omniverse mining" returned one unrelated result [7], and an arXiv query for mining
  combined with Isaac Sim, Omniverse or Replicator returned no paper on mineral extraction or excavation built on the
  stack [8]. NVIDIA's public blueprints organisation has no mining blueprint [9].

## Commercial mining simulation and twins

| Product | What it simulates or optimises | Where an open product cannot compete | Where an open product adds value |
|---|---|---|---|
| HAULSIM [10] | 3D discrete-event simulation of mine haulage: interactions, congestion, traffic control, stockpiles, crushers, maintenance; battery-electric, hydrogen and hybrid fleets | Calibrated OEM equipment library, site GPS calibration, support | Transparent equations, reproducible scenarios, coupling to sensor and physics simulation |
| TALPAC-3D [11] | Truck and loader productivity and cost: segment cycle times, rimpull curves, fleet sizing, cost per tonne | A long-validated cycle-time engine | Open rimpull and retarder physics |
| Deswik LHS [12] | Haul cycles calibrated with GPS truck cycles, rolling resistance, fuel and CO₂, dump scheduling, congestion re-routing | Integration with a planning suite | Open fuel and CO₂ models for education |
| GEOVIA Whittle [13] | Pit shells (pseudoflow or Lerchs–Grossmann), pushback optimisation, cut-off and blend optimisation | Industry-standard strategic planning | Open algorithms |
| Datamine Studio OP [14] | Medium- and short-term open-pit design and scheduling | The full CAD and planning workflow | — |
| Simcenter EDEM [15], Ansys Rocky [16] | GPU discrete-element modelling of bulk material: excavators, truck bodies, transfer chutes; blockage, spillage, wear | Calibrated material libraries, millions of particles, CAE coupling | Open GPU granular scenes for education and synthetic data |
| AGX Dynamics terrain [17] | Real-time deformable terrain for shovels, buckets and blades, several soils | Best-in-class real-time earthmoving | Open FEE and MPM approximations with stated error bounds |
| Vortex Studio [18], Immersive Technologies [19] | Real-time multibody earthmoving; operator-training simulators | Operator-training fidelity, OEM-licensed models | — |

**Takeaway.** Each commercial tool is a silo: haulage simulation, planning, bulk-material DEM, operator training,
radar or fleet management. All are closed and calibrated with proprietary data. None of the pages read describes a
camera, lidar or radar sensor simulation → synthetic data → trained model → validation loop for mining. That loop is
exactly what the physical-AI stack is marketed for [1] [2], and it is where an open product can stand.

## Open-source projects

| Project | Licence | What it offers | How PitStudio relates |
|---|---|---|---|
| OpenMines [20] [21] | MIT | Python discrete-event simulation of trucks, shovels, dumps and charging stations, baseline dispatchers (including SPTF) and a Gymnasium environment; reproducibility is its stated contribution | Shows that dispatch RL lives in DES; PitStudio adds GPU-vectorised training and browser-live policies |
| Mining-Gym [22] | paper CC BY-NC-SA | Configurable RL dispatch benchmark with failures and maintenance | Ideas only (non-commercial paper licence) |
| MineFlow [23] | MIT | Pseudoflow for ultimate-pit limits, with sub-blocks | PitStudio writes its own small min-cut with OR-Tools and networkx as oracles |
| `pseudoflow` on PyPI [24] | non-commercial, "not an open-source license" | Pseudoflow implementation | Not used |
| Chrono DEM-Engine [25] [26] | BSD-3 | GPU DEM; Linux and WSL2 wheels only | Not used as the primary engine (no native Windows path) |
| Genesis [27] | Apache-2.0 | Rigid, MPM, SPH, FEM and PBD solvers; requires Python < 3.14 | Not adopted |
| Taichi [28] | Apache-2.0 | GPU kernels; last release 2025-07-31 without Python 3.14 wheels | Not adopted (slowing maintenance) |
| Newton [29], Warp [30], MuJoCo-Warp [31] | Apache-2.0 | GPU physics with implicit MPM for granular material (Newton), differentiable kernels (Warp) | **Adopted** for the open studio lane |
| LIGGGHTS-PUBLIC [32], Yade [33] | GPL-2.0 | CPU DEM | Not linked or vendored (licence) |

Open source has good two-dimensional coverage of dispatch, haulage and pit optimisation, strong generic GPU physics
engines without packaged mining scenes, and a long tail of unlicensed excavator and "mine digital twin" dashboards with
no physics [7].

## Academic evidence, 2019–2026

| Study | What was validated |
|---|---|
| Egli et al. 2022 [34] | Excavation policy trained in simulation with FEE soil and heavy randomisation, tested on a real 12 t excavator |
| Gruetter et al. 2025 [35] | Boulder excavation: 70 % field success versus 83 % for human operators |
| Aoshima and Servin 2024 [36] | Wheel-loader digging: about 10 % sim-to-reality gap; about 5 % loss on controller transfer |
| Servin et al. 2021 [37] | Real-time multiscale terrain within 10–25 % of a high-resolution reference, more than 1000× faster |
| Zhang et al. 2026 [38] | Full-size wheel loader with world-model-guided action selection: scoops 651.8 → 540.6 (−17.1 %); 32/32 episodes versus 29/32 |
| Salas et al. 2024 [39] | Scaled load-haul-dump machine on a muck pile: fill factors 71–94 % |
| Zhang C. et al. 2020 [40] | Multi-agent deep-RL dispatch in an event-based simulator "calibrated in real mines": +5.56 % productivity |
| Kilian et al. 2024 [41] | Synthetic segmentation data for mining → real underground images: IoU 34.15, PQ 32.41 (39.35 / 49.16 on synthetic) |
| Qu et al. 2023 [42] | Review: slow digital-twin adoption in minerals; the term is often misused |

**Pattern.** Earthmoving sim-to-real works with measured gaps of roughly 5–25 % [34]–[37] [39]. Dispatch RL is
evaluated entirely inside discrete-event simulators, each with its own baselines [20] [22] [40], so published gains do
not transfer between papers. Synthetic data for mining perception is thin and weak on real images [41]. No paper found
couples an RTX-rendered USD open-pit scene, sensor simulation and physics in one validated pipeline [8].

## Web explainers: the bar

Open-pit models on public 3D platforms are static meshes without process, physics or data, and several carry
non-commercial licences [43]. The bar for explanation is set elsewhere: interactive explainers where physics runs live in
the page and complexity builds step by step [44] [45]. No public browser app was found that animates a physically
simulated open pit (haulage, loading, bulk flow and sensors) with real numbers.

## Gap analysis and positioning

1. **Nobody applies the Omniverse-class stack to mining in the open.** NVIDIA's own mining evidence is anecdotal or
   closed [1] [3] [4].
2. **Commercial tools are siloed and closed** [10]–[19]. None describes the closed physical-AI loop: sensor-realistic
   scene → synthetic labels → trained model → validation → stated transfer gap.
3. **Open source covers 2-D operations research well** and offers generic GPU physics without mining scenes.
4. **Academia shows earthmoving transfer with known gaps** but little on synthetic-data perception for mining.

PitStudio's positioning statement:

> *An open, reproducible physical-AI laboratory for open-pit mining. A real open pit is described as a USD scene and
> simulated on one workstation GPU: haul trucks on real grades, digging with literature-validated soil models, rock flow,
> and camera, lidar and radar sensors that generate labelled synthetic data. Models are trained on that data and
> evaluated with their sim-to-real gap stated, never hidden. Every number on the website is replayed from, or recomputed
> by, the code in the repository.*

Differentiators: the full loop rather than one silo; error bars against published field results; Apache-2.0 code with
the proprietary runtimes kept outside the repository; a browser explainer held to the interactive-explainer bar; and
reuse of existing haulage and deposit engines instead of rewriting them.

## What PitStudio reuses, borrows or avoids

| Item | Source | Licence | Use |
|---|---|---|---|
| Haulage DES kernel and pit generators | `minehaulsim` 0.12.1 [46] | Apache-2.0 | Reference engine for [M02](../methods/m02-haulage-des.md), with a TypeScript twin that reproduces its event trace ([DEC-0013](../architecture/decisions/DEC-0013-haulage-engine-minehaulsim.md)) |
| Synthetic ore deposits | `oreblocks` 0.5.2 [47] | MIT | Default block models for [E1](../cases/e1-pit-shell-pushbacks.md) |
| FEE soil model for fast randomised digging | Egli 2022 [34]; Salas 2024 [39] | published equations | Re-implemented from the papers; no code copied |
| Sim-to-reality gap as a reported KPI | Aoshima and Servin 2024 [36] | paper | The honesty metric of the robot-learning pages |
| Synthetic-to-real reporting protocol (IoU, PQ on real images) | Kilian 2024 [41] | open-access paper | Template for the fragmentation results |
| GPU granular MPM coupled to rigid bodies | Newton [29] | Apache-2.0 | The open studio lane (native Windows) |
| GPL DEM engines | [32] [33] | GPL-2.0 | Avoided in an Apache-2.0 repository |
| `pseudoflow` (PyPI) | [24] | non-commercial | Avoided |
| Non-commercial 3D pit meshes | [43] | CC BY-NC | Avoided; scenes are procedural on open DEMs |

**Names and marks.** Third-party marks never appear in the repository, product, package or domain names. NVIDIA's brand
guidance asks for no NVIDIA marks in product or domain names and no implied endorsement [48]; the OpenUSD licence denies
use of the licensor's marks [49]. Product names of commercial tools are used only nominatively, as in the table above.
PitStudio also avoids names already taken by open projects, such as OpenMines, Mining-Gym, AutoMine, MineTwin or
MineFlow.

## Assumptions and limits

- The survey reflects pages read in October 2026; vendor capabilities change and several vendor pages were not
  readable, so their claims are omitted.
- "No open project found" is a search result, not a proof of absence.
- An autonomous-mining perception dataset that is often cited (AutoMine, CVPR 2022) could not be reached, so its
  licence and contents are unknown; PitStudio does not rely on it.

## In PitStudio

- The gap defines the product: the [physical-AI loop](physical-ai-and-simulation-twins.md) on twelve
  [cases](../cases/README.md), with every studio tool showing only artefacts it produced
  ([showcase rules](../web/showcase-rules.md)).
- Reused engines have their own framework pages: [minehaulsim](../frameworks/minehaulsim.md),
  [oreblocks](../frameworks/oreblocks.md), [minephys](../frameworks/minephys.md).

## References

1. NVIDIA blog (2025-10-29). Into the Omniverse: open world foundation models generate synthetic worlds for physical AI
   development. https://blogs.nvidia.com/blog/scaling-physical-ai-omniverse/
2. NVIDIA. Omniverse product page. https://www.nvidia.com/en-us/omniverse/
3. NVIDIA blog (2022-11-03). A mining digital twin built on Omniverse (blog post). https://blogs.nvidia.com/blog/skycatch-vision-ai-digital-twins/
4. NVIDIA blog (2026-01-07). CES 2026 equipment-maker announcement. https://blogs.nvidia.com/blog/caterpillar-ces-2026
5. NVIDIA blog (2026-03-26). GTC 2026: virtual worlds and physical AI. https://blogs.nvidia.com/blog/gtc-2026-virtual-worlds-physical-ai/
6. excavator_PIRL repository. https://github.com/duc042103/excavator_PIRL
7. GitHub search API, "omniverse mining". https://api.github.com/search/repositories?q=omniverse+mining
8. arXiv API query: mining AND (Isaac Sim OR omniverse OR replicator).
   http://export.arxiv.org/api/query?search_query=all:mining+AND+(all:%22Isaac+Sim%22+OR+all:omniverse+OR+all:replicator)
9. NVIDIA Omniverse blueprints organisation. https://github.com/NVIDIA-Omniverse-blueprints
10. HAULSIM product page. https://rpmglobal.com/product/haulsim/
11. TALPAC-3D product page. https://rpmglobal.com/product/talpac-3d/
12. Deswik LHS product page. https://www.deswik.com/products/lhs
13. GEOVIA Whittle product page. https://www.3ds.com/products/geovia/whittle
14. Datamine Studio OP documentation. https://docs.dataminesoftware.com/StudioOP/Latest/STUDIO_OP/Introduction.htm
15. Simcenter EDEM product page. https://www.siemens.com/en-us/products/simcenter/fluids-thermal-simulation/edem/
16. Analysis of a transfer chute using Rocky. https://ansys.synopsys.com/academic/educators/education-resources/analysis-of-a-transfer-chute-using-ansys-rocky-software
17. AGX Dynamics, agxTerrain user manual (2.42.3.0).
    https://www.algoryx.se/documentation/complete/agx/tags/latest/doc/UserManual/source/agxTerrain.html
18. Vortex Studio product page. https://www.cm-labs.com/en/vortex-studio/
19. Immersive Technologies OEM range. https://www.immersivetechnologies.com/about/oem_range.htm
20. OpenMines repository. https://github.com/370025263/openmines
21. Meng et al. (2024). OpenMines. IEEE IV 2024. https://arxiv.org/abs/2404.00622
22. Banerjee, Nguyen, Fookes (2025). Mining-Gym. https://arxiv.org/abs/2503.19195
23. MineFlow repository (Deutsch, Dağdelen, Johnson 2022, https://doi.org/10.1007/s11053-022-10035-w).
    https://github.com/MineFlowCSM/MineFlow
24. `pseudoflow` on PyPI. https://pypi.org/pypi/pseudoflow/json
25. Chrono DEM-Engine repository. https://github.com/projectchrono/DEM-Engine
26. `deme` on PyPI. https://pypi.org/pypi/deme/json
27. Genesis on PyPI. https://pypi.org/pypi/genesis-world/json
28. Taichi 1.7.4 on PyPI. https://pypi.org/pypi/taichi/1.7.4/json
29. Newton on PyPI and GitHub. https://pypi.org/pypi/newton/json · https://github.com/newton-physics/newton
30. Warp 1.17.0 on PyPI. https://pypi.org/project/warp-lang/
31. MuJoCo Warp on PyPI. https://pypi.org/pypi/mujoco-warp/json
32. LIGGGHTS-PUBLIC repository. https://github.com/CFDEMproject/LIGGGHTS-PUBLIC
33. Yade repository. https://gitlab.com/yade-dev/trunk
34. Egli et al. (2022). Soil-adaptive excavation using reinforcement learning. *IEEE RA-L.*
    https://doi.org/10.1109/LRA.2022.3189834
35. Gruetter, Terenzi, Egli, Hutter (2025). Towards learning boulder excavation …. https://arxiv.org/abs/2509.17683
36. Aoshima, Servin (2024). Examining the sim-to-reality gap of a wheel loader digging …. *Multibody System Dynamics.*
    https://doi.org/10.1007/s11044-024-10005-5
37. Servin, Berglund, Nystedt (2021). Multiscale model of terrain dynamics for real-time earthmoving. *AMSES.*
    https://doi.org/10.1186/s40323-021-00196-3
38. Zhang et al. (2026). World-model-guided action selection for continuous pile excavation.
    https://arxiv.org/abs/2609.15382
39. Salas, Leiva, Ruiz-del-Solar (2024). Autonomous loading of ore piles with LHD using DRL.
    https://arxiv.org/abs/2409.07449
40. Zhang C. et al. (2020). Dynamic dispatching for large-scale heterogeneous fleet via multi-agent deep reinforcement
    learning. https://arxiv.org/abs/2008.10713
41. Kilian et al. (2024). Synthetic segmentation dataset generator … mining. *Frontiers in AI.*
    https://doi.org/10.3389/frai.2024.1453931
42. Qu, Kizil, Yahyaei, Knights (2023). Digital twins in the minerals industry – a comprehensive review. *Mining
    Technology.* https://doi.org/10.1080/25726668.2023.2257479
43. Sketchfab API search, "open pit mine". https://api.sketchfab.com/v3/search?type=models&q=open%20pit%20mine&downloadable=true
44. Bartosz Ciechanowski, interactive explainers. https://ciechanow.ski/
45. Explorable Explanations. https://explorabl.es/
46. `minehaulsim` on PyPI. https://pypi.org/project/minehaulsim/
47. `oreblocks` on PyPI. https://pypi.org/project/oreblocks/
48. NVIDIA. Logo and brand usage. https://www.nvidia.com/en-us/about-nvidia/legal-info/logo-brand-usage/
49. OpenUSD licence (TOST-1.0). https://raw.githubusercontent.com/PixarAnimationStudios/OpenUSD/dev/LICENSE.txt
