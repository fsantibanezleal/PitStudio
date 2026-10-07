# Guides

> Task-oriented how-tos: from a CPU-only quickstart to setting up every studio environment, running recipes, generating
> synthetic data, training Isaac Lab policies, encoding videos, profiling the GPU, reproducing a case and cutting a
> release. · Part of: [docs home](../README.md) · Related: [reference](../reference/README.md) ·
> [studio](../studio/README.md) · [pipelines](../pipelines/README.md)

## Orientation

Each guide has the same shape: goal, prerequisites, numbered steps with commands, expected output, troubleshooting,
limits and status. Most of PitStudio is written in the build phase, so **most commands in these guides do not exist
yet**. Every shell block says which kind it is:

| Info string | Meaning |
|---|---|
| `bash run` | Runs today in this repository (Git Bash, macOS or Linux shell) |
| `powershell run` | Runs today in Windows PowerShell |
| `bash run deferred=P6` | Specified, not yet implemented; works once the build phase (P6) implements it (runner, pipeline stages, `studio` CLI) |
| `bash` | Illustrative only (a fragment, a placeholder or a third-party command shown for context) |

Nothing on the GPU has been run for publication yet: the capability probes are written but not yet run on the reference
machine, and no model has been trained. Where a guide shows output, it shows the **form** of the output, never
invented numbers.

## Map

| Guide | Goal | Needs a GPU? |
|---|---|---|
| [quickstart.md](quickstart.md) | Clone, install, run the CPU tests, build and serve the web app | no |
| [set-up-the-studio.md](set-up-the-studio.md) | Create every studio environment, the portable tools and the one-time maintainer acts; run the capability probe | yes |
| [first-recipe.md](first-recipe.md) | Write a recipe, plan it, run it, read its manifest and cache | optional |
| [synthetic-data-generation.md](synthetic-data-generation.md) | Generate labelled synthetic images with Isaac Sim + Replicator, with domain randomisation | yes (RTX) |
| [isaac-lab-task.md](isaac-lab-task.md) | Train and evaluate the haul-truck and excavator policies in Isaac Lab | yes |
| [composer-review.md](composer-review.md) | Review the composed pit stage in USD Composer / Explorer and capture path-traced stills | yes (RTX) |
| [cosmos-tasks.md](cosmos-tasks.md) | Run the Cosmos Reason 2 hazard, plausibility and caption tasks with llama.cpp | yes |
| [tensorrt-bench.md](tensorrt-bench.md) | Build TensorRT engines of the exported models, check per-engine parity, benchmark | yes |
| [encode-videos.md](encode-videos.md) | Encode studio clips to AV1 + H.264 with NVENC and check the byte budget | yes (NVENC) |
| [profile-the-gpu.md](profile-the-gpu.md) | Read NVML telemetry, throttle reasons and Nsight captures | yes |
| [reproduce-a-case.md](reproduce-a-case.md) | Reproduce a published case artefact and compare it with its manifest | depends on the case |
| [release-and-cite.md](release-and-cite.md) | Version, tag and release; cite PitStudio and `minephys` | no |

## Learning paths

- **Just look around:** [quickstart](quickstart.md) → the [web](../web/README.md) section.
- **Reproduce a result:** [quickstart](quickstart.md) → [set up the studio](set-up-the-studio.md) →
  [first recipe](first-recipe.md) → [reproduce a case](reproduce-a-case.md).
- **Build the physical-AI loop:** [set up the studio](set-up-the-studio.md) →
  [synthetic data generation](synthetic-data-generation.md) → [TensorRT bench](tensorrt-bench.md) →
  [encode videos](encode-videos.md) → [profile the GPU](profile-the-gpu.md).
- **Robotics and VLM:** [Isaac Lab task](isaac-lab-task.md) → [Cosmos tasks](cosmos-tasks.md) →
  [Composer review](composer-review.md).

## Common pitfalls (read once)

| Symptom | Cause | Fix | Guide |
|---|---|---|---|
| Web build loads assets from `C:/Program Files/Git/PitStudio/` | Git Bash rewrites `BASE_PATH=/PitStudio/` as a Windows path | Build from PowerShell, or prefix `MSYS2_ENV_CONV_EXCL=BASE_PATH` | [quickstart](quickstart.md) |
| An NVIDIA env picks `...\WindowsApps\python.exe` | The Microsoft Store Python shim | uv-managed Python only (`python-preference = "only-managed"`) | [set up the studio](set-up-the-studio.md) |
| TensorRT / polygraphy loads `cudart64_12.dll` | `CUDA_PATH` points at an older machine-wide toolkit | Point `CUDA_PATH` at the CUDA 13 runtime wheel | [TensorRT bench](tensorrt-bench.md) |
| FFmpeg lists `av1_nvenc` but fails to open it | FFmpeg 9 builds need driver ≥ 610 | Use an FFmpeg 8.1 build | [encode videos](encode-videos.md) |
| Isaac Sim install fails on long file names | Windows long paths are off | The maintainer enables `LongPathsEnabled` (elevated, once) | [set up the studio](set-up-the-studio.md) |
| A GPU command refuses to start | `gpu0.hold` exists or another job holds `gpu0.compute` | Wait, or remove the hold only when the reason is resolved | [profile the GPU](profile-the-gpu.md) |
