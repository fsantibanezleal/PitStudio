# D1 — Blast design and muck pile

> What fragmentation, vibration and flyrock does a blast design produce — and can a segmentation model trained only on
> synthetic muck piles with exact size distributions measure real fragmentation? The one case with a measured
> sim-to-real gap. · Part of: [Cases](README.md) · Related: [Drill and blast](../theory/drill-and-blast.md) ·
> [M11 Fragmentation segmentation](../methods/m11-fragmentation-segmentation.md) ·
> [U-Net fragmentation](../models/unet-fragmentation.md) ·
> [Mendeley card](../data-contract/dataset-cards/mendeley-rock-fragments.md)

## What and why

**The question.** A drill-and-blast engineer changes burden, spacing, hole diameter or explosive and asks: what
median and P80 fragment size, how much oversize, what peak particle velocity (PPV) at the nearest structure, and how
far can flyrock travel? After the blast, the same engineer photographs the muck pile and asks whether the image-based
size distribution can be trusted. The AI practitioner's version: **does a segmenter trained only on synthetic muck
piles, where every fragment size is known, work on real muck-pile photographs?**

**Why it matters.**

- Flyrock and lack of blast-area security caused more than two-thirds of blasting-related injuries in US surface
  coal, metal and non-metal mines over 1978–2002 [1].
- Regulated vibration limits are tight: US surface-mining rules cap PPV at 1.25, 1.00 and 0.75 in/s at 0–300 ft,
  301–5,000 ft and beyond 5,001 ft [2]; the USBM study of 219 production blasts and 76 homes put safe levels at
  0.5–2.0 in/s depending on frequency [3].
- Fragmentation drives loading ([A3](a3-loading-payload-variance.md)) and milling ([D2](d2-mine-to-mill.md)).
- Image granulometry has a known bias: real images lack ground-truth size distributions, especially for occluded
  fines, and prior synthetic-muck-pile work reports watershed methods over-counting fragments 1.5–2.5× [4].

## Site and data

**Real labelled images — Mendeley rock-fragment set** (Si, Zhu, Di, Wang 2019; CC BY 4.0; DOI 10.17632/78ht3pjsr4.1)
[5]. One archive of 4,230,116,058 bytes, SHA-256 `7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d`,
verified on download. Facts from the data check of the first milestone:

| Fact | Value |
|---|---|
| Images | 960 RGB tiles, all 512 × 512 px |
| Structure | **240 originals × 4 dihedral augmentations**: 001–240 originals; 241–480 horizontal flips; 481–720 vertical flips; 721–960 180° rotations (verified: normalised correlation 1.000 and label IoU 1.000 for all 240 × 3 pairs) |
| Near-duplicates | No pixel-level overlap among the 240 originals (high-pass correlation test); 9 visually similar pairs are merged conservatively → **231 source groups** (240 without the merge) |
| Labels | one class (rock); indexed instance masks (0 = background, *k* = instance *k*) from labelme's dataset export; the original polygon files are not included |
| Instances | 63,144 in the 960 masks (mean 65.8, median 58 per image) → **15,786 unique** |
| Instance size | area p10 / p50 / p90 = 102 / 807 / 5,298 px; equivalent diameter p10 / p50 / p90 = 11 / 32 / 82 px |
| Physical scale | **none** (no mm per px anywhere in the archive) |

**Synthetic muck piles with exact PSD.** Warp DEM piles whose fragments are drawn from Kuz-Ram / Swebrec
distributions, rendered in Isaac Sim with instance masks, so every fragment's size is known. CC-BY-4.0
([synthetic-data](../data-contract/dataset-cards/synthetic-data.md)).

**Split protocol (fixed before any training).**

- **Split by source group, never by file.** Group key = $((k-1) \bmod 240) + 1$, merged with the 9 conservative similarity links. A
  per-file split would put flipped copies of test tiles into training and inflate TRTR.
- **Grouped k-fold** (e.g. 5 folds over the ~231 groups): a single 80/20 split would leave only about 46 test tiles.
- **Test on originals only** (tiles 001–240 that fall in the test groups). Training may use the shipped flips or its
  own augmentation; the effective real set is 240 tiles, not 960.
- Only metrics derived from these images are committed; no Mendeley image is redistributed by the web app.

## Methods and baseline

| Rung | Method | Role in D1 |
|---|---|---|
| Classical | [M12 Kuz-Ram / KCO + Swebrec + PPV + flyrock](../methods/m12-blast-fragmentation-models.md) | Design → fragmentation curve, vibration and flyrock envelope |
| Classical vs beyond-SOTA (learned) | [M11 Watershed + Swebrec vs U-Net on exact-PSD synthetic piles](../methods/m11-fragmentation-segmentation.md) | Image → instance masks → size distribution; smp U-Net [6][7]; SAM 2.1-tiny as a label assistant [8] |
| SOTA | [M7 GPU granular physics](../methods/m07-gpu-granular-physics.md) | Warp DEM muck-pile throw and settling, the source of the synthetic piles |

**Design models** (transcriptions pinned against the primary texts at specification):

- Kuznetsov mean size $x_{50} = A\,K^{-0.8}\,Q^{1/6}\,(115/RWS)^{19/30}$ (cm), with rock factor $A$ (–), powder
  factor $K$ (kg/m³), charge per hole $Q$ (kg) and relative weight strength $RWS$ (ANFO = 100) [9][10].
- Swebrec passing fraction $P(x) = 1/\{1 + [\ln(x_{\max}/x)/\ln(x_{\max}/x_{50})]^{b}\}$ (–) for
  $0 < x \le x_{\max}$, with fragment size $x$ and maximum size $x_{\max}$ (cm, same unit as $x_{50}$) and
  undulation $b$ (–) [11].
- Scaled-distance PPV $= K_s\,(D/\sqrt{W})^{-\beta}$ (mm/s), with distance $D$ (m), maximum charge per delay $W$ (kg)
  and site constants $K_s$ (mm/s) and $\beta$ (–), both fitted inputs.
- Flyrock as a ballistic trajectory with aerodynamic drag, driven by launch velocity [12].

**Two pre-registered comparisons** (see the diagram):

1. **TSTR vs TRTR.** A U-Net **trained on synthetic** and a U-Net **trained on real** (grouped folds) are both tested
   on the real originals of each test fold; the metric is foreground IoU [13].
2. **U-Net vs watershed + Swebrec** on x50 error; "beats watershed + Swebrec" only by the decision rule
   ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

![D1 TSTR vs TRTR design with grouped folds](../assets/diagrams/case-d1-tstr-design.svg)

*D1 evaluation design: synthetic exact-PSD piles and grouped Mendeley folds train two U-Nets; both are scored on real
originals only; the watershed + Swebrec baseline is compared on x50.*

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| x50, P80 | cm (design models); px on Mendeley images | Size at 50 % / 80 % passing of the predicted or measured distribution |
| % oversize | % | $1 - P(x_{\text{os}})$ for an oversize limit $x_{\text{os}}$ (input, e.g. crusher gape) |
| PPV | mm/s (and in/s) | Scaled-distance law at receiver distances |
| Flyrock radius | m | Maximum drag-ballistic range over launch angles for a launch-velocity input |
| TSTR / TRTR | ratio (–) | Mean foreground IoU of the synthetic-trained U-Net ÷ that of the real-trained U-Net, per fold, on real originals |
| x50 error | % (synthetic, physical units); % (real, px) | $\lvert \hat x_{50} - x_{50} \rvert / x_{50}$ against exact synthetic truth, or against the labelled masks on real tiles |

## Studio tools and artefacts

| Tool | Artefacts it produces for D1 |
|---|---|
| [Warp](../frameworks/warp.md) DEM (`st50_physics`) | Muck-pile particle states with per-fragment sizes (Zarr); throw replay shards |
| [Isaac Sim + Replicator](../frameworks/isaac-sim-replicator.md) (`st55_sdg`) | Muck-pile renders with instance masks and exact PSD labels |
| [TensorRT](../frameworks/tensorrt.md) (`s62_accel`, `s64_bench`) | U-Net engines (local) with published latency and parity tables |
| [PyTorch](../frameworks/pytorch.md) / [ONNX Runtime](../frameworks/onnx-runtime.md) | U-Net training (TS and TR arms); int8 export 5–15 MB, live |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Blast pattern on a design-code bench (labelled as regenerated) | LIVE | three.js / R3F |
| Simulate | Kuz-Ram / Swebrec / PPV / flyrock calculators | LIVE | TS port of `minephys.blasting`; Pyodide button |
| Simulate | Watershed vs U-Net on sample **synthetic** muck-pile renders | LIVE | TS watershed; ORT-web U-Net int8 |
| Studio replay | DEM muck-pile throw; Isaac Sim muck renders | REPLAY | shards; AV1 + H.264 |
| Charts | PSD curves (truth, U-Net, watershed + Swebrec); TSTR vs TRTR per fold; x50 error with CIs; TensorRT table | REPLAY | baked metrics |
| Context | Question, impact, data facts, honesty notes | STATIC | — |

## Assumptions and limits

- **No physical scale in the real data.** Real-image PSD comparisons are in pixels or relative (x50 / x80 ratios,
  curve shape). Any real-world size needs a stated scale assumption.
- **Surface view only.** Images see the pile surface; occluded fines are invisible to both methods.
- **Design models are site-calibrated regressions.** Rock factor, uniformity and PPV constants vary by site.
- **Small real set.** 240 effective tiles in ~231 groups; the TSTR/TRTR ratio is reported with its fold spread.
- Educational, not blast-design software; no regulatory PPV or flyrock clearance is implied.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/d1.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/d1.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

`s00_download` fetches the Mendeley archive into `PITSTUDIO_DATA` and verifies it against the pinned SHA-256.

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported, with acceptance criteria:

- **TSTR ≥ 0.90 × TRTR (foreground IoU) on the real test originals**, as mean and fold spread over the grouped folds.
- Synthetic held-out x50 relative error **≤ 15 %**.
- U-Net vs watershed + Swebrec on x50 error: "beats" only if the paired 95 % CI excludes 0.
- Synthetic-vs-real image C2ST on DINOv2 embeddings against a real-vs-real baseline (gap ≤ 0.10), duplicate scans and
  an injected-shift check; ONNX and TensorRT per-engine parity.

## In PitStudio

- Recipe `studio/recipes/cases/d1.yaml`; route `/cases/D1`; model card [U-Net fragmentation](../models/unet-fragmentation.md).
- Feeds fragmentation to [D2](d2-mine-to-mill.md); dataset card [Mendeley rock fragments](../data-contract/dataset-cards/mendeley-rock-fragments.md).

## References

1. Bajpayee, Lobb, Verakis (2004). *An Analysis and Prevention of Flyrock Accidents in Surface Blasting Operations*.
   NIOSH. https://stacks.cdc.gov/view/cdc/220760
2. 30 CFR § 816.67, *Use of explosives: control of adverse effects*. https://www.law.cornell.edu/cfr/text/30/816.67
3. Siskind, Stagg, Kopp, Dowding (1980). US Bureau of Mines Report of Investigations 8507.
   https://www.osti.gov/biblio/6777883
4. *FragmentIQ: The Systematic Bias of Image-Based Muckpile Fragmentation Analysis, and Its Correction* (v1.2).
   Zenodo, CC BY 4.0. https://zenodo.org/records/22834568
5. Si, Zhu, Di, Wang (2019). *Rock fragment image segmentation combining CNN and watershed algorithm*. Mendeley Data,
   CC BY 4.0. DOI 10.17632/78ht3pjsr4.1. https://data.mendeley.com/datasets/78ht3pjsr4/1
6. Ronneberger, Fischer, Brox (2015). *U-Net*. MICCAI. https://arxiv.org/abs/1505.04597
7. segmentation-models-pytorch (MIT). https://pypi.org/pypi/segmentation-models-pytorch/json
8. Meta AI. *SAM 2* (Apache-2.0). https://github.com/facebookresearch/sam2
9. Kuznetsov (1973). *The mean diameter of the fragments formed by blasting rock*. Soviet Mining Science 9:144–148.
   DOI 10.1007/BF02506177
10. Ouchterlony, Sanchidrián (2019). *A review of development of better prediction equations for blast
    fragmentation*. JRMGE 11(5):1094–1109. DOI 10.1016/j.jrmge.2019.03.001
11. Ouchterlony (2005). *The Swebrec function: linking fragmentation by blasting and crushing*. Mining Technology
    114(1):29–44. DOI 10.1179/037178405X44539
12. Szendrei, Tose (2022). *Flyrock in surface mining — limitations of predictive models*. JSAIMM 122(12):725–732.
    DOI 10.17159/2411-9717/1873/2022
13. Esteban, Hyland, Rätsch (2017). Real-valued (medical) time series generation with recurrent conditional GANs
    (TSTR / TRTS definition). https://arxiv.org/abs/1706.02633
