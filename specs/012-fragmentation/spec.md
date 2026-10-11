# Spec 012 — Fragmentation: synthetic exact-PSD muck piles, U-Net versus watershed + Swebrec, measured sim-to-real
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

Methods M11 and M12 and case D1 ask whether a segmenter trained **only** on synthetic muck piles, whose fragment size
distribution (PSD) is known exactly, measures real fragmentation. This spec fixes the real reference (the Mendeley
rock-fragment set: 960 images = 240 originals × 4 dihedral copies, 231 source groups, no physical scale), the grouped
5-fold protocol, the synthetic exact-PSD pile generator and renders, the U-Net and its label scheme, the classical
watershed + Swebrec baseline, the PSD and x50 definitions, the TSTR / TRTR criterion, the paired comparison with the
decision rule FR-000-05, the image-realism checks (classifier two-sample test on DINOv2 embeddings, duplicates,
injected shift) and the D1 design outputs. It is PitStudio's one **measured** sim-to-real result (SC-000-01).

Who benefits: drill-and-blast engineers (x50, x80 and oversize from photographs, with the classical method beside the
learned one), data/AI practitioners (a measured synthetic-to-real ratio on a group-split real set), and visitors (a
live U-Net and watershed on synthetic renders).

Out of scope:
- the Kuz-Ram, KCO, Swebrec, PPV and flyrock models themselves — they live in the `minephys` package, module
  `blasting`, specified in that repository; this spec calls them;
- the Warp DEM solver and its benchmarks (spec 005); generic download and SHA-256 checks (spec 008);
- generic ONNX export, parity layers 1, 2, 4 and TensorRT (spec 016); the TypeScript watershed, the web worker and
  browser parity (spec 018);
- absolute (mm) fragment sizes on the real images, which have no scale; sieved PSDs; blast design or regulatory use.

## 2. User stories

### US-012-1 (P1) A measured synthetic-to-real ratio
As a data/AI practitioner, I want a U-Net trained only on synthetic piles (TSTR) and one trained on real images
(TRTR) scored on the same real originals of grouped folds, so that the synthetic-to-real gap is measured, not assumed.
Independent test: build the folds from the committed group links and check them against the hand-computed partition.

### US-012-2 (P1) Fragment sizes from images, learned versus classical
As a drill-and-blast engineer, I want x50 (and x80) from both the U-Net and watershed + Swebrec, compared by the
paired decision rule, so that I know whether the learned method is actually better. Independent test: compute the PSD
and Swebrec fit on hand-built label images with known instance areas.

### US-012-3 (P1) Synthetic muck piles with an exact PSD
As a reviewer, I want every synthetic pile to come with its exact fragment table and a provable bound between its
realised and target PSD, so that "exact PSD" is checkable. Independent test: run the generator on CPU and check the
bound at every class boundary.

### US-012-4 (P1) Realism checks and licence-clean publishing
As a reviewer, I want classifier two-sample tests with a real-versus-real baseline, an injected-shift power check and
duplicate scans, and only metrics from the real set in the repository, so that realism claims are bounded and the
licence is respected. Independent test: run the C2ST on Gaussian fixtures with a known analytical AUC.

### US-012-5 (P2) A live segmenter in the browser
As a visitor, I want the int8 U-Net to run live next to the watershed on sample synthetic renders, so that I can see
both segmentations and PSD curves. Independent test: check the web build for the live ONNX file, its size and lane.

### US-012-6 (P2) Design outputs from cited models
As a drill-and-blast engineer, I want the D1 design grid (x50, x80, % oversize, PPV, flyrock radius) computed by the
cited `minephys` blasting models, so that the calculator and the baked fallback agree. Independent test: compare the
baked grid with direct `minephys.blasting` calls.

Story index (for traceability):

| Story | Title | Priority |
|---|---|---|
| US-012-1 | A measured synthetic-to-real ratio | P1 |
| US-012-2 | Fragment sizes from images, learned versus classical | P1 |
| US-012-3 | Synthetic muck piles with an exact PSD | P1 |
| US-012-4 | Realism checks and licence-clean publishing | P1 |
| US-012-5 | A live segmenter in the browser | P2 |
| US-012-6 | Design outputs from cited models | P2 |

## 3. Functional requirements (EARS)

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-012-01 | Ubiquitous | The D1 reader in `s10_preprocess` shall read only an archive that `s00_download` (spec 008) verified as 4,230,116,058 bytes with SHA-256 `7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d`, and shall extract only `Annotated data/pic/NNN.jpg` and `Annotated data/labelme_json/NNN_json/label.png` for NNN = 001–960 into the git-ignored data folder (`PITSTUDIO_DATA`). | unit + pipeline |
| FR-012-02 | Unwanted | If an archive member name is absolute, contains `..` or a drive letter, or resolves outside the extraction folder, or an image is not 512 × 512 RGB, or a `label.png` is not a 512 × 512 palette (indexed) image, or any of the 1,920 expected members is missing, then the reader shall stop with the member name and reason and leave no partial dataset. | unit (hostile) |
| FR-012-03 | Ubiquitous | The reader shall produce, for every file k = 1–960, the RGB image, the instance mask (uint16, 0 = background, value j = instance j), the foreground mask (label > 0) and the SHA-256 of the image and label bytes as stored in the archive; over all files it shall count 960 images and 63,144 non-empty instances. | pipeline |
| FR-012-04 | Ubiquitous | The split builder shall assign each file k the group key g(k) = ((k − 1) mod 240) + 1 and merge groups by union–find over the nine links committed in `data/splits/mendeley-78ht3pjsr4-links.yaml` (§7), giving exactly 231 source groups. | unit |
| FR-012-05 | Ubiquitous | The split builder shall partition the 231 groups into 5 folds with scikit-learn `GroupKFold(n_splits=5, shuffle=True, random_state=20261004)` over the 240 originals; for fold f the test list shall be the originals (k ≤ 240) of the fold's groups, the validation list the files (1–960) of a seeded 10 % of the remaining groups, and the training list the files (1–960) of all other groups. | unit + property |
| FR-012-06 | Unwanted | If a group occurs in the test list and in the training or validation list of the same fold, a test list contains a file k > 240, or the union of the five test lists differs from {1, …, 240}, then the split builder shall stop with `split-leak` and list the offending files. | unit (hostile) |
| FR-012-07 | Unwanted | If the SHA-256 of a label used for scoring differs from the value recorded at extraction, then `s50_evaluate` shall refuse to score with `label-modified` and name the file. | unit (hostile) |
| FR-012-08 | Ubiquitous | The label-assistant step (SAM 2.1-tiny) shall mark its outputs `role: label-assistant` for use in quality-control reports only, and the lineage recorded in the manifests shall show no SAM output in any test label set, any TRTR training label set or any metric. | contract |
| FR-012-09 | Ubiquitous | The pile generator shall draw fragment sizes (volume-equivalent sphere diameters, m) for a target total solid volume V over K = 20 log-spaced size classes on [x_min, x_max], processed in ascending order: fragments are added to class j, with sizes drawn inside the class by inverse-CDF sampling from a seeded counter-based generator, until the cumulative realised volume first reaches V·F(x_j), where x_j is the class's upper boundary and F the Swebrec passing function of `minephys.blasting` truncated and renormalised to [x_min, x_max]; it shall write the fragment table (DC-012-01). | unit + property |
| FR-012-10 | Ubiquitous | The pile generator shall keep, for every pile, the realised volume-passing fraction at every class boundary x_j strictly within v_max / V_real of F(x_j), where v_max is the largest fragment volume of the pile and V_real its realised total volume (the cumulative fill overshoots each target by less than one fragment). | property |
| FR-012-11 | Unwanted | If a generator parameter is non-finite, or b ≤ 0, or x_min ≤ 0, or the order x_min < x50 < x_max fails, or V ≤ 0, or the expected fragment count exceeds 10⁶, then the generator shall raise `ValueError` naming the parameter and write nothing. | unit (hostile) |
| FR-012-12 | Ubiquitous | The rock-mesh builder shall give each fragment a seeded procedural convex rock mesh scaled so that its enclosed volume equals π·x³/6 for its size x within rtol 1e-3 (divergence-theorem volume). | unit |
| FR-012-13 | Ubiquitous | The render stage `st55_sdg` shall write, for every view of a pile settled by `st50_physics` (spec 005), a 1,024 × 1,024 sRGB render, an instance mask whose ids equal fragment ids, a depth map (m, float32), the intrinsics (focal length in px) and a render-index record (DC-012-04); renders are cut into four non-overlapping 512 × 512 tiles. | integration (gpu) + contract |
| FR-012-14 | Ubiquitous | The synthetic dataset builder shall split piles by pile seed into train / validation / held-out in the proportions 80 / 10 / 10 % (seeded), with ≥ 5,000 training tiles and ≥ 50 held-out piles. | property |
| FR-012-15 | Ubiquitous | The synthetic dataset builder shall take as the truth of every pile its exact realised PSD: x50 and x80 as the volume-weighted quantiles of §7 (Q-1) over the fragment table (m), the surface-visible x50 over fragments with ≥ 1 visible pixel in the view, and the occlusion bias = visible x50 / full x50 − 1. | unit |
| FR-012-16 | Unwanted | If a rendered instance id has no row in the pile's fragment table, or a fragment id is duplicated in the table, then the dataset builder shall reject that view with `label-truth-mismatch`. | unit (hostile) |
| FR-012-17 | Unwanted | If the training manifest of the TSTR arm lists a file whose SHA-256 equals any of the 1,920 Mendeley member hashes, then `s30_train` shall refuse to start with `real-data-in-synthetic-arm`. | unit (hostile) |
| FR-012-18 | Ubiquitous | The target encoding shall label each pixel 0 (background, label 0), 2 (boundary: a foreground pixel with at least one 8-neighbour of a different label value, background included) or 1 (interior: any other foreground pixel). | unit |
| FR-012-19 | Ubiquitous | The decoder shall form instances as 4-connected components of predicted interior pixels with area ≥ 4 px, assign each predicted boundary pixel to an adjacent instance by marker-controlled watershed on the boundary probability restricted to the predicted foreground (interior ∪ boundary), and use interior ∪ boundary as the predicted foreground. | unit |
| FR-012-20 | Ubiquitous | The U-Net shall be the `segmentation_models_pytorch` 0.5.0 `Unet` with the timm encoder `resnet18.a1_in1k` (ImageNet weights, Apache-2.0), 3 output classes and 512 × 512 RGB input normalised with the ImageNet mean and standard deviation, trained on the sum of the pixel-weighted cross-entropy with the weight map w(x) = w_c(x) + w₀·exp(−(d₁(x) + d₂(x))² / (2σ²)), w₀ = 10, σ = 5 px, and a soft Dice term on the foreground. | unit + integration (gpu) |
| FR-012-21 | Optional | Where `segmentation_models_pytorch` cannot be installed or imported on Python 3.14 with torch 2.14.1, the pipeline shall use a vendored minimal U-Net with the same encoder and decoder layout, and the model card shall say so. | unit |
| FR-012-22 | Ubiquitous | The TSTR model (one, synthetic training tiles only) and the TRTR models (one per fold, that fold's training list) shall use the same architecture, optimiser (AdamW), learning-rate schedule, number of gradient steps, augmentation (8 dihedral maps and colour jitter) and seed, with model selection on their own validation data only. | contract |
| FR-012-23 | Unwanted | If U-Net inference receives a tensor that is not float32 [N, 3, 512, 512] or contains a non-finite value, or the watershed baseline receives an image that is not H × W × 3 uint8 with H, W ≥ 16, then the function shall raise `ValueError` and return no mask. | unit (hostile) |
| FR-012-24 | Ubiquitous | The image PSD shall give each instance k of area A_k (px) the size d_k = 2·√(A_k/π) (px) — on synthetic tiles converted to metres as d_k·z̃_k/f_px with z̃_k the median depth over the instance's pixels — and the area-weighted passing points (x_j, P_j) over the distinct sizes x_1 < … < x_n, where P_j is the area of all instances of size ≤ x_j divided by the total area (metric areas on synthetic tiles; equal sizes merged into one point), then fit Swebrec with FR-012-26. | unit |
| FR-012-25 | Unwanted | If an instance set has fewer than 3 instances or a non-finite or non-positive area, or the fit does not converge, then the PSD function shall return status `no-fit` with x50 = null, and that image shall count with relative x50 error 1.0 for its method in every comparison, with the number of `no-fit` images reported. | unit (hostile) |
| FR-012-26 | Ubiquitous | The Swebrec fit shall set x_max to the largest size x_n and find (x50, b) minimising Σ_{j<n} (S(x_j; x50, b, x_max) − P_j)², with S the Swebrec passing function of `minephys.blasting`, bounds x50 ∈ [10⁻⁶·x_max, (1 − 10⁻⁶)·x_max] and b ∈ [0.05, 50], start values x50 = the area-weighted median (Q-1) and b = 2, using `scipy.optimize.least_squares` (trust-region reflective, xtol = ftol = gtol = 1e-12). | unit |
| FR-012-27 | Unwanted | If the fit receives sizes that are ≤ 0, non-finite or not strictly increasing, passing values outside [0, 1] or decreasing, fewer than 3 points, or arrays of different lengths, then it shall raise `ValueError` naming the argument. | unit (hostile) |
| FR-012-28 | Ubiquitous | The classical baseline shall run grey conversion, Gaussian smoothing (σ_g), Otsu threshold plus an offset, Euclidean distance transform, `peak_local_max` with `min_distance`, and marker watershed on the negative distance within the foreground (scikit-image), keep instances of area ≥ 4 px, and feed them to FR-012-24; its parameters σ_g ∈ {0.5, 1, 2} px, `min_distance` ∈ {3, 5, 7, 9} px and offset ∈ {−0.05, 0, 0.05} shall be chosen per fold by the highest mean foreground IoU on that fold's training originals, and for synthetic evaluation on the synthetic validation tiles. | unit |
| FR-012-29 | Ubiquitous | The foreground IoU of a tile shall be \|P ∩ G\| / \|P ∪ G\| over foreground pixels, equal to 1.0 when both sets are empty, and the fold score shall be the mean over the fold's test originals. | unit |
| FR-012-30 | Ubiquitous | The stage `s50_evaluate` shall report, for each fold f, ρ_f = IoU_TSTR,f / IoU_TRTR,f, and over the five folds the mean ρ̄, the minimum and the standard deviation. | unit |
| FR-012-31 | Ubiquitous | The relative x50 error of an image shall be \|x̂50 − x50\| / x50, against the exact pile x50 (m) on synthetic held-out views and against the FR-012-24/26 x50 of the ground-truth instances (px) on real test originals; on a synthetic view both methods shall run on its four tiles, stitched into the 1,024 × 1,024 view before decoding; the synthetic score shall be the mean relative error over held-out views (MRE). | unit |
| FR-012-32 | Ubiquitous | The comparison "U-Net beats watershed + Swebrec" shall be computed twice, as separate claims: on the 240 real test originals (TSTR U-Net, pairing unit = original, 95 % percentile interval of a paired cluster bootstrap over the 231 source groups, B = 10,000) and on the synthetic held-out piles (pairing unit = pile, mean over its views, paired bootstrap over piles, B = 10,000), each with d = e_watershed − e_U-Net and the verdict of FR-000-05. | unit |
| FR-012-33 | Ubiquitous | The classifier two-sample test shall embed tiles with frozen DINOv2 ViT-B/14 (final-layer class token, 224 × 224 bicubic input, ImageNet normalisation, weights pinned by SHA-256), classify synthetic (240 seeded tiles, ≤ 2 per pile) against real (the 240 originals) with two families — L2 logistic regression on standardised features and a one-hidden-layer MLP (256 ReLU units) — with out-of-fold scores from `StratifiedGroupKFold(5)` (groups = source group or pile seed), and report each AUC with a 95 % cluster-bootstrap interval (B = 1,000); the real-versus-real baseline shall use the same procedure on two seeded group-disjoint halves of the originals. | unit + pipeline |
| FR-012-34 | Event | When a C2ST verdict is computed, the evaluation shall first apply the dust corruption of spec 009 (severity 3, constant depth 100 m) to a seeded group-disjoint half of the real originals, classify shifted against unshifted originals with both families, and report every C2ST verdict as "inconclusive (no power)" unless both AUCs are ≥ 0.80. | unit + pipeline |
| FR-012-35 | Ubiquitous | The train-versus-test check shall run the FR-012-33 procedure between synthetic training tiles and synthetic held-out tiles (≥ 240 each, groups = pile seed). | pipeline |
| FR-012-36 | Ubiquitous | The duplicate scan shall flag every pair, among all synthetic tiles and all 960 real files, with equal SHA-256, a 64-bit perceptual-hash Hamming distance ≤ 4, or a DINOv2 cosine similarity ≥ 0.95, and shall stop with `split-leak` if a flag links a real test original to a training or validation file of another group. | unit + pipeline |
| FR-012-37 | Unwanted | If a two-sample test receives fewer than 100 samples in a class, a single class, or a non-finite embedding, then it shall refuse with `c2st-invalid` and the reason. | unit (hostile) |
| FR-012-38 | Ubiquitous | The repository and the web build shall contain only metrics derived from the Mendeley images, never an image, mask, crop or thumbnail of them: CI shall fail if any committed or built file has a SHA-256 in the list of the 1,920 member hashes, and every displayed Mendeley-derived metric shall carry the attribution text of the dataset card verbatim. | CI + contract |
| FR-012-39 | Unwanted | If Isaac Sim is not passing in the capability report (no synthetic renders), then `s50_evaluate` shall mark TSTR, the synthetic x50 results, both comparisons involving the TSTR model and the C2ST "not run", and shall publish TRTR and watershed results only with the label "TRTR only — synthetic arm not run". | unit (fake GPU) |
| FR-012-40 | Unwanted | If the Mendeley archive is unavailable or fails its SHA-256 check, then `s50_evaluate` shall mark TRTR, TSTR, the real comparison and the C2ST "not run", and the D1 baked data shall state "synthetic-only U-Net claim; no measured sim-to-real". | unit |
| FR-012-41 | Ubiquitous | The D1 design grid (DC-012-05: x50, x80, % oversize, PPV and flyrock radius over the recipe's design inputs) shall be computed by calling `minephys.blasting`, with no re-implementation of those models in PitStudio, and shall record the `minephys` version. | unit + reference implementation |
| FR-012-42 | Ubiquitous | The live-lane export shall contain only the TSTR U-Net, as ONNX opset 17 (spec 016), int8 by static QDQ with per-channel weights and per-tensor activations, calibrated on 500 seeded synthetic training tiles disjoint from every evaluation set. | contract |
| FR-012-43 | Unwanted | If the int8 U-Net changes the mean foreground IoU on the real test originals or the synthetic MRE by more than 1 percentage point against fp32, or its mean mask IoU against fp32 on the evaluation tiles is < 0.99, then `s60_export` shall report it as rejected with its numbers and hand precomputed outputs to the D1 page (FR-000-02). | unit |
| FR-012-44 | Unwanted | If the links file does not validate against DC-012-02, names a file outside 1–240, or links a file to itself, then the split builder shall stop with `links-invalid` and write no fold file. | unit (hostile) |
| FR-012-45 | Unwanted | If the IoU or x50-error functions receive masks of different shapes, a foreground that is not boolean, or a reference x50 that is non-finite or ≤ 0, then they shall raise `ValueError` naming the argument. | unit (hostile) |
| FR-012-46 | Unwanted | If a D1 design-grid input is non-finite, non-positive where a positive quantity is required, or rejected by `minephys.blasting`, then the grid builder shall stop with the input name and write no grid. | unit (hostile) |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-012-01 | For any instance mask and any of the 8 dihedral maps π, the image PSD and the Swebrec fit of π(mask) equal those of the mask (symmetry; metamorphic). | random label images up to 512 × 512, 3–300 instances | exact (PSD points); bitwise (fit) |
| P-012-02 | Scaling every size by k (areas by k²) scales the fitted x50 and x_max by k and leaves b unchanged (unit change; metamorphic). | k in [10⁻³, 10³]; instance sets of 3–500 instances | rtol 1e-6 |
| P-012-03 | Relabelling instance ids or permuting the instance list leaves the PSD and the fit unchanged (permutation invariance; metamorphic). | as P-012-01 | exact |
| P-012-04 | Duplicating the instance set (every instance twice) leaves the passing points and the fit unchanged (replication invariance; metamorphic). | as P-012-02 | exact (points and fit) |
| P-012-05 | For any (x50*, b*, x_max) with 0 < x50* < x_max and b* in [0.5, 10], and ≥ 10 strictly increasing sizes ending at x_max with exact Swebrec passing values, the fit recovers x50* and b*. | Hypothesis, float64 | rtol 1e-6 |
| P-012-06 | Foreground IoU is symmetric, equals 1 for identical masks, lies in [0, 1], and is invariant under the dihedral maps and instance relabelling (metamorphic). | random binary and label masks up to 512 × 512 | exact |
| P-012-07 | For label images of separated or touching axis-aligned rectangles of at least 3 × 3 px, decoding the exact FR-012-18 encoding recovers the foreground exactly and the instance count exactly. | Hypothesis: 1–40 rectangles on 128 × 128 | exact |
| P-012-08 | For any seed, the five test lists partition {1, …, 240}, the four dihedral copies of an original share its group, and no group occurs in two roles of a fold. | seeds 0–10⁶ | exact |
| P-012-09 | Multiplying x50, x_max and x_min by k with the same seed and V scaled by k³ multiplies every generated size by k and leaves every class volume fraction unchanged (scaling; metamorphic). | k in [10⁻², 10²]; valid parameter sets | rtol 1e-12 |
| P-012-10 | Changing the solid density leaves the generated sizes and volume fractions identical and scales masses linearly (density invariance; metamorphic). | density 1,500–4,000 kg/m³ | exact (sizes); rtol 1e-12 (masses) |
| P-012-11 | Increasing the target x50 with all else fixed never raises the realised passing fraction at any class boundary by more than v₁/V₁ + v₂/V₂ (the two piles' largest-fragment fractions), because the Swebrec passing value at a fixed size falls as x50 rises (monotonicity; metamorphic). | valid parameter pairs with x50₂ > x50₁ | exact |
| P-012-12 | For every valid parameter set and seed, the bound of FR-012-10 holds at every class boundary. | Hypothesis: x_max 0.2–3 m, x50/x_max 0.05–0.8, b 0.5–5, V giving 2,000–50,000 fragments | exact |
| P-012-13 | The metric size d·z̃/f scales by k when every depth is multiplied by k and by 1/k when f is multiplied by k (pinhole scaling; metamorphic). | float64 | rtol 1e-12 |
| P-012-14 | For the logistic family, swapping the two class labels, multiplying every embedding by c > 0, and permuting the sample order (groups kept) each leave the AUC unchanged (metamorphic). | Gaussian fixtures, n = 200–2,000 per class | atol 1e-6 |
| P-012-15 | For classes N(0, I) and N(μ, I) in 16 dimensions, the out-of-fold logistic AUC is within 0.03 of the analytical Φ(‖μ‖/√2); for two samples of one distribution, its 95 % interval contains 0.5 in ≥ 45 of 50 seeded repeats. | logistic family; n = 4,000 per class; ‖μ‖ in [0.25, 2] | ±0.03; ≥ 45/50 |
| P-012-16 | The weight map is equivariant under the dihedral maps, invariant under instance relabelling, and satisfies w(x) ≥ w_c(x) everywhere, with equality where fewer than two instances exist (metamorphic). | random label images up to 256 × 256 | atol 1e-12 |
| P-012-17 | Adding a fragment smaller than every other fragment never increases the volume-weighted x50 (Q-1), and Q-1 is invariant to the order of the fragment table (metamorphic). | random fragment tables of 3–10⁵ rows | exact |
| P-012-18 | For the paired cluster bootstrap of FR-012-32, swapping the two methods negates both interval bounds and swaps "better" and "worse"; relisting the clusters in any order leaves the interval unchanged; identical errors give [0, 0] and "no significant difference" (antisymmetry, order invariance, identity; metamorphic). | Hypothesis: 20–240 units in 10–231 clusters | atol 1e-12 |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-012-01 | Size of the live int8 U-Net (expected 5–15 MB; ≈ 14 M parameters with the pinned encoder, estimate) | ≤ 25 × 10⁶ bytes | CI budget check (spec 016) |
| NFR-012-02 | Live U-Net latency per 512 × 512 tile | T1 median ≤ 300 ms over ≥ 50 tiles after 5 warm-up runs; T2 run ≤ 1 s | web timing record (spec 018) → manifest lane |
| NFR-012-03 | Training jobs | every resume segment ≤ 8 h; ≥ 1 checkpoint per epoch | run manifest |
| NFR-012-04 | Determinism | the fold file and the evaluation report are byte-identical across two runs on the same inputs | pipeline test |
| SC-012-01 | TSTR U-Net on synthetic held-out views | MRE of x50 ≤ 0.15 against the exact pile PSD (point estimate; 95 % pile-bootstrap interval reported) | `s50_evaluate` report |
| SC-012-02 | TSTR against TRTR on the real test originals, 5 grouped folds | ρ̄ ≥ 0.90 (foreground IoU), with every ρ_f, the minimum and the standard deviation reported | `s50_evaluate` report |
| SC-012-03 | "U-Net beats watershed + Swebrec" | stated only when the FR-012-32 interval of the paired x50-error difference excludes 0 in its favour; otherwise "no significant difference" (or "worse"); real and synthetic claims stated separately | `s50_evaluate` report + D1 baked data |
| SC-012-04 | Realism of the synthetic fragment images | AUC − real-versus-real AUC ≤ 0.10 for both families; injected-shift AUC ≥ 0.80 for both; train-versus-test AUC ≤ 0.60 for both; 0 synthetic-to-real duplicate flags | `s50_evaluate` report |
| SC-012-05 | int8 U-Net against fp32 | \|Δ IoU\| ≤ 1 percentage point, \|Δ MRE\| ≤ 1 percentage point, mean mask IoU ≥ 0.99; otherwise rejected | `s50_evaluate` / spec 016 layer 2 |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-012-01 | Fragment table per pile (fragment id, size m, volume m³, mass kg, class index, seed, visible px per view) as Parquet rows | `specs/012-fragmentation/contracts/fragment-table.schema.json` (draft; promoted to `contracts/fragment-table.schema.json` by T-012-001) | pile generator, `st55_sdg` → dataset builder, `s50_evaluate` |
| DC-012-02 | Real fold file and group links (archive SHA-256, links, 231 groups, per-fold test / validation / training lists, seed) | `specs/012-fragmentation/contracts/fragment-split.schema.json` (draft; promoted to `contracts/fragment-split.schema.json` by T-012-002) | split builder; `data/splits/mendeley-78ht3pjsr4-links.yaml` → `s30_train`, `s50_evaluate` |
| DC-012-03 | Fragmentation evaluation report (per-fold IoU and ρ_f, ρ̄, x50 errors, intervals, verdicts, `no-fit` counts, C2ST and duplicate results, statuses, attribution text) | `specs/012-fragmentation/contracts/fragmentation-eval.schema.json` (draft; promoted to `contracts/fragmentation-eval.schema.json` by T-012-003) | `s50_evaluate` → `s60_export`, D1 baked data, model card |
| DC-012-04 | Muck-pile render index (pile seed, view, tile, relative paths, SHA-256, intrinsics, depth path, instance-to-fragment map, `synthetic: true`, licence) | `specs/012-fragmentation/contracts/muck-pile-render.schema.json` (draft; promoted to `contracts/muck-pile-render.schema.json` by T-012-004) | `st55_sdg` → dataset builder |
| DC-012-05 | D1 design grid (design inputs, x50, x80, % oversize, PPV, flyrock radius, units, `minephys` version) | `specs/012-fragmentation/contracts/d1-design-grid.schema.json` (draft; promoted to `contracts/d1-design-grid.schema.json` by T-012-005) | D1 recipe → web D1 fallback, docs |

Run and asset manifests (lineage, lane, licence class) follow the foundation contract DC-000-01
(`contracts/manifest.schema.json`).

## 7. Edge cases and assumptions

**Real reference facts** (bootstrap data check of the archive, independent of the code under test; dataset card
`docs/data-contract/dataset-cards/mendeley-rock-fragments.md`): 960 RGB images of 512 × 512 px; files 241–480,
481–720 and 721–960 are the horizontal flip, vertical flip and 180° rotation of files 1–240; one class; indexed
instance masks from labelme's dataset export (no polygon files); 63,144 non-empty instances (15,786 unique); 48 named
instances with no pixels; equivalent diameter p10 / p50 / p90 = 11 / 32 / 82 px; no physical scale.

**The nine conservative links** (original file numbers, from the bootstrap overlap check): 29–39, 34–41, 36–37,
41–49, 59–60, 189–199, 192–196, 196–198, 196–201. Union–find gives the components {29, 39}, {34, 41, 49}, {36, 37},
{59, 60}, {189, 199}, {192, 196, 198, 201}: 240 − 9 = 231 groups (no link closes a cycle).

**Q-1 — weighted quantile.** Merge equal sizes, sort the distinct sizes ascending x_1 < … < x_n with summed weights
w_i (volume on the fragment table; area on images) and cumulative fractions F_j = Σ_{i≤j} w_i / Σ w. The q-quantile is
x_1 if F_1 ≥ q; otherwise the linear interpolation between (F_{j−1}, x_{j−1}) and (F_j, x_j) for the first j with
F_j ≥ q. x50 uses q = 0.5, x80 q = 0.8.

**Pinned values (read from primary sources).**
- U-Net weight map: Ronneberger, Fischer & Brox 2015, §3, Eq. (2), p. 5 (https://arxiv.org/abs/1505.04597):
  "In our experiments we set w0 = 10 and σ ≈ 5 pixels" (read 2026-10-06). Here w_c balances the three class
  frequencies of each training tile (inverse frequency, mean 1), and d₁, d₂ are the Euclidean distances to the nearest
  and second-nearest instance (0 inside an instance; the border term is 0 with fewer than two instances).
- Encoder `resnet18.a1_in1k`: model card licence "apache-2.0", 11.7 M parameters, trained on ImageNet-1k
  (https://huggingface.co/timm/resnet18.a1_in1k, read 2026-10-06). The `segmentation_models_pytorch` hub copy of the
  torchvision ResNet weights lists its licence as "other", so it is not used.

**Edge cases and assumptions.**
- Real sizes are in pixels; x50 on real tiles compares two image methods on the same tiles, not a sieve PSD.
- Image PSDs are area-weighted 2-D proxies of volume-weighted sieve curves; the synthetic truth is volume-weighted, so
  SC-012-01 measures the whole image-granulometry chain, including occlusion and projection bias (reported separately).
- The synthetic PSD is truncated at x_min (fragments below the DEM and render resolution are not simulated); the truth
  is the realised pile, which is exact by construction.
- A `no-fit` image counts as a relative error of 1.0, so a method cannot gain by failing on hard images.
- The TSTR model is trained once; the real folds vary only the TRTR models and the test lists. The five ρ_f therefore
  share the TSTR model, and the spread reflects test-fold and TRTR variation.
- Watershed parameters tuned on real training originals make the baseline strong; the comparison is conservative.
- The live U-Net is the TSTR model, whose weights saw no Mendeley image, so its licence is Apache-2.0 + attribution
  only; TRTR weights stay local.
- 1 MB = 10⁶ bytes. GPU-hours and VRAM are estimates measured by the runner.

## 8. Clarifications log

- Number of folds ("for example 5") → resolved: 5, seeded `GroupKFold` (FR-012-05).
- Aggregate of the TSTR / TRTR criterion ("per grouped fold", "with fold spread") → resolved: mean of per-fold ratios
  ρ̄ ≥ 0.90, with every ρ_f, the minimum and the spread reported (SC-012-02).
- Label scheme and size weighting ("fixed in the spec") → resolved: three classes (FR-012-18) and area weighting
  (FR-012-24); x50 from the Swebrec fit for both methods, exact volume-weighted truth on synthetic piles.
- Which U-Net is compared with watershed, and where → resolved: the TSTR U-Net, as two separate claims (real tiles in
  px, synthetic piles in m) (FR-012-32).
- Encoder licence (docs: UNVERIFIED) → resolved by reading the encoder's model card (§7).
- Duplicate thresholds ("fixed at specification") → resolved: pHash Hamming ≤ 4, DINOv2 cosine ≥ 0.95 (FR-012-36).
- Render stage of the muck piles: the M11 method page says `st52_rtx_render`, while the D1 case and the synthetic-data
  card say Isaac Sim muck renders with instance masks (`st55_sdg`) → resolved: `st55_sdg`, because Replicator's
  writers produce the instance masks the exact truth needs (FR-012-13); reported to the coordinator.
- The classifier two-sample test for fragment images is specified here (FR-012-33 … FR-012-37); other data types may
  reuse the same module from their own specifications.
- Integration 2026-10-07: draft schema written for DC-012-01 … DC-012-05 (`specs/012-fragmentation/contracts/`, valid
  and hostile examples indexed in `examples/index.json`); stricter readings chosen: the fragment table's JSON sidecar
  (target parameters, realised V_real, v_max, x50, x80, Parquet path, digest and row count ≤ 10⁶) is the schema root
  and the Parquet row is `$defs/row`, its `seed` being the rock-mesh seed of FR-012-12; `fragment-split` validates both
  the links file and the fold file, discriminated by `kind`, with the archive SHA-256, seed 20261004, 5 folds and 231
  groups as constants, and stores every fold list as original numbers (1–240) under the constant expansion
  `dihedral-4` (files k + 240 m, m = 0…3), so the 960-file validation and training lists are derived and a test list
  can never hold k > 240; every evaluation section has status `succeeded` or `not_run` with a reason, Isaac Sim not
  passing forces TSTR, the synthetic x50, both comparisons and the C2ST to `not_run` with the TRTR-only label, an
  unavailable or mismatching archive forces TRTR, TSTR, the real comparison and the C2ST to `not_run` with the D1
  statement, an unpowered C2ST can only read "inconclusive (no power)", the attribution is the card's text as a
  constant and cross-group leaks are the constant 0 (a leak stops the run); the render index is one record per view
  with the instance map keyed by ids ≥ 1 (≤ 262,144 entries, one instance per 4 px); the D1 grid stores SI values as
  `minephys.blasting` returns them (x50 in m, PPV in m/s) with a constant `units` record, bounds the rock factor to
  Cunningham's 0.8–22 and the hole diameter to ≤ 1 m (stricter than the library's warnings), and holds ≤ 4,096 points
  over ≤ 4 axes.
- (no open items)

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
(none — new feature)
### MODIFIED Requirements
(none)
### REMOVED Requirements
(none)
