# Pipeline stages

> The frozen pipeline stage list, `s00_download` to `s60_export`, extended by `s62_accel` and `s64_bench`: what each
> stage reads and writes, how long it is expected to take, and how it is cached and checked. · Part of:
> [Pipelines](README.md) · Related: [Studio stages](studio-stages.md) · [Ingestion](../data-contract/ingestion.md) ·
> [Training recipes](../models/training-recipes.md) · [Export, parity and acceleration](../models/export-parity-acceleration.md)

## What and why

The pipeline lane is where real and synthetic data become validated datasets, trained models, evaluations and web
artefacts. Its stage list is frozen (download → synthesize → preprocess → feature extraction → train → infer →
evaluate → export), so that every case uses the same steps and every artefact can be traced to one of them. Two
acceleration stages extend the list after `s60_export`; they run in an isolated environment because TensorRT 11.3
cannot share one with the TensorRT 10 libraries that ONNX Runtime's TensorRT provider loads.

![Pipeline stages with environments, runtimes and outputs](../assets/diagrams/pipeline-stages.svg)

*Data → learn → ship in `pipeline/`, then accelerate in `pipeline/accel/`; outputs split by lane.*

## The stages

Runtimes are the plan's estimates; the runner measures each run and records the measured time in its manifest.

| Stage | Environment | Runtime (estimate) | Reads | Writes | GPU lock | Determinism |
|---|---|---|---|---|---|---|
| `s00_download` | `pipeline/` | hours, once | `data/sources.yaml` | raw files (git-ignored) | none | `bitwise` (pinned SHA-256) |
| `s05_synthesize` | `pipeline/` | minutes–hours | recipe params, seeds; studio outputs as files | synthetic tables, fields, labels | none or `gpu0.compute` | `bitwise` (CPU generators) / `statistical` |
| `s10_preprocess` | `pipeline/` | minutes–1 h | raw + synthetic files | validated, cropped, split data | none | `bitwise` |
| `s20_feature_extraction` | `pipeline/` | minutes–1 h | preprocessed data | features, embeddings | `gpu0.compute` when embedding images | `statistical` on GPU |
| `s30_train` | `pipeline/` | per model ([Training recipes](../models/training-recipes.md)) | features, splits | checkpoints (git-ignored), training curves | `gpu0.compute` | `statistical` |
| `s40_infer` | `pipeline/` | minutes | checkpoints, held-out inputs | predictions of models and baselines | `gpu0.compute` | `statistical` |
| `s50_evaluate` | `pipeline/` | ≈ 0.5–2 h | predictions, references | metrics with paired CIs, C2ST / TSTR, corruption curves | none or `gpu0.compute` | `bitwise` given inputs |
| `s60_export` | `pipeline/` | minutes | checkpoints, scenes, results | ONNX + parity reports, glTF / 3D Tiles, shards, manifest, budget report, release-asset list | none | `bitwise` |
| `s62_accel` | `pipeline/accel/` | 1–2 h | ONNX files from `s60_export` | TensorRT engines fp32 / fp16 / int8 / fp8 (local only) | `gpu0.compute` | `none` (engine builds are not reproducible bit for bit) |
| `s64_bench` | `pipeline/accel/` (+ `pipeline/` for ORT backends) | 2–4 h | engines, ONNX files, golden sets | latency, throughput, J/inference, accuracy Δ, per-engine parity | `gpu0.compute` | `statistical` |

Training-throughput benchmarks are **not** a stage: they are the runner probe `studio bench`, which measures each model
in a short run before any long run.

## Stage by stage

### `s00_download`

Reads every entry of `data/sources.yaml`, downloads each file with pooch, and verifies its SHA-256; a mismatch stops
the stage. Account-bound sources (OpenTopography, Copernicus CDS, EGMS Explorer) read their keys from environment
variables and are skipped, with their documented fallback, when no key exists. Raw files go under `PITSTUDIO_DATA`
(default: the git-ignored `data/raw/` and `data/external/`). Details: [Ingestion](../data-contract/ingestion.md).

### `s05_synthesize`

Runs the CPU generators of the pipeline lane and collects the studio's GPU outputs:

| Generator | Library | Output |
|---|---|---|
| Haul-cycle DES | `minehaulsim` 0.12.1 (`pipeline/uv.lock`) | cycle tables (Parquet) |
| Kuz-Ram / Swebrec size distributions | `minephys.blasting` | PSD curves |
| Voight creep series | `minephys.geotech` | displacement series with a known failure time |
| Gaussian plume fields | `minephys.environment` | Zarr fields |
| Synthetic block models | `oreblocks` 0.5.2 | deposits with stamped optima |
| Analytical sweeps for the meta-model | `minephys.comminution` | sweep tables |
| Studio outputs (SDG images, sensor clouds, physics fields, Isaac Lab rollouts) | studio stages | collected as files with digests |

All synthetic data is labelled synthetic and validated as described in the
[synthetic-data card](../data-contract/dataset-cards/synthetic-data.md).

### `s10_preprocess`

Applies the ingestion schemas (pandera, "reject, never coerce"), crops to areas of interest, builds grids and tiles,
and fixes the split groups (for example the 231 source groups of the Mendeley fragment images). Terrain meshes and USD
are built by the studio stage `st10_terrain`, not here.

### `s20_feature_extraction`

Computes model inputs that are not raw data: tabular features, window features of displacement series, and frozen
DINOv2 image embeddings used by the classifier two-sample tests.

### `s30_train`

Trains every model of the [model cards](../models/README.md) except the Isaac Lab policies (`st60_il_train`) and the
DEM calibration (a studio stage). One job at a time under `gpu0.compute`, checkpointed at least once per epoch,
resumable, with an out-of-memory fallback declared in the recipe.

### `s40_infer`

Produces held-out predictions of each model **and of its classical baseline** on the same splits, so that every
comparison in `s50_evaluate` is paired.

### `s50_evaluate`

Computes held-out metrics, paired 95 % confidence intervals and the decision rule; classifier two-sample tests with a
real-vs-real baseline, TSTR vs TRTR for fragmentation, corruption curves for the detectors, and the descriptive
time-of-failure errors of the single real slope event. Thresholds come from `specs/000-foundation/thresholds.yaml`.

### `s60_export`

Exports ONNX (opset 17–19, IR version pinned to 10) with the two export parity gates, bakes glTF and 3D Tiles from the
scene, writes replay shards, measures each artefact's lane, checks the web budgets, writes the manifest and the list
of files that become release assets ([Export, parity and acceleration](../models/export-parity-acceleration.md),
[Manifest](../data-contract/manifest.md)).

### `s62_accel` and `s64_bench`

Build TensorRT 11.3 engines from the exported ONNX files and benchmark PyTorch, ONNX Runtime (CPU, CUDA, TensorRT
provider) and native TensorRT, with per-engine parity on every TensorRT version and provider. Engines stay local;
only the result tables are published, on the Acceleration tab. Total ≈ 4–7 GPU-h.

## Cache, resume and failure

- **Cache key:** SHA-256 over stage id, code digest, environment lock digest, params, derived seed and input digests;
  a hit materialises outputs from the content-addressed store under `PITSTUDIO_STORE`.
- **Atomic outputs:** each stage writes into its run's temporary folder and is promoted only after its outputs validate
  against their schemas.
- **Resume:** shardable stages (synthesis, inference) resume per shard; training resumes from its last checkpoint.
- **Retries:** only classified transient failures are retried (out-of-memory → declared fallback); a deterministic
  failure stops with the log tail in the manifest.

## Assumptions and limits

- Runtimes assume the reference laptop GPU; the Linux GPU profile runs the same recipes with different measured times.
- `s05_synthesize` depends on studio stages for every GPU-rendered or GPU-simulated dataset; on a machine without the
  NVIDIA environments those inputs are missing, and the dependent cases show "not yet run" rather than a substitute.
- The acceleration stages need an NVIDIA GPU and the TensorRT wheels from NVIDIA's package index; they never run in
  CI.

## In PitStudio

- **Code paths:** `pipeline/` (uv project `pitstudio-pipeline`, Python 3.14), `pipeline/accel/` (`pitstudio-accel`),
  orchestrated by the runner in `src/pitstudio/runner/`.
- **CI today:** the `pipeline/` CPU lane is installed and its tests run on every push ("Pipeline smoke (CPU, samples
  only)"); see [Run instructions](run-instructions.md).
- **Status:** no stage has run. Stages, schemas and recipes are implemented in the build phase.

```bash run deferred=P6
uv run --extra runner studio plan studio/recipes/cases/<case>.yaml
uv run --extra runner studio run studio/recipes/cases/<case>.yaml --stage s50_evaluate
```

## References

1. Pooch documentation, *Hashes*. https://www.fatiando.org/pooch/latest/hashes.html
2. pandera documentation. https://pandera.readthedocs.io/en/stable/
3. uv CLI reference (`uv run --project`, `--frozen`, `--locked`). https://docs.astral.sh/uv/reference/cli/
4. NVIDIA, *TensorRT 11.0.0 release notes* (strongly typed networks). https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-11/11.0.0.html
5. ONNX Runtime v1.30.0 CI variables (TensorRT 10.14.1.48 for the TensorRT provider). https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/tools/ci_build/github/azure-pipelines/templates/common-variables.yml
