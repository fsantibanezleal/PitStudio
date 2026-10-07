# Spec 015 — Vision-language reasoning (M22): Cosmos Reason 2 scored against exact scene truth
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Vision-language models promise "ask the camera what is wrong", but the evidence for safety use is thin. PitStudio has
something rare: exact ground truth. Every hazard question about a rendered pit frame has an answer computable from the
scene, every plausibility pair has a known corruption, and every synthetic frame has a scene graph. This feature
measures **Cosmos Reason 2 (2B)** zero-shot on three tasks:

- **A.** About 6,500 hazard questions of six types with exact answers from the USD scene.
- **B.** 100 physical-plausibility pairs of PitStudio's own granular simulations, each with exactly one controlled
  corruption, judged by two-alternative forced choice.
- **C.** About 2,000 captions of synthetic frames, scored for hallucination.

The model runs locally through llama.cpp b11381 (CUDA 13.4 build) on PitStudio's **own GGUF Q8_0 conversion** of the
official revision. The transformers BF16 weights are the quality reference. Qwen3-VL-2B-Instruct (Apache-2.0, the base
model) is the control, and the detector + geometric rule and a constant class are baselines. Acceptance:

- Q8_0 versus BF16 agreement ≥ 95 % on binary questions;
- per-type balanced accuracy with confidence intervals;
- "Cosmos beats Qwen base" only if McNemar's p < 0.05.

The result is **never a headline KPI**. Outputs are display-only text with "Built on NVIDIA Cosmos". The gated
weights need the maintainer's acceptance of the Hugging Face terms and a read token; without them, every Cosmos arm
shows "not run".

**Who benefits:** data/AI practitioners and safety engineers asking what a small VLM gets right about pit safety;
reviewers who need paired, pre-registered comparisons.

**Out of scope:**
- fine-tuning, distillation or training on Cosmos outputs;
- using captions to curate training data;
- running the model in the browser;
- publishing weights or GGUF files;
- vLLM, NIM or TensorRT-LLM;
- Cosmos Predict/Transfer (evaluated, not adopted);
- the SDG renders themselves (spec 009);
- the granular simulations (spec 005);
- the detector (spec 009).

## 2. User stories

| ID | Priority | Story | Independent test |
|---|---|---|---|
| US-015-1 | P1 | As a safety engineer, I want per-type accuracy of a 2B VLM on pit-hazard questions whose answers are exact, next to its base model and a detector rule, so that I can see where it helps and where it fails (dust, night). | The scoring module reproduces hand-calculated balanced accuracy, intervals and McNemar verdicts on synthetic answer tables. |
| US-015-2 | P1 | As a reviewer, I want the quantised model checked against the BF16 original before any result counts, so that quantisation cannot silently change the answers. | The gate fixture with 475/500 agreements passes and one with 474/500 fails. |
| US-015-3 | P1 | As the maintainer, I want the lane to run only on pinned binaries and weights of verified provenance, to degrade to "not run" without the gated terms, and never to publish weights, tokens or headline claims, so that licence and provenance traps cannot reach the site. | Hostile pins, a missing token and a planted GGUF in the tree are each refused. |
| US-015-4 | P2 | As a simulation developer, I want to know whether a VLM can tell a physically plausible granular clip from one with a single known corruption, compared with a physics check, so that I learn how much is visible from pixels alone. | Synthetic answer tables give the hand-calculated pair accuracy and interval; an always-first answerer scores exactly 0.5. |
| US-015-5 | P2 | As a dataset curator, I want caption hallucination and recall measured against the scene graph, with template captions as the baseline, so that caption quality is known before any caption is shown. | Template captions score CHAIR_i = 0 and recall = 1 exactly. |

## 3. Functional requirements (EARS)

### 3.1 Runtime, weights and provenance

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-015-01 | Ubiquitous | The reason lane shall run llama.cpp build b11381 (Windows CUDA 13.4 x64 archive and its matching `cudart` archive), unpacked outside the repository, after verifying both archives and every executable it invokes against the SHA-256 values in `studio/reason/pins.json` (`contracts/reason-pins.schema.json`). | unit (fake binary folder) |
| FR-015-02 | Unwanted | If a pinned archive or executable is missing or its SHA-256 differs from the pin, or the pin file is invalid, then every `st59_*` stage shall exit with code 2 before starting any process, naming the file. | unit (hostile) |
| FR-015-03 | Ubiquitous | The Cosmos arm shall use weights only from `nvidia/Cosmos-Reason2-2B` at the pinned full 40-hex revision beginning `9ce19a1`, and the control only from `Qwen/Qwen3-VL-2B-Instruct` at its pinned revision, each downloaded file verified against the SHA-256 recorded in the pin file. | unit (fake hub) |
| FR-015-04 | Unwanted | If a configuration names any other repository (including third-party GGUF conversions and modified or guardrail-removed variants), a revision other than the pinned one, or a downloaded file whose SHA-256 differs from its pin, then the lane shall refuse to load it, exit with code 2 and name the repository and file. | unit (hostile) |
| FR-015-05 | Event | When the Cosmos weights are converted, the lane shall run `convert_hf_to_gguf.py` from the llama.cpp source at tag b11381 to produce an F16 text model and an F16 vision projector (`mmproj`), then `llama-quantize` b11381 to produce Q8_0, and record the SHA-256 of every output; a second conversion from the same inputs shall produce identical SHA-256 values. | unit (fake tools) + local |
| FR-015-06 | Ubiquitous | No model weight or conversion — files with the extensions `.gguf`, `.safetensors`, `.pt`, `.pth`, `.bin` (weights), or a Hugging Face cache folder — shall be tracked in git, listed in a release-asset upload list or copied into the Pages artefact; artefacts of licence class `reference-only` shall never appear in a publish list. | unit (repository and publish-list scan) |
| FR-015-07 | Unwanted | If no Hugging Face read token is available, or the hub answers 401 or 403 for the Cosmos repository, then every Cosmos arm shall be recorded "not run" with the reason "gated terms not accepted or token missing"; tasks A–C shall still run on the Qwen control and the baselines; and the Cosmos panels and the Cosmos tool page shall show "not run". | unit (fake hub) + E2E |
| FR-015-08 | Unwanted | If the Hugging Face token value would appear in a log line, an exception message, a manifest or a record, then the lane shall write `<redacted>` in its place; a run with a canary token shall leave zero occurrences of the canary in every output file. | unit |
| FR-015-09 | Ubiquitous | The BF16 reference shall run the official revision with transformers in BF16 in the `pipeline/` environment (resolved and locked before feature code), and shall be used for the agreement gate (FR-015-14) and for native-video inputs of task B. | contract + gpu (local) |
| FR-015-10 | Unwanted | If the BF16 reference cannot load or run on the reference GPU, then the BF16 arm shall be recorded "not run" with the measured reason, and every Cosmos Q8_0 result shall be recorded "not run (agreement gate not evaluable)". | unit (fake) |
| FR-015-11 | Ubiquitous | The lane shall drive llama.cpp as `llama-server` bound to 127.0.0.1 on an ephemeral port with `--mmproj`, started inside the stage's job object and terminated at stage end; no `st59_*` stage shall open a network connection other than to that loopback server and, during downloads only, to the Hugging Face hub. | unit (fake server) |
| FR-015-12 | Unwanted | If the llama.cpp process exits with a non-zero code, a query exceeds 120 s, or the process reports out-of-memory, then the lane shall restart the server and retry that query once, then record it as `error` (excluded from scoring, counted in the error rate); a stage with more than 2 % errored queries shall fail. | unit (fake process) |

### 3.2 Footprint bench and quantisation gate

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-015-13 | Event | When `st59_reason_bench` runs, it shall measure on 200 mixed queries (single 1280 × 720 images and 8-frame 640 × 360 sequences) the device-peak VRAM, prefill and decode tokens/s and wall time per query for the Q8_0 and BF16 paths, and publish them with `performance: public` and the label "our hardware, not a comparative benchmark". | contract + gpu (local) |
| FR-015-14 | Ubiquitous | The agreement gate shall compare Q8_0 and BF16 on a fixed subset of 500 binary task-A queries (100 per binary type, 50 yes and 50 no, conditions stratified) with greedy decoding, reasoning off and identical prompts and image preprocessing; agreement a is the fraction of queries with identical normalised answers; the gate passes if and only if a ≥ 0.95 (point estimate), and its Wilson 95 % interval is reported. | unit + gpu (local) |
| FR-015-15 | Unwanted | If a < 0.95, then every Cosmos result shall come from the BF16 path, and the Q8_0 path shall be published only as "rejected: agreement a = … < 0.95" with no task metric. | unit |

### 3.3 Task A — hazard questions with exact ground truth

Ground truth comes from the per-frame scene state (DC-015-01): world transforms in metres (honouring `metersPerUnit`
and `upAxis`), classes, footprints, visible-pixel counts, depth and dust-field references, written by the SDG stage of
spec 009.

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-015-16 | Ubiquitous | The task-A query builder shall draw frames of the B2 scenes (day, night, dust, rain × haul road, bench, loading area) and produce 1,080 queries per type (6,480 in total), at most one per (frame, type); types 1, 2, 4, 5 and 6 with exactly 540 "yes" and 540 "no"; type 3 with exactly 270 per class {0, 1, 2, ≥ 3}; every condition with ≥ 20 % of the queries of each type; with a fixed seed. | unit |
| FR-015-17 | Ubiquitous | Type 1 ("Is a person within 30 m of a haul truck?") shall be "yes" if and only if a visible person (≥ 100 visible px) is within 30 m horizontally of the nearest point of a visible haul truck's oriented footprint (≥ 400 visible px); frames with any such distance in [27, 33] m, or with a person or truck inside the camera frustum but below its visibility threshold, shall not be asked. | unit (analytical fixtures) |
| FR-015-18 | Ubiquitous | Type 2 ("Is a berm present along the bench edge in view?") shall be "yes" if and only if the scene's berm design-variant flag is on for the bench edge in view; it shall be asked only when that bench edge has ≥ 2,000 visible px. | unit |
| FR-015-19 | Ubiquitous | Type 3 ("How many haul trucks are visible?") shall be the count of haul trucks with ≥ 400 visible px (1280 × 720) in the classes {0, 1, 2, ≥ 3}; frames with any truck in [100, 400) visible px shall not be asked. | unit |
| FR-015-20 | Ubiquitous | Type 4 ("Is visibility reduced by dust?") shall be "yes" if the median one-way optical depth along a 16 × 9 grid of camera rays (to their ground-truth distance, or to the dust-field box exit for sky rays) is ≥ 0.3216 (T₁ ≤ 0.725, the onset value of spec 013), and "no" if it is ≤ 0.1054 (T₁ ≥ 0.90); frames in between shall not be asked. | unit |
| FR-015-21 | Ubiquitous | Type 5 ("Is a light vehicle in the truck's blind zone?") shall be "yes" if and only if a light vehicle's footprint centre lies inside the blind-zone polygon of the truck asset (truck body frame); it shall be asked only for frames with exactly one visible haul truck, whose light vehicles within 50 m are all visible (≥ 100 px), and not when a centre lies within 1 m of the polygon boundary. | unit |
| FR-015-22 | Ubiquitous | Type 6 ("Is the truck on a ramp steeper than 10 %?") shall be "yes" if and only if the road grade under the footprint centre of the single visible haul truck, from the terrain along its heading over ±5 m, exceeds 10 %; frames with a grade in [9 %, 11 %] shall not be asked. | unit |
| FR-015-23 | Unwanted | If a frame state is invalid against `contracts/frame-state.schema.json` — missing `metersPerUnit` or `upAxis`, a non-finite transform, an unknown class label, a duplicated prim id, an empty object list or a SHA-256 mismatch with its frame — then the builder shall reject that frame, list it with the reason, and generate no query from it. | unit (hostile) |
| FR-015-24 | Ubiquitous | Every arm shall receive the committed, hashed prompt template of each question type, asking for the answer inside `<answer>…</answer>`, with greedy decoding (temperature 0, top-k 1), a fixed seed, images at native resolution, a maximum of 64 new tokens with reasoning off, and — on a stratified 300-query subset only — a reasoning-on run with a maximum of 4,096 new tokens. | unit (configuration) |
| FR-015-25 | Unwanted | If a lane configuration names an unknown arm, task or question type, sets a temperature other than 0 for a scored arm, a non-positive token limit, an image side above 4,096 px, or an input path outside the stage's declared inputs (including `..` traversal and URLs), then the stage shall exit with code 2 and name the field. | unit (hostile) |
| FR-015-26 | Ubiquitous | The answer parser shall read only the text inside the last `<answer>…</answer>` pair (or, with reasoning off and no tags, the first word), case-, whitespace- and punctuation-insensitive, mapping "yes"/"no" and the counts 0–3 (digits or words, with "3 or more", "three or more" and larger numbers mapped to ≥ 3), and shall return exactly one of {yes, no, 0, 1, 2, ≥ 3, unparseable}. | unit |
| FR-015-27 | Unwanted | If an output is empty, has no parseable answer, or holds conflicting answers inside one answer pair, then the parser shall return `unparseable`; such answers are scored as incorrect and their rate is reported per arm. | unit (hostile fuzz) |
| FR-015-28 | Ubiquitous | Task A shall run these arms on the same queries: Cosmos Q8_0 (reasoning off; reasoning on for the 300-query subset), Cosmos BF16 (the 500-query gate subset), Qwen3-VL-2B-Instruct (same prompts and preprocessing), the detector + geometric rule (types 1, 3 and 5; "not applicable" for 2, 4 and 6), and a constant arm ("no" for binary types, "1" for type 3). | unit |
| FR-015-29 | Ubiquitous | The detector + geometric rule shall use the D-FINE detections of spec 009 with score ≥ 0.5, the known camera calibration and the site terrain model: type 1 by ground-plane back-projection of box bottom-centres and the 30 m test; type 3 by counting truck boxes; type 5 by projecting the light-vehicle box into the truck's body frame and testing the polygon. | unit (analytical camera fixtures) |
| FR-015-30 | Ubiquitous | For every arm and type the scoring shall report balanced accuracy (mean per-class recall), F1 (macro-F1 for type 3), their 95 % intervals by a stratified percentile bootstrap (10,000 resamples within each true class, fixed seed), the unparseable rate, a breakdown by condition, and — for binary types and the Cosmos Q8_0 and Qwen arms — the AUROC of s = log p(yes) − log p(no) at the first answer token (from the top-20 token log-probabilities; an absent token takes the 20th log-probability). | unit (reference implementation) |
| FR-015-31 | Ubiquitous | For each type and for all binary queries pooled, the comparison of Cosmos with Qwen shall use the paired correctness of the two arms: b = queries Cosmos answers correctly and Qwen does not, c = the reverse; "Cosmos beats Qwen base" shall be stated only if b > c and the exact two-sided binomial McNemar test gives p < 0.05, otherwise "no significant difference"; b, c, p and, when b + c ≥ 25, the continuity-corrected χ² shall be reported. | unit (reference implementation) |
| FR-015-32 | Unwanted | If a scoring function receives arrays of unequal length, n = 0, a count k > n or k < 0, a non-finite score, or a label outside its type's classes, then it shall raise `ValueError`. | unit (hostile) |

### 3.4 Task B — physical-plausibility critic

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-015-33 | Ubiquitous | The task-B set shall hold 100 pairs of 5–8 s clips from spec 005's granular runs (muck-pile formation, truck dump, bench collapse); each pair holds a calibrated clip and the same scene with exactly one corruption from {gravity × 0.3, friction set to 0, mass injection, time reversal, interpenetration, frozen particles}, with 16 or 17 pairs per corruption, listed in `contracts/plausibility-pairs.schema.json`. | unit |
| FR-015-34 | Ubiquitous | Every corrupted clip shall be confirmed on its simulation state by the detector of its own corruption — fitted free-fall acceleration within ±5 % of 0.3 g; repose angle < 5°; total particle mass increase ≥ 5 % with no inflow boundary; frame order exactly reversed; ≥ 10 % of contacts with overlap > 50 % of the radius sum for ≥ 1 s; ≥ 5 % of particles with zero displacement for ≥ 1 s while neighbours within two radii move — and every calibrated clip shall trigger none of the six detectors. | unit (synthetic trajectories) |
| FR-015-35 | Unwanted | If a pair fails FR-015-34, declares zero or more than one corruption, or its clips differ in scene, camera, duration or frame count, then it shall be excluded and replaced by a regenerated pair of the same corruption before any query. | unit (hostile) |
| FR-015-36 | Ubiquitous | Each pair shall be asked as a two-alternative forced choice ("which clip is physically plausible?") in both orders and as a single-clip yes/no question for each clip; the BF16 path receives native video at 4 fps; the Q8_0 path receives frames sampled at 4 fps as an ordered image list, labelled "frame-list approximation". | unit |
| FR-015-37 | Ubiquitous | Task-B scoring shall give each pair the score s_i = fraction of its two orders answered correctly, the accuracy s̄, its 95 % interval s̄ ± t₀.₉₇₅,₉₉ · sd(s)/√100, the verdict "above chance" only if the lower bound exceeds 0.5, the detection rate per corruption, the single-clip AUROC, the position-bias index (fraction of "first clip" answers) and the physics-check baseline (repose angle and mass balance from the simulation state) on the same pairs. | unit |

### 3.5 Task C — captions scored for hallucination

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-015-38 | Ubiquitous | Task C shall caption about 2,000 synthetic frames with one committed prompt, extract the mentioned classes M of each caption with the committed vocabulary map (class → synonyms; lower-cased, singularised tokens; set semantics per caption), take as G the classes with ≥ 400 visible px in the scene graph, and report CHAIR_i = |M \ G| / |M|, CHAIR_s = sentences with a hallucinated class / all sentences, object recall |M ∩ G| / |G| and the balanced accuracy of dust, night and rain mentions against the scene conditions, for every arm and for the template-caption baseline. | unit |
| FR-015-39 | Unwanted | If a manifest of a data, training or curation stage (`s05_synthesize` to `s30_train`) lists an input produced by the Cosmos tool, then CI shall fail (captions are display-only). | contract (CI) |
| FR-015-46 | Unwanted | If a caption is empty or mentions no class of the vocabulary (|M| = 0), then CHAIR_i shall be undefined for it and the caption shall be excluded from CHAIR_i and counted in a reported "no object mentioned" rate; if a frame's scene graph has G = ∅, it shall be excluded from recall; and if the vocabulary map assigns one synonym to two classes, the scorer shall refuse to start. | unit (hostile) |
| FR-015-47 | Unwanted | If a query set fails `contracts/vlm-queries.schema.json` or its SHA-256, references a frame absent from the frame states, or the detector rule receives a missing camera calibration, a non-finite box or a box outside the image, then the stage or rule shall refuse that input (the rule answers `not applicable` for that query and the count is reported) and never guess an answer. | unit (hostile) |

### 3.6 Publication and honesty

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-015-40 | Ubiquitous | Each published record (`contracts/vlm-record.schema.json`) shall hold the frame asset ids, the question, the full model output, the parsed answer, the ground truth, a correct/incorrect flag and its provenance — model id and full revision, quantisation, GGUF SHA-256, llama.cpp build and archive SHA-256, sampling parameters and seed, date, GPU and driver; Cosmos records shall carry licence class `display-only`; the published records shall be a stratified random sample (by type and condition, fixed seed, selection independent of correctness), with the full set kept locally. | contract |
| FR-015-41 | Ubiquitous | Every web panel, card, chart and results table that shows a Cosmos output or metric shall show "Built on NVIDIA Cosmos" and "Zero-shot 2B VLM; not a safety system.", and shall show wrong answers as well as right ones. | E2E |
| FR-015-42 | Ubiquitous | No metric produced by the Cosmos tool shall be in the headline KPI set (Explore KPIs and case KPI tiles); a CI check over the KPI registry and the manifests shall fail otherwise. | contract (CI) + E2E |
| FR-015-43 | Unwanted | If a baked record file fails its SHA-256 or its schema, then the panel shall show "answers unavailable" and render none of its text. | web unit (hostile) |
| FR-015-44 | Ubiquitous | The lane shall send only the committed system prompt and prompt templates (hashes checked at stage start), none of which asks the model to ignore or bypass its safety behaviour. | unit |
| FR-015-45 | Optional | Where the optional real probe exists (≤ 200 licence-clean images, two labellers), the applicable task-A types shall be scored on it and reported in aggregate only, with Cohen's κ between the labellers; otherwise the real-image result shall read "not measured". | unit |

## 4. Correctness properties

Numerical cores and their metamorphic relations (MR): scoring statistics (P-015-01 to P-015-06), caption scoring
(P-015-07), ground truth (P-015-08, P-015-09), corruption generator (P-015-10), parser (P-015-11), conversion
(P-015-12).

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-015-01 | Balanced-accuracy MRs: (MR1) duplicating every query leaves BA unchanged; (MR2) swapping class labels in both truth and prediction leaves BA unchanged; (MR3) permuting queries leaves BA unchanged; a constant predictor gives BA = 1/K exactly (0.5 binary, 0.25 type 3); hand calculation: 200 positives, 800 negatives, TP = 180, TN = 560 → accuracy 0.74, BA = 0.80. | Hypothesis tables, n 2–10⁴ | exact (rational arithmetic) |
| P-015-02 | McNemar MRs: (MR1) swapping the arms swaps b and c and leaves p unchanged; (MR2) adding concordant queries leaves p unchanged; (MR3) b = c gives p = 1; hand calculation b = 60, c = 35 → exact p = 0.013379 (χ²_cc = 6.063). | b, c ∈ [0, 5,000] | rtol 1e-6 |
| P-015-03 | Wilson MRs: (MR1) the interval of (n − k, n) is [1 − U, 1 − L] of (k, n); (MR2) both bounds are non-decreasing in k; (MR3) the interval narrows as n grows at fixed k/n; hand calculation 485/500 → [0.9511, 0.9817]; half-width at 540/1,080 = 0.0298. | n ∈ [1, 10⁵] | rtol 1e-6 |
| P-015-04 | AUROC MRs: (MR1) invariant under strictly increasing transforms of s; (MR2) AUROC(−s) = 1 − AUROC(s); (MR3) invariant under query permutation; equals `sklearn.metrics.roc_auc_score`. | Hypothesis scores incl. ties | rtol 1e-12 |
| P-015-05 | Agreement MRs: (MR1) a(Q8_0, BF16) = a(BF16, Q8_0); (MR2) a = 1 for identical lists; (MR3) invariant under query permutation; the gate passes at 475/500 and fails at 474/500. | lists of 1–10⁴ answers | exact |
| P-015-06 | 2AFC MRs: (MR1) a responder that always picks the first clip scores s̄ = 0.5 exactly; (MR2) so does one that always picks the second; (MR3) swapping the presentation order of every pair leaves s̄ unchanged; a perfect responder scores 1. | 100-pair tables | exact |
| P-015-07 | Caption MRs: (MR1) template captions built from the scene graph give CHAIR_i = 0 and recall = 1 exactly; (MR2) replacing a word by a synonym of the same class leaves M unchanged; (MR3) permuting sentences leaves CHAIR_i and recall unchanged; adding a mention of an absent class never lowers CHAIR_i. | Hypothesis captions over the vocabulary | exact |
| P-015-08 | Ground-truth MRs: (MR1) a common rigid motion of the scene and camera leaves every answer unchanged; (MR2) re-authoring the stage in centimetres with `metersPerUnit` = 0.01 leaves every answer unchanged; (MR3) permuting prims leaves every answer unchanged; moving the person monotonically away flips the type-1 truth at most once. | Hypothesis scene states | exact |
| P-015-09 | Back-projection: projecting a ground point through the camera and back-projecting the pixel onto the terrain model returns the point. | points 5–300 m from the camera | atol 1e-6 m |
| P-015-10 | Corruption MRs: (MR1) time reversal is an involution; (MR2) the identity corruption (gravity × 1) reproduces the calibrated clip bit-exactly (deterministic Warp mode); (MR3) every corruption detector is invariant under permutation of particle ids. | synthetic trajectories | exact |
| P-015-11 | Parser: for any string the parser returns exactly one label of its set and never raises; it is idempotent on its own canonical outputs and invariant under case and surrounding whitespace. | Hypothesis text (Unicode, ≤ 10⁴ characters) | exact |
| P-015-12 | Conversion determinism: converting the same inputs with the same tools twice yields identical SHA-256 values for the F16 model, the projector and the Q8_0 file. | the pinned revision | exact |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-015-01 | Device-peak VRAM (publishable: MIT runtime, open-model licence without a benchmark clause) | Q8_0 ≤ 6 GB at a 16,384-token context; BF16 ≤ 12 GB; otherwise the context is reduced and the limit recorded | `st59_reason_bench` NVML telemetry |
| NFR-015-02 | GPU time for tasks A–C (plan estimate 8–16 GPU-h) | projected by the bench; if the projection exceeds 16 GPU-h, the run is split across ≥ 2 queue slots without reducing any pre-registered sample size | runner telemetry |
| NFR-015-03 | Baked text per case (B1, B2, A3) | < 1 MB | CI budget check |
| NFR-015-04 | Errored queries per stage | ≤ 2 % (FR-015-12) | stage summary |
| SC-015-01 | Quantisation | Q8_0 versus BF16 agreement ≥ 95 % on binary questions (otherwise BF16 replaces Q8_0) | `st59_reason_bench` gate report |
| SC-015-02 | Task A reporting | per-type balanced accuracy reported with its confidence interval, for every arm | scoring table |
| SC-015-03 | Comparison with the base model | "Cosmos beats Qwen base" only if McNemar p < 0.05 | scoring table + UI verdict text |
| SC-015-04 | Role | never a headline KPI | FR-015-42 check |
| SC-015-05 | Task B (pre-registered null) | pair accuracy with its 95 % interval against chance = 0.5; "above chance" only by FR-015-37 | task-B table |
| SC-015-06 | Task C | CHAIR_i, CHAIR_s, recall and condition accuracy reported against the template baseline | task-C table |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-015-01 | per-frame scene state (transforms in metres, classes, footprints, visible pixels, depth and dust-field references, conditions) | `contracts/frame-state.schema.json` (new, T-015-001) | SDG stage `st55_sdg` (spec 009) → task-A builder, task-C scorer |
| DC-015-02 | task-A query set | `contracts/vlm-queries.schema.json` (new, T-015-001) | query builder → `st59a_vqa`, scoring |
| DC-015-03 | pins (llama.cpp archives and executables, model repositories, revisions, file SHA-256, prompt hashes) | `contracts/reason-pins.schema.json` (new, T-015-001) | maintainer → every `st59_*` stage |
| DC-015-04 | published answer records | `contracts/vlm-record.schema.json` (new, T-015-001) | `studio publish` → web panels |
| DC-015-05 | metrics tables (tasks A–C, gate, bench) | `contracts/vlm-metrics.schema.json` (new, T-015-001) | scoring → web results, model card |
| DC-015-06 | plausibility pair index | `contracts/plausibility-pairs.schema.json` (new, T-015-001) | pair builder → `st59b_plausibility` |
| DC-015-07 | run and asset manifests | `contracts/manifest.schema.json` (spec 001) | `st59_*` stages → web, CI |
| DC-015-08 | probe `llamacpp` in `studio/capabilities.json` | `contracts/capabilities.schema.json` (DC-000-02) | `studio/bench/run_bench.py` → planner |

## 7. Edge cases and assumptions

**Pinned at specification (read 2026-10-06/07):**
- NVIDIA Open Model License (2025-10-24): no clause restricting the disclosure of benchmarking or performance data
  was found. §3.2 reads: "If you distribute or make available a NVIDIA Cosmos Model, or a product or service
  (including an AI model) that contains or uses a NVIDIA Cosmos Model, … you will include 'Built on NVIDIA Cosmos' on a
  related website, user interface, blogpost, about page, or product documentation". With llama.cpp (MIT) and PyTorch,
  the lane's performance numbers are therefore `public` (NFR-015-01), unlike the RTX lanes.
- GGUF Q8_0 layout, `ggml/src/ggml-common.h` (llama.cpp master): `#define QK8_0 32`; `block_q8_0 { ggml_half d;
  int8_t qs[QK8_0]; }`, so a block of 32 weights takes 34 bytes = 8.5 bits per weight.
- CHAIR: Rohrbach, Hendricks, Burns, Darrell & Saenko (2018), "Object Hallucination in Image Captioning", EMNLP 2018
  (arXiv 1809.02156), §2.1, p. 2: "CHAIRi = |{hallucinated objects}| / |{all objects mentioned}|", "CHAIRs =
  |{sentences with hallucinated object}| / |{all sentences}|".
- Model facts used for sizing: Cosmos-Reason2-2B, 2,438,696,960 BF16 parameters (≈ 4.9 GB), a post-trained
  Qwen3-VL-2B-Instruct; KV cache 2 × 28 × 8 × 128 × 2 B = 114,688 B per token (16,384 tokens ≈ 1.9 GB).

**UNVERIFIED (oracles independent of them):**
- McNemar (1947) and Wilson (1927) primary texts not read; the oracles are reference implementations
  (`scipy.stats.binomtest`, `statsmodels` `mcnemar(exact=True)` and `proportion_confint(method="wilson")`) and hand
  calculation.
- Native video for Qwen3-VL in llama.cpp: frame lists are labelled "frame-list approximation" (FR-015-36).
- Fit and speed on the 16 GB laptop GPU (measured by FR-015-13).

**Edge cases:**
- Type-3 answers above 3 map to "≥ 3"; "none" maps to 0.
- Condition slices (dust only, night only) are not balanced; balanced accuracy is used there for that reason.
- If b + c = 0, the verdict is "no significant difference" (p = 1).
- The constant arm is a floor; its balanced accuracy equals 1/K by construction.
- Synthetic frames only; real-image performance is "not measured" unless the probe exists (FR-015-45).

**Tolerances and their justification:** statistics are computed in float64 against reference implementations that
use the same formulas, so rtol 1e-6 covers differences in summation order and special-function evaluation (beta and
binomial tails). Rational quantities (BA from counts, agreement, s̄) are compared exactly through fractions.

## 8. Clarifications log

- Resolved (docs inconsistent): the McNemar variant. The M22 method page and the model card give χ² without
  continuity correction (6.58, p = 0.010); the theory page gives the continuity-corrected value (6.06, p ≈ 0.014). The
  claim uses the exact two-sided binomial test for every b + c (p = 0.0134 for the worked example) and requires b > c.
  χ²_cc is reported when b + c ≥ 25.
- Resolved (docs inconsistent): the gate subset. The framework page says "200 mixed queries"; the method page, the
  model card and the theory page say a 500-query subset. The 200 mixed queries are the footprint and speed bench; the
  agreement gate uses 500 binary queries.
- Resolved: the gate applies to the point estimate (plan wording); the Wilson interval is reported.
- Resolved: 1,080 queries per type × 6 = 6,480 ("about 6,500"), at most one per frame and type, exactly balanced.
- Resolved: ambiguity bands (27–33 m, 100–400 px, τ between 0.1054 and 0.3216, 1 m of the blind-zone boundary,
  9–11 % grade) are pre-registered exclusions, so ground truth is unambiguous from pixels.
- Resolved: the detector + geometric rule is "not applicable" to types 2, 4 and 6 (no detector evidence).
- Resolved: the BF16 reference and the llama.cpp driver run from `pipeline/` (Python 3.14). `studio/reason/` holds
  configuration, prompts and pins only, as its documentation states (no Python project).
- Resolved: reasoning on is run on a stratified 300-query subset with up to 4,096 new tokens; reasoning off on all
  queries.
- Resolved: the task-B interval is computed over pairs, not trials, because the two orders of a pair are not
  independent.
- Resolved: published records are a stratified random sample; the full answer set stays local (text budget, < 1 MB
  per case).

## 9. Changes (only for features that modify earlier behaviour)

### ADDED Requirements
- (none — new feature)

### MODIFIED Requirements
- (none)

### REMOVED Requirements
- (none)
