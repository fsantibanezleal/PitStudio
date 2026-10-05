# Knowledge

> The knowledge base: what it contains, which pages are generated from the `minephys` library at build time
> (parameters, equations, bibliography, glossary), how every parameter row carries its source, page and verification
> status, and how UNVERIFIED values are flagged. · Part of: [docs home](../README.md) · Related:
> [minephys](../frameworks/minephys.md) · [theory](../theory/README.md) · [glossary](../reference/glossary.md) ·
> [DEC-0017 companion package minephys](../architecture/decisions/DEC-0017-companion-package-minephys.md)

## What the knowledge base is

PitStudio is meant to be read as well as run. Its knowledge base has two halves:

| Half | Where | Holds |
|---|---|---|
| Narrative | `docs/` (this wiki) | context, theory with derivations, methods, cases, frameworks, data cards, model cards, guides |
| Machine-readable | the companion library `minephys` (`knowledge/*.yaml` + `references.bib`) | every model parameter with value or range, units, citation and page, verification status and the code symbol that uses it; the bibliography; glossary entries |

The machine-readable half is the single source for numbers: the Python models, their TypeScript ports in the browser,
the docs and the web app's `/knowledge` route all read the same tables, so a value is written once and cited once.

## Generated pages

These pages are **generated in the build phase** from the `minephys` version pinned in `uv.lock`. They do not exist
yet; until they do, the theory pages cite primary sources directly.

| Generated page | Source | Web route | Status |
|---|---|---|---|
| Parameters | `minephys/knowledge/*.yaml` | `/knowledge` → parameter browser | generated in the build phase |
| Equations | equation metadata of the `minephys` models (LaTeX, symbols, units, source) | `/knowledge` → equation explorer | generated in the build phase |
| Bibliography | `minephys/knowledge/references.bib` | `/knowledge` → bibliography | generated in the build phase |
| Glossary EN/ES | glossary entries of the knowledge tables, merged with the [hand-written glossary](../reference/glossary.md) | `/knowledge` → glossary | generated in the build phase |
| Datasets and frameworks | `data/sources.yaml`, `studio/tools.yaml` | `/knowledge` → datasets, frameworks | generated in the build phase |

Generation is deterministic, and CI fails when a generated page differs from what the pinned tables produce (a drift
check), so the docs cannot silently disagree with the code.

## The row format

Each parameter is one row in a YAML table of `minephys/knowledge/`:

| Field | Meaning |
|---|---|
| `id` | stable identifier |
| `value` or `range` | the number, or the minimum and maximum of a published range |
| `units` | units of the value as published; the code works in SI and converts explicitly |
| `citation` | BibTeX key in `references.bib` |
| `page` | page, table or equation number in the source |
| `verification` | `verified` (read on the primary source) or `UNVERIFIED` (not yet pinned) |
| `symbol` | the code symbol that uses the value, e.g. a function argument default |

An illustrative row (the schema is fixed in `minephys`'s own specification):

```yaml
- id: ppv_limit_0_300ft
  value: 1.25
  units: in/s
  citation: cfr30_816_67
  page: "§816.67, maximum PPV table"
  verification: verified
  symbol: minephys.blasting.ppv_limit
```

The tables are schema-validated, and every row without a source fails validation. Rows marked `UNVERIFIED` are
allowed but are flagged in the UI and in the generated pages.

## Verification status

A value moves from `UNVERIFIED` to `verified` only when it is read on the primary page (paper, standard, regulation,
official dataset page) and pinned by a test against a worked example from that source, during the specification and
test-first build of each `minephys` model. Until then it is shown as **"UNVERIFIED — pinned at specification"**.

The starting status of some values that the cases use, as the research left them:

| Value | Source | Status today |
|---|---|---|
| US surface-mining PPV limits 1.25 / 1.00 / 0.75 in/s by distance band (0–300 ft, 301–5,000 ft, beyond) | 30 CFR § 816.67 [1] | verified (regulatory text) |
| Safe residential PPV of 0.5–2.0 in/s depending on frequency and construction (76 homes, 219 blasts) | USBM RI 8507 [2] | verified (report record) |
| Trolley assist: +44 % uphill speed, −16 % cycle travel time, 85 % fuel saving per up–down cycle | Valenzuela Cruzat and Valenzuela 2018 [3] | verified (publisher abstract) |
| AP-42 unpaved-road PM10 constants $k = 1.5$, $a = 0.9$, $b = 0.45$ | AP-42 §13.2.2 [4] | **UNVERIFIED — pinned at specification** (PDF not read) |
| AP-42 PM2.5 constant $k$ (value withheld: two candidate values in excerpts) | AP-42 §13.2.2 [4] | **UNVERIFIED — pinned at specification** |
| Diesel ≈ 2.70 kg CO₂/L (from 10.21 kg CO₂ per US gallon) | EPA GHG Emission Factors Hub 2025 [5] | **UNVERIFIED — pinned at specification** |
| Swebrec fits with $r^2 > 0.995$ over 2–3 orders of magnitude of size | Ouchterlony 2005 [6] | **UNVERIFIED — pinned at specification** (search excerpt) |
| Hoek–Brown disturbance $D \approx 1.0$ for large production blasting | Hoek, Carranza-Torres and Corkum 2002 [7] | **UNVERIFIED — pinned at specification** |
| Kuz-Ram rock-factor constant 0.06 and Cunningham uniformity-index form | Cunningham 2005 [8] | **UNVERIFIED — pinned at specification** |

Values that remain unverified after the specification phase stay out of every headline result.

## Units

`minephys` computes in SI units. Sources that publish in US customary units (AP-42 in lb per vehicle-mile, 30 CFR in
in/s and ft) keep their published units in the table, and the model converts explicitly at its boundary; unit
conversions are tested.

## Assumptions and limits

- The knowledge base is educational. Parameter ranges come from the literature; they are not site data and do not
  replace site testing.
- Paywalled standards (CEMA, ISO 5048, DIN 22101, ISO 23247) are cited, and only their public equation forms are
  implemented; their text is never reproduced.

## In PitStudio

- The `minephys` repository holds the tables and models; PitStudio pins it in `uv.lock` (a git dependency until its
  first PyPI release).
- Spec `020-web-knowledge` (theory, methods, results, knowledge routes) and foundation requirement FR-000-10 (sources
  and UNVERIFIED flags).
- Status: no table or generated page exists yet; this page describes the format they will follow.

## References

1. 30 CFR § 816.67, "Use of explosives: control of adverse effects" (Cornell LII). https://www.law.cornell.edu/cfr/text/30/816.67
2. Siskind, D. E. et al. (1980), "Structure response and damage produced by ground vibration from surface mine blasting", USBM RI 8507. https://www.osti.gov/biblio/6777883
3. Valenzuela Cruzat, J. and Valenzuela, M. A. (2018), "Modeling and evaluation of benefits of trolley assist system for mining trucks", IEEE TIA 54(4). https://doi.org/10.1109/tia.2018.2823261
4. US EPA, AP-42 §13.2.2 "Unpaved Roads" (November 2006). https://www.epa.gov/sites/default/files/2020-10/documents/13.2.2_unpaved_roads.pdf
5. US EPA, "GHG Emission Factors Hub" (2025). https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf
6. Ouchterlony, F. (2005), "The Swebrec function: linking fragmentation by blasting and crushing", Mining Technology 114(1). https://doi.org/10.1179/037178405X44539
7. Hoek, E., Carranza-Torres, C. and Corkum, B. (2002), "Hoek–Brown failure criterion — 2002 edition", NARMS-TAC (bibliographic). https://www.semanticscholar.org/paper/HOEK-BROWN-FAILURE-CRITERION-2002-EDITION-Hoek-Carranza-Torres/e44829e6d2c1484d25efe6be2db830e16c8f9d89
8. Cunningham, C. V. B. (2005), "The Kuz-Ram fragmentation model — 20 years on", EFEE Brighton (bibliographic). https://www.scirp.org/reference/referencespapers?referenceid=4120306
