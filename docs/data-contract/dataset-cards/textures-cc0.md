# Poly Haven and ambientCG — CC0 textures and HDRIs

> CC0 rock, gravel and ground materials and sky HDRIs for studio scenes, synthetic images and web meshes, chosen so
> that every published render is free of third-party asset terms. · Part of: [Dataset cards](README.md) · Related:
> [Synthetic data](synthetic-data.md) · [McKinley Mine lidar](mckinley-lidar.md) ·
> [Isaac Sim and Replicator](../../frameworks/isaac-sim-replicator.md) ·
> [DEC-0004 Proprietary SDKs, reference only](../../architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md)

## What and why

Every image PitStudio publishes — studio renders, synthetic training images, web scene meshes — carries the licence
of every asset visible in it. The simulator's bundled 3D models and textures are under a licence that forbids
distributing "any portion of the Software" [3], so they are never used. PitStudio instead textures its own
procedural meshes with **CC0** materials:

- **Poly Haven** offers HDRIs, textures and models under CC0: they may be redistributed "even in a product you sell",
  with no attribution needed [1].
- **ambientCG** offers PBR materials (including rock, gravel and ground) under CC0 1.0, attribution optional [2].

CC0 removes every condition from the inputs, so the outputs can carry PitStudio's own CC BY 4.0 licence.

## Datasheet

### Composition

| Library | Asset types used | Typical use in PitStudio |
|---|---|---|
| Poly Haven | PBR textures (rock, gravel, ground), sky HDRIs | bench faces, haul-road surfaces, lighting of studio scenes and synthetic images |
| ambientCG | PBR materials (rock, gravel, ground) | the same, as a second source and for structured randomisation of rock appearance |

- **Per asset:** colour, normal, roughness and displacement maps (as the asset provides) at a chosen resolution; HDRIs
  as high-dynamic-range images.
- **Selection:** a short, fixed list of asset ids is recorded in `data/sources.yaml` at specification; each entry
  names the asset page, the file and its resolution.

### Collection and provenance

- **Publishers:** Poly Haven (https://polyhaven.com) and ambientCG (https://ambientcg.com) [1][2].
- **Collection:** surfaces and skies captured and processed by the libraries into tiling maps and HDRIs; the capture
  method varies per asset and is described on each asset page.
- **Version read:** licence pages read on 2026-10-02 [1][2]; assets are rolling, so the asset page and download date
  are recorded per file.

### Licence and attribution

- **SPDX:** `CC0-1.0`. **Licence class:** `open-no-attribution`. **Redistribution class:** `redistributable`.
- **Not everything on the sites is CC0.** Poly Haven's own site logos, renders and text are not CC0 [4]; PitStudio
  uses the asset files only, never site graphics.
- **Attribution text:** none required [1][2]. PitStudio adds a courtesy credit in the asset manifest and the site
  footer: "Textures and HDRIs: Poly Haven and ambientCG, CC0."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** per asset, depending on the chosen resolution; only resized, compressed derivatives reach the web.
- **Checksum:** per file; none published was relied on, so the SHA-256 is pinned at first download.
- **Account:** none.
- **Programmatic path:** HTTPS download of the listed asset files by `s00_download` (pooch).
- **Fallback:** none needed; if one asset disappears, another CC0 asset of the same type replaces it and the change is
  recorded.

## Assumptions and limits

- **Photographed surfaces are generic.** A CC0 rock texture is not the rock of Bingham or Hambach; scene appearance
  is plausible, not site-true. Site-true texture comes only from the [McKinley orthophoto](mckinley-lidar.md), when
  available.
- **No mining equipment.** These libraries provide textures, skies and props, not haul trucks or shovels; equipment
  is procedurally modelled in PitStudio's own code.
- **Appearance feeds the sim-to-real gap.** Texture choice affects synthetic images; the structured-randomisation
  design and the unstructured ablation arm ([Synthetic data](synthetic-data.md)) measure how much it matters.

## In PitStudio

- **Source ids:** `polyhaven`, `ambientcg` in `data/sources.yaml`.
- **Stages:** `s00_download` → `st30_assets` (materials on procedural meshes) → `st40_compose` → studio renders and
  SDG (`st52_rtx_render`, `st53_sensors`, `st55_sdg`) → `s60_export` (compressed textures for glTF and 3D Tiles).
- **Cases:** every case with a 3D scene; especially [B2](../../cases/b2-synthetic-perception.md) (synthetic images)
  and [D1](../../cases/d1-blast-muck-pile.md) (muck-pile renders).
- **Methods:** [M10](../../methods/m10-synthetic-data-detector.md), [M11](../../methods/m11-fragmentation-segmentation.md),
  [M23](../../methods/m23-rtx-sensor-simulation.md).
- **Committed:** textures (resized, compressed derivatives within the web budgets). **Never committed:** NVIDIA or
  Isaac Sim bundled assets of any kind.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. Poly Haven. "License" (CC0; redistribution allowed, no attribution required), accessed 2026-10-02.
   https://polyhaven.com/license
2. ambientCG. "License" (CC0 1.0, attribution optional), accessed 2026-10-02. https://docs.ambientcg.com/license/
3. NVIDIA. "NVIDIA Isaac Sim Additional Software and Materials License" (no distribution of any portion of the
   Software), accessed 2026-10-02.
   https://docs.isaacsim.omniverse.nvidia.com/6.0.0/common/license-isaac-sim-additional.html
4. Poly Haven. "License" — note that site logos, renders and text are not CC0, accessed 2026-10-02.
   https://polyhaven.com/license
