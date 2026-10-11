# Spec 013 — RTX sensor simulation (M23): truck lidar in dust and rain, survey and crusher cameras, proximity radar
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Perception in an open pit fails where it matters most: in dust, rain and at night. This feature turns PitStudio's own
USD pit scenes into sensor data with exact ground truth for those conditions. ovrtx (kit-less RTX renderer, Python
3.12, `studio/rtx/`) renders four scenarios: **S1** truck collision-avoidance lidar (rotary and solid-state), **S2**
drone survey camera, **S3** fixed crusher camera and **S4a** 77 GHz proximity radar. Isaac Sim renders the S1 **rain**
arm, because ovrtx does not expose the rain setting. A physical effect that no RTX model provides is PitStudio's own
open model: a **Beer–Lambert dust post-model** for lidar and cameras, calibrated to a mining dust study and built on
`minephys.environment`. The renderer is reached only through a thin `SensorBackend` adapter, written from the API
documentation and never from NVIDIA examples. Every lidar frame passes a point-count guard against a known ovrtx
defect. Outputs are shards of at most 10 MB. Rendering performance stays local-only (NVIDIA SLA §8.9). The web gets a
live dust slider (own model, exact parity with Python) and replayed sensor frames.

**Who benefits:** safety and autonomy engineers (case B1), perception practitioners (B2), surveyors (E2) and
developers who want a reproducible RTX sensor lane on one workstation.

**Out of scope:**
- volumetric radiative transfer inside the renderer (dust is a calibrated post-model);
- any vendor sensor model or NVIDIA sensor asset;
- validation against real sensor recordings (no licence-clean real set exists, so outputs are "calibrated synthetic");
- the Replicator instance-mask arm of S3 (spec 009-perception);
- the S4b slope-radar series, its generation and its forecasting (spec 010-slope);
- the C3 dust field itself (spec 005-physics; this spec consumes its extinction field).

## 2. User stories

| ID | Priority | Story | Independent test |
|---|---|---|---|
| US-013-1 | P1 | As a safety engineer, I want truck-lidar frames of a real-geometry haul road rendered clean and then degraded by dust at known transmittance, with exact target labels and a radar comparison, so that I can read detection probability and time-to-collision margin against dust. | A fake-backend S1 run plus the dust post-model produces P_d per range bin and transmittance level that match the analytical expectation of the rule (FR-013-12) on synthetic clouds. |
| US-013-2 | P1 | As a web visitor, I want a dust slider that re-attenuates a baked lidar frame live in my browser with the same model the studio uses, so that I can see how dust removes distant returns and adds dust returns. | The TS worker reproduces the Python post-model on golden frames at every slider level (P-013-15). |
| US-013-3 | P1 | As the maintainer, I want the sensor lane to fail fast on an empty lidar frame or an untested elevation fan, never to load two RTX runtimes in one process, and never to publish NVIDIA performance data or NVIDIA-derived code, so that defects and licence traps cannot reach a published artefact. | Fake-backend runs with an empty frame, an untested fan, a mixed-runtime process and a manifest with timings are each refused. |
| US-013-4 | P2 | As a surveyor or perception engineer, I want drone-survey images with exact camera poses, intrinsics and ground-truth depth, and crusher-camera images with semantic labels and dust haze, so that photogrammetry (E2) and boulder detection (B2) are trained and scored against exact truth. | Analytical camera fixtures check the pinhole model, GSD, exposure/noise and haze post-models. |
| ~~US-013-5~~ | — | Retired: the S4b slope-radar story moved to spec 010-slope (US-010-4). | superseded by US-010-4 (integration 2026-10-07) |
| US-013-6 | P3 | As a safety engineer, I want the same S1 poses rendered in rain through Isaac Sim, so that rain and dust can be compared. | A fake `isaac` backend run writes rain shards in the S1 contract or reports "not run" with the reason. |

## 3. Functional requirements (EARS)

### 3.1 Lane, backend and isolation

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-013-01 | Ubiquitous | The sensor lane shall reach any RTX renderer only through a `SensorBackend` interface with exactly four operations — `describe() → BackendInfo` (name, versions read from the environment lock, capabilities), `open(stage, sensors) → Session`, `step(session, frame_poses) → FrameOutputs` and `close(session)` — implemented by `ovrtx` (`studio/rtx/`), `isaac` (`studio/isaac/`) and `fake` (tests); no module outside a backend implementation shall import `ovrtx`, `ovstage`, `ovphysx`, `isaacsim`, `omni` or `carb`. | unit (import-graph scan + fake backend) |
| FR-013-02 | Ubiquitous | The dust post-model, the camera post-models, the S1 metrics and the web-shard quantiser shall be pure Python + NumPy (+ `minephys`) code, executed by the pipeline stages `s05_synthesize`, `s50_evaluate` and `s60_export` on schema-validated `st53_sensors` shards; the RTX lane itself shall contain only the backends, recipe validation, guards and the shard writer. | unit (import-graph scan) |
| FR-013-03 | Unwanted | If the `ovrtx` backend is requested in a process in which any `omni.kit*`, `isaacsim*` or `carb` module is already imported, or the `isaac` backend is requested in a process in which `ovrtx` is imported, then the backend factory shall raise `RuntimeIsolationError` before creating any renderer object. | unit (hostile: fake modules in `sys.modules`) |
| FR-013-04 | Unwanted | If a sensor recipe is not valid against `contracts/sensor-recipe.schema.json` — unknown sensor kind or key (`additionalProperties: false`, so no vendor profile or sensor-asset reference can be expressed), non-finite or out-of-range number, a length not in metres, an angle not in degrees, an asset reference with a URL scheme (`omniverse:`, `http:`, `https:`, `file:`) or a path outside the stage's declared inputs (including `..` traversal), a camera above 1920 × 1080 px, or an S1 elevation beyond ±45° — then `st53_sensors` shall exit with code 2 before opening a backend, name the offending JSON pointer, and promote no output. | unit (hostile) |
| FR-013-05 | Unwanted | If any lidar configuration (scan type, elevation fan [e_min, e_max], azimuth fan, mount rotation) of a recipe is not listed with status `pass` in `studio/rtx/lidar-envelope.json` (`contracts/lidar-envelope.schema.json`) for the same ovrtx and ovstage versions as the environment lock, or the envelope file is missing or invalid, then `st53_sensors` shall exit with code 2 before rendering, naming the sensor and the untested configuration. | unit (hostile, fake backend) |
| FR-013-06 | Event | When the `ovrtx` capability probe runs, it shall render every lidar configuration referenced by the committed sensor recipes once, on a probe scene of a ground plane and a 2 m cube at 20 m, and write `pass` (more than 0 valid points) or `fail` per configuration into `studio/rtx/lidar-envelope.json`, with ovrtx and ovstage versions read from `studio/rtx/uv.lock` and no timing, throughput or memory field. | contract + gpu (local) |
| FR-013-07 | Event | When a scene is loaded or a sensor setting changes, the `ovrtx` backend shall render and discard 40 warm-up frames before the first recorded frame, and no warm-up frame shall reach a shard. | unit (fake backend counts `step` calls) |
| FR-013-08 | Unwanted | If a clean lidar frame returned by a backend has zero valid points (returns with the valid flag `0x40`), then `st53_sensors` (and `st57_rain_lidar`) shall stop at that frame without calling `step` again, fail the stage with error class `lidar-zero-points` naming the sensor and frame index, and promote no output of the run. | unit (fake backend returns an empty frame at index k; `step` called exactly k + 1 times) |
| FR-013-09 | Unwanted | If a backend returns a frame whose arrays have an unexpected dtype or shape, non-finite coordinates, intensities, RCS or radial velocities on valid entries, a valid-point count that disagrees with the flags, or image arrays whose size differs from the configured resolution, then the stage shall fail with error class `backend-output-invalid` naming the field, and promote no output. | unit (hostile, fake backend) |
| FR-013-10 | Ubiquitous | `st53_sensors` shall record for every lidar frame the emitted beam count and the valid point count in the shard index (counts are outputs, not performance data). | contract |

### 3.2 Dust post-model (lidar)

The post-model acts on the clean RTX cloud. Optical depth along a beam is τ(R) = ∫₀ᴿ β(s) ds and one-way transmittance
is T₁ = e^(−τ). Thresholds come from Phillips, Guenther & McAree (2017): dust starts to affect measurements below an
atmospheric transmittance of 71–74 %; a target is still ranged down to 2 % if retroreflective and 6 % if of low
reflectivity (§7 A1).

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-013-11 | Ubiquitous | For every clean return at range R (m) on a beam with extinction profile β(s) (m⁻¹) sampled at spacing Δs ≤ 0.5 m from the C3 dust field, the dust post-model shall compute τ(R) with the transmittance functions of `minephys.environment` and set the intensity of a kept return to I₀ · e^(−2τ) (two-way path), leaving its range and position unchanged. | unit (analytical) |
| FR-013-12 | Ubiquitous | The dust post-model shall classify each return by its material class m — `retro` if its non-visual material carries the retroreflective attribute, otherwise `diffuse` — with τ_on = 0.3216 (T₁ = 0.725), τ_floor(retro) = 3.9120 (T₁ = 0.02) and τ_floor(diffuse) = 2.8134 (T₁ = 0.06), and shall (a) keep the return if τ ≤ τ_on, (b) for τ_on < τ ≤ τ_floor(m) keep it if and only if u · (τ_floor(m) − τ_on) < τ_floor(m) − τ, where u ∈ [0, 1) is the beam value of FR-013-14, and (c) drop it if τ > τ_floor(m). | unit (analytical) |
| FR-013-13 | Ubiquitous | For every beam with τ(R) > τ_on whose return is dropped, and for every beam with τ(R) > τ_on of a sensor with `max_returns` ≥ 2, the dust post-model shall emit exactly one dust return at the leading edge of the dust cloud, r_edge = the smallest sample range s < R with β(s) > 1 × 10⁻⁶ m⁻¹, with class `dust` and intensity equal to the recipe's `dust_return_intensity` (a display value with no physical claim). | unit (analytical) |
| FR-013-14 | Ubiquitous | The beam value u shall be h / 2³² with h = MurmurHash3_x86_32 (seed 0) of the 12-byte little-endian key (frame index, beam index, run seed) as unsigned 32-bit integers, so that Python and TypeScript produce identical u. | unit (reference implementation) + parity |
| FR-013-15 | Unwanted | If a β profile contains a negative, NaN or infinite value, has a sample spacing ≤ 0 or > 0.5 m, does not reach the return's range, or a return has a non-finite or non-positive range, a material class other than `retro`/`diffuse`, or arrays of mismatched length, then the dust post-model shall raise `ValueError` naming the beam index and return no partial cloud. | unit (hostile) |

### 3.3 Camera post-models (S2 drone camera, S3 crusher camera)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-013-16 | Ubiquitous | For every S3 pixel with clean linear radiance J (`HdrColor`, float16 promoted to float32), airlight A (recipe, linear RGB) and camera-ray optical depth τ_c = ∫₀ᵈ β ds to the ground-truth distance d (`DistanceToCameraSD`, m), the haze post-model shall output I = J · t + A · (1 − t) per channel, with t = e^(−τ_c); for pixels without a hit (non-finite distance), τ_c is integrated to the exit of the dust field's bounding box. | unit (analytical) |
| FR-013-17 | Ubiquitous | The S3 lane shall derive one 2-D box per 8-connected component of each semantic class in `SemanticSegmentation` with area ≥ the recipe's `min_box_area_px` (default 16 px), recorded with the note "boxes from semantic components; touching instances merge" (instance-accurate boxes come from spec 009's Replicator arm). | unit (reference implementation) |
| FR-013-18 | Ubiquitous | On linear S2 radiance L the exposure post-model shall compute the signal S = κ · L · t_e / N² (electrons), apply natural vignetting cos⁴θ (θ the angle between the pixel ray and the optical axis) when `vignetting: true`, add zero-mean Gaussian noise of variance S + σ_read² drawn from a counter-based generator keyed by (run seed, image index, pixel index), and output DN = clip(round(G · (S + n)), 0, DN_max). | unit (analytical + statistical) |
| FR-013-19 | Ubiquitous | S2 shall render with an ideal pinhole camera whose intrinsic matrix K is derived from the recipe's focal length f, pixel pitch p_x, resolution and principal point, and shall record K, the world-from-camera pose of every image and the ground-sampling distance GSD = p_x · H_agl / f in the image index. | unit (analytical) + gpu (local: a marker projects within 0.5 px) |
| FR-013-20 | Unwanted | If a camera post-model receives NaN or infinite radiance, a finite distance ≤ 0, arrays whose shapes differ, t_e ≤ 0, N ≤ 0, κ ≤ 0, G ≤ 0, σ_read < 0, DN_max < 1 or an airlight outside [0, 10⁶], then it shall raise `ValueError` naming the parameter and write no image. | unit (hostile) |

### 3.4 Proximity radar (S4a)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-013-21 | Unwanted | If an S4a radar is configured with a wavelength outside 3.70–3.95 mm (76–81 GHz), with Motion BVH disabled, or in a renderer session that also holds a camera render product, then `st53_sensors` shall exit with code 2 before rendering. | unit (hostile, fake backend) |
| FR-013-22 | Ubiquitous | S4a shall write per detection the position (m, sensor frame), RCS (dBsm), radial velocity (m/s) normalised by the adapter to the PitStudio convention "positive = range increasing" and, where available, the object id, to Parquet shards of `contracts/sensor-shard.schema.json`. | contract |
| FR-013-23 | Event | When the S4a validation scene (a light vehicle approaching the stationary sensor along the boresight at 11.11 m/s, from 80 m to 20 m) is rendered, the median normalised radial velocity of the detections on the vehicle shall be −11.11 m/s within max(`velResMps`, 0.25 m/s), and the adapter shall record the native sign convention it observed. | integration (gpu, local) |
| FR-013-24 | Ubiquitous | The S4a outputs shall not depend on any dust setting, and every artefact or chart that compares lidar with radar under dust shall carry the label "radar dust immunity assumed (UNVERIFIED)". | unit + E2E |

### 3.5 Slope-monitoring radar (S4b) — moved to spec 010-slope

The S4b slope-radar series is specified in spec 010-slope (§3.4, FR-010-34…37, FR-010-41, FR-010-42).

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| ~~FR-013-25~~ | — | Retired: LOS projection of the S4b generator. | superseded by FR-010-34, FR-010-41 (integration 2026-10-07) |
| ~~FR-013-26~~ | — | Retired: S4b phase, noise and unwrapping. | superseded by FR-010-41 (integration 2026-10-07) |
| ~~FR-013-27~~ | — | Retired: S4b wrap-ambiguity flag. | superseded by FR-010-36, FR-010-41 (integration 2026-10-07) |
| ~~FR-013-28~~ | — | Retired: S4b hostile inputs. | superseded by FR-010-37, FR-010-42 (integration 2026-10-07) |

### 3.6 Rain arm (Isaac Sim)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-013-29 | Optional | Where the `isaacsim` capability probe passes, `st57_rain_lidar` shall render the S1 poses and lidar configurations through the `isaac` backend with the Mie rain model at the recipe's rain rates (default {0, 2, 10, 50} mm/h), apply FR-013-04, FR-013-05, FR-013-08 and FR-013-09, and write shards in the same contract as `st53_sensors`. | unit (fake) + integration (gpu, local) |
| FR-013-30 | Unwanted | If the `isaacsim` probe is not `pass`, or the `isaac` backend reports an applied rain rate different from the requested one, then the rain arm shall be recorded "not run" with the reason and no rain artefact shall be published; and if a recipe requests a non-zero rain rate on the `ovrtx` backend, then `st53_sensors` shall exit with code 2 and the message "rain is available only on the isaac backend". | unit (hostile, fake) |

### 3.7 Outputs, manifests, licence and determinism

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-013-31 | Ubiquitous | Every output file of `st53_sensors` and `st57_rain_lidar` shall be ≤ 10 MB: point clouds and radar detections as Parquet shards, dense per-pixel arrays (HDR colour, distance, semantic ids) as Zarr v3 chunks, LDR images as PNG; every file shall be listed with its byte size and SHA-256 in a shard index valid against `contracts/sensor-shard.schema.json`. | unit + contract |
| FR-013-32 | Ubiquitous | Every manifest of `st53_sensors` and `st57_rain_lidar` shall carry `performance: local-only`, the outputs' licence class `own` (CC-BY-4.0) and the runtime's class `reference-only`, and every committed or published copy shall contain no wall time, throughput, frame time, memory or telemetry value for these stages (each replaced by "measured locally, not published (licence)"). | contract (manifest guard) |
| FR-013-33 | Ubiquitous | Every source file under `studio/rtx/` and the sensor backend of `studio/isaac/` shall carry an `SPDX-License-Identifier: Apache-2.0` header and shall contain none of the NVIDIA sample-code notices ("This software contains source code provided by NVIDIA Corporation", "NVIDIA CORPORATION & AFFILIATES. All rights reserved", `LicenseRef-NvidiaProprietary` in a source header); no recipe or scene of this lane shall reference an NVIDIA sensor or scene asset. | unit (repository scan) |
| FR-013-34 | Event | When the determinism re-run check re-renders one shard, the lane shall compare it with the original and record `determinism.class = statistical` and `rerun_check = pass` only if every frame's valid point count differs by ≤ 1 %, the symmetric mean Chamfer distance of each cloud is ≤ 3 × `rangeAccuracyM`, and every LDR image has PSNR ≥ 40 dB against its original; otherwise it records `fail` with the failing measure. | unit (fake) + gpu (local) |
| FR-013-35 | Ubiquitous | `s60_export` shall convert S1, S4a and rain clouds into web shards of `contracts/web-cloud-shard.schema.json`, each ≤ 10 MB: positions as 16-bit codes per axis over the shard's bounding box (offset and scale per axis and the code type `uint16` declared in the header field `encoding.position`, which the viewer reads, as for the replay shards of DC-018-03), intensity as uint8, class as uint8, and the SHA-256 of every shard in the asset manifest. | unit |

### 3.8 S1 metrics

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-013-36 | Ubiquitous | For every S1 run the metrics module shall compute, per target (light vehicle, person with retroreflective vest, boulder, oncoming truck), per 5 m range bin and per transmittance level of the pre-registered grid T₁ ∈ {1.0, 0.9, 0.74, 0.5, 0.3, 0.1, 0.06, 0.02} (uniform dust layer between sensor and target) and per C3 dust-field run: the detection probability P_d (fraction of frames with ≥ `k_min` target points, default 3), the points on target, the false dust returns per 10⁴ beams, and for v ∈ {30, 40, 50} km/h the TTC margin at detection R_det / v − 3 s, with R_det the largest range bin whose P_d ≥ 0.9. | unit (analytical fixtures) |
| FR-013-37 | Ubiquitous | The lidar-versus-radar comparison shall report the detection range of each sensor per dust level, and shall call one sensor "better" only by the decision rule of FR-000-05 on paired frames, otherwise "no significant difference". | unit |
| FR-013-42 | Unwanted | If the metrics module or the web-shard quantiser receives a shard or cloud that fails its schema, a non-finite coordinate, `k_min` < 1, an empty transmittance grid, a speed ≤ 0, a range bin width ≤ 0, or a target id absent from the scene labels, then it shall raise `ValueError` naming the input and write no metric or shard; a zero extent on an axis shall be quantised with scale 1 and offset at the common value. | unit (hostile) |

### 3.9 Web

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-013-38 | Event | When the visitor moves the dust slider, the web app shall re-attenuate the baked clean S1 frame in a Web Worker with the TypeScript port of FR-013-11 to FR-013-14, using the baked per-return inputs (quantised position, I₀ as uint8, class, τ at unit dust load as float32, r_edge as float32, h as uint32) and the baked slider levels k_j (41 levels, log-spaced in τ, from T₁ = 1.0 to T₁ = 0.02 on the reference target), and shall display the frame with a LIVE badge and the label "own Beer–Lambert dust model". | parity (web unit) + E2E |
| FR-013-39 | Unwanted | If the baked slider asset fails its SHA-256 or `contracts/dust-slider.schema.json`, holds a NaN, infinite or negative τ, a reference-target τ of 0, or more than 150,000 returns, or the slider receives a level outside 0…40, then the worker shall reject it, keep showing the clean frame, and the panel shall show "dust model unavailable — clean frame shown"; and if a replay cloud shard fails its SHA-256 or `contracts/web-cloud-shard.schema.json`, then the viewer shall not render it and shall show the poster frame. | web unit + E2E (hostile) |
| FR-013-40 | Ubiquitous | The sensor-comparison widget shall show one frame as RGB, semantic, lidar and radar (diverging Doppler colour map centred on 0 m/s), each with a REPLAY badge and provenance (producing tool, run id, commit), and shall show rendering performance only as the card "measured locally, not published (licence)". | E2E |
| FR-013-41 | Unwanted | If no S1–S4a artefact is published, then the B1, B2 and E2 sensor panels and the ovrtx tool page shall show "not yet run" (FR-000-07) and no placeholder image. | E2E |

## 4. Correctness properties

Numerical cores and their metamorphic relations (MR): dust post-model (P-013-01 to P-013-06), haze (P-013-07),
exposure (P-013-08), quantiser (P-013-11), beam hash (P-013-12), S1 metrics (P-013-13),
pinhole (P-013-14), web parity (P-013-15).

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-013-01 | MR zero dust: for any clean cloud with β ≡ 0, the dusty cloud equals the clean cloud (positions and intensities) and holds no dust return. | clouds of 1–10⁵ returns, ranges 0.5–250 m, both classes | exact |
| P-013-02 | MR additivity and two-way law: τ over [0, R₁ + R₂] equals τ[0, R₁] + τ[R₁, R₁ + R₂]; e^(−2τ) equals (e^(−τ))²; τ(0) = 0 so T₁(0) = 1. | β profiles with values 0–1 m⁻¹, Δs 0.01–0.5 m | rtol 1e-12 (float64) |
| P-013-03 | MR monotonicity: scaling β by k ≥ 1 never keeps a return that is dropped at k = 1 and never raises a kept intensity; moving a target farther along the same beam profile never raises T₁. | k ∈ [1, 100]; Hypothesis profiles | exact (decisions), rtol 1e-12 (intensity) |
| P-013-04 | MR permutation: permuting the order of beams in the input permutes the output identically (u depends on beam index, not array position). | random permutations | exact |
| P-013-05 | MR class dominance: at equal τ and u, a `retro` return is kept whenever a `diffuse` return is kept. | τ ∈ [0, 5], u ∈ [0, 1) | exact |
| P-013-06 | Calibration anchors: under a uniform layer, the kept fraction of `diffuse` returns is 1 for T₁ ≥ 0.725 and 0 for T₁ < 0.06; of `retro` returns 1 for T₁ ≥ 0.725 and 0 for T₁ < 0.02; at τ midway between τ_on and τ_floor(m) the empirical kept fraction over 10⁵ beams is 0.5. | 10⁵ beams per level | exact at the anchors; ±0.0063 at midway (4 binomial σ) |
| P-013-07 | Haze MRs: (MR1) τ_c = 0 or d = 0 gives I = J; (MR2) A = J gives I = J for every t; (MR3) I(aJ, aA) = a · I(J, A) for a > 0; (MR4) I lies between J and A per channel and tends to A as τ_c grows. | J, A ∈ [0, 10⁴]; τ_c ∈ [0, 20] | rtol 1e-6 (float32) |
| P-013-08 | Exposure MRs (noise off unless stated): (MR1) doubling t_e doubles S; (MR2) N → N/√2 doubles S; (MR3) DN never exceeds DN_max and never falls below 0; (MR4, noise on) the sample variance of S + n over 10⁵ draws lies in the two-sided 99.9 % χ² interval of S + σ_read². | L ∈ [0, 10³], t_e ∈ [10⁻⁵, 1] s, N ∈ [1.4, 22] | rtol 1e-6; statistical as stated |
| ~~P-013-09~~ | Retired: S4b projection relations. | — | superseded by P-010-15, P-010-16 (integration 2026-10-07) |
| ~~P-013-10~~ | Retired: S4b wrapping relations. | — | superseded by P-010-15, P-010-17 (integration 2026-10-07) |
| P-013-11 | Quantiser MRs: (MR1) each dequantised coordinate is within extent/(2 · 65,535) of the original; (MR2) translating the cloud leaves the quantisation errors unchanged; (MR3) permuting points permutes the shard identically. | clouds with extents 1–2,000 m | bound + 1e-9 · extent |
| P-013-12 | Beam hash: h equals the reference MurmurHash3_x86_32 for every key; u ∈ [0, 1); over 10⁶ consecutive beams a Kolmogorov–Smirnov test against U(0, 1) gives p > 0.001. | frames 0–10⁵, beams 0–2 × 10⁵, seeds 0–2³²−1 | exact; statistical |
| P-013-13 | S1 metrics MRs: (MR1) P_d is non-increasing in `k_min`; (MR2) duplicating every frame leaves P_d unchanged; (MR3) doubling v halves R_det / v. | synthetic labelled clouds | exact |
| P-013-14 | Pinhole MRs: (MR1) projecting a world point with K[R | t] and back-projecting the pixel with its ground-truth distance returns the point; (MR2) GSD is linear in H_agl and p_x and inversely proportional to f; (MR3) a common rigid motion of camera and scene leaves pixel coordinates unchanged. | points 1–1,000 m from the camera | atol 1e-6 m; rtol 1e-12 |
| P-013-15 | Web parity: on ≥ 3 golden frames at all 41 slider levels, the TypeScript worker and the Python post-model give identical keep/drop decisions, dust-return counts and r_edge values, intensities within rtol 1e-12, and identical uint8 display intensities. | golden frames of ≤ 150,000 returns | exact / rtol 1e-12 |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-013-01 | Live dust slider interaction on the T2 (WASM/JS) tier, one level change on a baked frame of ≤ 150,000 returns | ≤ 16 ms (lane gate, FR-000-15) | Playwright timing on the reference browser set |
| NFR-013-02 | Baked slider asset per frame; dust worker JavaScript | ≤ 10 MB; ≤ 50 KB gzip | CI budget check |
| NFR-013-03 | Web sensor shards | each ≤ 10 MB (plan §10: clouds ≤ 10 MB shards); they count toward the plan's "replay shards + point clouds" class (≤ 60 MB, plan §11; NFR-000-04) | CI budget check |
| NFR-013-04 | Thin adapter: size of the `ovrtx` backend module | ≤ 400 lines of code | CI line count |
| NFR-013-05 | Renderer session limits (16 GB GPU) | ≤ 2 cameras per session, each ≤ 1920 × 1080; radar in a session without camera products | recipe schema (FR-013-04, FR-013-21) |
| SC-013-01 | Pre-registered dust-model checks (M23 acceptance) | P-013-01 to P-013-06 pass | `tests/property`, `tests/metamorphic` |
| SC-013-02 | Pre-registered lane checks (M23 acceptance) | every published sensor artefact comes from a run in which every clean lidar frame passed FR-013-08 and every manifest carries its licence class and `performance: local-only` | contract test on the published manifests |
| SC-013-03 | Pre-registered parity check (M23 acceptance) | P-013-15 passes for every published slider frame | web parity test |
| SC-013-04 | Reported results (no accuracy threshold is pre-registered for M23, which produces data, not a trained model) | P_d against range × transmittance, points on target, false dust returns, TTC margins at 30/40/50 km/h, lidar-vs-radar ranges, rain comparison; never rendering throughput | results page review against FR-013-36, FR-013-37 |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-013-01 | sensor recipe block (S1, S2, S3, S4a, rain) | `specs/013-sensors/contracts/sensor-recipe.schema.json` (draft; promoted to `contracts/sensor-recipe.schema.json` by T-013-001) | maintainer → `st53_sensors`, `st57_rain_lidar`, `s05_synthesize` |
| DC-013-02 | `studio/rtx/lidar-envelope.json` | `specs/013-sensors/contracts/lidar-envelope.schema.json` (draft; promoted to `contracts/lidar-envelope.schema.json` by T-013-001) | `ovrtx` probe → `st53_sensors` guard |
| DC-013-03 | shard index + Parquet column sets (lidar returns, radar detections, image index) | `specs/013-sensors/contracts/sensor-shard.schema.json` (draft, column sets in `$defs/lidar_return`, `$defs/radar_detection`, `$defs/image_record`; promoted to `contracts/sensor-shard.schema.json` by T-013-001) | `st53_sensors`, `st57_rain_lidar` → `s05_synthesize`, `s50_evaluate`, `s60_export` |
| DC-013-04 | web point-cloud shard header | `specs/013-sensors/contracts/web-cloud-shard.schema.json` (draft; promoted to `contracts/web-cloud-shard.schema.json` by T-013-001) | `s60_export` → web replay viewer |
| DC-013-05 | baked dust-slider frame | `specs/013-sensors/contracts/dust-slider.schema.json` (draft; promoted to `contracts/dust-slider.schema.json` by T-013-001) | `s60_export` → web dust worker |
| ~~DC-013-06~~ | Retired: S4b line-of-sight series. | superseded by DC-010-02 (`contracts/displacement-series.schema.json`; integration 2026-10-07) | — |
| DC-013-07 | run and asset manifests | `contracts/manifest.schema.json` (spec 001) | lane stages → web, CI licence guard |
| DC-013-08 | `studio/capabilities.json` probes `ovrtx`, `isaacsim` | `contracts/capabilities.schema.json` (DC-000-02) | `studio/bench/run_bench.py` → stage planner |

## 7. Edge cases and assumptions

**Pinned at specification (read 2026-10-06/07):**
- **A1 — Phillips, Guenther & McAree (2017), *J. Field Robotics* 34(5):985–1009, DOI 10.1002/rob.21701, abstract read
  through the Crossref record:** "(i) where LiDAR measures dust, it does so to the leading edge of a dust cloud rather
  than as a random noise; (ii) dust starts to affect measurements when the atmospheric transmittance is less than
  71%–74%, but this is quite variable with conditions; (iii) LiDAR is capable of ranging to a target in dust clouds
  with transmittance as low as 2% if the target is retroreflective and 6% if it is of low reflectivity". These give
  τ_on (midpoint 0.725 → 0.3216), τ_floor(retro) = −ln 0.02 = 3.9120, τ_floor(diffuse) = −ln 0.06 = 2.8134, and the
  leading-edge placement of dust returns.
- **A2 — ovrtx issue #3** (open): with ovrtx 0.5.0.377615 / ovstage 0.2.0.377349 on Windows, fans of −80…+80° and
  −90…+90° with mount rotation (90, 0, −90) returned 0 points; −45…+45° with no rotation (~150,000 points), −90…+90°
  with no rotation (~16,000) and −60…+60° with rotation (90, 0, −90) (~206,000) returned points; no diagnostic was
  emitted. Hence the hard schema limit of ±45° and the probe-written envelope (FR-013-05, FR-013-06). The pre-registered
  S1 lidars are a rotary 64-channel unit with an elevation fan of −22.5…+22.5° and a solid-state unit of 120° × 30°.
- **A3 — Narasimhan & Nayar (2002)**, IJCV 48(3):233–254, DOI 10.1023/A:1016328200723, for I = J t + A(1 − t).

**UNVERIFIED (kept with analytical oracles that do not depend on them):**
- **U1** — mapping of the paper's "atmospheric transmittance" onto a beam path: the full text was not readable
  (HTTP 403). This spec uses the one-way transmittance T₁ over the sensor-to-target path. Tests check the rule for the
  stated thresholds; they do not depend on whether the mapping is right.
- **U2** — the mass extinction coefficient k_ext linking the C3 mass concentration to β: no value is verified. The
  coupling of C3 dust fields to S1 is labelled "calibrated synthetic"; the S1 metrics are expressed in transmittance.
- **U3** — radar dust immunity at millimetre wave (stated assumption, no source read; FR-013-24).
- **U4** — rain in ovrtx (the setting is documented only for Kit); the rain arm uses Isaac Sim.
- **U5** — the native sign convention of ovrtx `RadialVelocityMs`; FR-013-23 measures it and the adapter normalises it.
- **U6** — the citations of the classical relations used here (shot/read exposure noise, cos⁴ natural vignetting,
  pinhole camera). Their oracles are analytical.

**Edge cases:**
- A beam with no hit carries no target return; it gets no dust return (the rule needs a return range R).
- A dusty frame may legitimately have zero target points; the point-count guard applies to clean frames only.
- The rule is a threshold model: under a uniform layer, diffuse detection is a step at τ_on followed by a linear
  decline in τ. That is a stated simplification of "quite variable with conditions".
- `dust_return_intensity` is a display value; dust-return intensities carry no physical claim.
- Determinism: bit-exact rendering is not documented, so RTX outputs are `statistical`; post-models are `bitwise`.
- Simulation-grade twin; generic sensors; not a certified safety-system evaluation.

**Tolerances and their justification:**
- float64 analytical paths, rtol 1e-12: fewer than 10³ operations per value, each with relative error ≤ 2⁻⁵³.
- float32 image paths, rtol 1e-6: about 8 ulp of float32 (ε = 1.19 × 10⁻⁷) for float16 inputs promoted to float32.
- Python–TypeScript parity: decisions are computed by multiplication, subtraction and comparison of float64 values
  read from the same float32 or uint32 inputs, so they are exactly identical. `exp` may differ by 1 ulp between V8
  and NumPy, hence rtol 1e-12 on intensities.
- Statistical checks: 4 binomial standard deviations or 99.9 % χ² intervals, so a false failure has a probability
  below 10⁻³ per test.
- Re-run tolerances (FR-013-34): two independent Gaussian range errors of σ differ with a standard deviation of
  σ√2; the mean absolute difference is ≈ 1.13 σ, so 3 σ leaves margin. ±1 % on counts and PSNR ≥ 40 dB match the
  documented use of tolerance, not bit-exactness, for RTX outputs. Their `thresholds.yaml` keys are
  `sensors.rerun_point_count_rel_max: 0.01`, `sensors.rerun_chamfer_over_range_accuracy_max: 3` and
  `sensors.rerun_psnr_db_min: 40`.

## 8. Clarifications log

- Resolved: functional form of the dust rule (the docs defer it to the specification): FR-013-12 and FR-013-13, with
  thresholds pinned from the paper's abstract (A1). The abstract adds the 6 % low-reflectivity floor, which the docs
  did not quote; it is adopted for every non-retroreflective return (conservative for brighter diffuse targets).
- Resolved: the transmittance mapping is one-way over the sensor-to-target path (U1, UNVERIFIED).
- Resolved (plan wins): the docs mention a live "dust (and rain)" slider; plan §6 says "live dust slider (own
  model)". The live slider is dust only; rain frames (Isaac Sim Mie model) are REPLAY.
- Resolved: the "tested range" of the elevation fan is the probe-written envelope with a hard ±45° schema limit (A2).
- Resolved: the post-models run in `pipeline/` (`s05_synthesize`, `s50_evaluate`, `s60_export`) on the clean
  `st53_sensors` shards (file handoff), so the open numerical code is tested in CI on Python 3.14 and never shares a
  process with an RTX runtime. `st53_sensors` produces the clean S1–S4a data and enforces the guards.
- Resolved: scope split with other specs. The S4b line-of-sight series belongs to spec 010-slope (generation and
  forecasting; see the integration entry below, which superseded the first split). The S3
  instance-accurate boxes come from spec 009's Replicator arm; this spec supplies semantic-component boxes. The C3 β
  field comes from spec 005.
- Resolved: the S4b sign convention is "positive = toward the radar" (the docs leave it to the specification); it is
  now stated by FR-010-41.
- Resolved: the slider uses 41 discrete levels with baked k_j, so the browser never computes a logarithm on the
  decision path (exact parity class).
- Resolved: the web uses the `minephys` transmittance functions through the Python reference only; the TypeScript
  port is checked against that reference (P-013-15).
- Integration 2026-10-07: the S4b slope-radar series belongs to spec 010-slope (plan §9 lists S1, S2, S3 and S4a for
  `st53_sensors`; S4b is the analytical GB-InSAR model of `minephys.geotech` used by case C1). Retired here:
  US-013-5, FR-013-25…28, P-013-09, P-013-10 and DC-013-06 (the `los-series` schema; the series uses spec 010's
  `displacement-series.schema.json`). Behaviours stated only here were moved to spec 010 (FR-010-41, FR-010-42,
  P-010-16, P-010-17). FR-013-02, DC-013-01, SC-013-04, FR-013-41, U6, the title, intent and out-of-scope list no
  longer mention S4b generation; tasks T-013-050…052 are retired.
- Integration 2026-10-07: NFR-013-03 states the plan's 10 MB per-shard cap (plan §10) and the plan's "replay shards +
  point clouds ≤ 60 MB" class (plan §11); the earlier proposal of a 20 MB sensor allocation is withdrawn.
- Integration 2026-10-07: the re-run tolerances of FR-013-34 get proposed `thresholds.yaml` keys (`sensors.rerun_*`,
  pending maintainer approval), stated in §7.
- Integration 2026-10-07: draft schema written for DC-013-01 … DC-013-05 (`specs/013-sensors/contracts/`, valid and
  hostile examples indexed in `examples/index.json`). Resolved, stricter reading chosen: a sensor recipe block is the
  `params` of one `st53_sensors` or `st57_rain_lidar` stage and one renderer session, so `scenario` fixes the sensor
  kind and the backend, the radar-without-camera rule (FR-013-21) and the ≤ 2 cameras rule (NFR-013-05) hold per
  block, and a non-zero rain rate is valid only with `backend: isaac`; native renderer names become parameter keys
  (`rangeAccuracyM` → `range_accuracy_m`, `maxReturns` → `max_returns`, `velResMps` → `velocity_resolution_m_per_s`),
  every length is in metres (radar wavelength, focal length, pixel pitch included) and every angle in degrees; return
  intensities and `dust_return_intensity` are normalised to 0–1; "≤ 10 MB" is 10,000,000 bytes for every shard and
  payload; the lidar envelope keeps the ±45° limit and its `pass`/`fail` follows the valid-point count; every indexed
  clean lidar frame has ≥ 1 valid point (FR-013-08); web cloud shards and slider frames are a JSON header plus a
  planar little-endian binary payload (8 bytes per point, at most 1,250,000 points; 20 bytes per slider return) whose
  size and SHA-256 sit in the header, and per-return τ checks (NaN, negative) stay with the dust worker (FR-013-39);
  the slider header pins τ_on, both τ_floor values, the 41 levels and the "own Beer–Lambert dust model" label; a web
  shard carries an `intensity_map`, so an S4a shard can hold radial velocity in its uint8 channel for the Doppler view
  (FR-013-40); bounds the spec leaves open: ≤ 8 sensors per block, ≤ 512 channels, ≤ 4 returns, ranges ≤ 500 m, rain
  ≤ 200 mm/h, t_e ≤ 1 s, N in 1–32.
- Integration 2026-10-07 (2): FR-013-35 states that the position code type is declared in the shard header and read from it,
  the rule of the replay-shard schema DC-018-03 (spec 018). The sensor web shard keeps its own header (DC-013-04)
  because it also carries 8-bit intensity and class channels, which DC-018-03's raw16 layout does not.

## 9. Changes (only for features that modify earlier behaviour)

### ADDED Requirements
- (none — new feature)

### MODIFIED Requirements
- (none)

### REMOVED Requirements
- (none)
