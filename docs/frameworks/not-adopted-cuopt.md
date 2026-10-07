# NVIDIA cuOpt (evaluated, not adopted)

> NVIDIA's GPU solver for linear, mixed-integer and routing problems, evaluated for dispatch and scheduling and not
> adopted because it ships only Linux wheels and a CPU solver already covers PitStudio's problem sizes. · Part of:
> [Frameworks](README.md) · Related: [M03 LP dispatch](../methods/m03-lp-dispatch.md) ·
> [M18 pit optimisation and scheduling](../methods/m18-pit-optimisation-scheduling.md) ·
> [Scaling to Linux](../studio/scaling-to-linux.md)

## What and why

**cuOpt** is NVIDIA's GPU-accelerated optimisation engine for linear programming (LP), mixed-integer programming (MILP)
and vehicle routing, published under Apache-2.0 [1]. Mining has natural uses for it: the two-stage LP dispatch of case
A1 (M3) and the production-scheduling MILP of case E1 (M18).

## What we evaluated

| Check | Finding |
|---|---|
| Version and licence | `cuopt-cu13` / `cuopt-cu12` 26.8.0, uploaded 2026-08-06, Apache-2.0 [1] |
| Platforms | wheels for `manylinux_2_24` / `manylinux_2_28` on x86_64 and aarch64 only; no Windows wheel [1] |
| What Windows would need | an Ubuntu distribution under WSL2 — an install the maintainer performs |
| The alternative | HiGHS through `highspy` 1.15.1 (MIT, Windows wheels) solves the dispatch LP, and the MineLib-size scheduling MILPs, on the CPU [2]; OR-Tools max-flow covers the pit-shell min-cut [3] |

## Where it would have fitted

| Problem | Case / method | Size | Solver used instead |
|---|---|---|---|
| Two-stage dispatch: a flow-rate LP over shovels, dumps and road segments, then real-time truck assignment | A1 · M3 | small: one pit's shovels, dumps and roads | HiGHS (`highspy`), plus a small LP in TypeScript for the live workbench |
| Ultimate pit as maximum closure (a min-cut on the block precedence graph) | E1 · M18 | up to 10⁵ blocks live, more in the studio | our own min-cut, checked against OR-Tools `SimpleMaxFlow` and the exact optima of `oreblocks` |
| Production scheduling over periods (MILP) | E1 · M18 | MineLib-sized instances | HiGHS |

cuOpt's vehicle-routing solver has no counterpart in the cases: haulage routes are fixed road networks, and dispatch is
decided by the DES dispatchers and the learned policies ([M02](../methods/m02-haulage-des.md),
[M04](../methods/m04-ppo-dispatch.md)).

## Why not adopted

PitStudio adopts a tool for a measured benefit, not for coverage. On the reference workstation cuOpt would add a WSL
distribution and a cross-OS file handoff to solve problems that HiGHS already solves on the CPU in the time a case
needs. No PitStudio KPI depends on an LP or MILP being faster than that.

## Assumptions and limits

- The dispatch LP is small (a flow-rate LP over shovels, dumps and road segments); the scheduling MILP is MineLib-sized.
  If a case grows to sizes where HiGHS becomes the bottleneck, this verdict changes.
- No cuOpt timing was measured on our problems; the decision rests on platform fit, not on a benchmark.

## When to re-assess

- When a **Linux GPU host** exists for the `linux-gpu` runner profile ([Scaling to Linux](../studio/scaling-to-linux.md)):
  cuOpt then installs natively and a HiGHS-vs-cuOpt comparison on the M3 and M18 instances becomes cheap.
- When cuOpt publishes Windows wheels.
- When a scheduling instance makes HiGHS the measured bottleneck of a recipe.

## In PitStudio

- Status: **evaluated, not adopted.** The solver role is held by HiGHS (`highspy`) and OR-Tools.
- The web tool map shows this page instead of a tool card.

## References

1. Python Package Index. *cuopt-cu13* 26.8.0. https://pypi.org/project/cuopt-cu13/
2. Python Package Index. *highspy* 1.15.1. https://pypi.org/pypi/highspy/json
3. Google. *OR-Tools maximum flow*. https://developers.google.com/optimization/flow/maxflow
