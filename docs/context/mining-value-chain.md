# The mining value chain

> How rock becomes concentrate in an open-pit operation, what moves from one stage to the next, where cost and energy
> concentrate, and where PitStudio's five case categories sit on the chain. · Part of: [context](README.md) · Related:
> [open-pit operations](open-pit-operations.md) · [scenario impact](scenario-impact.md) ·
> [comminution theory](../theory/comminution.md) · [case catalogue](../cases/README.md)

## What and why

A mine is a chain of physical transformations. Each stage receives material in a state set by the stage before it and
passes on material whose state limits the stage after it. Blasting sets the size distribution that the shovel digs and
the crusher receives. The haul cycle sets how many tonnes per hour reach the crusher. The crusher and the mills turn
size into energy cost. The concentrator leaves tailings behind.

PitStudio models the chain from a block model to tailings. It does not model exploration geology, smelting or refining.
The point of this page is to show **which links carry the cost, energy and risk**, because those links decide which
cases are worth simulating (see [scenario impact](scenario-impact.md)).

## The chain, stage by stage

![Open-pit value chain with the five case categories](../assets/diagrams/mining-value-chain.svg)

*Six stages, the `minephys` module that models each one, the material that moves along the chain, and the five case
categories placed on the stages they cover.*

| Stage | What happens | Key quantities (units) | Theory | Cases |
|---|---|---|---|---|
| Explore and plan | A block model of grades and tonnages is turned into an ultimate pit, nested shells, pushbacks and a life-of-mine schedule | block value (USD), NPV (USD), strip ratio (t/t) | [planning](../theory/planning.md) | E1 |
| Drill and blast | Holes are drilled on a burden × spacing pattern and charged; the blast fragments the bench | powder factor $q$ (kg/m³), $x_{50}$ and $P_{80}$ (cm), PPV (mm/s), flyrock range (m) | [drill and blast](../theory/drill-and-blast.md) | D1, C3 |
| Load | Shovels or loaders dig the muck pile and fill trucks pass by pass | bucket fill factor (–), passes per truck (–), payload CV (–) | [loading and terramechanics](../theory/loading-and-terramechanics.md), [bulk flow](../theory/bulk-flow-dem-mpm.md) | A3, D1 |
| Haul and dump | Trucks climb the ramps to the crusher, stockpiles or waste dumps and return | cycle time (min), t/h, queue time (min), L/t·km, kWh/t, CO₂e/t | [haulage](../theory/haulage.md), [dust](../theory/dust.md) | A1, A2, B1, C3, E1 |
| Crush | The primary crusher reduces run-of-mine (ROM) ore; oversize boulders can jam it | feed size $F_{80}$ (µm), throughput (t/h), downtime (min) | [comminution](../theory/comminution.md) | B2, D2 |
| Grind and concentrate | SAG and ball mills grind to liberation size; flotation separates concentrate from tailings | specific energy (kWh/t), product size $P_{80}$ (µm), recovery (%) | [comminution](../theory/comminution.md), [tailings](../theory/tailings.md) | D2, C2 |

The powder factor is plain geometry: $q = Q_\text{hole}/(B\,S\,H)$, with $Q_\text{hole}$ the explosive mass per hole
(kg), $B$ the burden (m), $S$ the spacing (m) and $H$ the bench height (m). The empirical laws that turn $q$ into a
size distribution (Kuz-Ram, then KCO and Swebrec) are reviewed by Ouchterlony and Sanchidrián [8] and derived on the
[drill and blast](../theory/drill-and-blast.md) page.

## What moves between stages, and why it couples them

Four couplings run along the chain. Each one is a reason to simulate stages together rather than in isolation.

1. **Blast → load.** Finer, looser muck fills the bucket better and digs faster. Fill factor feeds the number of passes
   per truck, which feeds payload variance and fuel ([A3](../cases/a3-loading-payload-variance.md)).
2. **Blast → mill ("mine-to-mill").** The size distribution leaving the blast is the feed of the crusher and the
   mills. A 1998 study at an Australian gold operation linked blast design to SAG-mill throughput [9]. A 2026 study
   trained random-forest meta-models on more than three million simulated scenarios, reported more than 90 %
   predictive accuracy, and found that finer fragmentation lowers total comminution cost despite a higher explosive
   cost [10]. This is the logic of [D2](../cases/d2-mine-to-mill.md).
3. **Load ↔ haul.** Trucks wait at the shovel when the fleet is too large; the shovel waits for trucks when it is too
   small. The match factor and closed queueing models balance the two ([A1](../cases/a1-truck-shovel-dispatch.md);
   see [open-pit operations](open-pit-operations.md#the-production-cycle-in-equations)).
4. **Mill → tailings.** Everything not recovered as concentrate is pumped to a tailings storage facility, whose
   failure is a low-probability, high-consequence event ([C2](../cases/c2-tailings-breach.md)).

### Mass balance: what the concentrator recovers

The two-product formula follows from two balances. With feed, concentrate and tailings mass flows $F$, $C$, $T$ (t/h)
and grades $f$, $c$, $t$ (mass fraction of the metal):

$$
F = C + T, \qquad F f = C c + T t
$$

Eliminating $T$ gives the mass yield and the metal recovery (Wills' *Mineral Processing Technology* [11]):

$$
\frac{C}{F} = \frac{f - t}{c - t}, \qquad R = \frac{C\,c}{F\,f} = \frac{c\,(f - t)}{f\,(c - t)}
$$

*Worked example (illustrative grades, not a real ore).* With $f = 0.8\,\%$ Cu, $c = 25\,\%$ and $t = 0.1\,\%$:
$C/F = 0.7/24.9 = 0.0281$, so 2.81 % of the feed mass leaves as concentrate, and
$R = 25 \times 0.7 / (0.8 \times 24.9) = 0.879$, i.e. 87.9 % of the copper is recovered. The other 97.2 % of the mass
goes to the tailings facility. That ratio is why tailings volumes are so large.

### Comminution energy: what grinding costs

Bond's third theory relates the specific energy to the change in the 80 %-passing size [12] (transcription
**UNVERIFIED — pinned at specification**):

$$
W = 10\,W_i \left( \frac{1}{\sqrt{P_{80}}} - \frac{1}{\sqrt{F_{80}}} \right)
$$

where $W$ is the specific energy (kWh/t), $W_i$ the Bond work index of the ore (kWh/t), and $F_{80}$, $P_{80}$ the
feed and product sizes through which 80 % of the mass passes (µm). Morrell's SMC-based relation is the modern
alternative for whole circuits [13]; both are in `minephys.comminution`.

*Worked example (illustrative inputs).* For $W_i = 15$ kWh/t, $F_{80} = 10\,000$ µm and $P_{80} = 150$ µm:
$W = 150 \times (1/\sqrt{150} - 1/\sqrt{10\,000}) = 150 \times (0.08165 - 0.01000) = 10.7$ kWh/t. Halving $F_{80}$ to
5,000 µm raises the bracket to $0.08165 - 0.01414 = 0.06751$ and lowers $W$ to 10.1 kWh/t, a 5.8 % saving. A finer
blast moves energy from the mill to the explosive; the mine-to-mill question is whether that trade pays.

## Where cost and energy go

The anchors below are context, not PitStudio results. Each is the published figure for the scope its source states.

| Anchor | Value | Scope | Source |
|---|---|---|---|
| Haulage share of open-pit operating cost | up to 60 % | truck–shovel systems, queueing study | [1] |
| Milling share of operating cost | 59.1 % (6.18 USD/t) | one open-pit copper operation, 2025 process costing | [2] |
| Crushing share of operating cost | 11 % (1.15 USD/t) | same operation | [2] |
| Grinding share of mining energy | 40 % | US mining energy bandwidth, as cited | [3] [4] |
| Diesel materials handling share of mining energy | 17 % | same | [3] [4] |
| Diesel saved by trolley assist | 830,000 L per year | one Swedish copper mine, 2018 | [5] |
| Trolley assist in a drive-cycle model | +44 % uphill speed, −16 % cycle travel time, −85 % fuel per up–down cycle | modelled on real coordinates of a copper mine | [6] |

Read together, the first five rows say that **the haul cycle is the main cost lever inside the pit, and comminution
is the main lever across the whole chain** [1] [2]. Category A cases work on the first lever and category D cases on
the second. Electrification changes the haulage energy balance too: drive-cycle simulations of large battery-electric
trucks charged from trolley lines in an open-pit copper mine found the concept feasible and cheaper than
diesel-electric operation under the stated assumptions [7]. The safety and environmental anchors, and the numbers deliberately left out because their primary text
could not be read, are on [scenario impact](scenario-impact.md).

## The five case categories on the chain

| Category | Stages covered | Cases | What it reports |
|---|---|---|---|
| A. Haulage and energy | load, haul | [A1](../cases/a1-truck-shovel-dispatch.md), [A2](../cases/a2-haul-road-electrification.md), [A3](../cases/a3-loading-payload-variance.md) | t/h, queue, match factor, cost/t; L/t·km, kWh/t, CO₂e/t; payload CV, passes/truck, fuel/t |
| B. Safety and autonomy | haul, crush | [B1](../cases/b1-traffic-proximity.md), [B2](../cases/b2-synthetic-perception.md) | minimum time-to-collision, near-misses per 1,000 h; synthetic held-out mAP, robustness |
| C. Geotech and environment | whole pit, haul roads, tailings | [C1](../cases/c1-slope-time-of-failure.md), [C2](../cases/c2-tailings-breach.md), [C3](../cases/c3-dust.md) | FoS, PoF, time-of-failure error, lead time; breach arrival time, depth, area; PM10 kg/VKT, receptor concentration |
| D. Drill-blast-to-mill | drill and blast → grind | [D1](../cases/d1-blast-muck-pile.md), [D2](../cases/d2-mine-to-mill.md) | P80, % oversize, PPV, flyrock radius; t/h, kWh/t, cost/t |
| E. Planning and survey | plan → haul | [E1](../cases/e1-pit-shell-pushbacks.md), [E2](../cases/e2-survey-reconciliation.md) | NPV, strip ratio, haul km per lift; volume error % |

## Assumptions and limits

- **No exploration geology.** E1 starts from a block model: synthetic deposits from the `oreblocks` package by default,
  or the optional MineLib *marvin* instance, which is CC BY-SA and kept in a separate share-alike entry [14].
- **No smelting or refining.** The chain stops at concentrate and tailings.
- **Flotation is a model, not a case.** First-order and Klimpel kinetics live in `minephys.comminution` and feed D2;
  a flotation soft-sensor case was considered and rejected because it is not a physics or rendering use of the stack.
- **Anchors are aggregates.** They come from specific operations, years and accounting scopes. PitStudio cites them to
  explain why a case matters; it never presents them as outputs of its own models.
- **Illustrative numbers are not ore data.** Work indices, grades and sizes in the worked examples were chosen to show
  the arithmetic.

## In PitStudio

- **Code.** Each stage maps to one `minephys` module (`planning`, `blasting`, `bulk`, `haulage`, `comminution`,
  `environment`, `geotech`); the studio adds GPU physics for loading and bulk flow ([M07](../methods/m07-gpu-granular-physics.md))
  and the pipeline adds learned surrogates ([M17](../methods/m17-comminution-mine-to-mill.md)).
- **Web.** The `/cases` catalogue groups the twelve cases by the five categories above; each case page has a *Context*
  sub-tab that links back to this chain.
- **Status.** The theory and methods are specified; no case has been run yet. See the [case catalogue](../cases/README.md)
  for each case's pre-registered acceptance criteria.

## References

1. May, M. A. (2013). *Applications of Queuing Theory for Open-Pit Truck/Shovel Haulage Systems.* Virginia Tech thesis.
   https://vtechworks.lib.vt.edu/items/fecf61c3-860b-4671-91ed-09549ddad265
2. Mboyo et al. (2025). Distribution of operating costs along the value chain of an open-pit copper mine. *Applied
   Sciences* 15(3):1602. https://doi.org/10.3390/app15031602
3. *Improve Energy Efficiency in Surface Mines Using Artificial Intelligence.* IntechOpen chapter.
   https://doi.org/10.5772/intechopen.101493
4. U.S. Department of Energy (2007). *Mining Industry Energy Bandwidth Study.* https://doi.org/10.2172/1218653
5. CIM Magazine. All in on trolley assist. https://magazine.cim.org/en/net-zero-challenge/all-in-on-trolley-assist-en/
6. Valenzuela Cruzat, Valenzuela (2018). Modeling and evaluation of benefits of trolley assist system for
   mining trucks. *IEEE Transactions on Industry Applications* 54(4):3971–3981. https://doi.org/10.1109/tia.2018.2823261
7. Lindgren, Grauers, Ranggård, Mäki (2022). Drive-cycle simulations of battery-electric large haul
   trucks with electric roads. *Energies* 15(13). https://doi.org/10.3390/en15134871
8. Ouchterlony, F., Sanchidrián, J. A. (2019). A review of development of better prediction equations for blast
   fragmentation. *Journal of Rock Mechanics and Geotechnical Engineering.* https://doi.org/10.1016/j.jrmge.2019.03.001
9. Kanchibotla, S. S., Morrell, S., Valery, W., O'Loughlin, P. (1998). Exploring the effect of blast design on SAG
   mill throughput. AusIMM Mine-to-Mill Conference, Brisbane.
   https://www.ausimm.com/publications/conference-proceedings/mine-to-mill-conference-brisbane-qld-october-1998/exploring-the-effect-of-blast-design-on-sag-mill-throughput-at-kcgm/
10. Nobahar, Xu, Dowd (2026). Cost-integrated AI meta-models for mine-to-mill optimisation. *Minerals*
    16(1):73. https://doi.org/10.3390/min16010073
11. Wills' *Mineral Processing Technology*, 8th ed. (2016). Elsevier. https://doi.org/10.1016/C2010-0-65478-2
12. Bond, F. C. (1952). The third theory of comminution. *Trans. AIME* 193:484–494.
    https://www.scirp.org/reference/referencespapers?referenceid=3600515
13. Morrell, S. (2004). An alternative energy–size relationship to that proposed by Bond. *International Journal of
    Mineral Processing* 74(1–4):133–141. https://doi.org/10.1016/j.minpro.2003.10.002
14. Espinoza, D., Goycoolea, M., Moreno, E., Newman, A. (2013). MineLib: a library of open pit mining problems.
    *Annals of Operations Research* 206(1):93–114. https://doi.org/10.1007/s10479-012-1258-3
