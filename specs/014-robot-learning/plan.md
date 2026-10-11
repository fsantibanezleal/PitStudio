# Plan 014 — Robot learning (M21)
Spec: ./spec.md

## Summary

The feature has four parts:

- **Reference cores** (`src/pitstudio/robots/`, Python 3.14, NumPy, CI-tested). They hold every piece of mining
  physics and decision logic that the tasks, baselines, twins and evaluation share:
  - the FEE wedge (FR-014-17, FR-014-21);
  - the fill model (FR-014-18);
  - TTC (FR-014-34);
  - the observation and reward builders (FR-014-08 to FR-014-11);
  - the randomisation samplers (FR-014-13, FR-014-19);
  - pure pursuit + PID (FR-014-29, FR-014-31);
  - the twins (FR-014-40, FR-014-41).
- **Isaac Lab tasks** (`studio/isaaclab/`, Python 3.12, local only). These are the kit-less `Pit-HaulTruck-Ramp` and
  `Pit-Excavator-Dig-FEE` tasks with vectorised torch versions of the cores, parity-tested against them (P-014-15).
  They cover rsl_rl training, the handoff and the MPM evaluation (FR-014-02 to FR-014-06, FR-014-12 to FR-014-27,
  FR-014-30).
- **Evaluation** (`pipeline/` `s50_evaluate`) covers FR-014-32 to FR-014-39. Export goes through `s60_export`
  (spec 016; FR-014-27, FR-014-28).
- **Web**: TS twins with ORT-web policies (FR-014-42 to FR-014-45).

## Technical context

Runtimes:
- `studio/isaaclab/`: Python 3.12, locked to the v3.0.0-EA stack (FR-014-01): Isaac Lab packages from the tag, torch
  2.11.0+cu128, warp-lang 1.16.0, newton 1.5.2, MuJoCo / MuJoCo-Warp 3.11, rsl-rl-lib 5.4.1 (168 locked packages). It
  is entered only via `uv run --project studio/isaaclab --frozen`.
- Root and `pipeline/`: Python 3.14; NumPy, SciPy (reference statistics in tests), `minephys` (haulage envelopes).
- `web/`: TypeScript twins, ORT-web 1.30 (WASM / WebGPU).

Targets: the reference laptop GPU for training (`gpu0.compute`); CI for the reference cores, evaluation, contracts,
lock checks and web parity.

## Constitution check

| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | Real Bingham ramp geometry; real training with a pinned framework; machines from published academic dimensions; no field claim (FR-014-45) |
| Spec before code | yes | Task design (observations, actions, rewards, terminations, randomisation, stall rule) is fixed in FR-014-08 to FR-014-20 before code |
| Acceptance-test-first | yes | Every task in `tasks.md` is `[red]`/`[green]`; the plan's §7 criteria are SC-014-01 to SC-014-10 |
| Independent oracles | yes | FR-014-17 oracle = 2 × 2 wedge equilibrium solve + hand calculation; FR-014-29 = Coulter worked relation; statistics = SciPy reference implementations (`scipy.stats.binomtest(...).proportion_ci(method="exact")`, `scipy.stats.ttest_rel`, `statsmodels` Wilson); twins = analytical steady states |
| Determinism and tolerances | yes | Seeds derived per episode; evaluation uses deterministic actions; training is `statistical`; tolerances justified in spec §7 |
| Neutral contracts | yes | DC-014-01 to DC-014-05 new (T-014-001); DC-014-06, DC-014-07 reuse foundation contracts |
| Static delivery | yes | Live TS twins with replay fallback (FR-014-43); rollouts are REPLAY |
| Honesty | yes | "evaluated, not adopted" path (FR-014-03); "sim-to-sim" labels; "not run" for IL-2b/IL-3; per-metric verdicts only |
| Licence hygiene | yes | Isaac Lab BSD-3, Newton Apache-2.0; no NVIDIA or Isaac Lab robot asset; Apache-2.0 headers on task code (NFR-014-05); weights Apache-2.0 + attribution |
| Simplicity | yes | Isaac Lab used only for the two tasks that need articulation and contact; reference cores shared by the tasks, the twins and the evaluation |

## Design

![Isaac Lab task loop: vectorised environments, PPO, ONNX export and the TypeScript twin](../../docs/assets/diagrams/isaac-lab-task-loop.svg)

Related diagram: `docs/assets/diagrams/terramechanics-fee.svg` (the FEE wedge).

| Component | Location | Requirements |
|---|---|---|
| FEE wedge reference (factors, β* minimiser, H/V split) | `src/pitstudio/robots/fee.py` | FR-014-17, FR-014-21, P-014-01 to P-014-06 |
| Fill model | `src/pitstudio/robots/fill.py` | FR-014-18, P-014-13 |
| TTC | `src/pitstudio/robots/ttc.py` | FR-014-34, FR-014-47, P-014-08 |
| Task-parameter validation | `src/pitstudio/robots/config.py` (shared by the tasks and the evaluation) | FR-014-46 |
| Observation and reward builders (backend-agnostic state arrays) | `src/pitstudio/robots/obs.py`, `reward.py` | FR-014-08, FR-014-11, FR-014-15, P-014-09, P-014-10 |
| Randomisation samplers | `src/pitstudio/robots/randomise.py` | FR-014-13, FR-014-19, P-014-14 |
| Baselines (pure pursuit + PID; scripted dig) | `src/pitstudio/robots/baselines.py` | FR-014-29 to FR-014-31, P-014-07 |
| Twins (NumPy references) | `src/pitstudio/robots/twins.py` | FR-014-40, FR-014-41, P-014-12 |
| Machine generators (MJCF writers) | `src/pitstudio/robots/machines.py` | FR-014-05 to FR-014-07 |
| Lock and probe checks | `tests/contract` lock parser; `studio/bench/probe_isaaclab.py` | FR-014-01, FR-014-02, FR-014-04 |
| Planner gating and tool status | runner planner hook + `studio/tools.yaml` | FR-014-03 |
| Isaac Lab tasks (torch vectorised cores, env configs, rsl_rl configs, train/resume, OOM fallback, handoff, evaluation-mode rollouts) | `studio/isaaclab/src/pitstudio_isaaclab/` | FR-014-09, FR-014-10, FR-014-12, FR-014-14, FR-014-16, FR-014-20, FR-014-25 to FR-014-27, P-014-15 |
| MPM evaluation tier | `studio/isaaclab/src/pitstudio_isaaclab/mpm_eval.py` | FR-014-22, FR-014-23 |
| Evaluation (metrics, verdicts, gaps, hostile checks) | `pipeline/src/pitstudio_pipeline/evaluate/il.py` | FR-014-32 to FR-014-39, P-014-11 |
| Export hooks (size, opset, IR, normaliser) | spec 016 `s60_export`, with IL handoff validation | FR-014-27, FR-014-28, NFR-014-03 |
| TS twins, panels, hostile clamps | `web/src/engines/robots/` | FR-014-42 to FR-014-45, NFR-014-04 |

**Data flow.** `st10_terrain` and `st20_pit_design` (ramp segments) and the machine generators → `st60_il_train`
writes checkpoints, the handoff and evaluation episode tables (policy and baseline arms) → `st61_il_mpm_eval` writes
MPM episode tables → twin runner (pipeline) writes twin episode tables → `s50_evaluate` writes the acceptance tables,
verdicts and gaps → `s60_export` writes the ONNX policies and twin bundles → web.

## Test strategy

| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-014-01 | contract | the lock file itself (TOML parse) against the pinned list | pytest |
| FR-014-02 | contract + gpu | probe output schema; local run of the stock task | pytest (`gpu`, local) |
| FR-014-03 | unit + E2E | capabilities fixtures (fail, skip, missing, invalid) → planner and registry states | pytest + Playwright |
| FR-014-04 | contract | lock scan; manifest marker on fixture locks with and without a restricted package | pytest |
| FR-014-05 | unit + gpu | hand calculation of mass and wheelbase sums from the parameter file; local MuJoCo compile | pytest |
| FR-014-06 | unit | parameter file vs parsed MJCF attributes | pytest |
| FR-014-07 | unit | hostile parameter corpus | pytest + Hypothesis |
| FR-014-08 | unit | hand-constructed states with known body-frame coordinates | pytest |
| FR-014-09 | unit | hand calculation of the action mapping and clipping | pytest |
| FR-014-10 | unit | NaN/inf injection | pytest |
| FR-014-11 | unit | hand-computed reward for a scripted 3-step trajectory | pytest |
| FR-014-12 | unit | scripted trajectories reaching each termination | pytest |
| FR-014-13 | unit | range checks + `scipy.stats.kstest` (P-014-14) | pytest + Hypothesis |
| FR-014-14 | unit | counting the evaluation scenario set; conflict-point geometry | pytest |
| FR-014-15, FR-014-16 | unit | hand-constructed arm states | pytest |
| FR-014-17 | unit + parity | 2 × 2 equilibrium solve (P-014-04) + worked example (P-014-06) | pytest + NumPy |
| FR-014-18 | unit | analytical swept area for a straight tip path (P-014-13) | pytest |
| FR-014-19 | unit | range checks and δ ≤ φ | pytest + Hypothesis |
| FR-014-20 | unit | synthetic torque traces (0.99 s vs 1.00 s at limit) | pytest |
| FR-014-21 | unit | hostile corpus incl. α + δ + φ ≥ π | pytest + Hypothesis |
| FR-014-22 | unit + gpu | fake MPM backend (pairing, n bounds, k_f formula on a hand-built particle set) | pytest |
| FR-014-23, FR-014-24 | unit (+ E2E for FR-014-24) | fixture states → "not run" | pytest + Playwright |
| FR-014-25 | unit + gpu | fake trainer: config values, checkpoint cadence, resume equality of iteration and optimiser state | pytest |
| FR-014-26 | unit | fake trainer raising OOM once, then twice | pytest |
| FR-014-27 | contract + pipeline | schema; ONNX checker for opset/IR; size; parity on goldens (`onnxruntime` vs torch) | pytest |
| FR-014-28 | unit | hostile handoff corpus | pytest |
| FR-014-29 | unit | Coulter relation hand calculation (P-014-07); PID step response against the discrete-PID difference equation | pytest |
| FR-014-30 | unit | seed-disjointness and freeze check (hash of the tuned parameters before evaluation) | pytest |
| FR-014-31 | unit | hostile paths | pytest |
| FR-014-32 | unit | seed-set fixtures (disjointness, pairing) | pytest |
| FR-014-33 | unit | hand calculation on a 3-episode table; Wilson via `statsmodels.stats.proportion.proportion_confint(method="wilson")` | pytest |
| FR-014-34 | unit | analytical head-on and crossing cases (P-014-08) | pytest |
| FR-014-35 | unit | hand calculation of k_f, t_c, P on scripted episodes | pytest |
| FR-014-36 | unit | `scipy.stats.ttest_rel(...).confidence_interval()`; `scipy.stats.binomtest(b, b + c).proportion_ci(method="exact")`; hand calculation (b = 8, c = 1 → lower bound 0.518, "better"; b = 5, c = 0 → lower bound 0.478, "no significant difference") | pytest |
| FR-014-37, FR-014-38 | unit | t-interval by hand on 5-pair fixtures; `scipy.stats.t.ppf` | pytest |
| FR-014-39 | unit | hostile episode-table corpus | pytest + Hypothesis |
| FR-014-40, FR-014-41 | unit + parity | analytical steady states (P-014-12); FEE reference | pytest + Vitest |
| FR-014-42 | parity (web) | Python twin goldens; ORT CPU outputs | Vitest |
| FR-014-43, FR-014-45 | E2E | DOM states (badges, labels, fallback) | Playwright |
| FR-014-44 | web unit + E2E | hostile inputs; corrupted ONNX hash | Vitest + Playwright |
| FR-014-46 | unit | hostile task-parameter corpus; configuration-hash mismatch on resume | pytest + Hypothesis |
| FR-014-47 | unit | hostile core inputs | pytest + Hypothesis |
| P-014-01 to P-014-05 | metamorphic | relations stated in the spec | Hypothesis (≥ 200 examples) |
| P-014-06 | unit | hand calculation (spec §7 table) | pytest |
| P-014-07 to P-014-13 | metamorphic | relations stated in the spec | Hypothesis |
| P-014-14 | property | ranges + KS test | Hypothesis + SciPy |
| P-014-15 | parity (gpu) | NumPy float64 reference | pytest (`gpu`, local) |
| NFR-014-01, NFR-014-02 | gpu (local) | NVML telemetry thresholds | pytest |
| NFR-014-03 | CI | file size | budget check |
| NFR-014-04 | E2E | measured frame time on T2 | Playwright |
| NFR-014-05 | unit | repository scan with a planted-violation fixture | pytest |
| SC-014-01 to SC-014-10 | pipeline | `s50_evaluate` / `s60_export` outputs on the real runs (data-and-models phase), computed by the code verified above | pytest (`tests/pipeline`) |

## Risks and complexity tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Two implementations of each core (NumPy reference, torch task), plus a TS twin | Training needs vectorised GPU code; CI and parity need a testable reference; the web needs TS | Testing only the torch task would leave the physics untested in CI (the environment never runs in CI) |
| Clopper–Pearson on discordant pairs for binary verdicts | A Wald or bootstrap interval is anti-conservative with few discordant episodes (b = 5, c = 0 would read as "better") | DEC-0016 requires an interval method fixed per comparison; the exact method is equivalent to an exact McNemar test |
| Evaluation in the 3.14 pipeline from episode tables | Keeps statistics CI-tested and environment-independent | Computing verdicts inside the 3.12 task code would duplicate the decision rule |

Open risks: Isaac Lab EA API churn before GA (exact pins; the lane is optional); the Windows kit-less smoke may fail
(the "evaluated, not adopted" path is specified); MPM coupling is beta (evaluation tier only, "not run" path).
