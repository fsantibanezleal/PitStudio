# Mine planning: ultimate pit, pushbacks, cut-off and scheduling

> The ultimate pit is the maximum-weight closure of a block precedence graph, solved exactly as a minimum cut; nested
> shells give pushbacks, Lane's theory gives the cut-off grade, and a time-indexed MILP turns it all into a schedule
> with an NPV. · Part of: [Theory](README.md) · Related:
> [M18 pit optimisation & scheduling](../methods/m18-pit-optimisation-scheduling.md) ·
> [E1 pit shell & pushbacks](../cases/e1-pit-shell-pushbacks.md) · [oreblocks](../frameworks/oreblocks.md) ·
> [MineLib marvin card](../data-contract/dataset-cards/minelib-marvin.md)

## What and why

Strategic open-pit planning answers three questions in order:

1. **Where is the final pit wall?** Which blocks are worth mining at all, given that every ore block drags the waste
   above it along (the slope constraint)?
2. **In what order?** A pit is mined in **pushbacks** (phases), each a nested intermediate pit, so that early years
   carry the best ore per tonne moved.
3. **What is ore?** The **cut-off grade** separates ore sent to the plant from waste sent to the dump, and its optimum
   depends on capacities and on the time value of money.

These decisions fix the haul distances, strip ratios and net present value (NPV) of the life of mine. In PitStudio
they also generate the pit geometry: shells become benches, ramps and pushback variants of the USD scene that every
other case (haulage, dust, slopes, survey) runs on.

All of it is **combinatorial optimisation on the CPU**, not GPU physics. Small instances (up to about 10⁵ blocks)
solve fast enough to run live in the browser; larger ones are baked.

## Block model and block economic value

A block model divides the deposit into a regular 3-D grid of blocks $i = 1 \dots N$. Each block carries a tonnage
$T_i$ (t) and an estimated grade $g_i$ (units of metal per tonne, e.g. t Cu/t). The **block economic value** (BEV)
$v_i$ ($) is the profit of mining the block and sending it to its best destination. In standard notation (UNVERIFIED
notation — pinned at specification) [1]:

$$
v_i = \max\Big( \underbrace{T_i\big[g_i\, r\, (p - s_r) - c_p\big] - T_i c_m}_{\text{processed}},\;\; \underbrace{-T_i c_m}_{\text{waste}} \Big)
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $p$ | metal price | $/unit metal |
| $s_r$ | selling and refining cost | $/unit metal |
| $r$ | metallurgical recovery | – |
| $c_p$ | processing cost | $/t |
| $c_m$ | mining cost | $/t |

Waste blocks have $v_i = -T_i c_m < 0$. The BEV is deterministic here: grade uncertainty, the subject of stochastic
mine planning [13], is out of scope.

## Precedence and slope

A block can only be mined after the blocks above it that the wall angle exposes. With overall slope angle $\alpha$ and
block height $H_b$ (m), a block $k$ levels below a given block must lie within a horizontal radius of
$k H_b / \tan\alpha$ of it; every block in that inverted cone is a **predecessor**. On cubic blocks, linking each
block to the five blocks directly above and edge-adjacent above (a "1:5" pattern) approximates a 45° wall. Each pair
"$i$ requires $j$" is a directed **precedence arc** $i \to j$.

The slope angle itself is a geotechnical input; see [slopes and monitoring](slopes-and-monitoring.md).

## Ultimate pit as maximum closure

A set of blocks $C$ is **closed** if it contains every predecessor of each of its members: it is a minable pit. The
ultimate pit is the closed set of maximum total value (Lerchs & Grossmann 1965 [1]; bibliographic, search excerpt
only):

$$
\max_{x} \sum_{i} v_i x_i \quad \text{s.t.} \quad x_i \le x_j \;\; \forall (i \to j), \qquad x_i \in \{0, 1\}
$$

### Reduction to a minimum cut

The maximum-closure problem reduces to a minimum $s$–$t$ cut (Picard 1976; citation UNVERIFIED — pinned at
specification). Build a network:

- a **source** $s$ with an arc $s \to i$ of capacity $v_i$ for every block with $v_i > 0$ (ore);
- a **sink** $t$ with an arc $i \to t$ of capacity $-v_i$ for every block with $v_i < 0$ (waste);
- every precedence arc $i \to j$ with **infinite** capacity.

Take any cut $(S, \bar S)$ with $s \in S$ and let $C = S \setminus \{s\}$. A finite cut never severs an infinite arc,
so if $i \in C$ then every predecessor $j$ is in $C$ too: **finite cuts are exactly closed sets**. The cut severs the
arcs $s \to i$ of positive blocks left outside $C$ and the arcs $i \to t$ of negative blocks inside $C$:

$$
\mathrm{cap}(S, \bar S) = \sum_{i \notin C,\; v_i > 0} v_i \; + \sum_{i \in C,\; v_i < 0} (-v_i)
= \underbrace{\sum_{v_i > 0} v_i}_{P\ \text{(constant)}} \; - \; \sum_{i \in C} v_i
$$

Minimising the cut capacity therefore maximises the closure value, and

$$
\max_{C\ \text{closed}} \sum_{i \in C} v_i = P - \mathrm{mincut}(s, t)
$$

The optimal pit is the **source side** of the minimum cut.

![Block section with precedence arcs, the s–t network built from it, and the minimum cut that selects the pit](../assets/diagrams/pit-optimisation-mincut.svg)

*A four-block example: three waste blocks above one ore block. The minimum cut severs the three waste arcs, so the pit
is all four blocks.*

**Worked example.** Three waste blocks $a, b, c$ with $v = -1$ each sit on top of one ore block $d$ with $v_d = +5$;
$d$ requires $a$, $b$ and $c$. Then $P = 5$, and the candidate cuts are:

| Cut severs | Capacity | Closed set $C$ | Value $\sum_{C} v_i$ |
|---|---|---|---|
| $s \to d$ | 5 | ∅ | 0 |
| $a \to t,\ b \to t,\ c \to t$ | 3 | $\{a, b, c, d\}$ | 2 |

The minimum cut has capacity 3, so the pit is $\{a, b, c, d\}$ with value $5 - 3 = 2$. If $v_d = +2$ instead, the
minimum cut is $s \to d$ (capacity 2 < 3) and the optimal pit is empty: the ore does not pay for its waste.

### Algorithms and oracles

| Solver | Role | Licence | Note | Source |
|---|---|---|---|---|
| Lerchs–Grossmann graph algorithm | Classical | – | Historical industry standard | [1] |
| Hochbaum's pseudoflow | State of the art in mining software | – | Exact max-flow/min-cut; a parametric variant yields nested pits | [2][16] |
| PyPI `pseudoflow` package | **Rejected** | Non-commercial, not open source | Incompatible with an Apache-2.0 repo | [11] |
| OR-Tools `SimpleMaxFlow` | Oracle | Apache-2.0 | Exposes the source side of the minimum cut | [8] |
| SciPy `maximum_flow` | Oracle | BSD-3 | Dinic / Edmonds–Karp; integer capacities only, so values are scaled to integers | [9] |
| networkx | Oracle | BSD-3 | Pure-Python flow algorithms | [10] |

PitStudio implements its own min-cut (Python and TypeScript) and checks it against the oracles. Because SciPy needs
integer capacities, block values are scaled and rounded to integers for the comparison.

## Nested shells and pushbacks

Scale the revenue term by a **revenue factor** $\lambda$:

$$
v_i(\lambda) = \max\Big( T_i\big[\lambda\, g_i\, r\, (p - s_r) - c_p\big] - T_i c_m,\; -T_i c_m \Big)
$$

As $\lambda$ grows, every $v_i(\lambda)$ is non-decreasing, and the optimal closures are **nested**: the pit for a
smaller $\lambda$ lies inside the pit for a larger one. Hochbaum's parametric pseudoflow computes the whole family in
one pass [2][16]; PitStudio obtains it by repeated solves over a grid of $\lambda$ values.

**Worked example (continued).** Let block $d$ carry revenue $6\lambda$ and cost 1, so $v_d(\lambda) = 6\lambda - 1$,
while $a, b, c$ stay at −1. The full pit pays when $v_d \ge 3$, i.e. $\lambda \ge 2/3$. The shell sequence is ∅ for
$\lambda < 2/3$ and $\{a, b, c, d\}$ from $\lambda = 2/3$ on. On a real block model the same sweep yields dozens of
shells, each a little larger.

**Pushbacks** group consecutive shells into mining phases. A good phase has enough ore to feed the plant for its
duration, a wall position that respects the minimum mining width, and a high value per tonne moved early on.

### From shells to a minable design

A shell is a jagged block surface; the design turns it into benches and a ramp:

1. Contour the shell at bench elevations to get **crest** polygons.
2. Offset each crest inward by $H/\tan\beta_f$ (bench height $H$, face angle $\beta_f$) to get the **toe**, then by
   the berm width to get the next crest.
3. Wind a **ramp** along the crests at grade $g_r$: $z(s) = z_{\mathrm{top}} - g_r s$ along arc length $s$, so each
   bench of height $H$ consumes $H/g_r$ metres of ramp.
4. Place **safety berms (windrows)** on ramp edges at least as high as the mid-axle height of the largest haul unit,
   the US regulatory floor [14].

| Design parameter | Value used for illustration | Status | Source |
|---|---|---|---|
| Bench height | 12–15 m | secondary source | [15] |
| Bench width | 20–40 m | secondary source | [15] |
| Ramp grade | ≈ 8–10 % | customary value (UNVERIFIED — pinned at specification) | – |
| Berm (windrow) height | ≥ mid-axle height of the largest haul unit | regulatory floor (US) | [14] |

**Worked example (ramp length).** At $H = 15$ m and $g_r = 10$ %, each bench needs $15/0.10 = 150$ m of ramp. A pit
bottom ten benches down is 1.5 km of ramp from the rim, one way. This is the per-lift haul distance that grows with
every pushback and feeds the E1 KPI "haul km per lift" and the haulage cases ([haulage theory](haulage.md)).

**Worked example (inter-ramp angle; illustrative inputs).** With $H = 15$ m, face angle 70° and 8 m berms, each bench
advances $15/\tan 70° + 8 = 5.46 + 8 = 13.46$ m horizontally, so the inter-ramp slope is
$\arctan(15/13.46) \approx 48°$. A geotechnical limit lower than that forces wider berms or flatter faces.

## Strip ratio

The **strip ratio** of a pit or phase is the waste moved per tonne of ore:

$$
\mathrm{SR} = \frac{\sum_{i \in C,\ \text{waste}} T_i}{\sum_{i \in C,\ \text{ore}} T_i} \quad (\mathrm{t/t})
$$

In the worked example with 1 kt blocks, the pit $\{a, b, c, d\}$ has SR = 3 kt / 1 kt = 3. The **incremental** strip
ratio of a pushback (the ratio of the ring between two shells) is what a mine planner watches: the outer shells carry
the highest incremental ratios, which is why they are worth the least.

## Cut-off grade

### Break-even cut-off

For a block that is mined anyway (its mining cost is sunk), processing pays when its processed value exceeds the waste
value, i.e. when $g_i\, r\, (p - s_r) \ge c_p$. That gives the break-even cut-off, a direct consequence of the BEV
definition above:

$$
g_{\mathrm{be}} = \frac{c_p}{r\, (p - s_r)}
$$

**Worked example (illustrative inputs).** With $c_p = 10$ $/t, $r = 0.85$ and $p - s_r = 8{,}000$ $/t Cu,
$g_{\mathrm{be}} = 10 / (0.85 \times 8{,}000) = 1.47 \times 10^{-3}$ t/t, i.e. 0.147 % Cu.

### Lane's theory

Lane (1964) showed that the optimum cut-off is not the break-even value when capacities bind: a lower-value tonne
occupies capacity that a higher-value tonne could use, and delaying the remaining reserve costs money [7]. In Lane's
notation, with processing cost $h$ ($/t), price $s$ and selling cost $r_s$ ($/unit), recovery $y$, fixed costs $f$
($/yr) and the opportunity cost $F$ ($/yr) of delaying the remaining reserve, the three **limiting cut-offs** are
(UNVERIFIED transcription — pinned at specification) [7]:

$$
g_m = \frac{h}{(s - r_s)\, y} \quad \text{(mine-limited)}
$$

$$
g_h = \frac{h + (f + F)/H_c}{(s - r_s)\, y} \quad \text{(plant-limited, plant capacity } H_c \text{ in t/yr)}
$$

$$
g_k = \frac{h}{\big(s - r_s - (f + F)/K_c\big)\, y} \quad \text{(market-limited, market capacity } K_c \text{ in units/yr)}
$$

The mine-limited cut-off equals the break-even value: when only the mine is the bottleneck, every tonne that pays its
processing cost is ore. The plant- and market-limited forms add the time cost $(f + F)$ spread over the binding
capacity. The optimum is one of the three, or a **balancing** cut-off where two capacities bind at once. Because $F$
depends on the NPV of what remains, the calculation iterates with the schedule.

## Production scheduling as a MILP

Given the shells and a cut-off policy, the schedule decides **when** each block is mined. A time-indexed binary
programme with $x_{i,t} = 1$ if block $i$ is mined in period $t$, discount rate $\delta$ per period, mining capacity
$M_t$ (t) and processing capacity $P_t$ (t) is [3][4]:

$$
\max \sum_{t=1}^{T} \sum_{i} \frac{v_i}{(1 + \delta)^{t}}\, x_{i,t}
$$

$$
\text{s.t.}\quad \sum_{t} x_{i,t} \le 1 \;\;\forall i, \qquad
x_{i,t} \le \sum_{\tau \le t} x_{j,\tau} \;\;\forall (i \to j),\ \forall t
$$

$$
\sum_{i} T_i\, x_{i,t} \le M_t, \qquad \sum_{i\ \text{ore}} T_i\, x_{i,t} \le P_t \;\;\forall t, \qquad x_{i,t} \in \{0, 1\}
$$

The size explains the practice: $10^5$ blocks over 20 periods is $2 \times 10^6$ binary variables. Exact MILP solves are
therefore reserved for small instances, and larger ones use aggregation (blocks into benches of a pushback) or
heuristics. PitStudio solves the small MILPs with HiGHS [12] and bakes the schedules.

**NPV** of a schedule with yearly cash flow $\mathrm{CF}_t$ ($) is

$$
\mathrm{NPV} = \sum_{t=1}^{T} \frac{\mathrm{CF}_t}{(1+\delta)^t}
$$

## MineLib: reference instances

MineLib (Espinoza, Goycoolea, Moreno & Newman 2013) publishes standard instances and file formats for three problems
[3]: the ultimate pit (UPIT), the constrained pit limit problem (CPIT) and precedence-constrained production
scheduling (PCPSP). The publisher states a **CC BY-SA 3.0** licence [4].

| Instance | Deposit | Blocks | Block size | Notes | Source |
|---|---|---|---|---|---|
| KD | Arizona copper | – | 20 × 20 × 15 m | 2 destinations; published UPIT/CPIT/PCPSP optima | [5] |
| McLaughlin | California gold | 2,140,342 | 25 × 25 × 20 ft | `.prec` file zipped | [6] |
| Marvin | – | (UNVERIFIED) | – | PitStudio's optional instance | [4] |

Published optimal or best-known values make MineLib an **exact** check for a solver [3]. Because of the share-alike
licence, PitStudio treats MineLib as `derived-only`: raw instances are fetched, never re-hosted, and every derived
shell or schedule carries CC BY-SA 3.0 attribution in a separate layer.

## Assumptions and limits

- **Educational, not design software.** Shells, pushbacks and schedules illustrate the methods on a synthetic or
  public deposit; they are not a reserve statement and carry no economic advice.
- **Deterministic grades.** No geological uncertainty; stochastic planning [13] is out of scope.
- **Fixed slope angle per run.** The precedence cone uses one overall angle; sector-specific angles are a recipe input.
- **Unverified forms.** The BEV notation, the Lerchs–Grossmann and Picard attributions and Lane's formulas are tagged
  UNVERIFIED until the specification pins them to primary texts with worked examples.
- **Scale.** The live min-cut targets ≤ 10⁵ blocks; larger models are baked. MILP schedules are solved only for small
  instances or aggregated models.
- **Simulation-grade twin, not a live digital twin.** No survey or production feed updates the plan.

## In PitStudio

| Item | Where | Status |
|---|---|---|
| Case | [E1 pit shell & pushbacks → LOM haul distance](../cases/e1-pit-shell-pushbacks.md): KPIs NPV, strip ratio, haul km per lift | Not yet run |
| Methods | [M18 min-cut ultimate pit + nested shells + MILP scheduling](../methods/m18-pit-optimisation-scheduling.md); [M6 haul-road energy routing](../methods/m06-haul-road-energy-routing.md) on the designed ramps | Specified in the plan |
| Deposits | Synthetic deposits from [`oreblocks`](../frameworks/oreblocks.md) (default); MineLib marvin optional, CC BY-SA, derived-only ([card](../data-contract/dataset-cards/minelib-marvin.md)) | Data-and-models phase |
| Knowledge code | [`minephys`](../frameworks/minephys.md) module `planning`: Lane cut-offs and a small min-cut | Build phase |
| Pit design | Studio stage `st20_pit_design`: ultimate pit + nested shells → benches, berms, ramp → pushback variants of the USD `design` layer | Build phase |
| Oracles | OR-Tools 9.15.6755 (`studio/uv.lock`) and networkx 3.7 (`pipeline/uv.lock`) | Locked |
| Scheduling | HiGHS MILP, precomputed and baked | Build phase |
| Web | Live min-cut in a TypeScript worker for ≤ 10⁵ blocks (gate estimate: < 1 s, measured in the data-and-models phase); baked shells otherwise | Build phase |
| Review | Pushback review and measurement in USD Composer / Explorer | Optional, data-and-models phase |

**Results: Not yet run — produced in the data-and-models phase.** What will be reported:

- Shell family against the revenue factor, the chosen pushbacks, and per-pushback strip ratio and haul km per lift.
- NPV of the baked schedule, with the cut-off policy used.
- Oracle agreement of the own min-cut (closure value on integer-scaled instances) and, for the optional MineLib
  instance, the gap to its published value. The tolerances are fixed in the specification.

## References

1. Lerchs, Grossmann (1965). Optimum design of open-pit mines. *Trans. CIM* 58(633):47–54. Bibliographic
   data from a search excerpt only; context page: https://www.researchgate.net/publication/280082017_Pseudoflow_New_Life_for_Lerchs-Grossmann_Pit_Optimisation
2. Hochbaum (2008). The Pseudoflow Algorithm: a new algorithm for the maximum-flow problem. *Operations
   Research* 56(4):992–1009. DOI: 10.1287/opre.1080.0524
3. Espinoza, Goycoolea, Moreno, Newman (2013). MineLib: a library of open pit mining problems. *Annals
   of Operations Research* 206(1):93–114. DOI: 10.1007/s10479-012-1258-3
4. MineLib v1 (licence statement: CC BY-SA 3.0 Unported). URL: https://minelib.org/v1/
5. MineLib instance KD. URL: https://minelib.org/v1/kd.xhtml
6. MineLib instance McLaughlin. URL: https://minelib.org/v1/mclaughlin.xhtml
7. Lane (1964). Choosing the optimum cut-off grade. *Colorado School of Mines Quarterly* 59:811–829.
   Bibliographic data from a search excerpt only; reference-list page:
   https://www.scirp.org/reference/referencespapers?referenceid=1929843
8. Google. OR-Tools maximum flow (`SimpleMaxFlow`, min-cut accessors). URL:
   https://developers.google.com/optimization/flow/maxflow
9. SciPy. `scipy.sparse.csgraph.maximum_flow`. URL:
   https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.maximum_flow.html
10. networkx on PyPI (BSD-3). URL: https://pypi.org/pypi/networkx/json
11. `pseudoflow` on PyPI ("Non-commercial license. Not an open-source license."). URL: https://pypi.org/pypi/pseudoflow/json
12. HiGHS Python bindings `highspy` on PyPI (MIT). URL: https://pypi.org/pypi/highspy/json
13. Dimitrakopoulos (2011). Stochastic optimization for strategic mine planning: a decade of developments. *Journal
    of Mining Science* 47. DOI: 10.1134/S1062739147020018
14. 30 CFR § 56.9300 (berms or guardrails; Cornell LII). URL: https://www.law.cornell.edu/cfr/text/30/56.9300
15. Wikipedia. Open-pit mining (secondary source for bench dimensions). URL: https://en.wikipedia.org/wiki/Open-pit_mining
16. Hochbaum group. Pseudoflow parametric min-cut implementation (search excerpt only). URL:
    https://github.com/hochbaumGroup/pseudoflow-parametric-cut

Classical source cited by name only, **not yet verified** against its primary text (pinned at specification): Picard
(1976) for the reduction of maximum closure to a minimum cut.
