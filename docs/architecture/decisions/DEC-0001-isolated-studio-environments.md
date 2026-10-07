# DEC-0001: Isolated studio environments

> Each tool family gets its own uv project with its own lock file and interpreter; environments never share a virtual
> environment or import each other, and exchange only versioned files with manifests. · Part of: [decisions](README.md) ·
> Related: [studio environments](../../studio/environments.md) · [C4 containers](../c4-containers.md) ·
> [DEC-0002](DEC-0002-in-repo-runner.md)

**Status:** Accepted, 2026-10-04

## Context

PitStudio drives a dozen GPU tools on one Windows workstation, and their requirements conflict:

- **Python versions.** Isaac Sim 6.1 is published as `isaacsim` 6.1.0.0 for Python 3.12 only, and its install guide pins
  `torch==2.11.0` from the cu130 index [1] [2]. Kit 110.3 also needs Python 3.12; the Kit-less ovrtx libraries support
  Python 3.10–3.13 [3]. The open GPU stack (usd-core 26.8, Warp 1.17, Newton 1.6 with MuJoCo-Warp) runs on the apps'
  Python 3.14; a local GPU smoke test passed on 2026-10-03.
- **Process isolation.** ovrtx and Kit/Isaac Sim each carry an RTX runtime and must not be imported in the same process.
- **Library conflicts.** TensorRT 11.3 and the TensorRT 10.14 libraries used by ONNX Runtime's TensorRT execution
  provider share a distribution name and cannot live in one environment [4].
- **No RTX in WSL2.** The Isaac Sim container is Linux-only; OpenGL–CUDA interop is unsupported in WSL2, and Vulkan/RTX
  initialisation failures are reported there [5] [6] [7]. A container-based studio on the laptop is not a path.
- **Licences** forbid redistributing the NVIDIA runtimes and running them in CI, so the public repository must stay
  reproducible on CPU without them.

## Decision

Every environment is its own uv project with its own `uv.lock`, entered only through
`uv run --project <env> --frozen` [8]:

| Path | Python | Contents | Role |
|---|---|---|---|
| root | 3.14 | core package, contracts, runner (extra `runner`), console dependencies (extra `api`), `minephys` | orchestration and shared code |
| `studio/` | 3.14 | usd-core, warp-lang, newton[sim], usd-validation-nvidia, simready-validate, PyNvVideoCodec, nvidia-ml-py, nvtx | scene build and validation, GPU physics, media encode, telemetry |
| `studio/isaac/` | 3.12 (uv-managed only) | Isaac Sim + Replicator, torch 2.11 cu130 | RTX renders, synthetic data, PhysX vehicle visual twin |
| `studio/rtx/` | 3.12 | ovrtx, ovstage, ovphysx (exact builds from NVIDIA's index) | Kit-less RTX camera, lidar, radar |
| `studio/isaaclab/` | 3.12 | Isaac Lab 3.0 (pinned tag), kit-less on Newton | optional robot-learning tasks |
| `studio/kit/` | Kit's own | only PitStudio's Apache-2.0 extension, `.kit` file and scripts | scene review, path-traced captures |
| `studio/reason/` | — | configuration, prompts and evaluation for an external llama.cpp build | optional vision-language evaluation |
| `pipeline/` | 3.14 | torch (cpu / cu126 / cu130 extras), ONNX Runtime | training, evaluation, export |
| `pipeline/accel/` | 3.14 | TensorRT 11.3, Polygraphy, CUDA runtime 13 | engine builds and benchmarks; engines never committed |

Rules that come with it:

1. Environments never share a virtual environment and never import each other.
2. All exchange is through files: each stage reads declared inputs by content digest and writes outputs plus a
   `manifest.json` (JSON Schema 2020-12) with the recipe hash, seeds, tool versions read from the lock, GPU and driver,
   telemetry summary, determinism class, licence class and SHA-256 per output, and no host names, user names or paths.
3. The Python 3.12 environments use uv-managed interpreters only (`python-preference = "only-managed"`), never a
   Microsoft Store shim.
4. External tools (FFmpeg 8.1 LGPL, Nsight, COLMAP, Brush, llama.cpp) run as subprocesses and are never vendored.
5. The pipeline's frozen stage list gains `s62_accel` and `s64_bench` after `s60_export` (in `pipeline/accel/`), plus
   the studio's `st*` stages; throughput benchmarks of training are runner probes (`studio bench`), not stages.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| One shared environment for everything | One lock, simpler setup | torch pins diverge (Isaac Sim 2.11, pipeline 2.14); Kit and ovrtx RTX runtimes would share a process; TensorRT 11.3 and 10.14 collide | Not resolvable, and unsafe at run time |
| One shared Python 3.12 environment for all NVIDIA tools, 3.14 elsewhere | Fewer locks | Isaac Sim and Isaac Lab pins drift apart; Kit and ovrtx still in one process | Same runtime conflict |
| The whole studio on Python 3.12 | One interpreter | The open stack runs on 3.14 and the apps already use 3.14 | No benefit; a second interpreter for no reason |
| Containers on the laptop (WSL2 + Docker) | Linux parity | RTX rendering is not a supported path in WSL2; Docker Desktop is an elevated install | Not workable on the reference machine; kept for a future Linux host |

## Consequences

**Positive.** Each tool runs where it works best; upstream pins are honoured instead of fought; a broken NVIDIA update
cannot break the open lane; the public repository stays CPU-reproducible; the same lock files drive a Linux host later.

**Negative, accepted.** Seven uv projects to keep resolved (plus Kit's and llama.cpp's own runtimes); handoff code must
validate files on both sides; NVIDIA environments are large downloads.

**Watch.** Isaac Lab 3.0 GA (targeted for the end of October 2026); Isaac Sim driver matrices; Newton's classifiers;
the pre-release licence labels of ovrtx and ovphysx; TensorRT 11 on the R580 driver branch.

## References

1. `isaacsim` on PyPI (6.1.0.0, Python ==3.12). https://pypi.org/pypi/isaacsim/json
2. Isaac Sim pip installation (torch 2.11.0 cu130). https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html
3. ovrtx repository (Python 3.10–3.13, MSVC runtime ≥ 14.38). https://github.com/NVIDIA-Omniverse/ovrtx
4. NVIDIA package index: `tensorrt-cu13-libs` (10.14.1.48 and 11.3.0.99 under one name). https://pypi.nvidia.com/tensorrt-cu13-libs/
5. Isaac Sim container installation. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html
6. NVIDIA. CUDA on WSL user guide. https://docs.nvidia.com/cuda/wsl-user-guide/index.html
7. Community report of Vulkan/RTX initialisation failure in WSL2 (2026-03-30). https://github.com/robotmcp/ros-mcp-server/issues/289
8. Astral. uv command-line reference. https://docs.astral.sh/uv/reference/cli/
