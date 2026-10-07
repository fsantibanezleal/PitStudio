# Plan 013 — RTX sensor simulation (M23)
Spec: ./spec.md

## Summary

A thin RTX lane renders clean sensor data, and open code turns it into dusty, hazy and noisy variants:

- **RTX lane** (`studio/rtx/`, Python 3.12, local only). The `SensorBackend` interface and the `ovrtx` backend; recipe
  validation, the elevation-fan envelope, warm-up, the point-count guard and output validation; a shard writer.
  Stage `st53_sensors` (S1, S2, S3, S4a). Requirements FR-013-01 and FR-013-03 to FR-013-10, FR-013-19, FR-013-21 to
  FR-013-23, FR-013-30 to FR-013-34.
- **Rain arm** (`studio/isaac/`). The `isaac` backend behind the same interface, stage `st57_rain_lidar`
  (FR-013-29, FR-013-30).
- **Open post-models** (`src/pitstudio/sensors/`, Python 3.14, CI-tested; uses `minephys.environment`):
  - dust post-model (FR-013-11 to FR-013-15);
  - haze, exposure and pinhole models (FR-013-16 to FR-013-20);
  - quantiser (FR-013-35);
  - S1 metrics (FR-013-36, FR-013-37).

  They run in `pipeline/` stages `s05_synthesize`, `s50_evaluate` and `s60_export`.
- **Web**: a dust worker and the slider (FR-013-38, FR-013-39), and the sensor-comparison widget and honesty states
  (FR-013-40, FR-013-41) in `web/`.

## Technical context

Runtimes:
- `studio/rtx/`: Python 3.12. Locked: ovrtx 0.5.0.377615, ovstage 0.2.0.377349 and ovphysx 0.6.3 from NVIDIA's
  explicit index, plus numpy, openexr and pyyaml. Added and locked by T-013-002 before feature code: pyarrow, zarr,
  jsonschema and `minephys` (git), all with cp312 or pure wheels. Never imported in the same process as Kit or Isaac
  Sim.
- `studio/isaac/`: Python 3.12, Isaac Sim 6.1.0.0 (or 6.0.0.1 by the Compatibility Checker); used for the rain arm
  only.
- Root and `pipeline/`: Python 3.14; numpy, minephys, pyarrow, zarr; `mmh3` as a test-only reference (dev group).
- `web/`: Node 24, TypeScript, a Web Worker; Vitest and Playwright.

Target: the reference laptop GPU (local, `gpu0.compute` lock, FR-000-13) for rendering; CI (CPU) for everything else
through the fake backend. GPU tests are marked `gpu` and run only locally.

## Constitution check

| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | Real Bingham terrain and our own USD scenes; synthetic sensor data labelled "calibrated synthetic — not validated against real data" (FR-000-09); rule thresholds from a real field study (spec §7 A1) |
| Spec before code | yes | Every behaviour has an FR/P/NFR ID; post-model rule fixed in FR-013-12 and FR-013-13 |
| Acceptance-test-first | yes | Every task in `tasks.md` is a `[red]`/`[green]` pair; GPU behaviours are first tested against the fake backend |
| Independent oracles | yes | Analytical (Beer–Lambert, pinhole, haze), reference implementations (`mmh3`, `scipy.ndimage.label`, `scipy.spatial.cKDTree`), published values (abstract A1, ovrtx issue values A2), hand calculations (spec §7); see the test strategy |
| Determinism and tolerances | yes | Post-models `bitwise`; RTX outputs `statistical` with stated re-run tolerances (FR-013-34); tolerances justified in spec §7 |
| Neutral contracts | yes | DC-013-01 to DC-013-05 are new JSON Schema 2020-12 files with generated types (T-013-001); DC-013-07, DC-013-08 reuse foundation contracts |
| Static delivery | yes | RTX outputs are REPLAY; the dust slider is LIVE on a baked frame with a clean-frame fallback (FR-013-39); poster frames when no shard loads |
| Honesty | yes | "not yet run" (FR-013-41), radar-immunity label (FR-013-24), performance local-only card (FR-013-40), UNVERIFIED items listed (spec §7) |
| Licence hygiene | yes | Clean-room adapter and repository scan (FR-013-33); no NVIDIA asset; `performance: local-only` (FR-013-32); outputs CC-BY-4.0 |
| Simplicity | yes | One interface with two real backends (`ovrtx`, `isaac`) plus `fake`; post-models are plain NumPy functions; adapter ≤ 400 lines (NFR-013-04) |

## Design

![Sensor lane: USD stage → ovrtx → own dust model → point-count guard → shards](../../docs/assets/diagrams/sensor-lane-ovrtx.svg)

Related diagram: `docs/assets/diagrams/lidar-dust-beer-lambert.svg` (dust rule). The S4b slope radar is specified in
spec 010-slope.

| Component | Location | Requirements |
|---|---|---|
| `SensorBackend` protocol, factory, isolation check | `studio/rtx/src/pitstudio_rtx/backend.py` (pure Python, no third-party import; also loaded by path by the `isaac` backend) | FR-013-01, FR-013-03 |
| `ovrtx` backend (renderer, ovstage attach, render products, warm-up, sign normalisation) | `studio/rtx/src/pitstudio_rtx/backends/ovrtx_backend.py` — written from the API documentation only | FR-013-07, FR-013-19, FR-013-21 to FR-013-23, NFR-013-04 |
| `fake` backend (scripted frames, empty frames, malformed frames) | `studio/rtx/src/pitstudio_rtx/backends/fake.py` | test double for every lane behaviour |
| Lane entry `st53_sensors`: recipe validation, envelope, guard loop, output validation, index | `studio/rtx/src/pitstudio_rtx/lane.py` | FR-013-04, FR-013-05, FR-013-08 to FR-013-10, FR-013-30 |
| Probe `ovrtx` | `studio/bench/probe_ovrtx.py` | FR-013-06 |
| Shard writer | `studio/rtx/src/pitstudio_rtx/shards.py` | FR-013-31 |
| Re-run check | `studio/rtx/src/pitstudio_rtx/rerun.py` (cloud and image comparisons in NumPy) | FR-013-34 |
| `isaac` sensor backend and `st57_rain_lidar` | `studio/isaac/src/pitstudio_isaac/sensor_backend.py` | FR-013-29, FR-013-30 |
| Dust post-model, beam hash | `src/pitstudio/sensors/dust.py`, `src/pitstudio/sensors/beamhash.py` | FR-013-11 to FR-013-15 |
| Camera post-models (haze, exposure, pinhole, component boxes) | `src/pitstudio/sensors/camera.py` | FR-013-16 to FR-013-20 |
| S1 metrics and lidar-vs-radar comparison | `src/pitstudio/sensors/metrics.py` (uses the shared decision-rule helper of FR-000-05) | FR-013-36, FR-013-37, FR-013-42 |
| Web quantiser and slider bake | `src/pitstudio/sensors/quantise.py`; called by `s60_export` | FR-013-35, FR-013-38 (bake side), FR-013-42 |
| Manifest marker writer | lane stage wrapper (runner integration) | FR-013-32 |
| Repository scan | `tests/unit/test_t_013_072_clean_room.py` (also run by `tools/check_repo.py`) | FR-013-33 |
| Dust worker, slider, widget | `web/src/engines/sensors/` | FR-013-38 to FR-013-41, NFR-013-01, NFR-013-02 |

**Data flow.** `st40_compose` (USD stage) and kinematic poses (A1 DES or Rapier traces) → `st53_sensors` writes clean
shards and the index → `s05_synthesize` writes dusty clouds (uniform grid and C3 fields), hazy S3 images, exposed S2
images → `s50_evaluate` writes the S1 metrics → `s60_export` writes web shards and the slider bake.
Rain: `st57_rain_lidar` → the same contracts.

## Test strategy

| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-013-01 | unit | static import-graph scan (no NVIDIA module outside backends) + protocol conformance of `fake` | pytest + `ast` |
| FR-013-02 | unit | import-graph scan of `src/pitstudio/sensors/` and the lane | pytest + `ast` |
| FR-013-03 | unit | hand-built `sys.modules` states (Kit present → error before construction) | pytest |
| FR-013-04 | unit | hostile recipe corpus (each case violates exactly one rule), expected exit 2 and JSON pointer | pytest + jsonschema |
| FR-013-05 | unit | envelope fixtures with pass, fail and missing entries; version mismatch | pytest |
| FR-013-06 | contract + gpu | schema of the written envelope; no timing key; local render of the probe scene | pytest (`gpu` marker local) |
| FR-013-07 | unit | fake backend `step` counter: 40 discarded + N recorded | pytest |
| FR-013-08 | unit | fake backend with an empty frame at index k: `step` calls = k + 1, error class, nothing promoted | pytest |
| FR-013-09 | unit | malformed-frame corpus (dtype, shape, NaN, flag/count mismatch) | pytest + Hypothesis |
| FR-013-10 | contract | index rows equal the fake frames' known beam and valid counts | pytest |
| FR-013-11 | unit | analytical: uniform β gives τ = βR, I = I₀e^(−2βR); piecewise-constant β gives the exact sum | pytest |
| FR-013-12 | unit | hand calculation of keep/drop at τ just below and above τ_on and τ_floor; the linear law in u | pytest |
| FR-013-13 | unit | analytical r_edge for clouds starting at a known range; counts per sensor `max_returns` | pytest |
| FR-013-14 | unit + parity | reference implementation `mmh3.hash` (unsigned) on the 12-byte key; TS known-answer vectors | pytest + Vitest |
| FR-013-15 | unit | hostile profile corpus | pytest + Hypothesis |
| FR-013-16 | unit | analytical haze values for constant β; sky-pixel path to the box exit | pytest |
| FR-013-17 | unit | reference implementation `scipy.ndimage.label` (8-connectivity) and box extents | pytest |
| FR-013-18 | unit | analytical S; statistical variance check (P-013-08 MR4); cos⁴θ at known pixel angles | pytest |
| FR-013-19 | unit + gpu | hand calculation of the GSD worked example (p_x = 4 µm, f = 8.8 mm, H = 100 m → 4.5 cm); local marker projection within 0.5 px | pytest |
| FR-013-20 | unit | hostile parameter corpus | pytest + Hypothesis |
| FR-013-21 | unit | hostile radar configurations (λ = 3.69 / 3.96 mm, BVH off, camera product present) | pytest |
| FR-013-22 | contract | schema of the detection shard; sign normalisation on scripted fake detections | pytest |
| FR-013-23 | integration (gpu) | analytical kinematics: radial velocity = −11.11 m/s for a boresight approach | pytest (`gpu`, local) |
| FR-013-24 | unit + E2E | radar output unchanged across dust settings (fake); label present on comparison charts | pytest + Playwright |
| FR-013-29 | unit + gpu | fake `isaac` backend: guards applied and contract shared; local render at 0 and 50 mm/h | pytest |
| FR-013-30 | unit | fake probe states and applied-rate mismatch; rain on `ovrtx` | pytest |
| FR-013-31 | unit + contract | file sizes ≤ 10 MB on oversized fake outputs (split into shards); SHA-256 recomputed with `hashlib` | pytest |
| FR-013-32 | contract | manifest schema + licence guard on a fake-run manifest (no performance field) | pytest |
| FR-013-33 | unit | repository scan over `studio/rtx/` and the isaac sensor backend; planted-violation fixture | pytest |
| FR-013-34 | unit + gpu | analytical Chamfer distance of shifted clouds via `scipy.spatial.cKDTree`; PSNR by hand calculation | pytest |
| FR-013-35 | unit | analytical error bound (P-013-11) | pytest + Hypothesis |
| FR-013-36 | unit | synthetic labelled clouds with known P_d per bin; hand calculation of TTC margins (R_det = 50 m, 40 km/h → 4.50 s − 3 s = 1.50 s) | pytest |
| FR-013-37 | unit | decision-rule fixtures (CI including and excluding 0) | pytest |
| FR-013-38 | parity + E2E | Python post-model goldens (P-013-15) | Vitest + Playwright |
| FR-013-39 | web unit + E2E | hostile asset corpus (bad hash, NaN, τ_ref = 0, oversized, level 41; corrupted replay shard → poster frame) | Vitest + Playwright |
| FR-013-42 | unit | hostile metric and quantiser inputs; degenerate-axis hand calculation | pytest + Hypothesis |
| FR-013-40 | E2E | DOM assertions: four views, badges, provenance, local-only card | Playwright |
| FR-013-41 | E2E | empty manifest fixture → "not yet run" | Playwright |
| P-013-01 | property | invariant (identity) | Hypothesis (≥ 200 examples) |
| P-013-02 | property | analytical identities | Hypothesis |
| P-013-03 | metamorphic | monotonicity relation | Hypothesis |
| P-013-04 | metamorphic | permutation relation | Hypothesis |
| P-013-05 | metamorphic | class-dominance relation | Hypothesis |
| P-013-06 | property | published anchors (spec §7 A1) + binomial bound | pytest |
| P-013-07 | metamorphic | analytical identities of the haze model | Hypothesis |
| P-013-08 | metamorphic | analytical scaling + χ² interval (`scipy.stats.chi2`) | Hypothesis + pytest |
| P-013-11 | property | analytical bound | Hypothesis |
| P-013-12 | property | reference implementation `mmh3`; `scipy.stats.kstest` | pytest |
| P-013-13 | metamorphic | relations on synthetic clouds | Hypothesis |
| P-013-14 | metamorphic | analytical pinhole identities | Hypothesis |
| P-013-15 | parity | Python reference goldens | Vitest |
| NFR-013-01 | E2E | measured timing on T2 | Playwright |
| NFR-013-02, NFR-013-03 | CI | byte sizes | budget check |
| NFR-013-04 | CI | line count | `tools/check_repo.py` |
| NFR-013-05 | unit | schema limits | pytest |
| SC-013-01 to SC-013-03 | aggregate | the properties and contracts above, on the published artefacts | pytest + Vitest |

## Risks and complexity tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Two Python homes for one feature (3.12 lane, 3.14 post-models) | NVIDIA runtimes need 3.12; open numerical code must be CI-tested and never share a process with an RTX runtime | Post-models inside `st53_sensors` would be untested in CI and run beside the proprietary runtime |
| A probe-written envelope file instead of a fixed constant | ovrtx#3 depends on fan and mount rotation and on exact versions | A fixed range cannot follow version upgrades; the file is re-written by the probe |
| A hashed per-beam value u instead of a random generator | Exact Python–TypeScript parity and permutation invariance | A PRNG stream depends on iteration order and on browser transcendental precision |
| Threshold dust rule (step + linear) | The paper gives anchors, not a curve; full text unreadable (U1) | A fitted curve would invent constants the source does not give |

Open risks: pre-release ovrtx API churn (thin adapter, exact pins); the rain arm depends on Isaac Sim passing its
probe (otherwise "not run"); the RTX re-run check may fail on a vendor update (recorded, shown on the run card).
