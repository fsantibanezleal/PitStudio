# oreblocks

> A generator of synthetic 3D ore-body block models with exact pit-shell optima, used as PitStudio's default deposit
> for pit shells, pushbacks and life-of-mine haul distance. · Part of: [Frameworks](README.md) · Related:
> [M18 pit optimisation and scheduling](../methods/m18-pit-optimisation-scheduling.md) ·
> [E1 pit shell and pushbacks](../cases/e1-pit-shell-pushbacks.md) · [Planning](../theory/planning.md) ·
> [MineLib dataset card](../data-contract/dataset-cards/minelib-marvin.md)

## What and why

`oreblocks` builds synthetic block models "of the MineLib nature": seeded deposit archetypes, bench structure, slope
precedence, ultimate-pit economics, an exact maximum-closure solver, MineLib file read/write, a certified LP bound for
the constrained pit problem, rounding heuristics and spatial-coherence metrics [1]. It is the maintainer's own earlier
public package.

Why it is the default deposit:

- **Licence-clean.** Real benchmark block models come from MineLib, whose instances are CC BY-SA 3.0 per the publisher
  [2]. Share-alike outputs must stay in separate entries; `oreblocks` deposits carry no such obligation.
- **Exact answers.** A synthetic deposit with a stamped optimum lets the pit-shell solver be tested against truth, not
  against another solver.
- **Same format as the benchmark.** It reads and writes MineLib files, so the optional `marvin` instance runs through the
  same code path.

## Identity

| Item | Value |
|---|---|
| Package | `oreblocks` 0.5.2, pinned in `pipeline/uv.lock` |
| Release | 2026-09-26 [1] |
| Requires | Python ≥ 3.11; numpy ≥ 1.26 (extra `milp`: scipy) [1] |
| Licence | MIT (package) · open |
| Ring | Adopt (maintainer's own package) |
| Environment | `pipeline/` (Python 3.14) |
| Modules | `upit`, `fastcut`, `precedence`, `economics`, `schedule`, `stochastic`, `minelib_io`, `coherence` and others (from the installed wheel) |

## How PitStudio uses it

| Use | Case / method | Detail |
|---|---|---|
| Default deposit | E1 · M18 | `s05_synthesize` seeds a deposit; nested shells by parametric revenue factor; pushbacks; MILP scheduling with HiGHS |
| Oracle for our own min-cut | E1 · M18 | PitStudio's own min-cut (Python and TypeScript, live for ≤ 10⁵ blocks) is checked against the exact optimum |
| Pit geometry for the scene | all scene cases | shells feed `st20_pit_design`, where benches, berms and ramps are drawn |
| Optional real benchmark | E1 | MineLib `marvin`, CC BY-SA, labelled and kept in a separate share-alike entry |

Artefacts it will produce: shells and pushback variants (USD variants of the design layer), NPV and strip-ratio curves,
and life-of-mine haul distance per lift.

## Licence and redistribution

The package is MIT. Its Zenodo record is CC BY 4.0 and contains a note that MineLib instances are for academic download
only [3]; the publisher states CC BY-SA 3.0 [2]. PitStudio follows the publisher, keeps MineLib-derived layers
share-alike and separate, and uses `oreblocks` by default. The docs link only its PyPI page.

## Assumptions and limits

- A synthetic deposit is honest synthetic data: it shows how methods behave, not what a real ore body is worth.
- Planning outputs are educational, not design software ([Planning](../theory/planning.md)).

## In PitStudio

- Status: **not yet run.** The package is locked and installed in `pipeline/`.

## References

1. Python Package Index. *oreblocks* 0.5.2. https://pypi.org/project/oreblocks/
2. MineLib. *MineLib home* (CC BY-SA 3.0 statement). https://minelib.org/
3. Zenodo. *oreblocks v1.2 record*. https://zenodo.org/api/records/22834700
