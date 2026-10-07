# A3 — Loading and payload variance

> How do bucket fill and the number of passes spread truck payloads, what does that spread cost in fuel per tonne,
> and can GPU granular physics, a learned surrogate and a learned digging policy answer it honestly? ·
> Part of: [Cases](README.md) · Related: [Loading and terramechanics](../theory/loading-and-terramechanics.md) ·
> [Bulk flow, DEM and MPM](../theory/bulk-flow-dem-mpm.md) · [M7 GPU granular physics](../methods/m07-gpu-granular-physics.md) ·
> [GNS granular model](../models/gns-granular.md)

## What and why

**The question.** A load-and-haul supervisor sees trucks leave the shovel under- or over-loaded. They ask: for a
given muck pile and bucket, what is the bucket fill factor, how many passes does a truck need, how variable is the
payload (coefficient of variation), and how much fuel per tonne does that variability cost downstream? An automation
team asks the follow-on: can an excavator policy trained in simulation fill the bucket reliably, and does it still
work when the soil model changes?

**Why it matters.**

- At an Australian open-cut coal mine, reducing payload variance (0–30 % range tested) was found to cut haul-truck
  fuel by up to 35 % [1].
- Bucket fill is the main coupling between blasting and loading: fragmentation and muck-pile looseness control it
  ([D1](d1-blast-muck-pile.md)).
- Learned digging has field precedents: a policy trained with a randomised Fundamental Earthmoving Equation (FEE)
  soil model ran on a real 12 t excavator in several soils [2]; an Isaac Lab boulder-excavation policy reached 70 %
  field success against 83 % for human operators [3].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| Bucket–pile and truck-loading rollouts (particles, forces, payload per pass) | **synthetic** | Warp DEM and Newton implicit-MPM runs; CC-BY-4.0 | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| Calibration targets: angle of repose and heap shape | literature values | DEM calibration practice [4]; target values pinned at specification | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| IL-2 digging episodes (FEE soil, then zero-shot in MPM) | **synthetic** | Isaac Lab env, procedural excavator | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |

No open dataset of bucket fill factors or payload records was found. All A3 data are **"calibrated synthetic — not
validated against real data"**; the calibration anchor is the repose target, and published fill-factor ranges are
UNVERIFIED (OEM handbooks not read).

## Methods and baseline

| Rung | Method | Role in A3 |
|---|---|---|
| SOTA | [M7 GPU granular physics](../methods/m07-gpu-granular-physics.md) | Warp DEM (Hertz–Mindlin with rolling resistance) and Newton implicit MPM for bucket–pile interaction and truck-bed loading |
| Beyond-SOTA (learned) | [M8 GNS surrogate](../methods/m08-gns-surrogate.md) | Message-passing particle surrogate [5][6] trained on M7 rollouts and run live in the browser |
| Beyond-SOTA | [M9 Differentiable DEM calibration](../methods/m09-differentiable-dem-calibration.md) | Friction from repose via the Warp autodiff tape, compared with CMA-ES; deterministic accumulation and FD-vs-run-variance checks [7] |
| SOTA → beyond-SOTA (learned) | [M21 IL-2 excavator](../methods/m21-isaac-lab-policies.md) (+ optional IL-3 loader) | Dig policy on FEE soil, then a zero-shot check in Newton MPM |

**Baselines.** GNS is judged against held-out M7 rollouts. Differentiable calibration is compared with CMA-ES on the
same synthetic truth. IL-2 is compared with a **scripted dig**; "beats scripted dig" only by the decision rule on
fill × cycle time ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

**Pass model.** With heaped bucket volume $V_b$ (m³), fill factor $k_f$ (–), loose density
$\rho_{\text{loose}} = \rho_{\text{bank}}/(1+s_w)$ (t/m³, swell $s_w$) and target payload $M$ (t), the pass count is
$n_p = \lceil M / (V_b\,k_f\,\rho_{\text{loose}}) \rceil$. With independent passes the payload variance grows as
$\sigma_M^2 \approx n_p\,\sigma_{\text{pass}}^2$ — an idealisation that the DEM rollouts test rather than assume.

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Payload CV | % | Standard deviation ÷ mean of truck payloads over the simulated loading sequence |
| Passes per truck | passes | Mean and distribution of $n_p$ from the rollouts |
| Fuel per tonne | L/t | Payload distribution pushed through the [A2](a2-haul-road-electrification.md) haul-energy model on the reference route |
| Fill factor | – | Material mass in the bucket ÷ (heaped volume × loose density), per pass |
| GNS repose / run-out error | ° / % | Surrogate vs held-out solver rollouts on unseen geometries |
| Calibration coverage | % of trials | Trials whose 95 % CI of the recovered friction covers the synthetic truth |
| IL-2 fill success, stalls | % of episodes | Episodes with fill factor ≥ 0.8; episodes that stall |

## Studio tools and artefacts

| Tool | Artefacts it produces for A3 |
|---|---|
| [Warp](../frameworks/warp.md) (`st50_physics`) | DEM runs (Zarr fields, Parquet observables), autodiff calibration traces, replay shards ≤ 10 MB |
| [Newton](../frameworks/newton.md) | Implicit-MPM runs; MPM evaluation tier for IL-2 (`st61_il_mpm_eval`) |
| [MuJoCo-Warp](../frameworks/mujoco-warp.md) | Excavator articulation dynamics |
| [Isaac Lab](../frameworks/isaac-lab.md) (`st60_il_train`) | IL-2 (and optional IL-3) policies as ONNX MLP < 1 MB, episode tables, rollout clips |
| [PyTorch](../frameworks/pytorch.md) / [ONNX Runtime](../frameworks/onnx-runtime.md) | GNS training and export (~3 MB, live) |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Bench face, shovel and truck; payload per pass | LIVE | three.js / R3F |
| Simulate | Granular pile and bucket twin (≤ 2×10⁴ particles) | LIVE | WGSL compute (T1) |
| Simulate | GNS rollout on a user-drawn pile | LIVE | ORT-web, ≤ 50 ms/step target |
| Simulate | IL-2 dig on the TS twin | LIVE | TS twin + ORT-web |
| Studio replay | Warp DEM / Newton MPM particle replays; IL-2 rollout clips | REPLAY | shards ≤ 10 MB; AV1 + H.264 |
| Charts | Payload histogram and CV vs passes; repose calibration fit and loss landscape; IL-2 vs scripted dig with CIs | REPLAY | baked tables |
| Context | Question, impact, honesty notes | STATIC | — |

## Assumptions and limits

- **Everything is synthetic.** The DEM is calibrated to repose targets only; calibration is non-unique in general [4].
- **FEE is quasi-static and continuum.** It does not describe blasted rock with large fragments; the MPM check
  exposes the gap instead of hiding it. IL-2 reports an FEE → MPM sim-to-sim gap with a 95 % CI, not a real-world
  result.
- **Surrogate validity.** GNS results hold only inside the geometry and material range of its training rollouts.
- Validity range: dry, cohesionless or weakly cohesive material; no water content effects.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/a3.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/a3.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- Payload CV, passes per truck and fuel per tonne for the reference pile and bucket.
- GNS on held-out geometries. **Acceptance:** repose within ±1.5°, run-out within ±5 %; ONNX and in-browser parity.
- DEM calibration. **Acceptance:** the 95 % CI of the recovered parameter covers the synthetic truth in ≥ 90 % of
  trials; CMA-ES compared on the same trials.
- IL-2. **Acceptance:** fill factor ≥ 0.8 in ≥ 80 % of FEE episodes; stalls ≤ 5 %; FEE → MPM fill gap reported with a
  95 % CI; "beats scripted dig" only by the decision rule on fill × cycle time. IL-3 is optional and may end as
  "evaluated, not adopted".

## In PitStudio

- Recipe `studio/recipes/cases/a3.yaml`; route `/cases/A3`; model cards [GNS granular](../models/gns-granular.md),
  [DEM calibration](../models/dem-calibration.md), [Isaac Lab policies](../models/isaac-lab-policies.md).
- Physics engine decision: [DEC-0012](../architecture/decisions/DEC-0012-granular-physics-warp-newton.md).

## References

1. International Mining (2016). *Mining3 project looks at effect of payload variance on haul truck fuel consumption*.
   https://im-mining.com/2016/12/07/mining3-project-looks-effect-payload-variance-haul-truck-fuel-consumption/
2. Egli et al. (2022). *Soil-Adaptive Excavation Using Reinforcement Learning*. IEEE RA-L. DOI 10.1109/LRA.2022.3189834
3. Gruetter, Terenzi, Egli, Hutter (2025). *Towards Learning Boulder Excavation …*. https://arxiv.org/abs/2509.17683
4. Coetzee, C. J. (2017). *Review: Calibration of the discrete element method*. Powder Technol. 310:104–142. DOI
   10.1016/j.powtec.2017.01.015
5. Sanchez-Gonzalez et al. (2020). *Learning to Simulate Complex Physics with Graph Networks*. ICML.
   https://arxiv.org/abs/2002.09405
6. Choi, Kumar. *Graph Neural Network-based surrogate model for granular flows*. https://arxiv.org/abs/2305.05218
7. Yang et al. (2026). *On the Numerical Reliability of Differentiable Physics-Based Optimization*.
   https://arxiv.org/abs/2609.34666
