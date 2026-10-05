# M02 — Haulage discrete-event simulation with classical dispatchers

> A deterministic, seeded discrete-event simulation (DES) of trucks, shovels, dumps and roads that turns a pit's road
> network into cycle times, queues and tonnes per hour, with an exact-trace twin in the browser. · Part of:
> [Methods](README.md) · Related: [Haulage theory](../theory/haulage.md) · [M01](m01-match-factor-queueing.md) ·
> [minehaulsim](../frameworks/minehaulsim.md) · [DEC-0013](../architecture/decisions/DEC-0013-haulage-engine-minehaulsim.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical | no | live + precompute | [A1](../cases/a1-truck-shovel-dispatch.md), [A2](../cases/a2-haul-road-electrification.md), [B1](../cases/b1-traffic-proximity.md), [C3](../cases/c3-dust.md) | `minehaulsim` 0.12.1 (Apache-2.0) reference; TypeScript twin (exact trace); SimPy oracle (MIT) | not yet implemented |

## What and why

Queueing formulas ([M01](m01-match-factor-queueing.md)) assume exponential times, a single shovel per truck and no
dispatch decisions. Real haulage breaks all three: haul times follow the road profile, loading is not exponential,
trucks bunch, and a dispatcher reassigns trucks every cycle. Discrete-event simulation is the industry-standard
validator for exactly these effects [6][7].

M02 is the haulage engine of the whole suite:

- it produces cycle times, queue lengths, shovel idle time, match factor and tonnes per hour for case A1;
- it is the environment in which every dispatcher is evaluated: the classical rules here, the LP of
  [M03](m03-lp-dispatch.md) and the learned policies of [M04](m04-ppo-dispatch.md) and
  [M05](m05-attention-fleet-policy.md);
- its truck trajectories drive traffic in B1, emissions in C3 and energy in A2.

PitStudio does not re-implement a DES in Python. It uses the maintainer's published `minehaulsim` package as the
reference engine [1] and writes a TypeScript twin that must reproduce its event trace exactly
([DEC-0013](../architecture/decisions/DEC-0013-haulage-engine-minehaulsim.md)).

![DES event loop with exact-trace parity between the Python reference and the TypeScript twin](../assets/diagrams/des-event-loop.svg)

*The future-event list drives each truck through its cycle; at the dispatcher decision point a rule or policy picks
the next shovel, and the Python and TypeScript engines must emit the same event trace.*

## The algorithm

### State and events

The simulation state is the clock $t$, a **future-event list** (a binary heap) and, per truck, its state (travel
empty, queue at shovel, spot and load, travel loaded, queue at dump, dump), position on the road graph and payload.
Each event is a tuple ordered by a total key:

$$
\text{key}(e) = (t_e,\ \text{priority}_e,\ \text{seq}_e)
$$

where $t_e$ is the event time (s), priority breaks ties between event types (for example "end dump" before
"dispatch") and $\text{seq}_e$ is a monotonically increasing sequence id. The explicit tie-break is what makes two
independent implementations produce the same trace [8].

```text
run(scenario, seed, horizon):
    rng   = CounterPRNG(seed)              # same counter-based generator in Python and TS
    queue = heap of initial "dispatch" events, one per truck, at t = 0
    while queue not empty and queue.min.t <= horizon:
        e = queue.pop_min()                 # by (t, priority, seq)
        clock = e.t
        match e.type:
          dispatch     -> target = dispatcher(state, truck)          # decision point
                          schedule(arrive_shovel, clock + travel(truck.node, target, empty, rng))
          arrive_shovel-> if shovel busy: enqueue truck   else: schedule(end_load, clock + load(rng))
          end_load     -> schedule(arrive_dump, clock + travel(shovel, dump, loaded, rng))
                          if shovel queue: start next truck's load
          arrive_dump  -> if dump busy: enqueue        else: schedule(end_dump, clock + dump_time(rng))
          end_dump     -> record tonnes; schedule(dispatch, clock)
        trace.append((clock, truck, e.type, node))
    return trace, kpis(trace)
```

### Travel and loading times

Travel times are not drawn from an arbitrary distribution. Each road segment's time comes from the haul-physics model
of [M06](m06-haul-road-energy-routing.md): the steady speed on a segment solves
$F_{\text{rim}}(v) = F_{\text{req}}(v)$ uphill and is capped by the retarder envelope downhill, with total resistance
= rolling + grade resistance [2], plus seeded noise. Loading follows the standard pass model†:

$$
t_{\text{load}} = n_p \, t_{\text{sc}}, \qquad
n_p = \left\lceil \frac{M_{\text{target}}}{V_b \, k_f \, \rho_{\text{loose}}} \right\rceil, \qquad
\rho_{\text{loose}} = \frac{\rho_{\text{bank}}}{1 + s_w}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $n_p$ | number of bucket passes | – |
| $t_{\text{sc}}$ | shovel swing cycle time | s |
| $M_{\text{target}}$ | target payload | t |
| $V_b$ | heaped bucket volume | m³ |
| $k_f$ | bucket fill factor | – |
| $\rho_{\text{bank}}$, $\rho_{\text{loose}}$ | in-situ and loose bulk density | t/m³ |
| $s_w$ | swell factor | – |

The full cycle is the sum of its parts†:

$$
T_c = t_{\text{spot,L}} + t_{\text{load}} + t_{\text{haul}} + t_{\text{spot,D}} + t_{\text{dump}} + t_{\text{return}}
+ t_{\text{queue,L}} + t_{\text{queue,D}}
$$

† Standard textbook forms; transcriptions are checked by worked-example tests at specification.

### Classical dispatchers

The dispatcher is called at every "dispatch" event. The classical set targeted for comparison is the one used across
the open dispatch literature [3][4]:

| Rule | Decision for a free truck |
|---|---|
| Fixed allocation (FixedGroup) | always return to its assigned shovel |
| Nearest / greedy | the shovel with the shortest empty travel time |
| Shortest processing time first (SPTF) | the shovel with the earliest expected *start of loading* (travel + queue + current load) |
| Shortest queue (SQ) | the shovel with the fewest trucks waiting |
| Minimum shovel idle | the shovel that would otherwise idle soonest |

`minehaulsim` ships five baseline dispatch policies [1]; the exact mapping of its policies to this table is fixed in
the spec. The LP-guided dispatcher is [M03](m03-lp-dispatch.md); learned dispatchers are
[M04](m04-ppo-dispatch.md) and [M05](m05-attention-fleet-policy.md).

### Reproducibility and the TypeScript twin

`minehaulsim` is a deterministic, byte-identical DES on constrained road networks (one-way ramps, passing, junction
blocking, grade kinematics) with seeded parametric pit generators [1]. The twin follows four rules so that the
browser reproduces it exactly:

1. **One counter-based PRNG** (a PCG- or Philox-family generator) implemented identically in Python and TypeScript.
2. **No transcendental `Math.*` calls in variate generation.** JavaScript `Math` functions have
   implementation-dependent precision across browsers [8]; variates are drawn with integer arithmetic or from
   pre-baked variate streams in the golden fixture.
3. **Explicit tie-break** by (time, priority, sequence id).
4. **Event traces compared exactly**, KPIs within tolerance.

SimPy 4.1.2 (MIT) [5] provides an independent process-based oracle for small scenarios.

## Baseline and comparison

- **Against M01.** Under exponential times and fixed allocation, DES throughput must agree with MVA within the DES
  confidence interval (see [M01](m01-match-factor-queueing.md#baseline-and-comparison)).
- **Against SimPy.** The same small scenarios run in a SimPy model must give identical KPIs to tolerance.
- **Between dispatchers.** Classical rules are compared on **paired seeds** (common random numbers: the same seed
  gives every rule the same breakdowns and variates). The metric is tonnes per hour; the claim "rule A beats rule B"
  follows the [pre-registered decision rule](README.md#how-methods-are-compared). The greedy closest-shovel rule is
  the benchmark used in the dispatch literature [3].
- **Against the field.** No open haul telemetry exists for the case pits, so M02 is "calibrated synthetic — not
  validated against real data". Published DES studies [6][7] show the size of effects (for example road
  deterioration) but are not reproduced numerically.

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)):

- **DES exact trace.** For every golden scenario the TypeScript twin emits an event trace identical to the Python
  reference, event by event: (time, truck, event type, node).
- **Oracle agreement.** SimPy and M01 checks as above, within tolerances fixed in
  `specs/000-foundation/thresholds.yaml`.
- **Metamorphic relations** (at least three), for example: adding a truck never lowers total tonnes in the
  under-trucked regime; raising every shovel's loading rate never lowers throughput; permuting truck ids leaves KPIs
  unchanged; a zero-noise run equals the deterministic cycle.

**Results: Not yet run** — produced in the data-and-models phase. Reported: A1 KPIs (t/h, queue, match factor,
cost/t) per dispatcher with paired-seed confidence intervals, and the parity report.

## Lane and web delivery

**Live + precompute.** A shift is about $10^4$ events, which the TypeScript worker must finish in under 1 s on the
T2 (WASM-class) tier (gate estimate, measured when the web is built; [compute lanes](../pipelines/compute-lanes.md)).
Long sweeps and the paired-seed tables are precomputed in the pipeline and shipped as baked traces, which are also the
fallback when the live engine is unavailable.

## Assumptions and limits

- Road network, fleet and shovel parameters come from the Bingham road network and generic, academically sourced
  truck parameters — not from any operator. A simulation-grade twin, not a live digital twin.
- Breakdowns, shift changes and road deterioration enter only as modelled stochastic processes.
- The DES is only as good as its travel-time model ([M06](m06-haul-road-energy-routing.md)); OEM rimpull charts are
  proprietary and are not used.
- Exact-trace parity holds only within one version of the engine and the PRNG; a version bump re-bakes the goldens.

## In PitStudio

- **Cases:** [A1](../cases/a1-truck-shovel-dispatch.md) (dispatch and fleet sizing),
  [A2](../cases/a2-haul-road-electrification.md) (energy per cycle), [B1](../cases/b1-traffic-proximity.md) (truck
  trajectories for traffic), [C3](../cases/c3-dust.md) (vehicle-kilometres for dust).
- **Code (planned):** `minehaulsim` as a locked dependency of `pipeline/` (0.12.1 in `pipeline/uv.lock`); scenario
  recipes run by the runner (`src/pitstudio/runner/`); a TypeScript DES worker under `web/`; golden traces in the
  test fixtures.
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. `minehaulsim` 0.12.1 (Apache-2.0) — deterministic DES of open-pit and underground haulage; rimpull/retarder speed
   by grade; constrained roads; five dispatch policies; seeded pit generators. https://pypi.org/project/minehaulsim/
2. Soofastaei et al. (2016). MLP ANN for haul-truck energy consumption (TR = RR + GR; GVW, speed and resistance as fuel
   drivers). IJMST 26(2):285–293. https://doi.org/10.1016/j.ijmst.2015.12.015
3. Moradi-Afrapoli, A., Upadhyay, S. & Askari-Nasab, H. (2021). Two-stage dispatch review; greedy baselines. JSAIMM.
   https://doi.org/10.17159/2411-9717/522/2021
4. OpenMines — open-pit truck-dispatch simulator with baseline dispatchers (Naive, Random, Nearest, FixedGroup, SPTF,
   SQ), MIT. https://github.com/370025263/openmines
5. SimPy 4.1.2 (MIT). https://pypi.org/project/simpy/
6. Meneses & Sepúlveda (2023). DES of truck productivity and fuel under haul-road deterioration. Mining 3(1):96–105.
   https://doi.org/10.3390/mining3010006
7. Upadhyay et al. (2017). Simulation and optimisation for uncertainty-based short-term planning in open pits. IJMST.
   https://doi.org/10.1016/j.ijmst.2017.12.003
8. MDN — `Math`: precision of many functions is implementation-dependent across browsers.
   https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Math
