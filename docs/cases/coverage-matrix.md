# Coverage matrix — methods × cases

> Which of the 23 methods each case exercises, so that every method in the ladder is used by at least one real
> operational question. · Part of: [Cases](README.md) · Related: [Methods](../methods/README.md) ·
> [Tool matrix](tool-matrix.md) · [Compute lanes](../pipelines/compute-lanes.md)

## What and why

The method ladder ([M1–M23](../methods/README.md)) runs from classical engineering models through state-of-the-art
practice to beyond-state-of-the-art learned methods. A method that no case uses would be an orphan: it would have
no KPI, no baseline and no web workbench to show it. This matrix proves the opposite: **every method appears in at
least one case**, and every case combines a classical baseline with at least one higher rung.

The web version of this table (`/cases`, "Coverage" tab) is **generated from the case registry**, the same file that
generates the catalogue and the [tool matrix](tool-matrix.md). This page mirrors the approved case definitions; if
the two ever disagree, the registry is wrong and is fixed, not this page.

## Matrix

● = the method is part of the case's method list. Columns are the 12 cases; rows are the 23 methods.

| Method | Tier | A1 | A2 | A3 | B1 | B2 | C1 | C2 | C3 | D1 | D2 | E1 | E2 | Cases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [M1](../methods/m01-match-factor-queueing.md) Match factor + finite-source queue / MVA | classical | ● | | | | | | | | | | | | 1 |
| [M2](../methods/m02-haulage-des.md) Haulage DES, classical dispatchers | classical | ● | ● | | ● | | | | ● | | | | | 4 |
| [M3](../methods/m03-lp-dispatch.md) Two-stage LP dispatch | classical / industry SOTA | ● | | | | | | | | | | | | 1 |
| [M4](../methods/m04-ppo-dispatch.md) PPO dispatch, GPU-vectorised env (learned) | SOTA | ● | | | | | | | | | | | | 1 |
| [M5](../methods/m05-attention-fleet-policy.md) Attention fleet policy (learned) | beyond-SOTA | ● | | | | | | | | | | | | 1 |
| [M6](../methods/m06-haul-road-energy-routing.md) Haul-road energy + grade-constrained routing | classical | | ● | | | | | | | | | ● | | 2 |
| [M7](../methods/m07-gpu-granular-physics.md) GPU granular physics (Warp DEM + Newton MPM) | SOTA | | | ● | | | | | | ● | | | | 2 |
| [M8](../methods/m08-gns-surrogate.md) GNS granular surrogate in the browser (learned) | beyond-SOTA | | | ● | | | | | | | | | | 1 |
| [M9](../methods/m09-differentiable-dem-calibration.md) Differentiable DEM calibration vs CMA-ES | beyond-SOTA | | | ● | | | | | | | | | | 1 |
| [M10](../methods/m10-synthetic-data-detector.md) Synthetic-data detector + DR ablation (learned) | SOTA | | | | | ● | | | | | | | | 1 |
| [M11](../methods/m11-fragmentation-segmentation.md) Watershed + Swebrec vs U-Net on exact-PSD piles (learned) | classical vs beyond-SOTA | | | | | | | | | ● | | | | 1 |
| [M12](../methods/m12-blast-fragmentation-models.md) Kuz-Ram/KCO + Swebrec + PPV + flyrock | classical | | | | | | | | | ● | ● | | | 2 |
| [M13](../methods/m13-slope-stability-lem.md) LEM + Hoek–Brown + Monte-Carlo PoF | classical | | | | | | ● | | | | | | | 1 |
| [M14](../methods/m14-slope-forecasting.md) Inverse velocity + Bayesian TTF vs TCN / PatchTST / Chronos-Bolt (learned) | classical vs SOTA | | | | | | ● | | | | | | | 1 |
| [M15](../methods/m15-shallow-water-fno.md) GPU shallow water + FNO surrogate (learned) | SOTA + learned | | | | | | | ● | | | | | | 1 |
| [M16](../methods/m16-dust-dispersion.md) AP-42 + Gaussian plume + Lagrangian dust | classical / SOTA | | | | | | | | ● | | | | | 1 |
| [M17](../methods/m17-comminution-mine-to-mill.md) Bond/Morrell + PBM + mine-to-mill meta-model (learned) | classical + learned | | | | | | | | | | ● | | | 1 |
| [M18](../methods/m18-pit-optimisation-scheduling.md) Min-cut ultimate pit + nested shells + MILP | classical / SOTA | | | | | | | | | | | ● | | 1 |
| [M19](../methods/m19-gaussian-splat-survey.md) COLMAP → 3D Gaussian splats → volume (learned reconstruction) | SOTA | | | | | | | | | | | | ● | 1 |
| [M20](../methods/m20-traffic-ttc.md) Agent traffic + TTC + rigid-body vehicles | classical / SOTA | | | | ● | | | | | | | | | 1 |
| [M21](../methods/m21-isaac-lab-policies.md) Isaac Lab policies IL-1 / IL-2 / IL-3 (learned) | SOTA → beyond-SOTA | | ● | ● | | | | | | | | | | 2 |
| [M22](../methods/m22-cosmos-vlm-tasks.md) Cosmos Reason 2 VLM tasks (learned, zero-shot) | frontier | | | | ● | ● | | | | | | | | 2 |
| [M23](../methods/m23-rtx-sensor-simulation.md) RTX sensor simulation + own dust / slope-radar models | SOTA | | | | ● | ● | ● | | | | | | ● | 4 |
| **Methods per case** | | **5** | **3** | **4** | **4** | **3** | **3** | **1** | **2** | **3** | **2** | **2** | **2** | **34** |

Coverage check: 23 of 23 methods appear in at least one case. 11 methods are learned (M4, M5, M8, M10, M11, M14,
M15, M17, M19, M21, M22), and each of them is compared against a classical or simpler baseline in its case.

## Reading the matrix

- **Classical rungs anchor every case.** Each case has at least one classical or industry-practice method that
  serves as its baseline or as its ground-truth generator: M1/M2/M3 (A1), M6 (A2, E1), M7 with literature repose
  targets (A3), M2/M20 (B1), the structured-vs-unstructured DR arm (B2), M13 and inverse velocity (C1), the solver
  itself as FNO reference (C2), M16 (C3), M12 and watershed (D1), the analytical Bond/Morrell chain (D2), oracle
  min-cut solvers (E1) and DEM differencing (E2).
- **Learned rungs are judged by one rule.** A learned method is called better than its baseline only if the paired
  95 % confidence interval of the difference excludes 0 ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).
  The pairs are case-specific: seeds or seeded episodes (A1, A2, A3), seeded synthetic events (C1), grouped folds
  (D1). Surrogates (C2, D2) are judged against their own solver on held-out terrains or sweeps, and the VLM
  comparison (B1, B2) uses a paired McNemar test (p < 0.05).
- **Multi-case methods are shared engines.** M2 (the haulage DES) feeds A1 dispatch, A2 cycle energy, B1 traffic
  schedules and C3 vehicle-kilometres. M23 (sensors) serves B1 (truck lidar and radar), B2 (crusher camera), C1
  (analytical slope radar) and E2 (drone camera). M12 serves D1 directly and D2 through the fragmentation it
  hands to the mill.
- **Optional frontier pieces carry no headline KPI.** M22 (Cosmos Reason 2) and the MPM fine-tuning part of M21 have
  fallbacks that the open lane reproduces; no case's headline KPI depends on them.

## Lanes per method

The lane says how each method reaches the web ([Compute lanes](../pipelines/compute-lanes.md)).

| Lane | Methods |
|---|---|
| live | M1, M6, M11 (watershed + U-Net), M12, M13, M14, M17 |
| live + precompute | M2, M3 (small LP live), M16, M18 (≤ 10⁵ blocks live) |
| precompute → live | M4, M5, M8, M10 (ORT-web), M15, M21 (TS twins) |
| replay + live WGSL twin | M7 |
| live + replay | M20 |
| precompute (baked, viewed live) | M9, M19 (view + live volume) |
| precompute, display-only | M22 |
| precompute; live dust slider (own model) | M23 |

## Assumptions and limits

- The matrix lists methods by case, not effort: a ● in a single-method column (C2) can be a larger workload than five
  marks in another (A1).
- A method listed in a case may still be "not yet run" for that case; the run status lives in the run ledger
  (`/studio/runs`), not here.
- The optional pieces (M22; IL-3 and the MPM fine-tune inside M21) can end as "evaluated, not adopted" without
  changing any other mark.

## In PitStudio

- Source of truth: the case registry, rendered to `/cases` and checked so that every M1–M23 row has at least one ●.
- Every method page links back to the cases in its row; every case page links forward to its methods.

## References

No external figures are used on this page. The method sources are on each [method page](../methods/README.md).
