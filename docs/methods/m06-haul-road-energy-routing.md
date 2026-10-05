# M06 — Haul-road energy and grade-constrained routing (diesel, trolley, battery-electric)

> One-dimensional truck dynamics turn a road profile into speed, cycle time, energy and CO₂ per tonne, and an A*
> search over the terrain finds the least-energy route that respects a maximum ramp grade. · Part of:
> [Methods](README.md) · Related: [Haulage theory](../theory/haulage.md) · [M02 DES](m02-haulage-des.md) ·
> [Case A2](../cases/a2-haul-road-electrification.md) · [Case E1](../cases/e1-pit-shell-pushbacks.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical | no | live | [A2](../cases/a2-haul-road-electrification.md), [E1](../cases/e1-pit-shell-pushbacks.md) | `minephys.haulage` (Apache-2.0) + A* on the DEM (Python and TypeScript) | not yet implemented |

## What and why

Haulage can be up to 60 % of open-pit operating cost [7], and its energy is set by two numbers per road segment: grade
and rolling resistance. Total resistance is the sum of the two, and fuel or energy per tonne follows from gross vehicle
weight, speed and total resistance [1]. Electrification changes the answer: a trolley-assist model on real coordinates
from a copper mine reports a 44 % increase in uphill speed, 16 % shorter cycle travel time and 85 % fuel saving over
each up–down cycle [2]; drive-cycle simulations of battery-electric haul trucks charged from trolley lines find them
feasible and cheaper than diesel-electric under the stated assumptions [3]; one trolley operation reports 830,000 L of
diesel saved per year [4].

M06 gives PitStudio:

- the **travel-time model** that feeds every truck in the [DES](m02-haulage-des.md);
- the **energy, kWh/t and CO₂e/t** KPIs of case A2, for diesel, trolley-assist and battery-electric drivetrains on the
  same road;
- a **grade-constrained least-energy route** over the real terrain, which case E1 uses to turn pushbacks into haul
  distance per lift.

## The algorithm

### Resistance, rimpull and retarding

Per segment with grade angle $\theta$:

$$
TR = RR + GR, \qquad GR = 100 \sin\theta \approx 100 \tan\theta
$$

$$
F_{\text{req}} = m_{\text{GVW}}\, g\, \frac{TR}{100} + m_{\text{eff}}\,\frac{dv}{dt} + \tfrac12 \rho_a C_D A v^2
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $TR$, $RR$, $GR$ | total, rolling and grade resistance | % of weight |
| $m_{\text{GVW}}$ | gross vehicle mass (empty + payload) | kg |
| $m_{\text{eff}}$ | effective mass including rotating inertia | kg |
| $g$ | gravitational acceleration, 9.81 | m/s² |
| $\rho_a$, $C_D$, $A$ | air density, drag coefficient, frontal area | kg/m³, –, m² |
| $v$ | speed | m/s |

The decomposition is the industry one [1]; the force balance is the standard longitudinal-dynamics form†.

- **Uphill (rimpull-limited).** Tractive force is bounded by traction and by power,
  $F_{\text{rim}}(v) \le \min(\mu_t W_{\text{drive}},\ \eta P_{\text{eng}}/v)$, and the steady speed solves
  $F_{\text{rim}}(v) = F_{\text{req}}(v)$. In the power-limited regime $v \approx \eta P / (m g\, TR/100)$†. Here
  $\mu_t$ is the traction coefficient, $W_{\text{drive}}$ the weight on driven wheels (N), $\eta$ the drivetrain
  efficiency and $P_{\text{eng}}$ the engine power (W).
- **Downhill (retarder-limited).** The retarder must dissipate
  $P_{\text{ret}} = m g\, \frac{GR - RR}{100}\, v \le P_{\text{ret,max}}(v)$, which caps the safe descent speed†. On
  trolley or battery-electric trucks this is the energy regeneration can recover [2][3].

PitStudio uses a **generic truck parameter set from academic sources**, documented as such; OEM rimpull charts are
proprietary and are not used.

### Energy, fuel and CO₂

$$
E = \frac{1}{\eta} \int F_{\text{req}}\, v \; dt \quad \text{[J]}, \qquad
e_t = \frac{E}{3.6\times10^{6}\; m_{\text{payload}}} \quad \text{[kWh/t]}
$$

A physics floor anchors intuition: lifting 1 t through 100 m needs $1000 \times 9.81 \times 100$ J $= 0.273$ kWh at the
wheels (arithmetic). Diesel CO₂ uses 10.21 kg CO₂ per US gallon, i.e. about 2.70 kg CO₂/L (UNVERIFIED — pinned at
specification) [5]; grid electricity uses a configurable emission factor. Rolling-resistance values by surface
condition from OEM guidance are UNVERIFIED — pinned at specification, so $RR$ is an input with a stated default, not a
fact.

### Grade-constrained least-energy routing

The terrain (a 1 m DEM from the scene pipeline) becomes a graph: nodes are grid cells, edges connect 8-neighbours.
Each edge $e$ of horizontal length $L_e$ and elevation change $\Delta z_e$ is **feasible** only if
$\lvert\Delta z_e\rvert / L_e \le g_{\max}$, the maximum ramp grade (a design input; customary values around 8–10 %
are UNVERIFIED — pinned at specification). The edge cost is the traction energy drawn,

$$
c(e) = \frac{m g}{\eta}\,\max\!\left(0,\; \frac{RR}{100}L_e + \Delta z_e\right) \;\ge 0 ,
$$

so regenerated energy is booked in the KPI, not in the search (A* needs non-negative costs). The heuristic

$$
h(n) = \frac{m g}{\eta}\,\max\!\left(0,\; \frac{RR}{100}\, d_{xy}(n, \text{goal}) + z_{\text{goal}} - z_n\right)
$$

is admissible: along any path, $\sum_e \max(0, a_e) \ge \max(0, \sum_e a_e)$, the path length is at least the
straight-line distance $d_{xy}$, and the net rise is fixed. A* therefore returns the least-energy feasible route.
Least-cost raster routing with Douglas–Peucker simplification under curvature and bench constraints follows Baek and
Choi [6].

```text
route(dem, start, goal, g_max, truck):
    open = priority queue with (h(start), start); cost[start] = 0
    while open:
        n = pop lowest f = cost + h
        if n == goal: return reconstruct(n)
        for m in neighbours8(n):
            if |dz(n,m)| / L(n,m) > g_max: continue          # grade constraint
            c = cost[n] + edge_energy(n, m, truck)
            if c < cost.get(m, inf): cost[m] = c; push(c + h(m), m); parent[m] = n
    return None                                               # no feasible ramp
```

The route is simplified, then re-evaluated with the full force balance (acceleration and drag included) to give speed,
time and energy per segment; those segment times feed the DES.

### Worked example (illustrative inputs)

A loaded truck of 400 t gross (200 t payload) climbs 2 km of ramp at 10 % grade with 3 % rolling resistance.

- $TR = 13\,\%$, so $F = 400{,}000 \times 9.81 \times 0.13 = 510.1$ kN.
- Work at the wheels over 2,000 m: $1.020 \times 10^{9}$ J $= 283.4$ kWh, of which 218.0 kWh lift the truck 200 m and
  65.4 kWh overcome rolling resistance.
- Per tonne of payload: $283.4 / 200 = 1.42$ kWh/t at the wheels. The lift share agrees with the physics floor:
  $400 \times 2 \times 0.2725 = 218$ kWh.
- Halving rolling resistance to 1.5 % saves 32.7 kWh per trip — the "road maintenance" lever of case A2, which the
  DES then converts into cycle time and t/h.

## Baseline and comparison

M06 is deterministic physics: there is nothing stochastic to test with paired seeds. Comparisons are scenario
contrasts, reported side by side:

- **drivetrain:** diesel vs trolley-assist vs battery-electric on the same route (kWh/t, L/t·km, CO₂e/t, cycle time);
- **route:** least-energy route vs shortest-distance route vs the existing design ramp;
- **road condition:** rolling resistance sweep.

Published field results ([2]–[4]) are cited for scale, not reproduced: PitStudio's truck is generic.

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)):

- worked-example tests for every `minephys.haulage` function against primary sources;
- at least three metamorphic relations, for example: energy is non-decreasing in grade, payload and rolling
  resistance; the A* cost never exceeds the cost of any feasible path found by an exhaustive Dijkstra oracle on small
  grids; no returned edge violates $g_{\max}$ (property test over random terrains);
- TypeScript port parity in the exact class on golden vectors (tolerances in `specs/000-foundation/thresholds.yaml`).

**Results: Not yet run** — produced in the data-and-models phase. Reported: A2 energy and CO₂ tables per drivetrain
on the Bingham ramps, and E1 haul distance per lift.

## Lane and web delivery

**Live.** The force balance is closed-form per segment and A* on a cropped DEM runs in a web worker; analytical models
stay under 50 KB of JavaScript and 1–50 ms per evaluation (estimates; [compute lanes](../pipelines/compute-lanes.md)).
Fallback: baked route and energy grids. The `minephys` wheel in Pyodide gives a reference-engine check.

## Assumptions and limits

- Quasi-steady, one-dimensional dynamics per segment; no lateral dynamics, tyre slip or suspension.
- Generic truck parameters; no OEM charts. Absolute kWh/t is indicative; differences between scenarios are the
  meaningful output.
- The DEM resolves benches and ramps only where the lidar does; coarse terrain is regenerated by design code and
  labelled as such.
- Educational and planning-grade, not a road-design tool.

## In PitStudio

- **Cases:** [A2](../cases/a2-haul-road-electrification.md) (energy, electrification),
  [E1](../cases/e1-pit-shell-pushbacks.md) (haul distance per lift); travel times for
  [M02](m02-haulage-des.md).
- **Code (planned):** `minephys.haulage` (rimpull/retarder, resistance, cycle time, energy, CO₂, trolley/BEV); A* in
  the same module and in a `web/` worker; terrain from the studio stage `st10_terrain`
  ([studio stages](../pipelines/studio-stages.md)).
- **Status:** not yet implemented — built test-first in the build phase.

† Standard textbook form; the transcription is checked by a worked-example test at specification.

## References

1. Soofastaei et al. (2016). MLP ANN for haul-truck energy consumption: total resistance = rolling + grade; GVW, speed
   and total resistance drive fuel. IJMST 26(2):285–293. https://doi.org/10.1016/j.ijmst.2015.12.015
2. Valenzuela Cruzat, J. & Valenzuela, M. A. (2018). *Modeling and evaluation of benefits of trolley assist system for
   mining trucks*. IEEE Transactions on Industry Applications 54(4):3971–3981. https://doi.org/10.1109/tia.2018.2823261
3. Lindgren, Grauers, Ranggård & Mäki (2022). Drive-cycle simulations of battery-electric large haul trucks with
   electric roads. Energies 15(13) (CC BY). https://doi.org/10.3390/en15134871
4. CIM Magazine — *All in on trolley assist* (830,000 L/yr diesel saved; 79 kg CO₂e per cycle).
   https://magazine.cim.org/en/net-zero-challenge/all-in-on-trolley-assist-en/
5. US EPA — GHG Emission Factors Hub (2025), diesel 10.21 kg CO₂/gal (search excerpt; PDF unreadable).
   https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf
6. Baek, J. & Choi, Y. (2017). Haul-road design by raster least-cost path with Douglas–Peucker simplification.
   Applied Sciences 7. https://doi.org/10.3390/app7070747
7. May, M. A. (2013). *Applications of Queuing Theory for Open-Pit Truck/Shovel Haulage Systems* (Virginia Tech
   thesis) — haulage up to 60 % of operating cost. https://vtechworks.lib.vt.edu/items/fecf61c3-860b-4671-91ed-09549ddad265
