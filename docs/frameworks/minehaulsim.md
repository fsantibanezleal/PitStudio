# minehaulsim

> A deterministic discrete-event simulator of open-pit and underground haulage, used as PitStudio's reference haulage
> engine, with a TypeScript twin in the browser that must reproduce its event trace exactly. · Part of:
> [Frameworks](README.md) · Related: [M02 haulage DES](../methods/m02-haulage-des.md) ·
> [A1 truck–shovel dispatch](../cases/a1-truck-shovel-dispatch.md) · [Haulage](../theory/haulage.md) ·
> [DEC-0013](../architecture/decisions/DEC-0013-haulage-engine-minehaulsim.md)

## What and why

`minehaulsim` simulates trucks, shovels, crushers and dumps as discrete events on a constrained road network (one-way
ramps, passing, junction blocking), with speed set by grade through rimpull and retarder physics. It ships seeded
parametric open-pit and underground mine generators and baseline dispatchers, and its core depends only on numpy [1].
It is the maintainer's own earlier public package, published under Apache-2.0.

Why it is the haulage engine ([DEC-0013](../architecture/decisions/DEC-0013-haulage-engine-minehaulsim.md)):

- **Determinism by construction.** The same seed gives the same event trace, which is what an exact Python-to-browser
  parity test needs.
- **The physics PitStudio needs already exists:** grade-dependent travel, constrained roads, classical dispatchers.
- **Re-implementing a DES** would duplicate it without new value; **SimPy** stays a cross-check oracle rather than the
  main engine, because the product needs mining-specific road and equipment semantics on top of a generic kernel.

## Identity

| Item | Value |
|---|---|
| Package | `minehaulsim` 0.12.1, pinned in `pipeline/uv.lock` |
| Release | 2026-09-26 [1] |
| Requires | Python ≥ 3.11; numpy ≥ 1.26 (extras: `viz`, `geology` with `oreblocks`) [1] |
| Licence | Apache-2.0 · open |
| Ring | Adopt (maintainer's own package) |
| Environment | `pipeline/` (Python 3.14) |
| Modules | `des`, `equipment`, `geometry`, `network`, `planning`, `scenarios`, `io`, `rng`, `viz` (from the installed wheel) |

## How PitStudio uses it

| Use | Case / method | Detail |
|---|---|---|
| Reference DES with classical dispatchers | A1 · M2 | fixed allocation, nearest/greedy, shortest-processing-time, shortest queue, minimum shovel idle, on the Bingham road network |
| Cross-check of the learned dispatch policies | A1 · M4, M5 | the GPU-vectorised PyTorch environment is checked against DES statistics |
| Traffic for other cases | B1, C3, A2 | truck traces drive the sensor scenes (kinematic poses), dust emission (vehicle kilometres travelled) and energy |
| TS twin in the browser | A1 | a TypeScript DES worker reproduces the Python event trace **exactly**, with a shared counter-based PRNG and explicit tie-breaking; KPIs within tolerance |

Artefacts it will produce: event traces (golden fixtures for the TS twin), cycle-time and queue statistics, fleet KPIs
(t/h, queue time, match factor, cost per tonne) with paired-seed confidence intervals.

## Licence and redistribution

Apache-2.0, same as PitStudio. The docs link only its PyPI page.

## Assumptions and limits

- Truck performance curves are generic, from academic sources, not an OEM's data ([A2](../cases/a2-haul-road-electrification.md)).
- A DES is a model of a mine, not a live digital twin: no telemetry feed, and its validity is bounded by its inputs.
- Floating-point transcendental functions differ across browsers, so variates for the TS twin avoid them; this is a
  constraint on the twin, not on `minehaulsim` itself.

## In PitStudio

- Status: **not yet run** in PitStudio. The package is locked and installed in `pipeline/`; A1 is part of the first
  end-to-end slice.
- Theory: [Haulage](../theory/haulage.md). Methods: [M01](../methods/m01-match-factor-queueing.md),
  [M02](../methods/m02-haulage-des.md), [M03](../methods/m03-lp-dispatch.md).

## References

1. Python Package Index. *minehaulsim* 0.12.1. https://pypi.org/project/minehaulsim/
2. Python Package Index. *SimPy* 4.1.2. https://pypi.org/pypi/simpy/json
