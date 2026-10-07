# Plan 016 — Export and acceleration: ONNX with parity, TensorRT engines with per-engine parity, budgets
Spec: ./spec.md

## Summary
1. **Exporter** (`s60_export`): one dynamo export per model at a configured opset, `onnxslim`, IR pinned to 10, checker
   and load checks (FR-016-01 … FR-016-03).
2. **Parity layers 1 and 2**: one numpy comparator (element tolerance, maximum error, margin-aware argmax) and a
   reduced-precision gate built on ONNX Runtime's own converter and quantiser (FR-016-04 … FR-016-10).
3. **Bake accounting**: manifest entries, measured lanes from web timing records, asset hosts, the release-asset list,
   class budgets and validated glTF / 3D Tiles / shards (FR-016-11 … FR-016-19).
4. **Engines** (`s62_accel`): strongly typed TensorRT 11.3 builds through Polygraphy, local only, licence-gated
   (FR-016-20 … FR-016-25).
5. **Bench** (`s64_bench`): latency, throughput, energy, layer-4 parity, records, the publishable table and camera
   streams per GPU, with every failing cell kept (FR-016-26 … FR-016-36).

## Technical context
Runtime: Python 3.14 · `pipeline/` (locked: torch 2.14.1 cu130, onnxruntime-gpu 1.30.0, onnx 1.23.1, onnxslim
0.1.97) · `pipeline/accel/` (locked: `tensorrt-cu13-bindings` and `tensorrt-cu13-libs` 11.3.0.99, polygraphy 0.53.6,
`nvidia-cuda-runtime` 13.4.92, onnxruntime-gpu 1.30.0 CUDA provider, nvidia-ml-py) · to be resolved, locked and proved
before feature code (T-016-000): the TensorRT 10.14 libraries in `pipeline/` for the ONNX Runtime TensorRT provider
(optional; "not run" until present), the Khronos glTF Validator and the 3D Tiles Validator (project-local npm, locked)
· target: local GPU for engines and timing; CPU and the fake GPU backend for every test that CI runs; GitHub Pages for
the baked table and the live ONNX files.

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | every number comes from a run on the stated machine, with its fingerprint; no assumed speed-ups |
| Spec before code | yes | every behaviour has an id in spec 016 |
| Acceptance-test-first | yes | `[red]`/`[green]` pairs in tasks.md; SC rows have acceptance tests on the parity reports and bench records |
| Independent oracles | yes | analytical (tolerance boundaries, margin theorem, tile counts, energy), reference implementations (`onnx.checker`, ONNX Runtime CPU, numpy percentiles, Khronos glTF Validator, 3D Tiles Validator), hand calculation |
| Determinism & explicit tolerances | yes | bitwise export, seeded golden sets and bootstraps, tolerances from `thresholds.yaml` justified below |
| Neutral contracts | yes | DC-016-01 … DC-016-05 under `contracts/`; DC-000-01 manifests |
| Static delivery | yes | engines never ship; the web keeps ORT-web with a measured lane and a baked fallback for every model (FR-016-12) |
| Honesty | yes | rejected, build-failed and "not run" cells are published; one-machine caption; local-only marker for licence-restricted backends (FR-016-31, FR-016-33, FR-016-34) |
| Licence hygiene | yes | engines and caches never committed or uploaded; licence hash gate; TensorRT for RTX never published (FR-016-22, FR-016-23, FR-016-33) |
| Simplicity | yes | `torch.onnx`, `onnxslim`, ONNX Runtime's converter and quantiser and Polygraphy used directly; ModelOpt and Torch-TensorRT not added |

## Design
Data flow: [export parity](../../docs/assets/diagrams/model-export-parity.svg) and
[acceleration and encode flows](../../docs/assets/diagrams/acceleration-encode-flows.svg).

| Component (planned location) | Responsibility | Requirements |
|---|---|---|
| Exporter (`pipeline/`, export module) | dynamo export, cleanup, IR pin, checks, parity variant | FR-016-01 … FR-016-03, FR-016-05, P-016-11 |
| Comparator (`src/pitstudio/`, pure numpy) | element tolerance, maximum error, margin-aware argmax, fail-closed guards; shared by layers 1 and 4 | FR-016-04, FR-016-30, FR-016-39, P-016-01 … P-016-04 |
| Golden sets and reduced precision (`pipeline/`) | selection, guards, fp16 / int8 / fp8 variants, layer-2 gate | FR-016-06 … FR-016-10 |
| Bake accounting (`src/pitstudio/`, lane gate and budgets) | manifest entries, lanes, hosts, release list, budgets | FR-016-11 … FR-016-18, P-016-08 … P-016-10 |
| Web bake (`pipeline/` `s60_export`) | glTF, 3D Tiles, shards with validator runs and input guards | FR-016-19, FR-016-37 |
| Engine builder (`pipeline/accel/` `s62_accel`) | CUDA 13 runtime resolution, Polygraphy builds, records, licence gate | FR-016-20 … FR-016-24 |
| Bench (`pipeline/accel/` and `pipeline/` `s64_bench`) | timing loop with an injectable clock, statistics, energy, layer 4, records, table, streams | FR-016-25 … FR-016-36, FR-016-38, P-016-05 … P-016-07, P-016-12 |

The comparator, statistics, energy, lane, budget, host and stream functions are pure and run in CI; the TensorRT and
NVML calls sit behind thin adapters that the fake GPU backend (spec 002) replaces, so the bench logic is tested without
a GPU.

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-016-01 | unit + pipeline | reference implementation: `onnx.checker` and ONNX Runtime CPU on a tiny Conv → ReLU → GlobalAveragePool fixture; hand calculation: read-back `ir_version` = 10 and the configured opset | pytest |
| FR-016-02 | unit (hostile) | hand calculation: opset 16 and 20 configs, `ir_version` 11, a custom-domain node, a web graph with `GridSample`-20 | pytest + onnx |
| FR-016-03 | unit (hostile) | hand calculation: truncated bytes, `ir_version` 11, external data `../w.bin`, a reported size of 2³¹ bytes | pytest |
| FR-016-04 | unit + pipeline | analytical: perturbations exactly at and just beyond atol + rtol·\|y\| and max_abs; hand calculation of the argmax rule | pytest |
| FR-016-05 | unit + pipeline | hand calculation: a two-query fixture with tied scores (element-wise fails, task metric equal) | pytest |
| FR-016-06 | contract | hand calculation: golden list with SHA-256, provenance split = validation / held-out | pytest + jsonschema |
| FR-016-07 | unit (hostile) | hand calculation: 199 inputs, a NaN input, a wrong shape → `golden-invalid` | pytest |
| FR-016-08 | unit + pipeline | reference implementation: ONNX Runtime converter and quantiser used directly; hand calculation: blocked op types stay fp32, weight `DequantizeLinear` nodes carry an `axis`, calibration ∩ golden = ∅ | pytest + onnx |
| FR-016-09 | unit | hand calculation: Δ = 0.99 / 1.01 pp; mask IoU 0.990 / 0.989 | pytest |
| FR-016-10 | unit (hostile) | hand calculation: `bf16`, fp8 at opset 17, fp8 on a CNN → refused | pytest |
| FR-016-11 | contract | reference implementation: `jsonschema` validation of fixture entries against `contracts/manifest.schema.json` | pytest |
| FR-016-12 | unit | hand calculation: 25,000,000 / 25,000,001 bytes; 16 / 17 ms; 1.0 / 1.001 s; missing record → not LIVE | pytest |
| FR-016-13 | unit (hostile) | hand calculation: NaN, negative, wrong SHA-256, stale date | pytest |
| FR-016-14 | unit | hand calculation: files of 9,999,999 and 10,000,000 bytes; an in-git overflow moving the largest class | pytest |
| FR-016-15 | contract | hand calculation: sorted entries, POSIX paths, tag | pytest + jsonschema |
| FR-016-16 | unit (hostile) | hand calculation: `/abs`, `a/../b`, `a\b`, `C:x`, a symlink outside the root, tag `assets-v1.2.3`, a size of 2³¹ | pytest |
| FR-016-17 | unit | hand calculation: class totals against Table B; a 500,000,001-byte site | pytest |
| FR-016-18 | unit (hostile) | hand calculation: missing class; class `misc` | pytest |
| FR-016-19 | integration | reference implementation: Khronos glTF Validator and 3D Tiles Validator report 0 errors on a two-triangle fixture bake and ≥ 1 error on a deliberately invalid fixture; shard sizes by hand | pytest + npm validators |
| FR-016-20 | integration (gpu) + unit (fake GPU) | hand calculation: recorded builder configuration (TF32 cleared, profile batches), `CUDA_PATH` set to the CUDA 13 wheel folder; analytical: the probe-graph engine matches ONNX Runtime CPU within 1e-4 | pytest (`gpu`) + fake GPU backend |
| FR-016-21 | unit (fake GPU) | hand calculation: a builder that raises → `build-failed`, scrubbed text, next variant built | pytest + fake GPU backend |
| FR-016-22 | CI | hand calculation: fixture repository containing `x.plan` → guard fails | pytest |
| FR-016-23 | unit | hand calculation: fake distribution metadata with a different `LICENSE.txt` hash or none → `local-only` and the note | pytest |
| FR-016-24 | unit (fake GPU) | hand calculation: capability fixtures (no TensorRT; no CUDA; no 10.14 libraries) → expected cell statuses | pytest + fake GPU backend |
| FR-016-25 | unit (hostile) | hand calculation: a graph with fp16 initialisers sent to the TensorRT provider → refused | pytest |
| FR-016-26 | unit (fake GPU) + integration (gpu) | hand calculation with a fake clock: 20 ms → 1,000 iterations; 100 ms → 300 iterations; 1 s → 50 iterations; reference implementation: `numpy.percentile(method="linear")` | pytest + fake GPU backend |
| FR-016-27 | unit (fake GPU) | hand calculation: batch 16 × 100 iterations in 2 s → 800 samples/s | pytest |
| FR-016-28 | unit (fake GPU) | hand calculation: counter 1,000,000 → 1,500,000 mJ over 1,000 iterations of batch 1 → 0.5 J; thermal-slowdown flag on one sample | pytest |
| FR-016-29 | unit (hostile) | hand calculation: no counter, a decreasing counter, a 0.9 s window → null with reason | pytest |
| FR-016-30 | unit (fake GPU) + integration (gpu) | analytical: a fake engine adding 1e-2 to one output → `rejected` with that maximum error; an exact engine → `pass` | pytest + fake GPU backend |
| FR-016-31 | unit | hand calculation: a matrix with one rejected, one build-failed and one not-run cell → all three rows present with reasons | pytest |
| FR-016-32 | contract | reference implementation: `jsonschema` on fixture records; fingerprint fields present | pytest |
| FR-016-33 | unit + CI | hand calculation: a TensorRT-for-RTX record outside the local folder → guard fails | pytest |
| FR-016-34 | contract | hand calculation: caption string; two records with different power limits are not compared | pytest |
| FR-016-35 | unit | hand calculation: R = 2,800 tiles/s, 28 tiles, 10 frames/s → 10 streams | pytest |
| FR-016-36 | unit (hostile) | hand calculation: NaN and negative durations, backend `tensorrt-rtx-2`, precision `int4` | pytest |
| FR-016-37 | unit (hostile) + integration | hand calculation: a NaN vertex, index 3 in a two-vertex mesh, an unlicensed texture; reference implementation: a validator error fails the asset | pytest + npm validators |
| FR-016-38 | unit (hostile) | hand calculation: W = 0, t = o = 64, f = 0, R = NaN → `ValueError` | pytest |
| FR-016-39 | unit (hostile) | hand calculation: shapes (2, 3) vs (3, 2), two outputs vs one, a NaN candidate against a finite reference → `fail` | pytest |
| P-016-01 … P-016-04 | metamorphic / property | invariants and the margin theorem | Hypothesis |
| P-016-05, P-016-06 | metamorphic | unit change, shift, permutation; energy scaling | Hypothesis |
| P-016-07, P-016-12 | metamorphic | symmetry, monotonicity, the hand-computed 28 tiles | Hypothesis |
| P-016-08 … P-016-11 | metamorphic / property | additivity, monotonicity, order invariance, idempotence | Hypothesis |
| NFR-016-01, NFR-016-04, NFR-016-05 | CI / unit | sizes against the stated caps | pytest |
| NFR-016-02 | contract | run manifest wall time ≤ 8 h; cells cached individually | pytest |
| NFR-016-03 | pipeline | metamorphic: two exports, byte-identical files | pytest |
| NFR-016-06 | CI | hand calculation: CI workflow selects `-m "not gpu"` and never invokes `s62_accel` / `s64_bench` on hardware | pytest |
| SC-016-01 … SC-016-03 | pipeline (acceptance) | pre-registered tolerances read from the parity reports and bench records | pytest |

### Tolerances and their justification
- Layer 1 (rtol 1e-3, atol 1e-5, max abs 1e-4; `thresholds.yaml` `models.onnx_cpu_fp32`): fp32 kernels of ONNX Runtime
  and PyTorch differ in accumulation order, giving relative differences of order √n·ε ≈ 1e-5 for the reduction sizes of
  these models (n ≤ 10⁵, ε = 1.2e-7); the thresholds leave a margin of 10–100 and still catch any wrong operator.
- Argmax margin 2e-4: the margin theorem (P-016-04) — with max \|a − b\| ≤ 1e-4, a row can only flip if its top-2 gap is
  ≤ 2e-4, so exact agreement is required everywhere else.
- Deployed-graph task metric within 0.1 percentage point (FR-016-05): post-processing adds no learned parameters, so
  only tied scores at the top-K boundary can differ; 0.1 pp allows a handful of tie swaps on a 200-image golden set.
- Layer 2 and reduced-precision engines (\|Δ\| ≤ 1 pp, mask IoU ≥ 0.99; `thresholds.yaml`): the plan's acceptance values;
  a larger move means the variant behaves as a different model.
- Statistics (rtol 1e-12): scaling and shifting are exact up to float64 rounding.

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Two TensorRT environments | ONNX Runtime 1.30's provider needs TensorRT 10.14; native 11.3 has the same distribution name | one environment cannot hold both; dropping either removes a path the known issue may or may not affect |
| A `parity` export variant for post-processed graphs | element-wise comparison of top-K outputs is ill-posed under ties | comparing only task metrics would hide small numeric drifts that layer 1 must catch |
| Injectable clock and NVML adapters | the bench logic must be testable in CI without a GPU | testing only on the reference machine would leave the decision logic untested between runs |
| Per-class archive overflow | keeps the in-git total ≤ 100 MB deterministically | moving single files ad hoc would make the asset list order-dependent |
