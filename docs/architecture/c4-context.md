# C4 level 1: system context

> PitStudio as one software system: the two kinds of person who use it, the five external systems it depends on, what
> crosses each boundary, and what is deliberately outside the context. · Part of: [architecture](README.md) · Related:
> [C4 containers](c4-containers.md) · [deployment](deployment.md) ·
> [sources and licences](../data-contract/sources-and-licences.md) · [owner acts and licences](../studio/owner-acts-and-licences.md)

## What and why

The C4 model describes software at four zoom levels [5]. Level 1, the system context, answers who uses the system and which
other systems it relies on, without any internal detail. For PitStudio the context view matters because two very
different worlds meet in it: a public static website that anyone can open, and a local GPU studio that only the
maintainer runs and that drives proprietary NVIDIA software. The boundaries between them are where most of the licence,
security and honesty rules apply.

## The diagram

![C4 system context of PitStudio](../assets/diagrams/c4-context.svg)

*PitStudio in the middle; the visitor reaches it through the static site, the maintainer through the local studio; it
depends on GitHub, open data providers, package and model indexes, and locally installed NVIDIA runtimes.*

## People

| Person | Goal | How they reach PitStudio | What they need |
|---|---|---|---|
| Visitor: mining engineer or manager | Understand what dispatch, road grade, electrification, fragmentation, slope monitoring and tailings run-out mean in numbers | A browser on the GitHub Pages site | No account; no GPU required (WebGPU is used if present, WebAssembly otherwise, baked results as the last tier) |
| Visitor: data/AI practitioner | See how far synthetic-only training goes and how gaps are measured | Same | Same; results with confidence intervals and stated gaps |
| Visitor: student | Learn the theory with interactive figures | Same | Same; EN/ES, light and dark themes |
| Visitor: developer | Learn to build and operate an Omniverse-class pipeline on one workstation | The site, the repository and this wiki | A clone; the CPU-capable subset runs anywhere |
| Maintainer | Run recipes on the reference workstation, review results, publish releases | The `studio` CLI and the loopback console | An RTX workstation; acceptance of the NVIDIA terms; the owner acts listed in [owner acts and licences](../studio/owner-acts-and-licences.md) |

The visitor needs no account. The access gate on the site is a demo gate that states it is not a security boundary;
everything published is public ([access gate](../web/access-gate.md)).

## External systems

| System | What PitStudio uses it for | What crosses the boundary | Constraints |
|---|---|---|---|
| GitHub | Source hosting, Actions CI (ubuntu runners, CPU only), Pages hosting, release assets | Git pushes; the Pages artifact; release assets uploaded as drafts, verified and published | Pages: 1 GB site, 10-minute deploy, soft 100 GB/month bandwidth, 10 builds/hour [1]; release assets < 2 GiB each, up to 1,000 per release [2]; files > 100 MiB are blocked in git [3] |
| Open data providers | Real terrain, slope deformation, labelled rock fragments, mining footprints, weather, emission factors | Downloads by `s00_download`, each pinned by SHA-256 in `data/sources.yaml` | Licences traced to the publisher; raw data never committed; derived products follow each licence class ([sources and licences](../data-contract/sources-and-licences.md)) |
| Package and model indexes | PyPI, pypi.nvidia.com, the PyTorch wheel index, npm, Hugging Face | Locked dependencies (`uv.lock` files, `web/pnpm-lock.yaml`); model weights | Versions come only from the lock files; gated weights (Cosmos-Reason2-2B) need the maintainer's acceptance of the terms and a read token |
| NVIDIA runtimes (installed locally) | Isaac Sim + Replicator, Kit (USD Composer/Explorer), ovrtx, TensorRT | Our USD in; renders, sensor data, engines and timings out | Reference-only: never redistributed, never in CI; performance data local-only where the licence requires ([DEC-0004](decisions/DEC-0004-proprietary-sdks-reference-only.md), [DEC-0005](decisions/DEC-0005-performance-data-licence-rule.md)) |
| Companion library `minephys` | Sourced mining models and parameter tables | A git dependency now; a PyPI wheel after the first release | Numpy-only and Pyodide-safe so the same code runs in the studio, the pipeline, Kit and the browser ([DEC-0017](decisions/DEC-0017-companion-package-minephys.md)) |

The open data providers in use are listed with their dataset cards: USGS 3DEP (Bingham Canyon), OpenTopography
(McKinley Mine), the NRW geodata portal (Hambach), the Copernicus EGMS and climate data store, Zenodo (de Wit slope
failure, mining footprints and expansion), PANGAEA (Maus polygons), Mendeley Data (rock fragments), the US EPA (AP-42),
Poly Haven and ambientCG (CC0 textures) and MakeHuman (CC0 people exports). See
[dataset cards](../data-contract/dataset-cards/README.md).

## Relationships

| From → to | What moves | Protocol or mechanism |
|---|---|---|
| Visitor → PitStudio | Page views; live computations in the visitor's browser | HTTPS to GitHub Pages; everything after load runs locally in the browser |
| Maintainer → PitStudio | Recipes, reviews, releases | `studio` CLI, console on 127.0.0.1, `tools/release.py` |
| PitStudio → GitHub | Code, docs, baked artefacts < 10 MB, release assets, the Pages artifact | `git push`, `gh release`, Actions |
| PitStudio → open data providers | Raw data | `s00_download` (pooch) with pinned SHA-256 |
| PitStudio → indexes | Locked packages and weights | `uv sync --frozen`, `pnpm install --frozen-lockfile`, authenticated download for gated weights |
| PitStudio → NVIDIA runtimes | Stage jobs | Subprocesses in isolated environments, file-only handoff |

## Assumptions and limits

- **No operational data source.** No fleet-management system, telemetry feed or historian is in the context. That is
  the reason PitStudio calls itself a simulation-grade twin.
- **No backend for visitors.** Nothing in the public site calls a server other than the static host. The optional
  "connect to my local studio" button probes 127.0.0.1 only after a click, because browsers prompt for local-network
  access when a public page contacts a loopback address [4].
- **The NVIDIA runtimes are optional.** A clone without them can run the open lane, the tests and the web app; the
  pages of tools that need them show their published outputs or "not yet run".

## In PitStudio

- The next zoom level is [C4 containers](c4-containers.md); the physical placement is [deployment](deployment.md).
- Status: the context is fixed by the plan. The site, the repository, CI and the data-source registry exist; the
  studio's NVIDIA environments are locked but not yet run on the reference machine.

## References

1. GitHub Docs. GitHub Pages limits. https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
2. GitHub Docs. About releases. https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
3. GitHub Docs. About large files on GitHub.
   https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
4. Chrome for Developers. Local Network Access. https://developer.chrome.com/blog/local-network-access
5. Brown, S. The C4 model for visualising software architecture. https://c4model.com/
