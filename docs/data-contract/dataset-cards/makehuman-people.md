# MakeHuman people exports

> CC0 human characters exported from the official, unmodified MakeHuman 1.3.0 application, used to put people into
> synthetic pit scenes without third-party asset terms. · Part of: [Dataset cards](README.md) · Related:
> [B2 Synthetic perception](../../cases/b2-synthetic-perception.md) ·
> [DEC-0015 People assets from MakeHuman](../../architecture/decisions/DEC-0015-people-assets-makehuman.md) ·
> [Synthetic data](synthetic-data.md) · [M22 Cosmos VLM tasks](../../methods/m22-cosmos-vlm-tasks.md)

## What and why

Proximity and perception cases need **people** in the scene: a worker near a haul road (B1), the person class of the
synthetic detector (B2), and hazard questions about people for the vision-language model (M22), whose answers are
computed from the scene's USD prims.
The character assets bundled with the simulator are not redistributable, and dropping the people class would weaken
B1, B2 and the hazard questions.

MakeHuman is an open-source human-character generator. Its licence keeps the application and its data under AGPL,
but offers a **CC0 option for exported characters** when the export is made in a specific way (§C below) [1]. Renders
of those exports can then carry PitStudio's own CC BY 4.0 licence.

## Datasheet

### Composition

- **What is produced:** human character models exported by MakeHuman's file-export function (mesh, skeleton and
  textures as the export format provides), using **bundled system assets only**.
- **Variation:** body shape, proportions, pose and clothing chosen from the bundled assets; the parameter ranges and
  the export format are fixed at specification and recorded per export (seed, settings, application version).
- **Not used:** community-contributed clothes, skins or other assets — they carry their own licences.
- **Count:** a small library of exported characters, enough for the SDG scenes; the number is fixed at
  specification.

### Collection and provenance

- **Tool:** MakeHuman **1.3.0**, released 2024-05-15 [2]. It is a **stale** release (no newer release since), noted
  as such.
- **Build:** the official Windows zip from `files.makehumancommunity.org` (about 325 MB), **official and
  unmodified**; its SHA-256 was pinned at download [3].
- **Process:** characters are composed in the application and written with its file-export function; no export goes
  through a modified build or a third-party exporter.
- **Version record:** every export records the application version, the zip's SHA-256 and the export settings.

### Licence and attribution

The licence page states (fetched 2026-10-04, HTTP 200; SHA-256 of the page
`b4a7c61430ac61459abc21c72a36592861e525f134304aa25e7602c10006a1ce`) [1]:

- **§A:** the MakeHuman source and data are released under AGPL "with the exception described in section C".
- **§C:** "the option to use CC0 1.0 Universal … for the MakeHuman characters exported under the conditions that
  a) The assets were bundled in an export that was made using the file export functionality inside an OFFICIAL and
  UNMODIFIED version of MakeHuman and/or b) the asset solely consists of a 2D binary image in PNG, BMP or JPG format".

How PitStudio meets condition (a):

| Condition | PitStudio practice |
|---|---|
| Export made with the file-export function | yes — only the built-in file export is used |
| Official version | yes — the official 1.3.0 Windows zip, SHA-256 pinned |
| Unmodified version | yes — no source changes or added plugins; the pinned hash identifies the build |
| Assets covered | bundled system assets only; community assets excluded |

- **SPDX of the exports:** `CC0-1.0` (licence §C). **Licence class:** `open-no-attribution`. The application itself
  is AGPL and is used as an external tool only, never vendored or redistributed.
- **Redistribution class:** `redistributable` (CC0), but PitStudio **keeps raw exports local** and commits only its
  own renders.
- **Our renders** of the exports are licensed **CC-BY-4.0** (licence class `own`).
- **Attribution text:** none required for CC0 exports. PitStudio credits the tool on renders and data cards:
  "People: characters exported from MakeHuman 1.3.0 (official build) under the CC0 option of its licence §C."
- **Bootstrap status:** the zip was pinned and extracted, and §C was re-read on 2026-10-04 and found unchanged. The
  export smoke test has **not run yet**: it opens an OpenGL window and waits for the GPU hold to be lifted.

### Size, checksums and access

- **Size:** the application zip is about 325 MB [3]; each export is small (per asset).
- **Checksum:** the zip's SHA-256 was pinned at download; every export is hashed when written.
- **Account:** none.
- **Programmatic path:** none for the exports themselves: they are produced locally by the application. The zip is
  installed per user as a portable tool.
- **Fallback:** **procedural mannequins** (simple articulated human shapes built in PitStudio's own code). If the
  MakeHuman route fails (conditions not met, export smoke fails), B2 uses mannequins and its case page says so.

## Assumptions and limits

- **Licence page reachability.** The licence page could not be fetched again when this card was written; the quote
  above is the 2026-10-04 reading, and it is re-checked before any render is published.
- **Stale tool.** MakeHuman 1.3.0 is the latest release but over a year old; behaviour on current GPUs and drivers is
  checked by the export smoke.
- **Synthetic people are not real people.** Detection of people trained on these renders is **not validated against
  real images**: the people class is labelled "calibrated synthetic — not validated against real data" unless the
  optional real probe is labelled ([Synthetic data](synthetic-data.md)).
- **Limited diversity.** Bundled assets cover a limited range of clothing (no mining PPE is assumed); the ranges used
  are stated, and no claim is made about demographic coverage.

## In PitStudio

- **Source id:** `makehuman-exports` in `data/sources.yaml`.
- **Stages:** local export (maintainer machine) → `st30_assets` (rig and convert to USD, attach semantic labels) →
  `st40_compose` → `st55_sdg` (Replicator) and `st53_sensors` (ovrtx) → `st59a_vqa` (hazard questions).
- **Cases:** [B2](../../cases/b2-synthetic-perception.md) (person class), [B1](../../cases/b1-traffic-proximity.md)
  (people near traffic), Cosmos hazard questions in [M22](../../methods/m22-cosmos-vlm-tasks.md).
- **Models:** [D-FINE](../../models/d-fine.md), [RF-DETR-Seg](../../models/rf-detr-seg.md) (person class).
- **Committed:** our CC-BY renders only. **Never committed:** raw exports, the application zip.
- **Status:** **Not yet exported** — the application is pinned and extracted; exports are produced in the
  data-and-models phase after the export smoke passes. Nothing is fetched by `s00_download` for this source.

## References

1. MakeHuman Community. "License" (§A AGPL; §C "MakeHuman output GPL exception": CC0 option for exported
   characters), accessed 2026-10-04. http://www.makehumancommunity.org/content/license.html
2. MakeHuman Community. Releases (v1.3.0, 2024-05-15), accessed 2026-10-04.
   https://github.com/makehumancommunity/makehuman/releases
3. MakeHuman Community. Official Windows zip of MakeHuman 1.3.0 (about 325 MB).
   https://files.makehumancommunity.org/releases/makehuman-community-1.3.0-windows.zip
