# Capabilities probe

> The bench that checks, tool by tool, what actually runs on the studio machine and at which versions, and commits
> only what licences allow to publish, with local paths scrubbed. · Part of: [Studio](README.md) · Related:
> [Runner](runner.md) · [Capabilities contract](../data-contract/capabilities.md) · [Nsight / NVML](../frameworks/nsight-nvml.md) ·
> [DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)

## What and why

Before any long GPU run, the studio must know which tools work on this machine — driver, CUDA runtime, encoder,
NVIDIA runtimes — and record that in a committed file. Recipes then fail fast on a missing capability instead of
failing at 3 a.m. The probe is also the first evidence a reader sees: versions, pass/fail, and the numbers each tool's
licence allows us to publish.

The planned runner command `studio bench env` wraps it. **Status today:** the bench is written and lives in
`studio/bench/`; its contract tests pass in CI; it has **not yet run on the reference machine**, which is under a GPU
hold, so `studio/capabilities.json` does not exist yet.

## What exists today

| File | Role |
|---|---|
| `studio/bench/run_bench.py` | orchestrator: GPU hold check, machine-wide lock, start guards, NVML telemetry, Windows hardware-error delta, local report, public view |
| `studio/bench/_common.py` | shared by every probe, standard library only: the result shape, the `run_probe` wrapper, `SkipProbe`, scratch folders, the managed-interpreter check |
| `studio/bench/_onnx_model.py` | a tiny Conv → ReLU → GlobalAveragePool graph with seeded weights, opset 17, **IR version 10**, shared by the ONNX Runtime and TensorRT probes |
| `studio/bench/probe_warp_newton.py` | Warp kernels and a Newton step (`studio/`) |
| `studio/bench/probe_torch_ort.py` | PyTorch GEMM and torch ↔ ONNX Runtime CUDA parity (`pipeline/`, extra `cu130`) |
| `studio/bench/probe_tensorrt.py` | a TensorRT 11 FP32 engine and its parity (`pipeline/accel/`) |
| `studio/bench/probe_nvenc.py` | FFmpeg 8.1 NVENC encodes and a full decode check (`studio/` + external FFmpeg) |
| `contracts/capabilities.schema.json` | JSON Schema 2020-12 of the committed report |
| `tests/contract/test_capabilities_contract.py` | five contract tests (below) |

The probe registry also names `ovrtx`, `isaacsim` and `isaaclab`; their scripts are not written yet, so a run reports
them as `skip` ("probe script not written yet"). An opt-in `stress` probe (VRAM pattern fill, host–device copy loops,
sustained compute) runs only when named explicitly; it is the check that decides whether a machine is fit for long
GPU runs.

## How a run works

1. **Hold.** If `GPU_LOCK_DIR/gpu0.hold` exists, print its reason and exit with code **4**. `GPU_LOCK_DIR` is the
   machine-wide lock directory shared by every project (default: `gpu-locks` in the system temp folder).
2. **Lock.** Take `GPU_LOCK_DIR/gpu0.compute` with a 5 s timeout; if another job holds it, exit with code **3**.
3. **Per probe**, in its own locked environment:
   - skip if the script is missing, or if the environment is not installed (`uv sync` first);
   - read NVML: skip if free VRAM is below **4,096 MB** (another job is using the GPU) or the GPU is above **80 °C**;
   - count Windows WHEA hardware-error events;
   - run `uv run --locked --project <env> python probe_<name>.py` with a timeout (default 1,800 s) while NVML is
     sampled at **2 Hz**;
   - take the last JSON line of the probe's output as its result, and add wall time, a telemetry summary (samples, peak
     temperature, peak power, enforced power limit, peak memory used, peak utilisation, PCIe replay-counter delta) and
     the WHEA-event delta.
4. **Release** the lock.
5. **Write** everything to a local report, `$PITSTUDIO_TMP/bench/bench-<UTC time>.json` (git-ignored).
6. **Merge** the public view into `studio/capabilities.json`, unless `--no-write` is given.

| Exit code | Meaning |
|---|---|
| 0 | no probe failed (passes and skips only) |
| 1 | at least one probe failed |
| 2 | usage error (unknown probe name) |
| 3 | the GPU lock is held by another job; nothing ran |
| 4 | a GPU hold is in place; nothing ran |

Every probe prints one JSON object: `probe`, `status` (`pass`, `fail` or `skip`), `publish` (`public` or
`local-only`), `versions`, `metrics`, `notes`. A probe never raises: an exception becomes `fail` with its message, and
`SkipProbe` (a missing external tool or maintainer act) becomes `skip`. A probe whose interpreter is the Microsoft
Store shim (`WindowsApps` in its path) fails, which enforces the uv-managed-Python rule ([Environments](environments.md)).

## The four probes

| Probe | Environment | What it does | Pass condition | Publish |
|---|---|---|---|---|
| `warp_newton` | `studio/` | initialises Warp, records the CUDA device and architecture; runs a saxpy over 2²⁴ elements 20 times after a JIT warm-up; builds 64 Newton particles over a ground plane and runs 240 XPBD steps at Δt = 1/240 s (one second of free fall from about 1 m) | every sampled $y$ equals $2 + 3 \times 21 = 65$ exactly; every particle ends below 1.0 m and above −0.05 m | public |
| `torch_ort` | `pipeline/` (`cu130`) | preloads CUDA DLLs; records torch, CUDA, cuDNN and ORT versions; times fp16 and bf16 GEMMs at $N = 4096$; runs the probe graph on the ORT CUDA EP (TF32 off) and the same convolution in torch | ORT really used the CUDA EP; max absolute difference torch vs ORT ≤ 1 × 10⁻⁴ | public |
| `tensorrt` | `pipeline/accel/` | hashes the TensorRT `LICENSE.txt`; points `CUDA_PATH` at the CUDA 13 runtime wheel; builds an FP32 engine with Polygraphy; times 50 inferences | max absolute difference TensorRT vs ORT CPU ≤ 1 × 10⁻⁴ | public; **local-only if the licence text changed** |
| `nvenc` | `studio/` + FFmpeg | finds FFmpeg (`PITSTUDIO_FFMPEG` or `PATH`, else skip); records its version; encodes a 10 s 1920 × 1080, 30 fps test pattern with `av1_nvenc` (preset p5, CQ 30) and `h264_nvenc` (preset p5, CQ 23); decodes each file fully | both encoders present; both files decode with no error output | public |

GEMM throughput is computed as

$$
\Theta = \frac{2 N^3 R}{t},
$$

where $N = 4096$ is the matrix size, $R = 20$ the repetitions, $t$ (s) the measured wall time between CUDA
synchronisations and $\Theta$ the result in FLOP/s: each measurement performs $2 \cdot 4096^3 \cdot 20 \approx
2.75 \times 10^{12}$ floating-point operations. NVENC frames per second include the CPU-side test-pattern generation,
and the probe says so.

Checks made without a GPU so far: the probe graph matches torch on the CPU to 3 × 10⁻⁶; the TensorRT licence hash and
the CUDA 13 `cudart` resolution; FFmpeg n8.1.3 installed with both encoders listed. Two findings shaped the code: `onnx`
now writes IR 14 by default while ONNX Runtime 1.30 reads at most IR 13, hence the pinned IR 10; and a machine-wide
CUDA 12 toolkit's `CUDA_PATH` would make Polygraphy load the CUDA 12 runtime, hence the redirection.

## Public vs local-only

`public_view()` builds the committed report, and the schema makes leaks fail validation:

- each probe keeps `status` and `versions` (plus the probe's Python version);
- `metrics` are copied **only** when the probe says `publish: public`; otherwise the field holds the literal string
  `measured locally, not published (licence)`, the only non-object value the schema accepts;
- `telemetry` is copied only for public probes;
- `notes` and `error` are scrubbed, and `error` is cut to 300 characters;
- the report holds the GPU name, the driver version and the date — no host name, user name or path.

Why: the NVIDIA Software License Agreement §8.9 forbids disclosing "results of benchmarking … or performance data
relating to the Software" without written permission [1], which covers ovrtx, Isaac Sim, Kit and Replicator. The
regular TensorRT licence has no such clause [2], so the TensorRT probe is public — but it pins the reviewed licence by
SHA-256 (`c86915fd…88b4`), and if NVIDIA changes the text the result drops to local-only until it is re-read. TensorRT
for RTX keeps its own ban on publishing benchmarks (§2.13) [3] and has no public probe.

**Path scrubbing.** Before anything is written to the committed file, the repository root becomes `<repo>` and the home
directory becomes `~`, in three spellings each (native separators, forward slashes, escaped backslashes).

## Contract tests

| Test | What it proves |
|---|---|
| `test_schema_is_valid_2020_12` | the schema itself is valid JSON Schema 2020-12 |
| `test_public_view_matches_schema` | a mixed set of results (pass, fail, skip, local-only) produces a valid report |
| `test_local_only_probe_publishes_no_metrics_or_telemetry` | a local-only probe exposes neither metrics nor telemetry; a public one keeps both |
| `test_local_paths_are_scrubbed_and_errors_truncated` | no home or repository path survives; errors are ≤ 300 characters |
| `test_committed_report_matches_schema_when_present` | the committed `studio/capabilities.json`, once it exists, stays valid |

They need no GPU and run in CI:

```bash run
uv run pytest tests/contract/test_capabilities_contract.py
```

On a machine with an NVIDIA GPU and no hold file, the bench itself is run as below (shown, not executed here: the
reference machine is under a GPU hold):

```bash run deferred=P6
uv run --extra runner python studio/bench/run_bench.py
uv run --extra runner python studio/bench/run_bench.py warp_newton nvenc --no-write
```

Once the runner exists, the same check is one command:

```bash run deferred=P6
uv run studio bench env
```

## Which probes come next

| Probe | Environment | Waits for | Publish |
|---|---|---|---|
| ovrtx render (camera and lidar) | `studio/rtx/` | the GPU hold to lift; written against the API docs, never the examples | local-only |
| Isaac Sim Compatibility Checker + headless smoke | `studio/isaac/` | the maintainer's EULA acceptance | versions and pass/fail public; performance local-only |
| Synthetic-data images per second | `studio/isaac/` | the Isaac Sim smoke | local-only |
| Isaac Lab kit-less smoke | `studio/isaaclab/` | a consistent Isaac Lab lock | public (open stack) |
| llama.cpp smoke | `studio/reason/` | the binary is ready; Cosmos weights need the gated terms | public (runtime is MIT) |
| Brush smoke | external | the binary is ready | public |
| MakeHuman export smoke | external | opens an OpenGL window | public |

## Assumptions and limits

- The WHEA count uses `wevtutil` and exists only on Windows; elsewhere it is omitted. The PCIe replay counter may be
  unsupported and is then recorded as −1.
- NVML utilisation is a time-busy fraction, not occupancy ([Nsight / NVML](../frameworks/nsight-nvml.md)).
- One run proves a capability on one driver at one date; the report records both, and a driver change means a re-run.
- The probes test a tiny graph, not our models; model-level parity is the job of `s60_export` and `s64_bench`.

## In PitStudio

- Status: written; **not yet run** on the reference machine.
- The committed report feeds the runner's guards and the web's `/studio/gpu` page ([Capabilities contract](../data-contract/capabilities.md)).

## References

1. NVIDIA. *NVIDIA Software License Agreement* (2026-05-07), §8.9.
   https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
2. NVIDIA. *TensorRT Software License Agreement*. https://docs.nvidia.com/deeplearning/tensorrt/latest/reference/sla.html
3. NVIDIA. *TensorRT for RTX Software License Agreement*, §2.13. https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
4. NVIDIA. *NVML device queries*. https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceQueries.html
5. NVIDIA. *NVML clocks event reasons*. https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html
