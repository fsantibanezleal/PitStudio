# Spec 005 — Physics: `st50_physics` (Warp DEM, Newton implicit MPM, GPU shallow water, dust particles, vehicles) and physics benchmarks
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent
PitStudio's granular, tailings, dust and vehicle results come from GPU solvers in the open studio lane (`studio/`,
Python 3.14). A wrong solver poisons everything downstream: the GNS and FNO surrogates, the D1 muck-pile PSDs, the A3
bucket fills, the C2 flood maps and the browser twins. This spec fixes the solvers of stage `st50_physics` — an own
soft-sphere DEM in Warp (Hertz–Mindlin with rolling resistance), Newton's `SolverImplicitMPM`, an own explicit 2-D
MLS-MPM reference twin, an own depth-averaged shallow-water solver with Bingham bed stress, own Lagrangian dust
particles and a batched reduced-order truck model (plus a Newton rigid-body check) — and the **physics benchmarks**
every solver must pass, against analytical solutions and published values, before its rollouts are used anywhere:
contact mechanics, Beverloo discharge, angle of repose, granular column collapse (Lube et al.), dam break (Ritter,
Stoker), Bingham sheet flow, Stokes settling, diffusion and plume consistency, steady vehicle speed, and mass
conservation, each with at least three metamorphic relations per solver. Every solver has a CPU path (Warp's CPU device)
for CI except Newton's implicit MPM and Newton rigid bodies, which are GPU-only. Out of scope: DEM calibration and the
GNS and FNO surrogates (spec 011), the WGSL browser twins and their parity tests (spec 018), the closed-form models
(`minephys`: Beverloo function, AP-42, Gaussian plume), Isaac Lab (spec 014), the runner's locks, guards, retries,
telemetry sampling and publication (spec 002), and the stage-side evidence helpers (spec 006).

## 2. User stories
### US-005-1 (P1) A DEM that reproduces granular laws
As a reviewer, I want the Warp DEM to pass contact-mechanics checks, the Beverloo discharge law, the repose target and
the column-collapse run-out scaling, so that its muck piles and bucket fills can be trusted. Independent test: run the
DEM benchmark set; the benchmark report shows every check with its oracle value, tolerance and verdict.

### US-005-2 (P1) MPM solvers that agree with the same laws
As a reviewer, I want Newton's implicit MPM and the explicit 2-D MLS-MPM twin to conserve mass and momentum and to
reproduce the column-collapse and discharge scaling, so that large-volume piles and the browser twin rest on checked
physics. Independent test: run the MPM benchmark set (CPU twin in CI, Newton on the GPU) and read the report.

### US-005-3 (P1) A tailings solver verified on dam breaks and Bingham flow
As a mining engineer, I want the shallow-water solver verified against the Ritter and Stoker dam breaks, a lake at rest,
mass conservation and the Bingham sheet-flow solution, so that C2 arrival times, depths and areas mean something.
Independent test: run the shallow-water benchmark set on the CPU device and compare with the analytical solutions.

### US-005-4 (P2) Dust particles that settle and spread correctly
As a student, I want the Lagrangian dust model to settle at the Stokes velocity, spread as a random walk, match the
Gaussian plume on flat ground and close its mass budget, so that C3 maps over the real pit are credible.
Independent test: run the dust benchmark set on the CPU device.

### US-005-5 (P2) Vehicles with the right steady speed and energy
As a mining engineer, I want the batched truck model to reach the analytical steady speed on a grade and close its
energy balance, so that ramp travel times and energy feed the haulage cases correctly. Independent test: run the vehicle
benchmark set on the CPU device.

### US-005-6 (P1) Disciplined outputs on one shared GPU
As the maintainer, I want every physics run to write schema-valid fields, observables, replay shards and a benchmark
report, to run deterministically where Warp allows, to stay off the GPU when it must, and to fail with classified errors,
so that runs are reproducible and safe on a shared GPU. Independent test: run a scenario with a fake GPU backend that
raises out-of-memory, then on the CPU device under a hold file, and check the error class and that no CUDA context
was created.

Story index (for traceability):

| ID | Priority | Title |
|---|---|---|
| US-005-1 | P1 | A DEM that reproduces granular laws |
| US-005-2 | P1 | MPM solvers that agree with the same laws |
| US-005-3 | P1 | A tailings solver verified on dam breaks and Bingham flow |
| US-005-4 | P2 | Dust particles that settle and spread correctly |
| US-005-5 | P2 | Vehicles with the right steady speed and energy |
| US-005-6 | P1 | Disciplined outputs on one shared GPU |

## 3. Functional requirements (EARS)
Units are SI (m, s, kg, Pa); angles in degrees; g = 9.81 m/s². "Warp CPU" means Warp's `"cpu"` device, on which kernels
run serially; it is the CI path. Requirements verified on the GPU are marked `(gpu)` and run only on the reference
machine, never in CI. Every benchmark writes one row of the benchmark report (DC-005-05). The stage runs under spec
002's stage helper: error classes named below travel as the prefix of the stage-result message (`<class>: <detail>`)
with `error_class: unknown`, except `oom` and `lock-not-held`, which are the stage result's own `error_class` values
(spec 002, FR-002-63).

### 3.1 Soft-sphere DEM (Warp)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-005-01 | Ubiquitous | The DEM shall compute contacts with Hertz normal force F_n = (4/3) E* √R* δ_n^{3/2}, normal damping F_n^d = −2 √(5/6) β √(S_n m*) v_n^rel with S_n = 2 E* √(R* δ_n) and β = ln e / √(ln² e + π²), Mindlin tangential spring F_t = −S_t δ_t with S_t = 8 G* √(R* δ_n), accumulated tangential history and the Coulomb cap \|F_t\| ≤ μ_s F_n, and an elastic–plastic rolling-resistance torque capped at μ_r R* F_n, where 1/E* = (1 − ν₁²)/E₁ + (1 − ν₂²)/E₂, 1/G* = (2 − ν₁)/G₁ + (2 − ν₂)/G₂ with G = E / (2(1 + ν)), 1/R* = 1/R₁ + 1/R₂ (R → ∞ for a wall) and 1/m* = 1/m₁ + 1/m₂; for two spheres of R = 5 mm, E = 50 MPa, ν = 0.25 at δ_n = 0.01 R it shall return F_n = 0.6285 N, S_n = 1.8856 × 10⁴ N/m and S_t = 1.6162 × 10⁴ N/m. | unit (Warp CPU) |
| FR-005-02 | Event | When two equal elastic spheres (e → 1, μ_s = 0) collide head-on at relative speed v₀ ∈ [0.1, 10] m/s, the DEM shall reproduce the Hertz maximum overlap δ_max = (15 m* v₀² / (16 E* √R*))^{2/5} and the contact duration t_c = 2.9433 δ_max / v₀ within 1 % at dt = t_c / 200. | unit (Warp CPU) |
| FR-005-03 | Ubiquitous | The DEM's realised coefficient of restitution in a head-on two-sphere impact shall be within ± 0.01 of the nominal e for every e ∈ [0.1, 0.95], and shall vary by ≤ 0.5 % over impact speeds 0.1–10 m/s. | unit (Warp CPU) |
| FR-005-04 | Event | When a single sphere rests on a rigid plane inclined at θ with μ_r < μ_s, the DEM shall keep it at rest (centre speed ≤ 1 × 10⁻⁴ m/s after 1 s) for tan θ ≤ 0.95 μ_r, and for tan θ ≥ 1.05 μ_r (and tan θ < μ_s) shall make it roll with the mean acceleration a = (5/7) g (sin θ − μ_r cos θ) within 1 %. | unit (Warp CPU) |
| FR-005-05 | Event | When a sphere is launched sliding (v₀ > 0, ω₀ = 0, μ_r = 0) on a horizontal plane, the DEM shall reach pure rolling at speed (5/7) v₀ within 1 % after the time 2 v₀ / (7 μ_s g) within 2 %. | unit (Warp CPU) |
| FR-005-06 | Ubiquitous | The DEM shall find neighbours with Warp's `HashGrid` and store tangential and rolling history in a fixed-capacity per-particle contact list of declared capacity (default 12). | unit (Warp CPU) |
| FR-005-07 | Unwanted | If a particle's contacts exceed the contact-list capacity, then the DEM shall stop with error class `contact-overflow` reporting the particle index, its contact count and the step, and shall never drop a contact silently. | unit (hostile) |
| FR-005-08 | Unwanted | If the declared time step exceeds f_R × Δt_R, where Δt_R = π R_min √(ρ/G) / (0.1631 ν + 0.8766) for the smallest particle and f_R is declared (default 0.2), then the DEM shall reject the scenario with error class `dt-unstable` stating both values. | unit (hostile) |
| FR-005-09 | Optional | Where a scenario uses a Young's modulus below the material's real value, the DEM shall record both values in the observables and the benchmark report, and the Beverloo and repose benchmarks of that material shall be run at the reduced value before the scenario's rollouts are used. | unit |
| FR-005-10 | Event | When the 3-D Beverloo benchmark runs (flat-bottomed cylindrical silo of diameter 60 d filled to 90 d, orifice ratios D/d ∈ {5, 8, 10, 12.5, 15, 17.5, 20}), the DEM shall measure the steady mass flow rate Q over the window in which the silo holds 80 % to 30 % of its initial mass, such that (a) Q over the first and the second half of the window agree within ± 5 % (height independence), (b) every Q is within ± 5 % of the least-squares fit Q = C ρ_b √g (D − k d)^{5/2} with ρ_b the measured bulk density and k ≥ 0, and (c) a fit with a free exponent gives 2.5 ± 0.15; C is reported next to the published C = 0.56. | integration (gpu) |
| FR-005-11 | Event | When the quasi-2-D slot benchmark runs on Warp CPU (a box 30 d wide and 45 d high, periodic over a thickness of 4 d, slot widths W/d ∈ {4, 6, 8, 10}), the DEM shall give flow rates per unit thickness each within ± 10 % of the fit Q = C ρ_b √g (W − k d)^{3/2} with k ≥ 0. | integration (Warp CPU, slow) |
| FR-005-12 | Event | When the repose benchmark of a material card runs (with the measurement method the card declares: `lifted-cylinder` or `poured-cone`), the DEM shall produce a repose angle within ± 1.5° of the card's target, and the report shall show the target's citation and verification status. | integration (gpu) |
| FR-005-13 | Ubiquitous | The repose-angle measurement shall build the pile's surface height field on a grid of spacing ≤ d/2 (top of the highest particle per cell), average it radially about the pile axis (or along the ridge), fit a line to the flank where 0.1 h_max ≤ h ≤ 0.8 h_max, and return atan of the slope magnitude, within 0.1° on noise-free analytic cones and ridges of 20°–50° and within 0.5° on cones sampled with particles of diameter d. | unit |
| FR-005-14 | Event | When the axisymmetric column-collapse benchmark runs (initial radius R_i = 20 d, aspect ratios a = H_i/R_i ∈ {0.5, 0.75, 1.0, 1.25, 3, 5, 7}, run-out R_∞ = 99th percentile of the particles' radial distance once the kinetic energy is below 10⁻⁶ of the initial potential energy), the DEM and Newton's implicit MPM shall each give a log–log slope of (R_∞ − R_i)/R_i against a of 1.0 ± 0.15 over a ≤ 1.25 and 0.5 ± 0.12 over a ≥ 3, and every value within a factor [0.5, 2.5] of Lube et al. (2004): 1.24 a for a ≲ 1.7 and 1.6 a^{1/2} for a ≳ 1.7. | integration (gpu) |
| FR-005-15 | Ubiquitous | The DEM shall conserve mass exactly: the number of particles inside the domain plus the number recorded as having left through declared outflow boundaries shall equal the initial number at every output step, and the corresponding masses (float64 sums) shall agree to the last bit. | unit (Warp CPU) |

### 3.2 Material point methods
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-005-16 | Ubiquitous | `st50_physics` shall configure Newton's `SolverImplicitMPM` with every material and grid parameter (friction, Young's modulus, yield pressure, viscosity, density, voxel size, grid type, iteration limit, tolerance) set explicitly from the scenario (DC-005-01), never from a library default, and shall record them with the Newton version read from `studio/uv.lock`. | unit (fake solver) |
| FR-005-17 | Ubiquitous | The explicit 2-D (plane-strain) MLS-MPM reference twin in Warp shall use quadratic B-spline APIC transfers and the Drucker–Prager return map of Klár et al. (2016), and its particle-to-grid transfer shall conserve total mass and total linear momentum within rtol 1 × 10⁻⁵ at every step. | unit (Warp CPU) |
| FR-005-18 | Event | When the planar column-collapse benchmark runs on the 2-D twin (symmetric column of half-width L_i, a = H_i/L_i ∈ {0.5, 1.0, 1.5, 4, 6, 8}, run-out per side), it shall give a log–log slope of (L_∞ − L_i)/L_i against a of 1.0 ± 0.15 over a ≤ 1.5 and 2/3 ± 0.12 over a ≥ 4, and every value within a factor [0.5, 2.5] of Lube et al. (2005): 1.2 a for small a and 1.9 a^{2/3} for large a. | integration (Warp CPU, slow; gpu at full resolution) |
| FR-005-19 | Event | When the 3-D silo benchmark runs on Newton's implicit MPM (orifice diameters of 4, 6, 8, 10 and 12 voxels), it shall give flow rates each within ± 5 % of the fit Q = C ρ_b √g D^{5/2} (k = 0, a local rheology) and a free-exponent fit of 2.5 ± 0.15. | integration (gpu) |
| FR-005-20 | Ubiquitous | Both MPM solvers shall conserve particle mass exactly (constant particle count and per-particle mass, float64 total), and every particle leaving the domain shall be counted against a declared outflow boundary. | unit (Warp CPU; gpu for Newton) |
| FR-005-21 | State | While a scenario runs Newton's implicit MPM, `st50_physics` shall declare determinism class `statistical`, and a re-run of one shard shall reproduce run-out within ± 2 %, repose angle within ± 0.5° and discharge within ± 2 %. | integration (gpu) |
| FR-005-22 | Event | When the `parity-goldens` scenario set runs, `st50_physics` shall write, for each browser-twin scenario (DEM pile, 2-D MLS-MPM collapse, shallow-water dam break, dust release), the initial state, seed, parameters and golden observables (repose angle, run-out, Q(t), total-mass drift) in Warp's deterministic mode, pinned by SHA-256 (DC-005-06). | integration (Warp CPU and gpu) |

### 3.3 Shallow water with Bingham bed stress (Warp)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-005-23 | Ubiquitous | The shallow-water solver shall advance U = (h, hu, hv) on the terrain grid by finite volumes with the Rusanov interface flux, hydrostatic reconstruction of the bed at each face (well-balanced and positivity-preserving), and an explicit step dt = C_CFL Δx / max(\|u\| + √(g h)) with declared C_CFL ∈ (0, 0.5] (default 0.45). | unit (Warp CPU) |
| FR-005-24 | Event | When the Ritter dry-bed dam break runs (h_l = 0.005 m, x₀ = 5 m, L = 10 m, t = 6 s, a channel 4 cells wide with reflective walls), the solver shall give a relative L1 depth error ≤ 5 % at 400 cells, an observed L1 convergence order ≥ 0.5 between 400, 800 and 1600 cells, and a wet front (last cell with h > 10⁻³ h_l) within ± 5 % of the analytical travel distance to the point where the Ritter depth equals 10⁻³ h_l. | integration (Warp CPU) |
| FR-005-25 | Event | When the Stoker wet-bed dam break runs (h_l = 0.005 m, h_r = 0.001 m, x₀ = 5 m, L = 10 m, t = 6 s), the solver shall give a relative L1 depth error ≤ 5 % at 400 cells, the middle-state depth h_m within ± 2 % and the bore position within ± 2 % of the analytical travel distance. | integration (Warp CPU) |
| FR-005-26 | Event | When a lake at rest (constant free surface over a benched terrain crop of 128 × 128 cells) runs for 1000 steps, the solver shall keep every velocity magnitude ≤ 1 × 10⁻³ m/s and every depth ≥ 0. | integration (Warp CPU) |
| FR-005-27 | Ubiquitous | The solver shall keep h ≥ 0 in every cell at every step, and its dry threshold h_dry (default 10⁻⁴ m) shall only zero the velocity of cells with h < h_dry, never remove or add water. | unit + property |
| FR-005-28 | Ubiquitous | The solver shall conserve volume: in a closed domain \|V(t) − V₀ − ∫ S_h dA dt\| / V₀ ≤ 1 × 10⁻⁵ over 10⁴ steps, and with open boundaries the volume leaving through them shall be accumulated so that the same balance holds. | unit + property |
| FR-005-29 | Ubiquitous | The solver shall apply the Bingham bed stress τ_b opposite to the velocity, with τ_b from the Buckingham–Reiner relation U = (τ_b h / (3 μ_B)) [1 − (3/2)(τ_y/τ_b) + (1/2)(τ_y/τ_b)³] solved for τ_b ≥ τ_y in every wet cell, applied implicitly so that a cell whose post-flux momentum satisfies \|hu\| ≤ dt τ_y / ρ is set exactly to rest; on a uniform slope S a layer of depth h < h_stop = τ_y / (ρ g S) shall stay exactly at rest away from its edges (> 20 cells), and a layer fed at depth h ≥ 1.5 h_stop shall reach the mean velocity U of the relation with τ_b = ρ g h S within ± 2 % and its depth within ± 2 %. | integration (Warp CPU) |
| FR-005-30 | Ubiquitous | The solver shall reduce h(x, t) to the C2 maps — arrival time t_arr(x) = min{t : h > h_thr}, maximum depth h_max(x), maximum speed v_max(x) — and to the inundated area A = \|{x : h_max > h_thr}\| for a declared h_thr (default 0.05 m), written as Zarr fields (DC-005-02). | unit |
| FR-005-31 | Event | When a breach is prescribed as a triangular hydrograph of volume V and peak Q_p (base T = 2V/Q_p, peak at a declared fraction of T, default 0.5), the solver shall inject a total volume equal to V within rtol 1 × 10⁻⁶ over the breach cells. | unit |
| FR-005-32 | Unwanted | If the terrain or initial depth contains NaN or ±inf, a depth is negative, the depth and terrain grids differ in shape or cell size, C_CFL ∉ (0, 0.5], τ_y < 0, μ_B < 0, ρ ≤ 0, h_thr ≤ 0 or a hydrograph has V ≤ 0 or Q_p ≤ 0, then the solver shall reject the scenario with error class `swe-input-invalid` before any kernel launch. | unit (hostile) |

### 3.4 Lagrangian dust (Warp)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-005-33 | Ubiquitous | The dust model shall move each computational particle by dX = (U(X) − v_s ẑ) dt + √(2K) dW with the Stokes settling velocity v_s = (2/9)(ρ_p − ρ_f) g R² / μ, a counter-based random generator keyed by (stage seed, particle id, step) so that results do not depend on thread order, and U either uniform or trilinearly interpolated from a gridded wind field (DC-005-02). | unit (Warp CPU) |
| FR-005-34 | Event | When particles are released in still air with K = 0, every particle shall fall at v_s within rtol 1 × 10⁻⁵; for R = 5 µm, ρ_p = 2650 kg/m³, ρ_f = 1.2 kg/m³ and μ = 1.8 × 10⁻⁵ Pa·s that is v_s = 8.02 × 10⁻³ m/s. | unit (Warp CPU) |
| FR-005-35 | Event | When 2 × 10⁵ particles diffuse from a point in zero wind with constant K, no settling and no ground, the variance of each horizontal coordinate at time t shall equal 2 K t within ± 2 %. | unit (Warp CPU) |
| FR-005-36 | Event | When a continuous point source of rate Q at height H emits into uniform wind u over flat, reflecting ground with constant K and no settling, the particle model's ground-level concentration in bins at 100–500 m downwind shall be within ± 10 % of the Gaussian plume C = (Q / (2π u σ²)) exp(−y²/(2σ²)) · 2 exp(−H²/(2σ²)) with σ = √(2 K x / u), in every bin whose value exceeds 10 % of the maximum. | integration (Warp CPU, slow) |
| FR-005-37 | Ubiquitous | The dust model shall close its mass budget: emitted = airborne + deposited + exited at every output step, with a relative residual ≤ 1 × 10⁻⁹ (float64 accumulators). | unit (Warp CPU) |
| FR-005-38 | Ubiquitous | The dust model shall deposit a particle when it reaches the terrain surface (bilinear interpolation of the site-local terrain grid, DC-004-03) unless the scenario declares a reflecting ground, and shall record each deposit's position and mass. | unit (Warp CPU) |
| FR-005-39 | Unwanted | If a particle radius is ≤ 0 or gives a particle Reynolds number ρ_f v_s (2R) / μ ≥ 1 (outside the Stokes regime), K < 0, μ ≤ 0, an emission rate is negative or non-finite, or the wind field contains NaN or does not match the declared grid shape, then the dust model shall reject the scenario with error class `dust-input-invalid` naming the field. | unit (hostile) |

### 3.5 Vehicles
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-005-40 | Ubiquitous | The batched reduced-order truck model in Warp shall integrate m dv/dt = F_trac(v) − m g (RR + 100 sin θ)/100 − ½ ρ_a C_D A v² − F_ret(v) along the road-network grade profile (DC-004-06), with F_trac = min(μ_t W_drive, η P / v) uphill and on the level, and the retarder limit F_ret ≤ η_r P_ret / v downhill. | unit (Warp CPU) |
| FR-005-41 | Event | When a truck runs on a constant grade segment long enough to settle (≥ 10 relaxation lengths), the model shall reach the analytical steady speed within ± 0.5 %: v_ss = η P / (m g (RR + 100 sin θ)/100) when power-limited with drag neglected, and otherwise the root of F_trac(v) = resistance found by bisection. | unit (Warp CPU) |
| FR-005-42 | Ubiquitous | The model shall close the energy balance ∫ F_trac v dt − ∫ F_ret v dt = ΔKE + m g Δz + ∫ (rolling + drag) v dt with a relative residual ≤ 1 × 10⁻⁴ (float64 accumulators). | unit (Warp CPU) |
| FR-005-43 | Optional | Where Newton's rigid-body solver is used for a truck body (gpu), a rigid box on a plane inclined at θ with Coulomb friction μ shall stay at rest for tan θ ≤ 0.95 μ and slide with a = g (sin θ − μ cos θ) within ± 2 % for tan θ ≥ 1.05 μ. | integration (gpu) |
| FR-005-44 | Unwanted | If a vehicle has mass ≤ 0, power ≤ 0, η or η_r ∉ (0, 1], μ_t ≤ 0, RR < 0, a grade magnitude above 30 % or a non-finite parameter, then the model shall reject it with error class `vehicle-input-invalid`. | unit (hostile) |

### 3.6 Outputs, determinism and GPU discipline (all solvers)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-005-45 | Ubiquitous | `st50_physics` shall write particle replays as shards of at most 1.0 × 10⁷ bytes, positions quantised to uint16 per axis inside the scene bounding box, each shard listed in a replay manifest (units m, bounding box, fps, frame and particle counts, solver and version, seed, SHA-256 per shard) valid against DC-005-04. | unit |
| FR-005-46 | Ubiquitous | `st50_physics` shall write fields as Zarr (DC-005-02) and observables as Parquet (DC-005-03) with units in the column metadata, including for every run the time step, Δt_R where it applies, the mass or volume budget series and the solver version read from `studio/uv.lock`. | unit + contract |
| FR-005-47 | Ubiquitous | `st50_physics` shall write one benchmark-report row per benchmark (id, solver, version, material card, parameters, measured value, oracle value and source, tolerance, verdict `pass`, `fail` or `not run`, reason) valid against DC-005-05, and shall stamp every rollout output with the report id and the verdict of its solver version; a production scenario (any scenario that is not itself a benchmark) shall take the benchmark report of its solver version and material card as an input, and if that report is absent or any applicable benchmark in it is not `pass`, `st50_physics` shall refuse the scenario with error class `unbenchmarked-solver` before any kernel launch. | unit + contract |
| FR-005-48 | Ubiquitous | Warp reference runs (benchmarks and parity goldens) shall use Warp's deterministic execution mode for atomic operations, declare determinism class `bitwise`, reproduce the SHA-256 of their outputs on a re-run on the same device, and record the run-time overhead factor of the deterministic mode once per Warp solver. | integration (Warp CPU and gpu) |
| FR-005-49 | State | While no CUDA device is available, a `gpu0.hold` file exists or the scenario declares `device: cpu` (its recipe stage declaring `resources.gpu: none`), `st50_physics` shall hide CUDA devices from its process (`CUDA_VISIBLE_DEVICES=-1`) before importing Warp, run only the Warp CPU variants, and mark every GPU-only benchmark `not run (no GPU)` — never `pass`. | unit (fake GPU backend) |
| FR-005-50 | Unwanted | If a CUDA out-of-memory error occurs, then `st50_physics` shall stop with the stage result's `error_class: oom`, a message carrying the attempted particle or cell count and the peak device memory, and no promoted output, leaving the declared fallback (smaller count) to the runner; it shall not retry by itself. | unit (fake GPU backend) |
| FR-005-51 | Unwanted | If a scenario names an unknown solver, benchmark or material card, has a particle or cell count ≤ 0 or above the declared maximum for the profile's VRAM, or a material parameter that is non-finite or out of domain (E ≤ 0, ν ∉ (−1, 0.5), e ∉ (0, 1], μ_s < 0, μ_r < 0, ρ ≤ 0, d ≤ 0), then `st50_physics` shall reject it with error class `physics-params-invalid` within 1 s and before any allocation. | contract (hostile) |
| FR-005-52 | Unwanted | If a non-finite value appears in any particle or cell state (checked at least every 1000 steps and at every output), then `st50_physics` shall abort with error class `nonfinite-state` naming the step and the first offending index, and no output of that run shall be promoted. | unit (hostile) |
| ~~FR-005-53~~ | — | Retired: the stage's own zero-timeout probe of the lock file. | superseded by FR-002-62, FR-002-63 and FR-005-54 (integration 2026-10-07) |
| FR-005-54 | Unwanted | If `st50_physics` is about to create a CUDA context on device N and the runner's held-lock list (`PITSTUDIO_HELD_LOCKS`, FR-002-62) does not contain `gpuN.compute` or is malformed, then it shall refuse through the stage helper's guard `require_lock("compute", N)` (FR-002-63) with `error_class: lock-not-held`, before importing Warp's CUDA runtime or creating any CUDA context. | unit (fake GPU backend) |

## 4. Correctness properties
| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-005-01 | DEM, Froude similarity: scaling every length by λ, every time (and dt) by √λ and Young's modulus by λ, with ρ, ν, e, μ_s, μ_r and g fixed, scales every position by λ and every velocity by √λ. | λ ∈ {0.5, 2, 10}; two-body impacts and a 500-sphere pile (Warp CPU) | two-body: rtol 1 × 10⁻⁴; pile observables (repose, run-out): ± 1 % |
| P-005-02 | DEM, translation invariance: shifting every particle and wall by a vector leaves relative trajectories and observables unchanged. | shifts up to 100 m; two-body and 500-sphere pile | two-body: atol 1 × 10⁻⁵ m relative to the shifted origin; pile: repose ± 0.5°, run-out ± 1 % |
| P-005-03 | DEM, rotation invariance: rotating the scene by 90°, 180° or 270° about the gravity axis maps trajectories and observables accordingly. | two-body and 500-sphere pile | two-body: atol 1 × 10⁻⁶ m; pile: ± 0.5° |
| P-005-04 | DEM, time-step convergence: for observables O, \|O(dt) − O(dt/2)\| ≤ \|O(2dt) − O(dt)\| and \|O(dt) − O(dt/2)\| ≤ 1 % of O. | restitution, rolling acceleration, slot Q; dt from t_c/50 to t_c/400 | as stated |
| P-005-05 | DEM, permutation invariance: permuting the particle array leaves observables unchanged. | 500-sphere pile, 5 random permutations | repose ± 0.5°, Q ± 2 % |
| P-005-06 | DEM, monotonicity: raising μ_s or μ_r never lowers the repose angle; widening the orifice never lowers Q. | paired runs differing in one parameter | repose: ≥ −0.5°; Q: ≥ −2 % |
| P-005-07 | MLS-MPM twin, P2G partition of unity: for any particle configuration, grid mass equals particle mass and grid momentum equals particle momentum. | Hypothesis: 1–2000 particles anywhere inside the grid, random velocities and affine matrices | rtol 1 × 10⁻⁵ (float32) |
| P-005-08 | MLS-MPM twin, mirror symmetry: a symmetric column collapses into a symmetric deposit. | a ∈ {0.5, 2, 6} | \|L_left − L_right\| ≤ 2 % of L_∞ |
| P-005-09 | MLS-MPM twin, time-step convergence: run-out at dt and dt/2 differ by ≤ 2 %. | a ∈ {0.5, 6} | as stated |
| P-005-10 | MLS-MPM twin, monotonicity: raising the Drucker–Prager friction never increases the run-out. | friction angles 20°–40° in 5° steps | ≥ −1 % (non-increasing within noise) |
| P-005-11 | Newton MPM, resolution convergence: halving the voxel size (8× particles) changes run-out by ≤ 5 % and repose by ≤ 1.5°. | a ∈ {0.75, 5} | as stated (gpu) |
| P-005-12 | Newton MPM, symmetry: an axisymmetric column gives a deposit whose run-out varies by ≤ 3 % with azimuth (8 sectors). | a ∈ {0.75, 5} | as stated (gpu) |
| P-005-13 | Newton MPM, monotonicity: raising the friction coefficient never increases the run-out. | 3 friction values | ≥ −1 % (gpu) |
| P-005-14 | Shallow water, mirror symmetry: mirroring the terrain and the initial state in x mirrors h and negates hu at every step. | Hypothesis: random terrains 64², random initial depths | atol 1 × 10⁻⁶ × max h |
| P-005-15 | Shallow water, rotation: rotating terrain and state by 90° rotates the solution. | Hypothesis: random terrains 64² | atol 1 × 10⁻⁶ × max h |
| P-005-16 | Shallow water, Froude scaling: scaling lengths by λ, times by √λ, velocities by √λ, τ_y by λ and μ_B by λ^{3/2} leaves the dimensionless fields h/λ, u/√λ unchanged. | λ ∈ {0.1, 4}; dam break and Bingham slope | rtol 1 × 10⁻⁴ |
| P-005-17 | Shallow water, yield-stress monotonicity: raising τ_y never increases the inundated area or the run-out. | paired breach runs, τ_y ∈ [0, 500] Pa | non-increasing (exact ordering of A, ± 1 cell for run-out) |
| P-005-18 | Shallow water, Newtonian and water limits: with τ_y = 0 and μ_B = 0 the solver equals the frictionless solver bit for bit; with τ_y = 0 the steady sheet flow equals U = ρ g h² S / (3 μ_B). | dam break; inclined channel | exact; ± 2 % |
| P-005-19 | Shallow water, grid convergence: the Ritter and Stoker L1 errors decrease monotonically from 400 to 1600 cells. | both benchmarks | strictly decreasing |
| P-005-20 | Dust, linearity: multiplying every emission rate by k multiplies every concentration and deposit by k. | k ∈ {0.5, 2, 10}; same seed | rtol 1 × 10⁻⁶ |
| P-005-21 | Dust, rotation: rotating the wind direction by 90° rotates the concentration field's centroid and second moments by 90°. | uniform wind, flat ground | centroid ± 1 % of the travel distance; moments ± 3 % |
| P-005-22 | Dust, time-step invariance: under uniform wind, constant K and no ground, the particle-position distribution at a fixed time does not depend on dt. | dt ∈ {0.1, 0.5, 2} s | mean ± 0.5 %, variance ± 2 % |
| P-005-23 | Dust, settling monotonicity: a larger particle radius never increases the mean deposition distance. | R ∈ {1, 2.5, 5, 10, 15} µm, flat absorbing ground | non-increasing within ± 1 % |
| P-005-24 | Vehicles, scaling: multiplying mass, power, retarder power and traction by k leaves the speed profile unchanged. | k ∈ {0.5, 2} | rtol 1 × 10⁻⁶ |
| P-005-25 | Vehicles, monotonicity: a steeper uphill grade never increases the steady speed; a longer ramp never shortens the travel time. | grades 0–15 % | exact ordering |
| P-005-26 | Vehicles, time-step convergence: travel time over a ramp at dt and dt/2 differ by ≤ 0.1 %. | dt ∈ {0.2, 0.1, 0.05} s | as stated |
| P-005-27 | Replay quantisation: for any position inside the bounding box, the dequantised position differs from the original by ≤ extent / 131070 per axis plus one float32 ulp. | Hypothesis: random positions and boxes | as stated |
| P-005-28 | Determinism: a re-run in deterministic mode with the same seed, inputs and device gives byte-identical outputs. | every Warp benchmark scenario (CPU in CI, GPU on the reference machine) | exact |

## 5. Non-functional requirements and success criteria
| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-005-01 | Peak device memory of any `st50_physics` scenario on the 16 GB reference GPU | ≤ 14 GB | NVML telemetry summary (`mem_used_peak_bytes`) |
| NFR-005-02 | Wall time of one production scenario (plan rate 1–2 scenarios per hour) | ≤ 60 min | run manifest `wall_s` |
| NFR-005-03 | CPU-variant test time in the studio CPU job | non-`slow` tests ≤ 5 min; `slow` tests ≤ 60 min | CI job time |
| NFR-005-04 | Throughput recorded for every run | particle-steps/s, cell-steps/s or vehicle-steps/s present in the stage's `throughput` field (reported as spec 006 defines) for 100 % of runs | run manifest |
| NFR-005-05 | Deterministic-mode overhead recorded | an overhead factor present for every Warp solver in the benchmark report | benchmark report |
| SC-005-01 | Benchmark gate before use: every solver (DEM, Newton MPM, MLS-MPM twin, shallow water, dust, vehicles) has a benchmark report on the reference GPU in which every applicable benchmark is `pass` before any of its rollouts feeds GNS or FNO training, the D1 PSDs, a replay or a published number | 100 % of solvers, in the data-and-models phase | benchmark reports linked from the published runs |
| SC-005-02 | DEM vs MPM on the same pile and dump scenarios: differences in run-out and repose reported with values, never as "better"; any comparative claim follows FR-000-05 | 100 % of comparisons | results page check |

## 6. Data contracts
| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-005-01 | Physics scenario parameters (solver, device, benchmark ids, geometry, counts, time step, seed, material cards with values, citations and verification status) | `contracts/physics-scenario.schema.json` (to be written: T-005-001) | recipe `params` → `st50_physics` |
| DC-005-02 | Physics fields (Zarr: grid, CRS record, units, time axis, variables) incl. C2 maps and wind fields | `contracts/physics-field.schema.json` (T-005-001) | `st50_physics` → pipeline (FNO training), export stage |
| DC-005-03 | Physics observables (Parquet columns with units) | `contracts/physics-observables.schema.json` (T-005-001) | `st50_physics` → pipeline (GNS training, evaluation), publication |
| DC-005-04 | Replay manifest and shards | `contracts/replay-shard.schema.json` (T-005-001) | `st50_physics` → publication, web replays |
| DC-005-05 | Physics benchmark report | `contracts/physics-benchmark-report.schema.json` (T-005-001) | `st50_physics` → consumers' gate, web results page |
| DC-005-06 | Parity goldens for the browser twins | `contracts/physics-parity-golden.schema.json` (T-005-001) | `st50_physics` → web twin parity tests |

The terrain grid comes from DC-004-03 and the road network from DC-004-06; run manifests follow DC-000-01.

## 7. Edge cases and assumptions
**Pinned at specification (source read now):**
- Hertz normal force (4/3) E_eff R^{1/2} δ^{3/2}, Mindlin tangential stiffness 8 G_eff a, E_eff = [(1 − ν_i²)/E_i +
  (1 − ν_j²)/E_j]⁻¹ and G_eff = [(2 − ν_i)/G_i + (2 − ν_j)/G_j]⁻¹ with G = E/(2(1 + ν)): LAMMPS `pair_style granular`
  documentation, section "Description" (https://docs.lammps.org/pair_granular.html).
- Lube et al. (2004), axisymmetric: (R_∞ − R₀)/R₀ ≃ 1.24 a for a ≲ 1.7 and 1.6 a^{1/2} for a ≳ 1.7; Lube et al. (2005),
  planar: 1.2 a for a ≲ 2.3 and 1.9 a^{2/3} for a ≳ 2.3. The primary papers are closed access; the values are taken from
  two independent open quotations that agree: Staron & Hinch, arXiv physics/0501022, section III, p. 3, and Szewc, arXiv
  1602.07881, equations (22) and (24), p. 11. A third source (Dunatunga & Kamrin, arXiv 1411.5447, table on p. 11)
  quotes the planar regime bounds as a < 1.8 and a > 2.8; the fitting bands of FR-005-18 (a ≤ 1.5, a ≥ 4) satisfy all
  three statements. Lajeunesse et al. (2004) report 1.0 a (a ≲ 0.74) and 2.0 a^{1/2} (same p. 3); they are reported,
  not gated.
- Beverloo DEM validation (arXiv 2512.03698, section 4 and Fig. 4 caption): exponent fixed at 2.5, fitted C = 0.56,
  N = 4 × 10⁵ spheres, D/d ∈ {5, 8, 10, 12.5, 15, 17.5, 20}; k is not stated there.
- Plane-strain Beverloo form Q = C ρ √g (D − k d)^{3/2}: Dunatunga & Kamrin, arXiv 1411.5447, equation (4.4), p. 12;
  their local-rheology MPM gives k = 0 and a free exponent of 1.47 (p. 13).
- Ritter and Stoker solutions: SWASHES compilation (Delestre et al., arXiv 1110.0288, sections 4.1.1–4.1.2, pp. 22–24;
  Int. J. Numer. Methods Fluids 72(3), 2013, DOI 10.1002/fld.3741), which cites Stoker (1957, pp. 333–341) and Ritter
  (1892). Stoker's middle state c_m = √(g h_m) solves −8 g h_r c_m² (√(g h_l) − c_m)² + (c_m² − g h_r)² (c_m² + g h_r) = 0;
  the bore is at x_C = x₀ + t · 2 c_m² (√(g h_l) − c_m) / (c_m² − g h_r); Ritter's fan is h = (4/(9g)) (√(g h_l) −
  (x − x₀)/(2t))² between x₀ − t√(g h_l) and x₀ + 2t√(g h_l).
- Buckingham–Reiner relation: pinned by derivation. For a Bingham layer of depth h on bed slope S, τ(z) = ρ g S (h − z),
  the plug starts at z_p = h − τ_y/(ρ g S), u(z) = (ρ g S/μ_B)(z_p z − z²/2) below it, and the mean velocity is
  U = (τ_b h/(3 μ_B)) [1 − (3/2) ξ + (1/2) ξ³] with τ_b = ρ g h S and ξ = τ_y/τ_b. Example: ρ = 1800 kg/m³, S = 0.0875,
  τ_y = 100 Pa, μ_B = 10 Pa·s, h = 0.2 m → τ_b = 309.0 Pa, ξ = 0.3236, U = 1.095 m/s; h_stop = 0.0647 m.
- Contact duration constant: t_c = 2 (δ_max/v₀) ∫₀¹ (1 − x^{5/2})^{−1/2} dx = 2.9433 δ_max/v₀ (energy integral of the
  undamped Hertz contact; the test evaluates the integral by quadrature).
- Warp runs kernels on its `"cpu"` device, serially ("Currently, kernels launched on CPU devices will be executed in
  serial", Warp runtime documentation); `HashGrid` works on the CPU device.
- Newton's `SolverImplicitMPM` documentation states no CPU support and no determinism guarantee; its MPM tests are
  GPU-only and its determinism class is `statistical`.

**UNVERIFIED (kept out of every oracle):**
- The Rayleigh time-step constants 0.1631 and 0.8766: used only by the guard of FR-005-08; stability itself is tested by
  the time-step relations P-005-04, P-005-09.
- The LIGGGHTS damping form (2√(5/6) β): its realised restitution is checked against an independent SciPy integration
  of the same contact law and against the nominal e (FR-005-03); the literature mapping is not used as an oracle.
- The elastic–plastic rolling-resistance model of Ai et al. (2011) in detail: FR-005-04 uses only the torque cap, which
  every such model shares.
- Textbook Beverloo ranges C ≈ 0.55–0.65 and k ≈ 1.4–1.5: C is reported, k is fitted (k ≥ 0), neither is gated.
- Handbook repose angles (Glover, *Pocket Ref*, via a secondary table): material cards may use them as targets only with
  their verification status shown in the report.
- Martin & Moyce (1952) front data and SPHERIC Test 2 measurements: not extracted; not gated.
- Larrauri & Lall (2018) run-out regression coefficients: not used.
- The mapping from Newton's `mpm:friction` to an angle of repose: calibrated in spec 011, not assumed here.

**Other assumptions and limits:**
- Spheres with rolling resistance approximate angular rock; MPM approximates a pile as a continuum; depth-averaged flow
  has no vertical structure and no erosion; dust settles in the Stokes regime only (FR-005-39 rejects coarser particles)
  in a uniform or supplied wind field, with no terrain-induced flow model.
- The depth-averaged solver uses the bed gradient S = \|∇z_b\| (small-slope form); on a 5° slope S = tan θ differs from
  sin θ by 0.4 %.
- Run-out in the collapse benchmarks is the 99th percentile of particle distances, which is robust to isolated
  bouncing particles.
- Results are simulation-grade and educational, not equipment-design or regulatory software.

## 8. Clarifications log
- Resolved: the docs list the column-collapse law only in its axisymmetric form; the 2-D MLS-MPM twin is plane strain,
  so FR-005-18 uses the planar law (Lube et al. 2005, exponent 2/3). Not a contradiction; the axisymmetric law stays for
  the 3-D DEM and Newton MPM (FR-005-14).
- Resolved: "Beverloo ± 5 %" is read as each measured flow rate within ± 5 % of the law fitted to the solver's own runs
  with the exponent 5/2 (the published DEM practice), plus a free-exponent check; C is reported, not gated, because it
  depends on friction and packing.
- Resolved: the repose benchmark target comes from the material card (with its citation and status); calibrating
  parameters to reach it is spec 011's DEM calibration.
- Resolved: the explicit MLS-MPM reference twin is 2-D (plane strain), matching the 2-D GNS surrogate of the plan.
- Resolved: Bingham closure: the Buckingham–Reiner relation solved per cell, applied implicitly, with exact arrest when
  \|hu\| ≤ dt τ_y/ρ (since τ_b → τ_y as U → 0); the first-order approximation τ_b ≈ (3/2) τ_y + 3 μ_B U/h is not used.
- Resolved: "vehicles" in `st50_physics` are a batched reduced-order longitudinal model in Warp (validated analytically)
  plus an optional Newton rigid-body check; articulated machines for Isaac Lab are spec 014.
- Resolved: the CPU path runs with CUDA hidden (FR-005-49) so that CI and runs under a GPU hold never create a CUDA
  context.
- Resolved (alignment with spec 002; superseded by the integration entry below): the runner takes `gpu0.compute` for
  stages declared `resources.gpu: exclusive`; error classes travel as message prefixes because the stage result's
  `error_class` enum is closed.
- Resolved: "a solver must pass its benchmarks before its rollouts are used" is enforced at the producer: production
  scenarios take their solver's benchmark report as an input and are refused without a passing one (FR-005-47), since
  publication (spec 002) does not know about benchmarks.
- Resolved: the browser-twin parity tolerances proposed in the docs (repose ± 1.5°, run-out ± 5 %, discharge ± 5 %, mass
  drift < 0.5 %) are enforced by the web spec against the goldens of FR-005-22.
- Integration 2026-10-07: spec 002 now exports the locks it holds to each stage (`PITSTUDIO_HELD_LOCKS`, FR-002-62)
  and its stage helper refuses GPU work whose lock is not listed (FR-002-63, `error_class: lock-not-held`). The
  stage-side probe of the lock file (FR-005-53) is struck and replaced by FR-005-54, which uses that list; a direct
  launch outside the runner has no list and is refused. `lock-not-held` is now the stage result's own error class,
  not a message prefix. Task T-005-064 carries FR-005-54.
- Integration 2026-10-07: every `thresholds.yaml` key this spec proposes is marked "proposed key, pending maintainer
  approval" and compiled with the other specs' proposals for the maintainer; lane-gate keys are consolidated as
  `lane_gate.*` and budget keys as `budgets.*`.

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
(none — new feature)
### MODIFIED Requirements
(none)
### REMOVED Requirements
(none)
