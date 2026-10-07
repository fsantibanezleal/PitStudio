# M03 — Two-stage LP dispatch

> The industry's classical dispatch structure: a linear program sets target flow rates on every shovel→dump path, and
> a real-time rule assigns each free truck to the path that lags its target most. · Part of: [Methods](README.md) ·
> Related: [Haulage theory](../theory/haulage.md) · [M02 DES](m02-haulage-des.md) · [M04 PPO](m04-ppo-dispatch.md) ·
> [Case A1](../cases/a1-truck-shovel-dispatch.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical / industry SOTA | no | live (small) + precompute | [A1](../cases/a1-truck-shovel-dispatch.md) | HiGHS via `highspy` (MIT; 1.15.1 targeted, locked in the build phase); small TypeScript LP | not yet implemented |

## What and why

Computer dispatching in open pits goes back to systems built in the 1980s that combine an optimisation layer with a
real-time assignment layer [1]. Moradi-Afrapoli, Upadhyay and Askari-Nasab review this **two-stage structure**: an
upper-stage LP sets the desired flow rate on each shovel→dump path under production, blending and plant-feed
constraints, and a lower stage assigns individual trucks in real time, with "1-truck-m-shovels" and
assignment-problem variants [2].

In PitStudio M03 has two roles:

1. it is the **strongest classical baseline** for the learned dispatch policies ([M04](m04-ppo-dispatch.md),
   [M05](m05-attention-fleet-policy.md)) — a learned policy is called "better" only if it beats both SPTF and this LP
   under the [pre-registered decision rule](README.md#how-methods-are-compared);
2. it is a teaching device: the LP's dual values tell a planner *which* resource (trucks, a shovel, the crusher, a
   blend constraint) limits production, and by how much.

## The algorithm

### Upper stage: flow-rate LP

The planned formulation follows the structure reviewed in [2]; the exact constraint set is fixed in the spec.

$$
\begin{aligned}
\max_{f \ge 0}\quad & \sum_{(s,d)} m \, f_{sd} \\
\text{s.t.}\quad & \sum_{d} f_{sd} \le \mu_s && \forall s \quad \text{(shovel capacity)}\\
& \sum_{s} f_{sd} \le \kappa_d && \forall d \quad \text{(dump / crusher capacity)}\\
& \sum_{(s,d)} f_{sd} \, T_{sd} \le N_T && \text{(fleet: Little's law)}\\
& \sum_{s} f_{sd}\,(g_s - g_d^{\min}) \ge 0 && \forall d \in \text{plant} \quad \text{(blend floor)}
\end{aligned}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $f_{sd}$ | target flow on path shovel $s$ → dump $d$ | loads/h |
| $m$ | nominal payload | t/load |
| $\mu_s$ | loading capacity of shovel $s$ | loads/h |
| $\kappa_d$ | acceptance capacity of dump or crusher $d$ | loads/h |
| $T_{sd}$ | round-trip cycle time on the path, excluding queues | h |
| $N_T$ | trucks available | – |
| $g_s$, $g_d^{\min}$ | grade at shovel $s$; minimum blended grade at plant $d$ | % |

The fleet constraint is Little's law: the number of trucks busy on a path equals its flow times its cycle time. The
objective can be swapped for "minimise deviation from a plant feed target" without changing the solver.

### Lower stage: real-time assignment

At every dispatch event of the [DES](m02-haulage-des.md), the free truck is sent to the path whose realised flow lags
its LP target most — the 1-truck-m-shovels rule reviewed in [2]:

```text
assign(truck, now):
    for each feasible path p = (s, d) reachable from the truck:
        need[p] = f_target[p] * (now - t_start) - loads_sent[p]   # how far behind schedule
    return argmax(need)          # ties: lowest expected arrival time, then lowest path id
```

The LP is re-solved when the state changes materially (a shovel goes down, a truck leaves the fleet), never every
event.

### Solvers

- **Studio / pipeline:** HiGHS through `highspy` (MIT) [3] for the LP; the same solver handles MineLib-size MILPs in
  [M18](m18-pit-optimisation-scheduling.md).
- **Browser:** the A1 LP has a handful of variables, so a small own simplex in TypeScript solves it live. Its
  objective must equal HiGHS's on the golden instances.
- **Not adopted:** a GPU LP/MILP solver was evaluated and not adopted for the Windows reference machine
  ([not-adopted: cuOpt](../frameworks/not-adopted-cuopt.md)): HiGHS on CPU solves these sizes.

### Worked example (illustrative inputs)

Two ore shovels feed one crusher. S1 is close ($T_1 = 0.5$ h per round trip), S2 is far ($T_2 = 0.8$ h). Each
shovel loads up to 12 loads/h, the crusher accepts 20 loads/h, and 12 trucks are available.

- **Without a blend constraint:** maximise $x_1 + x_2$ s.t. $x_1 \le 12$, $x_2 \le 12$, $x_1 + x_2 \le 20$,
  $0.5x_1 + 0.8x_2 \le 12$. The optimum sends the near shovel to capacity ($x_1 = 12$), which uses 6 truck-units,
  and spends the remaining 6 on the far shovel ($x_2 = 6/0.8 = 7.5$): **19.5 loads/h**. The fleet constraint binds,
  so one more truck is worth $1/0.8 = 1.25$ loads/h — until the crusher binds at $x_2 = 8$.
- **With a blend floor:** S1 grades 0.8 %, S2 grades 0.4 %, the crusher needs at least 0.65 %. The blend constraint
  $0.15x_1 - 0.25x_2 \ge 0$ caps $x_2 \le 0.6\,x_1 = 7.2$: **19.2 loads/h**, and now the blend, not the fleet, is the
  binding constraint. An extra truck is worth nothing until the blend changes.

The lower stage then distributes the 12 trucks so that realised flows track 12 and 7.2 loads/h.

## Baseline and comparison

- **Against classical rules:** SPTF and the greedy closest-shovel rule [2][4], on the same paired seeds in the
  [DES](m02-haulage-des.md), metric tonnes per hour.
- **Against learned policies:** M03 is one of the two baselines in the acceptance criterion of
  [M04](m04-ppo-dispatch.md) and [M05](m05-attention-fleet-policy.md).
- **Reporting:** all dispatchers are reported on several axes together (t/h, queue time, shovel idle, cost/t), never
  as one number. "Better" follows the [decision rule](README.md#how-methods-are-compared).

## Acceptance criterion (pre-registered)

M03 makes no superiority claim of its own. Its pre-registered checks are correctness checks:

- the TypeScript LP and HiGHS reach the same optimum on every golden instance (tolerance in
  `specs/000-foundation/thresholds.yaml`);
- metamorphic relations: relaxing any capacity never lowers the optimum; scaling all capacities by $k$ scales the
  optimum by $k$ when the fleet scales too; removing a path never raises it;
- in the DES, realised flows converge to the LP targets when the LP is feasible.

**Results: Not yet run** — produced in the data-and-models phase. Reported: LP targets and dual values for the A1
scenarios, and LP-dispatch KPIs vs SPTF and the learned policies on paired seeds.

## Lane and web delivery

**Live (small) + precompute.** The A1 LP is solved live in a web worker (well inside the 1 s gate for analytical
models, estimate; [compute lanes](../pipelines/compute-lanes.md)). Larger instances and the paired-seed tables are
precomputed with HiGHS and baked.

## Assumptions and limits

- Steady state and deterministic cycle times in the upper stage: the LP ignores queue interactions, which is exactly
  what the DES measures.
- Flows are continuous; integrality of trucks is handled by the lower stage, not the LP.
- Grades are block-model averages; no grade uncertainty (stochastic planning is outside this method).
- Generic, illustrative parameters — not any operator's configuration.

## In PitStudio

- **Cases:** [A1](../cases/a1-truck-shovel-dispatch.md).
- **Code (planned):** an LP dispatcher plugged into the `minehaulsim` dispatcher interface in `pipeline/`; HiGHS via
  `highspy`; a small TypeScript LP in the `web/` DES worker.
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. White, J. W. & Olson, J. P. (1986). Computer-based dispatching in mines with concurrent operating objectives.
   Mining Engineering 38(11). https://www.osti.gov/biblio/7015726
2. Moradi-Afrapoli, A., Upadhyay, S. & Askari-Nasab, H. (2021). Review of two-stage truck dispatching, assignment
   variants and greedy baselines. JSAIMM. https://doi.org/10.17159/2411-9717/522/2021
3. `highspy` (HiGHS Python interface), MIT, Windows wheels. https://pypi.org/pypi/highspy/json
4. OpenMines — baseline dispatchers including Nearest, FixedGroup, SPTF and SQ, MIT.
   https://github.com/370025263/openmines
