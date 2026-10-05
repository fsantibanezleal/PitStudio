# Models

> Model cards for every model PitStudio trains or runs, plus the shared training recipes and the export, parity and
> acceleration rules. · Part of: [Docs home](../README.md) · Related: [Methods](../methods/README.md) ·
> [Data contract](../data-contract/README.md) · [Pipeline stages](../pipelines/pipeline-stages.md)

PitStudio trains small, licence-checked models on one 16 GB laptop GPU and ships the ones that fit the web budgets to
the browser through ONNX Runtime Web. Every learned model is compared with a classical baseline on held-out data, and
every "better than" claim follows one pre-registered rule.

> **Status: nothing has been trained yet.** Each card states what will be reported and its acceptance criterion, fixed
> before training. Results are produced in the data-and-models phase.

![ONNX export and parity gates](../assets/diagrams/model-export-parity.svg)

*From checkpoint to web model: export with a pinned opset and IR version, two parity gates, then a measured lane.*

## Map of this section

| Card | Task | Cases · methods | Environment | Budget (estimate) | Web lane · file | Status |
|---|---|---|---|---|---|---|
| [D-FINE-N / D-FINE-S](d-fine.md) | equipment, people and boulder detection | B2 · M10 | `pipeline/` | 12–25 GPU-h, 8–11 GB | N fp16 8 MB live; S int8 10 MB live; S fp32 40 MB precompute | not yet trained |
| [RF-DETR-Seg-N](rf-detr-seg.md) | instance segmentation | B2 · M10 | `pipeline/` | 8–16 GPU-h, 10–13 GB | precompute only (61 MB fp16) | not yet trained |
| [U-Net fragmentation](unet-fragmentation.md) | fragment masks → PSD | D1 · M11 | `pipeline/` | 2–4 GPU-h, 5–7 GB | int8 5–15 MB live | not yet trained |
| [GNS granular surrogate](gns-granular.md) | 2-D granular flow | A3 · M8 | `pipeline/` | 4–15 GPU-h, 2–6 GB | ~3 MB live | not yet trained |
| [FNO fields](fno-fields.md) | tailings and dust fields | C2, C3 · M15 | `pipeline/` | 0.5–2 GPU-h | ~5 MB live | not yet trained |
| [Dispatch policies](dispatch-policies.md) | PPO + attention fleet dispatch | A1 · M4, M5 | `pipeline/` | 1–5 GPU-h, 2–4 GB | < 2 MB live | not yet trained |
| [Isaac Lab policies](isaac-lab-policies.md) | haul-truck ramp driving; excavator digging | A2, A3 · M21 | `studio/isaaclab/` | 1–4 h + 2–8 h (+ 2–3 h optional) | < 1 MB live (TS twins) | not yet trained |
| [Slope forecasters](slope-forecasters.md) | time-of-failure forecasting | C1 · M14 | `pipeline/` | < 2 GPU-h | < 4 MB; ~18 MB live | not yet trained |
| [Mine-to-mill meta-model](mine-to-mill-meta-model.md) | kWh/t and t/h | D2 · M17 | `pipeline/` | minutes | < 1 MB live | not yet trained |
| [DEM calibration](dem-calibration.md) | friction from angle of repose | A3 · M9 | `studio/` | 0.2–2 h each | baked results | not yet run |
| [Cosmos Reason 2](cosmos-reason-2.md) | VLM hazard questions, plausibility, captions (inference only) | B1, B2 · M22 | `studio/reason/` | 8–16 GPU-h | precomputed text, display-only | not yet run |
| [Training recipes](training-recipes.md) | budgets, schedule, precision, decision rule | all | — | ≈ 55–150 GPU-h in total | — | — |
| [Export, parity and acceleration](export-parity-acceleration.md) | ONNX export, parity layers, TensorRT engines, the Acceleration tab | all learned | `pipeline/`, `pipeline/accel/` | 4–7 GPU-h | tables only | — |

## How to read a card

Each card follows the model-card practice of stating intended use, out-of-scope use, data, evaluation and limits
next to the model itself [1]. PitStudio adds four fields that its contracts check:

- **Budget (estimate):** GPU-hours and VRAM from the plan. The runner's `studio bench` probe measures each model before
  any long run; the measured value replaces the estimate in the card.
- **Export and web lane:** ONNX opset (17–19), IR version (pinned to 10), the parity gates, and the lane the measured
  gate assigns (LIVE only for files ≤ 25 MB that meet the interaction budget).
- **Pre-registered acceptance criteria:** copied from the plan, calibrated in `specs/000-foundation/thresholds.yaml`
  before training, never after.
- **Licence of weights:** Apache-2.0 with attribution when every input permits it, otherwise the most restrictive input
  terms ([Sources and licences](../data-contract/sources-and-licences.md)).

## The decision rule

A result is called **better** than another only if the paired 95 % confidence interval of the difference excludes 0.
Otherwise the docs and the web app say **"no significant difference"**. The pairs are defined per model (seeds, folds,
seeded events, scenes) in [Training recipes](training-recipes.md). Two cases never get a "better than" claim at all:
the single real slope-failure event (n = 1, descriptive only) and anything a licence or the honesty rule keeps from
being validated against real data.

## In PitStudio

- **Code paths:** training, inference, evaluation and export in `pipeline/` (`s30_train` → `s40_infer` →
  `s50_evaluate` → `s60_export`); acceleration in `pipeline/accel/` (`s62_accel` → `s64_bench`); Isaac Lab in
  `studio/isaaclab/`; Cosmos in `studio/reason/`.
- **Artefacts:** small final ONNX files with SHA-256 in `models/onnx/`; machine-readable cards with their accepted run
  manifests in `models/cards/`; checkpoints are git-ignored; larger files are release assets.
- **Web:** live models run in ONNX Runtime Web (WebGPU, falling back to WebAssembly); precompute-only models contribute
  their outputs as REPLAY artefacts.

## References

1. Mitchell et al. (2019), *Model Cards for Model Reporting*, arXiv 1810.03993. https://arxiv.org/abs/1810.03993
