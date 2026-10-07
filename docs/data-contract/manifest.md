# Manifest

> The one manifest format shared by studio runs and web assets: what produced an artefact, from which inputs, on which
> GPU, how deterministic it is, how it was encoded, under which licence, and in which lane it may be shown. · Part of:
> [Data contract](README.md) · Related: [Sources and licences](sources-and-licences.md) ·
> [Recipes and tool registry](recipes-and-tool-registry.md) · [Runner](../studio/runner.md) ·
> [Showcase rules](../web/showcase-rules.md)

## What and why

PitStudio's web app shows numbers, videos, point clouds and models that were produced on one workstation by more than a
dozen tools. A reader must be able to ask, for any of them: *which tool made this, from what, when, and may I trust the
label next to it?* The manifest answers those questions in a machine-checked way. It is also the hinge of the
project's honesty rules:

- a tool counts as "done" only when at least one published artefact names it as producer;
- a LIVE badge is only allowed when the measured gate says so;
- a performance number of licence-restricted software never reaches a committed file;
- the SHA-256 recorded in a manifest must equal the SHA-256 of the file the site serves.

![Manifest producers, field groups and consumers](../assets/diagrams/manifest-contract.svg)

*Four producers write manifests; eight field groups are read by the web app, CI and the Pages build.*

## Where manifests live

| Manifest | Location | Committed? |
|---|---|---|
| Run manifest | `runs/<run_id>/manifest.json` in the studio store (`PITSTUDIO_STORE`, default a short path such as `C:\ps` on Windows) | no (local store) |
| Run events and telemetry | `runs/<run_id>/events.jsonl`, `runs/<run_id>/telemetry.parquet` | no |
| Web asset manifest | `web/public/assets/manifest.json`, baked by `s60_export` and `studio publish` | yes |
| Accepted model runs | `models/cards/` (model cards with their accepted run manifests) | yes |
| Published run cards | web data baked by `studio publish <run>` (telemetry downsampled) | yes |

The normative schema is `contracts/manifest.schema.json` (JSON Schema 2020-12), written in the specification phase.
Pydantic and TypeScript types are generated from it, and CI fails on drift. The field names below follow the plan and
the studio design; the schema may refine them.

## Field groups

### Identity

| Field | Meaning |
|---|---|
| `run_id` | unique id of the run |
| `recipe`, `recipe_sha256` | recipe file and its digest ([Recipes and tool registry](recipes-and-tool-registry.md)) |
| `cache_key` | SHA-256 over stage id, code digest, environment lock digest, params, derived seed and input digests |
| `git_sha`, `runner_version`, `created` | code version, runner version, UTC timestamp |
| `producer.tool` | id of the tool in the studio tool registry (`studio/tools.yaml`); the web tool pages filter on it |
| `stages[]` | stage ids with cache hit or miss, exit status, retries and wall time |

### Inputs

| Field | Meaning |
|---|---|
| `inputs[].id` | a source id from `data/sources.yaml`, or an upstream artefact id |
| `inputs[].sha256` | digest of the exact bytes used |
| `params`, `seed` | stage parameters and the recipe's master seed |

### Environment

| Field | Meaning |
|---|---|
| `env.name`, `env.python` | uv environment (`studio/`, `pipeline/`, `studio/isaac/`, …) and its Python version |
| `env.lock_sha256` | digest of that environment's `uv.lock` |
| `env.versions` | tool versions **read from the lock**, never typed by hand |
| `gpu.name`, `gpu.driver`, `gpu.vram_total_bytes`, `gpu.power_limit_enforced_w` | the GPU and its enforced power limit, read through NVML at run time |
| `profile` | machine profile id (`laptop-rtx5000ada`, `linux-gpu`) |

**Privacy:** the schema has no field for a host name, a user name or an absolute path. Error text is scrubbed the same
way the capability report already does it (the repository root becomes `<repo>`, the home folder `~`,
[Capabilities](capabilities.md)).

### Telemetry (per stage)

NVML is sampled at 1–4 Hz while a stage runs; the full series stays in `telemetry.parquet`, and the manifest stores a
summary.

| Field | Definition and source |
|---|---|
| `wall_s`, `sample_hz`, `n_samples` | duration and sampling of the stage |
| `gpu_busy_pct` {mean, p50, p95} | NVML utilisation: "percent of time over the past sample period during which one or more kernels was executing", with a sample period of 1/6 s to 1 s depending on the product [1]. **It is a time-busy fraction, not SM occupancy.** |
| `mem_used_peak_bytes` | device-level peak (per-process memory is not available under Windows WDDM [2]) |
| `power_w` {mean, p95, max}, `power_at_limit_frac` | board power (on Ampere or newer, the average over the last second [2]) and the fraction of samples at ≥ 95 % of the enforced limit |
| `energy_j` | difference of two readings of the total-energy counter, which NVML reports in mJ since the driver was loaded [3] |
| `sm_clock_mhz` {mean, p5}, `temp_c_max` | clocks and temperature |
| `clocks_event_frac` {sw_power_cap, sw_thermal, hw_thermal, hw_slowdown, power_brake, idle} | share of samples per clocks-event reason [4] |
| `nvenc_util_pct` | encoder utilisation, for encode stages [3] |
| `throughput` {value, unit} | stage-specific: particle-steps/s, images/s, samples/s, encode fps |

On a power-limited laptop GPU, `SwPowerCap` under load is the expected signature of a fully used GPU; thermal and
hardware slowdown reasons are the warning signs [4]. A benchmark window with hardware thermal slowdown is flagged, and
comparisons are made only between runs with the same enforced power limit.

### Determinism

| Field | Meaning |
|---|---|
| `determinism.class` | `bitwise`, `statistical` or `none`, declared per stage |
| `determinism.seeds` | master seed and per-stage seeds, derived from a hash of (master seed, stage id, shard) |
| `determinism.rerun_check` | result of re-running one shard: equal SHA-256 (`bitwise`) or observables within tolerance (`statistical`) |

- `bitwise`: scene authoring (build-twice hash) and Warp kernels run in Warp's deterministic mode for atomic
  operations, added in Warp 1.15.0 [5].
- `statistical`: MPM, RTX rendering and synthetic data, training. PyTorch states that fully reproducible results are not
  guaranteed across releases or platforms; evaluation runs set `torch.use_deterministic_algorithms(True)` and
  `cudnn.benchmark = False` [6]. Replicator runs set its global seed [7].
- `none`: documented exceptions only.

### Encoder record (videos)

One entry per published video file ([Encode videos](../guides/encode-videos.md)):

| Field | Meaning |
|---|---|
| `codec`, `profile`, `pix_fmt`, `width`, `height`, `fps`, `frames`, `duration_s` | stream description |
| `bitrate_kbps`, `bytes`, `sha256` | size and digest of the file served |
| `vmaf` {mean, p5, model} | quality against the lossless source frames, from the VMAF search |
| `source_frames_sha256` | digest of the frame list that was encoded |
| `encoder` {ffmpeg_version, build_sha256, nvenc_api, args} | the exact FFmpeg build (8.1, LGPL) and arguments |
| `encode_fps` | encoder throughput |

### Artefacts

| Field | Meaning |
|---|---|
| `artefacts[].path`, `bytes`, `sha256` | the file, its size and digest |
| `artefacts[].lane` | `live`, `replay` or `static`, **as measured** (below) |
| `artefacts[].lane_measurements` | bytes, interaction or run time on the T2 tier, trace size |
| `artefacts[].asset_host` | `git` or `release` |
| `artefacts[].release_tag` | for `release`: the `assets-vX.YY.ZZZ` tag that holds the file |
| `artefacts[].budget_class` | the web budget class the file counts against |

### Licence

| Field | Meaning |
|---|---|
| `licence_class` | one of the classes in [Sources and licences](sources-and-licences.md): `public-domain`, `open-no-attribution`, `attribution`, `share-alike`, `own`, `display-only`, `reference-only` |
| `spdx`, `attribution` | SPDX id and the attribution text that must travel with the artefact |
| `performance` | `public` or `local-only`, per stage |

## The lane label is measured, not declared

A capability is **LIVE** if and only if it is web-drivable, its asset is ≤ 25 MB, one interaction takes ≤ 16 ms or one
run takes ≤ 1 s on the T2 tier, and its trace is ≤ 10 MB. Otherwise it is PRECOMPUTE / REPLAY. The export stage
measures these quantities, writes them to `lane_measurements`, and derives `lane`; CI recomputes the label from the
measurements and fails when it disagrees with the one in the manifest. Examples from the plan: D-FINE-N at fp16
(8 MB) is LIVE; RF-DETR-Seg-N (61 MB at fp16) is PRECOMPUTE ([Models](../models/README.md)).

## The `performance: local-only` marker

Kit, Isaac Sim, Replicator and ovrtx fall under the NVIDIA Software License Agreement, whose §8.9 forbids disclosing
benchmark, regression or performance data without written permission [8]; TensorRT for RTX has the same kind of
clause in §2.13 [9]. Every stage that runs one of these tools carries `performance: local-only`:

- its **outputs** (images, videos, point clouds, labels, answers) are published normally, with their own licence class;
- its **metrics and telemetry** stay in the local run folder; the published manifest replaces them with the string
  "measured locally, not published (licence)", exactly as the capability report does today
  ([Capabilities](capabilities.md));
- a CI guard fails if a committed file contains a metric from a stage marked `local-only`.

Regular TensorRT is not covered: its licence has no such clause, and the TensorRT probe pins the reviewed licence text
by SHA-256 ([Sources and licences](sources-and-licences.md)). Stages that run our own models under TensorRT are
`public`.

## Asset host: git or release

| Host | When | Rules |
|---|---|---|
| `git` | files < 10 MB | baked assets in git total ≤ 100 MB |
| `release` | larger files (videos, splats, models > 10 MB) and overflow archives of small-file classes | GitHub Release assets under a tag `assets-vX.YY.ZZZ`, pinned by SHA-256 in the manifest |

The release flow is compatible with immutable releases: create the `assets-vX.YY.ZZZ` release as a draft, upload,
verify every SHA-256 against the manifest, then publish it with `--latest=false`; every re-bake gets a new tag, and
the product release stays "Latest". At build time `.github/workflows/pages.yml` fetches the assets by tag, checks
their SHA-256 and copies them into the Pages artifact, so the browser fetches them same-origin and never from the
release page. GitHub limits release assets to under 2 GiB per file [10].

## An illustrative manifest

```json
{
  "run_id": "2026xxxxTxxxxxxZ-d1-unet",
  "recipe": "studio/recipes/cases/<case>.yaml",
  "cache_key": "<sha256>",
  "git_sha": "<40 hex>",
  "producer": { "tool": "pytorch", "stage": "s30_train", "env": "pipeline" },
  "inputs": [ { "id": "mendeley-78ht3pjsr4", "sha256": "7f4336a4…f402d" } ],
  "env": { "name": "pipeline", "python": "3.14", "lock_sha256": "<sha256>", "versions": { "torch": "2.14.1+cu130" } },
  "gpu": { "name": "<from NVML>", "driver": "<from NVML>", "power_limit_enforced_w": 0 },
  "determinism": { "class": "statistical", "seeds": { "master": 0 }, "rerun_check": "pending" },
  "stages": [ { "id": "s30_train", "performance": "public", "telemetry": { "gpu_busy_pct": { "mean": 0 } } } ],
  "artefacts": [
    { "path": "models/onnx/<model>.onnx", "bytes": 0, "sha256": "<sha256>", "lane": "live",
      "asset_host": "git", "licence_class": "own", "spdx": "Apache-2.0", "attribution": "…" }
  ]
}
```

All values above are placeholders: no run has produced a manifest yet.

## Assumptions and limits

- NVML fields can be missing on a given laptop SKU under WDDM. A missing field is stored as `null` with a reason, and
  the web app shows "not available on this GPU" rather than a guess.
- "Busy %" is a time fraction. The web app always pairs it with power-at-limit and, where the maintainer ran an
  elevated Nsight capture, with kernel-level evidence; it never headlines busy % alone ([Nsight and NVML](../frameworks/nsight-nvml.md)).
- Determinism is per engine and is recorded, not assumed. Statistical stages are compared on observables with
  tolerances from the specification.
- The manifest describes provenance; it does not make a result correct. Correctness comes from the tests, parity gates
  and evaluations the manifest points to.

## In PitStudio

- **Producers:** the runner (`src/pitstudio/runner/`), `s60_export`, `st56_encode`, `studio publish <run>`.
- **Consumers:** the web app (badges, tool pages, runs ledger, GPU evidence), the CI lane gate, the budget and size
  checks, the licence guard, and `pages.yml`.
- **Requirement:** every published artefact is described by a manifest valid against `contracts/manifest.schema.json`
  that names its producer tool, measured lane, licence class, inputs with SHA-256 and the run that produced it.
- **Status:** schema written in the specification phase; no run has produced a manifest yet.

## References

1. NVIDIA, NVML API reference, `nvmlUtilization_t`. https://docs.nvidia.com/deploy/nvml-api/api/structnvmlUtilization__t.html
2. NVIDIA, *nvidia-smi* documentation. https://docs.nvidia.com/deploy/nvidia-smi/index.html
3. NVIDIA, NVML API reference, device queries (power, energy, encoder utilisation). https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceQueries.html
4. NVIDIA, NVML API reference, clocks event reasons. https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html
5. NVIDIA Warp changelog (deterministic execution mode for atomic operations, 1.15.0). https://raw.githubusercontent.com/NVIDIA/warp/main/CHANGELOG.md
6. PyTorch reproducibility notes. https://raw.githubusercontent.com/pytorch/pytorch/main/docs/source/notes/randomness.md
7. NVIDIA Isaac Sim 6.0.0, Replicator snippets (`rep.set_global_seed`). https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_isaac_snippets.html
8. NVIDIA, *Software License Agreement* (§8.9). https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
9. NVIDIA, *TensorRT for RTX Software License Agreement* (§2.13). https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
10. GitHub Docs, *About releases*. https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
