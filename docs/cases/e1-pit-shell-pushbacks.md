# E1 — Pit shell and pushbacks → life-of-mine haul distance

> Which ultimate pit and nested pushbacks maximise value for a block model, and how do haul distance and vertical lift
> grow period by period as the pit deepens — the planning input behind every haulage case. · Part of: [Cases](README.md) ·
> Related: [Planning theory](../theory/planning.md) ·
> [M18 Pit optimisation and scheduling](../methods/m18-pit-optimisation-scheduling.md) ·
> [oreblocks](../frameworks/oreblocks.md) · [A1](a1-truck-shovel-dispatch.md)

## What and why

**The question.** A long-term planner has a block model with grades, prices and costs. They ask: what is the
ultimate pit that maximises undiscounted value, how should it be split into nested shells and pushbacks, what net
present value (NPV) and strip ratio does a schedule give, and — the question that links planning to haulage — how
many kilometres and vertical metres must each tonne travel in each period as the pit deepens?

**Why it matters.**

- Haulage can account for as much as 60 % of open-pit operating cost [1]; haul distance and lift are set by the pit
  design long before dispatch can optimise them ([A1](a1-truck-shovel-dispatch.md), [A2](a2-haul-road-electrification.md)).
- The ultimate pit is a maximum-closure problem [2] solved exactly as a minimum cut; pseudoflow is the reference
  algorithm [3][4], and public benchmark instances with reference values exist [5].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| Synthetic block models with stamped exact optima (default) | **synthetic** | `oreblocks` (PyPI) [6] | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| MineLib `marvin` instance (optional) | real benchmark | MineLib, CC BY-SA 3.0 per the publisher [7]; derived-only, share-alike, never re-hosted | [minelib-marvin](../data-contract/dataset-cards/minelib-marvin.md) |
| Pit surface and ramp context | real terrain | USGS 3DEP Bingham Canyon | [bingham-3dep](../data-contract/dataset-cards/bingham-3dep.md) |

Anything baked from MineLib carries CC BY-SA 3.0 and lives in a separate manifest entry. Synthetic deposits are the
default because their optima are known exactly.

## Methods and baseline

| Rung | Method | Role in E1 |
|---|---|---|
| Classical / SOTA | [M18 Min-cut ultimate pit + nested shells + MILP scheduling](../methods/m18-pit-optimisation-scheduling.md) | Own min-cut (TS + Python) for the ultimate pit and revenue-factor shells; MILP scheduling with HiGHS [8] |
| Classical | [M6 Grade-constrained routing](../methods/m06-haul-road-energy-routing.md) | Ramp paths on each pushback's surface → haul km and lift per period |

**Formulation.** With block value $v_i$ (USD) and precedence arcs $(i \to j)$ meaning block $j$ must be removed before
$i$, the ultimate pit solves $\max \sum_i v_i x_i$ subject to $x_i \le x_j$ for every arc and $x_i \in \{0,1\}$ [2];
the schedule maximises $\sum_t \sum_i v_i x_{i,t}/(1+r)^t$ (USD) under precedence-by-time and capacity constraints,
with discount rate $r$ (–) and period $t$ [5].

**Baselines and oracles.** The own min-cut must equal the networkx and OR-Tools max-flow oracles [9] exactly, match
`oreblocks`' stamped optima, and match MineLib reference values when that instance is used. The PyPI `pseudoflow`
package is not used (non-commercial licence).

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| NPV | USD | Discounted schedule value from the MILP (or a nested-shell heuristic schedule) |
| Strip ratio | t/t | Waste tonnes ÷ ore tonnes, per pushback and for the pit |
| Haul distance per period | km | Tonne-weighted mean length of the M6 route from each period's mining faces to the pit exit and destination |
| Vertical lift per period | m | Tonne-weighted mean elevation gain along the same routes |

## Studio tools and artefacts

| Tool | Artefacts it produces for E1 |
|---|---|
| [USD Composer / Explorer](../frameworks/kit-usd-composer-explorer.md) (`studio/kit/`, `st58_kit_capture`) | Pushback review and measure captures of the shells in the pit stage, via our own Apache-2.0 extension |
| [oreblocks](../frameworks/oreblocks.md) | Synthetic block models and their exact optima |
| [minephys](../frameworks/minephys.md) `planning` | Lane cut-off and small min-cut reference |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Pit with nested shells and pushback layers; ramp routes per period | LIVE | three.js / R3F |
| Simulate | Ultimate pit on ≤ 10⁵ blocks with a revenue-factor slider | LIVE | TS min-cut worker, < 1 s |
| Simulate | Shells → haul km and lift per period | LIVE | TS routing |
| Studio replay | Composer review captures; baked MILP schedules | REPLAY | stills / clips; Parquet |
| Charts | Pit-by-pit value and tonnage; NPV by schedule; haul km and lift per period | LIVE / REPLAY | — |
| Context | Question, impact, licence notes | STATIC | — |

## Assumptions and limits

- **Synthetic deposits by default.** No real resource model is used; prices and costs are inputs.
- **Deterministic planning.** Grade uncertainty and stochastic scheduling are out of scope.
- **Share-alike.** MineLib-derived layers are CC BY-SA 3.0 and optional.
- **Composer is optional.** It needs the maintainer's answer to the kit-app-template licence prompt; without it, the
  Composer page shows "not run" and review uses the Isaac Sim GUI. Kit performance data stay local-only.
- Educational planning study, not a mine design or a reserve statement.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/e1.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/e1.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

See [Composer review](../guides/composer-review.md) for the optional review step.

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- Ultimate pit, nested shells and schedules for the reference deposits; exact agreement of the own min-cut with the
  oracles and with the stamped optima.
- NPV, strip ratio, and haul km and lift per period, handed to A1 and A2 as life-of-mine inputs.

## In PitStudio

- Recipe `studio/recipes/cases/e1.yaml`; route `/cases/E1`.

## References

1. May, M. A. (2013). *Applications of Queuing Theory for Open-Pit Truck/Shovel Haulage Systems*. Virginia Tech.
   https://vtechworks.lib.vt.edu/items/fecf61c3-860b-4671-91ed-09549ddad265
2. Lerchs, Grossmann (1965). *Optimum design of open-pit mines*. Trans. CIM 58(633):47–54 (bibliographic context).
   https://www.researchgate.net/publication/280082017_Pseudoflow_New_Life_for_Lerchs-Grossmann_Pit_Optimisation
3. Hochbaum (2008). *The pseudoflow algorithm: a new algorithm for the maximum-flow problem*. Oper. Res.
   56(4):992–1009. DOI 10.1287/opre.1080.0524
4. Hochbaum, Chen (2000). *Performance Analysis … Algorithms for the Open-Pit Mining Problem*. Oper. Res.
   48:894–914. DOI 10.1287/opre.48.6.894.12392
5. Espinoza, Goycoolea, Moreno, Newman (2013). *MineLib: a library of open pit mining problems*. Ann. Oper. Res.
   206(1):93–114. DOI 10.1007/s10479-012-1258-3
6. `oreblocks` on PyPI. https://pypi.org/project/oreblocks/
7. MineLib. https://minelib.org/
8. HiGHS `highspy` 1.15.1 (MIT). https://pypi.org/pypi/highspy/json
9. OR-Tools 9.15 (Apache-2.0). https://pypi.org/pypi/ortools/json
