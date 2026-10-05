# U-Net fragmentation segmenter

> A small U-Net that segments rock fragments in muck-pile images and turns them into a size distribution, trained on
> synthetic muck piles with exact PSD and measured against real labelled images — PitStudio's one measured sim-to-real
> gap. · Part of: [Models](README.md) · Related:
> [M11 Fragmentation segmentation](../methods/m11-fragmentation-segmentation.md) ·
> [Case D1](../cases/d1-blast-muck-pile.md) ·
> [Mendeley rock fragments](../data-contract/dataset-cards/mendeley-rock-fragments.md) ·
> [Sim-to-real](../theory/sim-to-real.md)

## What and why

Blast results are judged by the fragment size distribution (PSD) of the muck pile: its median size $x_{50}$, its
$x_{80}$ and the oversize fraction. Image granulometry estimates the PSD from photos; the classical route segments the
image with edge detection and watershed and fits a distribution [1]. Real fragmentation photos rarely come with a
true PSD, least of all for hidden fines, so a learned segmenter is usually judged only by how its masks look. PitStudio
renders simulated muck piles whose **every fragment size is known**, trains a U-Net on them, and then asks the honest
question on **real labelled images**: does training on synthetic data get within 90 % of training on real data
(TSTR vs TRTR)?

## Model card

### Intended use

- Per-image fragment segmentation of muck-pile surfaces and the derived PSD ($x_{50}$, $x_{80}$, oversize share) in
  case D1, compared with watershed + Swebrec.
- A measured sim-to-real ratio on the real Mendeley test folds.
- An INT8 TensorRT case study: per-bucket PSD at video rate (acceleration tables).

### Out of scope

- Absolute fragment sizes on the real images: the Mendeley archive has **no physical scale** (mm per px), so real
  $x_{50}$ is in pixels or relative ($x_{50}/x_{80}$, curve shape). A scale assumption, if used, is stated in the D1
  card.
- Fines below the image resolution and fragments hidden inside the pile: any image method sees the surface only.
- Blast design or regulatory use; outputs are educational.

### Architecture

U-Net is an encoder–decoder with skip connections between matching resolutions [2]. PitStudio uses the
`segmentation_models_pytorch` (smp) 0.5.0 implementation (MIT) with an ImageNet-pretrained ResNet or EfficientNet
encoder, about 5–15 M parameters (UNVERIFIED — measured when the encoder is fixed) [3]. The network outputs per-pixel
class scores; the label scheme (for example fragment interior, fragment boundary and background, so that touching
fragments separate) is fixed in the fragmentation spec. Training minimises cross-entropy plus a soft Dice term [4]:

$$
\mathcal L=\mathcal L_{\text{CE}}+\Big(1-\frac{2\sum_u p_u g_u+\varepsilon}{\sum_u p_u+\sum_u g_u+\varepsilon}\Big),
\qquad
\mathrm{IoU}=\frac{|P\cap G|}{|P\cup G|}
$$

$p_u\in[0,1]$ is the predicted fragment probability at pixel $u$, $g_u\in\{0,1\}$ the label, $\varepsilon$ a smoothing
constant, and $P$, $G$ the predicted and labelled fragment-foreground pixel sets. **Foreground IoU** is the metric of the
TSTR/TRTR criterion.

**From masks to a PSD.** Each fragment instance $k$ with area $A_k$ (px²) gets an equivalent diameter
$d_k=2\sqrt{A_k/\pi}$ (px). The cumulative passing curve $P(x)$ is built from the $d_k$ with a size weighting fixed in
the spec, and $x_{50}$ is the size at $P=0.5$. Worked check on the real labels (bootstrap data check): instance areas at
the 10th / 50th / 90th percentiles of 102 / 807 / 5,298 px² give $d$ = 11 / 32 / 82 px, matching the recorded diameter
percentiles. The classical baseline fits the Swebrec function to the watershed sizes [5][6]:

$$
P(x)=\frac{1}{1+\left[\dfrac{\ln(x_{\max}/x)}{\ln(x_{\max}/x_{50})}\right]^{b}},\qquad 0<x\le x_{\max}
$$

with $x_{\max}$ the largest fragment size and $b$ the curve-shape parameter (–). The same fit is applied to U-Net
instances so both methods report $x_{50}$ the same way.

### Training data

| Source | Content | Split | Licence |
|---|---|---|---|
| Synthetic muck piles | Warp DEM piles rendered by Isaac Sim, exact per-fragment PSD and instance masks | held-out by pile seed | ours, CC-BY-4.0 |
| Mendeley `78ht3pjsr4` (Si, Zhu, Di, Wang 2019) [7] | 960 RGB images, 512 × 512, one class (`rock-N`), indexed instance masks | **grouped** (below) | CC BY 4.0 |

Bootstrap data check of the Mendeley archive (SHA-256 verified, 4,230,116,058 bytes): the 960 images are **240
originals × 4** (horizontal flip, vertical flip, 180° rotation), verified exactly; no pixel-level overlap among the originals; 9 visually
similar pairs merged conservatively leave **231 source groups**; 63,144 labelled instances (15,786 unique). Consequences fixed for evaluation:

- **Split by source group, never by file.** A per-file split would put flipped copies of test tiles into training and
  inflate TRTR.
- **Test on originals only.** With ~231 groups an 80/20 split leaves about 46 test tiles, so a **grouped k-fold** (e.g.
  5 folds) is used and the ratio is reported with its fold spread.

**SAM 2.1-tiny** (38.9 M parameters, Apache-2.0 + BSD-3) serves offline as a label assistant only; it is never the
evaluated model and never produces the real test labels [8]. Card: [Mendeley rock fragments](../data-contract/dataset-cards/mendeley-rock-fragments.md).

### Budget (estimate)

**2–4 GPU-h, 5–7 GB VRAM** (about 5k tiles × 100 epochs at 512², fp16/bf16 mixed precision). Measured by the runner
probe `studio bench` before any long run; the GPU probes are written but not yet run on the reference machine.

### Export and web lane

- **Opset 17**: a convolutional graph with no `GridSample` and no need for FP8 (TensorRT has no optimised FP8 group or
  depthwise convolutions on Ada and recommends INT8 for such ConvNets [9]). IR version **pinned to 10**;
  `torch.onnx.export(dynamo=True, verify=True)`, onnxslim.
- Parity: ONNX Runtime CPU fp32 vs PyTorch fp32 on ≥ 200 golden tiles (rtol 1e-3 / atol 1e-5 / max abs 1e-4); int8
  (static QDQ, per-channel weights) accepted only if IoU moves ≤ 1 pp and masks keep IoU ≥ 0.99 against fp32.
- Sizes (estimate): 20–60 MB fp32, 10–30 MB fp16, **5–15 MB int8 → LIVE** in ORT-web (WebGPU, WASM fallback). Whether
  the decoder's upsampling ops have WebGPU kernels in ORT 1.30 is UNVERIFIED; unsupported nodes fall back to WASM and
  the in-browser parity test decides. Gate: ≤ 25 MB.
- **TensorRT relevance — the best INT8 candidate:** a CNN with static shapes. Expected 3–8× over PyTorch eager
  (estimate), consistent with the 1.5–3.3× INT8-over-FP32 range reported for detectors [10]. Per-engine parity on every
  TensorRT version ([DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)).

### Pre-registered acceptance criteria

- Synthetic held-out **$x_{50}$ relative error ≤ 15 %**: $|\hat x_{50}-x_{50}|/x_{50}\le 0.15$ against the generator's
  exact PSD.
- **Real test split: TSTR ≥ 0.90 × TRTR (IoU)** — foreground IoU of the synthetic-trained model on the real test
  originals ≥ 0.90 × that of the real-trained model, per grouped fold.
- **"Beats watershed + Swebrec"** only by the decision rule on $x_{50}$ error: the paired 95 % CI of the per-image error
  difference (watershed − U-Net) must exclude 0
  ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

### Evaluation protocol

- **TSTR/TRTR** [11]: the same test folds for both models; ratio per fold, mean and spread. Real $x_{50}$ errors are in
  pixels against the label-derived $x_{50}$.
- **Synthetic held-out**: relative $x_{50}$ and $x_{80}$ errors vs the exact PSD; the gap between surface-visible and
  full-pile PSD is reported as the occlusion bias.
- **Data validation** of the synthetic images: a classifier two-sample test on frozen DINOv2 embeddings, synthetic vs
  real, with AUC − real-vs-real AUC ≤ 0.10 [12][13]; duplicate checks across splits.
- Instance and boundary metrics reported alongside IoU.

### Licence of weights

smp is MIT [3]. Encoder ImageNet weights are traced **per encoder** before use (UNVERIFIED until traced); NVIDIA's
SegFormer MiT weights are **rejected** (NVIDIA Source Code License, non-commercial) [14]. Synthetic-trained weights are
**Apache-2.0 + attribution**; weights trained with Mendeley images also carry its CC BY 4.0 attribution to Si et al.
From the Mendeley source itself PitStudio commits metrics only.

## Assumptions and limits

- Synthetic piles come from our DEM with rendered textures; their realism is what TSTR/TRTR measures, not assumes.
- Real labels are polygon instances by the dataset authors; 48 named instances have no pixels (fully overlapped), which
  is harmless for IoU.
- The 240 real originals are a small, single-source set; the fold spread is part of the result.
- smp has had no release for about 17 months [3]; if it fails on Python 3.14 / torch 2.14, a minimal U-Net is
  vendored with the same architecture.

## In PitStudio

- **Case:** [D1](../cases/d1-blast-muck-pile.md) (PSD, oversize, measured sim-to-real); feeds
  [D2](../cases/d2-mine-to-mill.md) through $x_{50}$.
- **Methods:** [M11](../methods/m11-fragmentation-segmentation.md), [M12](../methods/m12-blast-fragmentation-models.md).
- **Env and stages:** `studio/` DEM piles + `studio/isaac/` renders → `pipeline/` `s00_download` (Mendeley, pooch +
  SHA-256) → `s10_preprocess` → `s30_train` → `s40_infer` → `s50_evaluate` → `s60_export` → `pipeline/accel/`
  `s62_accel` → `s64_bench`. smp is added to `pipeline/` and locked in the build phase.
- **Artefacts:** `models/onnx/` (int8, live), `models/cards/`; web lane LIVE with a TS watershed side by side.

```bash run deferred=P6
uv run studio run studio/recipes/cases/d1.yaml --profile laptop-rtx5000ada
```

## Results

**Not yet trained** — produced in the data-and-models phase. Will be reported: synthetic held-out $x_{50}$/$x_{80}$
relative errors (acceptance ≤ 15 % on $x_{50}$); TSTR/TRTR IoU ratio per grouped fold (acceptance ≥ 0.90); U-Net vs
watershed + Swebrec paired $x_{50}$ error difference with 95 % CI; DINOv2 classifier two-sample test; ONNX and int8
parity; TensorRT per-engine parity, latency and J/inference.

## References

1. Maerz, N. H., Palangio, T. C., Franklin, J. A. *WipFrag image based granulometry system*. https://doi.org/10.1201/9780203747919-15
2. Ronneberger, O., Fischer, P., Brox, T. (2015). *U-Net*. MICCAI 2015. https://arxiv.org/abs/1505.04597
3. `segmentation-models-pytorch` 0.5.0 (MIT, 2025-04-17). https://pypi.org/pypi/segmentation-models-pytorch/json
4. Milletari, F., Navab, N., Ahmadi, S.-A. (2016). *V-Net* (Dice-based objective). https://arxiv.org/abs/1606.04797
5. Ouchterlony, F. (2005). The Swebrec function. Mining Technology 114(1):29–44. https://doi.org/10.1179/037178405X44539
6. Mutinda, E. K. et al. (2021). Prediction of rock fragmentation using the KCO model. JSAIMM 121(3). https://doi.org/10.17159/2411-9717/1401/2021
7. Si, Zhu, Di, Wang (2019). *Rock fragment image segmentation combining CNN and watershed algorithm* (Mendeley Data, CC BY 4.0). https://doi.org/10.17632/78ht3pjsr4.1
8. Meta AI. *SAM 2* repository (Apache-2.0 + BSD-3; SAM 2.1 sizes). https://github.com/facebookresearch/sam2
9. NVIDIA TensorRT 10.3.0 release notes (FP8 convolution on SM 89; INT8 for group/depthwise ConvNets). https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/getting-started/release-notes-10/10.3.0.html
10. Karimov et al. (2025). *Quantization Robustness to Input Degradations for Object Detection*. https://doi.org/10.48550/arXiv.2508.19600
11. Esteban, C., Hyland, S. L., Rätsch, G. (2017). TSTR/TRTS evaluation. https://arxiv.org/abs/1706.02633
12. Lopez-Paz, D., Oquab, M. (2016). *Revisiting Classifier Two-Sample Tests*. https://arxiv.org/abs/1610.06545
13. Meta AI. *DINOv2* repository (Apache-2.0). https://github.com/facebookresearch/dinov2
14. NVlabs SegFormer licence (NVIDIA Source Code License, non-commercial). https://api.github.com/repos/NVlabs/SegFormer/license
