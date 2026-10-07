# three.js, React Three Fiber and 3D Tiles

> The browser's 3D stack: three.js renders the pit, React Three Fiber binds it to the React shell, and the 3D Tiles
> renderer streams the real terrain in levels of detail. · Part of: [Frameworks](README.md) · Related:
> [OpenUSD](openusd.md) · [Rapier / WebGPU / Pyodide](rapier-webgpu-pyodide.md) · [Web structure](../web/structure.md) ·
> [DEC-0006](../architecture/decisions/DEC-0006-3d-and-simulation-on-static-web.md)

## What and why

- **three.js** is the WebGL/WebGPU 3D library. Its `WebGPURenderer` picks WebGPU when available and **falls back to a
  WebGL 2 backend automatically**, and materials written in TSL (three.js shading language) compile to both [1][2].
- **React Three Fiber (R3F)** renders three.js scenes as React components; v9 accepts an async renderer factory, so a
  route can opt into `WebGPURenderer` [3][4].
- **3DTilesRendererJS** (`3d-tiles-renderer`) streams 3D Tiles 1.1 tilesets with glTF tile content, an LRU cache with
  byte caps and R3F components [5][6].

PitStudio's web app is a static GitHub Pages site. Isaac Sim and Kit cannot run in a browser, so the site **replays**
baked studio artefacts and **runs** light engines live. USD stays in the studio; the web receives glTF and 3D Tiles
generated from the same scene specification ([OpenUSD](openusd.md)).

Rejected ([DEC-0006](../architecture/decisions/DEC-0006-3d-and-simulation-on-static-web.md)):

| Alternative | Why not |
|---|---|
| USD-WASM viewers | the known viewer is non-commercial and needs COOP/COEP headers that Pages cannot send [7] |
| Babylon.js | strong engine (WebGPU, Havok), but would replace R3F and break the shared React shell [8] |
| Kit streaming on the public site | needs a GPU host and signalling; local-only "studio link" at most [9] |
| CesiumJS | a globe engine with its own renderer; not needed for a local-grid pit [10] |
| three.js `USDLoader` as the scene path | no sublayers, `PointInstancer` or physics; kept for a single-asset "same USD" panel [11] |

## Identity

None of these libraries is in `web/pnpm-lock.yaml` yet: the web lock today holds the shell (React 19.3.0, React Router
8.4.0, Vite 8.3.2). The web phase adds them at these planned versions:

| Library | Planned version | Licence · class | Ring |
|---|---|---|---|
| `three` | 0.186.1 (r186) [12] | MIT · open | Adopt |
| `@react-three/fiber` | 9.8.1, peer `react >=19 <19.4` [13] | MIT · open | Adopt |
| `@react-three/drei` | 10.7.9 [14] | MIT · open | Adopt |
| `3d-tiles-renderer` | 0.5.3 [5] | Apache-2.0 · open | Trial |
| `@gltf-transform/cli` (bake time) | 4.5.1 [15] | MIT · open | Adopt |

## How PitStudio uses it

- **Explore route (`/`)**: the Bingham pit as 3D Tiles 1.1 with glTF (meshopt) tiles, first view ≤ 2 MB (LOD-0), the
  case rail and a shared timeline that is paused by default ([Budgets](../web/budgets.md)).
- **Per-case Scene tab**: design layers, fleet replays as node animation, field shards, sensor clouds.
- **Bake path** (`s60_export`): our glTF writer → `gltf-transform` (meshopt compression, which also compresses
  animation and instance data; WebP textures; `EXT_mesh_gpu_instancing`) → tilesets ≤ 10 MB per file [15][16][17].
- **Renderer per route**: `WebGPURenderer` with TSL where GPU compute matters, WebGL 2 elsewhere; never two renderers in
  one canvas. drei helpers that are WebGL-only stay on WebGL routes.
- Budgets: tiles + glb ≤ 95 MB of the 500 MB site; initial JavaScript ≤ 200 KB gzip; three.js and R3F load lazily per
  route.

## Licence and redistribution

MIT and Apache-2.0: shipped in the Pages artefact. Terrain derivatives carry their data source's terms (Bingham 3DEP is
public domain); glTF of our procedural equipment is CC-BY-4.0.

## Assumptions and limits

- R3F 9 caps React below 19.4; a React upgrade waits for R3F [13]. R3F v10 and drei v11 (first-class WebGPU) are
  alpha and not adopted [3].
- Whether TSL `compute()` runs on the WebGL 2 fallback is **UNVERIFIED**; GPU compute is treated as a WebGPU-only (T1)
  capability, and T2 uses WASM [2].
- WebGPU is not available everywhere (see [Rapier / WebGPU / Pyodide](rapier-webgpu-pyodide.md)); WebGL 2 is the
  mandatory fallback for 3D.
- `KHR_meshopt_compression` is a release candidate; the bake uses the ratified `EXT_meshopt_compression` [18].

## In PitStudio

- Status: **not yet run.** The shell is built and deployed; no 3D route exists yet.
- Pages: [Compute tiers](../web/compute-tiers.md), [Showcase rules](../web/showcase-rules.md),
  [DEC-0007](../architecture/decisions/DEC-0007-large-assets-as-release-assets.md) for assets over 10 MB.

## References

1. three.js. *WebGPURenderer*. https://threejs.org/docs/pages/WebGPURenderer.html
2. three.js. *Three.js Shading Language (wiki)*. https://github.com/mrdoob/three.js/wiki/Three.js-Shading-Language
3. pmndrs. *react-three-fiber releases*. https://github.com/pmndrs/react-three-fiber/releases
4. pmndrs. *R3F v9 migration guide*. https://r3f.docs.pmnd.rs/tutorials/v9-migration-guide
5. npm. *3d-tiles-renderer* 0.5.3. https://registry.npmjs.org/3d-tiles-renderer/latest
6. NASA-AMMOS. *3DTilesRendererJS*. https://github.com/NASA-AMMOS/3DTilesRendererJS
7. Needle Tools. *usd-viewer*. https://github.com/needle-tools/usd-viewer
8. Microsoft (2026-03-26). *Announcing Babylon.js 9.0*. https://blogs.windows.com/windowsdeveloper/2026/03/26/announcing-babylon-js-9-0/
9. NVIDIA. *web-viewer-sample*. https://github.com/NVIDIA-Omniverse/web-viewer-sample
10. npm. *cesium*. https://registry.npmjs.org/cesium/latest
11. three.js. *USDComposer.js source*. https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/jsm/loaders/usd/USDComposer.js
12. npm. *three* 0.186.1. https://registry.npmjs.org/three/latest
13. npm. *@react-three/fiber* 9.8.1. https://registry.npmjs.org/@react-three/fiber/latest
14. npm. *@react-three/drei* 10.7.9. https://registry.npmjs.org/@react-three/drei/latest
15. npm. *@gltf-transform/cli* 4.5.1. https://registry.npmjs.org/@gltf-transform/cli/latest
16. Khronos Group. *EXT_meshopt_compression*. https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Vendor/EXT_meshopt_compression/README.md
17. Khronos Group. *EXT_mesh_gpu_instancing*. https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Vendor/EXT_mesh_gpu_instancing/README.md
18. Khronos Group. *KHR_meshopt_compression*. https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos/KHR_meshopt_compression
