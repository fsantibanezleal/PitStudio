# M14 — Slope time-of-failure: inverse velocity and Bayesian updating vs TCN, PatchTST and Chronos-Bolt

> When a pit wall starts to accelerate, radar displacement series are extrapolated to a time of failure; the classical
> inverse-velocity method and its Bayesian update are compared with small learned forecasters on many seeded
> synthetic events and, descriptively, on one real recorded failure. · Part of: [Methods](README.md) · Related:
> [Slopes and monitoring theory](../theory/slopes-and-monitoring.md) · [M13 LEM](m13-slope-stability-lem.md) ·
> [M23 slope radar model](m23-rtx-sensor-simulation.md) · [Slope forecaster cards](../models/slope-forecasters.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical vs SOTA | **yes** (forecasters) | live | [C1](../cases/c1-slope-time-of-failure.md) | `minephys.geotech` (inverse velocity, Bayesian TTF); PyTorch TCN / PatchTST; Chronos-Bolt-tiny (Apache-2.0) | not yet implemented |

## What and why

Slope-monitoring radar turned wall failures from surprises into managed events: in one widely reported 2013 open-pit
slide, radar scanning every 6–8 minutes tracked movement of about 2 inches per day, the area was evacuated and no one
was hurt [10]. The forecasting tool behind such decisions is the **inverse-velocity method**: under accelerating
creep, the reciprocal of velocity falls roughly linearly to zero at failure [2]. It is simple, transparent and
noise-sensitive; guidelines for its use in alarm thresholds and forecasting exist [1], open-pit monitoring methods are
reviewed in [3], and ground-based radar practice in open pits systematises pixel selection and filtering [4].

Learned forecasters promise to cope better with noise and non-linear phases [5]. M14 tests that promise without
over-claiming:

- on **many seeded synthetic events** from the Voight creep law, where the true failure time is known, learned and
  classical forecasts are compared under the [decision rule](README.md#how-methods-are-compared);
- on the **one real open-pit failure series** available under an open licence, results are reported descriptively at
  fixed cut-offs, with no significance test, because $n = 1$.

## The algorithm

### Accelerating creep and inverse velocity

Voight's material-failure relation describes the terminal stage of failure [6][7]:

$$
\ddot\Omega = A\,\dot\Omega^{\alpha}
$$

where $\Omega$ is the displacement (mm), $\dot\Omega = v$ its rate (mm/day), $A$ and $\alpha > 1$ empirical constants.
Integrating gives

$$
\frac{1}{v} = \big[A(\alpha - 1)(t_f - t)\big]^{1/(\alpha-1)},
\qquad \alpha = 2:\ \frac{1}{v} = A\,(t_f - t)
$$

so for $\alpha \approx 2$ the inverse velocity is linear in time and the failure time $t_f$ (days) is its time-axis
intercept — Fukuzono's method, applied to open pits by Rose and Hungr [2]. Over a sliding window of filtered
velocities, an ordinary least-squares fit $1/v_k = \beta_0 + \beta_1 t_k$ gives $\hat t_f = -\beta_0/\beta_1$ (for
$\beta_1 < 0$).

### Bayesian time-to-failure

Treating $(\beta_0, \beta_1)$ as uncertain gives a distribution for $t_f$ instead of a point. With a Gaussian prior
$\mathcal N(\mu_0, \Sigma_0)$, design matrix $X$ (rows $[1, t_k]$), observations $y$ ($1/v_k$) and noise variance
$\sigma^2$, the conjugate posterior is

$$
\Sigma_N = \left(\Sigma_0^{-1} + \tfrac{1}{\sigma^2}X^{\top}X\right)^{-1}, \qquad
\mu_N = \Sigma_N\left(\Sigma_0^{-1}\mu_0 + \tfrac{1}{\sigma^2}X^{\top}y\right)
$$

and the predictive distribution of $t_f = -\beta_0/\beta_1$ is sampled from it. The posterior is updated sequentially
as each radar scan arrives, so the forecast and its interval tighten as failure approaches. This is the standard
conjugate Bayesian linear regression; no single mining-specific primary source is pinned for it (citation
UNVERIFIED).

### Learned forecasters

| Model | Architecture | Size (ONNX) | Licence |
|---|---|---|---|
| TCN | stacked dilated causal 1-D convolutions with residual blocks; outperforms canonical recurrent networks with longer effective memory [8] | < 4 MB | own |
| PatchTST | Transformer over patches of the series, channel-independent [9] | < 4 MB | own |
| Chronos-Bolt-tiny | pretrained time-series foundation model (9 M parameters), direct multi-quantile encoder–decoder; "up to 250 times faster and 20 times more memory-efficient" than the original Chronos [11] | ~18 MB | Apache-2.0 |

For a TCN with kernel size $k$ and one convolution per level at dilations $d_l$, the receptive field is
$1 + (k-1)\sum_l d_l$ samples, which sets how much history the model can use [8]. **Inputs:** a window of
line-of-sight displacement and velocity samples (and their timestamps). **Outputs:** quantile forecasts of future
velocity, from which the time at which forecast inverse velocity reaches zero is read; the exact read-out head is fixed
in the spec. **Loss:** a quantile loss over the forecast horizon. Chronos-Bolt is used zero-shot and fine-tuned; a
community ONNX export of Chronos-Bolt-tiny outputs embeddings, not forecasts, so PitStudio exports its own forecasting
head (export feasibility UNVERIFIED until tested) [12].

### Data

- **Synthetic (training and the paired comparison):** many seeded Voight creep events with random $A$, $\alpha$,
  $t_f$ and onset, plus measurement noise and sampling matched to the signal-to-noise ratio observed in the real
  series. Labelled "calibrated synthetic".
- **Real (descriptive only):** the de Wit open-pit slope-failure dataset (CC BY 4.0; 8.9 MB, plus an optional 7.5 GB
  HDF5 companion; mine anonymised) [13] — **one event**. Optional: EGMS deformation over the Hambach pit (derived-only
  terms) for context.
- **Budget:** under 2 GPU-hours for all forecasters (estimate).

```text
evaluate(event, cutoff_fraction):
    obs = event.series[: cutoff_fraction * len]            # data up to the forecast time t
    lead = event.t_f - obs.t_end
    for method in [inverse_velocity, bayes_ttf, tcn, patchtst, chronos_bolt]:
        t_f_hat = method.forecast(obs)
        error[method] = |t_f_hat - event.t_f| / lead        # fraction of lead time
```

### Worked example (illustrative numbers)

Inverse velocities of 0.50, 0.40, 0.30 and 0.20 day/mm at $t$ = 0, 1, 2 and 3 days lie on $1/v = 0.5 - 0.1\,t$, so
$\hat t_f = 0.5/0.1 = 5$ days. At $t = 3$ days the lead time is 2 days, and the pre-registered tolerance of 10 % of the
lead time is ±0.2 day (±4.8 h).

## Baseline and comparison

- **Classical baselines:** inverse velocity (point) and the Bayesian update (distribution).
- **Synthetic, paired:** each seeded event is one pair unit; on event $i$ the paired difference is the inverse-velocity
  error minus the learned-model error (both as fractions of lead time). "Better than inverse velocity" only by the
  [decision rule](README.md#how-methods-are-compared).
- **Real, descriptive:** TTF error of every method at the 50 % and 80 % record cut-offs of the de Wit series, shown as
  numbers with **no "better than" claim**; the UI says "single real event — no significance test".
- **TensorRT:** these models are tiny, so they serve as a negative control in the acceleration table (no material gain
  expected; estimate).

## Acceptance criterion (pre-registered)

- **Synthetic (many seeded Voight events): TTF error ≤ 10 % of lead time at the observed SNR.**
- **"Better than inverse velocity" only by the decision rule (pairs = seeded events).**
- **Real de Wit series = one event ($n = 1$): TTF error at the 50 % and 80 % record cut-offs reported descriptively,
  no "better than" claim; the UI says "single real event — no significance test".**
- Export parity: fp32 rtol 1e-3 / atol 1e-5 for every exported forecaster.

**Results: Not yet run** — produced in the data-and-models phase. Reported: error distributions per method on the
synthetic events with paired CIs, the two real cut-off errors, and forecast plots with intervals.

## Lane and web delivery

**Live.** Inverse velocity and the Bayesian update run in TypeScript (`minephys.geotech` twin); TCN and PatchTST
(< 4 MB) and Chronos-Bolt-tiny (~18 MB) run in ONNX Runtime Web. Long-short-term-memory models are not used, keeping the
graphs on well-supported operators. The visitor slides the forecast time along the real and synthetic series and sees
every method's forecast update. Gate: each model ≤ 25 MB (estimate). Fallback: precomputed forecasts.

## Assumptions and limits

- Inverse velocity assumes $\alpha \approx 2$; concave or convex inverse-velocity curves, regressive movement and
  noise amplification at low velocities are documented limitations [4].
- One real event cannot validate a forecaster; the synthetic events validate the *method* under the Voight model only.
- Line-of-sight displacement from a single radar sees one component of motion (see the radar model in
  [M23](m23-rtx-sensor-simulation.md)).
- **Educational, not a monitoring or alarm system.** No trigger-action response plan is implied.

## In PitStudio

- **Cases:** [C1](../cases/c1-slope-time-of-failure.md) (forecast error, lead time).
- **Code (planned):** `minephys.geotech` (inverse velocity, Bayesian TTF); synthetic series in `pipeline/`
  `s05_synthesize`; training and evaluation `s30_train`, `s50_evaluate`; export `s60_export`; live engines in `web/`.
  Cards: [slope forecasters](../models/slope-forecasters.md); data card:
  [de Wit slope failure](../data-contract/dataset-cards/dewit-slope-failure.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Carlà, T. et al. (2017). Guidelines on the use of the inverse-velocity method for alarm thresholds and forecasting
   (smoothing, automatic alarm levels). Landslides 14(2):517–534. https://doi.org/10.1007/s10346-016-0731-5
2. Rose, N. D. & Hungr, O. (2007). Forecasting potential rock slope failure in open pit mines using the inverse-velocity
   method (Fukuzono 1985 cited). IJRMMS 44(2):308–320. https://doi.org/10.1016/j.ijrmms.2006.07.014
3. Le Roux et al. (2025). Slope stability monitoring methods and technologies for open-pit mining: a systematic review.
   Mining 5(2):32 (CC BY 4.0). https://api.crossref.org/works/10.3390/mining5020032
4. Dick, Eberhardt, Cabrejo-Liévano, Stead & Rose (2015). Early-warning time-of-failure methodology for open-pit slopes
   using ground-based slope-stability radar. Canadian Geotechnical Journal 52(4):515–529.
   https://doi.org/10.1139/cgj-2014-0028
5. Wang et al. (2026). Open-pit slope displacement and time-to-failure prediction with a hybrid deep-learning model.
   Bulletin of Engineering Geology and the Environment 85(7) (method details UNVERIFIED — source unreachable).
   https://api.crossref.org/works/10.1007/s10064-026-05048-1
6. Voight, B. (1988). Nature 332:125–130 — the material-failure forecast law.
   https://api.crossref.org/works/10.1038/332125a0
7. Voight, B. (1989). A relation to describe rate-dependent material failure. Science 243:200–203.
   https://doi.org/10.1126/science.243.4888.200
8. Bai, S., Kolter, J. Z. & Koltun, V. (2018). *An Empirical Evaluation of Generic Convolutional and Recurrent Networks
   for Sequence Modeling*. https://arxiv.org/abs/1803.01271
9. PatchTST (ICLR 2023) — patching and channel-independent Transformer for long-term forecasting.
   https://arxiv.org/abs/2211.14730
10. High Country News — how technology detected a huge mine landslide before it happened (2013 slide: radar every
    6–8 min, about 2 in/day, evacuation, no injuries).
    https://www.hcn.org/issues/45-8/how-technology-detected-a-huge-mine-landslide-before-it-happened/
11. Chronos-Bolt model card (tiny 9 M; Apache-2.0; speed and memory claims). https://huggingface.co/amazon/chronos-bolt-tiny
12. Community Chronos-Bolt-tiny ONNX (13.9 MB, embedding outputs). https://huggingface.co/light-curve/chronos-bolt-tiny
13. de Wit (2025). Open-pit slope failure data (Zenodo, CC BY 4.0). https://zenodo.org/records/15003054
