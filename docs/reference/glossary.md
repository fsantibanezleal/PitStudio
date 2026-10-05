# Glossary

> The terms used across PitStudio's docs, code and web app, in English and Spanish, with a one-line definition and a
> primary source where one exists — mining, simulation and physics, machine learning and data, the NVIDIA stack, and
> the studio and web. · Part of: [Reference](README.md) · Related: [knowledge](../knowledge/README.md) ·
> [theory](../theory/README.md) · [FAQ](faq.md)

## What and why

PitStudio mixes four vocabularies that rarely meet: open-pit mining engineering, numerical simulation, machine
learning, and the NVIDIA physical-AI stack. This glossary fixes one meaning per term so the docs, the code and the web
app use them consistently, and gives the Spanish term used in the web app's Spanish locale. Spanish terms follow
common Latin American mining usage (Chile and Peru: *tronadura*, *chancado*, *relaves*); where Spain differs, the
alternative is in parentheses. Bracketed numbers point to the references at the end.

The web app's `/knowledge` glossary is generated from the `minephys` knowledge tables in the build phase
([knowledge](../knowledge/README.md)); this page also covers the stack and process terms that do not belong in a
mining library.

## Open-pit mining

| EN term | ES term | Definition |
|---|---|---|
| Angle of repose | Ángulo de reposo | Steepest stable slope of a loose granular pile; the standard bulk test used to calibrate DEM parameters [16] |
| AP-42 | AP-42 | US EPA compilation of air-emission factors; section 13.2.2 gives dust emitted per vehicle distance on unpaved roads [23] |
| Bank density | Densidad in situ (en banco) | Density of rock or soil in place, before it is broken |
| Battery-electric truck (BEV) | Camión eléctrico a batería | Haul truck driven by electric motors from an on-board battery, possibly charged from trolley lines [25] |
| Bench | Banco | Horizontal step of a pit wall between a crest and a toe, on which equipment works |
| Berm | Berma | Ledge or windrow on a bench or road edge that catches rockfall or stops vehicles |
| Blast design | Diseño de tronadura (voladura) | Hole diameter, burden, spacing, charge and timing of a blast |
| Block model | Modelo de bloques | 3D grid of blocks carrying grade, density and value; the input to pit optimisation |
| Burden | Burden (piedra) | Distance from a blast hole to the free face, or between rows of holes |
| Comminution | Conminución | Size reduction of ore by crushing and grinding; its energy follows Bond's or Morrell's laws [17] |
| Crushing | Chancado (trituración) | Coarse size reduction in crushers |
| Cut-off grade | Ley de corte | Grade that separates ore from waste; Lane's theory balances mine, mill and market capacity [21] |
| Cycle time | Tiempo de ciclo | One truck round trip: spot, load, haul, dump, return, plus queueing at the loader and the dump |
| Dispatch | Despacho | Real-time assignment of trucks to loaders and dumps |
| Fill factor | Factor de llenado | Payload volume over the rated heaped bucket volume; the main link between blasting and loading |
| Fleet sizing | Dimensionamiento de flota | Choosing the number of trucks and loaders for a production target |
| Flotation | Flotación | Separation of valuable minerals by attachment to air bubbles; first-order and Klimpel kinetics describe recovery over time [26] |
| Flyrock | Proyección de rocas | Rock thrown beyond the blast area; best predicted by ballistic flight with drag from the launch velocity [6] |
| Fragmentation | Fragmentación | Size distribution of blasted rock |
| Grade resistance | Resistencia por pendiente | Part of a truck's total resistance due to road slope, ≈ 100·sin θ percent of gross vehicle weight [1] |
| Grinding | Molienda | Fine size reduction in mills (SAG, ball) |
| Haul road | Camino de acarreo (rampa) | Road on which trucks carry material out of the pit |
| Haul truck | Camión de extracción (CAEX) | Off-highway truck that carries rock from loaders to dumps or the crusher |
| KCO model | Modelo KCO | Kuznetsov–Cunningham–Ouchterlony: Kuznetsov's mean fragment size with a Swebrec size distribution [5] |
| Kuz-Ram model | Modelo Kuz-Ram | Kuznetsov's mean fragment size with a Rosin–Rammler distribution and Cunningham's uniformity index [4] |
| Life of mine (LOM) | Vida de la mina | The planned production period of a mine |
| Match factor | Factor de acoplamiento (match factor) | Truck arrival rate over loader service rate, $MF = N_T t_L / (N_L T_c)$; below 1 loaders wait, above 1 trucks queue [2] |
| Mine-to-mill | Mina-planta (mine-to-mill) | Designing blasts with downstream crushing and grinding energy and throughput in view |
| Muck pile | Pila de material tronado (marina) | Broken rock left by a blast, ready to load |
| Ore / waste | Mineral / estéril (lastre) | Material processed at a profit / material mined but not processed |
| P80, x50 | P80, x50 | Size through which 80 % / 50 % of the mass passes |
| Payload | Carga útil | Mass carried in one truck load |
| Peak particle velocity (PPV) | Velocidad peak de partícula (VPP) | Peak ground-vibration velocity from blasting; US surface-mining limits are 1.25, 1.00 and 0.75 in/s by distance band [8] |
| Powder factor | Factor de carga | Explosive mass per volume of rock blasted, kg/m³ |
| Pushback | Fase (expansión) | Planned enlargement stage of the pit |
| Reconciliation | Conciliación | Comparing planned with surveyed volumes or tonnes |
| Recovery | Recuperación | Fraction of the valuable metal in the feed that reports to the concentrate |
| Retarder | Retardador | Brake that holds a loaded truck's speed on a downgrade; on electric trucks its energy can be recovered [24] |
| Rimpull | Fuerza en llanta (rimpull) | Tractive force available at the driven wheels |
| Rolling resistance | Resistencia a la rodadura | Resistance from tyre and road deformation, expressed as a percentage of gross vehicle weight [1] |
| SAG mill | Molino SAG | Semi-autogenous grinding mill, in which the ore itself is part of the grinding media |
| Spacing | Espaciamiento | Distance between adjacent holes in a row |
| Strip ratio | Razón estéril/mineral (REM) | Tonnes of waste mined per tonne of ore |
| Swebrec function | Función Swebrec | Three-parameter fragment-size distribution ($x_{50}$, $x_{\max}$, $b$) that links blasting and crushing [7] |
| Swell | Esponjamiento | Volume increase when rock is broken; $\rho_{\text{loose}} = \rho_{\text{bank}}/(1+s_w)$ |
| Tailings | Relaves (colas) | Fine waste from mineral processing, stored behind a tailings dam |
| Tailings dam breach | Rotura de tranque de relaves | Failure of a tailings dam and the run-out of the released tailings |
| Trolley assist | Asistencia trolley | Overhead power lines that drive electric-drive trucks uphill; one model of a copper mine found 85 % fuel saving per up–down cycle [24] |
| Ultimate pit | Pit final | Pit limit of maximum total value; the maximum closure of the block-precedence graph, solvable as a minimum cut [19][20] |
| Work index (Bond) | Índice de trabajo de Bond | Material constant of Bond's law of comminution energy, in kWh/t [17] |

## Geotechnics and environment

| EN term | ES term | Definition |
|---|---|---|
| Factor of safety (FoS) | Factor de seguridad (FS) | Available shear strength over mobilised shear stress along a slip surface, minimised over surfaces |
| GB-InSAR | GB-InSAR (interferometría radar terrestre) | Ground-based interferometric radar that measures line-of-sight displacement of a slope |
| Gaussian plume | Pluma gaussiana | Closed-form concentration downwind of a continuous source; Pasquill stability classes A–F set the spread [22] |
| Geological Strength Index (GSI) | Índice de resistencia geológica (GSI) | Rating of rock-mass structure and surface condition used by the Hoek–Brown criterion [11] |
| Hoek–Brown criterion | Criterio de Hoek–Brown | Non-linear rock-mass strength with parameters from GSI and the disturbance factor $D$ [11] |
| InSAR / EGMS | InSAR / EGMS | Satellite radar interferometry / the European Ground Motion Service's deformation products |
| Inverse velocity | Velocidad inversa | $1/v$ plotted against time; its linear extrapolation to zero estimates the time of failure [12] |
| Limit equilibrium method (LEM) | Método de equilibrio límite | Slope stability by slices: Bishop (moment equilibrium), Janbu (force), Spencer (both) [9][10] |
| PM10 | MP10 | Particulate matter with aerodynamic diameter ≤ 10 µm |
| Probability of failure (PoF) | Probabilidad de falla | Share of Monte-Carlo realisations with FoS < 1 |
| Slope radar | Radar de monitoreo de taludes | Ground-based radar that tracks wall movement for early warning and time-of-failure analysis [13] |
| Time to failure (TTF) | Tiempo a la falla | Forecast time at which an accelerating slope fails |
| Voight relation | Relación de Voight | Accelerating-creep law $\ddot\Omega = A\dot\Omega^{\alpha}$ for the last stage before failure [14] |

## Simulation and physics

| EN term | ES term | Definition |
|---|---|---|
| Beer–Lambert law | Ley de Beer–Lambert | Exponential attenuation of light through an absorbing or scattering medium; PitStudio's dust-in-lidar model |
| Bingham fluid | Fluido de Bingham | Material that flows only above a yield stress; a rheology for tailings run-out |
| DEM (discrete element method) | Método de elementos discretos (MED/DEM) | Contact-by-contact simulation of particles [15] |
| DEM (digital elevation model) | Modelo digital de elevación (MDE) | Raster of terrain heights; the context tells it apart from the discrete element method |
| Determinism class | Clase de determinismo | PitStudio's per-stage label: `bitwise`, `statistical` or `none` |
| Differentiable simulation | Simulación diferenciable | Simulation whose outputs have gradients with respect to its parameters, used for calibration |
| Discrete-event simulation (DES) | Simulación de eventos discretos (SED) | Simulation that jumps between events (arrive, load, dump); the industry check for haulage |
| Fundamental Earthmoving Equation (FEE) | Ecuación fundamental del movimiento de tierras | Quasi-static soil-cutting force on a tool from soil weight, cohesion, adhesion and surcharge [18] |
| Hertz–Mindlin contact | Contacto Hertz–Mindlin | Standard soft-sphere DEM contact law: Hertz normal force, Mindlin–Deresiewicz tangential force |
| Material point method (MPM) | Método del punto material (MPM) | Particles carry the material state while a background grid solves momentum; suited to large deformation and tool–material contact [27] |
| Mean value analysis (MVA) | Análisis de valor medio | Exact recursion for throughput and waiting in closed queueing networks |
| Population balance model (PBM) | Modelo de balance poblacional | Grinding as a rate process over size classes [28] |
| Queueing (M/M/c, finite-source) | Teoría de colas | Analytical waiting models; truck–shovel systems are finite-source (closed) queues [3] |
| Shallow-water equations | Ecuaciones de aguas someras | Depth-averaged free-surface flow equations, used for dam-break and run-out |
| Sim-to-real gap | Brecha simulación-realidad | Performance difference between a model evaluated in simulation and on real data |
| Sim-to-sim gap | Brecha entre simuladores | Performance difference of the same policy or model across two simulators |
| Simulation-grade twin | Gemelo de grado simulación | PitStudio's term for a twin built from public data and models, not synchronised with a live operation |
| Digital twin | Gemelo digital | A virtual counterpart linked to a physical system across its life cycle |
| Physical AI | IA física | Systems that perceive, reason and act in the physical world, trained with simulation and synthetic data |
| Surrogate model | Modelo sustituto | A fast learned model that approximates a slow simulator |
| Graph Network Simulator (GNS) | Simulador de redes de grafos (GNS) | Learned particle simulator based on message passing over a particle graph |
| Fourier neural operator (FNO) | Operador neuronal de Fourier (FNO) | Learned operator that maps fields to fields through truncated Fourier modes |
| Lidar | Lidar | Laser ranging sensor that returns a point cloud |
| Time to collision (TTC) | Tiempo a colisión (TTC) | Time until two vehicles collide if both keep their current velocities |
| Near miss | Cuasi accidente | Event that could have caused harm but did not |

## Machine learning and data

| EN term | ES term | Definition |
|---|---|---|
| C2ST | Prueba de dos muestras con clasificador (C2ST) | Train a classifier to tell real from synthetic; AUC near 0.5 means indistinguishable [31] |
| Corruption robustness | Robustez ante corrupciones | Performance under controlled image corruptions (noise, blur, weather) at graded severities [32] |
| Decision rule (pre-registered) | Regla de decisión (pre-registrada) | "Better" only when the paired 95 % confidence interval of the difference excludes 0 |
| Domain randomisation (DR) | Aleatorización de dominio | Randomise textures, lights and poses so widely that reality looks like one more variation [29] |
| GGUF | GGUF | llama.cpp's single-file model format, used for quantised weights |
| Grouped k-fold | Validación cruzada agrupada | Cross-validation in which near-duplicates share a group, so they never span train and test |
| Hallucination | Alucinación | A model output that mentions something absent from the input |
| Held-out set | Conjunto reservado | Data never used for training or tuning, used only for the final evaluation |
| IoU | Intersección sobre unión (IoU) | Overlap of predicted and true masks or boxes over their union |
| mAP50 | mAP50 | Mean average precision at an IoU threshold of 0.5 |
| McNemar's test | Prueba de McNemar | Paired test for two classifiers' disagreements on the same items |
| ONNX | ONNX | Open model-exchange format; *opset* versions the operators, *IR version* the file format |
| Parity | Paridad | Agreement of two implementations of one model within a stated tolerance |
| Policy | Política | The mapping from observations to actions learned by reinforcement learning |
| PPO | Optimización de política proximal (PPO) | Policy-gradient RL algorithm with a clipped update |
| Quantisation | Cuantización | Lower-precision weights and activations (fp16, int8, fp8, Q8_0) for speed and size |
| Reinforcement learning (RL) | Aprendizaje por refuerzo | Learning a policy from rewards by interacting with an environment |
| Structured domain randomisation | Aleatorización de dominio estructurada | Randomisation drawn from the scene's own context [30] |
| Synthetic data / SDG | Datos sintéticos / generación de datos sintéticos | Labelled data rendered or simulated rather than collected |
| TSTR / TRTR | Entrenar en sintético, evaluar en real / entrenar y evaluar en real | Train-on-synthetic-test-on-real against the train-on-real baseline [33] |
| Vision-language model (VLM) | Modelo de visión y lenguaje | Model that answers text questions about images or video |

## NVIDIA stack and other tools

| EN term | ES term | Definition |
|---|---|---|
| Compatibility Checker | Verificador de compatibilidad | NVIDIA's tool that checks a machine against Isaac Sim's requirements |
| Cosmos Reason 2 | Cosmos Reason 2 | NVIDIA's vision-language reasoning model (2B), a post-trained Qwen3-VL; open weights under the NVIDIA Open Model License |
| Isaac Lab | Isaac Lab | BSD-3 robot-learning framework; version 3.0 runs "kit-less" on Newton |
| Isaac Sim | Isaac Sim | NVIDIA's robotics simulator on Kit: RTX rendering, PhysX, sensors; proprietary, reference-only in PitStudio |
| Kit | Kit | NVIDIA Omniverse's application framework; USD Composer and USD Explorer are Kit apps generated from kit-app-template |
| Kit-less | Sin Kit | Running a library (Isaac Lab, ovrtx, ovphysx) without starting a Kit application |
| MuJoCo-Warp | MuJoCo-Warp | GPU port of the MuJoCo physics engine on Warp, used through Newton |
| Newton | Newton | Apache-2.0 GPU physics engine on Warp (rigid, articulated, MPM granular) |
| NVENC | Codificador NVENC | The GPU's hardware video encoder |
| NVML | NVML | NVIDIA Management Library: GPU telemetry (memory, power, clocks, throttle reasons) |
| NVTX | NVTX | Annotations that mark code ranges on profiler timelines |
| Nsight Systems | Nsight Systems | NVIDIA's system-wide profiler; captures kernels and NVTX ranges |
| OpenUSD | OpenUSD | Universal Scene Description: a *stage* composed of *layers* of *prims*, with *variant sets* for alternatives |
| ovphysx / PhysX | ovphysx / PhysX | NVIDIA's PhysX SDK (BSD-3) and its kit-less Python packaging |
| ovrtx | ovrtx | NVIDIA's kit-less RTX sensor and rendering library (camera, lidar, radar) |
| Replicator | Replicator | Isaac Sim's synthetic-data framework: randomisers, annotators, writers |
| TensorRT / engine | TensorRT / motor | NVIDIA's inference optimiser; an *engine* is a model compiled for one GPU and TensorRT version |
| TensorRT for RTX | TensorRT for RTX | A separate TensorRT variant whose licence forbids publishing benchmark data without permission |
| Throttle reasons | Motivos de reducción de reloj | NVML bitmask of why clocks are reduced: power cap, thermal slowdown, idle |
| Warp | Warp | NVIDIA's Apache-2.0 Python framework for GPU kernels, with automatic differentiation |
| WDDM | WDDM | Windows' display driver model; under it, per-process GPU memory is not reported |

## Studio and web

| EN term | ES term | Definition |
|---|---|---|
| Access gate | Puerta de acceso | The site's demo passphrase screen; not a security boundary |
| Artefact | Artefacto | Any published output (figure, video, model, table) with a manifest entry |
| Capability probe | Sonda de capacidades | `studio/bench/run_bench.py`: records which GPU tools run on a machine |
| Content-addressed cache | Caché direccionada por contenido | Store keyed by the hash of everything that determines an output |
| GPU hold | Retención de GPU (hold) | The `gpu0.hold` file that stops all GPU work on a machine |
| Lane | Carril | Where a result is produced: live (browser), precompute (studio), replay (committed outputs) |
| Manifest | Manifiesto | JSON record of a run or artefact: inputs, versions, seeds, telemetry, licence, lane |
| Pyodide | Pyodide | CPython compiled to WebAssembly; runs `minephys` in the browser |
| Recipe | Receta | YAML DAG of stages for one case, with parameters and a master seed |
| Release asset | Recurso de versión (release asset) | File attached to a GitHub release; PitStudio's home for files over 10 MB |
| Runner | Ejecutor (runner) | PitStudio's small job runner: DAG, cache, locks, guards, telemetry, manifests |
| Tier | Nivel (tier) | What the visitor's browser offers: T1 WebGPU, T2 WebAssembly, T0 baked |
| WebGPU / WGSL | WebGPU / WGSL | The browser GPU API / its shading language, used for compute kernels |

## Assumptions and limits

- Definitions are short by design; the theory pages give the equations, assumptions and validity ranges.
- Spanish terms vary by country; the web app uses the first form given.

## In PitStudio

- Spanish strings live in `web/src/locales/es/`; the generated knowledge glossary comes from `minephys` in the build
  phase.

## References

1. Soofastaei, A. et al. (2016), haul-truck energy, total resistance = rolling + grade resistance. https://doi.org/10.1016/j.ijmst.2015.12.015
2. Burt, C. N. and Caccetta, L. (2007), "Match factor for heterogeneous truck and loader fleets". https://doi.org/10.1080/17480930701388606
3. Carmichael, D. G. (1986), "Shovel–truck queues: a reconciliation of theory and practice". https://doi.org/10.1080/01446198600000013
4. Kuznetsov, V. M. (1973), "The mean diameter of the fragments formed by blasting rock". https://doi.org/10.1007/BF02506177
5. Mutinda, E. K. et al. (2021), "Prediction of rock fragmentation using the Kuznetsov–Cunningham–Ouchterlony model", JSAIMM. https://doi.org/10.17159/2411-9717/1401/2021
6. Szendrei, T. and Tose, S. (2023), "Flyrock in surface mining — limitations of predictive models", JSAIMM. https://doi.org/10.17159/2411-9717/1873/2022
7. Ouchterlony, F. (2005), "The Swebrec function: linking fragmentation by blasting and crushing". https://doi.org/10.1179/037178405X44539
8. 30 CFR § 816.67, "Use of explosives: control of adverse effects". https://www.law.cornell.edu/cfr/text/30/816.67
9. Bishop, A. W. (1955), "The use of the slip circle in the stability analysis of slopes". https://doi.org/10.1680/geot.1955.5.1.7
10. Spencer, E. (1967), "A method of analysis of the stability of embankments assuming parallel inter-slice forces". https://doi.org/10.1680/geot.1967.17.1.11
11. Hoek, E. and Brown, E. T. (2019), "The Hoek–Brown failure criterion and GSI — 2018 edition". https://doi.org/10.1016/j.jrmge.2018.08.001
12. Rose, N. D. and Hungr, O. (2007), "Forecasting potential rock slope failure in open pit mines using the inverse-velocity method". https://doi.org/10.1016/j.ijrmms.2006.07.014
13. Dick, G. J. et al. (2015), "Development of an early-warning time-of-failure analysis methodology for open-pit mine slopes utilizing ground-based slope stability radar monitoring data". https://doi.org/10.1139/cgj-2014-0028
14. Voight, B. (1989), "A relation to describe rate-dependent material failure", Science. https://doi.org/10.1126/science.243.4888.200
15. Cundall, P. A. and Strack, O. D. L. (1979), "A discrete numerical model for granular assemblies". https://doi.org/10.1680/geot.1979.29.1.47
16. Coetzee, C. J. (2017), "Review: Calibration of the discrete element method". https://doi.org/10.1016/j.powtec.2017.01.015
17. Bond, F. C. (1952), "The third theory of comminution", Trans. AIME 193:484–494 (bibliographic). https://www.scirp.org/reference/referencespapers?referenceid=3600515
18. Reece, A. R. (1964), "The fundamental equation of earth-moving mechanics". https://doi.org/10.1243/PIME_CONF_1964_179_134_02
19. Hochbaum, D. S. (2008), "The pseudoflow algorithm: a new algorithm for the maximum-flow problem". https://doi.org/10.1287/opre.1080.0524
20. Espinoza, D. et al. (2013), "MineLib: a library of open pit mining problems". https://doi.org/10.1007/s10479-012-1258-3
21. Lane, K. F. (1964), "Choosing the optimum cut-off grade", Colorado School of Mines Quarterly 59 (bibliographic). https://www.scirp.org/reference/referencespapers?referenceid=1929843
22. "Atmospheric dispersion modeling" — Gaussian plume with ground reflection, Pasquill classes. https://en.wikipedia.org/wiki/Atmospheric_dispersion_modeling
23. US EPA, AP-42 §13.2.2 "Unpaved Roads" (November 2006). https://www.epa.gov/sites/default/files/2020-10/documents/13.2.2_unpaved_roads.pdf
24. Valenzuela Cruzat, J. and Valenzuela, M. A. (2018), "Modeling and evaluation of benefits of trolley assist system for mining trucks", IEEE TIA. https://doi.org/10.1109/tia.2018.2823261
25. Lindgren, L. et al. (2022), "Drive-cycle simulations of battery-electric large haul trucks for open-pit mining with electric roads", Energies. https://doi.org/10.3390/en15134871
26. Gharai, M. and Venugopal, R. (2016), "Modeling of flotation process — an overview of different approaches". https://doi.org/10.1080/08827508.2015.1115991
27. Hu, Y. et al. (2018), "A moving least squares material point method with displacement discontinuity and two-way rigid body coupling", ACM TOG. https://doi.org/10.1145/3197517.3201293
28. Austin, L. G. (1971), "Introduction to the mathematical description of grinding as a rate process". https://doi.org/10.1016/0032-5910(71)80064-5
29. Tobin, J. et al. (2017), "Domain randomization for transferring deep neural networks from simulation to the real world". https://arxiv.org/abs/1703.06907
30. Prakash, A. et al. (2019), "Structured domain randomization". https://arxiv.org/abs/1810.10093
31. Lopez-Paz, D. and Oquab, M. (2017), "Revisiting classifier two-sample tests". https://arxiv.org/abs/1610.06545
32. Hendrycks, D. and Dietterich, T. (2019), "Benchmarking neural network robustness to common corruptions and perturbations". https://arxiv.org/abs/1903.12261
33. Esteban, C., Hyland, S. L. and Rätsch, G. (2017), TSTR / TRTS evaluation of synthetic data. https://arxiv.org/abs/1706.02633
