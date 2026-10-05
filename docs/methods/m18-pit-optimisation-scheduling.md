# M18 — Ultimate pit by minimum cut, nested shells and MILP production scheduling

> The most valuable pit a block model allows is found exactly as a minimum cut in a precedence graph, nested shells
> come from re-solving at scaled prices, and a mixed-integer program schedules the blocks into periods — live in the
> browser for up to about 10⁵ blocks. · Part of: [Methods](README.md) · Related:
> [Planning theory](../theory/planning.md) · [M06 haul routing](m06-haul-road-energy-routing.md) ·
> [oreblocks](../frameworks/oreblocks.md) · [Case E1](../cases/e1-pit-shell-pushbacks.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical / SOTA | no | live + precompute | [E1](../cases/e1-pit-shell-pushbacks.md) | own min-cut (Python + TypeScript, Apache-2.0); OR-Tools 9.15.6755 and networkx 3.7 as oracles; HiGHS (MIT) for MILP | not yet implemented |

## What and why

Every open pit starts from a block model and one question: which blocks are worth mining, given that a block can only
be mined once the blocks above it (within the slope angle) are gone? Lerchs and Grossmann showed in 1965 that the
optimal pit is the **maximum-weight closure** of the block precedence graph [1]; it is solved exactly as a
**minimum cut**, and Hochbaum's pseudoflow algorithm, with a parametric variant that produces nested pits, is the
modern reference [2]. MineLib publishes standard instances and formats for the ultimate-pit, constrained-pit and
precedence-constrained scheduling problems [3].

M18 gives case E1 the pit shell, the pushbacks (nested shells) and a production schedule, which [M06](m06-haul-road-energy-routing.md)
turns into haul distance per lift.

## The algorithm

### Block values

For block $i$ with tonnage $T_i$ (t), grade $g_i$ (fraction), recovery $r$, price $p$ and selling cost $s_r$ (per unit
of metal), processing cost $c_p$ and mining cost $c_m$ (per tonne), the economic value is (standard notation, pinned at
specification)†:

$$
v_i = \max\Big(T_i\big[g_i\, r\,(p - s_r) - c_p\big],\ 0\Big) - T_i\, c_m
$$

i.e. a block is processed if that pays, otherwise sent to waste.

### Ultimate pit as maximum closure

$$
\max_{x \in \{0,1\}^n} \sum_i v_i x_i \quad \text{s.t.} \quad x_i \le x_j \quad \forall (i \to j) \in \mathcal{P}
$$

where $(i \to j)$ means "mining $i$ requires $j$" (the precedence pattern derived from the slope angle, fixed in the
spec) [1][2].

### Minimum-cut construction

Build a flow network with a source $s$ and sink $t$:

- an arc $s \to i$ with capacity $v_i$ for every block with $v_i > 0$;
- an arc $i \to t$ with capacity $-v_i$ for every block with $v_i < 0$;
- an arc $i \to j$ with infinite capacity for every precedence $(i \to j)$.

The source side of a minimum $s$–$t$ cut is the optimal pit, and its value is
$\sum_{v_i > 0} v_i - \text{(min cut capacity)}$. Infinite precedence arcs can never be cut, so the closure constraint
is enforced automatically.

```text
ultimate_pit(blocks, precedences):
    G = graph(s, t)
    for i in blocks:
        if v[i] > 0: G.add(s, i, v[i])
        if v[i] < 0: G.add(i, t, -v[i])
    for (i, j) in precedences: G.add(i, j, INF)
    S = source_side(min_cut(G))          # own push-relabel / pseudoflow-style solver
    return S - {s}, sum(v[i] for i in S - {s})
```

### Nested shells and pushbacks

Scaling the metal price by a revenue factor $\lambda \in (0, 1]$ and re-solving gives a family of pits that are nested
(a smaller $\lambda$ never gives a larger pit); consecutive shells become pushbacks [2]. PitStudio re-solves at a grid of
$\lambda$; the parametric pseudoflow variant is the reference for doing this in one pass.

### Production scheduling (MILP)

With binary $x_{i,t}$ = "block $i$ mined in period $t$", discount rate $r_d$ and period resource limits, the
time-indexed program is [3]†:

$$
\max \sum_t \sum_i \frac{v_i}{(1 + r_d)^{t}}\, x_{i,t}
\quad \text{s.t.} \quad
\sum_{\tau \le t} x_{i,\tau} \le \sum_{\tau \le t} x_{j,\tau}\ \ \forall (i \to j), t; \quad
\sum_i T_i\, x_{i,t} \le C_t\ \ \forall t; \quad
\sum_t x_{i,t} \le 1
$$

with $C_t$ the mining capacity of period $t$ (t). HiGHS solves the relaxations and small instances; MineLib-size
instances run in the studio and are baked.

### Cut-off grade

Lane's theory balances mine, mill and market capacities with the opportunity cost of time; the mine-limited cut-off
is $g_m = h/((s - r)\,y)$ with processing cost $h$, price $s$, selling cost $r$ and recovery $y$ (transcription
UNVERIFIED — pinned at specification) [4]. It lives in `minephys.planning` for the planning theory page.

### Worked example (illustrative values)

One ore block $B$ lies under three waste blocks $A_1, A_2, A_3$, each worth −1. If $v_B = +4$, the network has
$s \to B$ (capacity 4) and $A_k \to t$ (capacity 1 each), with infinite arcs $B \to A_k$. The minimum cut is
$\min(4, 3) = 3$, so the pit value is $4 - 3 = +1$: mine all four blocks. If $v_B = +2$, the minimum cut is
$\min(2, 3) = 2$ and the value is 0: the empty pit is optimal — the ore does not pay for its stripping.

## Baseline and comparison

- **Oracles:** OR-Tools `SimpleMaxFlow` (Apache-2.0) [5] and networkx 3.7 (BSD-3) [6] compute the same minimum cut on
  integer-scaled values; SciPy's `maximum_flow` is a third oracle for integer capacities [7]. The PyPI `pseudoflow`
  package is **not** used: its licence is non-commercial [8].
- **Synthetic deposits with known optima:** `oreblocks` generates licence-free synthetic block models with stamped
  exact optima [9]; recovering them exactly is the core test.
- **MineLib (optional):** the marvin instance (CC BY-SA 3.0 per the publisher; a conflicting "no redistribution"
  statement exists and is recorded in the data card) is fetched at run time, never re-hosted, and its derived outputs
  carry the share-alike licence [3].
- No stochastic "better" claim: the min-cut is exact.

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)):

- the own min-cut equals the OR-Tools and networkx objective exactly on every golden instance, and recovers the stamped
  `oreblocks` optima;
- metamorphic relations: shells are nested in $\lambda$; adding a positive value to an ore block never shrinks the
  pit; raising mining cost never enlarges it; the TypeScript and Python solvers return the same block set;
- the MILP schedule satisfies every precedence and capacity constraint (property test).

**Results: Not yet run** — produced in the data-and-models phase. Reported: E1 shells and pushbacks, NPV and strip
ratio per schedule, haul km per lift via [M06](m06-haul-road-energy-routing.md).

## Lane and web delivery

**Live + precompute.** The minimum cut runs live in a web worker for up to about $10^5$ blocks within 1 s (gate
estimate, measured when the web is built); larger models and MILP schedules are precomputed and baked as shells.
Pushbacks are reviewed in USD Composer/Explorer in the studio (measure tools on the scene). Fallback: baked shells.

## Assumptions and limits

- Deterministic block values: no grade uncertainty (stochastic scheduling is outside this method).
- Precedence from a single overall slope angle; geotechnical domains are a configurable refinement.
- Synthetic deposits by default; real block models (MineLib) are optional and share-alike.
- Educational and planning-grade, not mine-planning software.

## In PitStudio

- **Cases:** [E1](../cases/e1-pit-shell-pushbacks.md) (NPV, strip ratio, haul km per lift).
- **Code (planned):** own min-cut in Python (studio stage `st20_pit_design`, which turns shells into benches, ramps and
  pushback variants of the USD scene) and in a `web/` worker; small min-cut and Lane cut-off in `minephys.planning`;
  MILP with HiGHS in `pipeline/`; `oreblocks` 0.5.2 and `ortools` 9.15.6755 in the locks. Data cards:
  [MineLib marvin](../data-contract/dataset-cards/minelib-marvin.md).
- **Status:** not yet implemented — built test-first in the build phase.

† Standard form; the transcription is checked against the primary source by a worked-example test at specification.

## References

1. Lerchs, H. & Grossmann, I. F. (1965). Optimum design of open-pit mines. Trans. CIM 58(633):47–54 (bibliographic
   context). https://www.researchgate.net/publication/280082017_Pseudoflow_New_Life_for_Lerchs-Grossmann_Pit_Optimisation
2. Hochbaum, D. S. (2008). The pseudoflow algorithm: a new algorithm for the maximum-flow problem. Operations Research
   56(4):992–1009. https://doi.org/10.1287/opre.1080.0524
3. Espinoza, D., Goycoolea, M., Moreno, E. & Newman, A. (2013). MineLib: a library of open pit mining problems. Annals
   of Operations Research 206(1):93–114. https://doi.org/10.1007/s10479-012-1258-3 · licence page
   https://minelib.org/v1/
4. Lane, K. F. (1964). Choosing the optimum cut-off grade. Colorado School of Mines Quarterly 59:811–829.
   https://www.scirp.org/reference/referencespapers?referenceid=1929843
5. OR-Tools max flow (`SimpleMaxFlow`, min-cut accessors, Apache-2.0).
   https://developers.google.com/optimization/flow/maxflow
6. networkx 3.7 (BSD-3). https://pypi.org/pypi/networkx/json
7. SciPy `maximum_flow` (Dinic, Edmonds–Karp; integer capacities).
   https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.maximum_flow.html
8. `pseudoflow` on PyPI — "Non-commercial license. Not an open-source license." https://pypi.org/pypi/pseudoflow/json
9. oreblocks (Zenodo record) — synthetic block models with stamped exact optima.
   https://zenodo.org/api/records/22834700
