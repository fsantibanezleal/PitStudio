# Mendeley rock-fragment segmentation images

> 960 labelled 512 × 512 images of blasted rock fragments (240 originals × 4 flips/rotations) under CC BY 4.0: the
> only real labelled set in PitStudio, and the basis of its one measured sim-to-real result. · Part of:
> [Dataset cards](README.md) · Related: [D1 Blast and muck pile](../../cases/d1-blast-muck-pile.md) ·
> [M11 Fragmentation segmentation](../../methods/m11-fragmentation-segmentation.md) ·
> [U-Net fragmentation](../../models/unet-fragmentation.md) · [Synthetic data](synthetic-data.md)

## What and why

Case D1 asks how blast design changes the muck-pile fragment size distribution (PSD), and whether a segmentation
model trained only on synthetic muck piles with an exact PSD works on real fragment photographs. That second question
needs **real images with real instance labels**. Si, Zhu, Di and Wang (2019) released such a set on Mendeley Data
under CC BY 4.0 [1]; it was the best openly licensed real blast-fragment image set found, and it publishes a SHA-256
for its archive [2].

Because the labels exist, D1 can report a **measured** sim-to-real gap: a U-Net trained on synthetic images (TSTR)
against a U-Net trained on real images (TRTR), both tested on the same real test images [7]. Every other perception
case in PitStudio reports sim-to-real as "not measured".

## Datasheet

### Composition

The archive was downloaded and inspected during bootstrap (see [Bootstrap data check](#bootstrap-data-check) for
how). Layout of `Research Data.7z` — 7,898 entries, 4.44 GB uncompressed:

| Path | Count | Content |
|---|---|---|
| `Annotated data/pic/NNN.jpg` | 960 | RGB images, all 512 × 512 px |
| `Annotated data/labelme_json/NNN_json/` | 960 folders | output of labelme's `labelme_json_to_dataset` |
| ├ `img.png` | 1 per folder | the image |
| ├ `label.png` | 1 per folder | indexed (palette) instance mask: 0 = background, *k* = instance *k* |
| ├ `label_names.txt`, `info.yaml` | 1 each per folder | `_background_`, `rock-1`, `rock-2`, … |
| └ `label_viz.png` | 1 per folder | preview overlay (not used) |
| `Annotated data/cv2_mask/NNN.png` | 960 | indexed masks; foreground equal to that of `label.png` (checked on file 001: foreground fraction 0.582 in both) |
| Extras | — | a TensorFlow Mask R-CNN checkpoint (256 MB), the authors' code (C++, Matlab, TensorFlow) and 40 example segmentations — **not used** |

- The original labelme `.json` **polygon files are not in the archive**; the instance masks are the labels.
- **One class only:** every instance is a `rock-N`.

Label statistics over the 960 masks (bootstrap check):

| Quantity | Value | Unit |
|---|---|---|
| Instances with pixels | 63,144 | instances |
| Instances per image: mean / median / min / max | 65.8 / 58 / 4 / 236 | instances per image |
| Names listed in `label_names.txt` | 63,192 | names |
| Named instances with no pixels | 48, in 48 images (fully overlapped polygons; harmless) | instances |
| Instance area p10 / p50 / p90 | 102 / 807 / 5,298 | px² |
| Equivalent diameter $d_{eq} = \sqrt{4A/\pi}$ p10 / p50 / p90 | 11 / 32 / 82 | px |

Here $A$ (px²) is the instance's pixel area and $d_{eq}$ (px) the diameter of a circle of equal area.

**No physical scale.** No millimetres-per-pixel value appears anywhere in the archive. PSD comparisons on this data
are therefore made **in pixels, or in relative terms** (ratios such as $x_{50}/x_{80}$, curve shape). Any conversion
to millimetres is an assumption, stated on the [D1 case page](../../cases/d1-blast-muck-pile.md).

### The 960 images are 240 originals × 4

The bootstrap check verified exactly that files 241–960 are flips and rotations of files 001–240: normalised
correlation 1.000 and label IoU 1.000 for all 240 × 3 pairs.

| Files $k$ | Relation |
|---|---|
| 001–240 | originals |
| 241–480 | horizontal flip of file $k - 240$ |
| 481–720 | vertical flip of file $k - 480$ |
| 721–960 | 180° rotation of file $k - 720$ |

Among the 240 originals there is **no pixel-level overlap**: a high-pass correlation test over all 28,680 pairs finds
none above 0.7. A raw-intensity phase-correlation search flagged **9 visually similar pairs** (normalised
cross-correlation > 0.9), but on this texture raw correlation does not separate related from unrelated tiles
(high-pass correlation of those pairs is 0.19–0.32, inside the range of unrelated tiles). The 9 pairs are merged
**conservatively**, which leaves **231 source groups** (240 without the merge); merging can only make the test
harder, never easier. The number of unique labelled instances is $63{,}144 / 4 = 15{,}786$.

### Collection and provenance

- **Authors:** Si, Zhu, Di, Wang [1].
- **Title:** "Rock fragment image segmentation combining CNN and watershed algorithm" [1].
- **Collection:** photographs of blasted rock fragments, annotated as polygons in labelme and exported to instance
  masks (the export tool's folder layout is visible in the archive). Camera, site and scale are not documented in the
  archive.
- **Version read:** Mendeley Data version 1, published 2019-08-12 [1].
- **Landing page:** https://data.mendeley.com/datasets/78ht3pjsr4/1 — DOI 10.17632/78ht3pjsr4.1 [1].

### Licence and attribution

- **SPDX:** `CC-BY-4.0`. **Licence class:** `attribution`. **Redistribution class:** `redistributable` under CC BY
  4.0, but PitStudio commits **metrics only**: no images, no masks, no crops.
- **Attribution text**, reproduced verbatim wherever a metric computed on this data is shown:
  "Si, Zhu, Di, Wang (2019). Rock fragment image segmentation combining CNN and watershed algorithm. Mendeley Data,
  V1. https://doi.org/10.17632/78ht3pjsr4.1. Licensed under CC BY 4.0."
- **Conflicts:** none found.

### Size, checksums and access

- **File:** `Research Data.7z`, **4,230,116,058 bytes** (4.23 GB) [2].
- **Checksum:** SHA-256 `7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d`, published in the
  publisher's file listing [2] and verified on the bootstrap copy.
- **Account:** none.
- **Programmatic path:** the Mendeley public files API returns the direct download URL [2]; `s00_download` fetches
  it with pooch and checks the published SHA-256.
- **Fallback:** if the labels had been unusable, D1 would have made a **synthetic-only U-Net claim** (no measured
  sim-to-real). The bootstrap check shows the labels are usable, so the fallback is not expected to be needed.

## Bootstrap data check

Done 2026-10-04, before the TSTR / TRTR criterion is fixed at specification. It is a **data check, not a training
result**: the archive was downloaded, hashed and inspected; nothing was trained.

1. The SHA-256 of the downloaded archive matched the publisher's value [2].
2. The annotated subset was extracted (the `label_viz.png` previews were skipped) and every mask was read.
3. Counts, sizes and the augmentation structure above were computed from the masks and images.
4. Exact duplicates were tested by flipping/rotating originals and comparing pixels and labels; near-duplicates by
   phase correlation between all original pairs.

The pipeline download in `s00_download` is still deferred to the data-and-models phase; the bootstrap copy is a
local check, not a pipeline artefact.

## Consequences for evaluation

- **The labels are usable as intended.** Instance masks give the foreground IoU used for TSTR / TRTR, and also
  instance and boundary metrics.
- **Split by source group, never by file.** The group key of file $k$ is

  $$g(k) = \big((k - 1) \bmod 240\big) + 1,$$

  merged with the 9 conservative similarity links, which gives 231 groups. A per-file split would put flipped copies of test tiles
  into training and inflate TRTR.
- **Evaluate on originals only:** test folds contain files 001–240 of the test groups. Training may use the shipped
  flips or its own augmentation. The **effective real set is 240 tiles, not 960**.
- **Grouped k-fold, not a single split.** With about 231 groups, one 80/20 split leaves only about 46 test tiles
  ($0.2 \times 231 \approx 46$). The protocol uses a grouped k-fold (for example 5 folds) and reports the
  TSTR / TRTR ratio with its fold spread.
- **x50 in pixels.** The x50-error comparison of the U-Net against watershed + Swebrec
  ([M11](../../methods/m11-fragmentation-segmentation.md)) is computed in pixels on real images.

## Validation role

| Check | What is compared | Pre-registered criterion |
|---|---|---|
| TSTR vs TRTR [7] | U-Net trained on synthetic exact-PSD muck piles vs trained on real training folds, both tested on real original tiles | TSTR ≥ 0.90 × TRTR (foreground IoU), reported per fold with spread |
| Classifier two-sample test on image embeddings [5][6] | synthetic muck-pile images vs real images, DINOv2 embeddings, two classifier families | AUC − real-vs-real AUC ≤ 0.10, bootstrap CI |
| Real-vs-real baseline | real vs real, split by source group | reference AUC for the line above |
| Duplicate scan | synthetic vs real and train vs test (exact hash, perceptual hash, embedding nearest neighbour) | no copy and no cross-split duplicate; similarity thresholds fixed at specification |
| "U-Net beats watershed + Swebrec" | paired x50 error per real tile | only if the paired 95 % CI of the difference excludes 0 |

**Not yet run** — produced in the data-and-models phase.

## Assumptions and limits

- **One site type, one camera set-up, unknown scale.** The images may not represent other rock types, lighting or
  camera heights; results transfer only to similar photographs.
- **240 effective tiles.** Small for a learned model; fold spread is reported because a single number would hide it.
- **Label quality** is the authors'. Overlapping polygons hid 48 named instances; touching fragments may be merged or
  split differently from a sieve. Masks are 2-D projections of 3-D fragments, so a PSD from them is an image PSD,
  not a sieved PSD.
- **No mm scale** means real-image PSDs cannot be compared with Kuz-Ram predictions in millimetres without the D1
  scale assumption.

## In PitStudio

- **Source id:** `mendeley-78ht3pjsr4` in `data/sources.yaml`.
- **Stages:** `s00_download` → `s10_preprocess` (read masks, attach group keys, build grouped folds, originals-only
  test lists) → `s30_train` (TRTR arm) → `s50_evaluate` (TSTR / TRTR, embedding test, duplicate scan, x50 error) →
  `s60_export` (metrics only).
- **Cases:** [D1](../../cases/d1-blast-muck-pile.md).
- **Methods:** [M11](../../methods/m11-fragmentation-segmentation.md) watershed + Swebrec vs U-Net;
  [M12](../../methods/m12-blast-fragmentation-models.md) for the PSD forms (the Swebrec function [3]; prediction
  equations and parameter priors [4]).
- **Models:** [U-Net fragmentation](../../models/unet-fragmentation.md).
- **Committed:** metrics only (IoU per fold, ratios, AUCs, x50 errors), each with the attribution text. **Never
  committed:** the archive, images, masks, crops or thumbnails.
- **Status:** **downloaded and checked during bootstrap** (data check above; nothing trained). The pipeline download
  by `s00_download` is still deferred to the data-and-models phase.

## References

1. Si, Zhu, Di, Wang (2019). "Rock fragment image segmentation combining CNN and watershed algorithm". Mendeley
   Data, V1, 2019-08-12. https://doi.org/10.17632/78ht3pjsr4.1 — https://data.mendeley.com/datasets/78ht3pjsr4/1
   (accessed 2026-10-02)
2. Mendeley Data. Public files API listing for dataset 78ht3pjsr4, version 1 (file name, size, SHA-256, download
   URL), accessed 2026-10-02. https://data.mendeley.com/public-api/datasets/78ht3pjsr4/files?folder_id=root&version=1
3. Ouchterlony, F. "The Swebrec function: linking fragmentation by blasting and crushing", *Mining Technology*
   114(1):29–44, 2005. https://doi.org/10.1179/037178405X44539
4. Ouchterlony, F., Sanchidrián, J. A. "A review of development of better prediction equations for blast
   fragmentation", *Journal of Rock Mechanics and Geotechnical Engineering* 11(5):1094–1109, 2019.
   https://doi.org/10.1016/j.jrmge.2019.03.001
5. Lopez-Paz, D., Oquab, M. "Revisiting Classifier Two-Sample Tests", 2016. https://arxiv.org/abs/1610.06545
6. Oquab, M. et al. "DINOv2: Learning Robust Visual Features without Supervision", 2023.
   https://arxiv.org/abs/2304.07193
7. Esteban, C., Hyland, S. L., Rätsch, G. "Real-valued (Medical) Time Series Generation with Recurrent Conditional
   GANs" (defines TSTR / TRTS), 2017. https://arxiv.org/abs/1706.02633
