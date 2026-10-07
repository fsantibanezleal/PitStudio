# Context

> Why PitStudio exists: the mining domain it simulates, the physical-AI idea it applies, the impact behind its twelve
> cases and the prior art it builds on. · Part of: [documentation home](../README.md) · Related:
> [theory](../theory/README.md) · [cases](../cases/README.md) · [architecture](../architecture/README.md)

## Orientation

Read this section first if you are new to open-pit mining, to physical AI, or to both. It answers four questions
before the theory and the cases go into depth:

1. **What happens in an open-pit mine, and where do cost, energy and risk sit?** The value chain runs from a block
   model through drilling, blasting, loading, hauling and crushing to grinding and concentration, with tailings and
   waste at the end. Haulage dominates cost inside the pit; grinding dominates energy across the chain.
2. **What does a "physical-AI simulation studio" add?** A closed loop: a sensor-realistic scene produces synthetic
   labels, the labels train a model, and the model is validated with its sim-to-real gap stated rather than hidden.
3. **Why these twelve cases?** Each was scored on published impact, how well it can be simulated, whether real data
   or an analytical ground truth exists to validate it, how well it explains in a browser, and whether it genuinely
   uses the GPU.
4. **What exists already?** Commercial tools are siloed and closed; open projects cover dispatch, haulage and pit
   optimisation in 2-D; nobody publishes the closed physical-AI loop for mining.

## Pages

| Page | What you learn | Diagram |
|---|---|---|
| [Mining value chain](mining-value-chain.md) | The stages from block model to tailings, what moves between them, where cost and energy go, and how the five case categories map onto the chain | [value chain](../assets/diagrams/mining-value-chain.svg) |
| [Open-pit operations](open-pit-operations.md) | Benches, berms, ramps, the loading face, haul roads, the crusher, dumps and the tailings facility; the production cycle and its first equations | [open-pit anatomy](../assets/diagrams/open-pit-operations.svg) |
| [Physical AI and simulation twins](physical-ai-and-simulation-twins.md) | Digital twin versus simulation-grade twin, the physical-AI loop, the Omniverse-class platform as of October 2026, and how PitStudio measures the sim-to-real gap | [physical-AI loop](../assets/diagrams/physical-ai-loop.svg) |
| [Scenario impact](scenario-impact.md) | The sourced impact anchors (cost, energy, safety, environment), the scoring that selected the cases, and the numbers deliberately left out | — |
| [Prior art and positioning](prior-art-and-positioning.md) | Commercial tools, open-source projects, academic evidence, the gap PitStudio fills and what it reuses instead of rewriting | — |

## Reading order

Domain newcomers: value chain → open-pit operations → scenario impact. AI practitioners: physical AI and simulation
twins → prior art → scenario impact. Then continue to [theory](../theory/README.md) or straight to the
[case catalogue](../cases/README.md).
