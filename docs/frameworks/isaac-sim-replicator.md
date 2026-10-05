# Isaac Sim and Replicator

> NVIDIA's robotics simulator and its synthetic-data engine, used for labelled RTX images of equipment, people and
> boulders, RTX case clips, lidar in rain and the PhysX vehicle twin. · Part of: [Frameworks](README.md) · Related:
> [ovrtx](ovrtx.md) · [B2 synthetic perception](../cases/b2-synthetic-perception.md) ·
> [M10 synthetic-data detector](../methods/m10-synthetic-data-detector.md) ·
> [DEC-0008](../architecture/decisions/DEC-0008-isaac-sim-version-by-compatibility-checker.md)

## What and why

**Isaac Sim** is NVIDIA's simulator built on Kit: RTX rendering, PhysX, sensors and Python standalone apps
(`SimulationApp`, headless supported) [1][2]. **Replicator** (`omni.replicator.core`) ships inside it and generates
synthetic datasets: randomizers, annotators (RGB, semantic and instance segmentation, 2D/3D boxes, depth, occlusion)
and writers such as BasicWriter and the COCO writer [3][4].

PitStudio uses it where no open tool reaches the same fidelity:

- **Synthetic data for perception (B2, D1):** equipment, people and boulders under dust, night and rain, with
  structured and unstructured domain randomisation, labelled exactly from the USD `SemanticsLabelsAPI` labels our
  scene pipeline writes. People come from MakeHuman CC0 exports, never NVIDIA character assets
  ([DEC-0015](../architecture/decisions/DEC-0015-people-assets-makehuman.md)).
- **RTX case clips** of our own scenes, encoded later by FFmpeg ([NVENC / FFmpeg](nvenc-ffmpeg.md)).
- **Lidar in rain:** its lidar model includes a Mie-scattering rain simulation set by a Kit setting [5].
- **PhysX vehicle visual twin** for B1 ([PhysX / ovphysx](physx-ovphysx.md)).

Rejected alternatives: running it in WSL2 or a container on the laptop (the container is Linux-only; OpenGL interop is
unsupported in WSL2 and Vulkan/RTX initialisation failures are reported there) [6][7][8]; Isaac Sim 7.0.0a1 (alpha) [9];
NVIDIA asset-library or character content in published scenes (not redistributable) [10].

## Identity

| Item | Value |
|---|---|
| Package | `isaacsim[all,extscache]` 6.1.0.0 with `isaacsim-replicator` 6.1.0.0, pinned in `studio/isaac/uv.lock` |
| Release | wheels uploaded 2026-09-09; GitHub release 6.1.0 [11][9] |
| Kit inside | Kit 110.3.0 (6.1 release notes) [12] |
| Torch | `torch==2.11.0` on the cu130 index, the version Isaac Sim's pip guide installs [2] |
| Python | `==3.12.*` [11] |
| Licence | Isaac Sim source on GitHub is Apache-2.0; the runtime, Kit and NVIDIA assets fall under NVIDIA terms including the Isaac Sim Additional Software and Materials License [13][14] |
| Class | reference-only |
| Ring | Trial |
| Environment | `studio/isaac/` (uv-managed Python 3.12, `python-preference = "only-managed"`) |

The lock also carries security floors (`override-dependencies`) for transitive pins of the Isaac Sim stack, added when
dependency alerts appeared; Isaac Sim itself and its torch pin are unchanged.

## Which version: the Compatibility Checker decides

NVIDIA's requirements page for 6.1 lists Windows driver 595.97 as the version Isaac Sim **was tested on**, and 6.0.0
was tested on 581.42 [15][16]. The Omniverse technical requirements accept Ada workstation GPUs on R580 from 581.42
(from 582.41 with KB5074109) [17]. The rule ([DEC-0008](../architecture/decisions/DEC-0008-isaac-sim-version-by-compatibility-checker.md)):

1. Run Isaac Sim's Compatibility Checker and a headless smoke on the reference driver (R580, 582.78).
2. Pass → Isaac Sim 6.1.0.
3. Fail → Isaac Sim 6.0.0.1, or 6.1 after the maintainer installs an R595 driver (an elevated act).

The minimum GPU is an RTX 4080-class card with 16 GB of VRAM [15], so the 16 GB laptop GPU sits exactly at the floor:
renders stay ≤ 720p with one or two cameras, and GPU jobs run one at a time.

## How PitStudio uses it

| Stage | What | Case | Output |
|---|---|---|---|
| `st55_sdg` | Replicator SDG, ~10k images per family × 2 families + one unstructured-DR arm | B2, D1 | COCO labels, masks, depth; a gallery with ground-truth overlays |
| `st52_rtx_render` | RTX clips of our scenes | all video cases | PNG/EXR frame sequences → `st56_encode` |
| `st54_vehicles` | PhysX vehicle visual twin | B1 | clips |
| `st57_rain_lidar` | lidar rain arm | B1 (S1) | point clouds |

Budget: the project sizes SDG at 0.5–2 images/s on the laptop, about 3–11 hours per 20k images; the rate itself is an
open measurement of the probe. For orientation only, NVIDIA's published benchmark gives 28.88 images/s (RGB + depth)
and 9.16 images/s (all annotators) on a desktop RTX 5080 under Windows [18]. Replicator seeds are fixed with
`rep.set_global_seed` [19].

## Licence and redistribution

The Isaac Sim licence FAQ says Isaac Sim is free for internal R&D, that outputs such as "simulation videos, analytic
reports, or datasets" may be sold without an enterprise licence, and that redistributing Isaac Sim or Kit needs one
[10]. Omniverse has been free for development and production since May 2026 [20]. PitStudio therefore publishes only
**its own** code, USD and outputs (CC-BY-4.0), never Isaac Sim binaries, caches, extscache or NVIDIA assets. Accepting
the EULA (`OMNI_KIT_ACCEPT_EULA`) is the maintainer's act [2]. SDG throughput and any other performance data stay
local-only ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

## Assumptions and limits

- First run: about 5–10 minutes of shader-cache warm-up; later starts take 10–30 s [21].
- Windows known issues include WinError 126, thread clean-up on close and a telemetry path over 260 characters [22].
- Texture streaming defaults to 60 % of VRAM; a lower budget is set per stage [23].
- Never imported in the same process as ovrtx, never in CI (NVIDIA software runs only on NVIDIA platforms [24]).

## In PitStudio

- Probe: Compatibility Checker + headless smoke, and an SDG images/s measurement, after the GPU hold and the
  maintainer's EULA acceptance ([Capabilities probe](../studio/capabilities-probe.md)).
- Guide: [Synthetic data generation](../guides/synthetic-data-generation.md).
- Status: **not yet run** — produced in the data-and-models phase. Reported then: the B2 datasets (synthetic held-out mAP50
  ≥ 0.80 for D-FINE-S and ≥ 0.70 for D-FINE-N as the acceptance targets) and the case clips.

## References

1. NVIDIA. *Isaac Sim repository*. https://github.com/isaac-sim/IsaacSim
2. NVIDIA. *Isaac Sim Python (pip) installation*. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html
3. NVIDIA. *Replicator overview*. https://docs.isaacsim.omniverse.nvidia.com/latest/replicator_tutorials/tutorial_replicator_overview.html
4. NVIDIA. *Isaac Sim 6.0 scene-based SDG*. https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_scene_based_sdg.html
5. NVIDIA. *Omniverse Lidar extension*. https://docs.omniverse.nvidia.com/kit/docs/omni.sensors.nv.lidar/latest/lidar_extension.html
6. NVIDIA. *Isaac Sim container installation*. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html
7. NVIDIA. *CUDA on WSL user guide*. https://docs.nvidia.com/cuda/wsl-user-guide/index.html
8. GitHub issue (2026-03-30). *Isaac Sim fails in WSL2 + Docker due to Vulkan/RTX initialization*.
   https://github.com/robotmcp/ros-mcp-server/issues/289
9. NVIDIA. *Isaac Sim releases*. https://github.com/isaac-sim/IsaacSim/releases
10. NVIDIA. *Isaac Sim licence FAQ*. https://docs.isaacsim.omniverse.nvidia.com/latest/common/license-faq.html
11. Python Package Index. *isaacsim* 6.1.0.0. https://pypi.org/pypi/isaacsim/json
12. NVIDIA. *Isaac Sim release notes*. https://docs.isaacsim.omniverse.nvidia.com/latest/overview/release_notes.html
13. NVIDIA. *Isaac Sim licensing*. https://docs.isaacsim.omniverse.nvidia.com/latest/common/licenses-isaac-sim.html
14. NVIDIA. *Isaac Sim Additional Software and Materials License*.
    https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/
15. NVIDIA. *Isaac Sim requirements (latest)*. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html
16. NVIDIA. *Isaac Sim 6.0 requirements*. https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html
17. NVIDIA. *Omniverse technical requirements*. https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html
18. NVIDIA. *Isaac Sim benchmarks*. https://docs.isaacsim.omniverse.nvidia.com/latest/reference_material/benchmarks.html
19. NVIDIA. *Isaac Sim 6.0 Replicator snippets* (`rep.set_global_seed`).
    https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_isaac_snippets.html
20. NVIDIA developer forum (2026-07-24). *Clarification on charging customers for software built with Omniverse*.
    https://forums.developer.nvidia.com/t/clarification-on-charging-customers-for-software-built-with-omniverse/377476
21. NVIDIA. *Isaac Sim workstation installation*. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_workstation.html
22. NVIDIA. *Isaac Sim known issues*. https://docs.isaacsim.omniverse.nvidia.com/latest/overview/known_issues.html
23. NVIDIA. *Isaac Sim performance optimisation handbook*.
    https://docs.isaacsim.omniverse.nvidia.com/latest/reference_material/sim_performance_optimization_handbook.html
24. NVIDIA. *Product Specific Terms for NVIDIA AI Products* (2026-04-01, PDF).
    https://www.nvidia.com/content/dam/en-zz/Solutions/license-agreements/enterprise-software/product-specific-terms-ai-products-omniverse-16042026.pdf
