# Web

> The static web companion: its routes, the paths a visitor takes, the honesty rules it enforces, where it computes,
> what it may weigh and what its access gate is and is not. · Part of: [docs home](../README.md) · Related:
> [architecture](../architecture/README.md) · [compute lanes](../pipelines/compute-lanes.md) ·
> [DEC-0006 3D and simulation on static web](../architecture/decisions/DEC-0006-3d-and-simulation-on-static-web.md)

## Orientation

The web app is a static site on GitHub Pages at `https://fsantibanezleal.github.io/PitStudio/`. It is built from
`web/` with React 19.3, Vite 8.3 and React Router 8.4 in framework mode (`ssr: false`), and every static route is
prerendered to HTML (versions from `web/pnpm-lock.yaml`). It has no server: anything computed on the site is computed
in the visitor's browser, and anything heavier is precomputed in the local studio and replayed.

**Status today.** The shell exists and is tested: header, footer, access gate, language (EN/ES), theme
(system/light/dark) and the ⓘ architecture view. The seven top-level routes exist as stub pages that say "Not built
yet". No data, models or simulation results are published, and every studio tool is "not yet run". The routes, engines
and assets described in this section are built in the build phase and filled with real artefacts in the
data-and-models phase.

## Map

| Page | What you find |
|---|---|
| [structure.md](structure.md) | The shell and every route: `/`, `/cases`, `/cases/:id`, `/studio`, the 17 tool pages, `/studio/runs`, `/studio/gpu`, `/theory`, `/methods`, `/results`, `/knowledge`, the ⓘ tabs; what exists in `web/src/` today versus planned |
| [user-flow.md](user-flow.md) | How each audience moves through the site, the shared timeline, opt-in actions and fallbacks |
| [showcase-rules.md](showcase-rules.md) | The honesty rules checked in CI: lane badges, "not yet run", outputs-only for proprietary tools, local-only performance cards |
| [compute-tiers.md](compute-tiers.md) | T1 WebGPU, T2 WebAssembly, T0 baked; the engines (TS workers, WGSL, ORT-web, Rapier, Pyodide + `minephys`) and their fallbacks |
| [access-gate.md](access-gate.md) | Threat note for the demo gate: what the SHA-256 digest and `sessionStorage` do, and why it is not security |
| [budgets.md](budgets.md) | The 500 MB byte budget per asset class, git versus release assets, the asset-release flow and how CI enforces it |

## Diagrams

| Diagram | Shows |
|---|---|
| [web-routes.svg](../assets/diagrams/web-routes.svg) | Route tree with lane badges, existing versus planned route modules |
| [compute-tiers.svg](../assets/diagrams/compute-tiers.svg) | Capability probe → T1 / T2 / T0 per engine family, with fallbacks |
| [access-gate-threat.svg](../assets/diagrams/access-gate-threat.svg) | Build-time digest, run-time check, and what the gate does not protect |

## Reading order

1. [structure.md](structure.md) for the map of the site.
2. [showcase-rules.md](showcase-rules.md) before reading any result on it.
3. [compute-tiers.md](compute-tiers.md) and [budgets.md](budgets.md) if you build or extend it.
4. [access-gate.md](access-gate.md) if you deploy it.
