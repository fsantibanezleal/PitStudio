# Profile the GPU

> Read the GPU evidence PitStudio records — NVML telemetry with throttle reasons, NVTX stage ranges, PyTorch and Warp
> timings, optional Nsight Systems captures — and know which of it may be published. · Part of: [Guides](README.md) ·
> Related: [Nsight and NVML](../frameworks/nsight-nvml.md) · [runner](../studio/runner.md) ·
> [capabilities probe](../studio/capabilities-probe.md) · [showcase rules](../web/showcase-rules.md)

## What and why

**Goal:** turn "it ran on the GPU" into evidence: how busy the GPU was, how much memory a stage needed, how much energy
it used, and whether the clocks were capped while it ran. A laptop GPU is power-limited and spends much of a long job
power-capped or thermally slowed; a utilisation percentage alone hides that. NVML reports why clocks are reduced as a
bitmask of reasons [1]:

| Reason | NVML meaning (paraphrased from [1]) |
|---|---|
| `SwPowerCap` | clocks reduced so the GPU stays under its power limit |
| `SwThermalSlowdown` | clocks reduced so the temperature stays below the maximum operating temperature |
| `HwThermalSlowdown` | hardware cut core clocks by a factor of 2 or more because the temperature is too high |
| `GpuIdle` | nothing running |

PitStudio records the fraction of time in each state for every GPU stage, so stage timings can be compared honestly.

**Status:** the capability bench already samples NVML (`studio/bench/run_bench.py`); the runner's 1–4 Hz telemetry,
NVTX ranges, `studio profile` and the `/studio/gpu` page are written in the build phase. Nsight captures are optional
and need the maintainer, because the Nsight Systems CLI must run as administrator on Windows [2].

## Prerequisites

- [Set up the studio](set-up-the-studio.md); the root environment with the `runner` extra (`nvidia-ml-py`,
  `filelock`, `psutil`). `nvidia-ml-py` is NVIDIA's NVML binding; the older `pynvml` package is deprecated in its favour
  [3].
- `GPU_LOCK_DIR` set machine-wide ([configuration](../reference/configuration.md)).
- Optional, maintainer: Nsight Systems / Compute redistributables, an elevated shell for captures, and a one-time
  setting that allows GPU performance counters.

## What is recorded

| Source | Rate | Fields | Where |
|---|---|---|---|
| Capability bench (exists) | 2 Hz while a probe runs | temperature, power and enforced power limit, utilisation, used/total memory, SM clock, clocks-event-reasons bitmask, PCIe replay counter; on Windows the change in WHEA hardware-error events | `$PITSTUDIO_TMP/bench/bench-<UTC>.json` (local); public summary in `studio/capabilities.json` for open tools only |
| Runner telemetry (build phase) | 1–4 Hz per GPU stage | the same NVML fields, NVTX stage ranges | `$PITSTUDIO_STORE/runs/<run_id>/telemetry.parquet`; summary in the manifest: peak VRAM, mean and peak W, energy in Wh, % time per throttle reason |
| `studio profile` (build phase) | on demand | `torch.profiler` traces for PyTorch stages, Warp kernel timings; prints the matching Nsight command | local; summaries publishable for open runtimes |
| Nsight Systems (optional) | per capture | CUDA kernels, NVTX ranges, Python sampling on Windows, PyTorch annotations [4] | raw `.nsys-rep` stays local; exported to Parquet/SQLite summaries [4] |

**VRAM is device-level.** Under Windows' WDDM driver model, per-process GPU memory is not available, because Windows
manages the memory [5]; guards and manifests therefore use device-level used/free memory and each framework's own
allocator counters.

## Steps

1. **Record telemetry for one probe** without updating the committed capabilities file, then open the local report.

   ```bash run deferred=P6
   uv run --extra runner python studio/bench/run_bench.py warp_newton --no-write
   ```

   The report's `telemetry` block per probe holds the sample count, maximum temperature, maximum power, power limit,
   maximum used memory, maximum utilisation, the PCIe replay-counter delta and, on Windows, the WHEA event delta. A
   non-zero PCIe or WHEA delta during a probe is a hardware warning worth investigating before long runs.

2. **Profile a stage** with the framework profilers.

   ```bash run deferred=P6
   uv run --extra runner studio profile studio/recipes/cases/a3.yaml --stage st50_physics
   ```

3. **Capture with Nsight Systems** (maintainer, elevated shell; illustrative form):

   ```bash run deferred=P6
   nsys profile --trace=cuda,nvtx --python-sampling=true -o st50_physics <command printed by studio profile>
   nsys export --type=parquetdir st50_physics.nsys-rep
   ```

4. **Publish** the summaries of open-runtime stages to `/studio/gpu` with the run.

   ```bash run deferred=P6
   uv run --extra runner studio publish <run_id>
   ```

## Expected output

- Step 1: `[bench] warp_newton: pass (<seconds> s)` and `[bench] local report: <path>`; the committed file is not
  touched (`--no-write`).
- Steps 2–4: per stage, a timeline of busy %, VRAM against 16 GB, power against the enforced limit, SM clock and
  throttle reasons, with a "how measured" note on the web.

## What may be published

| Stage runs on | GPU evidence on the site |
|---|---|
| Warp, Newton, MuJoCo-Warp, PyTorch, ONNX Runtime, regular TensorRT for PitStudio's models, FFmpeg/NVENC | full timelines and summaries |
| Isaac Sim, Kit, Replicator, ovrtx, TensorRT for RTX | outputs only, with "performance local-only (licence)" (NVIDIA SLA §8.9 [6]; TensorRT for RTX SLA §2.13 [7]) |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `GPU hold in <dir>/gpu0.hold: <reason> -- not starting` (exit 4) | a hold file stops all GPU work on the machine, for every project sharing `GPU_LOCK_DIR` | resolve the reason written in the file; only then delete it |
| `GPU lock <dir>/gpu0.compute is held by another job -- not starting` (exit 3) | another GPU job is running | wait for it; never run two heavy GPU jobs at once |
| Utilisation is high but the stage is slow | the GPU spent the run in `SwPowerCap` or a thermal state | read the throttle fractions; compare runs only under similar conditions |
| `nsys` refuses to start | not an elevated shell, or performance counters not enabled | maintainer act; NVML evidence remains available without it |
| Per-process memory shows "N/A" | WDDM on Windows | expected; use device-level memory |

## Assumptions and limits

- Telemetry describes one laptop GPU under its own power limit; it is evidence of what happened, not a benchmark of
  the hardware.
- Sampling at 1–4 Hz misses sub-second spikes; peak VRAM is a sampled peak, guarded with a margin.

## In PitStudio

- Spec `006-media-telemetry` (NVML/NVTX telemetry, publish) and `002-runner` (guards, hold, locks); `/studio/gpu` in
  [web structure](../web/structure.md).

## References

1. NVIDIA, "NVML API Reference: Clocks Event Reasons" (updated 2026-09-09). https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html
2. NVIDIA, "Nsight Systems User Guide" (2026.5) — "You must run the CLI on Windows as administrator"; CLI switches and export. https://docs.nvidia.com/nsight-systems/UserGuide/index.html
3. PyPI, `pynvml` — deprecated in favour of `nvidia-ml-py`. https://pypi.org/pypi/pynvml/json
4. NVIDIA, "Nsight Systems User Guide" — `nsys export` types, `--python-sampling` on Windows, `--pytorch` annotations. https://docs.nvidia.com/nsight-systems/UserGuide/index.html
5. NVIDIA, "nvidia-smi documentation" — per-process memory not available under WDDM on Windows. https://docs.nvidia.com/deploy/nvidia-smi/index.html
6. NVIDIA, "NVIDIA Software License Agreement", §8.9. https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
7. NVIDIA, "TensorRT for RTX Software License Agreement", §2.13. https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
