# M22 — Cosmos Reason 2 vision-language tasks scored against exact scene truth

> A 2-billion-parameter vision-language model answers pit-safety questions, judges the physical plausibility of
> PitStudio's own simulations and captions synthetic images — and every answer is scored against ground truth computed
> from the USD scene, next to its base model and a detector-plus-geometry baseline. · Part of: [Methods](README.md) ·
> Related: [Vision-language reasoning theory](../theory/vision-language-reasoning.md) ·
> [Cosmos Reason 2 framework](../frameworks/cosmos-reason-2.md) · [Cosmos Reason 2 card](../models/cosmos-reason-2.md) ·
> [DEC-0009](../architecture/decisions/DEC-0009-vlm-llamacpp-gguf.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Frontier | **yes** (zero-shot, inference only) | precompute (display-only) | [B1](../cases/b1-traffic-proximity.md), [B2](../cases/b2-synthetic-perception.md) | llama.cpp b11381 (MIT) + own GGUF Q8_0 of the official revision; transformers BF16 reference; Qwen3-VL-2B-Instruct (Apache-2.0) control | not yet implemented |

**Built on NVIDIA Cosmos.** Cosmos Reason 2 is licensed by NVIDIA Corporation under the NVIDIA Open Model License.
NVIDIA and Cosmos are named nominatively; PitStudio is not affiliated with or endorsed by NVIDIA, never redistributes
the weights (or any GGUF conversion of them), and shows Cosmos outputs as display-only text.

## What and why

Vision-language models (VLMs) promise "ask the camera what is wrong". The evidence for safety use is thin: a mining
safety VQA system improved substantially over an un-fine-tuned 72B VLM only after fine-tuning [8]; a construction study
found its best detector-plus-small-VLM pipeline at an F1 of 50.6 % for hazard identification [9]; NVIDIA's own
worker-safety recipe for Cosmos Reason 2 gives qualitative views but no precision or recall [10]. The model card itself
names complex scene composition, fast motion, overlapping interactions and low light as cases where the model may not
follow its input accurately [1] — dust, night and occlusion are exactly those cases.

M22 does not ask anyone to trust the model. It **measures** it where PitStudio has something rare: exact ground truth.
Every question about a rendered pit scene has an answer computable from the USD prims (positions, semantics, dust
optical depth, road grade), every plausibility pair has a known corruption, and every synthetic image has a scene graph.
M22 is a frontier showcase and **never a headline KPI**.

## The algorithm

### Model and runtime

- **Model:** Cosmos-Reason2-2B, a post-trained Qwen3-VL-2B-Instruct with 2,438,696,960 BF16 parameters, gated on
  Hugging Face; official revision `9ce19a1` [1][2]. Its reasoning format is `<think>…</think>` followed by
  `<answer>…</answer>` [1].
- **Runtime (primary):** llama.cpp build b11381 (MIT), a portable Windows CUDA build, which supports Qwen3-VL [3][4].
  PitStudio converts its **own GGUF** (F16 → Q8_0, plus an F16 vision projector) from the official revision and records
  every file's SHA-256, because the community GGUF that NVIDIA's Jetson page points to predates the improved checkpoint
  and another is licence-mislabelled [5]. For scale, that community Q8_0 file is about 2.17 GB plus a 0.82 GB projector
[5].
- **Reference:** transformers in BF16 (about 4.9 GB of weights, arithmetic) for parity and for native video input.
- **Footprint:** the model card states a 24 GB minimum on Linux/Hopper/Blackwell, while NVIDIA's Jetson AI Lab runs
  the 2B quantised (GGUF Q8_0) on an 8 GB device [1][6]; whether it fits and how fast it runs on PitStudio's 16 GB
  laptop GPU is measured by the bench (budget estimate about 3–5 GB). Video for Qwen3-VL in llama.cpp is UNVERIFIED, so
  video questions use frame lists in llama.cpp only when labelled as such, or the BF16 reference.

### Task A — PitVQA: hazard questions with exact answers

About 1,000 Replicator frames from the B2 scenes (day, night, dust, rain × road, bench, loading area) and six templated
question types whose answers are computed from the USD stage:

| Type | Question | Ground truth from |
|---|---|---|
| 1 | Is a person within 30 m of a haul truck? | prim positions |
| 2 | Is a windrow/berm present along the bench edge in view? | design variant |
| 3 | How many haul trucks are visible? | instance visibility (pixel count) |
| 4 | Is visibility reduced by dust? | optical-depth threshold from the plume field ([M16](m16-dust-dispersion.md)) |
| 5 | Is a light vehicle in the truck's blind zone? | geometric zone |
| 6 | Is the truck on a ramp steeper than 10 %? | road grade |

Positives and negatives are balanced per type, about 6,500 queries in total. With about 1,080 queries per type (six types), a
Wilson 95 % interval at an accuracy of 0.5 has a half-width of about ±3.1 points (arithmetic, [11]).

**Arms:** Cosmos-Reason2-2B Q8_0 (reasoning on and off); BF16 on a subset; **Qwen3-VL-2B-Instruct** (the base model,
Apache-2.0 [14]) as the "does the Cosmos post-training help?" control; **D-FINE detector + geometric rule**
([M10](m10-synthetic-data-detector.md)) as the classical/SOTA baseline; majority class. An optional real probe (≤ 200
licence-clean images labelled by two people) is reported only in aggregate and only if labelled.

### Task B — plausibility critic of our simulations

100 pairs of 5–8 s renders of Warp DEM / Newton MPM runs ([M07](m07-gpu-granular-physics.md)): a calibrated run and the
same scene with exactly one corruption (gravity × 0.3, friction removed, mass injected, time reversed,
interpenetration, frozen particles). Labels are known by construction. Protocol: two-alternative forced choice ("which
clip is physically plausible?") in both orders, plus a single-clip yes/no question. The pre-registered null is chance
(50 %). For scale, NVIDIA's fine-tuned plausibility recipe reaches an accuracy of 0.401 on an absolute 1–5 rating task
[7], which is why PitStudio uses paired, known-corruption comparisons instead of absolute scores. A physics check
(repose angle and mass balance from the simulation state) is the baseline; it is expected to win, and the point is to
measure how much a VLM sees from pixels alone.

### Task C — captions scored for hallucination

About 2,000 synthetic frames are captioned and scored against the scene graph: object hallucination rate (objects
mentioned but absent), object recall, and condition accuracy (dust, night, rain). Deterministic template captions from
the scene graph are the baseline and the fallback. Captions are display-only (gallery text, dataset-card summaries);
they are **not** used to filter training data unless the "Built on NVIDIA Cosmos" notice is added to that model's card
[12].

### Statistics

- **Balanced accuracy and F1 per question type**, with Wilson 95 % intervals [11].
- **AUROC** from the yes/no first-token log-probabilities.
- **Cosmos vs Qwen base:** McNemar's test on paired answers to the same queries, with discordant counts $b$ (Cosmos
  right, Qwen wrong) and $c$ (the reverse): $\chi^2 = (b - c)^2/(b + c)$, or the exact binomial version when
  $b + c < 25$ [13].
- **Quantisation agreement:** exact-match agreement of the `<answer>` between Q8_0 and BF16 on binary questions.

```text
run_task_A(frames, questions):
    for (frame, q) in balanced_queries:
        truth = q.answer_from_usd(frame.stage)               # exact
        for arm in [cosmos_q8, cosmos_bf16_subset, qwen_base, detector_rule, majority]:
            pred, logprob_yes = arm.ask(frame.image, q.text, seed)
            log(frame, q, arm, pred, truth, logprob_yes)
    report balanced_accuracy, F1, Wilson CI, AUROC per type; McNemar(cosmos_q8, qwen_base)
```

## Baseline and comparison

- Task A: detector + geometric rule, Qwen3-VL-2B base, majority class.
- Task B: physics check from simulation state; chance.
- Task C: template captions from the scene graph.
- "Cosmos beats Qwen base" **only if McNemar $p < 0.05$**; every other "better" claim follows the
  [decision rule](README.md#how-methods-are-compared).

## Acceptance criterion (pre-registered)

- **Q8_0 vs BF16 agreement ≥ 95 % on binary questions** (otherwise the Q8_0 path is replaced by BF16).
- **Per-type balanced accuracy reported with CI.**
- **"Cosmos beats Qwen base" only if McNemar $p < 0.05$.**
- **Never a headline KPI.**

**Results: Not yet run** — produced in the data-and-models phase. Reported: per-type accuracy and F1 with intervals for
every arm, AUROC, the McNemar result, plausibility accuracy per corruption, caption hallucination and recall, and the
Q8_0–BF16 agreement. Wrong answers are shown as well as right ones.

## Lane and web delivery

**Precompute, display-only.** About 6.5k hazard queries, 100 plausibility pairs and 2k captions are run in 1–2
overnight slots (8–16 GPU-hours, estimate) and baked into JSON records (< 1 MB of text per case). Each record holds the
frames, question, full model output, ground-truth answer and a correct/incorrect badge, with provenance: model id and
revision, GGUF SHA-256, llama.cpp build and zip SHA-256, sampling parameters and seed, date, GPU and driver. The panel
carries "Built on NVIDIA Cosmos" and the honesty statement **"Zero-shot 2B VLM; not a safety system."** The model never
runs in the browser.

## Assumptions and limits

- Zero-shot, no fine-tuning: no licence-clean mining training set exists, and NVIDIA's own fine-tuning recipes use
  multi-GPU servers [7].
- Synthetic frames: results transfer to real cameras only as far as the optional real probe shows.
- Quantisation may change answers; the agreement gate measures it. Whether quantisation affects in-weight safety
  behaviour under the licence's guardrail clause is a legal reading PitStudio cannot settle; no jailbreak prompts,
  refusal removal or modified "abliterated" variants are ever used [12].
- The model needs the maintainer's acceptance of the gated terms and a read token; without them the tasks run on the
  Qwen3-VL base only and the Cosmos arm shows "not run".

## In PitStudio

- **Cases:** [B1](../cases/b1-traffic-proximity.md) (hazard questions), [B2](../cases/b2-synthetic-perception.md)
  (captions, detector comparison).
- **Code (planned):** `studio/reason/` (llama.cpp as an external tool), stages `st59_reason_bench`, `st59a_vqa`,
  `st59b_plausibility`, `st59c_captions`; question templates and USD ground truth from the scene pipeline; baked JSON
  published with `studio publish`. Card: [Cosmos Reason 2](../models/cosmos-reason-2.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Cosmos-Reason2-2B model card (base model, inputs, reasoning format, 24 GB minimum, benchmarks, limitations,
   licence). https://huggingface.co/nvidia/Cosmos-Reason2-2B
2. Hugging Face API — Cosmos-Reason2-2B revision `main` = `9ce19a1…`, parameter count, gating.
   https://huggingface.co/api/models/nvidia/Cosmos-Reason2-2B/revision/main
3. llama.cpp releases — build b11381, Windows CUDA zips. https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8
4. llama.cpp PR #16780 — Qwen3-VL support (merged 2025-10-30). https://api.github.com/repos/ggml-org/llama.cpp/pulls/16780
5. Community GGUF of Cosmos-Reason2-2B — file sizes and dates (predates the improved checkpoint).
   https://huggingface.co/api/models/apolo13x/Cosmos-Reason2-2B-GGUF?blobs=true
6. NVIDIA Jetson AI Lab — Cosmos Reason 2 2B on an 8 GB Orin Nano (FP8 / GGUF Q8_0).
   https://www.jetson-ai-lab.com/models/cosmos-reason2-2b/
7. Cosmos Cookbook — physical-plausibility post-training recipe (VideoPhy-2; accuracy 0.401, correlation 0.419).
   https://nvidia-cosmos.github.io/cosmos-cookbook/recipes/post_training/reason2/physical-plausibility-check/post_training.html
8. Wu et al. — MonitorVLM, mining safety VQA. https://arxiv.org/abs/2510.03666
9. Adil et al. — detector + small VLMs for construction hazards (F1 50.6 % vs 34.5 %). https://arxiv.org/abs/2604.05210
10. Cosmos Cookbook — worker-safety inference recipe (no quantitative metrics).
    https://nvidia-cosmos.github.io/cosmos-cookbook/recipes/inference/reason2/worker_safety/inference.html
11. *Binomial proportion confidence interval* — Wilson score interval.
    https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval
12. NVIDIA Open Model License (2025-10-24) — §2.1 guardrails, §3.1 notice, §3.2 "Built on NVIDIA Cosmos", outputs.
    https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
13. *McNemar's test*. https://en.wikipedia.org/wiki/McNemar%27s_test
14. Qwen3-VL-2B-Instruct (Apache-2.0). https://huggingface.co/api/models/Qwen/Qwen3-VL-2B-Instruct
