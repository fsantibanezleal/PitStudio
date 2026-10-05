# M20 — Agent-based mixed traffic, time-to-collision and rigid-body vehicles

> Haul trucks driven by the DES share the real road network with light vehicles and people; every interaction is
> scored by time-to-collision, near-misses are counted per 1,000 hours, and rigid-body physics runs the same scenes
> deterministically in the browser. · Part of: [Methods](README.md) · Related:
> [Haulage theory](../theory/haulage.md) · [M02 DES](m02-haulage-des.md) · [M23 sensors](m23-rtx-sensor-simulation.md) ·
> [Case B1](../cases/b1-traffic-proximity.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical / SOTA | no | live + replay | [B1](../cases/b1-traffic-proximity.md) | TypeScript agents + Rapier 0.21 (Apache-2.0, WASM); PhysX vehicles in Isaac Sim as the visual twin | not yet implemented |

## What and why

Powered haulage is the leading cause of US mining deaths: 13 of 33 fatalities (39 %) in 2025 [1]. Mobile equipment
caused 26 % of fatalities in the global industry body's data for 2021–2024 [2], and US surface mines now operate under a
written safety-program rule for surface mobile equipment [3]. Mixed fleets — autonomous haul trucks next to manned
dozers, light vehicles and people — add new interaction risks [4].

Case B1 asks how close the fleet comes to its people and light vehicles, and how that changes with road layout,
speed limits and dispatch. M20 is the traffic layer that answers it:

- **agents:** haul trucks follow trajectories from the [DES](m02-haulage-des.md) with speeds from
  [M06](m06-haul-road-energy-routing.md); light vehicles and people follow the road graph with right-of-way rules and
  proximity envelopes;
- **metric:** time-to-collision (TTC) for every pair, aggregated to minimum TTC and near-misses per 1,000 operating
  hours;
- **physics:** Rapier rigid bodies for vehicles, rock fall and berm impacts in the browser; PhysX vehicles inside
  Isaac Sim for the rendered visual twin.

## The algorithm

### Agents

```text
tick(dt):
    for truck in trucks: pose = des_trace.interpolate(t)            # M02 trajectory, M06 speeds
    for lv in light_vehicles + people:
        lv.target_speed = min(speed_limit(edge), envelope_speed(nearest_truck))
        if at_intersection and not has_right_of_way(lv): yield
        lv.advance(dt)
    for each pair (a, b) within a search radius: record ttc(a, b)
    rapier.step(dt)                                                  # rigid bodies (rocks, berm impacts, vehicle bodies)
```

Right-of-way rules and proximity envelopes are scenario inputs (fixed per case in the spec).

### Time-to-collision

Treat two agents as discs whose radii sum to $R$ (m), with relative position $\mathbf p = \mathbf x_b - \mathbf x_a$ (m)
and relative velocity $\mathbf w = \mathbf v_b - \mathbf v_a$ (m/s), held constant. They touch when
$\lVert \mathbf p + \mathbf w\tau\rVert = R$, a quadratic in $\tau$; the TTC is its smallest positive root (derived here
from constant-velocity kinematics):

$$
\mathrm{TTC} = \frac{-(\mathbf p\cdot\mathbf w) - \sqrt{(\mathbf p\cdot\mathbf w)^2 - \lVert\mathbf w\rVert^2\big(\lVert\mathbf p\rVert^2 - R^2\big)}}{\lVert\mathbf w\rVert^2}
$$

defined when the agents are closing ($\mathbf p\cdot\mathbf w < 0$) and the discriminant is non-negative; otherwise
$\mathrm{TTC} = \infty$. **Minimum TTC** is the smallest value over an encounter; a **near-miss** is an encounter whose
minimum TTC falls below a threshold $\tau^{\ast}$ (s, fixed in the spec; the haul-truck policy of
[M21](m21-isaac-lab-policies.md) uses 3 s); the rate is near-misses per 1,000 h of exposure.

**Worked example.** A truck heads east at 10 m/s, a light vehicle west at 5 m/s, 100 m apart on the same line, combined
radius 4 m: $\mathbf p\cdot\mathbf w = -1{,}500$, $\lVert\mathbf w\rVert^2 = 225$, discriminant
$2{,}250{,}000 - 225 \times 9{,}984 = 3{,}600$, so $\mathrm{TTC} = (1{,}500 - 60)/225 = 6.4$ s — exactly the gap of
96 m divided by the closing speed of 15 m/s.

### Rigid bodies (Rapier)

Rapier 0.21 (Apache-2.0) runs as WASM in a worker. Its JavaScript/WASM build is **cross-platform deterministic** for
the same Rapier version and identical initial conditions, verifiable by hashing a snapshot; its documentation warns
that `Math.sin`/`Math.cos` are not consistent across platforms, so initial conditions avoid them [5]. The JavaScript
bindings moved from the archived `rapier.js` repository into the main Rapier repository in July 2026 [6]. Uses:
vehicles as rigid bodies on the ramp mesh, rock fall from benches, a truck striking a berm (US rules require berms at
least mid-axle height of the largest vehicle on the road [7]).

## Baseline and comparison

- **Scenario contrasts:** road layout (one-way vs two-way ramps), speed limits, dispatch rule and light-vehicle access
  rules are compared on minimum-TTC distributions and near-miss rates, on **paired seeds** (the same DES seed gives
  every scenario the same truck variates). "Scenario A is safer" follows the
  [decision rule](README.md#how-methods-are-compared).
- **Sensor context:** the lidar and radar of [M23](m23-rtx-sensor-simulation.md) report at which range each agent is
  detected in dust; the TTC margin at detection is the joint metric of case B1.
- **Rendered twin:** PhysX vehicles in Isaac Sim (stage `st54_vehicles`) render the same encounters for video; they are
  a visual twin, not the source of the TTC statistics.

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)):

- TTC unit tests (head-on and crossing cases with closed-form answers) and metamorphic relations: scaling both
  velocities by $k$ scales TTC by $1/k$; translating or rotating the scene leaves TTC unchanged; swapping the two
  agents leaves it unchanged;
- truck agents reproduce the DES trace they are driven by (exact parity with [M02](m02-haulage-des.md));
- Rapier parity by snapshot hash against golden runs of the same Rapier version in Node.

**Results: Not yet run** — produced in the data-and-models phase. Reported: B1 minimum-TTC distributions and
near-misses per 1,000 h per scenario, with paired CIs, and rendered encounter clips.

## Lane and web delivery

**Live + replay.** The agents and Rapier run live in workers; the gate is about 2 MB of Rapier WASM and 60 Hz for up to
40 vehicles (estimates, measured when the web is built). The Isaac Sim encounter videos are replayed (Isaac Sim
performance data stay local-only). Fallback: baked video.

## Assumptions and limits

- Agent behaviour is rule-based and parameterised, not learned from real driver data; near-miss rates are
  scenario comparisons, not predictions of real incident rates.
- Constant-velocity TTC ignores braking and steering; it is a screening metric.
- Rapier vehicles are rigid bodies with simplified wheels; tyre and suspension fidelity is not claimed.
- **Educational, not a proximity-detection or collision-avoidance system.**

## In PitStudio

- **Cases:** [B1](../cases/b1-traffic-proximity.md) (minimum TTC, near-misses per 1,000 h).
- **Code (planned):** TypeScript agents and the Rapier worker under `web/`; scenario recipes and DES traces from
  `pipeline/`; PhysX visual twin in `studio/isaac/` (`st54_vehicles`). Framework page:
  [Rapier, WebGPU and Pyodide](../frameworks/rapier-webgpu-pyodide.md).
- **Status:** not yet implemented — built test-first in the build phase.

NVIDIA, Isaac Sim and PhysX are named nominatively; PitStudio is not affiliated with or endorsed by NVIDIA.

## References

1. US MSHA — Powered Haulage Safety (2025: 13 of 33 fatalities, 39 %).
   https://www.msha.gov/safety-and-health/safety-and-health-initiatives/powered-haulage-safety
2. ICMM — 2020–2024 safety performance insights (mobile equipment 26 % of fatalities, 2021–2024).
   https://www.icmm.com/en-gb/research/health-safety/2025/insights-2020-2024-safety-data
3. Federal Register (2023-12-20) — Safety program for surface mobile equipment (final rule).
   https://www.federalregister.gov/documents/2023/12/20/2023-27640/safety-program-for-surface-mobile-equipment
4. Haight & Burgess-Limerick (2023). Automation experience with a global perspective (NIOSH).
   https://stacks.cdc.gov/view/cdc/148735
5. Rapier — JavaScript determinism (snapshot hash; `Math.sin/cos` caveat).
   https://rapier.rs/docs/user_guides/javascript/determinism
6. `dimforge/rapier.js` — archived 2026-07-12, merged into `dimforge/rapier`. https://github.com/dimforge/rapier.js
7. 30 CFR 56.9300 — berms at least mid-axle height of the largest self-propelled equipment.
   https://www.law.cornell.edu/cfr/text/30/56.9300
