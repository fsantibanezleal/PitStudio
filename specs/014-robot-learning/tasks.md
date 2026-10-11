# Tasks 014 — Robot learning (M21)
Format: `- [ ] T-014-xxx [US-014-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/014-robot-learning/tests.lock <files>`). Tests marked
`gpu` run only on the reference machine under the GPU lock, never in CI.

## Phase 1 — Setup
- [ ] T-014-001 (DC-014-01, DC-014-02, DC-014-03, DC-014-04, DC-014-05) contract schemas `il-task`, `machine-params`, `il-policy-handoff`, `il-episodes`, `il-twin` + generated Pydantic and TypeScript types + drift check — test: tests/contract/test_t_014_001_il_schemas.py
- [ ] T-014-002 [US-014-3] (FR-014-01, FR-014-04, DC-014-06) lock check of `studio/isaaclab/uv.lock` (tag, commit prefix, torch/Warp/Newton/MuJoCo/rsl-rl pins, no `isaacsim*`) and the performance marker derived from the lock — test: tests/contract/test_t_014_002_isaaclab_lock.py

## Phase 2 — US-014-3 (P1) lane gating
- [ ] T-014-010 [US-014-3] (FR-014-02, DC-014-07) `isaaclab` probe writer (schema, versions from the lock, pass rule) — test: tests/contract/test_t_014_010_isaaclab_probe.py
- [ ] T-014-011 [US-014-3] (FR-014-03) planner skip, `evaluated-not-adopted` registry status and reason for every non-pass probe state — test: tests/unit/test_t_014_011_lane_gating.py
- [ ] T-014-012 [US-014-3] (NFR-014-05) repository scan of task code (SPDX headers, no copied Isaac Lab source markers, no NVIDIA or Isaac Lab asset references) — test: tests/unit/test_t_014_012_il_provenance.py

## Phase 3 — US-014-2 (P1) excavator physics cores
- [ ] T-014-020 [US-014-2] (FR-014-17, P-014-01, P-014-02, P-014-03, P-014-05) FEE wedge reference: factors, β* minimiser, H/V split; metamorphic relations — test: tests/metamorphic/test_t_014_020_fee_relations.py
- [ ] T-014-021 [US-014-2] (FR-014-17, P-014-04, P-014-06) FEE equilibrium oracle and worked examples (cohesionless, cohesive, rake table) — test: tests/unit/test_t_014_021_fee_worked_examples.py
- [ ] T-014-022 [US-014-2] (FR-014-21) FEE hostile inputs and inadmissible domains — test: tests/unit/test_t_014_022_fee_hostile.py
- [ ] T-014-023 [US-014-2] (FR-014-18, P-014-13) fill model (gain, cap, terrain conservation) — test: tests/metamorphic/test_t_014_023_fill_model.py
- [ ] T-014-024 [US-014-2] (FR-014-15, FR-014-16, FR-014-20) IL-2 observation builder, action mapping and stall detector — test: tests/unit/test_t_014_024_il2_obs_stall.py
- [ ] T-014-025 [US-014-2] (FR-014-19, P-014-14) soil randomisation sampler — test: tests/property/test_t_014_025_soil_randomisation.py
- [ ] T-014-026 [US-014-2] (FR-014-06, FR-014-07) excavator MJCF generator and hostile parameter files — test: tests/unit/test_t_014_026_excavator_mjcf.py
- [ ] T-014-027 [US-014-2] (FR-014-30) scripted-dig baseline: seed disjointness and freeze before evaluation — test: tests/unit/test_t_014_027_scripted_dig.py

## Phase 4 — US-014-1 (P1) haul-truck cores
- [ ] T-014-030 [US-014-1] (FR-014-08, P-014-09) IL-1 observation builder (63 elements) and its rigid-motion, mirror and permutation relations — test: tests/metamorphic/test_t_014_030_il1_observation.py
- [ ] T-014-031 [US-014-1] (FR-014-09, FR-014-10) action mapping, clipping and non-finite termination — test: tests/unit/test_t_014_031_il1_actions.py
- [ ] T-014-032 [US-014-1] (FR-014-11, P-014-10) reward terms with `minephys.haulage` speed limits; shaping telescopes — test: tests/metamorphic/test_t_014_032_il1_reward.py
- [ ] T-014-033 [US-014-1] (FR-014-12, FR-014-14) terminations, success rule, light-vehicle scenarios and the 25/25/25/25 evaluation mix — test: tests/unit/test_t_014_033_il1_episodes.py
- [ ] T-014-034 [US-014-1] (FR-014-13, P-014-14) IL-1 randomisation sampler — test: tests/property/test_t_014_034_il1_randomisation.py
- [ ] T-014-035 [US-014-1] (FR-014-34, P-014-08) TTC between oriented footprints — test: tests/metamorphic/test_t_014_035_ttc.py
- [ ] T-014-038 [US-014-1] (FR-014-47) hostile inputs of TTC, the twin steps and the fill model — test: tests/unit/test_t_014_038_cores_hostile.py
- [ ] T-014-036 [US-014-1] (FR-014-29, FR-014-31, P-014-07) pure pursuit + PID baseline and its hostile paths — test: tests/metamorphic/test_t_014_036_pure_pursuit.py
- [ ] T-014-037 [US-014-1] (FR-014-05, FR-014-07) truck MJCF generator (mass, wheelbase, track within 0.1 %) — test: tests/unit/test_t_014_037_truck_mjcf.py

## Phase 5 — US-014-1 / US-014-2 training, export and evaluation
- [ ] T-014-040 [US-014-3] (FR-014-25, FR-014-26) training wrapper with a fake trainer: PPO config, checkpoint cadence, resume equality, single OOM fallback — test: tests/unit/test_t_014_040_training_wrapper.py
- [ ] T-014-049 [US-014-3] (FR-014-46) hostile task parameters and resume with a mismatched configuration hash — test: tests/unit/test_t_014_049_task_params_hostile.py
- [ ] T-014-041 [US-014-1] (FR-014-27, FR-014-28, NFR-014-03, SC-014-10) policy handoff contract, export hooks (opset 17, IR 10, normaliser in graph, < 1 MB, parity on ≥ 200 goldens) and hostile handoffs — test: tests/pipeline/test_t_014_041_policy_export.py
- [ ] T-014-042 [US-014-1] (FR-014-32, FR-014-33, FR-014-39, P-014-11) evaluation protocol, IL-1 metrics, Wilson intervals and hostile episode tables — test: tests/pipeline/test_t_014_042_il1_evaluation.py
- [ ] T-014-043 [US-014-2] (FR-014-35, FR-014-39) IL-2 metrics (k_f, t_c, productivity, stalls, lift-off) — test: tests/pipeline/test_t_014_043_il2_evaluation.py
- [ ] T-014-044 [US-014-1] (FR-014-36, SC-014-04, SC-014-09) per-metric verdicts: paired t for continuous, Clopper–Pearson on discordant episodes for binary; no composite — test: tests/pipeline/test_t_014_044_verdicts.py
- [ ] T-014-045 [US-014-1] (FR-014-37, FR-014-38, SC-014-05, SC-014-08) sim-to-sim gaps (twin and MPM) with paired t-intervals — test: tests/pipeline/test_t_014_045_sim_to_sim_gaps.py
- [ ] T-014-046 [US-014-2] (FR-014-22, FR-014-23) MPM tier with a fake backend (pairing, 16 ≤ n ≤ 64, k_f from particle mass, "not run" paths) — test: tests/unit/test_t_014_046_mpm_tier.py
- [ ] T-014-047 [US-014-1] (SC-014-01, SC-014-02, SC-014-03, SC-014-06, SC-014-07) acceptance table builder: observed rates against the pre-registered thresholds with intervals reported alongside — test: tests/pipeline/test_t_014_047_acceptance_table.py
- [ ] T-014-048 [US-014-5] (FR-014-24) optional IL-3: evaluated with IL-2's metrics and protocol when trained, "not run" otherwise — test: tests/unit/test_t_014_048_il3_optional.py

## Phase 6 — US-014-4 (P2) twins and web
- [ ] T-014-050 [US-014-4] (FR-014-40, P-014-12) IL-1 dynamic-bicycle twin (NumPy reference) — test: tests/metamorphic/test_t_014_050_bicycle_twin.py
- [ ] T-014-051 [US-014-4] (FR-014-41) IL-2 planar arm twin with FEE and torque-limited stalls (NumPy reference) — test: tests/unit/test_t_014_051_arm_twin.py
- [ ] T-014-052 [US-014-4] (FR-014-42) TypeScript twins against the Python goldens; ORT-web WASM actions against ORT CPU — test: web/src/engines/robots/twin-parity.test.ts
- [ ] T-014-053 [US-014-4] (FR-014-44) hostile twin inputs and corrupted ONNX hash — test: web/src/engines/robots/twin-hostile.test.ts
- [ ] T-014-054 [US-014-4] (FR-014-43, FR-014-45, FR-014-03, FR-014-24, NFR-014-04) live panels, "sim-to-sim" labels, replay fallback, "evaluated, not adopted" and "not run" states, frame time on T2 — test: web/e2e/robot-policies.spec.ts

## Phase 7 — Local GPU integration (reference machine, after the GPU hold is lifted)
- [ ] T-014-060 [US-014-3] (FR-014-02) kit-less smoke of the stock Cartpole task on `newton_mjwarp` — test: tests/gpu/test_t_014_060_isaaclab_smoke.py
- [ ] T-014-061 [US-014-2] (P-014-15, FR-014-17, FR-014-18) torch task cores against the NumPy references — test: tests/gpu/test_t_014_061_task_parity.py
- [ ] T-014-062 [US-014-1] (FR-014-05, FR-014-25, NFR-014-01, NFR-014-02) MJCF compile, short training run with resume, VRAM and time budget checks — test: tests/gpu/test_t_014_062_training_smoke.py
- [ ] T-014-063 [US-014-2] (FR-014-22) coupled rigid–MPM smoke — test: tests/gpu/test_t_014_063_mpm_smoke.py

## Phase 8 — Polish and review
- [ ] T-014-090 mutation run on `src/pitstudio/robots/` and `pitstudio_pipeline.evaluate.il`; record the score (numerical core ≥ 0.80)
- [ ] T-014-091 independent review of the diff against this spec; append tasks for gaps
