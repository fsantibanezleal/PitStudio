# Data contract

> What data PitStudio may use, under which licence, how it enters the pipeline, and how every artefact that leaves a run
> is described. · Part of: [Docs home](../README.md) · Related: [Models](../models/README.md) ·
> [Pipelines](../pipelines/README.md) · [Studio](../studio/README.md)

PitStudio is a public, reproducible project, so its data rules carry as much weight as its code. Four rules hold
everywhere:

1. **Licences are traced to the original publisher**, not to a mirror's label, and recorded as SPDX ids in
   `data/sources.yaml`. Share-alike material (CC BY-SA) is always kept in separate entries.
2. **Third-party raw data is never committed.** The pipeline downloads it (`s00_download`, pooch + SHA-256) into
   git-ignored folders and commits only licence-cleared derived artefacts.
3. **Ingestion rejects, it never coerces.** A file or a value that breaks its declared schema stops the stage with a
   report; nothing is silently clipped, cast or imputed.
4. **Every published artefact has a manifest** valid against `contracts/manifest.schema.json`, naming the tool that
   produced it, its measured lane, its licence class and the SHA-256 of every input.

![Sources grouped by licence class and what is committed](../assets/diagrams/data-sources-licences.svg)

*Every source belongs to one licence class; only derived, licence-cleared artefacts are committed or published.*

## Map of this section

| Page | What it answers |
|---|---|
| [Sources and licences](sources-and-licences.md) | Every real source of the plan: landing URL, SPDX licence, size, account, what is committed, fallback; the licence classes, including share-alike and NVIDIA reference-only material |
| [Ingestion](ingestion.md) | The `data/sources.yaml` fields, the download with pooch and SHA-256, the pandera schemas ("reject, never coerce") and the outlier policy |
| [Manifest](manifest.md) | The manifest contract: telemetry, determinism, encoder record, licence class, `performance: local-only`, asset host (git or release), the measured lane label |
| [Recipes and tool registry](recipes-and-tool-registry.md) | The runner recipe schema and the studio tool registry that becomes the web tool map |
| [Capabilities](capabilities.md) | The existing `contracts/capabilities.schema.json`, field by field |
| [Dataset cards](dataset-cards/README.md) | One datasheet per source, including the synthetic data and the MakeHuman people assets |

## The contracts at a glance

All contracts are JSON Schema 2020-12 files in `contracts/`. Pydantic models (Python) and TypeScript types (web) are
generated from them, and CI fails when the generated types drift from the schemas.

| Schema | Status today | Producer → consumer |
|---|---|---|
| `contracts/capabilities.schema.json` | **exists**, covered by 5 contract tests | `studio/bench/run_bench.py` → runner guards, web `/studio` |
| `contracts/manifest.schema.json` | written in the specification phase | runner, `s60_export`, `st56_encode`, `studio publish` → web app, CI |
| `contracts/recipe.schema.json` | written in the specification phase | maintainer → runner |
| `contracts/tools.schema.json` | written in the specification phase | maintainer → web tool map |
| `contracts/sources.schema.json` | written in the specification phase | maintainer → `s00_download`, docs |
| ingestion schemas (pandera) | written in the build phase | `s10_preprocess` → every later stage |

## Status

- `data/sources.yaml` exists with an empty `sources: []` list and a commented example entry. The real entries are added
  with the download stage.
- The only third-party archive handled so far is the Mendeley rock-fragment set, downloaded and checked during the
  bootstrap (label format, counts, augmentation structure). See its
  [dataset card](dataset-cards/mendeley-rock-fragments.md). Nothing has been trained on it.
- No run has produced a manifest yet, and `studio/capabilities.json` does not exist yet: the GPU capability probes are
  written but not yet run on the reference machine.

## Where to go next

- To add or change a source: [Ingestion](ingestion.md), then a new [dataset card](dataset-cards/README.md).
- To understand a published number in the web app: [Manifest](manifest.md).
- To see how stages consume these contracts: [Pipeline stages](../pipelines/pipeline-stages.md) and
  [Studio stages](../pipelines/studio-stages.md).
