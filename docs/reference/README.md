# Reference

> Look-up pages: every command (existing and planned), every configuration variable and file, the bilingual glossary
> and the frequently asked questions. · Part of: [docs home](../README.md) · Related: [guides](../guides/README.md) ·
> [studio](../studio/README.md) · [knowledge](../knowledge/README.md)

## Orientation

Guides tell you how to do a task; these pages tell you exactly what a command accepts or what a variable means. Each
entry says whether it **exists today** or is **planned** for the build phase, using the same code-block convention as
the guides (`bash run`, `powershell run`, `bash run deferred=P6`, `bash` for illustrative fragments).

## Map

| Page | What you find |
|---|---|
| [cli.md](cli.md) | Existing commands (`studio/bench/run_bench.py`, `scripts/*`, `tools/*`, web `pnpm` scripts) and the planned `studio` CLI (`bench env`, `plan`, `run`, `publish`, `profile`, `gc`) and pipeline runner (`run_pipeline --stage …`) |
| [configuration.md](configuration.md) | Environment variables (`PITSTUDIO_*`, `GPU_LOCK_DIR`, `BASE_PATH`, `ACCESS_PASSPHRASE`, tool caches), machine profiles, recipes, `params.yaml`, per-environment project files, thresholds |
| [glossary.md](glossary.md) | Over 80 terms in English and Spanish: mining, simulation, machine learning and the NVIDIA stack |
| [faq.md](faq.md) | Short answers to the questions people ask first: what PitStudio is and is not, licences, hardware, honesty rules |

## Related look-ups elsewhere

- Stage-by-stage behaviour: [pipeline stages](../pipelines/pipeline-stages.md) and
  [studio stages](../pipelines/studio-stages.md).
- Schemas: [manifest](../data-contract/manifest.md),
  [recipes and tool registry](../data-contract/recipes-and-tool-registry.md),
  [capabilities](../data-contract/capabilities.md).
- Parameters, equations and bibliography generated from `minephys`: [knowledge](../knowledge/README.md).
