# Tasks 005 — Physics: `st50_physics` and physics benchmarks
Format: `- [ ] T-005-xxx [US-005-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/005-physics/tests.lock <files>`).
Tests under `tests/gpu/` carry the `gpu` marker (reference machine only, skipped while `gpu0.hold` exists); every other
test runs in the studio CPU job (T-004-002) on Warp's CPU device with CUDA hidden.

## Phase 1 — Setup
- [ ] T-005-001 (DC-005-01, DC-005-02, DC-005-03, DC-005-04, DC-005-05, DC-005-06) contract schemas `physics-scenario`, `physics-field`, `physics-observables`, `replay-shard`, `physics-benchmark-report`, `physics-parity-golden` + generated types; valid and invalid examples — test: tests/contract/test_t_005_001_physics_schemas.py
- [ ] T-005-002 fake GPU backend for physics tests (device list, free memory, out-of-memory on demand, context-creation recorder) and the benchmark scenario files under `studio/recipes/_bench/physics/` (no requirement IDs; setup)

## Phase 2 — US-005-1 (P1) A DEM that reproduces granular laws
- [ ] T-005-010 [US-005-1] (FR-005-01) Hertz–Mindlin contact law and effective properties: worked-example forces and stiffnesses — test: tests/unit/test_t_005_010_dem_contact_law.py
- [ ] T-005-011 [US-005-1] (FR-005-02, FR-005-03) elastic impact overlap and duration; restitution against the SciPy reference and its velocity independence — test: tests/unit/test_t_005_011_dem_impact.py
- [ ] T-005-012 [US-005-1] (FR-005-04, FR-005-05) sphere on an incline (rest vs rolling) and sliding-to-rolling transition — test: tests/unit/test_t_005_012_dem_rolling.py
- [ ] T-005-013 [US-005-1] (FR-005-06, FR-005-07) hash-grid neighbours, contact-list capacity and `contact-overflow` — test: tests/unit/test_t_005_013_dem_contacts.py
- [ ] T-005-014 [US-005-1] (FR-005-08, FR-005-09) time-step guard `dt-unstable`; reduced-modulus record and re-benchmark flag — test: tests/unit/test_t_005_014_dem_timestep.py
- [ ] T-005-015 [US-005-1] (FR-005-15) exact particle and mass accounting with outflow — test: tests/unit/test_t_005_015_dem_mass.py
- [ ] T-005-016 [US-005-1] (FR-005-13) repose-angle measurement on analytic cones, ridges and sampled cones — test: tests/unit/test_t_005_016_repose_measure.py
- [ ] T-005-017 [US-005-1] (P-005-01, P-005-02, P-005-03, P-005-04, P-005-05, P-005-06) DEM metamorphic relations: similarity, translation, rotation, time step, permutation, monotonicity — test: tests/metamorphic/test_t_005_017_dem_relations.py
- [ ] T-005-018 [US-005-1] (FR-005-11) quasi-2-D slot discharge benchmark on Warp CPU (`slow`) — test: tests/pipeline/test_t_005_018_dem_slot_beverloo.py
- [ ] T-005-019 [US-005-1] (FR-005-10, FR-005-12, FR-005-14) 3-D Beverloo, repose and axisymmetric collapse benchmarks — test: tests/gpu/test_t_005_019_dem_benchmarks.py

## Phase 3 — US-005-2 (P1) MPM solvers that agree with the same laws
- [ ] T-005-020 [US-005-2] (FR-005-16) Newton implicit MPM configured explicitly from the scenario (fake solver) — test: tests/unit/test_t_005_020_newton_config.py
- [ ] T-005-021 [US-005-2] (FR-005-17, FR-005-20, P-005-07) MLS-MPM twin transfers: mass and momentum conservation, partition of unity — test: tests/property/test_t_005_021_mlsmpm_p2g.py
- [ ] T-005-022 [US-005-2] (P-005-08, P-005-09, P-005-10) MLS-MPM twin metamorphic relations: mirror symmetry, time step, friction — test: tests/metamorphic/test_t_005_022_mlsmpm_relations.py
- [ ] T-005-023 [US-005-2] (FR-005-18) planar column-collapse benchmark on the twin (CPU `slow`) — test: tests/pipeline/test_t_005_023_mlsmpm_collapse.py
- [ ] T-005-024 [US-005-2] (FR-005-14, FR-005-19, FR-005-20, FR-005-21, P-005-11, P-005-12, P-005-13) Newton MPM benchmarks and relations: axisymmetric collapse, silo, mass, statistical re-run, resolution, symmetry, friction — test: tests/gpu/test_t_005_024_newton_mpm.py
- [ ] T-005-025 [US-005-2] (FR-005-22) parity goldens for the browser twins in deterministic mode — test: tests/pipeline/test_t_005_025_parity_goldens.py

## Phase 4 — US-005-3 (P1) A tailings solver verified on dam breaks and Bingham flow
- [ ] T-005-030 [US-005-3] (FR-005-23, FR-005-27) Rusanov flux, hydrostatic reconstruction, CFL step, positivity and dry threshold — test: tests/unit/test_t_005_030_swe_scheme.py
- [ ] T-005-031 [US-005-3] (FR-005-24, FR-005-25, P-005-19) Ritter and Stoker dam breaks with grid convergence — test: tests/pipeline/test_t_005_031_swe_dam_break.py
- [ ] T-005-032 [US-005-3] (FR-005-26, FR-005-28) lake at rest over benched terrain; volume conservation with sources and open boundaries — test: tests/property/test_t_005_032_swe_balance.py
- [ ] T-005-033 [US-005-3] (FR-005-29) Bingham bed stress: exact arrest below h_stop, sheet-flow velocity above — test: tests/unit/test_t_005_033_swe_bingham.py
- [ ] T-005-034 [US-005-3] (FR-005-30, FR-005-31) C2 maps (arrival time, maximum depth and speed, inundated area) and breach hydrograph volume — test: tests/unit/test_t_005_034_swe_outputs.py
- [ ] T-005-035 [US-005-3] (P-005-14, P-005-15, P-005-16, P-005-17, P-005-18) shallow-water metamorphic relations: mirror, rotation, Froude scaling, yield-stress monotonicity, Newtonian and frictionless limits — test: tests/metamorphic/test_t_005_035_swe_relations.py
- [ ] T-005-036 [US-005-3] (FR-005-32) hostile shallow-water inputs, no kernel launch — test: tests/unit/test_t_005_036_swe_hostile.py

## Phase 5 — US-005-4 (P2) Dust particles that settle and spread correctly
- [ ] T-005-040 [US-005-4] (FR-005-33, FR-005-34, FR-005-35) particle step, Stokes settling, random-walk variance — test: tests/unit/test_t_005_040_dust_kinematics.py
- [ ] T-005-041 [US-005-4] (FR-005-37, FR-005-38) mass budget and deposition on terrain — test: tests/unit/test_t_005_041_dust_budget.py
- [ ] T-005-042 [US-005-4] (FR-005-36) plume consistency on flat ground (`slow`) — test: tests/pipeline/test_t_005_042_dust_plume.py
- [ ] T-005-043 [US-005-4] (P-005-20, P-005-21, P-005-22, P-005-23) dust metamorphic relations: linearity, wind rotation, time-step invariance, settling monotonicity — test: tests/metamorphic/test_t_005_043_dust_relations.py
- [ ] T-005-044 [US-005-4] (FR-005-39) hostile dust inputs incl. the Stokes-regime check — test: tests/unit/test_t_005_044_dust_hostile.py

## Phase 6 — US-005-5 (P2) Vehicles with the right steady speed and energy
- [ ] T-005-050 [US-005-5] (FR-005-40, FR-005-41, FR-005-42) reduced-order truck model: step, steady speed, energy balance — test: tests/unit/test_t_005_050_vehicle_model.py
- [ ] T-005-051 [US-005-5] (P-005-24, P-005-25, P-005-26) vehicle metamorphic relations: scaling, grade monotonicity, time step — test: tests/metamorphic/test_t_005_051_vehicle_relations.py
- [ ] T-005-052 [US-005-5] (FR-005-44) hostile vehicle parameters — test: tests/unit/test_t_005_052_vehicle_hostile.py
- [ ] T-005-053 [US-005-5] (FR-005-43) Newton rigid box on an incline — test: tests/gpu/test_t_005_053_newton_rigid.py

## Phase 7 — US-005-6 (P1) Disciplined outputs on one shared GPU
- [ ] T-005-060 [US-005-6] (FR-005-45, P-005-27) replay quantisation, shard size cap and replay manifest — test: tests/property/test_t_005_060_replay_shards.py
- [ ] T-005-061 [US-005-6] (FR-005-46, FR-005-47) Zarr fields, Parquet observables, benchmark report, rollout stamps and refusal of unbenchmarked production scenarios — test: tests/contract/test_t_005_061_physics_outputs.py
- [ ] T-005-062 [US-005-6] (FR-005-48, P-005-28) deterministic mode, byte-identical re-run on Warp CPU, overhead factor recorded — test: tests/property/test_t_005_062_determinism_cpu.py
- [ ] T-005-063 [US-005-6] (FR-005-48, P-005-28) byte-identical re-run on CUDA in deterministic mode — test: tests/gpu/test_t_005_063_determinism_cuda.py
- [ ] T-005-064 [US-005-6] (FR-005-49, FR-005-50, FR-005-54) device policy with the fake GPU backend: CUDA hidden on CPU runs, `not run (no GPU)` rows, `oom` classification, `lock-not-held` from the held-lock list (spec 002) — test: tests/unit/test_t_005_064_device_policy.py
- [ ] T-005-065 [US-005-6] (FR-005-51, FR-005-52) hostile scenarios and non-finite state abort — test: tests/contract/test_t_005_065_physics_hostile.py
- [ ] T-005-066 [US-005-6] (NFR-005-01, NFR-005-02, NFR-005-04, NFR-005-05, SC-005-01, SC-005-02) acceptance on the published runs (data-and-models phase): memory, wall time, throughput, overhead record, benchmark gate, comparison wording — test: tests/pipeline/test_t_005_066_physics_acceptance.py
- [ ] T-005-067 (NFR-005-03) CPU-variant test time budget in the studio CPU job — test: tests/pipeline/test_t_005_067_cpu_suite_time.py

## Phase 8 — Polish and review
- [ ] T-005-090 mutation run on `pitstudio_studio.physics.dem.contact`, `.swe`, `.dust`, `.vehicles`, `.mlsmpm2d` and `.measure`; record the score against `mutation.numerical_core_min`
- [ ] T-005-091 independent review of the diff against this spec; append tasks for gaps
