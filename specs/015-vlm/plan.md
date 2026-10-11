# Plan 015 — Vision-language reasoning (M22)
Spec: ./spec.md

## Summary

The feature has five parts:

- **Provenance and runtime** (`pipeline/src/pitstudio_pipeline/reason/runtime.py`, with configuration in
  `studio/reason/`):
  - pin verification of llama.cpp b11381 and its `cudart`, the model revisions and the files (FR-015-01 to FR-015-04);
  - own GGUF conversion (FR-015-05);
  - gated-terms degradation and token hygiene (FR-015-07, FR-015-08);
  - the loopback `llama-server` driver and its failure policy (FR-015-11, FR-015-12);
  - the transformers BF16 reference (FR-015-09, FR-015-10).
- **Bench and gate**: `st59_reason_bench` (FR-015-13 to FR-015-15).
- **Task builders and truth** (`src/pitstudio/reason/`, Python 3.14, NumPy, CI-tested):
  - the task-A ground truth and query builder (FR-015-16 to FR-015-23);
  - the detector rule (FR-015-29);
  - the task-B pair builder and corruption detectors (FR-015-33 to FR-015-35);
  - the caption scorer (FR-015-38).
- **Scoring** (`src/pitstudio/reason/stats.py`, `parse.py`; FR-015-24 to FR-015-28, FR-015-30 to FR-015-32,
  FR-015-36, FR-015-37):
  - parser, balanced accuracy, bootstrap intervals, AUROC;
  - exact McNemar, Wilson, the 2AFC pair statistic.
- **Publication**: records, notices, the headline-KPI exclusion and display-only guards (FR-015-39 to FR-015-45) in
  `studio publish`, CI and `web/`.

## Technical context

Runtimes and inputs:
- llama.cpp b11381, a portable Windows CUDA 13.4 build plus its matching `cudart` archive (MIT), external. It is
  verified by SHA-256 and unpacked outside the repository under the data folder set by `PITSTUDIO_MODELS`.
- `pipeline/` (Python 3.14): torch 2.14.1 cu130. To be resolved and locked before feature code (T-015-002):
  transformers (with Qwen3-VL support), `gguf` (for `convert_hf_to_gguf.py` at tag b11381), `huggingface-hub`, SciPy
  and statsmodels (test reference only).
- The root package (Python 3.14, NumPy) holds the truth, builders and statistics.
- Inputs from other specs: SDG frames and frame states (spec 009, DC-015-01); D-FINE detections (spec 009); granular
  runs and renders (spec 005, with renders from `st52_rtx_render`).

Targets: the reference laptop GPU for inference (`gpu0.compute`); CI for every builder, scorer, guard and contract,
with a fake hub, fake tools and a fake server.

## Constitution check

| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | The real model at its official revision; exact ground truth from our scenes; synthetic-only scope labelled; optional real probe "not measured" when absent |
| Spec before code | yes | Question definitions, ambiguity bands, arms, decoding and tests fixed before any run (FR-015-16 to FR-015-31) |
| Acceptance-test-first | yes | All tasks `[red]`/`[green]`; plan §7 criteria as SC-015-01 to SC-015-04 |
| Independent oracles | yes | Analytical scene fixtures for ground truth; reference implementations (`scipy.stats.binomtest`, `statsmodels` `mcnemar`, `proportion_confint`, `sklearn.metrics.roc_auc_score`, `scipy.stats.bootstrap`); hand calculations (spec §4); the published CHAIR definition |
| Determinism and tolerances | yes | Greedy decoding with fixed seeds; conversion determinism (P-015-12); tolerances justified in spec §7 |
| Neutral contracts | yes | DC-015-01 to DC-015-06 new (T-015-001); DC-015-07, DC-015-08 reused |
| Static delivery | yes | Precomputed text only; the model never runs in the browser; "answers unavailable" fallback (FR-015-43) |
| Honesty | yes | "not run" paths (FR-015-07, FR-015-10), "rejected" Q8_0 path (FR-015-15), wrong answers shown, never headline (FR-015-42), "frame-list approximation" label |
| Licence hygiene | yes | Weights and GGUF never redistributed (FR-015-06); "Built on NVIDIA Cosmos" (FR-015-41); display-only class; captions never used for training (FR-015-39); no guardrail bypass (FR-015-44) |
| Simplicity | yes | One external runtime driven over loopback; one shared statistics module; no serving framework |

## Design

![Cosmos evaluation design: exact answers from the USD stage, the same renders for every arm, paired scoring](../../docs/assets/diagrams/cosmos-evaluation-design.svg)

| Component | Location | Requirements |
|---|---|---|
| Pin file and verifier | `studio/reason/pins.json`; `pitstudio_pipeline.reason.runtime` | FR-015-01 to FR-015-04 |
| Hub client (gated access, token redaction) | `pitstudio_pipeline.reason.hub` | FR-015-03, FR-015-04, FR-015-07, FR-015-08 |
| GGUF conversion | `pitstudio_pipeline.reason.convert` (calls `convert_hf_to_gguf.py` at tag b11381 and `llama-quantize`) | FR-015-05, P-015-12 |
| Server driver (loopback, job object, retries) | `pitstudio_pipeline.reason.server` | FR-015-11, FR-015-12 |
| BF16 reference | `pitstudio_pipeline.reason.bf16` | FR-015-09, FR-015-10 |
| Bench and gate | stage `st59_reason_bench` | FR-015-13 to FR-015-15 |
| Ground truth, query builder | `src/pitstudio/reason/truth.py`, `queries.py` | FR-015-16 to FR-015-23, P-015-08 |
| Prompts, configuration validation | `studio/reason/prompts/*.txt` (hashed); `src/pitstudio/reason/config.py` | FR-015-24, FR-015-25, FR-015-44 |
| Parser | `src/pitstudio/reason/parse.py` | FR-015-26, FR-015-27, P-015-11 |
| Arms runner | stage `st59a_vqa` | FR-015-28 |
| Detector rule | `src/pitstudio/reason/detector_rule.py` | FR-015-29, P-015-09 |
| Statistics | `src/pitstudio/reason/stats.py` | FR-015-30 to FR-015-32, FR-015-37, P-015-01 to P-015-06 |
| Plausibility pairs and corruption detectors | `src/pitstudio/reason/plausibility.py`; stage `st59b_plausibility` | FR-015-33 to FR-015-37, P-015-10 |
| Caption scorer | `src/pitstudio/reason/captions.py`; stage `st59c_captions` | FR-015-38, P-015-07 |
| Publication (records, sampling, guards) | `studio publish` hook; CI checks | FR-015-39 to FR-015-42, FR-015-45 |
| Web panels | `web/src/features/reason/` | FR-015-41, FR-015-43 |
| Probe `llamacpp` (added to the bench registry, run from the `pipeline` project) | `studio/bench/probe_llamacpp.py` | DC-015-08, FR-015-13 |

**Data flow.** `st55_sdg` frames and frame states → query builder → `st59_reason_bench` (footprint and gate) →
`st59a_vqa`; physics runs and renders → pair builder → `st59b_plausibility`; frames and scene graphs →
`st59c_captions` → scoring → `studio publish` (records + metrics, display-only) → web.

## Test strategy

| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-015-01, FR-015-02 | unit | SHA-256 recomputed with `hashlib` on fixture files; tampered-file corpus | pytest |
| FR-015-03, FR-015-04 | unit | fake hub with recorded LFS hashes; hostile repository and revision corpus | pytest |
| FR-015-05 | unit + local | fake tools write deterministic files; real conversion run twice locally (P-015-12) | pytest |
| FR-015-06 | unit | git-tracked file list + publish-list scan with planted `.gguf` / `.safetensors` fixtures | pytest |
| FR-015-07 | unit + E2E | fake hub returning 401 / 403 / no token → arm states; web "not run" | pytest + Playwright |
| FR-015-08 | unit | canary token search over every output file | pytest |
| FR-015-09, FR-015-10 | contract + gpu | lock contains transformers; fake loader failure → states; local BF16 load | pytest |
| FR-015-11 | unit | fake server: bind address 127.0.0.1, ephemeral port, termination; socket audit hook rejects non-loopback | pytest |
| FR-015-12 | unit | fake process exits, timeouts, OOM; error-rate threshold at 2 % | pytest |
| FR-015-13 | contract + gpu | metrics schema; label present; local bench | pytest |
| FR-015-14, FR-015-15 | unit + gpu | hand calculation (475/500 pass, 474/500 fail; Wilson for 485/500 = [0.9511, 0.9817]) | pytest + statsmodels |
| FR-015-16 | unit | counting on a synthetic frame pool (balance, ≤ 1 per frame and type, ≥ 20 % per condition) | pytest |
| FR-015-17 to FR-015-22 | unit | analytical scene fixtures at each threshold and band edge (e.g. person at 26.9 / 27.0 / 33.0 / 33.1 m) | pytest |
| FR-015-23 | unit | hostile frame-state corpus | pytest + Hypothesis |
| FR-015-24, FR-015-25 | unit | configuration fixtures; hostile corpus | pytest |
| FR-015-26, FR-015-27 | unit | table of hand-written outputs and expected labels; Hypothesis fuzz (P-015-11) | pytest + Hypothesis |
| FR-015-28 | unit | arm plan over fixture queries (same query ids for every arm) | pytest |
| FR-015-29 | unit | analytical camera with known pose and flat terrain (P-015-09) | pytest |
| FR-015-30 | unit | reference implementations `sklearn.metrics.balanced_accuracy_score`, `f1_score`, `roc_auc_score`, `scipy.stats.bootstrap` | pytest |
| FR-015-31 | unit | `scipy.stats.binomtest`, `statsmodels.stats.contingency_tables.mcnemar(exact=True)`; worked example b = 60, c = 35 | pytest |
| FR-015-32 | unit | hostile inputs | pytest + Hypothesis |
| FR-015-33 | unit | counting on the pair index (16 or 17 per corruption, exactly one corruption) | pytest |
| FR-015-34, FR-015-35 | unit | synthetic trajectories with known physics (free fall under 0.3 g, reversed frames, frozen subsets, overlaps) | pytest |
| FR-015-36 | unit | request plan per pair (both orders + single clips; labels) | pytest |
| FR-015-37 | unit | hand calculation on fixture tables; `scipy.stats.ttest_1samp` | pytest |
| FR-015-38 | unit | the published CHAIR definition (spec §7) on hand-written captions | pytest |
| FR-015-46 | unit | hostile captions (empty, no class, G = ∅) and a duplicated-synonym vocabulary | pytest + Hypothesis |
| FR-015-47 | unit | hostile query sets (bad hash, unknown frame) and detector inputs (no calibration, NaN or out-of-image boxes) | pytest + Hypothesis |
| FR-015-39 | contract | manifest fixtures with a Cosmos-produced input in `s30_train` | pytest |
| FR-015-40 | contract | schema; sampling independence (selection seed fixed, no correctness field used) | pytest |
| FR-015-41, FR-015-42 | E2E + contract | DOM notices; KPI registry scan | Playwright + pytest |
| FR-015-43 | web unit | corrupted record fixtures | Vitest |
| FR-015-44 | unit | hash check of committed prompts; phrase list of bypass instructions absent | pytest |
| FR-015-45 | unit | Cohen's κ by hand calculation on a 2 × 2 table; `sklearn.metrics.cohen_kappa_score` | pytest |
| P-015-01 to P-015-07 | metamorphic | relations stated in the spec | Hypothesis (≥ 200 examples) |
| P-015-08, P-015-09 | metamorphic | analytical scene relations | Hypothesis |
| P-015-10 | metamorphic | involution and identity relations | Hypothesis |
| P-015-11 | property | invariants | Hypothesis |
| P-015-12 | local | equality of SHA-256 | pytest (local) |
| NFR-015-01, NFR-015-02 | gpu (local) | NVML telemetry; projection arithmetic | pytest |
| NFR-015-03, NFR-015-04 | CI / unit | byte sizes; error counts | budget check, pytest |
| SC-015-01 to SC-015-06 | pipeline | tables produced on the real runs (data-and-models phase) by the code verified above | pytest (`tests/pipeline`) |

## Risks and complexity tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Exact McNemar for every b + c | The documentation disagrees on the χ² variant; the exact test is valid at every sample size | Choosing χ² or χ²_cc after seeing the data would break pre-registration |
| Ambiguity bands that drop borderline frames | Ground truth must be decidable from pixels | Keeping borderline frames measures label noise, not the model |
| A stratified record sample instead of all records on the web | Text budget (< 1 MB per case) with reasoning outputs up to 4,096 tokens | Publishing everything breaks the budget; publishing only right answers breaks honesty |
| Driving `llama-server` over loopback rather than the CLI per query | One model load per stage; token log-probabilities for AUROC | Per-query CLI reloads 3 GB of weights each time |

Open risks: the gated terms may not be accepted ("not run" path); fit on 16 GB is unmeasured (bench first); answers
near chance on dust and night are an expected, reported outcome; the llama.cpp converter may need a newer `gguf` than
the pinned tag (then the pin moves deliberately, recorded in the pins file).
