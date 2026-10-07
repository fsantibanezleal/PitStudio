# DEC-0013: `minehaulsim` is the haulage reference engine

> The truck–shovel discrete-event simulation reuses the Apache-2.0 package `minehaulsim` as the Python reference engine;
> a TypeScript twin runs it live in the browser with exact event-trace parity, and SimPy serves only as an independent
> oracle. · Part of: [decisions](README.md) · Related: [minehaulsim](../../frameworks/minehaulsim.md) ·
> [M02 haulage DES](../../methods/m02-haulage-des.md) · [A1 dispatch](../../cases/a1-truck-shovel-dispatch.md) ·
> [prior art](../../context/prior-art-and-positioning.md)

**Status:** Accepted, 2026-10-04

## Context

Cases A1 (dispatch and fleet sizing), A2 (road energy), B1 (traffic) and C3 (dust from traffic) all need the haul cycle simulated event by event: loading, hauling, dumping, returning and queueing on a real road
network. The dispatch methods (LP in M03, PPO in M04, an attention policy in M05) need the same simulator as their
environment and as their judge.

- `minehaulsim` 0.12.1 (PyPI, 2026-09-26, Apache-2.0, Python ≥ 3.11) is a deterministic discrete-event simulation of
  open-pit and underground haulage with rimpull and retarder speed-by-grade, constrained roads (one-way ramps, passing,
  junction blocking), five dispatch policies and seeded parametric mine generators [1]. It is published by the
  maintainer and already locked in `pipeline/`.
- SimPy 4.1.2 (MIT) is a general-purpose process-based DES library [2].
- Open dispatch simulators exist (for example OpenMines, MIT [3]), and dispatch RL results are published on many
  different simulators with different baselines, so their gains do not transfer between papers [3] [4] [5].
- The web app must run the simulation live, which means a JavaScript or WebAssembly engine whose results match the
  Python reference exactly.

## Decision

- **Reference engine:** `minehaulsim` (version from the lock) runs every precomputed haulage experiment in `pipeline/`.
- **Browser twin:** a TypeScript port runs in a web worker. Parity is an **exact event trace** against Python goldens:
  seeded counter-based PRNG, explicit tie-breaks, no `Math.*` transcendental calls in variate generation
  ([DEC-0006](DEC-0006-3d-and-simulation-on-static-web.md)). A shift of about 10⁴ events must finish in under 1 s on the
  WebAssembly tier to stay live ([lanes](../lanes.md)).
- **Oracles:** SimPy reproduces selected scenarios independently, and in the exponential case the DES must reproduce the
  closed-form results of finite-source queueing and mean-value analysis ([M01](../../methods/m01-match-factor-queueing.md)).
- **Learning environment:** PPO and attention dispatch policies train in a GPU-vectorised PyTorch environment and are
  cross-checked in the DES; "beats SPTF / LP" requires the pre-registered decision rule on t/h over ≥ 30 paired seeds
  ([DEC-0016](DEC-0016-pre-registered-decision-rule.md)).
- **Links.** The documentation links `minehaulsim` and `oreblocks` by their PyPI pages.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Re-implement a haulage DES inside PitStudio | Full control | Duplicates a maintained, tested Apache-2.0 engine | No new capability |
| SimPy as the main engine | Widely known, MIT | A general library: rimpull physics, road constraints, dispatchers and generators would all have to be written; process-based scheduling makes an exact TypeScript twin harder | Kept as an oracle only |
| Adopt an external open dispatch simulator | Existing baselines | Different road and physics model; would still need a browser twin | `minehaulsim` already fits the physics and the generators |

## Consequences

**Positive.** Haulage physics and dispatchers are reused, not rewritten; one engine is the judge for classical, LP and
learned dispatch; the browser twin is held to exact parity.

**Negative, accepted.** An external dependency whose upgrades regenerate the trace goldens; the TypeScript port must
follow the engine's event semantics exactly.

**Watch.** `minehaulsim` releases; trace-parity failures after upgrades.

## References

1. `minehaulsim` on PyPI. https://pypi.org/project/minehaulsim/
2. SimPy on PyPI. https://pypi.org/pypi/simpy/json
3. OpenMines repository. https://github.com/370025263/openmines
4. Banerjee, Nguyen, Fookes (2025). Mining-Gym. https://arxiv.org/abs/2503.19195
5. Zhang C. et al. (2020). Dynamic dispatching for large-scale heterogeneous fleet via multi-agent deep reinforcement
   learning. https://arxiv.org/abs/2008.10713
