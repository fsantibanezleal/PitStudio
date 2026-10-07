# Spec 007 — Haulage and dispatch (M1–M6)
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Cases A1 (truck–shovel dispatch and fleet sizing) and A2 (haul-road energy and electrification) need one haulage
engine that is exact enough to be the judge of every dispatcher, fast enough to run live in a browser, and honest about
being calibrated synthetic. This spec turns methods M1–M6 into testable requirements for PitStudio's own code:

- **M1** — fleet sizing with the match factor and finite-source queueing / MVA. The models live in `minephys.haulage`.
  PitStudio specifies how it uses them: a TypeScript port for the live panel, and the DES-versus-MVA oracle.
- **M2** — a seeded discrete-event simulation (DES) with classical dispatchers:
  - the `minehaulsim` package (Apache-2.0, 0.12.1, locked in `pipeline/`) is the Python reference engine, run through
    a PitStudio adapter that supplies a counter-based variate source;
  - a TypeScript twin reproduces its event trace exactly;
  - an independent SimPy model is the oracle on small scenarios.
- **M3** — two-stage LP dispatch: HiGHS in the pipeline, a small TypeScript simplex in the browser.
- **M4** — PPO dispatch trained in a GPU-vectorised PyTorch environment.
- **M5** — a size-invariant attention fleet policy, judged by the same paired-seed rule.
- **M6** — route energy, fuel and CO₂ per tonne for diesel, trolley-assist and battery-electric trucks (physics from
  `minephys.haulage`), plus grade-constrained least-energy A* routing on the DEM.

Who benefits:
- mining engineers, who get live, reproducible dispatch and energy trade-offs;
- data/AI practitioners, who get a learned-versus-classical comparison that follows the pre-registered decision rule
  (FR-000-05);
- developers, who get a bit-exact Python ↔ TypeScript DES.

**Out of scope:**
- the `minephys` models themselves (specified in the `minephys` repository);
- the web routes, workers, compute tiers and UI controls that host these engines (spec 018-web-cases);
- ONNX/TensorRT export mechanics beyond the dispatch-specific checks (spec 016-export-acceleration);
- terrain extraction from lidar (spec 004-scene-pipeline);
- any claim about a real fleet: no haul telemetry exists, so every haulage output is "calibrated synthetic — not
  validated against real data".

## 2. User stories

| ID | Priority | Story (short) |
|---|---|---|
| US-007-1 | P1 | Live shift with any dispatcher and fleet size, identical to the reference engine |
| US-007-2 | P1 | Learned versus classical dispatch on paired seeds with the decision rule |
| US-007-3 | P1 | Energy, fuel and CO₂ per tonne by drivetrain on a grade-constrained route over real terrain |
| US-007-4 | P2 | Analytical fleet sizing next to the DES, with the gap explained |
| US-007-5 | P2 | Bit-exact Python ↔ TypeScript DES with goldens |

### US-007-1 (P1) Live shift, identical to the reference
As a mining engineer, I want to pick a dispatcher and a fleet size, run a shift in the browser and read t/h, queue
time, match factor, shovel utilisation and truck- and shovel-hours per kilotonne (cost per tonne from my own rates), so
that I can compare dispatch rules on a real pit road network. Independent test: a golden scenario run in the TypeScript
twin gives the same event trace and KPIs, bit for bit, as the Python reference.

### US-007-2 (P1) Learned versus classical dispatch, decided by paired seeds
As a data/AI practitioner, I want the PPO and attention policies compared with SPTF and LP dispatch in the reference
engine on at least 30 paired seeds, with a paired 95 % confidence interval and a pre-registered verdict, so that I can
trust or reject the "learned is better" claim. Independent test: the evaluation table of a fixed seed set reproduces
the verdict from its own per-seed numbers by hand calculation.

### US-007-3 (P1) Energy and routing by drivetrain
As a planner or decarbonisation lead, I want kWh/t, L/(t·km) and kg CO₂e/t for diesel, trolley-assist and
battery-electric trucks on a grade-constrained least-energy route over the real terrain, so that I can compare ramp
designs and drive systems. Independent test: on a straight synthetic ramp the energy equals the hand-calculated worked
example, and the A* route cost equals a Dijkstra oracle.

### US-007-4 (P2) Analytical fleet sizing next to the DES
As a student, I want the match factor, M/M/1//N and MVA results next to the DES for the same fleet, so that I can see
what randomness costs. Independent test: under the exponential profile the DES throughput matches exact MVA within the
stated tolerance.

### US-007-5 (P2) Reproducible engine for developers
As a developer, I want a documented scenario bundle, a counter-based variate source and golden traces, so that I can
extend dispatchers in Python and TypeScript without breaking parity. Independent test: the golden suite passes in both
languages from a clean checkout.

## 3. Functional requirements (EARS)

All Python modules named below live in the `pipeline/` environment (package `pitstudio_pipeline`), unless they are
marked as root-core (package `pitstudio`, root environment). TypeScript engines live under `web/src/engines/`.

**Reference engine and scenarios (M2)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-007-01 | Ubiquitous | The haulage adapter (`pitstudio_pipeline.haulage`) shall run one shift of the `minehaulsim` reference engine, at the version locked in `pipeline/uv.lock` (0.12.1). Its inputs are a scenario bundle valid against `contracts/haul-scenario.schema.json`, a seed (integer, 0 ≤ seed < 2⁶³), a dispatcher id and a variate profile. Throughout the run it shall replace the engine's random-stream manager with the counter-based variate source of FR-007-05 to FR-007-07. It shall return the event trace (FR-007-09), the cyclelog rows, the engine's executed-event count and the KPIs of FR-007-08. | integration |
| FR-007-02 | Unwanted | If the installed `minehaulsim` version, or the SHA-256 of any engine module the adapter's seam depends on, differs from the adapter's engine pin file, then the adapter shall refuse to run with `EngineVersionMismatch` naming every differing item, and shall write no trace. The modules are `des/sim.py`, `des/engine.py`, `des/dispatch.py`, `des/failures.py`, `des/traversal.py`, `des/resources.py`, `network/kinematics.py`, `network/routing.py`, `network/graph.py` and `equipment/catalog.py`. | unit (hostile) |
| FR-007-03 | Unwanted | If a scenario bundle has a hostile input, then the adapter and the TypeScript twin shall reject it before simulating, with `InvalidScenario` listing every violation (JSON path, value, rule), and shall never clip, default or coerce a value. Hostile inputs are: a schema violation; a NaN or infinite number; a count ≤ 0 where a positive count is required (trucks, loaders, dumps, loader spots); a fleet of more than 40 trucks in a bundle marked `live`, or more than 400 otherwise; a segment length ≤ 0 m; a \|grade\| ≥ 100 %; a rolling resistance < 0 %; a speed limit ≤ 0 km/h; an unknown dispatcher, variate profile, truck class or loader class; a duplicate node, segment or truck id. | unit (hostile) |
| FR-007-04 | Unwanted | If, on the frozen network without closures, some loader cannot be reached from some dump, or some dump from some loader, for a truck class in the fleet (disconnected graph, width class or one-way constraints), then the adapter and the twin shall reject the scenario with `DisconnectedNetwork` naming every unreachable (origin, destination, truck class) triple. They shall do so within 1 s for networks of ≤ 10⁴ segments. | unit (hostile) |
| FR-007-05 | Ubiquitous | The variate source (`pitstudio_pipeline.haulage.variates`; TypeScript `web/src/engines/random/`) shall draw every random number from Philox4x64-10 as defined by Random123. The key is (seed, FNV-1a-64 of the UTF-8 stream purpose name). The counter is (block index, 0, 0, 0), starting at block 0 for each stream. The four 64-bit words of each block are consumed in order. The generator shall be identical in Python and TypeScript. | unit + parity |
| FR-007-06 | Ubiquitous | The variate source shall produce variates only from integer operations, the IEEE-754 basic operations (+, −, ×, ÷) and linear interpolation in quantile tables carried in the scenario bundle. This covers uniform(lo, hi), normal(loc, scale), unit-mean lognormal(−σ²/2, σ), exponential(scale) and bounded integers. The TypeScript variate and DES modules shall contain no call to a transcendental function: `Math.exp`, `Math.log`, `Math.log1p`, `Math.log2`, `Math.log10`, `Math.expm1`, `Math.pow`, `Math.sin`, `Math.cos`, `Math.tan`, `Math.asin`, `Math.acos`, `Math.atan`, `Math.atan2`, `Math.sinh`, `Math.cosh`, `Math.tanh`, `Math.cbrt`, `Math.hypot`. They shall also contain no `**` with a non-integer exponent. | unit + static check |
| FR-007-07 | State | While the variate profile is `exponential`, the variate source shall answer the `loadtime` and `dumptime` unit-mean lognormal requests with unit-mean exponential variates, answer `payload` requests with their mean, and leave the other streams as in `engine`. While the profile is `deterministic`, it shall answer every request with the distribution mean: uniform → midpoint, normal → loc, unit-mean lognormal → 1, exponential → scale; bounded integers return their lower bound. In both cases it shall record the profile in the trace header. | unit |
| FR-007-08 | Ubiquitous | The KPI layer (`pitstudio_pipeline.haulage.kpi`) shall compute from a trace, per loader and for the fleet, over the evaluation window [warm-up, horizon] declared in the bundle: production (t/h); cycles per hour; queue time at loaders and dumps (mean and P90, min per cycle); loader utilisation (busy fraction); match factor; truck-hours and loader-hours per kilotonne. The match factor comes from `minephys.haulage`, with t_L the mean loading time and T_c\* the free-flow cycle time; the heterogeneous form is used when the fleet mixes classes. Cost per tonne shall be computed only when truck and loader hourly rates are supplied, and shall otherwise be reported as `not-computed (rates not supplied)`. | unit |
| FR-007-42 | Unwanted | If a trace given to the KPI layer fails its schema, is not strictly ordered by (t, seq), contains a non-finite time or payload, or its evaluation window has warm-up ≥ horizon, then the KPI layer (Python and TypeScript) shall reject it with `InvalidTrace` naming the first offending row, and shall return no KPI. | unit (hostile) |
| FR-007-09 | Ubiquitous | The event trace shall list every executed engine event in execution order as (t, seq, kind, truck, node). The kind comes from the canonical vocabulary of `contracts/des-trace.schema.json`, mapped from the engine's callbacks by the pinned name map. Cancelled events are not executed and do not appear, but they consume a seq. The cyclelog rows (t, truck, node, event ∈ {load, haul, dump, return}, payload) shall be sorted stably by (t, truck), as the reference engine sorts them. | unit |
| FR-007-10 | Ubiquitous | For every golden scenario, the TypeScript DES twin (`web/src/engines/des/`) shall emit an event trace and cyclelog identical to the Python reference: the same number of events; for every event, the same t (float64 bit pattern), seq, kind, truck and node; the same cyclelog rows, including payload bit patterns; the same executed-event count; and the same scalar results (tonnes, cycles, truck wait, per-loader wait, downtime) bit for bit. | parity |
| FR-007-11 | Ubiquitous | The golden set shall cover each of the six classical dispatchers in fast and traffic mode, with and without failures (24 scenarios), plus: the LP dispatcher in both modes; one scenario with one-way ramps, a direction zone and a junction; one scenario whose segments share a speed-solver cache key (grades that round to the same 0.01 %); and one scenario per non-`engine` variate profile. Every golden scenario shall have ≥ 2 loaders and ≥ 2 dumps where the dispatcher can choose, and ≥ 4 goldens shall run a full 8 h shift. | unit (coverage check) |
| FR-007-12 | Unwanted | If a scenario uses a reference-engine feature outside the twin's declared feature set, then the twin shall refuse with `UnsupportedFeature` naming the feature, and the web shall fall back to the baked trace with that reason. The features outside the set are: underground units (LHDs), ore passes, shaft bins, a planning overlay and a routing zone penalty ≠ 0. | unit (hostile) |
| FR-007-13 | Unwanted | If the adapter or the twin receives a seed that is not an integer in [0, 2⁶³), or a horizon ≤ 0 s or > 7 days, or a run passes 2 × 10⁶ executed events, then it shall stop within 2 s with `InvalidSeed`, `InvalidHorizon` or `EventBudgetExceeded`, and shall return no partial KPIs. | unit (hostile) |
| FR-007-14 | Ubiquitous | The classical dispatcher set shall be `fixed`, `nearest`, `sptf`, `sq`, `random` and `min-idle`. The first five delegate to the reference engine's policies: FixedPolicy, NearestPolicy, MinSaturationPolicy (earliest expected start of loading, max(ETA, backlog)), MinQueuePolicy (fewest queued + inbound, then ETA) and RandomPolicy (shown for context only). `min-idle` is PitStudio's own: the serviceable loader with the smallest backlog, where backlog = time until free + (queued + inbound) × mean loading time, with ties broken by ETA. Every dispatcher shall break the remaining ties by the lowest node id. Every dispatcher, including LP and learned ones, shall send a loaded truck to its loader's declared destination dump, or to the first dump when none is declared. | unit |

**Analytical fleet sizing (M1)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-007-15 | Ubiquitous | The fleet-sizing engine shall compute the match factor, M/M/1//N (π₀, U, X), open M/M/c (C, W_q, L_q) and exact MVA by calling `minephys.haulage` in Python and its TypeScript port (`web/src/engines/haulage/`) in the browser. The port shall equal `minephys.haulage` on the committed golden vectors within rtol 1e-12, atol 1e-15. | parity |
| FR-007-16 | Unwanted | If a fleet-sizing input is non-finite, N_T or N_L is not a positive integer, a rate or time is ≤ 0, or N_T > 400, then the port shall return `InvalidInput` naming the field. If ρ ≥ 1 for open M/M/c, it shall return `Unstable`. It shall never return NaN or Infinity. | unit (hostile) |
| FR-007-17 | Event | When the adapter runs the exponential oracle family, the DES fleet throughput (cycles/h), averaged over 30 seeds × 100 h with the first 2 h discarded, shall lie within max(3 standard errors, 1 %) of exact MVA. The family is: one loader, one dump, one two-way route, fast mode, `fixed` dispatcher, `exponential` profile, N_T = 1 … 12. MVA treats the loader and the dump as FCFS stations and the haul and return legs as one delay station whose time is hand-calculated from the segment lengths and speed limits. | integration (analytical oracle) |
| FR-007-18 | Ubiquitous | The A1 evaluation shall report the DES-versus-MVA throughput gap per N_T under the `engine` profile and traffic mode as a result (how far product-form assumptions misjudge this pit), never as a pass/fail check. | integration |

**Two-stage LP dispatch (M3)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-007-19 | Ubiquitous | The LP upper stage shall maximise Σ m·f_p over the declared loader → destination paths p. The constraints are loader capacity Σ f ≤ μ_s, dump capacity Σ f ≤ κ_d, the fleet constraint Σ f_p·T_p ≤ N_T (Little's law, with T_p the queue-free round trip) and the optional blend floors. It shall solve with HiGHS (`highspy`) in the pipeline and with the TypeScript simplex (`web/src/engines/lp/`) in the browser, and return the status, the optimum, f_p and the dual value of every constraint. | unit |
| FR-007-20 | Event | When the LP status is optimal, the TypeScript simplex shall equal HiGHS on every golden instance: optimum within rtol 1e-7; on non-degenerate instances, f_p and the dual values within atol 1e-6. | parity |
| FR-007-21 | Unwanted | If the LP is infeasible or unbounded, or has a non-finite coefficient, a negative capacity, T_p ≤ 0 or no path, then both solvers shall return the typed status `infeasible`, `unbounded` or `invalid-input` within 1 s. The LP dispatcher shall then fall back to `sptf` and record the status and the fallback in the trace header. | unit (hostile) |
| FR-007-22 | Event | When a truck becomes free, the LP dispatcher shall assign it to the feasible path with the largest need, need_p = f_p·(t − t₀) − loads_sent_p. Ties go to the lowest expected arrival time, then the lowest path id. It shall re-solve the LP only when a loader or a truck changes availability, never at every event. | unit |

**Learned dispatch (M4, M5)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-007-23 | Ubiquitous | The vectorised environment (`pitstudio_pipeline.dispatch.env`) shall simulate B ≥ 1 independent copies of a scenario's haul cycle as PyTorch tensors on CPU or CUDA. Fleets are padded to 40 trucks with a mask. The environment is event-stepped with a decision tick Δt ≤ 10 s and uses the bundle's free-flow leg times, mean service times and variate-profile families. The reward of decision k shall be the fleet's tonnes dumped in (t_k, t_{k+1}] divided by 1,000, with no other shaping. | unit |
| FR-007-43 | Unwanted | If the vectorised environment is built with B < 1, a bundle with more than 40 trucks or 16 targets, Δt ≤ 0 s or Δt > 10 s, or a non-finite or negative leg or service time, then it shall raise `InvalidEnvConfig` before allocating any tensor. | unit (hostile) |
| FR-007-24 | Ubiquitous | Both the environment and the policies shall mask every target that is not serviceable or not reachable for the deciding truck, and the policies shall give masked targets a probability of exactly 0. | unit + property |
| FR-007-25 | Ubiquitous | Advantages shall use time-delta-aware GAE: δ_k = r_k + γ^{Δt_k}·V(s_{k+1}) − V(s_k), and Â_k = Σ_{l≥0} (Π_{j<l} (γλ)^{Δt_{k+j}})·δ_{k+l}, with Δt in ticks and the sum truncated at the episode end. | unit |
| FR-007-26 | Optional | Where a CUDA device passes the runner's guards, `s30_train` shall train M4 (parameter-shared MLP) and M5 (dense attention) with PPO under the `gpu0.compute` lock, checkpoint after every iteration block, and resume a stopped run from its last checkpoint. On the CPU device with the fake GPU backend, a resumed run shall be bitwise identical to an uninterrupted run. | integration (gpu) + unit (fake GPU) |
| FR-007-27 | Unwanted | If training raises CUDA out-of-memory, then `s30_train` shall apply the recipe's declared fallback (halve B, at most twice) and record each fallback in the manifest. A third out-of-memory error shall stop the stage with the log tail. | unit (fake GPU) |
| FR-007-28 | Unwanted | If a training or validation seed is in the pre-registered test-seed set, then `s30_train` and `s50_evaluate` shall refuse to start with `SeedLeak`. Test seeds are derived as the first 8 bytes of SHA-256("pitstudio/a1/test/" + i), shifted right by one bit, for i = 0 … n − 1 with n ≥ 30. They are committed in the evaluation recipe before any training run. | unit (hostile) |
| FR-007-29 | Event | When `s50_evaluate` runs the dispatch comparison, it shall run `fixed`, `nearest`, `sptf`, `sq`, LP, PPO and attention in the reference engine (traffic mode, `engine` profile) on the same test seeds. It shall record, per seed and dispatcher, t/h, mean queue time, loader utilisation, match factor and truck- and loader-hours per kt, in a table valid against `contracts/dispatch-eval.schema.json`. For every learned-versus-baseline pair it shall add the paired differences, the paired-t 95 % CI and the FR-000-05 verdict. | integration |
| FR-007-30 | Unwanted | If fewer than 30 paired seeds exist, the two arms' seed sets differ, or a paired difference is non-finite, then the verdict shall be `insufficient-evidence`, and no output shall say "better". | unit (hostile) |
| FR-007-31 | Ubiquitous | An exported policy shall take the input layout of `contracts/dispatch-policy-io.schema.json` and return one logit per target slot. The layout is: truck features [1, 40, 12], target features [1, 16, 9], truck mask [1, 40] and target mask [1, 16]. The DES, in Python and TypeScript, shall apply the mask and the argmax, with ties going to the lowest target index. | contract |
| FR-007-32 | Event | When the twin runs a golden policy shift with ONNX Runtime Web (WASM), its trace shall equal the Python reference (ONNX Runtime CPU) up to the first decision whose top-2 logit margin in the reference is ≤ 2 × 10⁻⁴. ≥ 99.5 % of golden policy shifts shall be identical end to end. | parity (web) |
| FR-007-33 | Unwanted | If every target of a decision is masked, then the learned and LP dispatchers shall raise `NoServiceableLoader`, and the engine shall park the truck exactly as it does for the classical dispatchers. | unit (hostile) |
| FR-007-44 | Unwanted | If a policy's input tensors have a shape, dtype or layout version other than DC-007-04, or contain a non-finite feature, or the ONNX file's SHA-256 differs from its manifest, then the policy dispatcher (Python and TypeScript) shall stop the run with `InvalidPolicyInput` or `PolicyPinMismatch`, and shall return no partial KPIs. | unit (hostile) |

**Route energy and grade-constrained routing (M6)**

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-007-34 | Ubiquitous | The route-energy engine (root-core `pitstudio.haulage.energy`; TypeScript `web/src/engines/haulage/`) shall compute, through `minephys.haulage`, the wheel and source energy of every leg and the regenerated energy on trolley and battery-electric descents. Its inputs are an ordered route of segments (length m, signed grade %, rolling resistance %, trolley flag), a truck (empty mass t, payload t, drivetrain ∈ {diesel, trolley, bev}) and the leg (loaded or empty). It shall report kWh/t, L/(t·km) for diesel and kg CO₂e/t, each stating its basis (payload tonnes, along-road kilometres). | unit |
| FR-007-45 | Unwanted | If the route-energy engine or the network builder receives a non-finite length, grade or mass, a length ≤ 0 m, a payload ≤ 0 t (per-tonne results are undefined), an unknown drivetrain, a duplicate or out-of-grid declared cell, or a Douglas–Peucker tolerance ≤ 0, then it shall reject the input with `InvalidRouteInput` naming the field and value, and shall never return NaN or Infinity. | unit (hostile) |
| FR-007-35 | Ubiquitous | The router (root-core `pitstudio.haulage.routing`; TypeScript `web/src/engines/routing/`) shall return the least-energy feasible 8-neighbour path between two DEM cells. An edge is feasible only if \|Δz\|/L ≤ g_max. The edge cost is c(e) = (m·g/η)·max(0, RR/100·L + Δz), and the search uses the admissible heuristic h(n) = (m·g/η)·max(0, RR/100·d_xy + z_goal − z_n). Ties are broken by (f, g, cell index). | unit + property |
| FR-007-36 | Unwanted | If a DEM has a NaN or infinite cell outside its declared nodata mask, a cell size ≤ 0 or non-finite, or more than 4096 × 4096 cells (pipeline) or 1024 × 1024 cells (browser), or if g_max is non-finite, ≤ 0 or > 1, or the start or goal is outside the grid or on a nodata cell, then the router shall reject the request with `InvalidDEM` or `InvalidRouteRequest`. The error names the first offending cell or field and the number of offending cells. | unit (hostile) |
| FR-007-37 | Event | When no feasible path exists under the grade limit, the router shall return `NoFeasibleRoute` (a value, not an exception) after expanding each feasible cell at most once. | unit |
| FR-007-38 | Ubiquitous | The network builder (root-core `pitstudio.haulage.network`) shall turn A* routes between the scenario's declared loader, dump and junction cells into the bundle's road network. It simplifies each route with Douglas–Peucker (tolerance ε from the recipe), splits it into segments of constant grade, and refines any segment whose \|grade\| exceeds g_max until none does. Every emitted segment shall satisfy \|grade\| ≤ g_max, and its endpoint elevations shall equal the bilinear DEM sample within 0.01 m. | unit + property |
| FR-007-39 | Ubiquitous | The TypeScript ports of the router and the route-energy engine shall equal the Python implementations on the golden vectors: the identical cell sequence, and costs and energies within rtol 1e-12. | parity |
| FR-007-40 | Ubiquitous | Every physical constant and default used by M1, M6 and the KPI layer shall come from the `minephys` knowledge tables, never from a literal in PitStudio code. This covers g, the diesel CO₂ factor, efficiencies, rolling-resistance defaults and the g_max default. Every result shall list the ids of the UNVERIFIED rows it used. | unit + contract |
| FR-007-41 | Ubiquitous | Every A1 and A2 artefact (trace, KPI table, evaluation table, energy table) shall carry the label "calibrated synthetic — not validated against real data" and the known DES cycle-time bias note, and shall make no C2ST or TSTR claim (FR-000-09). | contract |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-007-01 | The Philox4x64-10 block for counter 0 and key 0 is `16554d9eca36314c db20fe9d672d0fdc d7e772cee186176b 7e68b68aec7ba23b`. The block for a counter and key whose every word is 2⁶⁴−1 is `87b092c3013fe90b 438c3c67be8d0224 9cc7d7c69cd777b6 a09caebf594f0ba0` (Random123 known-answer vectors). For any key and counter, the block equals `numpy.random.Philox` with the counter offset by −1 (numpy increments before each block). FNV-1a-64("") = `cbf29ce484222325`, ("a") = `af63dc4c8601ec8c`, ("foobar") = `85944171f73967e8`. | 3 KAT vectors; 10⁴ random (key, counter) pairs (Hypothesis) | exact |
| P-007-02 | Metamorphic, variate source: (i) the n-th draw of stream A is the same whether or not stream B was drawn (stream independence); (ii) jumping to block k equals k sequential blocks (counter addressability); (iii) for the same counter, normal(loc, 2^j) − loc = 2^j·normal(0, 1) and uniform(lo, lo + 2^j) − lo = 2^j·uniform(0, 1) (affine exactness for power-of-two scales). | seeds in [0, 2⁶³), purposes from the engine set, j ∈ [−8, 8] | exact |
| P-007-03 | For every quantile table: the mean of the table-defined distribution, computed exactly from the knots, equals the target mean (rtol 1e-12); its variance equals the target variance (rtol 1e-2); its Kolmogorov–Smirnov distance to the target CDF is ≤ 2⁻¹¹. For 10⁵ draws on fixed seeds, the empirical KS statistic is ≤ 0.007. | uniform, normal, unit-mean lognormal (σ ∈ [0.05, 1]), exponential | as stated |
| P-007-04 | For any seed and purpose, the first 10⁴ variates of every family are equal in Python and TypeScript. | seeds in [0, 2⁶³) (Hypothesis → JSON fixtures) | bit pattern |
| P-007-05 | The same (bundle, seed, dispatcher, profile) gives byte-identical trace files in two separate processes (Python) and two separate workers (TypeScript). | every golden scenario | exact |
| P-007-06 | Metamorphic, both engines: a strictly increasing relabelling of truck ids gives the identical trace with the ids mapped. For a homogeneous fleet with one shared start loader, any permutation of truck ids leaves the fleet KPIs unchanged. | random relabellings of golden scenarios | exact |
| P-007-07 | Metamorphic, both engines, fast mode without direction zones: reversing the stored orientation of a two-way segment (swap a and b, negate the grade, reverse the polyline) leaves the trace unchanged. | random two-way segments of golden scenarios | exact |
| P-007-08 | Metamorphic, twin and vectorised environment: multiplying every length, headway distance and duration by 2 (segment lengths, headways, pass, spot and dump times, stagger window, failure times, closure windows, retry intervals, horizon) and dividing accelerations by 2 doubles every event time exactly. Event order and seq stay the same, tonnes stay identical, and t/h halves. | golden scenarios | exact (power-of-two scaling) |
| P-007-09 | Under the `deterministic` profile, fast mode, `fixed` dispatcher and a single route: (a) adding one truck never decreases the tonnes dumped by any time t ≤ horizon; (b) the fleet cycle rate over [W, H] equals min(N_T/T_c\*, μ_L, μ_D) within N_T/(H − W). T_c\*, μ_L and μ_D are hand-calculated from the bundle. | N_T = 1 … 40, H = 8 h, W = 1 h | (a) exact; (b) as stated |
| P-007-10 | For any dispatcher (classical, LP, learned), under the `deterministic` profile the loads completed in [0, H] are ≤ LP\*·H + N_T, where LP\* is the optimum of FR-007-19 in loads/h: every realised flow satisfies the LP constraints. Under the `engine` profile, the 30-seed mean satisfies the same bound plus 3 SE. | A1-like scenarios with 2–4 loaders | as stated |
| P-007-11 | Metamorphic, LP (both solvers): relaxing any capacity never lowers the optimum; scaling every loader and dump capacity and N_T by k ∈ {0.5, 2, 3} scales the optimum by k; removing a path never raises the optimum; expressing times in minutes and rates per minute divides the optimum by 60. | random feasible instances ≤ 64 paths | rtol 1e-7 |
| P-007-12 | On scenarios with ≤ 2 loaders, 1 dump, ≤ 8 trucks, fast mode and `fixed` or `nearest` dispatch, an independent SimPy model fed by the same variate streams gives the same cyclelog: identical events, cycles and tonnes, and times within 1e-6 s. | 20 random small scenarios × 3 seeds | as stated |
| P-007-13 | Vectorised environment: (a) under the `deterministic` profile it reproduces P-007-09(b); (b) under the `exponential` profile with `fixed` dispatch it reproduces exact MVA within max(3 SE, 1 %); (c) the trajectory of copy b is identical for B = 1 and B = 64 with the same per-copy seed; (d) a strictly increasing relabelling of truck ids leaves the copy's tonnes series unchanged. | CPU device | (a), (b) as stated; (c), (d) exact |
| P-007-14 | Metamorphic, time-delta GAE: (i) with every Δt = 1 it equals the standard GAE recursion; (ii) Δt' = k·Δt with γ' = γ^{1/k} and λ' = λ^{1/k} leaves the advantages unchanged; (iii) multiplying rewards and values by c multiplies the advantages by c. | float32, length 1 … 512, Δt ∈ [1, 600], γ, λ ∈ [0.9, 1) | (i), (iii) rtol 1e-6; (ii) rtol 1e-5 |
| P-007-15 | Metamorphic, attention policy (M5): (i) permuting non-deciding truck tokens leaves the action distribution unchanged; (ii) permuting target tokens permutes the logits the same way; (iii) appending masked padding tokens leaves the outputs unchanged; (iv) the same weights accept 1 … 40 trucks. | float32, random states | max abs 1e-6 |
| P-007-16 | MLP policy (M4): permuting target slots permutes the logits; permuting non-deciding trucks leaves them unchanged (pooled fleet features); masked targets have probability 0. | float32, random states | max abs 1e-6; masked = 0 exactly |
| P-007-17 | A\*: on random DEMs of ≤ 64 × 64 cells with dyadic elevations, the A\* cost equals the networkx Dijkstra cost on the same feasible graph; every returned edge satisfies the grade limit; h(n) never exceeds the true cost-to-go (Dijkstra from the goal on the reverse graph). | elevations k·2⁻¹⁰ m, \|z\| ≤ 2¹² m, g_max ∈ [0.02, 0.3] | rtol 1e-12; grade exact |
| P-007-18 | Metamorphic, A\*: (i) mirroring the DEM and the start and goal gives the same cost; (ii) adding a dyadic constant to every elevation gives the same path and cost; (iii) raising RR never lowers the cost; (iv) raising g_max never raises the cost; (v) on a flat DEM the cost equals (m·g/η)·(RR/100)·(octile distance). | as P-007-17 | (i), (iii), (iv) rtol 1e-12; (ii) exact; (v) rtol 1e-12 |
| P-007-19 | Metamorphic, route energy: (i) non-decreasing in grade, payload and RR; (ii) additive over concatenated routes; (iii) wheel energy of a climb ≥ m·g·Δz; (iv) diesel CO₂ = fuel × the knowledge-table factor (linear); (v) a trolley route with zero trolley length equals diesel; (vi) regenerated energy ≤ η_regen·m·g·(GR − RR)/100·L; (vii) on a flat road A → B equals B → A. | routes ≤ 200 segments, grades ±20 %, RR ∈ [0.5, 10] %, payload ∈ [50, 400] t | rtol 1e-12; inequalities exact |
| P-007-20 | Metamorphic, KPI layer: (i) computing the KPIs with trace times in seconds or in hours gives the same t/h, match factor and utilisation; (ii) the match factor is unchanged when N_T and N_L are multiplied by the same integer k; (iii) fleet tonnes equal the sum of per-loader tonnes. | random traces from golden scenarios | rtol 1e-12 |
| P-007-21 | The variate seam does not change the model: under the `engine` profile, traffic mode and `sptf`, the mean t/h over 30 seeds with the counter variate source and with the engine's own random-stream manager differ by an amount whose Welch 99 % CI contains 0. | A1-like scenario, 30 seeds per arm | as stated |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-007-01 | One 8 h shift (≈ 10⁴ events, ≤ 40 trucks) in the TypeScript twin on tier T2 (WASM) | ≤ 1 s (`lane_gate.run_s_max`, proposed key, pending maintainer approval); otherwise the lane is precompute (FR-000-15) | Playwright timing on the reference machine, recorded in the manifest |
| NFR-007-02 | Size of the TypeScript analytical ports (M1, M6 energy, A\*, LP); loading of all haulage engines | ≤ 50 KB gzip together; all engines lazy-loaded, none in the initial JS (NFR-000-01) | build report |
| NFR-007-03 | Each exported dispatch policy (ONNX) | < 2 MB (live lane) | CI budget check |
| NFR-007-04 | A\* on a 512 × 512 grid and the A1 LP (≤ 64 paths) on T2 | A\* ≤ 1 s; LP ≤ 50 ms | Vitest benchmark on the reference machine |
| NFR-007-05 | Dispatch training budget | the recipe stage declares `resources.vram_gib_est` ≤ 4 and `timeout_s` ≤ 18,000 (5 GPU-hours; the recipe contract of spec 001 has no GPU-hour field); `studio bench` measures decisions/s before any run expected to last > 1 h | recipe schema check + bench record |
| SC-007-01 | PPO dispatch (M4) against SPTF and against LP, on t/h (refines SC-000-02) | ≥ 30 paired seeds; "beats SPTF / LP" only if the paired 95 % CI of the t/h difference excludes 0, otherwise "no significant difference" | `s50_evaluate` table (FR-007-29) |
| SC-007-02 | Attention policy (M5) against SPTF and against LP, on t/h; also against M4 and per fleet size | ≥ 30 paired seeds; same decision rule; the per-fleet-size comparison is reported | `s50_evaluate` table |
| SC-007-03 | Export parity of each policy | ONNX Runtime CPU fp32 against PyTorch fp32 on ≥ 200 golden states: rtol 1e-3, atol 1e-5, max abs 1e-4; 100 % masked-argmax agreement; TensorRT and reduced-precision variants are reported, and failing ones are reported as rejected (spec 016) | `s60_export` parity report |
| SC-007-04 | Fidelity of the training environment before training is accepted | for `fixed`, `nearest`, `sptf` and `sq`: \|mean t/h (environment) − mean t/h (reference DES, fast mode)\| ≤ 3 % of the DES value over 30 seeds; the traffic-mode gap is reported | `s30_train` pre-check report |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-007-01 | Scenario bundle (network, equipment classes, fleet, loaders, dumps, destinations, dispatcher, variate profile, quantile tables, engine constants, KPI window, live flag) | `contracts/haul-scenario.schema.json` (new, T-007-001) | network builder / `s05_synthesize` → adapter, TypeScript twin, vectorised environment |
| DC-007-02 | Event trace + cyclelog + scalar results (with header: bundle SHA-256, seed, dispatcher, profile, engine version) | `contracts/des-trace.schema.json` (new) | adapter → goldens, KPI layer, web replay |
| DC-007-03 | Paired dispatch evaluation table | `contracts/dispatch-eval.schema.json` (new) | `s50_evaluate` → web Charts, docs, run manifest |
| DC-007-04 | Policy input/output layout (feature order, units, normalisation, masks, tie rule) | `contracts/dispatch-policy-io.schema.json` (new) | `s60_export` → TypeScript twin, ONNX Runtime Web |
| DC-007-05 | Route-energy table (per drivetrain and route: kWh/t, L/(t·km), kg CO₂e/t, regenerated kWh, basis, UNVERIFIED row ids) | `contracts/haul-energy.schema.json` (new) | route-energy engine → A2 Charts, E1 |

Every artefact above is also listed in a manifest valid against `contracts/manifest.schema.json` (DC-000-01).

## 7. Edge cases and assumptions

**Edge cases**
- **Closures and breakdowns.** Temporary unreachability caused by closure windows or breakdowns is normal engine
  behaviour (trucks park and retry); it is not `DisconnectedNetwork`, which applies only to the frozen network without
  closures (FR-007-04).
- **No serviceable loader.** When no loader can serve (all faces blocked or down), every dispatcher parks the truck
  (FR-007-33). That is not an error of the run.
- **Quantile tables.** Tables have 2¹² bins with linear interpolation. The top 12 bits of a 64-bit word choose the bin
  and the next 52 bits the position inside it. The end bins are set so that their means equal the conditional tail
  means. A bundle that requests a family/parameter pair with no table is rejected (`InvalidScenario`).
- **Speed-solver memoisation.** The reference engine memoises speeds on rounded keys, and the first value computed for
  a key is reused. The twin reproduces this rule exactly, including Python's round-half-even at 0.01 % on the exact
  binary value; a dedicated golden scenario covers it (FR-007-11).
- **Policy near-ties.** The ONNX Runtime CPU and WASM backends differ by up to 1e-4 in fp32, which can flip an argmax at
  a near-tie. FR-007-32 bounds exactly that case.
- **Exact parity is version-bound.** A new engine version or a new variate-table build re-bakes every golden
  (FR-007-02).

**Assumptions (sources pinned at specification)**
- **Cycle-component families.** Dindarloo, Osanloo and Frimpong (2015), J. SAIMM 115(3):209–219,
  DOI 10.17159/2411-9717/2015/v115n3a6, read on 2026-10-06:
  - Table A.4, p. 219, gives loading as exponential (mean 1.54 min), dumping as exponential (mean 1.7 min), and truck
    spot, manoeuvre and return times as uniform. The uniform bounds are printed "Min - Max 0.52-0.13", "0.42-0.11",
    "0.42-0.10" and "0.54-0.13" min, with the order as printed.
  - Table A.3, p. 219, gives loaded haul times as normal per loader and destination.
  - PitStudio uses only the families: the `exponential` profile matches Table A.4's loading and dumping. The means are
    site-specific (an iron-ore mine) and are not used. The `engine` profile keeps the reference engine's
    class-representative lognormal families.
- **Philox4x64-10 known-answer vectors.** Random123 `tests/kat_vectors`, read on 2026-10-06. FNV-1a-64 uses the standard
  offset basis `cbf29ce484222325` and prime `100000001b3`.
- **Diesel CO₂.** 10.21 kg CO₂ per US gallon: EPA GHG Emission Factors Hub 2025, Table 2, p. 2, verified in the docs.
  With 3.785411784 L per US gallon, that is 2.6972 kg CO₂/L. The value is taken from the `minephys` knowledge table
  (FR-007-40).
- **Decision-rule worked example (hand calculation).** For n = 30, t₀.₉₇₅,₂₉ = 2.0452. With s_d = 110 t/h the
  half-width is 41.07 t/h. A mean of 45 t/h gives [3.9, 86.1], which is "better"; a mean of 30 t/h gives
  [−11.1, 71.1], which is "no significant difference".
- **LP worked example (hand calculation).**
  - Without a blend floor: optimum 19.5 loads/h at (12, 7.5); duals: loader 1 = 0.375, fleet = 1.25, others 0.
  - With the blend floor 0.15·x₁ − 0.25·x₂ ≥ 0: optimum 19.2 at (12, 7.2); duals: loader 1 = 1.6, blend = 4, fleet = 0.
- **M1 worked examples (hand calculation).**
  - N = 8, λ/μ = 1/7, μ = 20 /h: π₀ = 0.17882, X = 16.424 loads/h.
  - N = 5, λ/μ = 0.2, μ = 15 /h: π₀ = 0.28487, X = 10.727 /h. MVA with one queue (μ = 15 /h) and a 20 min delay gives
    the same X. For N = 1, 3, 6 and 8, X = 2.50, 7.06, 12.12 and 13.95 /h.
- **M6 worked example (hand calculation).** A 400 t gross truck on 2 km at 10 % grade with 3 % RR (small-angle form):
  510.12 kN and 283.4 kWh at the wheels, of which the lift is 218.0 kWh.

**UNVERIFIED (kept as inputs; no oracle depends on them)**
- **Rolling resistance by surface.** The OEM article could not be read (it timed out on 2026-10-06). RR is a scenario
  input. The `minephys` default row stays UNVERIFIED and is flagged in results (FR-007-40). All RR oracles use explicit
  values.
- **Customary maximum ramp grade (8–10 %).** The primary text (Tannant and Regensburg, 2001) could not be read; only a
  search snippet was seen. g_max is a required design input of the A2/E1 recipes. Its knowledge-table default stays
  UNVERIFIED, and the A\* oracles use explicit values.
- **Truck and loader hourly rates.** No primary source was read, so there is no default. Cost per tonne appears only
  with user-supplied rates; truck- and loader-hours per kt are always reported (FR-007-08).
- **Generic specific fuel consumption, diesel energy density and drivetrain efficiencies.** These are `minephys`
  knowledge rows with their own status. The energy oracles use explicit values.

## 8. Clarifications log

1. **Variate seam (resolved).** The reference engine draws from NumPy's PCG64 with ziggurat normals and calls `exp` for
   lognormal variates. A TypeScript twin cannot reproduce that without transcendental functions, which the parity
   class forbids. Resolution: the adapter replaces the engine's random-stream manager for the duration of a run with
   PitStudio's counter-based source (FR-007-01, FR-007-05). A version and module-hash guard (FR-007-02) protects the
   seam. P-007-21 shows that the seam does not change the model's behaviour. If a later engine release exposes a
   random-source parameter, the seam moves there, and the goldens are re-baked.
2. **Event ordering key (docs vs reference; plan wins).** The M02 page shows the key (time, priority, sequence). The
   reference engine orders by (t, seq), with seq a global schedule counter and no priority field. The plan names this
   engine as the reference, so parity uses (t, seq) (FR-007-09). The docs' priority field is degenerate.
3. **Dispatcher mapping (resolved).** SPTF = the engine's MinSaturationPolicy; shortest queue = MinQueuePolicy. The
   engine also ships RandomPolicy, which is reported for context. "Minimum shovel idle", listed on the M02 and
   minehaulsim pages, is not shipped by the engine and is implemented by PitStudio as `min-idle` (FR-007-14). The A1
   page's set (fixed, nearest, SPTF, shortest queue) is a subset.
4. **Travel-time model (docs vs plan; plan wins).** The M06 page says M6 segment times feed the DES. The plan makes
   `minehaulsim` the reference engine, with its own rimpull/retarder kinematics. Resolution: M6 provides the route
   geometry (FR-007-38), and the DES computes the times. The M6 per-segment speeds are reported next to the DES speeds
   for A2 (descriptive).
5. **Where A\* lives (docs vs plan; plan wins).** The M06 page places A\* in `minephys.haulage`. The plan's module list
   for `minephys` has no routing. Resolution: A\* is PitStudio root-core code plus a TypeScript port; `minephys`
   supplies the energy physics (FR-007-34, FR-007-35).
6. **Queue-time P90.** It needs arrival times that the cyclelog does not hold. Resolution: the event trace records the
   engine's arrival events (FR-007-09).
7. **Observation features and reward**, which the M04 page and the dispatch card leave to this spec, are fixed here:
   - truck token (12): state one-hot (7: travel-empty, queue-loader, loading, travel-loaded, queue-dump, dumping,
     parked/down), payload / mean payload, time left in the state (h), ETA to its current target (h), deciding flag,
     valid flag;
   - target token (9): loader/dump flag, queued / 40, inbound / 40, time until free (h), backlog (h), mean service
     time (h), ETA of the deciding truck (h; 0 when masked), spots / 4, serviceable flag;
   - reward: fleet tonnes dumped per decision interval / 1,000, with no shaping (FR-007-23, FR-007-31);
   - the target-token "grade" on the M05 page is omitted because the environment has no blending.
8. **Dump choice (resolved).** The engine's baselines always send loaded trucks to the first dump. For a fair
   comparison, every dispatcher, including LP and the learned ones, uses the loader's declared destination (FR-007-14).
   LP paths are therefore loader → declared destination.
9. **Environment acceptance (resolved).** The vectorised environment has no traffic layer, so its fidelity gate is
   checked against the reference DES in fast mode, and the traffic-mode gap is reported (SC-007-04).
10. **Scope split with 018-web-cases.** The engines (twin, LP, ports, A\*) and their parity are specified here. Routes,
    workers, tiers and UI controls are in 018.
11. **Cost per tonne.** The hourly rates are UNVERIFIED, so there is no default. Resource hours per kt are reported
    instead (FR-007-08).
12. **Export opset.** The plan says opset 17–19 and the dispatch card says opset 17 with IR 10; they agree. The export
    mechanics are in spec 016.
13. Integration 2026-10-07: field names follow spec 001's contracts. NFR-007-05 now names `resources.vram_gib_est`
    (GiB, not `vram_gb_est`) and expresses the 5 GPU-hour budget through `timeout_s`, because the recipe contract has no
    `gpu_h_est` field.
14. Integration 2026-10-07: `lane_gate.run_s_max` (NFR-007-01) is marked "proposed key, pending maintainer approval".

## 9. Changes (only for features that modify earlier behaviour)
Not applicable: a new feature. It refines SC-000-02 without modifying it.
### ADDED Requirements
### MODIFIED Requirements
### REMOVED Requirements
