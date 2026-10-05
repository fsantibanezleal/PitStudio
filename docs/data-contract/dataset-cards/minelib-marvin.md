# MineLib — marvin instance (optional)

> A benchmark block model from the MineLib library of open-pit mining problems, CC BY-SA 3.0, used optionally to check
> PitStudio's pit-optimisation solvers against published optima. · Part of: [Dataset cards](README.md) · Related:
> [E1 Pit shell and pushbacks](../../cases/e1-pit-shell-pushbacks.md) ·
> [M18 Pit optimisation and scheduling](../../methods/m18-pit-optimisation-scheduling.md) ·
> [oreblocks](../../frameworks/oreblocks.md) · [Maus et al. mining polygons](maus-polygons.md)

## What and why

Case E1 computes an ultimate pit, nested shells and pushbacks with a min-cut solver and a scheduling model
([M18](../../methods/m18-pit-optimisation-scheduling.md)). A solver is only trustworthy if it reproduces known
answers. MineLib (Espinoza, Goycoolea, Moreno, Newman) is the standard library of open-pit mining problem instances,
with published optimal values for several problem types [1][2].

PitStudio's **default** deposits are synthetic: the `oreblocks` package generates seeded block models with stamped
exact optima ([oreblocks](../../frameworks/oreblocks.md), https://pypi.org/project/oreblocks/). MineLib's `marvin`
instance is an **optional** real-format benchmark on top of that, because its licence is share-alike and its hosts
were partly unreachable.

## Datasheet

### Composition

- **Library content:** instances such as `newman1`, `zuck_small` / `zuck_medium` / `zuck_large`, `kd`, `marvin` and
  `mclaughlin`, each as text files [2]:

  | File | Content |
  |---|---|
  | `.blocks` | block list with coordinates and economic attributes |
  | `.prec` | precedence (slope) constraints between blocks |
  | `.upit` | ultimate-pit-limit problem |
  | `.cpit` | constrained pit-limit problem |
  | `.pcpsp` | precedence-constrained production-scheduling problem |
  | solution files | published solutions / optima |

- **For scale:** `kd` uses 20 × 20 × 15 m blocks and publishes UPIT / CPIT / PCPSP optima [2]; `mclaughlin` has
  2,140,342 blocks [3].
- **`marvin`:** its block count, block size and published optima are pinned from its instance page at specification
  (UNVERIFIED here).

### Collection and provenance

- **Authors:** Espinoza, Goycoolea, Moreno, Newman; library paper in *Annals of Operations Research* 206, DOI
  10.1007/s10479-012-1258-3 [1][4].
- **Collection:** instances assembled by the authors (for example `kd`, an Arizona copper deposit, and `mclaughlin`,
  a California gold mine) and published with reference solutions [2][3].
- **Version read:** MineLib v1, home page read on 2026-10-02 [1].
- **Host status on 2026-10-02:** the instance index page returned HTTP 403 and the legacy host had an **expired TLS
  certificate**, so neither could be read; individual instance pages under `minelib.org/v1/` were readable [2][3].
- **Landing page:** https://minelib.org/ [1].

### Licence and attribution

- **Publisher statement:** "Minelib is licensed under a Creative Commons Attribution-ShareAlike 3.0 Unported
  License" [1].
- **SPDX:** `CC-BY-SA-3.0`. **Licence class:** `share-alike`. **Redistribution class:** **`derived-only`** with
  share-alike: raw instances are never re-hosted, and every derived artefact (pit shells, schedules, solver checks)
  is CC BY-SA 3.0.
- **A conflicting note exists.** A third-party package description claims the instances are "granted for academic
  download only and cannot be redistributed", citing no primary source. The publisher's licence governs; the note is
  recorded, and the derived-only rule (no re-hosting) satisfies both readings.
- **Separate manifest entries.** MineLib-derived layers are never merged with CC BY layers.
- **Attribution text**, reproduced verbatim on every derived artefact:
  "Derived from MineLib (Espinoza, Goycoolea, Moreno, Newman), instance marvin, https://minelib.org/. Licensed under
  CC BY-SA 3.0. This derived artefact is licensed under CC BY-SA 3.0."

### Size, checksums and access

- **Size:** small (text files of one instance).
- **Checksum:** none published; the SHA-256 is pinned at first download.
- **Account:** none.
- **Programmatic path:** HTTPS download of the instance files from relative links under `minelib.org/v1/data/` by
  pooch [2]. Because the index page is blocked, the file list is pinned at specification from the instance page.
- **Fallback:** `oreblocks` synthetic deposits, which are the **default** anyway.

## Assumptions and limits

- **Optional.** No E1 KPI depends on MineLib; it adds an external check on the solver.
- **Format conversion.** Block values and precedences are converted to PitStudio's block-model tables; the
  conversion is tested by reproducing the instance's published optimum.
- **Host fragility.** The library's hosting has failed partially before; a pinned SHA-256 makes a later re-download
  verifiable or fail loudly.
- **Economic attributes are the authors'.** They are not re-priced; results on `marvin` are solver checks, not
  economic statements about a real mine.

## In PitStudio

- **Source id:** `minelib-marvin` (optional) in `data/sources.yaml`.
- **Stages:** `s00_download` (optional) → `s10_preprocess` (convert to block tables) → solver check against the
  published optima in `s50_evaluate` → `s60_export` (a separate CC BY-SA shell layer, if published).
- **Cases:** [E1](../../cases/e1-pit-shell-pushbacks.md).
- **Methods:** [M18](../../methods/m18-pit-optimisation-scheduling.md) min-cut ultimate pit, nested shells, MILP
  scheduling.
- **Committed:** derived-only, CC BY-SA 3.0, in separate manifest entries. **Never committed:** the instance files.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. Espinoza, D., Goycoolea, M., Moreno, E., Newman, A. MineLib home page (CC BY-SA 3.0 statement, citation),
   accessed 2026-10-02. https://minelib.org/
2. MineLib. Instance `kd` (block size, files, published optima), accessed 2026-10-02. https://minelib.org/v1/kd.xhtml
3. MineLib. Instance `mclaughlin` (2,140,342 blocks, file links), accessed 2026-10-02.
   https://minelib.org/v1/mclaughlin.xhtml
4. Espinoza, D., Goycoolea, M., Moreno, E., Newman, A. "MineLib: a library of open pit mining problems", *Annals of
   Operations Research* 206, 2013. https://doi.org/10.1007/s10479-012-1258-3
