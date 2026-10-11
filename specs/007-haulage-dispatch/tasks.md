# Tasks 007 — Haulage and dispatch (M1–M6)
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`

Rules:
- Every task with requirement IDs is a `[red]`/`[green]` commit pair.
- Each task's tests live in their own file(s) and are locked after `[red]`
  (`python tools/lock_tests.py specs/007-haulage-dispatch/tests.lock <files>`).
- Python tests carry `@pytest.mark.req("<ID>")`, and TypeScript test titles start with `"<ID> · "`.
- `tests/pipeline/` runs in the `pipeline/` environment; `tests/gpu/` carries the `gpu` marker and never runs in CI.

## Phase 1 — Setup
- [ ] T-007-001 (DC-007-01, DC-007-02, DC-007-03, DC-007-04, DC-007-05) Write the schemas `haul-scenario`,
  `des-trace`, `dispatch-eval`, `dispatch-policy-io` and `haul-energy` (JSON Schema 2020-12) and generate their Pydantic
  and TypeScript types; contract tests check the meta-schema, round trips and that a hostile document is rejected — test: tests/contract/test_t_007_001_haulage_schemas.py
- [ ] T-007-002 Dependency validation, before any feature code: `uv add highspy` (pipeline), `uv add --dev simpy scipy`
  (pipeline), `uv add --dev networkx` (root). The lock must resolve on Python 3.14 Windows wheels; record licences
  (MIT, MIT, BSD-3, BSD-3); smoke-import each package — test: tests/pipeline/test_t_007_002_deps_smoke.py
- [ ] T-007-003 [US-007-5] (FR-007-02) Engine pin file (version + module SHA-256 + callback-name map) and the guard
  that refuses on any mismatch — test: tests/pipeline/test_t_007_003_engine_pin.py

## Phase 2 — US-007-5 (P2): variate source, reference adapter, oracles, goldens
- [ ] T-007-010 [US-007-5] (FR-007-05, P-007-01, P-007-02) Philox4x64-10 + FNV-1a-64 stream keys in Python; checked
  against the KAT vectors, `numpy.random.Philox` (counter offset −1) and the variate-source invariants — test: tests/pipeline/test_t_007_010_philox.py
- [ ] T-007-011 [US-007-5] (FR-007-06, FR-007-07, P-007-03) Quantile tables (2¹² bins, end bins at the conditional tail
  means) and the `engine` / `exponential` / `deterministic` profiles; table moments and KS checked against the closed-form
  distributions — test: tests/pipeline/test_t_007_011_variates.py
- [ ] T-007-012 [US-007-5] (FR-007-05, FR-007-06, P-007-04) TypeScript Philox (BigInt) and variates, bit-equal to the
  Python fixtures; AST scan that forbids transcendental `Math.*` and non-integer `**` in `web/src/engines/random/` and
  `web/src/engines/des/` — test: web/src/engines/random/philox.test.ts, web/src/engines/random/variates.test.ts, web/src/engines/random/no-transcendental.test.ts
- [ ] T-007-013 [US-007-5] (FR-007-01, FR-007-09, P-007-05, P-007-21) Adapter seam (random-stream substitution + engine
  event recorder with the canonical kinds); the recorder is cross-checked against the engine's own cyclelog;
  determinism across processes; the seam does not change the model (Welch 99 % CI against the engine's own random
  streams) — test: tests/pipeline/test_t_007_013_adapter_trace.py
- [ ] T-007-014 [US-007-1] (FR-007-03, FR-007-04) Hostile scenario bundles (one violation per case, every class of
  FR-007-03) and disconnected networks, rejected with every violation listed, in Python and TypeScript — test: tests/pipeline/test_t_007_014_scenario_hostile.py, web/src/engines/des/scenario.hostile.test.ts
- [ ] T-007-015 [US-007-1] (FR-007-14) Dispatcher set: delegation to the engine policies, `min-idle`, the
  declared-destination dump rule, tie rules; hand-calculated MineView cases — test: tests/pipeline/test_t_007_015_dispatchers.py
- [ ] T-007-016 [US-007-1] (FR-007-08, FR-007-42, P-007-20) KPI layer on a hand-written 3-truck trace (t/h, queue mean/P90,
  utilisation, match factor, hours per kt, cost only with rates), its unit and homogeneity relations, and malformed
  traces rejected with `InvalidTrace` — test: tests/pipeline/test_t_007_016_kpi.py
- [ ] T-007-017 [US-007-4] (FR-007-17, FR-007-18, P-007-09) The exponential MVA oracle family (N_T = 1 … 12, 30 seeds
  × 100 h); deterministic-profile monotonicity and closed-form cycle rate; the realistic-profile gap is reported
  without a pass flag — test: tests/pipeline/test_t_007_017_des_oracles.py
- [ ] T-007-018 [US-007-5] (P-007-06, P-007-07) Metamorphic relations of the reference: order-preserving relabelling,
  homogeneous permutation, orientation reversal — test: tests/pipeline/test_t_007_018_des_metamorphic.py
- [ ] T-007-019 [US-007-5] (P-007-12) An independent SimPy model of small fast-mode scenarios, fed by the same variate
  streams, compared with the reference cyclelog — test: tests/pipeline/test_t_007_019_simpy_oracle.py
- [ ] T-007-020 [US-007-5] (FR-007-11) Golden writer over the coverage matrix (24 classical + LP × 2 + ramp/zone/junction
  + memo-collision + one per profile; ≥ 4 full shifts); coverage and size checks (each < 2 MB gzip, ≤ 20 MB in total) — test: tests/pipeline/test_t_007_020_golden_coverage.py

## Phase 3 — US-007-1 (P1): TypeScript DES twin
- [ ] T-007-021 [US-007-1] (FR-007-10, P-007-06, P-007-07, P-007-08) TypeScript twin, bit-identical to every golden
  (events, cyclelog, scalar results); the relabelling, reversal and time-dilation-by-2 relations — test: web/src/engines/des/twin.parity.test.ts, web/src/engines/des/twin.metamorphic.test.ts
- [ ] T-007-022 [US-007-1] (FR-007-12, FR-007-13) Unsupported features, invalid seeds and horizons, and the event
  budget in the twin and the Python adapter: typed errors within 2 s and no partial KPIs — test: web/src/engines/des/twin.hostile.test.ts, tests/pipeline/test_t_007_022_adapter_limits.py
- [ ] T-007-023 [US-007-1] (NFR-007-01, NFR-007-02) One 8 h shift ≤ 1 s on T2; analytical ports ≤ 50 KB gzip; engines
  lazy-loaded and absent from the initial JS — test: web/e2e/haulage-engines-budget.spec.ts

## Phase 4 — US-007-4 (P2): analytical fleet sizing (M1)
- [ ] T-007-030 [US-007-4] (FR-007-15, FR-007-16) Golden vectors written from `minephys.haulage` (match factor,
  M/M/1//N, M/M/c, MVA, including the spec §7 worked examples); the TypeScript port equals them within rtol 1e-12;
  hostile inputs return typed results, never NaN or Infinity — test: tests/parity/test_t_007_030_m1_goldens.py, web/src/engines/haulage/queueing.test.ts

## Phase 5 — US-007-2 (P1): two-stage LP dispatch (M3)
- [ ] T-007-040 [US-007-2] (FR-007-19, FR-007-21, P-007-11) HiGHS upper stage: the worked example (19.5 and 19.2
  loads/h; duals 0.375 / 1.25 and 1.6 / 4), typed statuses for hostile LPs, the metamorphic relations — test: tests/pipeline/test_t_007_040_lp_highs.py
- [ ] T-007-041 [US-007-1] (FR-007-20, FR-007-21, P-007-11, NFR-007-04) TypeScript simplex equal to the HiGHS fixtures,
  typed statuses, metamorphic relations, ≤ 50 ms for ≤ 64 paths — test: web/src/engines/lp/simplex.test.ts
- [ ] T-007-042 [US-007-2] (FR-007-22, FR-007-33, P-007-10) Lower-stage assignment (hand-calculated need values),
  re-solve triggers, SPTF fallback, all-masked parking, and the LP throughput bound for every dispatcher — test: tests/pipeline/test_t_007_042_lp_dispatch.py

## Phase 6 — US-007-2 (P1): learned dispatch (M4, M5)
- [ ] T-007-050 [US-007-2] (FR-007-23, FR-007-24, FR-007-43, P-007-13, P-007-08) Vectorised environment on CPU: tick
  script, masks, deterministic and MVA oracles, batch independence, relabelling, time dilation; hostile configurations
  rejected before any allocation — test: tests/pipeline/test_t_007_050_env.py
- [ ] T-007-051 [US-007-2] (FR-007-25, P-007-14) Time-delta GAE against the hand recursion and its three relations — test: tests/pipeline/test_t_007_051_gae.py
- [ ] T-007-052 [US-007-2] (FR-007-24, P-007-15, P-007-16) M4 MLP and M5 attention: exact zero probability on masked
  targets, permutation, padding and size invariance — test: tests/pipeline/test_t_007_052_policies.py
- [ ] T-007-053 [US-007-2] (FR-007-26, FR-007-27, FR-007-28, NFR-007-05) Training stage: bitwise resume on CPU with the
  fake GPU backend, OOM fallback (halve B, ≤ 2 times, then stop), seed-leak guard, recipe budgets; a short GPU run
  under the lock — test: tests/pipeline/test_t_007_053_train_stage.py, tests/gpu/test_t_007_053_train_gpu.py
- [ ] T-007-054 [US-007-2] (SC-007-04) Environment fidelity gate against the reference DES in fast mode (≤ 3 % for
  fixed, nearest, SPTF, SQ over 30 seeds); the traffic-mode gap is reported — test: tests/pipeline/test_t_007_054_env_fidelity.py
- [ ] T-007-055 [US-007-2] (FR-007-28, FR-007-29, FR-007-30, SC-007-01, SC-007-02) Paired evaluation in the reference
  engine: the table schema, the paired-t CI against `scipy`, the spec §7 worked example, `insufficient-evidence` cases,
  per-fleet-size rows for M5 — test: tests/pipeline/test_t_007_055_dispatch_eval.py
- [ ] T-007-056 [US-007-2] (FR-007-31, FR-007-33, FR-007-44, SC-007-03, NFR-007-03) Export against the I/O schema;
  ONNX Runtime CPU vs PyTorch on ≥ 200 golden states, 100 % masked-argmax agreement, < 2 MB per policy; wrong shapes,
  non-finite features and pin mismatches stop the run — test: tests/pipeline/test_t_007_056_policy_export.py
- [ ] T-007-057 [US-007-1] (FR-007-32) Twin + ONNX Runtime Web (WASM) policy shifts against the Python reference up to
  the near-tie bound; ≥ 99.5 % identical end to end — test: web/src/engines/des/policy.parity.test.ts

## Phase 7 — US-007-3 (P1): route energy and grade-constrained routing (M6)
- [ ] T-007-060 [US-007-3] (FR-007-35, FR-007-37, P-007-17, P-007-18) A\* against networkx Dijkstra on dyadic DEMs,
  grade feasibility, admissibility, `NoFeasibleRoute`, the five metamorphic relations — test: tests/property/test_t_007_060_astar.py
- [ ] T-007-061 [US-007-3] (FR-007-36) Hostile DEMs and requests (NaN/inf cells, cell size, oversize grids, g_max,
  start/goal outside or on nodata) — test: tests/unit/test_t_007_061_astar_hostile.py
- [ ] T-007-062 [US-007-3] (FR-007-34, FR-007-40, FR-007-45, P-007-19) Route energy against the M06 worked example and
  the lift floor; constants only from the knowledge tables; UNVERIFIED ids listed; the seven relations; hostile route
  inputs rejected — test: tests/unit/test_t_007_062_route_energy.py
- [ ] T-007-063 [US-007-3] (FR-007-38, FR-007-45) Network builder: Douglas–Peucker + constant-grade splitting,
  |grade| ≤ g_max after refinement, endpoint elevations within 0.01 m of the bilinear DEM sample; duplicate or
  out-of-grid cells and tolerance ≤ 0 rejected — test: tests/property/test_t_007_063_network_builder.py
- [ ] T-007-064 [US-007-3] (FR-007-39, NFR-007-04) TypeScript A\* and route energy equal to the Python goldens
  (identical cells, rtol 1e-12); A\* ≤ 1 s on 512 × 512 — test: web/src/engines/routing/astar.test.ts, web/src/engines/haulage/energy.test.ts

## Phase 8 — Honesty
- [ ] T-007-070 [US-007-2] (FR-007-41) Every A1/A2 artefact header and manifest entry carries the exact label and the
  cycle-time bias note, and no C2ST/TSTR field — test: tests/contract/test_t_007_070_haulage_honesty.py

## Phase 9 — Polish and independent review
- [ ] T-007-090 Mutation run on `pitstudio_pipeline.haulage`, `pitstudio_pipeline.dispatch`, `pitstudio.haulage` and
  `web/src/engines/{random,des,lp,routing,haulage}`; record the scores against `thresholds.yaml` `mutation`
- [ ] T-007-091 Independent review of the diff against this spec; append tasks for gaps
