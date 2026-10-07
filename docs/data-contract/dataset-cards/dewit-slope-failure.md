# de Wit — open-pit slope failure series

> The only openly licensed displacement record of a real open-pit slope failure found: one event (n = 1), used for a
> descriptive time-of-failure check in case C1. · Part of: [Dataset cards](README.md) · Related:
> [C1 Slope time of failure](../../cases/c1-slope-time-of-failure.md) ·
> [M14 Slope forecasting](../../methods/m14-slope-forecasting.md) ·
> [Slope forecasters](../../models/slope-forecasters.md) · [Synthetic data](synthetic-data.md)

## What and why

Time-of-failure (TTF) forecasting from slope displacement is the core of C1. Real pre-failure series are rare and
usually confidential. The de Wit (2025) dataset from the Colorado School of Mines releases, under CC BY 4.0, the
data of a study of a real open-pit slope failure: velocity changes from seismic noise interferometry, seismic events,
weather and **radar-derived surface deformation** [1]. It is the only openly licensed real open-pit failure
displacement series found.

Because it is **one event**, PitStudio uses it for an honest, descriptive check of the forecasters, and relies on
many seeded synthetic Voight events ([Synthetic data](synthetic-data.md)) for every statistical claim.

## Datasheet

### Composition

- **Title:** "Data used for the study of time-lapse velocity variations during an open-pit mine slope failure using
  seismic noise interferometry" [1].
- **Content:** seismic velocity changes, seismic events, weather records and radar-derived surface deformation of one
  slope failure at an open-pit mine; the mine is not named [1].
- **Files:** `Data.zip`, 8.9 MB [1]. The inner file formats and the radar series' sampling interval and units are
  read after download and recorded in the manifest (not asserted here).
- **Companion record:** a 7.5 GB+ HDF5 cross-correlation record, CC BY 4.0, DOI 10.5281/zenodo.14969229 [2]. It is
  optional and not needed for the displacement series.

### Collection and provenance

- **Author and institution:** de Wit, Colorado School of Mines [1].
- **Collection:** monitoring data from the failure study (seismic noise interferometry plus the mine's radar
  deformation and weather records), packaged by the author [1].
- **Version read:** Zenodo record published 2025-03-11, read on 2026-10-02 [1].
- **Landing page and DOI:** https://zenodo.org/records/15003054, DOI 10.5281/zenodo.15003054 [1].
- **Related article:** in *Geophysical Research Letters*; its DOI was not confirmed (UNVERIFIED).

### Licence and attribution

- **SPDX:** `CC-BY-4.0`. **Licence class:** `attribution`. **Redistribution class:** `redistributable`; PitStudio
  commits derived series only.
- **Attribution text**, reproduced verbatim on every derived artefact:
  "de Wit (2025). Data used for the study of time-lapse velocity variations during an open-pit mine slope failure
  using seismic noise interferometry. Zenodo. https://doi.org/10.5281/zenodo.15003054. Licensed under CC BY 4.0."
- **Conflicts:** none found.

### Size, checksums and access

- **Size:** 8.9 MB (`Data.zip`); optional companion 7.5 GB+ [1][2].
- **Checksum:** MD5 published by Zenodo [1]; `s00_download` checks it and pins a SHA-256 at first download.
- **Account:** none.
- **Programmatic path:** Zenodo record API → HTTPS download by pooch [1].
- **Fallback:** none needed (open, small).

## How the single event is used

Let $t_f$ (h) be the observed failure time and $t_0$ (h) the start of the displacement record. A **record cut-off**
$c \in \{0.5, 0.8\}$ gives the forecaster only the data up to

$$t_c = t_0 + c\,(t_f - t_0).$$

The forecaster returns $\hat t_f^{(c)}$, and the card reports the **TTF error** $e_c = \hat t_f^{(c)} - t_f$ (h) and
its ratio to the remaining lead time $t_f - t_c$ (h), for the inverse-velocity baseline and each learned forecaster.

- **Descriptive only.** With one event there is no distribution of errors, so no confidence interval, no ranking and
  **no "better than" claim**. The UI shows "single real event — no significance test".
- **Never used for a classifier two-sample test, TSTR or TRTR.** Synthetic-data validation uses fragment images and
  terrain statistics; a single series cannot support it.
- **Inverse velocity** (the classical baseline) follows Voight's material-failure law [3] with the practice
  guidelines of Carlà et al. [4]; its use on ground-based radar in open pits is documented by Dick et al. [5]. The
  equations live on the [M14 page](../../methods/m14-slope-forecasting.md).
- **Noise level.** The noise observed on this series informs the noise model of the synthetic Voight generator, so
  that the synthetic criterion ("TTF error ≤ 10 % of lead time at the observed SNR") is stated against a real level.

## Assumptions and limits

- **n = 1.** One failure at one unnamed mine. Every result on it is an anecdote with numbers, not evidence of skill.
- **Unknown site context.** Geology, slope geometry and failure mechanism are not given [1]; the series cannot be
  tied to a slope-stability (LEM) section.
- **Radar processing is the mine's.** PitStudio uses the deformation as delivered and does not re-process it.
- **Cut-offs are fixed in advance** (50 % and 80 %), so they cannot be tuned after seeing the forecast.

## In PitStudio

- **Source id:** `dewit-slope-failure` in `data/sources.yaml`.
- **Stages:** `s00_download` → `s10_preprocess` (extract the displacement series, resample, record units) →
  `s40_infer` (forecasts at the two cut-offs) → `s50_evaluate` (descriptive TTF errors) → `s60_export`.
- **Cases:** [C1](../../cases/c1-slope-time-of-failure.md).
- **Methods:** [M14](../../methods/m14-slope-forecasting.md) inverse velocity + Bayesian TTF vs TCN / PatchTST /
  Chronos-Bolt; [M23](../../methods/m23-rtx-sensor-simulation.md) analytical slope-radar noise.
- **Models:** [Slope forecasters](../../models/slope-forecasters.md) (evaluated, never trained on this series).
- **Committed:** the derived displacement series and the descriptive TTF table, with the attribution text.
  **Never committed:** `Data.zip` or its raw contents.
- **Status:** **Not yet downloaded by the pipeline** — fetched by `s00_download` in the data-and-models phase.

## References

1. de Wit (2025). "Data used for the study of time-lapse velocity variations during an open-pit mine slope failure
   using seismic noise interferometry". Zenodo. https://doi.org/10.5281/zenodo.15003054 — record API:
   https://zenodo.org/api/records/15003054 (accessed 2026-10-02)
2. de Wit (2025). Companion HDF5 cross-correlation record. Zenodo. https://doi.org/10.5281/zenodo.14969229
   (found via https://zenodo.org/api/records?q=%22open%20pit%22%20AND%20resource_type.type:dataset&size=25&sort=mostviewed,
   accessed 2026-10-02)
3. Voight, B. "A method for prediction of volcanic eruptions", *Nature* 332:125–130, 1988.
   https://doi.org/10.1038/332125a0
4. Carlà, T. et al. "Guidelines on the use of inverse velocity method as a tool for setting alarm thresholds and
   forecasting landslides and structure collapses", *Landslides* 14(2):517–534, 2017.
   https://doi.org/10.1007/s10346-016-0731-5
5. Dick, G. J. et al. "Development of an early-warning time-of-failure analysis methodology for open-pit mine slopes
   utilizing ground-based slope stability radar monitoring data", *Canadian Geotechnical Journal* 52(4):515–529,
   2015. https://doi.org/10.1139/cgj-2014-0028
