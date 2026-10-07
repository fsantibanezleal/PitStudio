# M11 — Fragmentation: watershed + Swebrec vs a U-Net trained on synthetic muck piles

> Blast fragmentation is measured from images two ways — classical watershed segmentation with a Swebrec fit, and a
> U-Net trained only on rendered muck piles whose size distribution is known exactly — and the synthetic-trained model
> is tested on real labelled rock images, the project's one measured sim-to-real result. · Part of:
> [Methods](README.md) · Related: [Drill and blast theory](../theory/drill-and-blast.md) ·
> [Sim-to-real theory](../theory/sim-to-real.md) · [U-Net card](../models/unet-fragmentation.md) ·
> [Mendeley dataset card](../data-contract/dataset-cards/mendeley-rock-fragments.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical vs beyond-SOTA | **yes** (U-Net) | live | [D1](../cases/d1-blast-muck-pile.md) | TypeScript watershed; `segmentation_models_pytorch` U-Net (MIT) in `pipeline/`; SAM 2.1-tiny (Apache-2.0) as label assistant | not yet implemented |

## What and why

Fragmentation decides how fast shovels dig, how much the crusher sees as oversize and how much energy the mill needs.
Image-based granulometry is the standard way to measure it in the field: WipFrag-style systems segment a photo with
edge detection or watershed and fit a size distribution [3]. Deep segmentation is the current state of the art; a
fine-tuned YOLO12l-seg reached a mask mAP@0.5 of about 0.80 on more than 500 post-blast images [5] (AGPL, so not
usable here).

Real fragmentation datasets share a blind spot: they rarely have a **ground-truth size distribution**, least of all for
fines hidden under larger rocks. A simulated muck pile ([M07](m07-gpu-granular-physics.md)) rendered with RTX has exact
per-fragment ground truth, so the bias from segmentation to PSD can be measured honestly. None of the published work
found does this. M11 therefore asks two questions:

1. Does a U-Net trained **only on synthetic** muck piles segment **real** rock images almost as well as one trained on
   real images? (TSTR vs TRTR.)
2. Does it estimate the median fragment size better than the classical watershed + Swebrec pipeline?

## The algorithm

### Classical pipeline: watershed + Swebrec

```text
classical_psd(image):
    g  = denoise(grey(image))
    fg = threshold(g)                                  # rock vs background/shadow
    d  = distance_transform(fg)
    markers = local_maxima(d, min_distance)
    labels  = watershed(-d, markers, mask=fg)          # one label per fragment
    sizes   = [2*sqrt(area(l)/pi) for l in labels]     # equivalent diameter (px or m)
    return fit_swebrec(cumulative_area_passing(sizes))
```

The equivalent diameter of a fragment of projected area $A$ is $d_{\text{eq}} = 2\sqrt{A/\pi}$. The cumulative
distribution is area-weighted, a 2-D proxy for the mass-weighted sieve curve (a known bias of all image methods). The
fit uses the **Swebrec** function [4]:

$$
P(x) = \frac{1}{1 + \left[\dfrac{\ln(x_{\max}/x)}{\ln(x_{\max}/x_{50})}\right]^{b}}, \qquad 0 < x \le x_{\max}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $P(x)$ | fraction passing size $x$ | – |
| $x_{50}$ | median fragment size | m (px on unscaled images) |
| $x_{\max}$ | maximum fragment size | m (px) |
| $b$ | undulation parameter | – |

**Worked example (illustrative parameters).** With $x_{50} = 0.25$ m, $x_{\max} = 1.5$ m and $b = 2$:
$P(0.10\ \text{m}) = 1/\big(1 + [\ln 15/\ln 6]^2\big) = 1/(1 + 1.511^2) = 0.304$, and solving $P(x_{80}) = 0.8$ gives
$\ln(x_{\max}/x_{80}) = \ln 6 \times 0.25^{1/2}$, so $x_{80} = 1.5/\sqrt{6} = 0.61$ m. The [M12](m12-blast-fragmentation-models.md)
prediction from blast design uses the same function, which lets the measured and predicted curves be compared
directly.

### Learned pipeline: U-Net

- **Architecture:** U-Net [1] — a convolutional encoder–decoder with skip connections — from
  `segmentation_models_pytorch` 0.5.0 (MIT; "ONNX export … friendly") [2] with an ImageNet-pretrained encoder (the
  encoder weights' licence is traced per encoder and recorded in the model card; UNVERIFIED until then).
- **Input / output:** an RGB tile (512 × 512) → per-pixel class probabilities for fragment interior, fragment boundary
  and background (planned head, fixed in the spec). Instances are the connected interior regions grown to the
  boundaries; sizes and the Swebrec fit follow as in the classical pipeline.
- **Loss:** pixel-wise softmax cross-entropy with a weight map that emphasises the thin separation borders between
  touching objects, as in the original U-Net [1].
- **Training data (TSTR arm):** synthetic muck piles from [M07](m07-gpu-granular-physics.md) rendered in Isaac Sim with
  exact instance masks and exact PSD, including fragments hidden from the camera.
- **Training data (TRTR arm):** the real Mendeley images (below), training folds only.
- **Label assistant:** SAM 2.1-tiny (Apache-2.0) [6] helps inspect and correct masks; it is not a model under test.
- **Budget:** 2–4 GPU-hours, 5–7 GB of VRAM (estimate; measured by the `studio bench` probe first).

### The real test set

The real reference is the Mendeley "Rock fragment image segmentation" dataset (CC BY 4.0) [7][8], checked at bootstrap
(SHA-256 pinned):

| Fact | Value |
|---|---|
| Images | 960 RGB at 512 × 512 = **240 originals × 4** (original, horizontal flip, vertical flip, 180° rotation) |
| Labels | indexed instance masks, **one class** (rock) |
| Instances | 63,144 in the 960 masks (mean 65.8, median 58 per image) → **15,786 unique** |
| Size spread | equivalent diameter p10 / p50 / p90 = 11 / 32 / 82 px |
| Independence | no pixel-level overlap among the originals; 9 visually similar pairs merged conservatively → **231 source groups** |
| Physical scale | **none** (no mm per px) |

Consequences, fixed before the comparison is run:

1. **Split by source group, never by file** — a per-file split would put flipped copies of test tiles into training
   and inflate TRTR.
2. **Evaluate on originals only** (the effective real set is 240 tiles, not 960).
3. **Grouped k-fold** (for example 5 folds) instead of one 80/20 split, reporting the TSTR/TRTR ratio with its fold
   spread.
4. **Sizes in pixels** on real data; real-world sizes need a stated scale assumption (D1 card).

### Metrics

- **Foreground IoU** on the real test folds: $\text{IoU} = \lvert P \cap G\rvert / \lvert P \cup G\rvert$ over rock
  pixels.
- **TSTR / TRTR:** IoU of the synthetic-trained model divided by IoU of the real-trained model on the same test folds
  (train-synthetic-test-real vs train-real-test-real [9]).
- **x50 relative error:** $\lvert \hat x_{50} - x_{50}\rvert / x_{50}$, against the exact PSD on synthetic held-out
  piles, and against the size distribution of the labelled instances on real images (pixels).

## Baseline and comparison

- **Classical baseline:** the watershed + Swebrec pipeline above, on the same images.
- **Paired comparison:** per test image, the absolute x50 error of the U-Net and of the classical pipeline; "beats
  watershed + Swebrec" only by the [decision rule](README.md#how-methods-are-compared) on the paired differences.
- **Sim-to-real:** TSTR vs TRTR as above. This is the one place in PitStudio where a real labelled training set
  exists, so it is the project's **measured** sim-to-real result.
- **Image realism:** classifier two-sample tests on DINOv2 embeddings of synthetic vs real fragment images, with a
  real-vs-real baseline, are reported alongside (data validation; see [sim-to-real theory](../theory/sim-to-real.md)).

## Acceptance criterion (pre-registered)

- **Synthetic held-out x50 relative error ≤ 15 %.**
- **Real test split: TSTR ≥ 0.90 × TRTR (IoU).**
- **"Beats watershed + Swebrec" only by the decision rule on x50 error.**
- Export parity: fp32 rtol 1e-3 / atol 1e-5; int8 Δ ≤ 1 pp on IoU and PSD error, or the variant is reported as rejected.

**Results: Not yet run** — produced in the data-and-models phase. Reported: TSTR/TRTR with fold spread, x50 errors for
both pipelines with the paired CI, PSD curves against exact synthetic truth, and the int8 accuracy delta.

## Lane and web delivery

**Live.** The U-Net is exported to ONNX and quantised to int8 (5–15 MB) for ONNX Runtime Web; the watershed runs in a
TypeScript worker. A visitor can drop a muck-pile photo, see both segmentations and both PSD curves, and move the
scale assumption. Gate: each live model ≤ 25 MB and ≤ 300 ms per image on the WebGPU tier (estimate). Fallback:
precomputed outputs.

## Assumptions and limits

- 2-D surface images see only the visible face of the pile; hidden fines are exactly what synthetic ground truth
  quantifies, but real images cannot show them.
- The real set has one class, no scale, and 231 independent source groups — a small test set, hence the grouped
  folds.
- The synthetic renderer and material are calibrated, not photographs: the TSTR/TRTR ratio *is* the measured gap.
- Educational, not a blasting-QA product.

## In PitStudio

- **Cases:** [D1](../cases/d1-blast-muck-pile.md) (P80, % oversize, measured sim-to-real); its PSDs feed
  [M17](m17-comminution-mine-to-mill.md).
- **Code (planned):** muck-pile physics in `studio/` (`st50_physics`), renders in `studio/isaac/` (`st52_rtx_render`);
  real-data ingestion `s00_download` and `s10_preprocess`; training and evaluation `s30_train`, `s50_evaluate`; export
  `s60_export`; TypeScript watershed in a `web/` worker; Swebrec in `minephys.blasting`. Card:
  [U-Net fragmentation](../models/unet-fragmentation.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Ronneberger, O., Fischer, P. & Brox, T. (2015). *U-Net: Convolutional Networks for Biomedical Image Segmentation*.
   MICCAI. https://arxiv.org/abs/1505.04597
2. `segmentation_models_pytorch` 0.5.0 (MIT). https://pypi.org/pypi/segmentation-models-pytorch/json
3. Maerz, N. H., Palangio, T. C. & Franklin, J. A. *WipFrag image based granulometry system*.
   https://doi.org/10.1201/9780203747919-15
4. Ouchterlony, F. (2005). The Swebrec function: linking fragmentation by blasting and crushing. Mining Technology
   114(1):29–44. https://doi.org/10.1179/037178405X44539
5. Yang (2025). Automated deep segmentation for post-blast fragmentation (YOLO12l-seg, mask mAP@0.5 ≈ 0.80).
   https://arxiv.org/abs/2507.20126
6. SAM 2 / 2.1 (Apache-2.0 code and checkpoints). https://github.com/facebookresearch/sam2
7. Si, Zhu, Di & Wang (2019). Rock fragment image segmentation combining CNN and watershed algorithm (Mendeley Data,
   CC BY 4.0). https://data.mendeley.com/datasets/78ht3pjsr4/1
8. Mendeley public API — file list, size and SHA-256 of the archive.
   https://data.mendeley.com/public-api/datasets/78ht3pjsr4/files?folder_id=root&version=1
9. Esteban, C., Hyland, S. L. & Rätsch, G. (2017). Real-valued (medical) time series generation with recurrent
   conditional GANs — TSTR/TRTS definition. https://arxiv.org/abs/1706.02633
