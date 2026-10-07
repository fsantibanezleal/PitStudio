# Compute tiers

> How the browser decides where to compute — T1 WebGPU, T2 WebAssembly, T0 baked — which engines run on each tier, how
> they fall back, how their results are kept equal to the Python references, and why heavy runtimes load only on a user
> action. · Part of: [Web](README.md) · Related: [compute lanes](../pipelines/compute-lanes.md) ·
> [Rapier / WebGPU / Pyodide](../frameworks/rapier-webgpu-pyodide.md) · [ONNX Runtime](../frameworks/onnx-runtime.md) ·
> [budgets](budgets.md)

## What and why

A *lane* says where a result is produced: **live** in the browser, **precompute** on the local studio, **replay** of
committed outputs ([compute lanes](../pipelines/compute-lanes.md)). A *tier* says which live machinery the visitor's
browser actually offers. The same case page must work on a desktop with WebGPU, on a browser without it, and when a
runtime fails, and it must say which of these happened. Three tiers cover that:

| Tier | Condition | What runs |
|---|---|---|
| **T1 · WebGPU** | `navigator.gpu.requestAdapter()` returns an adapter and a device is created | WGSL compute kernels, ORT-web WebGPU execution provider, three.js `WebGPURenderer`, plus everything of T2 |
| **T2 · WebAssembly** | no adapter, device lost, or T1 initialisation failed | TypeScript workers, ORT-web WASM execution provider, Rapier (WASM), Pyodide; WebGL 2 rendering; no GPU compute |
| **T0 · baked** | a runtime failed or WebAssembly is unavailable | precomputed outputs, videos, posters and figures only; nothing computed |

The active tier is **always shown** as a badge, and a failed tier falls back to the next one (FR-000-02).

![Compute tiers](../assets/diagrams/compute-tiers.svg)

*The probe picks T1 when an adapter is granted; each engine family lists what it runs on each tier and what it falls
back to.*

## The capability probe

The probe runs once on load, before any engine, and costs no download:

1. `navigator.gpu` present → `requestAdapter()` → `requestDevice()`; read the adapter limits. The WebGPU defaults are
   `maxStorageBufferBindingSize` = 128 MiB and `maxBufferSize` = 256 MiB [1][2]; kernels are sized to stay inside the
   defaults so that no special limits are requested.
2. WebAssembly available → T2 is possible.
3. `MediaCapabilities` for AV1 and H.264 → which video of each pair to load.
4. `prefers-reduced-motion` → explainer animation off.

A lost device during a session (driver reset, tab in background on some platforms) triggers the same fallback as a
failed probe.

## Engines per tier

| Engine family | Methods | T1 | T2 | T0 | Gate figures (estimates, measured at the web phase) |
|---|---|---|---|---|---|
| Analytical models | M1, M6, M12, M13, M16 plume, M17, dust and slope-radar models | TS worker | TS worker | baked grid | < 50 KB JS; < 1–50 ms per evaluation |
| … the same in Python | `minephys` via Pyodide ("run in Python" button) | on click | on click | — | Pyodide load set 13.54 MB |
| DES and policies | M2, M4, M5; M21 TS twins of the Isaac Lab policies | TS worker + ORT-web WebGPU | TS worker + ORT-web WASM | baked traces | policies < 2 MB; one shift ≈ 10⁴ events < 1 s |
| Min-cut ultimate pit | M18 | TS worker, ≤ 10⁵ blocks | same | baked nested shells | < 1 s |
| Rigid-body traffic | M20 | Rapier WASM | Rapier WASM | baked video | Rapier 3.42 MB; 60 Hz for ≤ 40 vehicles |
| Granular, shallow water, dust fields | M7 (and the WGSL twins of the studio's Warp kernels) | WGSL compute, ≤ 2×10⁴ particles | replay shards | baked aggregates | shards ≤ 10 MB; ≥ 30 fps on T1 |
| Learned models | GNS, FNO, forecasters, mine-to-mill meta-model, D-FINE-N/S int8, U-Net | ORT-web WebGPU EP | ORT-web WASM EP | precomputed outputs | each ≤ 25 MB; ≤ 50 ms/step (surrogates), ≤ 300 ms/image (detector, T1) |
| Precompute-only models | RF-DETR-Seg-N (61 MB), D-FINE-S fp32 (40 MB) | — | — | precomputed outputs | above the 25 MB live cap |
| Studio media | RTX renders, Kit captures, rollouts, sensor clouds | AV1 1080p or H.264 720p | same | WebP posters | each video pair ≤ 25 MB; clouds ≤ 10 MB shards |

### The lane gate

A capability is LIVE only when all four conditions hold; otherwise it is precompute or replay:

$$
\text{LIVE} \iff D \;\wedge\; S_{\text{asset}} \le 25\ \text{MB} \;\wedge\; \big(t_{\text{interaction}} \le 16\ \text{ms} \;\vee\; t_{\text{run}} \le 1\ \text{s on T2}\big) \;\wedge\; S_{\text{trace}} \le 10\ \text{MB}
$$

where $D$ is "web-drivable" (the engine exists in the browser), $S_{\text{asset}}$ the largest file the engine needs
(MB), $t_{\text{interaction}}$ the time to respond to one input (ms), $t_{\text{run}}$ the time for one full run on the
WASM tier (s) and $S_{\text{trace}}$ the size of the trace it must load (MB). The 16 ms bound is one frame at 60 Hz. The
measured values are stored in the manifest; CI fails on a mislabel. The tier never changes a lane: a LIVE
engine that falls back to T0 shows its precomputed output with the REPLAY badge.

## The runtimes

**TypeScript workers.** Analytical models, the DES, min-cut and the TS twins of the Isaac Lab policies run in module
workers so the main thread stays responsive. They need no runtime download beyond the app's own JavaScript.

**WGSL compute (T1 only).** Granular, shallow-water and dust kernels are WGSL compute shaders. Scale evidence: the
three.js `webgpu_compute_particles` example simulates 200,000 particles with storage buffers and compute passes [3], and
an open MLS-MPM implementation reports about 100,000 particles on integrated graphics and about 300,000 on discrete
GPUs [4]. PitStudio's live cap of 2×10⁴ particles sits well inside that. Whether three.js's WebGL 2 backend executes
compute nodes is not documented [5], so T2 never assumes GPU compute: it switches to replay.

**ONNX Runtime Web 1.30.** One build that loads in every browser. The WebGPU execution provider is the recommended path
and the WebGL and JSEP paths are being phased out [6][7]; outputs can stay on the GPU (`preferredOutputLocation:
'gpu-buffer'`) between steps of a surrogate rollout [8]. The WebGPU operator list does not support `Conv` in 3-D, and it
does not confirm `NonMaxSuppression`, `ScatterElements` or `RoiAlign` [9]. Detectors are therefore exported with
non-maximum suppression outside the graph (done in the worker), and the GNS is exported in a dense-adjacency form when
scatter operators would fall back to the CPU. Models use ONNX opset 17–19, and the export pins the ONNX IR version to
one that both ORT (Python and web) and TensorRT read: `onnx` now writes IR 14 by default while ORT 1.30 reads at most
IR 13.

**Rapier 0.21 (WASM).** Rigid bodies for traffic and rock-fall views. The JS/WASM build is cross-platform
deterministic for the same Rapier version and identical initial conditions, verifiable with a snapshot hash, with the
caveat that `Math.sin`/`Math.cos` in the caller are not [10]. The `-compat` packages inline the WASM as base64 [11]. The
former `rapier.js` repository was archived on 2026-07-12 and merged into the `dimforge/rapier` monorepo, so the version
is pinned and tracked there [12].

**Pyodide 314.0.7 + `minephys`.** A "run in Python" button loads Pyodide [13], its `numpy` and `PyYAML` packages and
the self-hosted `minephys` wheel, then evaluates the same model with the reference implementation. `minephys` depends
only on NumPy and PyYAML for exactly this reason ([minephys](../frameworks/minephys.md)). The button doubles as a
parity demonstration: the TS port and the Python reference produce the same numbers side by side.

**Lazy loading.** None of these runtimes is in the first view. They are self-hosted (copied from npm at build, never
fetched from a CDN) and load only when the visitor opens a live tab or presses a button; the first view stays ≤ 2 MB
and the initial JavaScript ≤ 200 KB gzip ([budgets](budgets.md)).

**No threads.** GitHub Pages cannot send the COOP/COEP headers that `SharedArrayBuffer` needs, so every WASM runtime
runs single-threaded and multithreaded builds are excluded.

## Parity with the Python references

Every live engine that has a Python reference is checked against it, with tolerances by system class
(`specs/000-foundation/thresholds.yaml`, `web.*`):

| Class | Check | Tolerance |
|---|---|---|
| WASM fp32 numerics | max absolute difference vs the Python reference | $1\times10^{-4}$ |
| WebGPU fp32 numerics | max absolute difference | $1\times10^{-3}$ |
| fp16 paths | max absolute difference | $1\times10^{-2}$ |
| Classifiers / detectors | top-1 agreement | ≥ 0.995 |
| DES | event trace | exact |
| Rapier | snapshot hash vs a golden run of the same version | exact |
| Chaotic granular systems | per kernel (forces and one step on a fixed configuration) + statistical (repose angle, discharge rate, pile profile) | per kernel tight; statistical within the case's tolerance |

Exact DES parity needs care because JavaScript's `Math` functions have implementation-dependent precision across
browsers and platforms [14]. The DES therefore uses a counter-based PRNG implemented identically in Python and
TypeScript, draws variates without transcendental `Math.*` calls, and breaks event ties explicitly by
(time, priority, sequence id).

## Worked examples

**Granular replay versus live compute.** A replay of $N = 2\times10^4$ particles stores three int16 coordinates per
particle and frame: $2\times10^4 \times 3 \times 2\ \text{B} = 120\ \text{KB}$ per frame. At 10 frames/s for 20 s
that is $200 \times 120\ \text{KB} = 24\ \text{MB}$, i.e. at least three shards of ≤ 10 MB. The same scene at
$10^5$ particles would be about 120 MB, which no budget allows; that is why the large-particle views replay aggregate
fields and re-simulate on T1 instead of shipping raw frames.

**Position quantisation.** Over a pit bounding box of $L = 3.3$ km, int16 positions resolve
$L / 2^{16} = 3300 / 65536 \approx 0.05$ m. Half precision (fp16, 11 significant bits) spaces representable values
2 m apart between 2,048 and 4,096 m, so fp16 is unsuitable for absolute positions at pit scale; positions are int16
relative to the bounding box.

**GPU memory.** A live DEM state of $2\times10^4$ particles with position and velocity in fp32 is
$2\times10^4 \times 6 \times 4\ \text{B} = 480\ \text{KB}$, far below the 128 MiB default binding limit [1].

## Browser support

| Browser | WebGPU (T1) status [15] |
|---|---|
| Chrome / Edge | 113+ on Windows, macOS, ChromeOS; Android 121+; Linux: Intel Gen12+ from 144, NVIDIA on Wayland from 147, others behind flags |
| Firefox | Windows 141+; macOS on Apple Silicon 145+ (macOS 26), all macOS 147+; Linux and Android Nightly only |
| Safari | 26 on macOS, iOS, iPadOS, visionOS |

caniuse estimates global WebGPU support at 87.35 % [16]. The gap is why T2 and T0 are first-class: every case works
without WebGPU, with replays where compute is missing.

## Assumptions and limits

- Gate figures in the engine table are design estimates; they are measured in the web phase and recorded in the
  manifest.
- The probe reports capability, not speed: a weak integrated GPU passes the T1 probe and still runs the T1 path, with
  per-view budgets (particles, draw calls) chosen for that device class.
- Live engines reproduce the Python references within the stated tolerances; they are not new physics.

## In PitStudio

- Spec `018-web-cases` (engines, tiers, parity) and the browser-parity property of the foundation spec (written in the specification phase).
- [DEC-0006 3D and simulation on static web](../architecture/decisions/DEC-0006-3d-and-simulation-on-static-web.md).
- Status: no engine exists in `web/src/` yet; the tier badge, probe and engines land in the build phase, A1 (DES) and
  C1 (limit equilibrium, inverse velocity) first.

## References

1. W3C, "WebGPU", Candidate Recommendation Draft, 2026-09-15 — default limits. https://www.w3.org/TR/webgpu/
2. MDN, `GPUSupportedLimits` — 128 MiB storage binding, 256 MiB buffer defaults. https://developer.mozilla.org/en-US/docs/Web/API/GPUSupportedLimits
3. three.js, `webgpu_compute_particles` example — 200,000 particles. https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/webgpu_compute_particles.html
4. matsuoka-601, "WebGPU-Ocean" (MIT) — MLS-MPM ~100k particles on integrated, ~300k on discrete GPUs. https://github.com/matsuoka-601/WebGPU-Ocean
5. three.js wiki, "Three.js Shading Language" — WGSL/GLSL node builders; compute on WebGL not stated. https://github.com/mrdoob/three.js/wiki/Three.js-Shading-Language
6. npm registry, `onnxruntime-web` latest — 1.30.0. https://registry.npmjs.org/onnxruntime-web/latest
7. Microsoft, ONNX Runtime releases — 1.30.0, WebGL/JSEP phase-out, WebGPU EP recommended. https://github.com/microsoft/onnxruntime/releases
8. ONNX Runtime, "Using the WebGPU execution provider". https://onnxruntime.ai/docs/tutorials/web/ep-webgpu.html
9. ONNX Runtime, WebGPU operator list. https://github.com/microsoft/onnxruntime/blob/main/js/web/docs/webgpu-operators.md
10. Rapier, "Determinism" (JavaScript user guide). https://rapier.rs/docs/user_guides/javascript/determinism
11. Rapier, "Getting started (JavaScript)" — `-compat` packages inline WASM. https://rapier.rs/docs/user_guides/javascript/getting_started_js/
12. dimforge, `rapier.js` repository — archived 2026-07-12, merged into `dimforge/rapier`. https://github.com/dimforge/rapier.js
13. npm registry, `pyodide` latest — 314.0.7. https://registry.npmjs.org/pyodide/latest
14. MDN, `Math` — precision of many functions is implementation-dependent. https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Math
15. gpuweb, "Implementation Status" wiki. https://github.com/gpuweb/gpuweb/wiki/Implementation-Status
16. caniuse, "WebGPU" — 87.35 % global. https://caniuse.com/webgpu
