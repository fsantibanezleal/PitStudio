# DEC-0017: Domain knowledge lives in the companion package `minephys`

> The sourced mining-engineering models and their cited parameter tables live in a separate, numpy-only, Pyodide-safe
> Python package, `minephys`, which the studio, the pipeline, Kit and the browser all import; the wiki's knowledge
> catalogue is generated from it. · Part of: [decisions](README.md) · Related: [minephys](../../frameworks/minephys.md) ·
> [knowledge catalogue](../../knowledge/README.md) · [theory](../../theory/README.md)

**Status:** Accepted, 2026-10-04

## Context

PitStudio's analytical core (haulage resistance and cycle times, match factor and queueing, Kuz-Ram and Swebrec, PPV and
flyrock, Hoek–Brown and limit equilibrium, inverse velocity, Beverloo and repose, Bond and Morrell, AP-42 and the
Gaussian plume, the dust and slope-radar sensor models, Lane's cut-off and a small min-cut) is needed in four places:

- the open studio and the pipeline (Python 3.14), to generate and evaluate data;
- inside Kit (Kit's own Python 3.12), for scene annotations and checks;
- the browser, through a Pyodide button that runs the same Python code client-side [1];
- other public mining repositories of the maintainer, which need the same models.

The knowledge base must also be machine-checkable: every constant needs its value or range, units, citation with page,
and a verification status, so that the UI can flag unverified rows. Three conditions justify a separate package: a
domain capability the product consumes, a second consumer, and a purity boundary (numpy-only, so it runs in Pyodide and
in Kit).

## Decision

- **Package.** `minephys` (distribution and import name), in its own public repository, Apache-2.0, depending only on
  numpy and PyYAML, for Python ≥ 3.12, tested on 3.12–3.14, in Pyodide and inside Kit (installed to a git-ignored target
  folder).
- **Modules.**

  | Module | Contents |
  |---|---|
  | `haulage` | rimpull and retarder, resistances, cycle time, energy, CO₂, trolley and battery-electric, match factor, M/M/c, mean-value analysis |
  | `blasting` | Kuz-Ram, KCO, Swebrec, PPV, flyrock |
  | `geotech` | Hoek–Brown, limit equilibrium, inverse velocity, Bayesian time of failure, GB-InSAR slope-radar line-of-sight model |
  | `bulk` | Beverloo, repose, CEMA, Gy |
  | `comminution` | Bond, Morrell, population balance, Klimpel |
  | `environment` | AP-42, Gaussian plume, Beer–Lambert dust attenuation for lidar |
  | `planning` | Lane, small min-cut |
  | `knowledge` | cited tables, bibliography and loader |

- **Knowledge tables.** `minephys/knowledge/*.yaml` plus `references.bib`: value or range, units, citation and page,
  verification status, and the code symbol that uses it. Schema-validated. The web app and the generated catalogue in
  [knowledge/](../../knowledge/README.md) flag UNVERIFIED rows.
- **Test-first.** Every model has locked tests from worked examples in its primary source before it is implemented.
- **Release.** A git dependency of PitStudio until its first release; then TestPyPI and PyPI through trusted publishing,
  which needs two pending publishers registered by the maintainer at release time. The browser loads its wheel together
  with numpy and PyYAML on user action, inside the runtime budget.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Parameter tables and models only inside the PitStudio repository | One repository | Not importable by Kit, Pyodide or other projects without pulling the whole product; no purity boundary | Fails the second-consumer and purity conditions |
| A separate documentation site only | Good for reading | Tables would not be executable, testable or version-locked with the code that uses them | The knowledge must run, not only be read |

## Consequences

**Positive.** One implementation of each model for every runtime; the knowledge base is executable, tested and
versioned; the same code runs in the browser, so live results match the Python reference by construction.

**Negative, accepted.** Two repositories to release in step; a git-pinned dependency until the first PyPI release; an
owner act for the PyPI publishers.

**Watch.** Pyodide's numpy version; Kit's Python version; wheel size in the browser's runtime budget.

## References

1. Pyodide releases. https://github.com/pyodide/pyodide/releases
2. `minephys` repository. https://github.com/fsantibanezleal/minephys
