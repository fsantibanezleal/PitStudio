# Set up the studio

> Create every studio environment (open lane on Python 3.14, NVIDIA lanes on a uv-managed Python 3.12, acceleration),
> install the portable tools, complete the maintainer's one-time acts, and run the capability probe that records what
> works on this machine. · Part of: [Guides](README.md) · Related: [environments](../studio/environments.md) ·
> [capabilities probe](../studio/capabilities-probe.md) · [owner acts and licences](../studio/owner-acts-and-licences.md) ·
> [configuration](../reference/configuration.md)

## What and why

**Goal:** a workstation on which every studio tool either runs or is recorded as not running, with the reason. The
studio is split into isolated uv environments because the tools cannot share one: NVIDIA's runtimes pin Python 3.12
and their own PyTorch, the open physics stack runs on Python 3.14, and the two TensorRT versions cannot live in one
environment ([DEC-0001](../architecture/decisions/DEC-0001-isolated-studio-environments.md)). Environments exchange
files only, never imports. The runner enters each one with `uv run --project <env> --frozen`.

## Prerequisites

**Hardware.** An NVIDIA RTX GPU. The reference machine is an RTX 5000 Ada Laptop GPU (16 GB), 64 GB RAM, Windows 11,
driver 582.78 (R580 branch). Isaac Sim's published minimum is an RTX 4080-class GPU with 16 GB VRAM, 32 GB RAM and a
50 GB SSD on Windows 11 or Ubuntu 22.04/24.04, and GPUs without RT cores are not supported [1]; a 16 GB laptop GPU sits
at that floor. CUDA 13.0 maps to driver branch R580, and CUDA 13.x applications run on drivers ≥ 580 under
minor-version compatibility [2].

**Software.** The [quickstart](quickstart.md) done (uv, Python 3.14, Node 24 + pnpm). Disk: Isaac Sim alone takes tens
of GB; synthetic data and physics runs take tens more, which is why the run store lives on its own short path
(`PITSTUDIO_STORE`).

**The environments.**

| Env | Python | Holds | Lock |
|---|---|---|---|
| root | 3.14 | core, contracts, the runner (extra `runner`: `filelock`, `nvidia-ml-py`, `psutil`), `minephys` | `uv.lock` |
| `studio/` | 3.14 | `usd-core`, `warp-lang`, `newton[sim]`, `usd-validation-nvidia`, `simready-validate`, `PyNvVideoCodec`, NVML, NVTX, geospatial libraries | `studio/uv.lock` |
| `studio/isaac/` | 3.12, uv-managed only | Isaac Sim 6.1.0.0 + Replicator (`isaacsim[all,extscache]`), torch 2.11.0 (cu130) | `studio/isaac/uv.lock` |
| `studio/rtx/` | 3.12, uv-managed only | ovrtx 0.5.0.377615, ovstage 0.2.0.377349, ovphysx 0.6.3 | `studio/rtx/uv.lock` |
| `studio/isaaclab/` | 3.12, uv-managed only | Isaac Lab from the `v3.0.0-EA` tag (kit-less on Newton) with its tested stack: torch 2.11.0 cu128, Warp 1.16.0, Newton 1.5.2 | `studio/isaaclab/uv.lock` |
| `studio/kit/` | Kit's own | PitStudio's own Kit extension only (the Composer/Explorer app is generated outside the repo) | — |
| `studio/reason/` | — | configuration for the external llama.cpp binary | — |
| `pipeline/` | 3.14 | training and evaluation: torch (extras `cpu`, `cu126`, `cu130`), ONNX, ONNX Runtime | `pipeline/uv.lock` |
| `pipeline/accel/` | 3.14 | TensorRT 11.3.0.99 (`tensorrt-cu13-*`), Polygraphy, CUDA 13 runtime wheel | `pipeline/accel/uv.lock` |

## Steps

1. **Point the data, model, temp and store folders** at a disk with room. Unset, they default to git-ignored folders in
   the repository (store excepted). Per-user environment variables need no elevation:

   ```powershell
   [Environment]::SetEnvironmentVariable("PITSTUDIO_STORE", "C:\ps", "User")
   [Environment]::SetEnvironmentVariable("PITSTUDIO_TMP", "D:\pitstudio\tmp", "User")
   [Environment]::SetEnvironmentVariable("GPU_LOCK_DIR", "D:\gpu-locks", "User")
   ```

   Use your own drive letters. `GPU_LOCK_DIR` must be the **same for every project on the machine** that uses the GPU:
   it holds the machine-wide locks. All variables: [configuration](../reference/configuration.md).

2. **Install a uv-managed Python 3.12** for the NVIDIA environments.

   ```bash run
   uv python install 3.12
   ```

3. **Create the open studio environment** (Python 3.14).

   ```bash run
   cd studio
   uv sync --locked
   ```

4. **Create the training environment with CUDA 13 PyTorch** and check that the CUDA build was installed, not a silent
   CPU fallback.

   ```bash run deferred=P6
   cd pipeline
   uv sync --extra cu130 --all-groups --locked
   uv run python ../scripts/verify_gpu.py --expect cu130
   ```

5. **Create the acceleration environment** (TensorRT 11.3 from NVIDIA's package index).

   ```bash run
   cd pipeline/accel
   uv sync --locked
   ```

6. **Accept NVIDIA's terms, then create the NVIDIA environments.** Accepting the NVIDIA software terms and the Isaac
   Sim EULA is a legal act of the person who installs; PitStudio's scripts never accept it on anyone's behalf. Isaac Sim
   asks at first import, or reads `OMNI_KIT_ACCEPT_EULA=YES` when the installer has decided to accept [3].

   ```bash run deferred=P6
   cd studio/isaac && uv sync --locked
   cd ../rtx && uv sync --locked
   cd ../isaaclab && uv sync --locked
   ```

   Each `pyproject.toml` sets `python-preference = "only-managed"`, so uv uses the interpreter from step 2 and never the
   Microsoft Store shim. NVIDIA binaries land in the local `.venv` only; they are never committed or redistributed.

7. **Install the portable tools** (per-user, no elevation). Download each official release archive, verify its SHA-256
   against the publisher's checksum, and unpack it outside the repository:

   | Tool | Version | Used for | Set |
   |---|---|---|---|
   | FFmpeg, LGPL shared build (BtbN) | n8.1 | NVENC AV1 + H.264 encode, VMAF | `PITSTUDIO_FFMPEG` = path to `ffmpeg.exe` |
   | llama.cpp, CUDA build | b11381 | Cosmos Reason 2 GGUF inference | path in `studio/reason/` config |
   | COLMAP | 4.2.1 | photogrammetry for E2 | on `PATH` or configured |
   | Brush | v0.3.0 | Gaussian-splat training for E2 | on `PATH` or configured |
   | MakeHuman | 1.3.0 | CC0 people exports for synthetic data | — |
   | Nsight Systems / Compute redistributables | 2026.3.x | profiling (running `nsys` on Windows needs administrator rights) | — |
   | `@playcanvas/splat-transform` | 3.9.0 | PLY → SPZ, project-local npm | lock file |

   Release pages and checksums: FFmpeg builds [4], llama.cpp [5], COLMAP [6].

8. **Run the capability probe.** It runs each probe in its own environment, one at a time, under the machine-wide GPU
   lock, samples NVML telemetry, and writes the committed `studio/capabilities.json` (versions, pass/fail, publishable
   metrics only) plus a full local report.

   ```bash run deferred=P6
   uv run --extra runner python studio/bench/run_bench.py
   uv run --extra runner python studio/bench/run_bench.py warp_newton nvenc --no-write
   ```

   The runner's own wrapper, once it exists:

   ```bash run deferred=P6
   uv run --extra runner studio bench env
   ```

9. **Check Isaac Sim against this driver** with NVIDIA's Compatibility Checker and a headless smoke render, before any
   long run. Isaac Sim 6.1 was tested on driver 595.97 [12]; NVIDIA's driver table lists the R580 branch from 581.42
   (582.41 or later with Windows update KB5074109) as supported [7]. The checker decides: if 6.1 fails on R580, the
   studio uses Isaac Sim 6.0.0.1, or 6.1 after the maintainer installs an R595 driver.

   ```bash run deferred=P6
   uv run --extra runner python studio/bench/run_bench.py isaacsim isaaclab ovrtx
   ```

## Expected output

The bench prints one line per probe and the paths it wrote:

```text
[bench] warp_newton ...
[bench] warp_newton: pass (<seconds> s)
[bench] ovrtx ...
[bench] ovrtx: skip (<seconds> s)
[bench] local report: <PITSTUDIO_TMP>/bench/bench-<UTC time>.json
[bench] updated studio/capabilities.json
```

- Probes with a script today: `warp_newton`, `torch_ort`, `tensorrt`, `nvenc`. `ovrtx`, `isaacsim` and `isaaclab` report
  `skip` with "probe script not written yet" until the build phase adds them.
- A probe whose environment is not installed reports `skip` with "environment … is not installed (uv sync)".
- Licence-restricted probes (ovrtx, Isaac Sim) put "measured locally, not published (licence)" in the committed file.
- Exit code: 0 when no probe failed, 1 when one failed, 3 when another job holds the GPU lock, 4 when a `gpu0.hold`
  file stops all GPU work.

**Status:** the probes are written but **not yet run on the reference machine**; `studio/capabilities.json` does not
exist yet.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| A probe fails with "interpreter is the Microsoft Store shim, not a uv-managed Python" | the env resolved `...\WindowsApps\python.exe` | `uv python install 3.12`; keep `python-preference = "only-managed"`; delete the env's `.venv` and `uv sync` again |
| Isaac Sim install or first start fails on long paths | Windows long paths are off | The maintainer sets `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1` once (elevated) [8] |
| The TensorRT probe loads `cudart64_12.dll` | a machine-wide CUDA 12 toolkit's `CUDA_PATH` comes first in Polygraphy's search | The probe points `CUDA_PATH` at the CUDA 13 runtime wheel; do the same in your own shells ([TensorRT bench](tensorrt-bench.md)) |
| `nvenc` fails although `ffmpeg -encoders` lists `av1_nvenc` | FFmpeg 9 builds use NVENC SDK 13.1 headers, which need driver ≥ 610 [9] | Use FFmpeg n8.1 (SDK 13.0 headers, driver ≥ 570 [10]) |
| `[bench] ... skip: only <n> MB VRAM free; another job uses it` | the bench needs 4,096 MB free VRAM before a probe | Close the other GPU job; the bench never competes for the GPU |
| `skip: GPU at <t> C before start` | GPU above 80 °C at start | Let it cool down |
| `GPU hold in <dir>/gpu0.hold: <reason> -- not starting` | a maintainer-placed hold stops all GPU work on the machine | Resolve the reason in the file, then remove it |
| The first ovrtx render takes minutes | shader compilation on first use (1–2 min per the ovrtx docs [11]) | Expected once per driver/version |
| Isaac Sim in WSL2 or Docker on Windows | the Isaac Sim container is Linux-only [1], and Vulkan/RTX initialisation failures are reported under WSL2 [13] | Use the Windows-native environment; containers belong to a Linux GPU host ([scaling to Linux](../studio/scaling-to-linux.md)) |

## Assumptions and limits

- Versions are those in the lock files; the lock files are the source of truth, not this page.
- Pre-release NVIDIA libraries (ovrtx, ovstage, ovphysx, Isaac Lab EA) can change between versions; they are pinned
  exactly, and a tool that does not run ends as "evaluated, not adopted" with the reason, never as a silent gap.
- NVIDIA software performance figures from this machine stay local (licence); see
  [showcase rules](../web/showcase-rules.md).

## In PitStudio

- Environments and their rules: [environments](../studio/environments.md); the probe: `studio/bench/` and
  `contracts/capabilities.schema.json`; the machine acts: [owner acts and licences](../studio/owner-acts-and-licences.md).
- Status: all environment locks exist; the GPU probes await their first run on the reference machine.

## References

1. NVIDIA, "Isaac Sim 6.0 requirements" — Windows 11 / Ubuntu, RTX 4080-class 16 GB, 32 GB RAM, 50 GB SSD; container Linux-only. https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html
2. NVIDIA, "CUDA Toolkit release notes" — CUDA 13.0 → R580; 13.x minor-version compatibility on drivers ≥ 580. https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html
3. NVIDIA, "Isaac Sim Python install" — Python 3.12, EULA acceptance, dedicated environment, long paths. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html
4. BtbN, "FFmpeg-Builds" — win64 n8.1 / n9.0 × gpl / lgpl, `checksums.sha256`. https://github.com/BtbN/FFmpeg-Builds
5. ggml-org, "llama.cpp releases" — b11381 Windows CUDA 13.4 x64 builds. https://github.com/ggml-org/llama.cpp/releases
6. COLMAP, "Releases" — 4.2.1. https://github.com/colmap/colmap/releases
7. NVIDIA, "Omniverse technical requirements" — driver table per branch; KB5074109 note (R580 ≥ 582.41). https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html
8. Microsoft, "Maximum path length limitation" — `LongPathsEnabled`. https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation
9. FFmpeg, `nv-codec-headers` README (master) — SDK 13.1.15, driver ≥ 610. https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/master/README
10. FFmpeg, `nv-codec-headers` README (n13.0.19.1) — SDK 13.0.19, driver ≥ 570. https://raw.githubusercontent.com/FFmpeg/nv-codec-headers/n13.0.19.1/README
11. NVIDIA, "ovrtx Python getting started" — install, first render, 1–2 min shader compile. https://nvidia-omniverse.github.io/ovrtx/python_api/getting_started.html
12. NVIDIA, "Isaac Sim requirements" (latest, 6.1) — tested driver 595.97 (Windows), 595.58.03 (Linux); Compatibility Checker. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html
13. GitHub issue, "Isaac Sim fails in WSL2 + Docker due to Vulkan/RTX initialization" (2026-03-30). https://github.com/robotmcp/ros-mcp-server/issues/289
