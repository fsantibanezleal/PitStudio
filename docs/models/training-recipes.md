# Training recipes

> The shared rules for training and evaluating every PitStudio model on one 16 GB laptop GPU: budgets, the overnight
> queue, precision, splits, and the pre-registered decision rule. · Part of: [Models](README.md) · Related:
> [Export, parity and acceleration](export-parity-acceleration.md) · [Pipeline stages](../pipelines/pipeline-stages.md) ·
> [Compute lanes](../pipelines/compute-lanes.md) · [Runner](../studio/runner.md)

## What and why

All learned models run on one machine: an NVIDIA RTX 5000 Ada Generation Laptop GPU with 16 GB of memory, power-limited
like every laptop part. That machine also renders, simulates and encodes, so training cannot be an afterthought. The
recipes below make three things explicit before any run: how much GPU time each model is allowed (an estimate, replaced
by a measurement), how runs share the GPU (one at a time, overnight, resumable), and how a result earns the word
"better" (a paired confidence interval, decided before the numbers exist).

## Budgets

The plan's budgets are **estimates**. Upstream projects publish no single-16 GB-laptop training times; the D-FINE and
DEIM recipes, for instance, document 4-GPU training [1]. The estimates were derived from published FLOPs and parameter
counts and are replaced by the runner's `studio bench` probe, which measures each model in a short run before any long
run.

| Model | Data | Environment | GPU-h (estimate) | VRAM (estimate) |
|---|---|---|---|---|
| [D-FINE-N + D-FINE-S](d-fine.md) | ~10k synthetic images per family × 2 families + 1 unstructured-DR ablation arm | `pipeline/` | 12–25 | 8–11 GB |
| [RF-DETR-Seg-N](rf-detr-seg.md) | same images, instance masks | `pipeline/` | 8–16 | 10–13 GB |
| [U-Net (smp)](unet-fragmentation.md) | synthetic exact-PSD muck piles + real Mendeley images (group split) | `pipeline/` | 2–4 | 5–7 GB |
| [GNS 2-D](gns-granular.md) | Warp DEM / Newton MPM rollouts | `pipeline/` | 4–15 | 2–6 GB |
| [FNO-2D](fno-fields.md) | Warp shallow-water and dust runs | `pipeline/` | 0.5–2 | — |
| [PPO + attention dispatch](dispatch-policies.md) | vectorised env, DES cross-check | `pipeline/` | 1–5 | 2–4 GB |
| [IL-1 haul truck](isaac-lab-policies.md) | Isaac Lab env on Newton | `studio/isaaclab/` | 1–4 | ≤ 5 GB |
| [IL-2 excavator (+ IL-3 loader, optional)](isaac-lab-policies.md) | Isaac Lab env, FEE soil + MPM check | `studio/isaaclab/` | 2–8 (+ 2–3) | ≤ 6 GB |
| [TCN / PatchTST; Chronos-Bolt-tiny](slope-forecasters.md) | Voight creep (synthetic) + de Wit real series | `pipeline/` | < 2 | — |
| [Mine-to-mill meta-model](mine-to-mill-meta-model.md) | `minephys` sweeps | `pipeline/` | minutes | — |
| [DEM calibration](dem-calibration.md) | literature repose targets + synthetic truth | `studio/` | 0.2–2 each | — |
| [Cosmos Reason 2 (inference only)](cosmos-reason-2.md) | ~6.5k hazard queries, 100 plausibility pairs, 2k captions | `studio/reason/` | 8–16 | ~3–5 GB (to measure) |
| TensorRT engines (derived) | exported ONNX files | `pipeline/accel/` | 4–7 | — |

### Total GPU time

| Item | GPU-h (estimate) |
|---|---|
| Training and evaluation | ≈ 45–110 |
| Synthetic image generation (~30k images: 2 families × ~10k + a ~10k DR arm, at 0.5–2 images/s) | ≈ 4–17 |
| Physics, sensor renders and videos | ≈ 5–20 |
| **Total** | **≈ 55–150** |

Worked check of the synthetic-image line: 30,000 images at 2 images/s take 15,000 s ≈ 4.2 h; at 0.5 images/s they take
60,000 s ≈ 16.7 h. The rate itself is measured once on the reference machine and, because Replicator falls under the
NVIDIA Software License Agreement §8.9, it stays a local-only figure [2].

### Overnight slots

The total corresponds to **≈ 8–19 overnight slots**, run sequentially by the runner's queue (≈ 55 h / 8 slots and
≈ 150 h / 19 slots are both just under 8 h per slot). Every long job is time-boxed to its slot, checkpoints at least
once per epoch and resumes from its last checkpoint after an interruption.

## Sharing one GPU

- **One heavy GPU job at a time.** Every GPU stage takes the machine-wide lock `gpu0.compute`; encoding takes
  `gpu0.nvenc` ([Runner](../studio/runner.md)). Rendering and training never run concurrently.
- **Pre-flight guards.** Free VRAM (estimate + margin), free disk, GPU temperature and the capability report are checked
  before start; a machine-wide `gpu0.hold` file stops all GPU work.
- **Memory cap.** PyTorch stages cap their share of device memory with `torch.cuda.set_per_process_memory_fraction`,
  which makes the allocator raise an out-of-memory error beyond the cap [3]; the runner then retries with the stage's
  declared `oom_fallback` (smaller batch or shard).
- **Telemetry.** NVML is sampled at 1–4 Hz during every stage; the manifest stores busy time, power against the
  enforced limit, energy and clocks-event reasons, so that a slow epoch can be traced to throttling
  ([Manifest](../data-contract/manifest.md)).

## Precision and compilation

| Model family | Training precision | Why |
|---|---|---|
| Transformers (D-FINE, RF-DETR, PatchTST, Chronos-Bolt) | bf16 autocast | supported on Ada; avoids fp16 overflow in attention |
| CNNs (U-Net) and small MLPs | fp16 autocast with gradient scaling, or bf16 | CUDA autocast defaults to float16, and gradient scaling exists because fp16 gradients underflow [4] |
| Surrogates (GNS, FNO) | fp32 first; mixed precision only if parity holds | spectral and scatter operations are precision-sensitive |

- **No FP8 training.** Transformer Engine, the FP8 training path, is installed on Linux x86_64 only [5], and models of
  ≤ 120 M parameters gain little from it. FP8 appears only as an inference precision in
  [TensorRT engines](export-parity-acceleration.md).
- **`torch.compile` is opt-in.** On Windows it needs the `triton-windows` package, which is in Beta [6].

## Splits, seeds and evaluation

- **Group splits are fixed at ingestion** ([Ingestion](../data-contract/ingestion.md)). Real fragment images are split
  by source group (231 groups; test on originals only; grouped *k*-fold). Synthetic data is grouped by scenario seed,
  pit layout or shift; duplicates across splits are checked before any metric.
- **Seeds.** One master seed per recipe; per-stage seeds are derived from it; every seed is in the manifest.
- **Held-out data is touched by `s50_evaluate` only.** Model and threshold choices use validation data.
- **Baselines run on the same splits.** Every learned model has a classical baseline: watershed + Swebrec (U-Net),
  inverse velocity (forecasters), SPTF and LP dispatch (policies), pure pursuit + PID and a scripted dig (Isaac Lab),
  the analytical chain (meta-model), CMA-ES (differentiable calibration), the Qwen3-VL base model and a detector +
  geometric rule (Cosmos).
- **Evaluation runs are as deterministic as the engine allows:** `torch.use_deterministic_algorithms(True)` and
  `cudnn.benchmark = False` [7].

## The decision rule

The rule is pre-registered: it is fixed now, before any result exists, and the web app's unit tests enforce it.

For two methods A and B evaluated on the same *n* paired units *i* (seeds, folds, seeded events, test tiles or
episodes, as each card states) with a metric *m*:

$$
d_i = m_i(A) - m_i(B), \qquad \bar d = \frac{1}{n}\sum_{i=1}^{n} d_i, \qquad
s_d = \sqrt{\frac{1}{n-1}\sum_{i=1}^{n}\left(d_i - \bar d\right)^2}
$$

$$
\mathrm{CI}_{95\%} = \bar d \;\pm\; t_{0.975,\,n-1}\,\frac{s_d}{\sqrt{n}}
$$

where $d_i$ has the unit of the metric (e.g. t/h, %, m), $n$ is dimensionless and $t_{0.975,\,n-1}$ is the 97.5 %
quantile of Student's t distribution with $n-1$ degrees of freedom. A percentile bootstrap over the pairs is the
alternative when the differences are clearly non-normal; the estimator used for each claim is fixed in its feature
specification.

- If the interval excludes 0, the result is reported as better (or worse) with the interval.
- If it includes 0, the docs and the UI say **"no significant difference"**, even when $\bar d$ looks large.
- **Worked example (illustrative numbers, not a result):** 30 paired seeds of a dispatch policy against SPTF give
  $\bar d = 12$ t/h and $s_d = 40$ t/h. Then $s_d/\sqrt{30} = 7.3$ t/h, $t_{0.975,29} \approx 2.05$, and the interval
  is $12 \pm 15.0$ t/h $= [-3.0, 27.0]$ t/h. It contains 0, so the UI says "no significant difference".
- **Binary agreement tasks** (Cosmos vs its base model on the same questions) use McNemar's test on the paired
  disagreements instead; "better" requires p < 0.05 ([Cosmos Reason 2](cosmos-reason-2.md)).
- **No significance test for n = 1.** The real de Wit slope failure is one event; its time-of-failure errors at the 50 %
  and 80 % record cut-offs are reported descriptively, and the UI says "single real event — no significance test".

## Assumptions and limits

- Budgets assume the reference laptop at its enforced power limit; a different machine changes every GPU-hour figure,
  which is why the measured value is recorded per run.
- Thermal and power throttling make wall-clock times noisy; comparisons of speed are only made between runs with the
  same enforced limit and power source.
- A paired CI controls the error of one comparison. Cards that make several comparisons say so, and none of them
  turns a family of tests into a single headline number.
- Results are reported on several axes together (accuracy, robustness, speed, size), never as one score.

## In PitStudio

- **Stages:** `s30_train`, `s40_infer`, `s50_evaluate` in `pipeline/`; `st60_il_train`, `st61_il_mpm_eval` in
  `studio/isaaclab/`; `st59*` in `studio/reason/` ([Pipeline stages](../pipelines/pipeline-stages.md),
  [Studio stages](../pipelines/studio-stages.md)).
- **Thresholds:** `specs/000-foundation/thresholds.yaml` (they only ratchet upwards; lowering one needs a spec change
  and the maintainer's explicit decision).
- **Status:** not yet run. The capability probes that precede any training are written but not yet run on the reference
  machine. Once the build phase adds the runner:

```bash run deferred=P6
uv run --extra runner studio bench <suite>
uv run --extra runner studio run studio/recipes/<case>.yaml --stage s30_train
```

## References

1. D-FINE repository (training documented on 4 GPUs). https://github.com/Peterande/D-FINE
2. NVIDIA, *Software License Agreement* (§8.9). https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
3. PyTorch 2.14, `torch.cuda.memory.set_per_process_memory_fraction`. https://docs.pytorch.org/docs/2.14/generated/torch.cuda.memory.set_per_process_memory_fraction.html
4. PyTorch 2.14, *Automatic Mixed Precision*. https://docs.pytorch.org/docs/2.14/amp.html
5. NVIDIA, *Transformer Engine installation*. https://docs.nvidia.com/deeplearning/transformer-engine/installation.html
6. `triton-windows` on PyPI. https://pypi.org/pypi/triton-windows/json
7. PyTorch reproducibility notes. https://raw.githubusercontent.com/pytorch/pytorch/main/docs/source/notes/randomness.md
