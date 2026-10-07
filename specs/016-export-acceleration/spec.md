# Spec 016 — Export and acceleration: ONNX with parity, TensorRT engines with per-engine parity, budgets
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Every trained PitStudio model becomes one ONNX file that ONNX Runtime (CPU, CUDA, TensorRT provider), ONNX Runtime Web
and TensorRT can all read, and every conversion is treated as a claim to check. This spec fixes three stages:
- `s60_export` (`pipeline/`): ONNX export with a pinned opset and IR version, parity layers 1 (ONNX = PyTorch) and 2
  (reduced precision), the web bake (glTF / 3D Tiles / shards), measured lanes, budgets, asset hosts, the manifest and
  the release-asset upload list;
- `s62_accel` (`pipeline/accel/`): native TensorRT 11.3 engines fp32 / fp16 / int8 / fp8, local only;
- `s64_bench` (`pipeline/accel/` and `pipeline/` for the ONNX Runtime backends): latency, throughput, joules per
  inference, accuracy change and parity layer 4 on every engine, every TensorRT version and every execution provider,
  with failing variants reported as rejected (the known D-FINE wrong-output issue #4813 makes no TensorRT path safe).

It inherits FR-000-08 (licence-restricted performance data), FR-000-14/15 (manifest, measured lane) and the model
tolerances of `thresholds.yaml` (`models.onnx_cpu_fp32`, `models.quantized_task_metric_delta_max_pp`,
`models.mask_iou_min_vs_fp32`).

Who benefits: developers (one portable, checked graph per model), reviewers (an acceleration table where every number
has a parity verdict), mining engineers (camera streams per laptop GPU) and the maintainer (enforced budgets and a
deterministic asset list).

Out of scope:
- model-specific export choices and acceptance (specs 009, 011, 012 and the other model specs); this spec provides the
  mechanism they call;
- parity layer 3 (browser = Python) and the web timing tool (spec 018); the Acceleration tab UI (spec 020-web-knowledge,
  FR-020-28);
- the release workflow that creates, verifies and publishes the asset release (repository tooling); this spec only
  writes the list;
- TensorRT in the browser (engines are device-specific); FP4 / INT4 (emulated or without benefit on this GPU);
  publishing any TensorRT for RTX number.

## 2. User stories

### US-016-1 (P1) One checked ONNX file per model
As a developer, I want each model exported once at a pinned opset and IR version and proved equal to PyTorch on a
golden set, so that the browser, ONNX Runtime and TensorRT all start from a graph I can trust. Independent test: export
a tiny fixture model and run layer 1.

### US-016-2 (P1) Reduced precision only when equivalent
As a reviewer, I want fp16, int8 and fp8 variants accepted only when the task metric moves by at most 1 percentage
point (and masks keep IoU ≥ 0.99), so that smaller or faster models are not silently worse. Independent test: feed the
gate fixture metrics on both sides of the threshold.

### US-016-3 (P1) An honest acceleration table
As a reviewer, I want latency, throughput, energy and accuracy change for every model × backend × precision, each with
its parity verdict and with rejected engines listed, so that I can read speed against correctness on one stated
machine. Independent test: run the bench logic on the fake backend with a deliberately wrong engine.

### US-016-4 (P1) Budgets, lanes and the asset list
As the maintainer, I want every exported artefact measured into its lane, counted against its budget class and
assigned to git or a release asset, with a deterministic upload list, so that the site stays within 500 MB and every
large file is pinned. Independent test: run the bake accounting on fixture files.

### US-016-5 (P1) Licence-safe acceleration evidence
As a reviewer, I want TensorRT numbers published only while the reviewed licence text is unchanged, TensorRT for RTX
numbers never published and engines never committed, so that the evidence is legal to show. Independent test: run the
gate with a changed licence hash and a TensorRT-for-RTX record.

### US-016-6 (P2) Camera streams per GPU
As a mining engineer, I want the number of 4K pit-camera streams one laptop GPU can serve at a stated frame rate and
recall, so that I can reason about edge deployment. Independent test: compute the tile count and streams by hand.

Story index (for traceability):

| Story | Title | Priority |
|---|---|---|
| US-016-1 | One checked ONNX file per model | P1 |
| US-016-2 | Reduced precision only when equivalent | P1 |
| US-016-3 | An honest acceleration table | P1 |
| US-016-4 | Budgets, lanes and the asset list | P1 |
| US-016-5 | Licence-safe acceleration evidence | P1 |
| US-016-6 | Camera streams per GPU | P2 |

## 3. Functional requirements (EARS)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-016-01 | Ubiquitous | The stage `s60_export` shall export each model with `torch.onnx.export(dynamo=True, verify=True)` (torch 2.14.1) at the default-domain opset of its export config (DC-016-04), one of {17, 18, 19}, record the opset and its reason in the manifest, clean the graph with `onnxslim`, set `ir_version` to 10, and accept the file only if `onnx.checker.check_model(full_check=True)` passes and ONNX Runtime 1.30 CPU loads it. | unit + pipeline |
| FR-016-02 | Unwanted | If the export config does not validate against DC-016-04 or names an unknown model, the configured opset is outside {17, 18, 19}, the written `ir_version` differs from 10, the checker fails, a node uses a domain outside the config's allow-list, or a graph flagged `web` contains `GridSample` at since-version ≥ 20, then `s60_export` shall fail that model's export with the reason and publish nothing for it. | unit (hostile) |
| FR-016-03 | Unwanted | If an ONNX file given to `s62_accel`, `s64_bench` or the web bake does not parse as a ModelProto, has `ir_version` > 10, references external data outside its own folder, or is ≥ 2³¹ bytes, then the consumer shall reject it with the reason and process nothing from it. | unit (hostile) |
| FR-016-04 | Ubiquitous | The layer-1 parity check shall run the ONNX Runtime CPU fp32 graph and the PyTorch fp32 model on CPU (`torch.use_deterministic_algorithms(True)`) on the golden set and pass only if every raw output element satisfies \|y_ort − y_pt\| ≤ 1e-5 + 1e-3·\|y_pt\|, the maximum \|y_ort − y_pt\| ≤ 1e-4, and argmax agrees for 100 % of the rows of every `class_scores` output whose reference top-2 gap exceeds 2e-4 (rows with smaller gaps counted and reported). | unit + pipeline |
| FR-016-05 | Optional | Where a graph has an in-graph post-processor (top-K, box scaling), the layer-1 parity check shall compare the `parity` variant exported from the same weights without the post-processor, and the deployed graph shall reproduce the PyTorch post-processed task metric on the golden set within 0.1 percentage point. | unit + pipeline |
| FR-016-06 | Ubiquitous | The golden set of a model shall hold ≥ 200 inputs drawn (seeded) from its validation or held-out data, never from training data, listed by SHA-256 in the parity report (DC-016-03), and kept local when derived from third-party data whose images may not be committed. | contract |
| FR-016-07 | Unwanted | If a golden set has fewer than 200 inputs, an input or reference output contains a non-finite value, or an input shape or dtype differs from the graph's declared input, then the parity stage shall refuse with `golden-invalid` and the reason. | unit (hostile) |
| FR-016-08 | Ubiquitous | The fp16 variant shall be produced with ONNX Runtime's `float16.convert_float_to_float16(keep_io_types=True)` with `LayerNormalization`, `Softmax`, `ReduceMean`, `ReduceSum` and `ReduceMax` kept in fp32, and the int8 and fp8 variants with ONNX Runtime's `quantize_static` in QDQ format (`QInt8` or `QFLOAT8E4M3FN`), per-channel weights, per-tensor activations, calibrated on 500 seeded training inputs disjoint from the golden and evaluation sets. | unit + pipeline |
| FR-016-09 | Ubiquitous | The layer-2 gate shall accept a reduced-precision variant only if \|metric_variant − metric_fp32\| ≤ 1 percentage point on the model's evaluation set and, for mask outputs, the mean mask IoU against fp32 is ≥ 0.99 (and, for detectors, the spec 009 robustness criterion holds); every other variant shall be marked `rejected` with its numbers and reason and shall not ship. | unit |
| FR-016-10 | Unwanted | If a variant is requested with a precision outside {fp32, fp16, int8, fp8}, or fp8 for a graph below opset 19 or one not flagged `gemm_heavy`, then `s60_export` and `s62_accel` shall refuse that variant with the reason. | unit (hostile) |
| FR-016-11 | Ubiquitous | The stage `s60_export` shall write, for every exported or baked artefact, a manifest entry (DC-000-01) with path, bytes, SHA-256, measured lane and lane measurements, asset host and release tag, budget class, licence class, SPDX id, attribution, producer tool and stage, and the `performance` marker of the producing stage. | contract |
| FR-016-12 | Ubiquitous | The stage `s60_export` shall derive the lane as LIVE if and only if the artefact is web-drivable, its bytes ≤ 25 × 10⁶, (its interaction time ≤ 16 ms or its run time ≤ 1 s on T2) and its trace ≤ 10 × 10⁶ bytes, taking times from the web timing record of that artefact's SHA-256 (spec 018), and otherwise PRECOMPUTE or REPLAY; an artefact without a valid timing record shall not be LIVE. | unit |
| FR-016-13 | Unwanted | If a timing record has a non-finite or negative time, a SHA-256 different from the artefact's, or a date earlier than the artefact's creation, then `s60_export` shall ignore it, record the reason, and derive a non-LIVE lane. | unit (hostile) |
| FR-016-14 | Ubiquitous | The stage `s60_export` shall host a file in git if it is < 10 × 10⁶ bytes and the in-git baked total stays ≤ 100 × 10⁶ bytes, and otherwise as a release asset; when the in-git total would exceed 100 × 10⁶ bytes, whole budget classes, largest total first, shall move into per-class release-asset archives until it does not. | unit |
| FR-016-15 | Ubiquitous | The stage `s60_export` shall write the release-asset upload list (DC-016-02): every release-hosted file with its repository-relative POSIX path, bytes, SHA-256 and the tag `assets-vX.YY.ZZZ`, sorted by path. | contract |
| FR-016-16 | Unwanted | If a release-list path is absolute, contains `..`, a backslash or a drive letter, or resolves outside the bake root, or the tag does not match `^assets-v\d+\.\d{2}\.\d{3}$`, or a file is ≥ 2³¹ bytes, then `s60_export` shall fail the list with the offending entry. | unit (hostile) |
| FR-016-17 | Ubiquitous | The stage `s60_export` shall total the bytes of every budget class and fail the bake if any total exceeds its cap (§7 Table B) or the site total exceeds 500 × 10⁶ bytes, writing a budget report with each class total, cap and margin. | unit |
| FR-016-18 | Unwanted | If an artefact has no budget class or a class not in §7 Table B, then `s60_export` shall fail the bake with the artefact's path. | unit (hostile) |
| FR-016-19 | Ubiquitous | The stage `s60_export` shall bake the composed scene (spec 004) into glTF 2.0 binary files that pass the Khronos glTF Validator with 0 errors and 3D Tiles 1.1 tilesets that pass the 3D Tiles Validator with 0 errors, and shall write replay shards of ≤ 10 × 10⁶ bytes each with their SHA-256 in the manifest. | integration |
| FR-016-20 | Ubiquitous | The stage `s62_accel` shall build, per model and applicable precision, a strongly typed TensorRT 11.3 engine with Polygraphy from the layer-1/2 ONNX variants — fp32 with the TF32 builder flag cleared, fp16 from the fp16 cast graph, int8 and fp8 from their QDQ graphs — with one fixed optimisation profile covering the bench batch sizes, after pointing `CUDA_PATH` and the DLL search path at the CUDA 13 runtime wheel, and shall record engine SHA-256, TensorRT version, builder configuration and build time in the run manifest. | integration (gpu) + unit (fake GPU) |
| FR-016-21 | Unwanted | If an engine build fails, then `s62_accel` shall record the variant as `build-failed` with the builder's error text (scrubbed of paths) and continue with the next variant, and the variant shall appear in the published table. | unit (fake GPU) |
| FR-016-22 | Ubiquitous | The engine builder shall write engines and timing caches only under the git-ignored run folder, and never commit, upload or list them in a release-asset list; CI shall fail on any `*.plan`, `*.engine`, `*.trt` or timing-cache file in git or in the Pages artefact. | CI |
| FR-016-23 | Unwanted | If the SHA-256 of the `LICENSE.txt` of the installed `tensorrt-cu13-libs` differs from `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4` or the file is missing, then `s62_accel` and `s64_bench` shall mark every TensorRT result of that run `performance: local-only`, keep it out of committed and published files, and note "TensorRT licence text changed since review". | unit |
| FR-016-24 | Unwanted | If TensorRT, the CUDA 13 runtime wheel or a CUDA GPU is unavailable, then `s64_bench` shall mark every TensorRT cell "not run" and still run the PyTorch and ONNX Runtime cells; and if the TensorRT 10.14 libraries are not in the `pipeline/` lock, then it shall mark every ONNX Runtime TensorRT-provider cell "not run". | unit (fake GPU) |
| FR-016-25 | Unwanted | If a graph whose float tensors were pre-cast to fp16 is given to the ONNX Runtime TensorRT provider, then `s64_bench` shall refuse that cell with `precast-fp16-to-ort-trt`; that provider shall receive fp32 graphs (with its fp16 flag for the fp16 cell) or QDQ graphs only. | unit (hostile) |
| FR-016-26 | State | While in latency mode, the stage `s64_bench` shall run batch 1 with a warm-up of ≥ 5 s and ≥ 10 iterations, then time until 1,000 iterations or 30 s have elapsed, whichever comes first, but never fewer than 50 iterations, in two regimes (spaced: a 200 ms untimed gap between calls; sustained: back to back) and two scopes (GPU compute timed with CUDA events; end to end, host to device and back, timed with the host clock), and report p50, p90 and p99 (linear interpolation) with 95 % percentile bootstrap intervals (B = 2,000, seeded, resampling the sorted sample). | unit (fake GPU) + integration (gpu) |
| FR-016-27 | State | While in throughput mode, the stage `s64_bench` shall sweep batch sizes {1, 4, 16, 64} for vision models, {1, 64, 4096} for policies and particle counts {1,000, 2,000, 10,000} for the GNS, reporting samples per second as batch × iterations / elapsed seconds. | unit (fake GPU) |
| FR-016-28 | Ubiquitous | The stage `s64_bench` shall compute joules per inference as (E_end − E_start) / 1,000 / (iterations × batch) from the NVML total-energy counter (mJ), and sample power, SM and memory clocks, temperature and clocks-event reasons at 10 Hz, flagging any window with a hardware thermal-slowdown sample. | unit (fake GPU) |
| FR-016-29 | Unwanted | If the energy counter is unavailable, decreases during the window, or the window is shorter than 1 s, then `s64_bench` shall set joules per inference to null with the reason. | unit (hostile) |
| FR-016-30 | Ubiquitous | The layer-4 parity check shall compare every engine, on every TensorRT version (11.3 native; 10.14 through the ONNX Runtime provider) and every execution provider, with the stored PyTorch fp32 golden outputs: fp32 cells pass if every element satisfies \|y − y_pt\| ≤ 1e-5 + 1e-3·\|y_pt\| with TF32 cleared on both sides; fp16, int8 and fp8 cells pass if \|Δ task metric\| ≤ 1 percentage point on the evaluation set (and mask IoU ≥ 0.99; detectors also re-run the spec 009 corruption curves); each cell shall get the verdict `pass` or `rejected` with its maximum error, mismatch fraction and metric change. | unit (fake GPU) + integration (gpu) |
| FR-016-31 | Ubiquitous | The bench records and the published table shall list every `rejected`, `build-failed` or "not run" cell with its numbers (where measured) and its reason, and shall drop no cell. | unit |
| FR-016-32 | Ubiquitous | The stage `s64_bench` shall write one bench record (DC-016-01) per model × backend × precision × TensorRT version, with the fingerprint (GPU name, driver, TensorRT, ONNX Runtime and torch versions, ONNX and engine SHA-256, enforced power limit, power source, operating-system power mode), and bake a web table (DC-016-05) from the publishable records. | contract |
| FR-016-33 | Unwanted | If a bench record comes from TensorRT for RTX, or from any backend whose licence forbids publishing performance data, then `s64_bench` shall mark it `performance: local-only` and keep it out of every committed or published file, and CI shall fail on any such record outside the local run folder. | unit + CI |
| FR-016-34 | Ubiquitous | The table bake shall give every published bench table the caption "measured on one RTX 5000 Ada Laptop GPU (power-limited), Windows 11, <date>, <commit SHA> — not a general benchmark", and comparisons in it shall be made only between records with the same enforced power limit and power source. | contract |
| FR-016-35 | Ubiquitous | The stage `s64_bench` shall report camera streams per GPU for each detector cell as ⌊R / (n_tiles · f)⌋, with R the measured tiles per second at the best batch of the sweep, n_tiles = n_x·n_y where n_x = 1 if W ≤ t else ⌈(W − o)/(t − o)⌉ (likewise n_y with H), t = 640 px, o = 64 px, W × H = 3,840 × 2,160 px, f = 10 frames/s, together with the recall of that variant at score ≥ 0.5 and IoU ≥ 0.5 on the pit-family held-out set (spec 009). | unit |
| FR-016-36 | Unwanted | If a bench measurement has a non-finite or negative duration, or a record names a backend or precision outside its enum, then `s64_bench` shall discard that measurement or record with the reason and keep the cell's status "rejected (invalid measurement)". | unit (hostile) |
| FR-016-37 | Unwanted | If a scene mesh given to the web bake has a non-finite vertex coordinate or an out-of-range index, a texture without a licence record, or a validator reports any error, then `s60_export` shall fail the bake of that asset with the validator message and publish nothing for it. | unit (hostile) + integration |
| FR-016-38 | Unwanted | If the stream calculation receives a non-positive frame size, a tile size ≤ the overlap, a non-positive frame rate, or a non-finite or negative throughput, then it shall raise `ValueError` naming the argument. | unit (hostile) |
| FR-016-39 | Unwanted | If the reference and candidate outputs differ in number, shape or dtype class, or the candidate holds a non-finite value where the reference is finite, then the comparator shall return `fail` with that reason, never `pass`. | unit (hostile) |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-016-01 | Applying the same permutation to the reference and candidate tensors leaves the parity verdict, the maximum error and the mismatch fraction unchanged (permutation invariance; metamorphic). | float32 / float64 tensors of 1–10⁵ elements | exact |
| P-016-02 | If a pair passes at (rtol, atol, max_abs), it passes at every looser triple; if it fails, it fails at every tighter triple (tolerance monotonicity; metamorphic). | as P-016-01; tolerances in [1e-9, 1e-1] | exact |
| P-016-03 | A tensor compared with itself passes with maximum error 0; changing one element by more than atol + rtol·\|y\| (or by more than max_abs) makes it fail. | as P-016-01 | exact |
| P-016-04 | If max \|a − b\| ≤ τ, the row-wise argmax of a and b agrees on every row whose top-2 gap in b exceeds 2τ (margin theorem). | random score matrices, τ in [1e-6, 1e-2] | exact |
| P-016-05 | Multiplying every latency sample by k > 0 multiplies p50, p90, p99 and their interval bounds by k; adding c > 0 adds c; permuting the samples changes nothing (unit change, shift, permutation; metamorphic). | samples of 50–5,000 positive floats | rtol 1e-12 |
| P-016-06 | Joules per inference are unchanged when the iterations and the energy difference are both multiplied by k, are non-negative, and scale by 10⁻³ under a mJ → J relabelling of the counter (metamorphic). | positive counters, k in [1, 10³] | rtol 1e-12 |
| P-016-07 | n_tiles(W, H) = n_tiles(H, W), is non-decreasing in W and H, equals 1 for W, H ≤ t, and equals 28 for 3,840 × 2,160 (symmetry, monotonicity; metamorphic). | W, H in [1, 16,384] px | exact |
| P-016-08 | The budget total of a union of disjoint file sets equals the sum of their totals, does not depend on file order, and never decreases when a file is added; a passing bake stays passing when a file is removed (additivity, permutation, monotonicity; metamorphic). | random file lists with sizes 0–10⁹ bytes and classes from Table B | exact |
| P-016-09 | Increasing an artefact's bytes, interaction time, run time or trace size never turns a non-LIVE lane into LIVE (monotonicity). | random measurement tuples | exact |
| P-016-10 | The release-asset list and the asset-host assignment are byte-identical for any order of the input files, and re-running the assignment on its own output changes nothing (order invariance, idempotence). | random file sets | exact |
| P-016-11 | Pinning the IR version twice equals pinning once, and the pinned model differs from the input only in `ir_version` (same nodes, initialisers and opset imports) (idempotence). | `onnx.helper` fixture graphs at opsets 17–19 | exact |
| P-016-12 | Camera streams are non-increasing in f and in the frame size, and non-decreasing in R (monotonicity). | R in [0, 10⁵] tiles/s, f in [1, 60] frames/s | exact |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-016-01 | Baked acceleration table (web data) | ≤ 200,000 bytes | CI budget check |
| NFR-016-02 | `s62_accel` + `s64_bench` for the full model matrix | ≤ 8 h wall time (one overnight slot; estimate 4–7 GPU-h, measured and recorded); every cell is a resumable, cached unit | run manifest |
| NFR-016-03 | Export determinism | re-exporting from the same checkpoint, code and lock gives byte-identical ONNX files and manifest entries | pipeline test |
| NFR-016-04 | ONNX files in the web build | each live model ≤ 25 × 10⁶ bytes; the ONNX class ≤ 80 × 10⁶ bytes in total | budget report |
| NFR-016-05 | Files and shards | every shard ≤ 10 × 10⁶ bytes; every git-hosted file < 10 × 10⁶ bytes; in-git baked total ≤ 100 × 10⁶ bytes (NFR-000-05) | budget report + CI |
| NFR-016-06 | GPU stages and CI | `s62_accel` and `s64_bench` never run in CI; CI runs their logic against the fake GPU backend only | CI configuration check |
| SC-016-01 | TensorRT engines (plan §7) | per-engine parity on every TensorRT version and execution provider: fp32 rtol 1e-3 / atol 1e-5; reduced precision \|Δ\| ≤ 1 percentage point; failing variants reported as rejected, none dropped | `s64_bench` records |
| SC-016-02 | Every published ONNX model | passes layer 1 (rtol 1e-3, atol 1e-5, max abs 1e-4, argmax 100 % on rows with a top-2 gap > 2e-4) | parity reports |
| SC-016-03 | Every published reduced-precision variant | passes layer 2 (\|Δ task metric\| ≤ 1 percentage point; mask IoU ≥ 0.99) | parity reports |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-016-01 | Bench record (model, backend, precision, TensorRT version, regime, scope, statistics with intervals, throughput, J/inference, VRAM, parity verdict and errors, metric change, status and reason, fingerprint, `performance`) | `contracts/bench-record.schema.json` (new, T-016-001) | `s64_bench` → web table bake, model cards |
| DC-016-02 | Release-asset upload list (tag, entries: path, bytes, SHA-256) | `contracts/release-assets.schema.json` (new, T-016-002) | `s60_export` → release tooling, Pages build |
| DC-016-03 | Parity report (layer, model, variant, golden-set SHA-256 list, tolerances, maximum error, mismatch fraction, argmax agreement, metric change, verdict) | `contracts/parity-report.schema.json` (new, T-016-003) | `s60_export`, `s64_bench` → manifest, model cards |
| DC-016-04 | Export config per model (opset and reason, output roles such as `class_scores`, `gemm_heavy`, `web`, domain allow-list, task metric, golden-set id, live flag) | `contracts/export-config.schema.json` (new, T-016-004) | model specs' recipes → `s60_export`, `s62_accel` |
| DC-016-05 | Acceleration web table (publishable records only, caption fields, rejected cells) | `contracts/accel-table.schema.json` (new, T-016-005) | `s64_bench` → web Acceleration tab (spec 020, FR-020-28) |

Run and asset manifests (lane, asset host, budget class, licence, `performance`) follow the foundation contract
DC-000-01 (`contracts/manifest.schema.json`), which this spec's `s60_export` writes.

## 7. Edge cases and assumptions

**Table B — budget classes (plan §11; 1 MB = 10⁶ bytes).** The site total is 500 MB.

| Class | Cap (MB) |
|---|---|
| `videos` | 150 |
| `tiles-glb` | 95 |
| `shards-clouds` (replay shards + point clouds) | 60 |
| `splats` | 25 |
| `onnx` (each live model ≤ 25) | 80 |
| `runtimes` (ORT-web, Pyodide, Rapier; copied at build) | 55 |
| `own-code` (own JS / WASM / fonts) | 10 |
| `studio-showcase` | 25 |

Class ids are the values of the manifest field `budget_class` (spec 001 data-model §2.5). `thresholds.yaml` has no
`budgets` section yet; these caps are the plan's values and move there as the `budgets.*` keys (proposed keys,
pending maintainer approval).

**Known issues that hit the lane** (open unless stated; docs page *Export, parity and acceleration*):
TensorRT #4813 (strongly typed FP32 D-FINE-S engine silently wrong on 11.1, also reported on sm_89 and on 10.14 /
10.16 — https://github.com/NVIDIA/TensorRT/issues/4813); #4838 (FP16 grouped convolution fails to build on 11.2 on
Ada); #3650 (closed, fix not shown: `ScatterElements` with reduction when indices outnumber outputs — the GNS case);
TensorRT 11.3 known issue: GridSample FP16 context creation may fail on Windows on an RTX 5080. Each is caught by the
per-cell verdicts of FR-016-21 and FR-016-30, never assumed away.

**Pinned values.**
- ONNX Runtime 1.30 reads IR versions ≤ 13 while `onnx` 1.23.1 writes IR 14 by default; IR 10 is the value the
  bootstrap probe graph uses and is read by ONNX Runtime (Python and web) and the TensorRT parser.
- Reviewed TensorRT licence: `LICENSE.txt` of the 11.3.0.99 wheels, 47,141 bytes, SHA-256
  `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4`, no benchmark clause (the hash pinned by
  `studio/bench/probe_tensorrt.py`).
- ONNX Runtime 1.30's TensorRT provider is built against TensorRT 10.14.1.48; the two TensorRT majors cannot share an
  environment.

**Edge cases and assumptions.**
- Whether TF32 is on by default in TensorRT 11.3 is UNVERIFIED; FR-016-20 clears the flag explicitly, so no
  requirement depends on the default.
- Whether ONNX Runtime-produced FP8 QDQ graphs fuse into FP8 GEMMs on TensorRT 11.3 is UNVERIFIED; the fp8 cell is
  measured and reported as it is, with no assumed speed-up.
- The TensorRT 10.14 libraries are not yet in the `pipeline/` lock; until they are, the provider cells are "not run".
- Clocks are recorded, not locked: locking needs elevated rights.
- Golden-set parity bounds the error on that set only; task metrics and corruption curves are the second line.
- Laptop throttling makes timings drift; regimes, power state and thermal flags are recorded with every number.
- GitHub release assets must be under 2 GiB per file (FR-016-16 uses < 2³¹ bytes).

## 8. Clarifications log

- IR version "pinned ≤ 10" (assignment) versus "pinned to 10" (docs) → resolved: exactly 10, never above
  (FR-016-01, FR-016-02).
- Layer-4 reference: the decision page says "the ONNX reference", the export page says "PyTorch fp32" → resolved: the
  stored PyTorch fp32 CPU golden outputs; ONNX Runtime CPU matches them by layer 1, so both readings agree
  (FR-016-30); reported to the coordinator.
- "At least 1,000 timed iterations or 30 s" → resolved: stop at whichever comes first, with a floor of 50 iterations
  (FR-016-26).
- "Δ ≤ 1 pp" → resolved: absolute change in either direction, because the gate tests equivalence (FR-016-09,
  FR-016-30).
- `max_abs` 1e-4 → applies to layer 1 only; the plan's TensorRT criterion lists rtol and atol (FR-016-30).
- Detectors with in-graph top-K → layer 1 on a `parity` variant without the post-processor, plus a task-metric
  check of the deployed graph (FR-016-05); top-K ordering under ties makes element-wise comparison ill-posed.
- Bench telemetry at 10 Hz (runner telemetry is 1–4 Hz) → resolved: the bench samples faster because its windows are
  short (FR-016-28).
- Frame rate and recall for camera streams ("a fixed frame rate", "a stated recall") → resolved: 10 frames/s, score
  ≥ 0.5, IoU ≥ 0.5 (FR-016-35).
- In-git overflow rule ("small-file classes ship as release-asset archives") → resolved: whole classes, largest first
  (FR-016-14).
- Integration 2026-10-07: the Acceleration tab is specified by spec 020-web-knowledge (FR-020-28), not spec 018; the
  out-of-scope list and DC-016-05 now name it.
- Integration 2026-10-07: Table B uses the budget-class ids of spec 001's manifest field `budget_class` (`tiles-glb`,
  `shards-clouds`, `own-code`, `studio-showcase` replace `tiles_glb`, `replay_shards_point_clouds`,
  `own_js_wasm_fonts`, `studio_showcase`); the caps are unchanged and their `thresholds.yaml` keys are proposed keys,
  pending maintainer approval.
- (no open items)

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
(none — new feature)
### MODIFIED Requirements
(none)
### REMOVED Requirements
(none)
