# Rapier, WebGPU and Pyodide

> The live engines of the web app: Rapier for deterministic rigid bodies, WebGPU compute for granular and field
> kernels, and Pyodide to run the `minephys` reference models in the browser on demand. · Part of:
> [Frameworks](README.md) · Related: [three.js / R3F / 3D Tiles](threejs-r3f-3d-tiles.md) · [ONNX Runtime](onnx-runtime.md) ·
> [Compute tiers](../web/compute-tiers.md) · [Compute lanes](../pipelines/compute-lanes.md)

## What and why

The site's lane rule: an element is **LIVE** only if it is web-drivable, its asset is ≤ 25 MB, an interaction takes
≤ 16 ms or a run ≤ 1 s on tier T2, and its trace is ≤ 10 MB; otherwise it is **REPLAY** of baked studio work
([Compute lanes](../pipelines/compute-lanes.md)). These three tools make the live lane real:

- **Rapier** is a Rust rigid-body engine compiled to WebAssembly. Its JS/WASM build is **cross-platform deterministic**
  for the same version and identical initial conditions, verifiable by a snapshot hash [1]. That makes exact parity
  tests possible. It runs the B1 traffic workbench (rigid trucks and light vehicles).
- **WebGPU** gives the browser compute shaders (WGSL). PitStudio writes small WGSL twins of its Warp kernels: granular
  MPM/DEM, shallow water and dust particles, with the Warp version as the reference. A published WebGPU MLS-MPM runs
  about 100,000 particles on integrated graphics and about 300,000 on stronger GPUs [2].
- **Pyodide** is CPython compiled to WebAssembly. A "verify with the reference engine" button loads the `minephys` wheel
  and evaluates the same Python models that the docs cite ([minephys](minephys.md)).

Rejected: Jolt's multithreaded build (needs SharedArrayBuffer and cross-origin isolation) [3]; ammo.js (Bullet 2.82,
legacy) [4]; Havok (Babylon-centric) [5]; raw replay of 10⁵-particle frames (10⁵ particles × 3 axes × 2 bytes ×
10 frames/s × 20 s ≈ 120 MB per clip, so live re-simulation from a baked initial state replaces it).

## Identity

None of these is in `web/pnpm-lock.yaml` yet; the web phase adds them at these planned versions.

| Tool | Planned version | Licence · class | Ring | Notes |
|---|---|---|---|---|
| Rapier (`@dimforge/rapier3d-simd-compat`) | 0.21.0 [6] | Apache-2.0 · open | Adopt | the `rapier.js` repo was archived on 2026-07-12 and merged into the `dimforge/rapier` monorepo [7] |
| WebGPU | W3C Candidate Recommendation Draft, 2026-09-15 [8] | open standard | Trial (tier T1) | not Baseline: see limits |
| Pyodide | 314.0.7 (Python 3.14) [9] | MPL-2.0 · open | Adopt | module workers only |

## How PitStudio uses it

| Engine | Workbench | Parity with the Python side |
|---|---|---|
| Rapier in a worker | B1 traffic and proximity: ≤ 40 vehicles at 60 Hz | snapshot hash against golden trajectories from the same Rapier version |
| WGSL compute | A3 granular (≤ 2 × 10⁴ particles live), C2 shallow water, C3 dust | per-kernel checks on a fixed configuration, plus statistical observables (repose ±1.5°, run-out ±5 %, mass drift) — granular flow is chaotic, so trajectories are never compared |
| Pyodide + `minephys` | every analytical model (haulage, blasting, slope, dust, comminution) | the same code as the studio; exact |

Tiers are always shown: **T1** WebGPU, **T2** WASM, **T0** baked results ([Compute tiers](../web/compute-tiers.md)).
Measured runtime sizes from the web budget work: Rapier 0.21.0 is 3.42 MB; the Pyodide load set
(`pyodide.asm.wasm`, glue, stdlib zip, lock file) is 13.54 MB; numpy, PyYAML and `minephys` wheels add about 3 MB.
They load only on user action ([Budgets](../web/budgets.md)).

## Licence and redistribution

Rapier (Apache-2.0) and Pyodide (MPL-2.0) are shipped unmodified inside the Pages artefact; MPL-2.0 is file-level
copyleft and applies only to modified Pyodide files, which PitStudio does not have. WGSL kernels are ours (Apache-2.0).

## Assumptions and limits

- **WebGPU reach:** Chrome and Edge 113+, Safari 26, Firefox on Windows from 141 and on Apple-Silicon macOS from 145;
  Firefox on Linux and Android is behind a flag; caniuse reports about 87 % global support [10][11]. Every live
  element has a T2 or T0 fallback.
- **WGSL has no float atomics**, only 32-bit integer ones, so scatter steps use fixed-point accumulation [2]; parity is
  statistical.
- Default WebGPU limits: 128 MiB per storage-buffer binding and 256 MiB per buffer [12].
- **`Math.*` precision is implementation-dependent** across browsers [13]; DES variates avoid transcendental functions
  and use a counter-based PRNG shared with Python.

## In PitStudio

- Status: **not yet run.** No live engine is in the web build yet.
- Pages: [Rapier and traffic](../methods/m20-traffic-ttc.md), [GPU granular physics](../methods/m07-gpu-granular-physics.md),
  [minephys](minephys.md).

## References

1. Dimforge. *Rapier JS determinism*. https://rapier.rs/docs/user_guides/javascript/determinism
2. matsuoka-601. *WebGPU-Ocean* (MLS-MPM and SPH on WebGPU). https://github.com/matsuoka-601/WebGPU-Ocean
3. J. Rouwé. *JoltPhysics.js*. https://github.com/jrouwe/JoltPhysics.js
4. kripken. *ammo.js*. https://github.com/kripken/ammo.js
5. npm. *@babylonjs/havok*. https://registry.npmjs.org/@babylonjs/havok/latest
6. npm. *@dimforge/rapier3d-simd-compat* 0.21.0. https://registry.npmjs.org/@dimforge/rapier3d-simd-compat/latest
7. Dimforge. *rapier.js (archived)*. https://github.com/dimforge/rapier.js
8. W3C. *WebGPU*. https://www.w3.org/TR/webgpu/
9. npm. *pyodide* 314.0.7. https://registry.npmjs.org/pyodide/latest
10. gpuweb. *WebGPU implementation status*. https://github.com/gpuweb/gpuweb/wiki/Implementation-Status
11. caniuse. *WebGPU*. https://caniuse.com/webgpu
12. MDN. *GPUSupportedLimits*. https://developer.mozilla.org/en-US/docs/Web/API/GPUSupportedLimits
13. MDN. *Math*. https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Math
