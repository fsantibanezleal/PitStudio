# DEC-0006: 3D scenes and simulation on a static web app

> USD stays in the studio; one scene specification emits both USD and glTF; the site delivers glTF, 3D Tiles,
> quantized replay shards, AV1 + H.264 video and splats, renders with three.js/R3F using WebGPU per route with a WebGL 2
> fallback, runs live engines in workers, and defines parity per system class. · Part of: [decisions](README.md) ·
> Related: [lanes](../lanes.md) · [three.js, R3F and 3D Tiles](../../frameworks/threejs-r3f-3d-tiles.md) ·
> [compute tiers](../../web/compute-tiers.md) · [budgets](../../web/budgets.md)

**Status:** Accepted, 2026-10-04

## Context

The site must show real 3D scenes (lidar terrain, designed pits, fleets), replay GPU simulations and run lighter
simulations live, all from free static hosting with a 2 MB first view. The constraints:

- **USD is not browser-deliverable today.** The USD-WASM viewer that exists needs cross-origin isolation headers that
  GitHub Pages does not send and carries a non-commercial licence [1]; three.js's `USDLoader` reads USD, USDA, USDC and
  USDZ but is not a full composition engine for sublayers and instancers [2].
- **Raw replays are heavy.** 10⁵ particles × 3 coordinates × 2 bytes (int16) is 0.6 MB per frame, so 20 s at 10 frames
  per second is 120 MB (derived).
- **WebGPU is not available everywhere** [3]; three.js's WebGPURenderer falls back to WebGL 2 automatically [4].
- **Floating point differs between browsers** for transcendental functions, so bit-exact parity is impossible for
  chaotic systems [5].
- **ORT-web's WebGPU kernels have gaps:** `GridSample` is registered only for opset 16–19, and NMS, RoiAlign and NonZero
  have no WebGPU kernel [6].
- Library versions read in October 2026: three r186, React Three Fiber 9.8.1 (peer React < 19.4) [7], 3DTilesRendererJS
  [8], Rapier 0.21, Spark for splats [9], ORT-web 1.30.

## Decision

1. **USD stays in the studio.** A scene specification (procedural recipe + data ids) emits USD for the studio and glTF
   for the web from the same code; converters are not on the critical path. `USDLoader` may open one small `.usdz` as a
   "same asset" proof panel only.
2. **Delivery formats.**

   | Content | Format |
   |---|---|
   | Terrain | 3D Tiles 1.1 with glTF tiles, skirts against cracks |
   | Equipment, design surfaces | glTF 2.0 with meshopt compression, mesh quantization, KTX2 textures and GPU instancing; equipment cycles as glTF animations |
   | Fleet and particle replays | int16-quantized poses and positions in a bounding box, time-window shards ≤ 10 MB, plus a JSON manifest (schema, units, fps, SHA-256) |
   | Fields | 16-bit PNG or Float32 tiles |
   | KPIs | Parquet |
   | RTX renders and replays | AV1 1080p (primary) + H.264 720p (fallback) MP4 with a WebP poster; the pair ≤ 25 MB; bitrate chosen by measured VMAF ([DEC-0011](DEC-0011-nvenc-ffmpeg-8-1.md)); `MediaCapabilities` picks AV1 only where decoding is power-efficient |
   | Splats | SPZ ≤ 25 MB per scene |

   Every file is content-hashed and listed in the manifest with its lane and licence class.
3. **Budgets.** Initial JavaScript ≤ 200 KB gzip; first view ≤ 2 MB (an LOD-0 terrain tile set plus the UI); heavier 3D
   loads only after a user action, with progress and abort; whole site ≤ 500 MB as an exact sum
   ([budgets](../../web/budgets.md)); the studio showcase references case assets by manifest id instead of duplicating
   them; CI fails on any overrun.
4. **Rendering.** three.js + R3F 9. Routes that benefit use WebGPURenderer through R3F's async `gl` factory with TSL
   materials, falling back to WebGL 2 automatically; `?renderer=webgl` forces the fallback for end-to-end tests. Splat
   routes use WebGLRenderer + Spark in their own canvas; two renderers never share a canvas. One shared `SimClock`
   (paused by default, step and scrub) drives 3D, charts, maps and video; no autoplay; reduced motion is respected.
5. **Live compute and parity by system class.** Discrete-event and analytical engines in TypeScript with a seeded
   counter-based PRNG, explicit tie-breaks and no `Math.*` transcendental calls in variate generation: parity = exact event
   trace. Rapier: parity = snapshot hash against Node goldens of the same version. Chaotic and particle systems in WGSL:
   per-kernel unit parity plus observables (repose ±1.5°, run-out and discharge ±5 %, mass drift < 0.5 %). ONNX models:
   numerical tolerances. Tiers T1 WebGPU, T2 WASM and T0 baked are always present.
6. **ONNX opset.** The default stays opset 20. A model may export at opset 17–19 when a WebGPU kernel it needs is
   registered only there; the reason is recorded in the manifest and parity is checked against the opset-20 export.
   Graphs avoid operators without WebGPU kernels, or run on the WASM provider with the fallback on a CI allow-list.
7. **Local tiers never in the Pages build.** The console ([DEC-0003](DEC-0003-loopback-console.md)) and the optional Kit
   WebRTC studio link are excluded from the Pages artifact and labelled "requires an RTX workstation".
8. **Honesty of the showcase.** Every artefact card carries LIVE, REPLAY or STATIC; a tool with no published artefact
   shows "not yet run"; performance numbers follow [DEC-0005](DEC-0005-performance-data-licence-rule.md).

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| A USD-WASM viewer in the browser | Same file as the studio | Needs cross-origin isolation headers (not on Pages); non-commercial licence; no imaging [1] | Hosting and licence |
| Raw particle replays at full resolution | Faithful | About 120 MB per 20 s (derived above) | Replaced by live WGSL kernels plus baked aggregates |
| WebGPU-only rendering | Fastest path | Not available in every browser [3] | WebGL 2 fallback is mandatory |
| Bit-exact parity for every engine | Strongest claim | Impossible with float atomics and chaotic dynamics | Parity by system class |
| Kit streaming on the public site | Full RTX in the browser | Needs a GPU host, signalling, cost; Chromium-only | Localhost studio link only |
| Babylon.js | WebGPU and a physics engine built in | Breaks continuity with the React/R3F shell | Not adopted |

## Consequences

**Positive.** Real scenes, replays and live simulations on free static hosting, each with a stated parity contract and
budgets; the site works without WebGPU.

**Negative, accepted.** A bake step per scene and two delivery formats from one specification; WGSL twins of selected
kernels to maintain; more manifest fields.

**Watch.** R3F v10 (WebGPU and TSL first-class) and its React cap; Spark on WebGPU; ORT-web WebGPU kernel coverage;
GitHub Pages compression and range-request behaviour (an open measurement); WebGPU in Firefox.

## References

1. Needle usd-viewer (PolyForm Noncommercial; requires SharedArrayBuffer and COOP/COEP). https://github.com/needle-tools/usd-viewer
2. three.js documentation: USDLoader. https://threejs.org/docs/pages/USDLoader.html
3. Can I use: WebGPU. https://caniuse.com/webgpu
4. three.js documentation: WebGPURenderer (automatic WebGL 2 fallback). https://threejs.org/docs/pages/WebGPURenderer.html
5. Rapier. JavaScript determinism guide. https://rapier.rs/docs/user_guides/javascript/determinism
6. ONNX Runtime Web. WebGPU operator list. https://github.com/microsoft/onnxruntime/blob/main/js/web/docs/webgpu-operators.md
7. npm: @react-three/fiber (9.8.1). https://registry.npmjs.org/@react-three/fiber/latest
8. 3DTilesRendererJS repository. https://github.com/NASA-AMMOS/3DTilesRendererJS
9. Spark, Gaussian-splat renderer for three.js. https://github.com/sparkjsdev/spark
