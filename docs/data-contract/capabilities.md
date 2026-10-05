# Capabilities

> The committed capability report, `studio/capabilities.json`, and its schema `contracts/capabilities.schema.json`,
> field by field: which GPU tools run on the reference machine, in which versions, with which publishable metrics. ·
> Part of: [Data contract](README.md) · Related: [Capabilities probe](../studio/capabilities-probe.md) ·
> [Manifest](manifest.md) · [Environments](../studio/environments.md) · [Sources and licences](sources-and-licences.md)

## What and why

Several studio tools are gated by things the code cannot control: the NVIDIA driver version, the GPU architecture, the
CUDA runtime a wheel finds, an NVIDIA licence that forbids publishing performance data. Instead of assuming, PitStudio
probes each tool once on the reference machine and commits the result. Recipes then fail fast when a stage needs a
capability the report does not show, and the web `/studio` pages show the versions and the pass / fail state of every
tool. The report is the first artefact of the project that applies the licence rule mechanically: metrics of
licence-restricted tools are replaced by a fixed string before the file is written.

This is the one contract that **exists today**: the schema, the bench runner (`studio/bench/run_bench.py`), four probe
scripts and five contract tests are in the repository.

## The document: top-level fields

`contracts/capabilities.schema.json` is JSON Schema 2020-12 with `$id`
`https://fsantibanezleal.github.io/PitStudio/contracts/capabilities.schema.json`. The top level is a closed object
(`additionalProperties: false`).

| Field | Required | Type and constraint | Written by `run_bench.py` as |
|---|---|---|---|
| `$schema` | no | string | `"../contracts/capabilities.schema.json"`, so editors validate the file in place |
| `generated` | **yes** | string, `format: date` | the local date of the run, ISO 8601 (`YYYY-MM-DD`) |
| `gpu` | **yes** | string, `minLength: 1` | the NVML device name of GPU 0 |
| `driver` | **yes** | string, pattern `^[0-9]+(\.[0-9]+)+$` | the NVML system driver version, e.g. `582.78` |
| `probes` | **yes** | object; property names match `^[a-z][a-z0-9_]*$`; each value is a `probe` | one entry per probe, merged with the probes of earlier runs |

Merging means that running a single probe updates its own entry and keeps the others. A machine identifier never
appears: the GPU model and driver version are the only hardware facts.

## The `probe` object

Each probe entry is also closed (`additionalProperties: false`).

| Field | Required | Type and constraint | Meaning |
|---|---|---|---|
| `status` | **yes** | enum `pass`, `fail`, `skip` | `skip` = a prerequisite outside the environment is missing (tool not installed, environment not synced, another job holds the GPU, GPU too hot); `fail` = the probe ran and something was wrong |
| `versions` | **yes** | object of strings | versions read at run time; the bench prepends `python` (the interpreter version of the probe's environment) |
| `metrics` | no | **either** an object of numbers or strings, **or** the constant `"measured locally, not published (licence)"` | the measured figures for public probes; the constant for licence-restricted ones |
| `telemetry` | no | object of numbers | NVML summary of the probe window; present **only** for public probes |
| `notes` | no | array of strings | human-readable notes, with local paths scrubbed |
| `error` | no | string, `maxLength: 300` | the failure message, scrubbed and truncated |

The `oneOf` on `metrics` is the licence rule in schema form: a licence-restricted probe cannot carry numbers in the
committed file, because the only other allowed value is the constant string.

### Telemetry keys

The bench samples NVML at 2 Hz while a probe runs and writes this summary (all numbers):

| Key | Meaning |
|---|---|
| `samples` | number of samples |
| `max_temp_c` | maximum GPU temperature, °C |
| `max_power_w`, `power_limit_w` | maximum board power and the enforced power limit, W |
| `max_mem_used_mb` | maximum device memory used, MiB |
| `max_util_pct` | maximum NVML utilisation (time-busy fraction, not occupancy [1]) |
| `pcie_replays_delta` | change of the PCIe replay counter during the probe |
| `whea_events_delta` | change in the number of WHEA hardware-error events in the Windows System log (Windows only) |

The last two exist because the reference laptop has logged PCIe-link errors on its GPU; every probe now records whether
it coincided with new hardware errors.

## The probe protocol

Every probe is a script `studio/bench/probe_<name>.py` that runs inside its own environment and prints one JSON object
as the last line of standard output (helpers in `studio/bench/_common.py`, standard library only):

```json
{"probe": "tensorrt", "status": "pass", "publish": "public",
 "versions": {"tensorrt": "…", "polygraphy": "…"}, "metrics": {"trt_infer_median_ms": 0.0},
 "notes": [], "env": {"python": "3.14.x", "managed_interpreter": true}}
```

- A missing external prerequisite raises `SkipProbe` → `status: skip`.
- Any other exception → `status: fail` with the exception text; a probe never crashes the bench.
- `publish` is `public` or `local-only` and follows the tool's licence. The bench uses it to build the public view.
- If the interpreter is the Microsoft Store shim instead of a uv-managed Python, the probe is marked `fail`.

| Probe | Environment (`uv run --project … --locked`) | Script today | Publish | What it checks |
|---|---|---|---|---|
| `warp_newton` | `studio` | written | public | Warp SAXPY on 2²⁴ elements ×20 with a result check; a 64-particle Newton XPBD drop over 240 steps that must stay above the ground; OpenUSD import |
| `torch_ort` | `pipeline` (extra `cu130`) | written | public | fp16 and bf16 GEMM throughput at 4096²; ONNX Runtime CUDA EP vs PyTorch on a Conv→ReLU→GlobalAveragePool graph, TF32 off, max abs error ≤ 1e-4 |
| `tensorrt` | `pipeline/accel` | written | public, unless the licence hash changed | TensorRT 11.3 FP32 engine built with Polygraphy from the same graph; median of 50 inferences; max abs error vs ONNX Runtime CPU ≤ 1e-4; SHA-256 of the wheel's licence text |
| `nvenc` | `studio` | written | public | FFmpeg `av1_nvenc` (preset p5, cq 30) and `h264_nvenc` (preset p5, cq 23) on a 10 s 1080p30 test pattern; a full decode must be clean; fps and kbps |
| `ovrtx` | `studio/rtx` | not yet | local-only (licence) | RTX render through ovrtx |
| `isaacsim` | `studio/isaac` | not yet | local-only (licence) | Compatibility Checker + headless smoke |
| `isaaclab` | `studio/isaaclab` | not yet | decided by the licences of what it loads | kit-less smoke |

The shared probe graph (`studio/bench/_onnx_model.py`) is built with `onnx.helper` at opset 17 and **IR version 10**:
`onnx` writes IR 14 by default while ONNX Runtime 1.30 reads at most IR 13, so the IR version is pinned
([Export, parity and acceleration](../models/export-parity-acceleration.md)).

## What `run_bench.py` does

1. **GPU hold.** If a file `gpu0.hold` exists in the machine-wide lock folder (`GPU_LOCK_DIR`), the bench prints its
   reason and exits with code 4 before touching the GPU.
2. **Lock.** It takes the machine-wide lock `gpu0.compute` (5 s timeout; exit code 3 if another job holds it), so a
   probe never runs next to another GPU job of any project on the machine.
3. **Guards per probe.** It skips a probe when the probe script or its environment is missing, when less than
   4,096 MB of VRAM is free, or when the GPU is above 80 °C before start. Each probe has a timeout (default 1,800 s).
4. **Run.** It launches `uv run --locked --project <env> [extras] python probe_<name>.py`, samples NVML, and records
   the wall time and the WHEA delta.
5. **Write.** It writes everything, including licence-restricted metrics and telemetry, to a local report
   `$PITSTUDIO_TMP/bench/bench-<UTC time>.json` (never committed), then the **public view** to
   `studio/capabilities.json`:
   - `metrics` are copied only for `publish: public`; otherwise they become the constant string;
   - `telemetry` is copied only for public probes;
   - in `notes` and `error`, the repository root becomes `<repo>` and the home folder `~`; `error` is cut to 300
     characters.
6. **Exit code.** 0 when no probe failed, 1 otherwise.

## Contract tests

`tests/contract/test_capabilities_contract.py` holds five tests that run in CI without a GPU:

| Test | Asserts |
|---|---|
| `test_schema_is_valid_2020_12` | the schema itself is valid JSON Schema 2020-12 |
| `test_public_view_matches_schema` | a public view built from sample results validates |
| `test_local_only_probe_publishes_no_metrics_or_telemetry` | a local-only probe gets the constant string and no telemetry; a public probe keeps both, with `python` first in `versions` |
| `test_local_paths_are_scrubbed_and_errors_truncated` | no home or repository path survives; errors are ≤ 300 characters and start with the scrubbed path |
| `test_committed_report_matches_schema_when_present` | the committed `studio/capabilities.json`, once it exists, validates |

```bash run
uv run pytest tests/contract -m "not gpu"
```

## Assumptions and limits

- The report describes **one** machine on **one** date. It is evidence that a tool ran there, not a claim that it runs
  everywhere; the Linux profile gets its own probes when a Linux GPU host exists.
- NVML "utilisation" is a time-busy fraction over a 1/6–1 s window [1]; a single small kernel can read 100 %. The
  report keeps the maximum only as a sanity signal, never as a performance claim.
- Probe metrics are smoke-test numbers (tiny graphs, a test pattern), not benchmarks of the tools. Model benchmarks come
  from `s64_bench` ([Export, parity and acceleration](../models/export-parity-acceleration.md)).
- The TensorRT probe's publish status depends on a licence text it hashes at run time: the reviewed `LICENSE.txt` of the
  TensorRT 11.3.0.99 wheels is 47,141 bytes with SHA-256
  `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4`, and it contains no benchmark clause [2].

## In PitStudio

- **Files:** `contracts/capabilities.schema.json`, `studio/bench/run_bench.py`, `studio/bench/_common.py`,
  `studio/bench/_onnx_model.py`, `studio/bench/probe_{warp_newton,torch_ort,tensorrt,nvenc}.py`,
  `tests/contract/test_capabilities_contract.py`.
- **Consumers:** runner guards (recipes fail fast on a missing capability), the web `/studio` pages, the
  [Capabilities probe](../studio/capabilities-probe.md) guide.
- **Status:** the probes are written but **not yet run on the reference machine**: a machine-wide GPU hold is in place
  after two hardware bugchecks, and the bench refuses to start while it exists. `studio/capabilities.json` is therefore
  not committed yet. Checks that need no GPU are done: the probe graph matches a CPU reference (max abs error 3e-6), the
  TensorRT licence hash is recorded, the CUDA 13 runtime resolves for Polygraphy, and the FFmpeg 8.1 build lists both
  NVENC encoders. Once the hold is lifted:

```bash run deferred=P6
uv run --extra runner python studio/bench/run_bench.py
```

(While the hold file exists, this command prints the reason and exits with code 4 without touching the GPU.)

## References

1. NVIDIA, NVML API reference, `nvmlUtilization_t`. https://docs.nvidia.com/deploy/nvml-api/api/structnvmlUtilization__t.html
2. NVIDIA, *TensorRT Software License Agreement*. https://docs.nvidia.com/deeplearning/tensorrt/latest/reference/sla.html
3. JSON Schema 2020-12 specification. https://json-schema.org/draft/2020-12/schema
4. NVIDIA, NVML API reference, device queries (PCIe replay counter, power, memory). https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceQueries.html
