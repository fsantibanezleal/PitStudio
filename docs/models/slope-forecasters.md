# Slope forecasters — TCN, PatchTST and Chronos-Bolt-tiny

> Small sequence models that forecast slope displacement from radar-style series and estimate time to failure,
> compared with the classical inverse-velocity method on many synthetic events and described on one real failure. ·
> Part of: [Models](README.md) · Related: [M14 Slope forecasting](../methods/m14-slope-forecasting.md) ·
> [Case C1](../cases/c1-slope-time-of-failure.md) · [Slopes and monitoring](../theory/slopes-and-monitoring.md) ·
> [de Wit slope failure](../data-contract/dataset-cards/dewit-slope-failure.md)

## What and why

Before a pit wall fails it usually accelerates. Voight's material-failure relation describes that terminal stage,
$\ddot\Omega = A\,\dot\Omega^{\alpha}$ [1][2]; for $\alpha>1$ it integrates to the inverse velocity

$$
\frac{1}{v}=\big[A(\alpha-1)(t_f-t)\big]^{1/(\alpha-1)}\ \xrightarrow{\ \alpha=2\ }\ \frac1v=A\,(t_f-t)
$$

so with $\alpha \approx 2$ the failure time $t_f$ is where a straight line through $1/v$ meets the time axis. This is
the inverse-velocity method used on open-pit slope radar [3][4]. $\Omega$ is displacement (mm), $v=\dot\Omega$ velocity
(mm/d), $t$ time (d), and $A$, $\alpha$ empirical constants. Its weaknesses are noise amplification in $1/v$ and
non-linear phases [4]. Case C1 asks whether learned forecasters — **TCN**, **PatchTST** and the foundation model
**Chronos-Bolt-tiny** — estimate $t_f$ better, and states plainly how little a single real event can show.

**Worked example (illustrative).** If $1/v$ falls linearly from 10 d/mm at $t = 0$ to 4 d/mm at $t = 6$ d, the fit is
$1/v = 10 - t$ and $t_f = 10$ d. Forecasting at $t_c = 6$ d gives a lead time of 4 d, so the 10 %-of-lead-time
criterion below allows an error of ±0.4 d (about 9.6 h).

## Model card

### Intended use

- Forecast the displacement/velocity path of a monitored slope pixel and derive a time-to-failure (TTF) estimate, next
  to inverse velocity and a Bayesian TTF update from `minephys.geotech`.
- Teaching how forecast error, lead time and noise interact.

### Out of scope

- Operational early warning or trigger-action response plans: outputs are educational, with stated validity ranges.
- Regressive (decelerating) movements as failure predictions; multi-pixel spatial models.

### Architecture

- **TCN** — stacks of dilated causal 1-D convolutions with residual blocks; output at step $s$ is
  $F(s)=\sum_{i=0}^{k-1} f(i)\,x_{s-d\,i}$ for kernel $f$ of size $k$ and dilation $d$, so the receptive field grows
  exponentially with depth; TCNs outperform canonical recurrent networks with longer effective memory [5].
- **PatchTST** — splits each univariate series (channel independence) into patches of length $P$ with stride $S$, giving
  $N=\lfloor (L-P)/S\rfloor+2$ tokens for a look-back of $L$ steps, fed to a Transformer encoder [6]. With the paper's
  $P = 16$, $S = 8$ and $L = 336$: $N = 42$ tokens.
- **Chronos-Bolt-tiny** — a pretrained time-series foundation model (9 M parameters, Apache-2.0) that chunks the context
  into patches and directly outputs quantile forecasts for several future steps, "up to 250 times faster" than the
  original Chronos [7][8]. Quantile heads are trained with the pinball loss
  $\rho_\tau(u)=u\,(\tau-\mathbb 1[u<0])$ for residual $u = y-\hat y_\tau$ and level $\tau\in(0,1)$ [9].

TCN and PatchTST have about 0.1–1 M parameters (estimate). How TTF is obtained — read off the forecast velocity path or
regressed by a head — is fixed in the slope spec; the same rule applies to all three models.

### Training data

| Source | Use | Licence |
|---|---|---|
| Voight creep series (synthetic) | many seeded events with known $t_f$: regressive and progressive creep, radar noise and atmospheric artefacts, noise level matched to the observed SNR | ours, CC-BY-4.0 |
| de Wit open-pit slope failure (Zenodo 15003054) [10] | **one real event** (radar-derived deformation of a failing slope, mine anonymised); evaluation only, descriptive | CC BY 4.0 |

Synthetic splits are grouped by event seed. The de Wit series is never used for training, a classifier two-sample test
or TSTR/TRTR: with n = 1 it supports description only.

### Budget (estimate)

**< 2 GPU-h** in total (TCN and PatchTST train in minutes; Chronos-Bolt-tiny fine-tuning dominates). Measured by the
runner probe `studio bench`; the GPU probes are written but not yet run on the reference machine.

### Export and web lane

- **Opset 17** for all three (convolutions, MatMul, Softmax, LayerNorm; nothing needs 18–19); IR version **pinned to
  10**; dynamo export with `verify=True`; parity rtol 1e-3 / atol 1e-5 / max abs 1e-4 on ≥ 200 golden windows.
- TCN / PatchTST: **< 4 MB, LIVE**. Chronos-Bolt-tiny: 9 M parameters ≈ 36 / 18 / 9 MB at 4/2/1 bytes → **~18 MB fp16,
  LIVE** (ORT-web WebGPU, WASM fallback), under the 25 MB cap.
- A community ONNX of Chronos-Bolt-tiny (13.9 MB) outputs **embeddings only**, not forecasts [11], so PitStudio exports
  its own forecasting graph; that this export works with parity is **UNVERIFIED** until the build phase. If it fails,
  Chronos-Bolt is precomputed and the live lane keeps TCN/PatchTST.
- **TensorRT relevance — none.** The models are tiny and sub-millisecond on CPU (estimate); they appear in the bench as
  a negative control.

### Pre-registered acceptance criteria

- **Synthetic (many seeded Voight events):** TTF error ≤ 10 % of lead time at the observed SNR,
  $|\hat t_f-t_f|\le 0.10\,(t_f-t_c)$ for forecast time $t_c$; and "better than inverse velocity" only by the decision
  rule, with **pairs = seeded events** (paired 95 % CI of the per-event absolute-error difference excludes 0;
  [DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).
- **Real de Wit series = one event (n = 1):** TTF error at the 50 % and 80 % record cut-offs reported descriptively, no
  "better than" claim; the UI says **"single real event — no significance test"**.

### Evaluation protocol

- Synthetic: for each held-out event, forecasts issued at several cut-offs; TTF error, lead time and the inverse-velocity
  error on the same event (paired). Results stratified by SNR.
- Real: the series is cut at 50 % and 80 % of its record; each model and inverse velocity give a TTF; errors are listed
  side by side, without intervals or rankings.

### Licence of weights

Chronos-Bolt weights and the `chronos-forecasting` package are Apache-2.0 [7][12]; the fine-tuned weights keep
Apache-2.0 with its notice. TCN/PatchTST are our own code. Training data are our CC-BY-4.0 synthetic series → weights
**Apache-2.0 + attribution**. The de Wit data (CC BY 4.0) are cited wherever their results appear.

## Assumptions and limits

- Synthetic events follow Voight's law by construction, which favours methods built on it; the real event is the
  only check against nature, and it is one event.
- The observed SNR is estimated from the de Wit series; a different site's radar noise would change the error.
- Educational, not a slope-monitoring system; simulation-grade twin, not a live digital twin.

## In PitStudio

- **Case:** [C1](../cases/c1-slope-time-of-failure.md) (part of the first end-to-end slice).
- **Method:** [M14](../methods/m14-slope-forecasting.md); classical side in `minephys.geotech`
  ([minephys](../frameworks/minephys.md)).
- **Env and stages:** `pipeline/` `s00_download` (de Wit, pooch + checksum) → `s05_synthesize` (Voight series) →
  `s30_train` → `s40_infer` → `s50_evaluate` → `s60_export` → `pipeline/accel/` `s64_bench` (negative control).
- **Artefacts:** `models/onnx/` (TCN, PatchTST, Chronos-Bolt-tiny if parity holds), `models/cards/`; web lane LIVE.

```bash run deferred=P6
uv run studio run studio/recipes/cases/c1.yaml --profile laptop-rtx5000ada
```

## Results

**Not yet trained** — produced in the data-and-models phase. Will be reported: synthetic TTF error as a fraction of lead
time per model and SNR (acceptance ≤ 10 % at the observed SNR); paired comparison with inverse velocity over seeded
events (decision rule); de Wit TTF errors at the 50 % and 80 % cut-offs, descriptive only; ONNX parity and in-browser
parity.

## References

1. Voight, B. (1988). A method for prediction of volcanic eruptions. Nature 332:125–130.
   https://doi.org/10.1038/332125a0
2. Voight, B. (1989). A relation to describe rate-dependent material failure. Science 243:200–203.
   https://doi.org/10.1126/science.243.4888.200
3. Rose, N. D., Hungr, O. (2007). Forecasting potential rock slope failure in open pit mines using the inverse-velocity
   method. IJRMMS 44(2):308–320. https://doi.org/10.1016/j.ijrmms.2006.07.014
4. Carlà, T. et al. (2017). Guidelines on the use of inverse velocity method. Landslides 14(2):517–534.
   https://doi.org/10.1007/s10346-016-0731-5 ; Dick, G. J. et al. (2015). Can. Geotech. J. 52(4):515–529.
   https://doi.org/10.1139/cgj-2014-0028
5. Bai, S., Kolter, J. Z., Koltun, V. (2018). *An Empirical Evaluation of Generic Convolutional and Recurrent Networks
   for Sequence Modeling* (TCN). https://arxiv.org/abs/1803.01271
6. Nie, Y. et al. (2023). *A Time Series is Worth 64 Words* (PatchTST). ICLR 2023. https://arxiv.org/abs/2211.14730
7. Amazon. *chronos-bolt-tiny* model card (9 M, Apache-2.0, direct quantile forecasts).
   https://huggingface.co/amazon/chronos-bolt-tiny
8. Ansari, A. F. et al. (2024). *Chronos: Learning the Language of Time Series*. https://arxiv.org/abs/2403.07815
9. Koenker, R., Bassett, G. (1978). Regression quantiles. Econometrica 46(1):33–50. https://doi.org/10.2307/1913643
10. de Wit (2025). Open-pit slope failure data (Zenodo, CC BY 4.0). https://doi.org/10.5281/zenodo.15003054
11. Community ONNX `light-curve/chronos-bolt-tiny` (embeddings outputs). https://huggingface.co/light-curve/chronos-bolt-tiny
12. `chronos-forecasting` on PyPI (Apache-2.0). https://pypi.org/pypi/chronos-forecasting/json
