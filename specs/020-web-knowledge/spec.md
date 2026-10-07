# Spec 020 — Web knowledge: theory, methods, results, knowledge base, interactive figures and site-wide quality
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent
The site must teach and justify, not only run. This spec covers `/theory` (one page per phenomenon, MDX + KaTeX, with
interactive figures), `/methods` (the ladder M1–M23), `/results` (learned versus classical with confidence intervals,
sim-to-real and sim-to-sim gaps, browser parity, the domain-randomisation ablation, Isaac Lab versus baselines, Cosmos
versus Qwen versus the detector, and the Acceleration tab), `/knowledge` (glossary EN/ES, equation explorer, parameter
browser generated from the `minephys` knowledge tables with UNVERIFIED flags, datasets, frameworks, bibliography) and the
ⓘ architecture modal. It also fixes, once for the whole site, the interactive-chart rules (zoom, pan and read-out in
physical units, marked features, perceptually uniform colour maps, keyboard and data-table fallback), the
decision-rule display used by every "better" claim, and the site-wide quality bar: both languages, both themes, axe,
Lighthouse and the byte budgets. Students, practitioners and reviewers benefit: every equation is sourced, every claim
carries its interval and verdict, every parameter its citation and verification status. Out of scope: the content of
the knowledge tables and the models (the `minephys` repository), the production of results (pipeline specs 007–017),
the browser engines (018) and the studio pages (019).

## 2. User stories
### US-020-1 (P2) Learn the theory with live figures
As a student, I want each phenomenon explained with sourced equations and a figure I can zoom, read and drive, so that
I understand the model behind each case. Independent test: open `/theory/slopes-and-monitoring/`, move the record
cut-off and read the predicted failure time on the marked point and in the read-out.

### US-020-2 (P1) Check a claim
As a data/AI practitioner, I want every learned-versus-classical result shown with its paired interval, the
pre-registered criterion and a verdict that follows the decision rule, so that I can trust or reject it. Independent
test: on `/results`, an interval that includes 0 reads "no significant difference" and a criterion without a result
reads "Not yet run".

### US-020-3 (P2) Look up a parameter with its source
As a mining engineer, I want to find any model parameter with its value, units, citation, page and verification status,
so that I can judge how far to rely on it. Independent test: search `/knowledge` for "Kuz-Ram" and see the row with its
UNVERIFIED badge and a working citation link.

### US-020-4 (P2) Navigate the method ladder
As a developer, I want one page per method with its baseline, comparison design, criterion, lane and live demo, so that
I can see how each method is judged. Independent test: `/methods/m02/` shows the DES comparison design and links to
`/cases/A1/?tab=simulate`.

### US-020-5 (P1) Use the site in my language, theme and assistive technology, fast
As any visitor, I want every view in English or Spanish, light or dark, usable with a keyboard and a screen reader, and
light to load, so that the site works for me. Independent test: axe and Lighthouse on every route in both themes and
languages; budget report on the built artifact.

### US-020-6 (P3) Understand the architecture
As a reviewer, I want the ⓘ view to explain the product, lanes, studio, web flow, science flow, contracts and tools with
a diagram each, so that I can find my way around the repository. Independent test: open ⓘ, switch theme, and check the
diagrams repaint and the keyboard flow.

| Story | Priority | Title |
|---|---|---|
| US-020-1 | P2 | Learn the theory with live figures |
| US-020-2 | P1 | Check a claim |
| US-020-3 | P2 | Look up a parameter with its source |
| US-020-4 | P2 | Navigate the method ladder |
| US-020-5 | P1 | Use the site in my language, theme and assistive technology, fast |
| US-020-6 | P3 | Understand the architecture |

## 3. Functional requirements (EARS)
Sizes use KB = 10³ bytes and MB = 10⁶ bytes, as specs 001 and 006 do; the git per-file cap stays 10 MiB.

### 3.1 Theory
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-020-01 | Ubiquitous | `/theory` shall list the 13 phenomena — `haulage`, `loading-and-terramechanics`, `drill-and-blast`, `slopes-and-monitoring`, `bulk-flow-dem-mpm`, `comminution`, `dust`, `tailings`, `planning`, `rtx-sensor-physics`, `robot-learning`, `vision-language-reasoning`, `sim-to-real` — each with title, one-line summary, methods and cases, and `/theory/<id>/` shall be a prerendered page answering HTTP 200 for each; any other id shall answer HTTP 404 with the not-found page. | E2E |
| FR-020-02 | Ubiquitous | Each theory page shall be rendered at build time from MDX in EN and ES, and every display equation of `docs/theory/<id>.md` shall appear, after LaTeX whitespace normalisation, in the EN page, with the same set of equation labels in the ES page. | contract |
| FR-020-03 | Unwanted | If an equation does not parse in KaTeX (`throwOnError: true`), then the build shall fail naming the file and line, and no KaTeX error box shall reach a page. | contract |
| FR-020-04 | Ubiquitous | Every equation shall be rendered to HTML and MathML (`output: "htmlAndMathml"`), carry a stable anchor `#eq-<label>`, and be followed by a symbol table giving each symbol's meaning and unit. | E2E |
| FR-020-05 | Ubiquitous | Each theory page shall list its references with DOI or URL, attach a reference to every external number, and show the text badge "UNVERIFIED — pinned at specification" next to every transcription the docs mark as unverified (FR-000-10). | contract + E2E |
| FR-020-06 | Ubiquitous | Each theory page shall contain the interactive figure(s) listed for it in §7.1, each driven by the engine named there. | unit + E2E |

### 3.2 Interactive figures and charts (every analytical chart on any route)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-020-07 | Ubiquitous | Every analytical chart shall support zoom and pan (wheel or pinch, drag, and the keys `+`, `−` and arrows), reset by double-click or a Reset button, and a crosshair read-out at the cursor giving x and y in physical units (SI, or the source's units followed by SI in parentheses). | E2E |
| FR-020-08 | Ubiquitous | Every chart shall draw, as a labelled marker, each feature its engine reports for that figure (§7.1, for example FoS = 1 crossing, x50 and x80, predicted failure time, maximum ground-level concentration and its distance, dam-break front, clip bounds, p = 0.05, AUC = 0.60), and the marker label shall show the same number, with the same rounding, as the read-out panel. | unit + E2E |
| FR-020-09 | Unwanted | If a figure is three-dimensional and its registry entry (DC-020-04) has no `justification3d` naming its third independent variable, then the build shall fail naming the figure. | contract |
| FR-020-10 | Unwanted | If a figure or chart maps continuous data to a colour map other than viridis, cividis, inferno or magma (jet, rainbow, hsv, turbo or a custom gradient included), then the build shall fail naming the figure. | contract |
| FR-020-11 | Ubiquitous | Every chart shall be focusable and keyboard-operable (arrow keys move the crosshair by one data point, `+` and `−` zoom, `0` resets) and shall offer a "Show data" control revealing an HTML table with units in its header cells and the values of every plotted series taken from the full, undecimated data. | E2E |
| FR-020-12 | Ubiquitous | Every chart shall take its colours from the theme tokens and repaint within one frame when the theme changes, without reload; chart source files shall contain no hex colour literal (lint). | E2E + lint |
| FR-020-13 | Event | When the visitor changes any control of a figure, the plotted data shall change within 100 ms, the digest of the plotted series differing between the two settings, for every control of every figure. | E2E |
| FR-020-14 | Unwanted | If a figure control receives an empty, non-numeric, NaN, infinite or out-of-range value, then it shall keep its last valid value, show the allowed range and unit inline, and not call the engine. | E2E (hostile) |
| FR-020-15 | Ubiquitous | Charts shall compute on the full data, draw a min/max-per-pixel-column decimation of it, store series in typed arrays, and keep at most 8 WebGL contexts alive per page. | unit + E2E |
| FR-020-16 | Unwanted | If a theory, method or results page contains a raster image of a chart (any raster image not registered as `kind: photo` with alt text), then the build shall fail naming the file. | contract |

### 3.3 Methods
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-020-17 | Ubiquitous | `/methods` shall list M1–M23 from the method registry (DC-020-01) with tier, implementation and SPDX licence, lane, cases, learned flag and status, and `/methods/<m01…m23>/` shall be a prerendered page answering HTTP 200 for each; any other id shall answer HTTP 404. | E2E |
| FR-020-18 | Ubiquitous | Each method page shall show what the method computes, its baseline and comparison design (metric with unit and orientation, pairing unit, number of pairs), its pre-registered acceptance criterion as recorded in the method registry, its lane with the measured gate values (DC-018-06) or the word "estimate", a link to the case Simulate tab where it runs live, its docs page, and its status ("Not yet run" until a published result exists). | unit + E2E |
| FR-020-19 | Unwanted | If the method registry lacks one of M1–M23, holds another id, uses a tier, lane or licence outside its enums, or lacks an acceptance criterion for a learned method, then the build shall fail naming the entry. | contract |

### 3.4 Results
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-020-20 | Ubiquitous | `/results` shall offer the tabs Learned vs classical · Sim-to-real and sim-to-sim · Parity · DR ablation · Isaac Lab vs baselines · Cosmos vs Qwen vs detector · Acceleration, as a WAI-ARIA tab list whose selection is kept in `?tab=`. | E2E |
| FR-020-21 | Ubiquitous | Every comparison row shall show the metric with unit and orientation, the challenger and the baseline, the pairing unit and n, the paired 95 % confidence interval of the difference with its method (paired t or paired bootstrap), and the verdict of FR-020-22; a result with several axes (for example accuracy, latency, size, robustness) shall show them together and with no composite score. | unit + E2E |
| FR-020-22 | Ubiquitous | The decision-rule display shall show "<challenger> better than <baseline>" only when the oriented interval has lo > 0, "<baseline> better than <challenger>" only when hi < 0, and "no significant difference" otherwise (an interval touching 0 included); for McNemar comparisons it shall require p < 0.05 and take the direction from the discordant counts; for n = 1 it shall show "single real event — no significance test" (FR-000-05). | unit |
| FR-020-23 | Unwanted | If a results entry stores a verdict that differs from the one FR-020-22 derives from its interval or p-value, or has a non-finite bound, lo > hi, n < 2 for a paired claim, or no orientation, then the build shall fail naming the entry. | contract |
| FR-020-24 | Ubiquitous | For each model of plan §7 (D-FINE-N/S, RF-DETR-Seg-N, U-Net, GNS, FNO, PPO and attention dispatch, IL-1, IL-2, slope forecasters, mine-to-mill meta-model, DEM calibration, Cosmos Reason 2, TensorRT engines), `/results` shall show its pre-registered acceptance criterion as recorded in DC-020-01 and the status pass, fail or "Not yet run" computed from the results bundle against that criterion. | unit + E2E |
| FR-020-25 | Ubiquitous | The Sim-to-real tab shall show the fragmentation TSTR/TRTR IoU ratio against 0.90, the C2ST AUCs with their real-versus-real baseline against 0.60 (tabular and 1-D) or an AUC gap ≤ 0.10 (images), the sim-to-sim gaps (FEE → MPM fill gap with its 95 % CI; Isaac Lab → TypeScript twin), "not measured" for equipment and people sim-to-real unless the optional real probe exists, and "calibrated synthetic — not validated against real data" for each data type without a real reference (FR-000-09). | unit + E2E |
| FR-020-26 | Ubiquitous | The Parity tab shall render the parity report of the deployed commit (DC-018-05) grouped by system class: engine, class, tolerance, maximum observed error, browsers and verdict. | unit + E2E |
| FR-020-27 | Ubiquitous | The Cosmos tab shall show, per question type, balanced accuracy with its 95 % CI for Cosmos Reason 2, Qwen3-VL-2B and the detector + geometric rule, the Q8_0 versus BF16 agreement against 95 %, the McNemar p-value of Cosmos versus Qwen, and the attribution "Built on NVIDIA Cosmos"; no Cosmos result shall appear as a headline KPI on `/` or on a case page. | unit + E2E |
| FR-020-28 | Ubiquitous | The Acceleration tab shall show, per model and backend (PyTorch, ORT CPU, ORT CUDA, TensorRT fp32, fp16, int8, fp8), latency p50 and p95 (ms), throughput (items/s), energy per inference (J), accuracy change (percentage points) and the per-engine parity verdict, list failing variants as "rejected" with the reason, and state the conditions (GPU, driver, enforced power limit, throttle fractions, TensorRT licence SHA-256) and "our hardware, not a comparative benchmark". | unit + E2E |
| FR-020-29 | Unwanted | If a results or acceleration entry carries performance data of TensorRT for RTX, Isaac Sim, Kit, Replicator or ovrtx, then the build shall fail naming the entry (FR-000-08). | contract |
| FR-020-30 | Unwanted | If the TensorRT licence SHA-256 recorded with a TensorRT row differs from the reviewed `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4`, then the Acceleration tab shall replace that row's numbers with "measured locally, not published (licence)". | unit |
| FR-020-31 | State | While a comparison, criterion or tab has no published result, `/results` shall show "Not yet run" with what will be reported and its pre-registered criterion, and no placeholder number. | unit + E2E |

### 3.5 Knowledge
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-020-32 | Ubiquitous | `/knowledge` shall offer the sections Glossary · Equations · Parameters · Datasets · Frameworks · Bibliography, generated at build time (DC-020-03) from the `minephys` version pinned in `uv.lock`, `docs/reference/glossary.md`, `data/sources.yaml` and `studio/tools.yaml`, and shall show the `minephys` version and commit it was generated from. | contract + E2E |
| FR-020-33 | Ubiquitous | The parameter browser shall show one row per knowledge-table row with id, value or range, units as published, the SI value, the citation linking to its bibliography entry, page or table, verification status and code symbol; it shall filter by module and status and search by text, and every UNVERIFIED row shall carry the text badge "UNVERIFIED — pinned at specification" with an icon. | unit + E2E |
| FR-020-34 | Ubiquitous | The equation explorer shall show, per `minephys` equation, the rendered LaTeX, its symbols with units, source and page, verification status, the implementing `minephys` symbol, a link to its theory anchor and, where a browser engine of spec 007, 013, 014 or 018 implements it, a "Try it" panel that evaluates it with that engine. | unit + E2E |
| FR-020-35 | Ubiquitous | The glossary shall show for every term the EN term, the ES term, the definition in the active language and its source where one exists, and its search shall match either language ignoring case and accents. | unit + E2E |
| FR-020-36 | Ubiquitous | The datasets section shall list every entry of `data/sources.yaml` with id, real or synthetic, SPDX licence, redistribution class, landing URL and dataset-card link, with "fetched by the pipeline, never redistributed" for third-party data. | unit + E2E |
| FR-020-37 | Ubiquitous | The frameworks section shall list every `studio/tools.yaml` entry, the evaluated-not-adopted ones included, each linking to `/studio/tools/<id>/`. | unit |
| FR-020-38 | Ubiquitous | The bibliography shall render every `references.bib` entry with its DOI or URL and a stable anchor equal to its citation key, and list for each entry the parameters and equations that cite it. | unit + E2E |
| FR-020-39 | Unwanted | If generation finds a knowledge row without citation, units, page or verification status, a verification value other than `verified` or `UNVERIFIED`, a citation key missing from `references.bib`, a bibliography entry with neither DOI nor URL, a glossary entry without ES text, or a duplicate id, then the build shall fail naming the file and row (FR-000-10). | contract (hostile) |
| FR-020-40 | Ubiquitous | Knowledge generation shall be deterministic — two generations from the pinned inputs give a byte-identical bundle — and CI shall fail when the committed generated pages under `docs/knowledge/` differ from a fresh generation. | contract |
| FR-020-41 | Unwanted | If a search query, typed or from `?q=`, contains markup, regular-expression metacharacters, control or bidirectional characters, or more than 2,000 characters, then the search shall match it as literal text (truncated to 2,000 characters), render highlights as escaped text and raise no error. | unit + E2E (hostile) |
| FR-020-42 | Unwanted | If a headline KPI's manifest lists an UNVERIFIED knowledge row among its inputs (an input with `kind: knowledge` and the knowledge-table row id as its `id`, see 001 data-model §2), then the KPI shall not be shown as a headline on `/` or `/results` and shall carry the UNVERIFIED badge wherever it appears. | unit + E2E |

### 3.6 The ⓘ modal
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-020-43 | Ubiquitous | The ⓘ modal shall have at least the seven tabs What it is · Lanes · Studio · Web flow · Science flow · Contracts · Tools, each with EN and ES text and an inline SVG diagram from `docs/assets/diagrams/` whose embedded custom-property token block is removed when it is inlined, so that its colours come from the app's theme tokens and repaint on a theme change without reload. | E2E |
| FR-020-44 | State | While the ⓘ modal is open, focus shall stay inside it and the arrow keys shall move between tabs; Escape shall close it and return focus to the ⓘ button. | E2E |
| FR-020-51 | Unwanted | If a diagram referenced by an ⓘ tab or a theory page is missing, is not well-formed SVG, contains a hex colour literal outside its custom-property token block (for example a `fill="#…"` attribute), a script element, an event-handler attribute, or an `href` / `xlink:href` to another file or origin (namespace declarations excepted), then the build shall fail naming the file. | contract (hostile) |

### 3.7 Languages, themes and teaching functions
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-020-45 | Unwanted | If a locale namespace has a key in EN that is missing in ES or the reverse, or a component renders a JSX text literal outside the locale files, then CI shall fail naming the key or file (FR-000-03). | contract + lint |
| FR-020-46 | Ubiquitous | For every text colour token and every surface token it can sit on, in both themes, the contrast ratio computed with the WCAG 2.2 relative-luminance formula shall be ≥ 4.5:1 for normal text and ≥ 3:1 for large text and non-text marks. | unit |
| FR-020-47 | Unwanted | If a theory or method page exists in one language only, or its ES page differs from its EN page in the sets of equation labels, figure ids or reference keys, then the build shall fail naming the page. | contract |
| FR-020-48 | Unwanted | If `?tab=`, `?q=`, `?module=`, `?status=` or `?lang=` on `/theory`, `/methods`, `/results` or `/knowledge` is unknown, malformed or longer than 2,000 characters, then the page shall fall back to its default, render normally, raise no uncaught error and request no resource derived from the value. | E2E (hostile) |
| FR-020-49 | Ubiquitous | The teaching functions of `web/src/theory/fn/` (Beverloo discharge, Ritter dam break, lidar range with Beer–Lambert extinction, PPO clipped objective, exact McNemar test, Gaussian two-sample AUC, paired-t interval) shall equal their analytical forms on hand-calculated cases and SciPy reference values within rtol 1e-9. | unit + parity |
| FR-020-50 | Unwanted | If a teaching function receives NaN, ±Infinity or an argument outside its domain (D ≤ 0, d ≤ 0, h₀ ≤ 0, t < 0, R ≤ 0, ε ∉ (0, 1), non-integer or negative counts, n < 2, σ ≤ 0), then it shall throw a `RangeError` naming the argument and return no value. | unit (hostile) |

## 4. Correctness properties
fast-check with 200 examples per property in CI and 2,000 at release (`property_tests`).

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-020-01 | Verdict orientation flip: negating the interval and flipping the orientation swaps the roles of challenger and baseline in the verdict and keeps "no significant difference" unchanged. | lo ≤ hi finite, both orientations | exact |
| P-020-02 | Verdict widening: widening the interval (lo′ ≤ lo, hi′ ≥ hi) never turns "no significant difference" into a "better than" verdict. | random intervals | exact |
| P-020-03 | Verdict unit invariance: multiplying both bounds by k > 0 leaves the verdict unchanged. | k ∈ [10⁻⁶, 10⁶] | exact |
| P-020-04 | Decimation keeps extremes: for every pixel column, its minimum and maximum, and the global minimum and maximum, appear in the output exactly. | series length 1..10⁶, columns 1..4,096, values incl. ±1e300 | exact |
| P-020-05 | Decimation idempotence: with n ≤ 2 × columns the output equals the input; decimating an output again changes nothing. | as P-020-04 | exact |
| P-020-06 | Decimation affine equivariance: decimate(a y + c) selects the same sample indices as decimate(y) for a > 0, and output times are strictly increasing. | a ∈ (0, 10³], c ∈ [−10⁶, 10⁶] | exact (indices) |
| P-020-07 | Zoom about the cursor keeps the data point under the cursor at the same screen position. | zoom factors [0.1, 10], any cursor | ≤ 0.5 px |
| P-020-08 | Zooming in and then out by the same factor about the same point restores the view. | as P-020-07 | rtol 1e-12 |
| P-020-09 | Screen → data → screen round trip of the read-out returns the cursor position. | linear and log axes | ≤ 0.5 px |
| P-020-10 | Beverloo discharge is linear in the bulk density ρ_b. | ρ_b ∈ [500, 3,000] kg/m³ | rtol 1e-12 |
| P-020-11 | Beverloo discharge is 0 for D ≤ k d and strictly increasing in D above it. | D, d in the validity range | exact |
| P-020-12 | Beverloo scaling: multiplying D and d by λ multiplies the discharge by λ^{5/2}. | λ ∈ [0.1, 10] | rtol 1e-12 |
| P-020-13 | Ritter self-similarity: h(λx, λt) = h(x, t) for λ > 0, and h(0, t) = 4h₀/9. | x ∈ [−3c₀t, 3c₀t] | rtol 1e-12 |
| P-020-14 | Ritter mass conservation: ∫ h dx over the domain equals h₀ L while the rarefaction has not reached the back wall (t < L/c₀). | L ∈ [10, 10³] m, quadrature 10⁵ points | rtol 1e-6 |
| P-020-15 | Ritter depth scaling: multiplying h₀ by k multiplies the front speed 2√(g h₀) by √k. | k ∈ [0.1, 10] | rtol 1e-12 |
| P-020-16 | Lidar received power is linear in target reflectivity. | ρ ∈ (0, 1] | rtol 1e-12 |
| P-020-17 | Without extinction, doubling the range quarters the received power. | R ∈ [1, 10³] m | rtol 1e-12 |
| P-020-18 | Extinction σ multiplies the received power by the two-way transmittance e^{−2σR}. | σ ∈ [0, 0.1] m⁻¹ | rtol 1e-12 |
| P-020-19 | PPO clip is positively homogeneous in the advantage: L(r, kA) = k L(r, A) for k > 0. | r ∈ [0, 3], A ∈ [−10, 10] | rtol 1e-12 |
| P-020-20 | PPO clip at r = 1 equals the advantage: L(1, A) = A. | A ∈ [−10, 10] | exact |
| P-020-21 | PPO clip saturation: for A > 0, L is constant for r ≥ 1 + ε; for A < 0, L is constant for r ≤ 1 − ε. | ε ∈ (0, 1) | exact |
| P-020-22 | McNemar symmetry: p(b, c) = p(c, b). | b, c ∈ 0..10⁴ | exact |
| P-020-23 | McNemar null: p(b, b) = 1. | b ∈ 0..10⁴ | exact |
| P-020-24 | McNemar monotonicity: at fixed b + c, p is non-increasing in ∣b − c∣. | b + c ∈ 1..10⁴ | exact (order) |
| P-020-25 | Gaussian AUC scale invariance: AUC(kΔμ, kσ) = AUC(Δμ, σ). | k ∈ [10⁻³, 10³] | rtol 1e-12 |
| P-020-26 | Gaussian AUC antisymmetry: AUC(−Δμ, σ) = 1 − AUC(Δμ, σ), and AUC(0, σ) = 0.5 exactly. | Δμ/σ ∈ [−10, 10] | atol 1e-12 (exact at 0) |
| P-020-27 | Gaussian AUC is strictly increasing in Δμ/σ. | Δμ/σ ∈ [−8, 8] | exact (order) |
| P-020-28 | Paired-t interval translation: adding c to every difference shifts both bounds by c. | n ∈ 2..10³ | rtol 1e-12 |
| P-020-29 | Paired-t interval scaling: multiplying every difference by k > 0 multiplies both bounds by k. | k ∈ [10⁻³, 10³] | rtol 1e-12 |
| P-020-30 | Paired-t interval width is strictly decreasing in n at a fixed sample standard deviation. | n ∈ 2..10³ | exact (order) |
| P-020-31 | Knowledge generation determinism: generating twice, or after shuffling row order in the input YAML files, gives a byte-identical bundle. | the pinned tables with random row orders | exact |
| P-020-32 | Search normalisation and refinement: results(q) = results(upper(q)) = results(strip-accents(q)), and appending characters to q never adds results. | random queries over the glossary and parameters | exact |

## 5. Non-functional requirements and success criteria
| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-020-01 | Initial JavaScript of every prerendered route (each dynamic template included) (NFR-000-01) | ≤ 200 KB gzip each (200,000 bytes; the current postbuild constant of 200 × 1024 bytes is aligned) | `web/scripts/postbuild.mjs` extended to every route |
| NFR-020-02 | First view of every top-level route other than `/` (whose budget is NFR-018-01) and of one instance of each dynamic template (NFR-000-03) | ≤ 2 MB encoded bytes before interaction | Playwright + CDP |
| NFR-020-03 | Per-class budgets on the built Pages artifact, each file assigned through its manifest `budget_class` (unlisted files count as own code) (NFR-000-04, NFR-000-07) | videos ≤ 150 MB; tiles + glb ≤ 95 MB; replay shards + point clouds ≤ 60 MB; splats ≤ 25 MB; ONNX ≤ 80 MB; runtimes ≤ 55 MB; own JS/WASM/fonts ≤ 10 MB; studio showcase ≤ 25 MB; total ≤ 500 MB | CI budget script over `web/build/client` |
| NFR-020-04 | Equations are rendered at build: the client bundles contain no KaTeX JavaScript, and KaTeX CSS and fonts are requested only on pages with equations | 0 KaTeX JS bytes; 0 KaTeX requests on equation-free pages | build report + Playwright |
| NFR-020-05 | Accessibility: every top-level route in light and dark × EN and ES, one instance of every dynamic template in the four combinations, every prerendered instance in light/EN (NFR-000-02) | axe 0 serious/critical | Playwright + axe |
| NFR-020-06 | Lighthouse on each top-level route, one theory page and one method page | accessibility ≥ 0.95; performance warns below 0.80 | LHCI |
| NFR-020-07 | Figures: first interactive render after entering the viewport; frame time while zooming | ≤ 1 s on CI Chromium; p95 ≤ 16.7 ms on the reference desktop (reported, warning in CI) | Playwright performance marks |
| NFR-020-08 | Knowledge search latency over 10⁴ rows | p95 ≤ 100 ms over 50 queries | Playwright |
| NFR-020-09 | Quality of `web/src/charts/**`, `web/src/theory/fn/**`, `web/src/results/verdict*`, `web/src/knowledge/search*` | branch coverage ≥ 0.85; mutation ≥ 0.80 (fail < 0.70) | Vitest coverage; Stryker |
| SC-020-01 | At the web gate, every prerendered route meets NFR-020-05 and NFR-020-06 in both themes and both languages | 100 % of routes | CI report |
| SC-020-02 | Every model row of plan §7 has its criterion and a computed status on `/results` | 13 of 13 rows present | E2E on the release build |
| SC-020-03 | At release, no headline KPI depends on an UNVERIFIED value | 0 headline KPIs flagged by FR-020-42 | CI report |

## 6. Data contracts
| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-020-01 | Method registry `studio/methods.yaml`: id M1–M23, names EN/ES, tiers, implementation, SPDX licence, lane, learned flag, cases, baseline, metric with unit and orientation, pairing unit, n, pre-registered acceptance criterion (copied from the owning model spec), docs page | `contracts/methods.schema.json` (new) | maintainer → `/methods`, `/results`, CI cross-checks |
| DC-020-02 | Results bundle `web/public/results/<comparison-id>.json`: case, challenger, baseline, metric, unit, orientation, pairing unit, n, interval lo/hi and method, p-value for McNemar, stored verdict, criterion status, run ids; for acceleration rows the backend, precision, timings, energy, parity and conditions | `contracts/results.schema.json` (new) | `s50_evaluate`, `s64_bench` (spec 016), Cosmos evaluation (spec 015), via `studio publish` → `/results`, case Charts tabs (018), CI verdict check |
| DC-020-03 | Knowledge bundle `web/public/knowledge/bundle.json` and generated `docs/knowledge/*.md` | `contracts/knowledge-bundle.schema.json` (new) | `tools/build_knowledge.py` (root environment, pinned `minephys`) → `/knowledge`, theory symbol tables, equation explorer, CI drift check |
| DC-020-04 | Figure registry `web/src/theory/figures.yaml`: figure id, topic, engine, controls with ranges and units, marked features, colour map, `justification3d` | `contracts/figures.schema.json` (new) | maintainer → figure components, CI rubric checks (FR-020-09, FR-020-10, FR-020-16) |

Consumed, defined elsewhere: the case registry (DC-018-01), the parity report (DC-018-05), the lane measurements
(DC-018-06), the web manifest (DC-000-01), the tool registry (DC-000-04) and the data registry (DC-000-05).

## 7. Edge cases and assumptions

### 7.1 Figure table (at least one interactive figure per theory page)
| Topic | Figure id | Engine | Controls (units) | Marked features |
|---|---|---|---|---|
| haulage | `haulage-speed-grade` | `haulage` (spec 007 port) | grade (%), payload (t), drive (diesel, trolley, battery-electric) | operating speed at the grade; retarder limit |
| loading-and-terramechanics | `fee-force-depth` | `il2-twin` FEE force (spec 014) | cutting depth (m), cohesion (kPa), friction angle (°) | maximum cutting force |
| drill-and-blast | `psd-kuzram-swebrec` | `blasting` (spec 018) | powder factor (kg/m³), burden (m), rock factor (–) | x50, x80, % oversize at the crusher gape |
| slopes-and-monitoring | `inverse-velocity`, `fos-cohesion` | `geotech` (spec 018) | record cut-off (% of record), smoothing window (h); cohesion (kPa), friction angle (°) | predicted failure time (1/v = 0) and the cut-off; FoS = 1 crossing |
| bulk-flow-dem-mpm | `beverloo-discharge` | teaching `beverloo` | orifice D (m), grain d (mm), C (–), k (–), ρ_b (kg/m³) | D = k d (no flow); operating point |
| comminution | `bond-energy` | `comminution` (spec 018) | F80 (µm), P80 (µm), work index (kWh/t) | F80; chosen P80 and its energy |
| dust | `plume-ground-field` (2-D field, viridis) | `plume` (spec 018) | source strength (g/s), wind speed (m/s), stability class, release height (m) | maximum ground-level concentration and its downwind distance |
| tailings | `ritter-dam-break` | teaching `ritter` | initial depth h₀ (m), time (s) | front position 2√(g h₀) t; depth 4h₀/9 at the dam |
| planning | `nested-pits` (2-D section) | `mincut` (spec 018) | revenue factor (–), slope angle (°) | optimal pit outline and its value |
| rtx-sensor-physics | `lidar-range-dust` | teaching `lidarRange` | range (m), dust concentration (mg/m³), reflectivity (–) | maximum detection range at the receiver threshold |
| robot-learning | `ppo-clip` | teaching `ppoClip` | clip ε (–), advantage sign | clip bounds 1 − ε and 1 + ε |
| vision-language-reasoning | `mcnemar` | teaching `mcnemar` | discordant counts b and c | p-value and the p = 0.05 line |
| sim-to-real | `c2st-auc`, `paired-ci` | teaching `gaussianAuc`, `pairedTCi` | separation Δμ/σ (–); n, mean and SD of the differences | AUC = 0.60 line; the interval against 0 with its verdict |

Default control values come from the `minephys` knowledge tables; a default taken from an UNVERIFIED row shows the
UNVERIFIED badge next to the control. Tests use hand-chosen inputs, so no oracle depends on an unverified value.

### 7.2 Other assumptions
- Tolerances: rtol 1e-12 for closed forms of a few binary64 operations (error ≤ 10 ε ≈ 2.2e-15); rtol 1e-9 against
  SciPy, whose special functions (`ndtr`, `stdtrit`, binomial CDF) are accurate to about 1e-14 while the TypeScript
  implementations use rational approximations accurate to about 1e-12; rtol 1e-6 for the Ritter integral with 10⁵
  trapezoid points (the kink at the front limits the trapezoid error to O(Δx) on one cell).
- Plotted digests (FR-020-13) are SHA-256 of the plotted Float64Array; a control whose valid range is a single value
  is exempt and listed in DC-020-04.
- Budgets use the class ids of spec 001's manifest field `budget_class` and the caps of spec 016 (Table B: `videos` 150,
  `tiles-glb` 95, `shards-clouds` 60, `splats` 25, `onnx` 80, `runtimes` 55, `own-code` 10, `studio-showcase` 25;
  total 500 MB), which equal `docs/web/budgets.md`. `thresholds.yaml` has no `budgets` section yet although NFR-000-04
  refers to it; its `budgets.*` keys and `budgets.first_view_mb_max: 2` are proposed keys, pending maintainer approval. Spec 016 checks the budgets at export
  (FR-016-17); NFR-020-03 checks the built Pages artifact, the last point before deploy.
- The pre-registered acceptance criteria are owned as SC rows by the model specs (007, 009, 010, 011, 012, 014, 015,
  016); this spec displays them from DC-020-01 and never redefines them.
- No constant used by an oracle here is UNVERIFIED.

## 8. Clarifications log
- Resolved — *where the interactive-figure rules live.* The docs do not describe them yet; FR-020-07…16 state them once
  for the whole site and specs 018 and 019 refer to them. The coordinator may add a docs page that cites this spec.
- Resolved — *detail routes.* The plan lists `/theory` and `/methods`; the docs give one theory page per phenomenon and
  one method page per method, so both have an index plus prerendered detail pages (13 and 23).
- Resolved — *one source for equations.* Theory MDX lives in `web/`; `docs/theory/` stays the source of the equations and
  FR-020-02 checks that the web pages carry the same ones.
- Resolved — *verdict when the baseline wins.* FR-000-05 permits a "better than" claim whenever the interval excludes
  0, so an interval entirely below 0 reads "<baseline> better than <challenger>"; an interval touching 0 does not
  exclude it.
- Resolved — the method registry lives in `studio/methods.yaml`, next to `studio/tools.yaml` and `studio/cases.yaml`.
- Resolved — site-wide byte budgets are verified here (per-route and per-class); spec 016 keeps the export-side per-file
  caps.
- Resolved — the UNVERIFIED-in-headline rule needs manifests to name knowledge rows as inputs (`kind: knowledge`, row id as `id`);
  this id convention is requested from spec 001's manifest schema.
- Resolved — "TensorRT for RTX stays internal" (plan §11) is enforced by failing the build (FR-020-29), not by hiding
  rows at run time.
- Resolved — the "Try it" panel of the equation explorer reuses existing browser engines (specs 007, 013, 014, 018); no new engine is added for it.
- Resolved — *units.* MB = 10⁶ bytes and KB = 10³ bytes, as specs 001 and 006 read the plan's budgets; the existing initial-JS check, written with 200 × 1024 bytes, is aligned to 200,000 bytes by T-020-062.
- Integration 2026-10-07: budget-class ids follow spec 001's manifest field `budget_class` (`tiles-glb`,
  `shards-clouds`, `own-code`, `studio-showcase`); the `budgets.*` threshold keys this spec relies on are proposed keys,
  pending maintainer approval (the first-view key is proposed as `budgets.first_view_mb_max`, not `web.first_view_mb_max`).

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
- (none beyond this spec; the stub pages of `/theory`, `/methods`, `/results` and `/knowledge` are replaced, no
  requirement is retired)
### MODIFIED Requirements
- (none)
### REMOVED Requirements
- (none)
