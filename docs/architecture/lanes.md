# Lanes and the measured gate

> Every capability in PitStudio runs in one of four lanes (live, precompute, replay, local-only); a measured gate,
> not a preference, decides which, and the decision is recorded per artefact and checked in CI. · Part of:
> [architecture](README.md) · Related: [compute lanes](../pipelines/compute-lanes.md) ·
> [compute tiers](../web/compute-tiers.md) · [budgets](../web/budgets.md) · [showcase rules](../web/showcase-rules.md)

## What and why

A static website cannot run Isaac Sim, train a detector or simulate a million particles. It can run an analytical
model, a discrete-event simulation, a small ONNX model or a few thousand particles on the visitor's GPU. PitStudio
therefore splits every capability into the part that runs **live** in the browser and the part that is **precomputed**
on the studio and **replayed** on the site. A fourth lane, **local-only**, exists for a licence reason: some NVIDIA
licences forbid publishing performance data of their software. The lane of each capability is decided by measurement
and shown to the visitor on every artefact, so that nobody mistakes a replay for a live computation.

## The four lanes

| Lane | Where it is computed | What the visitor sees | Badge | Diagram colour |
|---|---|---|---|---|
| Live | In the visitor's browser, now: TS workers, WGSL compute, ORT-web, Rapier WASM, Pyodide | Results that change with the sliders | **LIVE** | `--chart-2` |
| Precompute | On the studio or pipeline, by a named tool in a named run | Nothing directly; it produces replay artefacts | — | `--chart-4` |
| Replay | Baked artefacts animated in the browser: video, particle and pose shards, event traces, tables | A recorded result with its run id and provenance | **REPLAY** | `--chart-4` |
| Local-only | Performance data (timings, telemetry, profiles) of licence-restricted software, measured on the maintainer's machine | A "measured locally, not published (licence)" card | `performance: local-only` | `--warning` |

Figures that are neither computed nor replayed (diagrams, photographs) carry **STATIC**. Local-only applies to
*performance data*, not to outputs: an Isaac Sim render is published as a replay, while the time Isaac Sim took to make
it is not ([DEC-0005](decisions/DEC-0005-performance-data-licence-rule.md)).

## The measured gate

A capability is live if and only if four measured conditions hold:

$$
\text{LIVE} \iff D \;\wedge\; S_\text{asset} \le 25\ \text{MB} \;\wedge\;
\big(t_\text{int} \le 16\ \text{ms} \;\vee\; t_\text{run} \le 1\ \text{s on T2}\big) \;\wedge\; S_\text{trace} \le 10\ \text{MB}
$$

- $D$: the capability is web-drivable, i.e. it needs no GPU runtime, proprietary engine or server (boolean).
- $S_\text{asset}$: the size of the largest file of the capability's own (MB): its model, policy, shard, scene or
  fixture. Shared runtimes (ORT-web's WASM build, Pyodide, Rapier) are not counted here; they have their own class
  budget of ≤ 55 MB ([budgets](../web/budgets.md)).
- $t_\text{int}$: the time of one interaction step (ms); 16 ms is one frame at 60 frames per second
  ($1000/60 = 16.7$ ms).
- $t_\text{run}$: the time of a complete run (s), such as one simulated shift of a discrete-event model, measured on the
  WebAssembly tier T2, the slower of the two compute tiers.
- $S_\text{trace}$: the size of any trace or shard the live engine streams (MB).

Otherwise the capability is precomputed and replayed. Independently of the gate, the performance data of software
covered by NVIDIA SLA §8.9 or the TensorRT for RTX licence §2.13 is local-only [1] [2].

![The measured lane gate](../assets/diagrams/lanes-measured-gate.svg)

*Four checks in sequence: any "no" sends a capability to precompute and replay; only a capability that passes all four
is live; a separate licence check keeps restricted performance data local-only.*

## Lane per capability

The measurements in this table are **estimates** from the plan. They are measured in the data-and-models phase and
recorded in each artefact's manifest.

| Capability | Methods | Lane | Gate measurements (estimate) | Fallback |
|---|---|---|---|---|
| Analytical models (match factor, road energy, blasting, slope LEM, plume, comminution, dust and slope-radar models) | M01, M06, M12, M13, M16, M17, M23 | live (TypeScript + `minephys` through a Pyodide button) | < 50 KB of JavaScript; < 1–50 ms per evaluation | baked grid |
| Discrete-event haulage and dispatch policies; Isaac Lab policies on TypeScript twins | M02, M04, M05, M21 | live (TS worker + ORT-web) | policies < 2 MB; one shift ≈ 10⁴ events in < 1 s | baked traces |
| Min-cut ultimate pit | M18 | live up to 10⁵ blocks | < 1 s | baked shells |
| Rigid-body traffic | M20 | live (Rapier) | Rapier ~2 MB; 60 Hz for ≤ 40 vehicles | baked video |
| Granular flow | M07 | replay + live WGSL (≤ 2×10⁴ particles) | shards ≤ 10 MB; ≥ 30 fps on T1 | baked aggregates |
| GNS, FNO, slope forecasters, mine-to-mill meta-model, D-FINE-N/S int8, U-Net | M08, M10, M11, M14, M15, M17 | live (ORT-web, WebGPU → WASM) | each ≤ 25 MB; ≤ 50 ms per step (surrogates), ≤ 300 ms per image (detector, T1) | precomputed outputs |
| RF-DETR-Seg-N, D-FINE-S fp32 | M10 | precompute | 61 MB and 40 MB, over the 25 MB cap | — |
| RTX renders, synthetic data, sensor point clouds, Kit captures, Isaac Lab rollouts | M10, M21, M23 | replay | videos ≤ 25 MB per AV1 + H.264 pair; point clouds in ≤ 10 MB shards | poster frames |
| Cosmos Reason 2 answers and captions | M22 | precomputed, display-only | text < 1 MB | — |
| Performance of Isaac Sim, Kit, Replicator, ovrtx, TensorRT for RTX | — | local-only | — | "measured locally, not published" card |
| Regular TensorRT latency and throughput of our own models | — | replay (published; its licence has no benchmark clause) | tables < 200 KB | data table |
| GPU telemetry of open-runtime stages | — | replay (charts) | ≤ 200 KB per run | data table |

## Compute tiers in the browser

Live capabilities run on the best tier the visitor's browser offers, and the active tier is always shown:

- **T1, WebGPU:** WGSL compute kernels and the ORT-web WebGPU execution provider. WebGPU is not yet available
  everywhere [3].
- **T2, WebAssembly:** the same engines on the CPU, with smaller problem sizes where needed. The gate's timing is
  measured on T2 so that a live capability stays live without WebGPU.
- **T0, baked:** precomputed aggregates or grids when neither tier is available or the visitor prefers not to compute.

See [compute tiers](../web/compute-tiers.md).

## Parity by system class

A live engine re-implements, in TypeScript or WGSL, something the Python side also computes. Bit-exact equality is
impossible for some systems, so parity is defined per class ([DEC-0006](decisions/DEC-0006-3d-and-simulation-on-static-web.md)):

| System class | Examples | Parity test |
|---|---|---|
| Discrete-event and analytical (deterministic) | haulage DES, LEM, Kuz-Ram, plume | **Exact event trace** against Python goldens. Seeded counter-based PRNG, explicit tie-breaks, no `Math.*` transcendental calls in variate generation, because their precision differs between browsers [4] |
| Deterministic rigid-body physics | Rapier traffic | **Snapshot hash** against goldens generated in Node with the same Rapier version [4] |
| Chaotic and particle systems | DEM, MPM, shallow water in WGSL; Warp twins | **Per-kernel unit parity** plus **observables**: repose angle ±1.5°, run-out and discharge ±5 %, mass drift < 0.5 % (ratified in the specifications) |
| Machine-learning models | ONNX in ORT-web | Numerical tolerances from `specs/000-foundation/thresholds.yaml`: WASM fp32 max abs error ≤ 1e-4, WebGPU fp32 ≤ 1e-3, fp16 ≤ 1e-2, top-1 agreement ≥ 0.995 |

ONNX models are exported at opset 17–19, chosen per model with the reason recorded in the manifest: PyTorch's default
export opset is 20, but ORT-web registers WebGPU kernels such as `GridSample` only for opset 16–19 [5]. Parity is
checked against PyTorch fp32 ([export, parity and acceleration](../models/export-parity-acceleration.md)). The
bootstrap probe also found that the `onnx` library
writes IR version 14 by default while ONNX Runtime 1.30 reads at most IR 13, so the export stage pins the IR version
explicitly.

## How the lane is recorded and enforced

- **In the manifest.** Every published artefact carries its lane, the measurements behind it, its licence class and,
  where applicable, the `performance: local-only` marker ([manifest](../data-contract/manifest.md)).
- **In CI.** A lane label that does not match its recorded measurements fails the build; so does any published
  performance field for a stage marked `performance: local-only`, and any budget overrun ([budgets](../web/budgets.md)).
- **On screen.** Every artefact card shows LIVE, REPLAY or STATIC; a studio tool with nothing published shows "not yet
  run" ([showcase rules](../web/showcase-rules.md)).

## Assumptions and limits

- The thresholds 25 MB, 16 ms, 1 s and 10 MB are design limits chosen for a 2 MB first view and a 500 MB site; they
  are not universal truths about browsers.
- Timings depend on the measuring machine. The gate is measured on the reference configurations named in the
  manifest, and a slower visitor device may still feel slow; the tier badge and the T0 fallback cover that case.
- A capability can move lanes between releases when its measurements change; the manifest records which release
  measured it.

## In PitStudio

- Code: the lane gate lives in `src/pitstudio/` (planned); the web app reads lanes from the web manifest.
- Related pages: [compute lanes](../pipelines/compute-lanes.md) (the CPU/GPU side), [compute tiers](../web/compute-tiers.md),
  [budgets](../web/budgets.md).
- Status: **Not yet run** — the gate measurements are produced in the data-and-models phase; until then every number
  in the table above is an estimate from the plan.

## References

1. NVIDIA Software License Agreement (2026-05-07), §8.9.
   https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
2. NVIDIA TensorRT for RTX, software license agreement, §2.13.
   https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
3. Can I use: WebGPU. https://caniuse.com/webgpu
4. Rapier. JavaScript determinism guide. https://rapier.rs/docs/user_guides/javascript/determinism
5. ONNX Runtime Web. WebGPU operator list.
   https://github.com/microsoft/onnxruntime/blob/main/js/web/docs/webgpu-operators.md
