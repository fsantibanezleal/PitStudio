# Haulage

> The physics of a haul truck on a road profile and the queueing of a truck fleet around shovels and dumps, from
> rimpull curves to mean-value analysis. · Part of: [Theory](README.md) · Related:
> [Loading and terramechanics](loading-and-terramechanics.md), [M1 match factor and queueing](../methods/m01-match-factor-queueing.md),
> [M2 haulage DES](../methods/m02-haulage-des.md), [M6 haul-road energy routing](../methods/m06-haul-road-energy-routing.md)

## What and why

Haulage is the largest single in-pit cost: a queueing study of open-pit truck–shovel systems states that haulage can
account for up to 60 % of total operating cost [16]. It is also dangerous: in 2025, powered haulage caused 13 of the
33 US mining fatalities (39 %) [17]. Diesel materials handling is about 17 % of mining energy [20].

Two scales matter, and PitStudio models both:

- **One truck on one road** (seconds to minutes). Longitudinal dynamics: resistances, rimpull, retarding, speed,
  travel time, energy, fuel and CO₂. This is a 1-D ordinary differential equation along the road profile.
- **A fleet in a shift** (hours). Trucks cycle between loaders and dumps and wait for each other. The structure is a
  *closed* queueing network: a fixed number of trucks circulates. Analytical models (match factor, finite-source
  queues, mean-value analysis) bound it; discrete-event simulation (DES) handles dispatch rules and everything that
  breaks the analytical assumptions.

The single-truck physics feeds the fleet model: each truck's travel time is the physics model plus noise, not an
arbitrary distribution.

## 1. Resistances

The industry decomposition of the force a truck must overcome is **total resistance = rolling resistance + grade
resistance**, each expressed as a percentage of gross vehicle weight. Fuel and energy models are built on gross
vehicle weight, speed and total resistance [1].

$$
TR = RR + GR, \qquad GR = 100\,\sin\theta \approx 100\,\tan\theta
$$

$$
F_{\text{req}} = m_{\text{GVW}}\, g\, \frac{TR}{100} + m_{\text{eff}}\,\frac{dv}{dt} + \tfrac12\,\rho_a\, C_D\, A\, v^2
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $TR$, $RR$, $GR$ | total, rolling and grade resistance | % of GVW |
| $\theta$ | road inclination | rad |
| $m_{\text{GVW}}$ | gross vehicle mass (empty + payload) | kg |
| $m_{\text{eff}}$ | effective mass, including rotating inertia | kg |
| $g$ | gravitational acceleration, 9.81 | m/s² |
| $\rho_a$, $C_D$, $A$ | air density, drag coefficient, frontal area | kg/m³, –, m² |
| $v$ | speed | m/s |

Grade is quoted as rise over run (a 10 % grade has $\tan\theta = 0.1$). The small-angle form is close: at 10 %,
$\sin\theta = 0.0995$, a 0.5 % relative difference (arithmetic). The aerodynamic term is small at haul speeds and is
kept only for completeness.

**Rolling resistance** depends on the road surface and tyre penetration. OEM guidance quotes about 1.5 % for a hard,
smooth surface, about 3 % for a firm maintained surface, about 8 % for rutted soft dirt with about 100 mm penetration,
about 10 % for loose gravel with 150 mm or more, and roughly +0.6 % per cm of penetration [2] (UNVERIFIED — pinned at
specification). Road condition has a first-order effect: a DES study of a 5 km ramp at 9.5 % grade with ten 300 t
trucks reports large productivity and fuel deviations when road deterioration is ignored [3].

## 2. Rimpull and retarder curves

![Forces on a haul truck on a grade and a rimpull curve reading](../assets/diagrams/haulage-forces-rimpull.svg)

*Left: forces on a loaded truck climbing a ramp. Right: an illustrative rimpull curve; each crossing with a resistance
line is a steady speed.*

**Uphill and on the level**, the tractive force available at the wheels (rimpull) is limited by traction at low speed
and by power at higher speed:

$$
F_{\text{rim}}(v) \le \min\!\Big(\mu_t\, W_{\text{drive}},\ \frac{\eta_{\text{dt}}\, P_{\text{eng}}}{v}\Big)
$$

with $\mu_t$ the tyre–road traction coefficient (–), $W_{\text{drive}}$ the load on the driven wheels (N),
$\eta_{\text{dt}}$ the drivetrain efficiency (–) and $P_{\text{eng}}$ the engine power (W). The steady speed on a
segment solves $F_{\text{rim}}(v) = F_{\text{req}}(v)$ with $dv/dt = 0$. In the power-limited regime, with drag
neglected:

$$
v_{\text{ss}} \approx \frac{\eta_{\text{dt}}\, P_{\text{eng}}}{m_{\text{GVW}}\, g\, TR/100}
$$

OEM rimpull–speed–gradeability charts tabulate exactly this intersection, but they are proprietary and not open
data; PitStudio uses a **generic, documented truck parameter set** instead. The same curve gives **gradeability**, the largest total
resistance the truck can hold at speed $v$: $TR_{\max}(v) = 100\,F_{\text{rim}}(v)/(m_{\text{GVW}}\,g)$.

**Downhill**, the effective grade is $GR - RR$, and the retarder (or service brakes) must dissipate the power the
road delivers:

$$
P_{\text{ret}} = m_{\text{GVW}}\, g\, \frac{GR - RR}{100}\, v \;\le\; P_{\text{ret,max}}(v)
$$

so the safe descent speed is set by the retarder envelope, not by the engine. On trolley-assist or battery-electric
trucks this is the energy that regeneration can recover [6][7].

**Worked example 1** (illustrative inputs: 400 t GVW, 1.8 MW at the wheels, traction limit 900 kN, 10 % grade, 2 %
rolling resistance):

- Total resistance: $F = 400{,}000 \times 9.81 \times 0.12 = 470.9$ kN, below the traction limit.
- Steady speed: $v = 1.8\times10^6 / 470{,}880 = 3.82$ m/s = 13.8 km/h (the accent crossing in the figure).
- At $TR$ = 4, 8 and 16 % the same truck holds 41.3, 20.6 and 10.3 km/h.
- Loaded descent of the same ramp with an illustrative 2.5 MW retarder: net grade $10 - 2 = 8$ %, so
  $v_{\max} = 2.5\times10^6 / (400{,}000 \times 9.81 \times 0.08) = 7.96$ m/s = 28.7 km/h. Empty (180 t), the limit
  rises to 63.7 km/h and the site speed limit binds instead.

## 3. Travel-time integration

Along a road profile $s \in [0, L]$ split into segments with grade, rolling resistance and speed limit, the truck obeys

$$
m_{\text{eff}}\,\frac{dv}{dt} = F_{\text{rim}}(v) - m_{\text{GVW}}\, g\, \frac{TR(s)}{100} - \tfrac12 \rho_a C_D A v^2,
\qquad \frac{ds}{dt} = v, \qquad v \le v_{\text{lim}}(s)
$$

and the travel time is $t = \int_0^L ds / v(s)$. Two levels of fidelity are standard:

1. **Steady-state per segment.** For long segments, $t_k = L_k / \min(v_{\text{ss},k}, v_{\text{lim},k})$. This is
   what an analytical cycle-time calculator uses.
2. **Explicit integration.** For short segments, curves and grade changes, step the ODE (for example
   $v_{n+1} = v_n + \Delta t\,(F_{\text{rim}} - F_{\text{res}})/m_{\text{eff}}$, $s_{n+1} = s_n + v_n \Delta t$), clamp
   to the speed limit and to the retarder envelope on descents, and accumulate time and energy.

By definition, the truck cycle time is the sum of its parts:

$$
T_c = t_{\text{spot,L}} + t_{\text{load}} + t_{\text{haul}} + t_{\text{spot,D}} + t_{\text{dump}} + t_{\text{return}}
+ t_{\text{queue,L}} + t_{\text{queue,D}}
$$

Loading time and payload come from the loading page ([Loading and terramechanics](loading-and-terramechanics.md)).
The queue terms are what the fleet models of §6–§8 add. *Worked example 1, continued:* a 3 km climb at a steady
3.82 m/s takes 785 s = 13.1 min (a vertical rise of 298.5 m).

## 4. Energy, fuel and CO₂ per tonne-kilometre

Energy at the wheels over a cycle is $E_{\text{wheel}} = \int F_{\text{req}}\, v\, dt$, and the energy drawn from the
tank or the grid is $E = E_{\text{wheel}}/\eta$. A physics bound is useful as a check: lifting 1 t through 100 m needs
$1000 \times 9.81 \times 100$ J = 0.2725 kWh at the wheels (arithmetic).

The engine-load model writes the fuel rate as linear in the engine load factor [4]:

$$
FC\ [\text{L/h}] = \frac{SFC \cdot P \cdot LF}{\rho_{\text{fuel}}}
$$

with $SFC$ the specific fuel consumption (kg/kWh), $P$ the rated power (kW), $LF$ the load factor (–) and
$\rho_{\text{fuel}}$ the fuel density (kg/L). A generic $SFC$ constant is UNVERIFIED — pinned at specification.

**CO₂.** The US EPA emission factor for diesel fuel is **10.21 kg CO₂ per US gallon** [5], i.e.
$10.21 / 3.785 = 2.70$ kg CO₂ per litre (arithmetic). This is combustion CO₂ only (Table 2 of [5]); the CH₄ and N₂O factors
of non-road vehicles are in a separate table, Table 5 of the same document (g per US gallon) [5].

**Worked example 2** (worked example 1 continued; illustrative tank-to-wheel efficiency 0.35 and diesel energy
36 MJ/L):

| Quantity | Value | Basis |
|---|---|---|
| Energy at the wheels, 3 km climb | 392.4 kWh | $470.9\ \text{kN} \times 3000\ \text{m}$ |
| Per tonne of payload (220 t) | 1.78 kWh/t | payload basis |
| Per payload tonne-kilometre | 0.595 kWh/(t·km) | along-road distance |
| Fuel | 112 L | $E/(0.35 \times 36\ \text{MJ/L})$ |
| CO₂ | 302 kg (1.37 kg/t payload) | 2.70 kg/L [5] |

Every energy or CO₂ number in PitStudio states its basis (payload or gross mass, along-road or horizontal distance).
Fleet-level levers are large: dispatch optimisation studies report fuel reductions of a few percent (8.82 % and
4.49 % in two scenarios) [18], and controlling payload variance can cut haul-truck fuel by up to 35 % [19].

## 5. Trolley assist and battery-electric haulage

On a **trolley** segment the drive power comes from an overhead line, so the ramp speed is set by the line and motor
power rather than the engine: $v_{\text{trolley}} \approx \eta\,P_{\text{line}} / (m_{\text{GVW}}\,g\,TR/100)$ with
the same structure as §2. On a **descent**, an electric drivetrain can recover part of the power the retarder would
otherwise burn:

$$
E_{\text{regen}} \le \eta_{\text{regen}}\; m_{\text{GVW}}\, g\, \frac{GR - RR}{100}\, L
$$

*Worked example 1, descent:* 400 t over 3 km at 8 % net grade dissipates 261.6 kWh at the wheels, the upper bound on
what regeneration could return before losses.

Published evidence:

- An electro-mechanical trolley-assist model on real copper-mine coordinates reports a 44 % increase in uphill speed,
  16 % shorter cycle travel time and 85 % fuel saving over each up–down cycle [6].
- Trolley assist at a Swedish copper mine saved 830,000 L of diesel per year; a Canadian pilot showed 79 kg CO₂e saved
  per truck cycle on the trolley section and more than twice the ramp speed; one operator reports an 80 % cut in
  transport greenhouse gas along trolley routes [8].
- Drive-cycle simulations of large battery-electric haul trucks charged from trolley lines in an open-pit copper mine
  (five drive cycles, validated model) find battery-electric operation feasible and cheaper than diesel-electric under
  the stated assumptions [7].

Grid CO₂ intensity is site- and region-specific. PitStudio takes it as an input and ships no default.

## 6. Match factor

The match factor compares the truck arrival rate with the loader service rate [9]:

$$
MF = \frac{N_T\, t_L}{N_L\, T_c^{\ast}}
$$

with $N_T$ and $N_L$ the truck and loader counts, $t_L$ the time to load one truck (min) and $T_c^{\ast}$ the truck
cycle time excluding waiting (min). $MF < 1$ means the loaders wait (under-trucked), $MF > 1$ means the trucks queue
(over-trucked), and $MF = 1$ is the deterministic balance. Burt and Caccetta extend the ratio to heterogeneous truck
and loader fleets [9].

## 7. Queueing models

![Truck–shovel system as a closed queueing network](../assets/diagrams/truck-shovel-queue.svg)

*A fixed truck population circulates through queueing stations (loader, dump) and delay stations (haul and return
roads); the chart compares exact mean-value analysis with the deterministic bound.*

**Open M/M/c (a loader bank fed by Poisson arrivals)** [11]. With arrival rate $\lambda$ (trucks/h), service rate
$\mu$ per loader (trucks/h), $c$ loaders, offered load $a = \lambda/\mu$ and utilisation $\rho = a/c < 1$:

$$
C(c,a) = \frac{\dfrac{a^c}{c!}\dfrac{1}{1-\rho}}{\displaystyle\sum_{k=0}^{c-1}\frac{a^k}{k!} + \frac{a^c}{c!}\frac{1}{1-\rho}},
\qquad W_q = \frac{C(c,a)}{c\mu - \lambda}, \qquad L_q = \lambda W_q
$$

*Illustrative:* $c = 2$, $\lambda = 24$ /h, $\mu = 15$ /h → $a = 1.6$, $\rho = 0.8$, $C = 0.711$, $W_q = 7.1$ min,
$L_q = 2.84$ trucks. The open model assumes an infinite truck population, which is the wrong structure for a pit: it
is a large-fleet approximation only.

**Closed finite-source queue (one loader, $N$ trucks).** Carmichael models shovel–truck operations as finite-source
or cyclic queues: shovel, loaded haul, dump, empty return [10]. With exponential times this is the machine-repairman
model M/M/1//N, with $1/\lambda$ the mean time a truck spends away from the shovel and $1/\mu$ the mean loading time:

$$
\pi_0 = \Bigg[\sum_{n=0}^{N} \frac{N!}{(N-n)!}\Big(\frac{\lambda}{\mu}\Big)^{n}\Bigg]^{-1}, \qquad
U_{\text{shovel}} = 1 - \pi_0, \qquad X = \mu\,(1 - \pi_0)
$$

(standard result; transcription UNVERIFIED — pinned at specification). Chance-constrained truck allocation has been
built on exactly these shovel idle probabilities [13].

**Mean-value analysis (MVA) for several stations.** For product-form closed networks (shovels, crusher, dumps as
queueing stations; roads as delay stations), exact MVA iterates over the population $n = 1 \dots N$ [12]:

$$
W_k(n) = \frac{1 + L_k(n-1)}{\mu_k}, \qquad X(n) = \frac{n}{\sum_k v_k\, W_k(n)}, \qquad L_k(n) = v_k\, X(n)\, W_k(n)
$$

with $v_k$ the visit ratio of station $k$, $W_k$ its residence time, $L_k$ its mean queue length and $X$ the system
throughput. Delay stations take $W_k = 1/\mu_k$ (no queueing).

**Worked example 3** (illustrative: one shovel, 4 min mean load, 20 min mean travel away from the shovel, exponential
times). The machine-repairman formula and MVA give the same throughput, which is the cross-check PitStudio's tests
will use:

| Trucks $N$ | $MF$ | Exact $X$ (trucks/h) | Deterministic $\min(N/T_c^{\ast}, \mu)$ (trucks/h) |
|---|---|---|---|
| 1 | 0.17 | 2.50 | 2.5 |
| 3 | 0.50 | 7.06 | 7.5 |
| 5 | 0.83 | 10.73 | 12.5 |
| 6 | 1.00 | 12.12 | 15.0 |
| 8 | 1.33 | 13.95 | 15.0 |

For $N = 5$: the sum in $\pi_0$ is 3.5104, so $\pi_0 = 0.285$, shovel utilisation 0.715 and $X = 15 \times 0.715 =
10.73$ trucks/h. At $MF = 1$ the fleet delivers 12.1 instead of 15 trucks/h: a 19 % loss that comes only from random
cycle times (bunching). A deterministic match-factor calculation hides it.

## 8. Discrete-event simulation

Exponential times are violated in practice. Loading is closer to Erlang or lognormal, haul times follow
deterministic profile physics, and bunching, dispatch rules, breakdowns and road deterioration break product form. DES
is the industry-standard validator [3][14]. The DES state is an event list (arrive at loader, start load, end load,
arrive at dump, end dump, arrive back) plus the truck, loader and dump resources:

1. pop the earliest event and advance the clock;
2. update the resource (start service if idle, else enqueue);
3. sample the next event time: service time from its distribution, travel time from the §3 physics plus noise;
4. at each truck release, call the dispatcher (fixed allocation, nearest, shortest queue, SPTF, LP-guided or a learned
   policy) to choose the next destination.

Two checks keep a DES honest. In the exponential, single-route case it must reproduce the MVA numbers of §7. And it
must be reproducible: same seed, same trace. PitStudio's haulage engine is
[minehaulsim](../frameworks/minehaulsim.md), a deterministic DES with an exact-trace TypeScript twin; SimPy (4.1.2,
MIT) [15] serves only as a cross-check oracle.

## Assumptions and limits

- **1-D longitudinal physics.** Lateral dynamics, curve superelevation and tyre slip are not in these equations.
- **Generic truck, not an OEM truck.** Rimpull, retarder and efficiency curves are parametric and documented as
  generic; OEM charts are proprietary and not used.
- **Unverified constants.** The rolling-resistance guidance values and any generic $SFC$ are UNVERIFIED until pinned
  at specification; the knowledge tables flag them in the UI.
- **Product form.** M/M/c, machine-repairman and MVA are exact only for exponential service and simple routing. Use
  them as bounds and as DES test oracles, not as forecasts.
- **Simulation-grade twin.** There is no live telemetry feed; PitStudio is a simulation-grade twin, not a live digital
  twin of an operation, and its numbers are educational, not design values.
- **CO₂ scope.** The diesel factor covers combustion CO₂ (tank-to-wheel); upstream fuel emissions and grid factors
  are explicit inputs.

## In PitStudio

| Where | What | Lane |
|---|---|---|
| `minephys.haulage` | rimpull/retarder, resistance, cycle time, energy, CO₂, trolley/BEV, match factor, M/M/c, MVA | live (TypeScript port + Pyodide button) |
| [M1](../methods/m01-match-factor-queueing.md) | match factor + finite-source queue / MVA | live |
| [M2](../methods/m02-haulage-des.md) | DES with classical dispatchers (`minehaulsim` reference, TS twin, SimPy oracle) | live + precompute |
| [M6](../methods/m06-haul-road-energy-routing.md) | haul-road energy and grade-constrained routing (diesel, trolley, BEV) on the terrain | live |
| Cases | [A1](../cases/a1-truck-shovel-dispatch.md) dispatch and fleet sizing, [A2](../cases/a2-haul-road-electrification.md) electrification, [A3](../cases/a3-loading-payload-variance.md) payload variance; traffic for [C3](../cases/c3-dust.md) | — |

Cited constants live in the `minephys` knowledge tables with their verification status; see
[Knowledge](../knowledge/README.md).

**Status: Not yet run** — produced in the data-and-models phase. The analytical models are written test-first from
worked examples; the first numbers reported will be:

- the DES-versus-MVA parity in the exponential case (tolerance pinned at specification);
- A1: throughput, queue time, match factor and cost per tonne for classical dispatchers, and the learned policies
  against SPTF and LP over at least 30 paired seeds, called better only if the paired 95 % confidence interval of the
  difference excludes 0;
- A2: L/t·km, kWh/t and CO₂e/t for diesel, trolley and battery-electric variants on the real pit profile.

## References

1. Soofastaei, Aminossadati, Arefi, Kizil (2016). Development of a multi-layer perceptron
   artificial neural network model to determine haul trucks energy consumption. *Int. J. Mining Sci. Technol.* 26(2),
   285–293. https://doi.org/10.1016/j.ijmst.2015.12.015
2. Caterpillar. Rolling resistance factors (OEM article). https://www.cat.com/en_US/articles/ci-articles/rolling-resistance-factors.html
   (UNVERIFIED — source unreachable when this page was written)
3. Meneses, Sepúlveda (2023). Modeling productivity reduction and fuel consumption in open-pit mining trucks by
   considering the temporary deterioration of mining roads through discrete-event simulation. *Mining* 3(1), 96–105.
   https://doi.org/10.3390/mining3010006
4. Kecojevic, Komljenovic (2010). Haul truck fuel consumption and CO₂ emission under various engine load
   conditions. *Mining Engineering* 62(12), 44–48.
   https://www.researchgate.net/publication/261214668_Haul_truck_fuel_consumption_and_CO2_emission_under_various_engine_load_conditions
5. US EPA (2025). GHG Emission Factors Hub, Table 2 (mobile combustion: diesel fuel 10.21 kg CO₂/gal) and Table 5
   (mobile combustion CH₄ and N₂O for non-road vehicles).
   https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf
6. Valenzuela Cruzat, Valenzuela (2018). Modeling and evaluation of benefits of trolley assist system for
   mining trucks. *IEEE Trans. Ind. Appl.* 54(4), 3971–3981. https://doi.org/10.1109/TIA.2018.2823261
7. Lindgren, Grauers, Ranggård, Mäki (2022). Drive-cycle simulations of battery-electric large haul
   trucks for open-pit mining with electric roads. *Energies* 15(13), 4871. https://doi.org/10.3390/en15134871
8. CIM Magazine. All in on trolley assist. https://magazine.cim.org/en/net-zero-challenge/all-in-on-trolley-assist-en/
9. Burt, Caccetta (2007). Match factor for heterogeneous truck and loader fleets. *Int. J. Mining, Reclam.
   Environ.* 21(4), 262–270. https://doi.org/10.1080/17480930701388606
10. Carmichael (1986). Shovel–truck queues: a reconciliation of theory and practice. *Constr. Manag. Econ.*
    4(2), 161–177. https://doi.org/10.1080/01446198600000013
11. M/M/c queue (Erlang-C and waiting-time formulas). https://en.wikipedia.org/wiki/M/M/c_queue
12. Mean value analysis (closed-network recursion). https://en.wikipedia.org/wiki/Mean_value_analysis
13. Ta, Kresta, Forbes, Marquez (2005). A stochastic optimization approach to mine truck
    allocation. *Int. J. Surface Mining, Reclam. Environ.* 19(3), 162–175. https://doi.org/10.1080/13895260500128914
14. Upadhyay, Askari-Nasab (2018). Simulation and optimization approach for uncertainty-based short-term
    planning in open pit mines. *Int. J. Mining Sci. Technol.* 28(2), 153–166. https://doi.org/10.1016/j.ijmst.2017.12.003
15. SimPy 4.1.2 (MIT), Python Package Index. https://pypi.org/project/simpy/
16. May (2013). *Applications of Queuing Theory for Open-Pit Truck/Shovel Haulage Systems.* Virginia Tech.
    https://vtechworks.lib.vt.edu/items/fecf61c3-860b-4671-91ed-09549ddad265
17. US MSHA. Powered haulage safety (2025 statistics).
    https://www.msha.gov/safety-and-health/safety-and-health-initiatives/powered-haulage-safety
18. Bajany, Xia, Zhang (2017). A MILP model for truck-shovel scheduling to minimize fuel consumption.
    *Energy Procedia* 105, 2739–2745. https://doi.org/10.1016/j.egypro.2017.03.925
19. International Mining (2016). Mining3 project looks at effect of payload variance on haul truck fuel consumption.
    https://im-mining.com/2016/12/07/mining3-project-looks-effect-payload-variance-haul-truck-fuel-consumption/
20. Soofastaei, Fouladgar (2022). Improve energy efficiency in surface mines using artificial intelligence.
    In *Alternative Energies and Efficiency Evaluation*, IntechOpen. https://doi.org/10.5772/intechopen.101493
