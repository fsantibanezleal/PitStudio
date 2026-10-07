# Plan 005 — Physics: `st50_physics` and physics benchmarks
Spec: ./spec.md

## Summary
One stage, `st50_physics`, in the `studio/` environment, with one module per solver under `pitstudio_studio.physics`:
`dem` (own Warp soft-sphere DEM — FR-005-01…15), `mpm_newton` (adapter over Newton's `SolverImplicitMPM` — FR-005-16,
FR-005-19…21), `mlsmpm2d` (own explicit 2-D reference twin — FR-005-17, FR-005-18, FR-005-20), `swe` (own shallow-water
solver with Bingham bed stress — FR-005-23…32), `dust` (own Lagrangian particles — FR-005-33…39) and `vehicles`
(reduced-order truck model + optional Newton rigid check — FR-005-40…44). Shared modules handle scenario validation,
device policy, outputs, benchmarks and errors (FR-005-45…53). Every benchmark is data: a scenario file, an oracle
function written from the cited source, a tolerance and a verdict row.

## Technical context
Runtime: Python 3.14 in `studio/` (`uv run --project studio --frozen …`); locked `warp-lang` 1.17.0, `newton` 1.6.0
(`sim` extra, with `mujoco-warp` 3.12.0), `zarr` 3.4.0, `pyarrow`, `numpy` 2.5.3. Oracles that need SciPy (ODE reference,
quadrature, root finding) run in the root `dev` environment or a `studio` dev group (T-004-002) — never inside the code
under test. Target: the reference GPU (16 GB) for `gpu` tests; Warp's CPU device for CI.

### CPU path and GPU-only tests per solver
| Solver | CPU path (CI, studio CPU job, CUDA hidden) | GPU-only (`gpu` marker, reference machine) |
|---|---|---|
| Warp DEM | Warp `"cpu"` device, serial: contact law, impact, restitution, incline, sliding, overflow, mass accounting, P-005-01…05 on two-body and 500-sphere cases, slot discharge (`slow`) | 3-D Beverloo (≈ 3 × 10⁵ spheres), repose benchmark, 3-D column collapse, deterministic re-run on CUDA |
| MLS-MPM 2-D twin | Warp `"cpu"`: P2G conservation, symmetry, time step, friction monotonicity, planar collapse at 128² (`slow`) | full-resolution planar collapse |
| Newton implicit MPM | none — Newton documents no CPU support (UNVERIFIED), so only a fake-solver adapter test (FR-005-16) runs in CI | silo, 3-D collapse, statistical re-run, P-005-11…13 |
| Shallow water | Warp `"cpu"`: Ritter, Stoker (400–1600 cells), lake at rest 128², Bingham channel, conservation, P-005-14…19 | real-terrain C2 crops |
| Dust | Warp `"cpu"`: settling, diffusion (2 × 10⁵ particles), mass budget, P-005-20…23, plume consistency (`slow`) | real-terrain C3 runs |
| Vehicles | Warp `"cpu"`: all reduced-order checks | Newton rigid box (FR-005-43) |

`gpu` tests also skip, with the hold text as the reason, while `gpu0.hold` exists in the lock directory, and never run
in CI.

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Real, not demo | yes | own solvers checked against laws before any rollout is used (FR-005-47, SC-005-01) |
| Spec before code | yes | every behaviour has an FR/P id |
| Acceptance-test-first | yes | benchmark tests are locked `[red]` before the kernels exist |
| Independent oracles | yes | analytical solutions (Hertz, rolling, Ritter, Stoker, Bingham film, Stokes, diffusion, plume, steady speed), published values (Lube 2004/2005, Beverloo exponent, C = 0.56), reference implementations (SciPy `solve_ivp`, `quad`, `brentq`) — never the solver under test |
| Determinism & explicit tolerances | yes | Warp deterministic mode, counter-based RNG, SHA re-run (FR-005-48, P-005-28); tolerances justified below |
| Neutral contracts | yes | DC-005-01…06, JSON Schema 2020-12 (T-005-001) |
| Static delivery | yes | parity goldens (FR-005-22) feed the browser twins' parity tests |
| Honesty | yes | `not run (no GPU)` never counts as `pass` (FR-005-49); UNVERIFIED targets shown in the report (FR-005-12) |
| Licence hygiene | yes | Warp and Newton are dependencies, never vendored; outputs are ours (CC-BY-4.0) |
| Simplicity | yes | one stage, plain Warp kernels, Newton used through a thin adapter |

## Design
Diagrams: ![DEM contact model](../../docs/assets/diagrams/dem-contact-model.svg) ·
![Tailings shallow water](../../docs/assets/diagrams/tailings-shallow-water.svg) ·
![Dust plume](../../docs/assets/diagrams/dust-plume.svg)

```text
scenario (DC-005-01) → validate (FR-005-51) → device policy (FR-005-49, FR-005-54) → solver → state checks (FR-005-52)
   → outputs: fields.zarr (DC-005-02), observables.parquet (DC-005-03), replay shards (DC-005-04)
   → benchmark rows (DC-005-05) → rollout stamps (FR-005-47) ; parity goldens (DC-005-06)
```

| Component (module) | Requirements |
|---|---|
| `physics.dem.contact` (Hertz–Mindlin, damping, rolling torque, effective properties) | FR-005-01…05 |
| `physics.dem.grid` (`HashGrid`, contact list) | FR-005-06, FR-005-07 |
| `physics.dem.step` (symplectic Euler for translation and rotation, dt guard, reduced-modulus record) | FR-005-08, FR-005-09, FR-005-15 |
| `physics.dem.benchmarks` (silo, slot, repose, collapse scenarios) | FR-005-10…12, FR-005-14 |
| `physics.measure` (repose, run-out percentile, steady-window flow rate, fits) | FR-005-13, FR-005-10, FR-005-14 |
| `physics.mpm_newton` (explicit configuration, outflow accounting, statistical re-run) | FR-005-16, FR-005-19…21 |
| `physics.mlsmpm2d` (P2G/G2P APIC, Drucker–Prager return map) | FR-005-17, FR-005-18, FR-005-20 |
| `physics.swe` (Rusanov + hydrostatic reconstruction, CFL, Bingham implicit friction, hydrograph, maps) | FR-005-23…32 |
| `physics.dust` (advection, settling, random walk, deposition, budget) | FR-005-33…39 |
| `physics.vehicles` (reduced-order model; Newton rigid adapter) | FR-005-40…44 |
| `physics.io` (replay quantisation and shards, Zarr, Parquet) | FR-005-45, FR-005-46 |
| `physics.report` (benchmark rows, rollout stamps, goldens) | FR-005-22, FR-005-47 |
| `physics.runtime` (validation, device policy, deterministic mode, OOM, non-finite checks, lock check) | FR-005-48…52, FR-005-54 |

Key decisions:
- **DEM integration:** symplectic (semi-implicit) Euler for positions and angular velocities; contact force and torque
  accumulated per particle with atomics (deterministic mode for reference runs).
- **Bingham friction (FR-005-29):** after the flux and bed-slope update gives momentum m*, set m = 0 if \|m*\| ≤ dt τ_y/ρ;
  otherwise solve \|m\| = \|m*\| − dt τ_b(\|m\|/h², h)/ρ for \|m\| by a bracketed Newton–bisection on [0, \|m*\|]
  (τ_b from the Buckingham–Reiner cubic), keeping the direction of m*. This is unconditionally stable and makes the
  arrest exact.
- **Hydrostatic reconstruction:** h_{i+1/2}^± = max(0, h^± + z^± − max(z_i, z_{i+1})) on each face (Audusse et al. 2004,
  SIAM J. Sci. Comput. 25(6):2050–2065, DOI 10.1137/S1064827503431090), which makes the lake at rest an exact discrete
  steady state up to round-off.
- **RNG:** Warp's counter-based `rand_init(seed, offset)` with offset = particle id × steps + step, so streams do not
  depend on launch order or device.
- **Device policy:** the stage entry point sets `CUDA_VISIBLE_DEVICES=-1` before `import warp` when running on the CPU
  (FR-005-49), and before CUDA work calls the stage helper's `require_lock("compute", N)`, which reads the runner's
  `PITSTUDIO_HELD_LOCKS` (FR-002-62, FR-002-63; FR-005-54); tests use a fake GPU backend module that reports devices,
  memory and raises `oom` on demand, and set the variable directly.
- **Stage protocol:** `python -m pitstudio_studio.physics.run` under spec 002's stage helper; error classes as message
  prefixes (`contact-overflow`, `dt-unstable`, `swe-input-invalid`, `dust-input-invalid`, `vehicle-input-invalid`,
  `physics-params-invalid`, `nonfinite-state`, `unbenchmarked-solver`) with `error_class: unknown`; `oom` and
  `lock-not-held` as the result's own error classes (spec 002).
- **Benchmark scenarios** live in `studio/recipes/_bench/physics/*.yaml` (validated by DC-005-01), so the same files
  drive tests and published reports.

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-005-01 | unit | hand calculation (spec values F_n = 0.6285 N, S_n = 1.8856 × 10⁴ N/m, S_t = 1.6162 × 10⁴ N/m) | pytest |
| FR-005-02 | unit | analytical Hertz impact (energy integral; constant 2.9433 from `scipy.integrate.quad`) | pytest, SciPy |
| FR-005-03 | unit | reference implementation: SciPy `solve_ivp` (DOP853, rtol 1 × 10⁻¹¹) of the 1-D damped Hertz ODE; nominal e | pytest, SciPy |
| FR-005-04 | unit | analytical rolling with torque cap: static iff tan θ ≤ μ_r, a = (5/7) g (sin θ − μ_r cos θ) | pytest |
| FR-005-05 | unit | analytical sliding-to-rolling: v = (5/7) v₀ at t = 2 v₀ / (7 μ_s g) | pytest |
| FR-005-06 | unit | hand-built 13-neighbour cluster (12 contacts fit, 13th overflows) | pytest |
| FR-005-07 | unit (hostile) | the same cluster with capacity 12 must raise `contact-overflow` | pytest |
| FR-005-08 | unit (hostile) | hand calculation of Δt_R for the worked example (0.197 ms at E = 50 MPa) and a dt above 0.2 Δt_R | pytest |
| FR-005-09 | unit | expected record fields and a benchmark re-run flag (hand-written expectation) | pytest |
| FR-005-10 | integration (gpu) | published law: Beverloo exponent 5/2 (Beverloo et al. 1961; DEM validation arXiv 2512.03698) and height independence; fit by `scipy.optimize.least_squares` | pytest, SciPy |
| FR-005-11 | integration (CPU, slow) | published plane-strain law exponent 3/2 (Dunatunga & Kamrin eq. 4.4) | pytest, SciPy |
| FR-005-12 | integration (gpu) | material-card target with its citation (handbook or lab value) | pytest |
| FR-005-13 | unit | analytical cones and ridges generated in the test (tan of the known angle) | pytest |
| FR-005-14 | integration (gpu) | published values: Lube et al. 2004 (1.24 a, 1.6 a^{1/2}) | pytest, NumPy polyfit |
| FR-005-15 | unit | exact integer accounting (hand count of particles through a declared outlet) | pytest |
| FR-005-16 | unit (fake solver) | a fake Newton solver records every parameter it receives; expected = the scenario values | pytest |
| FR-005-17 | unit | analytical: B-spline weights sum to 1 and first moments vanish, so Σ m_i = Σ m_p and Σ m_i v_i = Σ m_p v_p | pytest |
| FR-005-18 | integration (CPU slow, gpu) | published values: Lube et al. 2005 planar (1.2 a, 1.9 a^{2/3}) | pytest |
| FR-005-19 | integration (gpu) | published law: exponent 5/2 with k = 0 for a local continuum (Dunatunga & Kamrin, p. 13) | pytest, SciPy |
| FR-005-20 | unit | exact accounting (float64 sums of constant per-particle masses) | pytest |
| FR-005-21 | integration (gpu) | the first run's observables, compared within the stated statistical tolerance | pytest |
| FR-005-22 | integration | schema DC-005-06 and SHA-256 equality on a re-run (hashlib) | pytest, jsonschema |
| FR-005-23 | unit | hand calculation of one Rusanov flux and one hydrostatic-reconstruction face (2-cell example) | pytest |
| FR-005-24 | integration (CPU) | analytical Ritter solution (SWASHES §4.1.2): x_A = 3.6712 m, x_B = 7.6577 m, 10⁻³ h_l point at 7.5316 m | pytest |
| FR-005-25 | integration (CPU) | analytical Stoker solution (SWASHES §4.1.1): c_m = 0.157832 m/s, h_m = 2.5394 × 10⁻³ m, x_C = 6.2598 m (c_m by `scipy.optimize.brentq`) | pytest, SciPy |
| FR-005-26 | integration (CPU) | analytical: the lake at rest is an exact steady state | pytest |
| FR-005-27 | unit + property | invariant h ≥ 0; mass unchanged by the dry threshold (sum before and after) | Hypothesis |
| FR-005-28 | unit + property | conservation identity with the integrated source | Hypothesis |
| FR-005-29 | integration (CPU) | analytical Bingham film (derivation in spec §7): h_stop = 0.0647 m, U = 1.095 m/s for the worked example | pytest |
| FR-005-30 | unit | hand calculation on a synthetic 3-cell, 5-time-step depth series | pytest |
| FR-005-31 | unit | hand calculation: T = 2V/Q_p (Miraí: V = 3.8 × 10⁶ m³, Q_p = 422 m³/s → T = 1.801 × 10⁴ s); injected volume = V | pytest |
| FR-005-32 | unit (hostile) | each listed invalid input once; assert no kernel launch through a launch counter | pytest |
| FR-005-33 | unit | hand calculation of one particle step with a known noise draw | pytest |
| FR-005-34 | unit | analytical Stokes velocity (8.02 × 10⁻³ m/s for the spec example) | pytest |
| FR-005-35 | unit | analytical Wiener variance 2Kt | pytest |
| FR-005-36 | integration (CPU, slow) | analytical Gaussian plume with ground image and σ² = 2Kx/u | pytest |
| FR-005-37 | unit | exact conservation identity (float64) | pytest |
| FR-005-38 | unit | hand-placed particles above a two-cell terrain with known bilinear heights | pytest |
| FR-005-39 | unit (hostile) | each listed invalid input once (Reynolds number by hand at ρ_p = 2650 kg/m³: R = 30 µm gives Re ≈ 1.16 → rejected; R = 25 µm gives Re ≈ 0.67 → accepted) | pytest |
| FR-005-40 | unit | hand calculation of one integration step | pytest |
| FR-005-41 | unit | analytical steady speed; `scipy.optimize.brentq` root with drag | pytest, SciPy |
| FR-005-42 | unit | analytical energy balance (trapezoid quadrature of the logged series in float64) | pytest |
| FR-005-43 | integration (gpu) | analytical sliding block: a = g (sin θ − μ cos θ) (μ = 0.5, θ = 35° → 1.609 m/s²) | pytest |
| FR-005-44 | unit (hostile) | each listed invalid input once | pytest |
| FR-005-45 | unit | schema DC-005-04; shard sizes counted with `os.stat`; SHA-256 by hashlib | pytest, jsonschema |
| FR-005-46 | unit + contract | schemas DC-005-02/03; units read back from metadata | pytest, jsonschema |
| FR-005-47 | unit + contract | schema DC-005-05; stamps recomputed from a hand-written report; production scenarios with no report, with a `fail` row and with a `not run` row must be refused before any launch (launch counter) | pytest, jsonschema |
| FR-005-48 | integration (CPU, gpu) | SHA-256 equality of two runs (hashlib) | pytest |
| FR-005-49 | unit (fake GPU backend) | environment variable inspected in a child process; fake backend with no device; GPU-only rows must read `not run (no GPU)` | pytest |
| FR-005-50 | unit (fake GPU backend) | fake backend raising out-of-memory at a set allocation; expected error class and payload | pytest |
| FR-005-51 | contract (hostile) | schema-generated invalid scenarios (unknown enum, out-of-domain values, NaN, oversized counts); 1 s wall-clock bound | Hypothesis, jsonschema |
| FR-005-52 | unit (hostile) | a state injected with NaN at a known step and index | pytest |
| FR-005-54 | unit (fake GPU backend) | hand-written `PITSTUDIO_HELD_LOCKS` values (`gpu0.compute` → runs; unset, empty, `gpu0.nvenc`, `gpu1.compute` for device 0, malformed → `lock-not-held`); the fake backend records any context creation | pytest |
| P-005-01 | metamorphic | Froude similarity (dimensional analysis of the Hertz–Mindlin law with E ∝ λ) | pytest |
| P-005-02 | metamorphic | translation invariance | pytest |
| P-005-03 | metamorphic | rotation invariance (exact axis permutation) | pytest |
| P-005-04 | metamorphic | time-step self-convergence | pytest |
| P-005-05 | metamorphic | permutation invariance | pytest |
| P-005-06 | metamorphic | monotonicity in friction and orifice size | pytest |
| P-005-07 | property | partition of unity of quadratic B-splines | Hypothesis |
| P-005-08 | metamorphic | mirror symmetry | pytest |
| P-005-09 | metamorphic | time-step self-convergence | pytest |
| P-005-10 | metamorphic | monotonicity in friction | pytest |
| P-005-11 | metamorphic (gpu) | resolution convergence | pytest |
| P-005-12 | metamorphic (gpu) | azimuthal symmetry | pytest |
| P-005-13 | metamorphic (gpu) | monotonicity in friction | pytest |
| P-005-14 | metamorphic | mirror symmetry | Hypothesis |
| P-005-15 | metamorphic | 90° rotation | Hypothesis |
| P-005-16 | metamorphic | Froude scaling of the shallow-water equations with Bingham stress | pytest |
| P-005-17 | metamorphic | monotonicity in yield stress | pytest |
| P-005-18 | metamorphic | Newtonian and frictionless limits; Newtonian film U = ρ g h² S/(3 μ_B) | pytest |
| P-005-19 | property | grid convergence | pytest |
| P-005-20 | metamorphic | linearity in emission | pytest |
| P-005-21 | metamorphic | rotation of the wind | pytest |
| P-005-22 | metamorphic | time-step invariance of a constant-coefficient SDE (exact in distribution) | pytest |
| P-005-23 | metamorphic | monotonicity in radius | pytest |
| P-005-24 | metamorphic | scaling of mass, power and forces | pytest |
| P-005-25 | metamorphic | monotonicity in grade and length | pytest |
| P-005-26 | metamorphic | time-step self-convergence | pytest |
| P-005-27 | property | analytical quantisation bound | Hypothesis |
| P-005-28 | property | exact equality | pytest |
| NFR-005-01, NFR-005-02, NFR-005-04 | pipeline (data phase) | thresholds in the spec | run manifests |
| NFR-005-03 | CI | job time | CI |
| NFR-005-05 | unit | presence check on the benchmark report | pytest |
| SC-005-01, SC-005-02 | pipeline (data phase) | benchmark reports; FR-000-05 decision rule | pytest on published runs |
| DC-005-01…06 | contract | JSON Schema 2020-12 meta-validation; valid and invalid examples; generated types round-trip | jsonschema |

### Tolerances and their justification
| Quantity | Tolerance | Why |
|---|---|---|
| Contact forces (FR-005-01) | rtol 1 × 10⁻⁵ | float32 kernel, about ten operations, each ≤ 6 × 10⁻⁸ relative |
| Impact overlap and duration (FR-005-02) | 1 % at dt = t_c/200 | first-order time integration resolves the contact end to one step (0.5 % of t_c) |
| Restitution (FR-005-03) | ± 0.01; 0.5 % across speeds | the reference ODE gives the law's restitution to < 10⁻⁴; one-step quantisation of the separation event at dt = t_c/200 is ≈ 0.5 %. The damped Hertz law is velocity-independent by dimensional analysis (overlap scales as v₀^{4/5}, time as v₀^{−1/5}, the damping term keeps a constant ratio) |
| Rolling and sliding (FR-005-04, FR-005-05) | 1 % (2 % for the event time) | mean acceleration over ≥ 0.5 s after the transient; event detection quantised to one step |
| Beverloo (FR-005-10) | ± 5 % per point; exponent ± 0.15 | ± 5 % is the plan's tolerance and the scatter of published DEM fits; the flow-rate noise over the steady window with ≥ 10⁵ outflowing particles is < 1 %; ± 0.15 is 6 % of 5/2 and covers the local-MPM result 1.47 vs 1.5 |
| Slot discharge (FR-005-11) | ± 10 % | ≈ 6 × 10³ particles: flow-rate noise ≈ 3 % at 3σ, plus wall effects in a thin slab |
| Repose (FR-005-12, P-005-11) | ± 1.5° | the plan's tolerance; measurement error alone ≤ 0.5° (FR-005-13) |
| Collapse exponents (FR-005-14, FR-005-18) | ± 0.15 (linear band), ± 0.12 (power band); prefactor ratio [0.5, 2.5] | experimental exponents are reported as "≃"; numerical studies differ in prefactor by up to 2.1× (DEM 2.5 a vs experiment 1.2 a, Staron & Hinch p. 6), so the prefactor gate only rejects gross errors |
| Shallow-water L1 (FR-005-24, FR-005-25) | ≤ 5 % at 400 cells; order ≥ 0.5 | first-order schemes converge at order 1/2 in L1 near discontinuities and up to 1 in smooth rarefactions |
| Stoker middle state and bore (FR-005-25) | ± 2 % | the plateau is measured away from the smeared edges (inner 80 %); a first-order bore is smeared over ≈ 3–5 cells = 0.3 % of the domain at 400 cells |
| Lake at rest (FR-005-26) | ≤ 1 × 10⁻³ m/s | round-off in float32 fluxes gives δu ≈ ε₃₂ √(g h) √n ≈ 1.2 × 10⁻⁷ × 10 × 32 ≈ 4 × 10⁻⁵ m/s after 10³ steps; a non-balanced scheme produces currents of cm/s to m/s on benches, so 10⁻³ still discriminates |
| Volume conservation (FR-005-28) | ≤ 1 × 10⁻⁵ | the flux form is conservative exactly in real arithmetic; unbiased float32 rounding over 10⁴ steps stays several orders below |
| Bingham film (FR-005-29) | ± 2 % | uniform steady flow is an exact discrete fixed point; 2 % covers incomplete relaxation after ≥ 10 relaxation times |
| Stokes settling (FR-005-34) | rtol 1 × 10⁻⁵ | float32 constant-velocity integration |
| Diffusion (FR-005-35) | ± 2 % | relative standard error of a sample variance √(2/(N − 1)) = 0.32 % at N = 2 × 10⁵: 2 % is > 6σ |
| Plume consistency (FR-005-36) | ± 10 % | Monte Carlo noise ≈ 1 % per bin at ≥ 10⁴ residences; finite bin height (≤ 0.1 σ_z) bias < 1 %; the slender-plume approximation neglects along-wind diffusion (Péclet u x/K ≥ 300) |
| Mass budgets (FR-005-15, FR-005-20, FR-005-37) | exact / ≤ 1 × 10⁻⁹ | integer counting; float64 accumulators of float32 masses |
| Vehicle steady speed (FR-005-41) | ± 0.5 % | the steady state is a fixed point independent of dt; 0.5 % covers incomplete settling after 10 relaxation lengths |
| Vehicle energy (FR-005-42) | ≤ 1 × 10⁻⁴ | trapezoid quadrature error O(dt²) with dt = 0.05 s over 600 s |
| Similarity and symmetry (P-005-01…03, P-005-14…16) | rtol 1 × 10⁻⁴ / atol as stated | the transformed runs differ only by float32 rounding of scaled or permuted values; observables of many-body (chaotic) runs are compared, not trajectories |
| Newton MPM re-run (FR-005-21) | run-out ± 2 %, repose ± 0.5°, Q ± 2 % | half of the benchmark tolerances, so that a re-run cannot flip a verdict unnoticed |

Proposed `thresholds.yaml` keys (proposed keys, pending maintainer approval; values above): `physics.beverloo_point_rtol: 0.05`,
`physics.beverloo_exponent_atol: 0.15`, `physics.repose_atol_deg: 1.5`, `physics.collapse_exponent_atol: [0.15, 0.12]`,
`physics.swe_l1_max: 0.05`, `physics.swe_volume_drift_max: 1.0e-5`, `physics.mass_drift_twin_max: 0.005`.

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Own DEM, MLS-MPM twin, shallow-water and dust kernels | testable, citable cores mirrored by WGSL twins; Warp's DEM example is a linear toy | adopting a black-box engine (PhysX particles, Genesis, DEM-Engine) loses calibration, Windows support or the twin mirror |
| Newton MPM tests GPU-only | Newton documents no CPU path | testing Newton on CPU could pass or fail for reasons unrelated to our use |
| `slow` CPU benchmarks | serial Warp CPU makes 10³–10⁴-particle benchmarks take minutes | smaller cases would not reach the asymptotic regimes the laws describe |
| Risk: Newton API change on upgrade | Newton releases monthly | the lock pins 1.6.0; an upgrade re-runs every benchmark (FR-005-47 stamps the version) |
| Risk: deterministic mode is slow | its cost is measured, not assumed (FR-005-48) | — |
