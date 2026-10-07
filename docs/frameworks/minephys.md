# minephys

> The companion package that holds PitStudio's knowledge base as code: sourced mining-engineering models and cited
> parameter tables, pure numpy, the same code in the studio, the pipeline, Kit and the browser. · Part of:
> [Frameworks](README.md) · Related: [Knowledge](../knowledge/README.md) ·
> [DEC-0017](../architecture/decisions/DEC-0017-companion-package-minephys.md) ·
> [Rapier / WebGPU / Pyodide](rapier-webgpu-pyodide.md) · [Theory](../theory/README.md)

## What and why

`minephys` is a separate public repository and Python package of "sourced, tested reference implementations of
mining-engineering models with cited parameter tables" [1]. Every equation cites its primary source and every
parameter-table row carries its value or range, units, citation with page, verification status and the code symbol
that uses it.

Why a separate package ([DEC-0017](../architecture/decisions/DEC-0017-companion-package-minephys.md)):

- **One implementation, four places.** The studio, the pipeline, the browser (through Pyodide) and Kit's own Python
  all import the same functions, so a slope factor of safety computed in a notebook equals the one shown on the web.
- **A purity boundary.** numpy and PyYAML only, no GPU and no heavy dependencies, so it runs in Pyodide and inside Kit.
- **Second consumers.** The maintainer's other public mining projects can use it without pulling in the studio.

Rejected: keeping the tables only inside the product repo (no reuse, no browser path) and a separate docs site only
(no executable knowledge).

## Identity

| Item | Value |
|---|---|
| Package | `minephys` 0.0.0, git dependency at commit `143e709` (the scaffold), pinned in the root, `studio/` and `pipeline/` locks |
| Requires | Python ≥ 3.12; numpy ≥ 2.0, PyYAML ≥ 6.0 [1] |
| Tested on | Python 3.12–3.14, Pyodide, and inside Kit (installed to a git-ignored target folder) |
| Licence | Apache-2.0 (code); knowledge tables cite their sources · open |
| Ring | Adopt (maintainer's own package) |
| Release | a git-tag dependency until the first release; then TestPyPI → PyPI by trusted publishing |

## How PitStudio uses it

| Module | Contents | Cases |
|---|---|---|
| `haulage` | rimpull and retarder, rolling and grade resistance, cycle time, energy, CO₂, trolley and battery trucks, match factor, M/M/c, mean-value analysis | A1, A2 |
| `blasting` | Kuz-Ram, KCO, Swebrec, peak particle velocity, flyrock | D1 |
| `geotech` | Hoek–Brown, limit-equilibrium methods, inverse velocity, Bayesian time to failure, a ground-based slope-radar line-of-sight model | C1 |
| `bulk` | Beverloo, angle of repose, CEMA, Gy | A3 |
| `comminution` | Bond, Morrell, population balance, Klimpel | D2 |
| `environment` | AP-42 haul-road emission, Gaussian plume, Beer–Lambert dust attenuation for lidar | C3, B1 |
| `planning` | Lane's cut-off, small min-cut | E1 |
| `knowledge` | cited tables (YAML) + `references.bib` + loader | all |

The `docs/knowledge/` section is **generated** from these tables: parameters, equations, bibliography and an EN/ES
glossary ([Knowledge](../knowledge/README.md)). The web UI flags rows whose status is UNVERIFIED.

## Licence and redistribution

Apache-2.0 code. The wheel is shipped in the Pages artefact for the Pyodide button.

## Assumptions and limits

- Each model is valid only inside its stated range; slope, tailings and blasting outputs are educational, not design or
  regulatory results.
- A constant still marked UNVERIFIED against its primary text stays out of headline tables until it is pinned.

## In PitStudio

- Status: **scaffold only** at commit `143e709`; the models are written test-first, each against worked examples from
  its primary source.
- Repository: https://github.com/fsantibanezleal/minephys

## References

1. F. A. Santibanez-Leal. *minephys* repository. https://github.com/fsantibanezleal/minephys
