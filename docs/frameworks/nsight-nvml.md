# Nsight and NVML

> The GPU evidence layer: NVML telemetry on every GPU stage, NVTX ranges that name the stages, and kernel-level
> Nsight captures that the maintainer runs with admin rights. · Part of: [Frameworks](README.md) · Related:
> [Runner](../studio/runner.md) · [Profile the GPU guide](../guides/profile-the-gpu.md) ·
> [Capabilities probe](../studio/capabilities-probe.md) · [Manifest](../data-contract/manifest.md)

## What and why

PitStudio claims to use the GPU fully; it must prove it with numbers a reader can audit. Three tiers of evidence, each
with a different claim strength:

| Tier | Tool | Admin? | What it may claim |
|---|---|---|---|
| T-a | **NVML** through `nvidia-ml-py`, sampled by the runner | no | "busy X % of the stage, power-bound Y % of the time", energy, VRAM, clocks, temperature, throttle reasons, encoder use |
| T-b | `torch.profiler` (CUPTI), Warp timing, Kit ChromeTrace | no | kernel time per stage and the top kernels [1][2] |
| T-c | **Nsight Systems** captures with GPU metrics; **Nsight Compute** for the top kernels | **yes** | SM-active and occupancy timelines; roofline per kernel — the only tier allowed to say "SM-saturated" |

**NVML** is NVIDIA's management library; `nvidia-ml-py` is its official Python binding, while the older `pynvml` is
deprecated [3][4]. **NVTX** annotations name code ranges for profilers and do nothing when no tool is attached, so they
stay on in every run [5].

Rejected: utilisation-only claims (misleading, below); DCGM (Linux-only) [6]; screenshots of NVIDIA tools on the web
(we export data and draw our own charts).

## Identity

| Item | Value |
|---|---|
| `nvidia-ml-py` | 13.615.71 (2026-09-25), BSD · open — in the root lock (extra `runner`), `studio/` and `pipeline/accel/` [3] |
| `nvtx` | 0.2.16 (2026-08-12), Apache-2.0 WITH LLVM-exception · open — in `studio/uv.lock` [7] |
| Nsight Systems | 2026.5.1 (2026-09-10) standalone; 2026.3.2.476 in the CUDA 13.4.2 redistributable archives [8][9] |
| Nsight Compute | 2026.3.1 (2026-09-12) standalone; 2026.3.1.2 in the redistributable archives [10][9] |
| Nsight licence | NVIDIA SLA · reference-only; raw reports never published [9] |
| Ring | Adopt (NVML) · Trial (Nsight, maintainer-run captures) |

Nsight versions older than Systems 2025.5.1 and Compute 2025.3 predate CUDA 13 support and are not used on this
project's CUDA 13 workloads [11][12].

## How PitStudio uses it

**Runner telemetry (T-a).** A background sampler reads NVML at 1–4 Hz on every GPU stage; NVML's own sample period is
between 1/6 s and 1 s depending on the product [13]. Each sample stores time, utilisation, memory used, power, enforced
power limit, SM clock, temperature, encoder utilisation and the clocks-event-reasons bitmask. Energy per stage is the
difference of two readings of the total-energy counter (millijoules since driver load) [14]. Results go to
`telemetry.parquet` and a summary in the manifest; the web gets a 1 Hz downsample of ≤ 200 KB per run.

**Reading utilisation honestly.** NVML utilisation is the "percent of time over the past sample period during which one
or more kernels was executing" [13] — a time-busy fraction, not SM occupancy: one tiny kernel can read 100 %. So the
GPU evidence page never headlines busy % alone. It pairs it with **power at the enforced limit**: on a power-limited
laptop GPU, the `SwPowerCap` reason under load means "power-bound", the signature of a fully used GPU; thermal and
hardware slowdown reasons are the warning signs [15].

**Per-process VRAM is not observable on Windows (WDDM)** [16], so VRAM guards use device-level free memory plus each
framework's allocator counters.

**Profiling (T-b, T-c).** `studio profile` runs `torch.profiler` or Warp timing without admin and prints the Nsight
Systems command for the maintainer, because "You must run the CLI on Windows as administrator" [17]. GPU performance
counters are restricted by default and unlocking them needs a one-time admin setting [18]. Nsight Compute locks SM
clocks by default, so its timings are labelled "kernel analysis, not wall-clock" [19]. Exports go to Parquet or JSON
Lines (the legacy JSON and text exports were removed in 2026.4) and are reduced to small summary tables [8][17].

## Licence and redistribution

NVML bindings and NVTX are open. Nsight tools are NVIDIA-licensed: run locally, never vendored, reports never
published — only our derived summary numbers. Telemetry of open-runtime stages is published; for stages running Isaac
Sim, Kit, Replicator, ovrtx or TensorRT for RTX, the GPU page shows their outputs with a "performance local-only
(licence)" note ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

## Assumptions and limits

- Some NVML fields may be unsupported on a laptop SKU under WDDM; the sampler probes each field and records `null` with
  the reason.
- Thermal and power throttling make runs non-comparable unless the enforced limit and throttle fractions match; both
  are stored in every manifest.
- Nsight captures depend on the maintainer's elevated acts; without them, evidence stops at T-a and T-b and the page
  says so.

## In PitStudio

- Today, the capability bench samples NVML at 2 Hz while each probe runs and also records the PCIe replay counter and,
  on Windows, the count of WHEA hardware-error events before and after ([Capabilities probe](../studio/capabilities-probe.md)).
- Guide: [Profile the GPU](../guides/profile-the-gpu.md). Status: **not yet run** on the reference machine — produced in the data-and-models phase.

## References

1. PyTorch. *Profiler (2.14)*. https://docs.pytorch.org/docs/2.14/profiler.html
2. NVIDIA. *Kit profiling*. https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/profiling.html
3. Python Package Index. *nvidia-ml-py* 13.615.71. https://pypi.org/pypi/nvidia-ml-py/json
4. Python Package Index. *pynvml* (deprecated). https://pypi.org/pypi/pynvml/json
5. NVIDIA. *NVTX Python*. https://nvidia.github.io/NVTX/python/
6. NVIDIA. *DCGM getting started*. https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/getting-started.html
7. Python Package Index. *nvtx* 0.2.16. https://pypi.org/pypi/nvtx/0.2.16/json
8. NVIDIA. *Nsight Systems release notes*. https://docs.nvidia.com/nsight-systems/ReleaseNotes/index.html
9. NVIDIA. *CUDA 13.4.2 redistributable manifest*. https://developer.download.nvidia.com/compute/cuda/redist/redistrib_13.4.2.json
10. NVIDIA. *Nsight Compute 2026.3 announcement*. https://forums.developer.nvidia.com/t/nvidia-nsight-compute-2026-3-with-nsight-copilot-is-now-available/383027
11. NVIDIA. *Nsight Systems 2025.5.1 announcement* (CUDA 13.0 support). https://forums.developer.nvidia.com/t/nsight-systems-2025-5-1-desktop-server-x86-64-arm-sbsa-release-announcement/342135
12. NVIDIA. *Nsight Compute release notes*. https://docs.nvidia.com/nsight-compute/ReleaseNotes/index.html
13. NVIDIA. *nvmlUtilization_t*. https://docs.nvidia.com/deploy/nvml-api/api/structnvmlUtilization__t.html
14. NVIDIA. *NVML device queries*. https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceQueries.html
15. NVIDIA. *NVML clocks event reasons*. https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html
16. NVIDIA. *nvidia-smi documentation*. https://docs.nvidia.com/deploy/nvidia-smi/index.html
17. NVIDIA. *Nsight Systems user guide*. https://docs.nvidia.com/nsight-systems/UserGuide/index.html
18. NVIDIA. *ERR_NVGPUCTRPERM: permission issue with performance counters*.
    https://developer.nvidia.com/nvidia-development-tools-solutions-err_nvgpuctrperm-permission-issue-performance-counters
19. NVIDIA. *Nsight Compute profiling guide*. https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html
