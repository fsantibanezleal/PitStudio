# Cosmos Reason 2 (2B) — inference-only evaluation card

> A 2-billion-parameter vision-language model run locally, zero-shot, on three mining tasks with exact answers from our
> own scenes, and scored against its base model, our detector and a geometric rule. Never trained, never published as
> weights, never a headline KPI. · Part of: [Models](README.md) · Related:
> [M22 Cosmos VLM tasks](../methods/m22-cosmos-vlm-tasks.md) · [Cosmos Reason 2](../frameworks/cosmos-reason-2.md) ·
> [Vision-language reasoning](../theory/vision-language-reasoning.md) ·
> [DEC-0009](../architecture/decisions/DEC-0009-vlm-llamacpp-gguf.md)

## What and why

Vision-language models (VLMs) are proposed for site-safety monitoring, yet the evidence is thin: a fine-tuned
mining-safety VLM improved F1 by 28 points over an unfine-tuned 72B model [1], a detector + small-VLM pipeline reached
50.6 % F1 on construction hazards [2], and NVIDIA's own worker-safety recipe for this model gives no quantitative
metrics [3]. PitStudio can do something rare: ask the model questions whose **answers are known exactly**, because they
are computed from the USD scene that produced the image. NVIDIA Cosmos Reason 2 (2B) is a post-trained
Qwen3-VL-2B-Instruct [4]. PitStudio is not affiliated with NVIDIA; the model is named nominatively.

## Model card

### Intended use

- **Task A — hazard questions** (≈ 6.5k queries) on synthetic pit renders with exact USD ground truth, six templated
  question types, positives and negatives balanced per type: a person within 30 m of a haul truck; a berm present along
  the bench edge; how many haul trucks are visible; visibility reduced by dust (optical-depth threshold); a light
  vehicle in the truck's blind zone; the truck on a ramp steeper than 10 %.
- **Task B — physics-plausibility critic** (100 pairs): two renders of the same granular scene, one calibrated, one with
  exactly one corruption (gravity × 0.3, zero friction, mass injection, reversed time, interpenetration, frozen
  particles); two-alternative forced choice, both orders, plus a single-clip yes/no question.
- **Task C — captions** (≈ 2k synthetic frames) scored against the scene graph for hallucinated and omitted objects and
  for condition accuracy (dust, night, rain).

### Out of scope

- A safety system of any kind: "zero-shot 2B VLM; not a safety system."
- Training, fine-tuning or distilling from the model; using its captions to curate training data (default: rule-based
  curation, captions display-only).
- Running in the browser or publishing weights (licence and a ≈ 3 GB footprint).

### Architecture

Qwen3-VL-2B-Instruct architecture post-trained by NVIDIA: 2,438,696,960 BF16 parameters; 28 text layers with 8 KV
heads of dimension 128; vision patches of 16 px with 2 × 2 merging, so about one visual token per 32 × 32 px [4][6][7].
Inputs are images or video (fps 4 recommended) and text; outputs follow `<think>…</think><answer>…</answer>` [4][5].
Worked footprint (arithmetic, to be measured): BF16 weights ≈ 4.9 GB; KV cache in F16 ≈ 0.11 MiB per token
($2\cdot28\cdot8\cdot128\cdot2$ B), so an 8K context ≈ 0.9 GB; a 1280 × 720 frame ≈ 900–920 visual tokens.

**Runtimes.** Primary: llama.cpp build **b11381** (MIT, portable CUDA build, no elevation) with **our own GGUF Q8_0
conversion of the official Hugging Face revision `9ce19a1`** plus an F16 vision projector [8]. Third-party GGUFs are not
used: the one NVIDIA's Jetson page points to predates the improved 2026-03-10 checkpoint, and another is mislabelled
Apache-2.0 [9]. Reference: transformers in **BF16**, which also handles native video. llama.cpp video for Qwen3-VL is
UNVERIFIED, so video questions there use an ordered frame list, labelled as an approximation. The model card asks for
24 GB minimum on Hopper/Blackwell under Linux [4], while NVIDIA's Jetson AI Lab runs a Q8_0 GGUF on an 8 GB Orin Nano
[10]; whether it fits our 16 GB laptop GPU is measured, not assumed. A community Q8_0 (2,165,040,800 B) plus projector
(819,395,424 B) totals ≈ 3.0 GB [11].

**Controls and baselines.** Qwen3-VL-2B-Instruct (Apache-2.0) — "does the Cosmos post-training help?" [7]; our
[D-FINE detector](d-fine.md) + a geometric rule; majority class; for task B a physics-check baseline (repose angle and
mass balance from the simulation state); for task C deterministic template captions from the scene graph.

### Training data

None — inference only. Evaluation data are ours (CC-BY-4.0): Replicator renders of the B2 scenes (day, night, dust,
rain; road, bench, loading area) with answers computed from USD prims; Warp DEM / Newton MPM render pairs for task B; the
same scene graphs for task C. An optional real probe (≤ 200 licence-clean images, two labellers, Cohen's κ) is
reported in aggregate only if it exists.

### Budget (estimate)

**8–16 GPU-h (1–2 overnight slots); about 3–5 GB VRAM, to be measured.** Short answers (about 64 tokens) are used for
the metrics, reasoning mode on a small showcase subset. The `st59_reason_bench` stage first measures VRAM, prefill and
decode tokens/s and Q8_0-vs-BF16 agreement; the GPU probes are written but not yet run on the reference machine.

### Export and web lane

- No ONNX and no TensorRT: weights stay **reference-only** (local, never committed or redistributed).
- Web lane: **precomputed text only, display-only**, < 1 MB per case. Each record holds the frames shown, the question,
  the full output, the ground-truth answer and a correct/incorrect badge — wrong answers included — and provenance:
  model id + revision `9ce19a1`, quantisation + GGUF SHA-256, llama.cpp build + zip SHA-256, sampling parameters + seed,
  date, GPU and driver. Every panel shows **"Built on NVIDIA Cosmos"**.

### Pre-registered acceptance criteria

- **Q8_0 vs BF16 agreement ≥ 95 % on binary questions** (exact match of `<answer>`); otherwise BF16 replaces Q8_0.
- **Per-type balanced accuracy with CI**: $\mathrm{BA}=\tfrac12(\mathrm{TPR}+\mathrm{TNR})$ with a 95 % interval.
- **"Cosmos beats Qwen base" only if McNemar p < 0.05.**
- **Never a headline KPI.**

**McNemar's test** on paired binary correctness [12]: with $b$ the queries Cosmos answers correctly and Qwen does not,
and $c$ the reverse,

$$
\chi^2=\frac{(b-c)^2}{b+c}\quad(1\ \text{d.o.f.}),
$$

or the exact binomial version when $b+c$ is small. Worked example (illustrative): $b = 60$, $c = 35$ gives
$\chi^2 = 625/95 = 6.58$, $p = 0.010$ (exact binomial $p = 0.013$) — a significant difference; concordant answers do
not enter the test.

### Evaluation protocol

- Task A: balanced accuracy and F1 per question type with Wilson 95 % intervals [13] — about ±3.1 pp at $n = 1{,}000$
  and $p = 0.5$; AUROC from the yes/no first-token log-probabilities; condition breakdown (dust, night); arms: Cosmos
  Q8_0 (reasoning on and off), BF16 on a 500-query subset, Qwen3-VL-2B, detector + rule, majority class.
- Task B: pairwise 2AFC accuracy with CI against a pre-registered chance level of 50 %; single-clip AUROC;
  per-corruption detection rate; the physics-check baseline is expected to win — the point is how much a VLM sees from
  pixels. Prior: absolute 1–5 plausibility scoring reaches only 0.401 accuracy even after fine-tuning [14].
- Task C: object hallucination rate (CHAIR-style), object recall and condition accuracy against the scene graph.

### Licence of weights

NVIDIA Open Model License (Oct 24, 2025) [15]: **§3.1** — distributing the model requires the agreement and a Notice;
PitStudio never distributes it, and its own GGUF (a Derivative Model, §2.4) stays local. **§3.2** — making available a
product that uses a Cosmos model or its outputs requires "Built on NVIDIA Cosmos", so every page and card showing
answers carries it; the same duty would reach the [D-FINE](d-fine.md) card if captions ever curated its training data.
**§2.1** — bypassing guardrails terminates the licence: no jailbreak prompts, no "abliterated" variants. NVIDIA claims no
rights in the outputs. Answers are class `display-only`. The weights are gated: running the tasks needs **the
maintainer's acceptance of the gated Hugging Face terms** (optional); without it every Cosmos arm shows **"not run"**.
Throughput numbers follow the performance-data rule
([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

## Assumptions and limits

- The model card warns it may not follow inputs accurately with complex composition, fast motion or low light [4] —
  dust and night are exactly our hard conditions; near-chance results there are an expected, reported outcome.
- Q8_0 is quantised and self-converted; the BF16 agreement gate guards it. The upstream repository is in limited
  maintenance (successor family announced), so the revision is pinned [16].
- Synthetic scenes only unless the real probe exists; simulation-grade twin, not a live digital twin.

## In PitStudio

- **Cases:** [B1](../cases/b1-traffic-proximity.md) (hazard questions), [B2](../cases/b2-synthetic-perception.md)
  (captions); task B uses the granular renders of [A3](../cases/a3-loading-payload-variance.md) and
  [D1](../cases/d1-blast-muck-pile.md). **Method:** [M22](../methods/m22-cosmos-vlm-tasks.md).
- **Env and stages:** `studio/reason/` (llama.cpp b11381 external tool + transformers BF16 reference):
  `st59_reason_bench` → `st59a_vqa` → `st59b_plausibility` → `st59c_captions` → `studio publish <run>`. Guide:
  [Cosmos tasks](../guides/cosmos-tasks.md).
- **Artefacts:** precomputed JSON answers and metrics with provenance; `models/cards/` holds this card; no file in
  `models/onnx/`.

## Results

**Not yet run** — inference only, produced in the data-and-models phase (only if the gated terms are accepted). Will be
reported: Q8_0 vs BF16 agreement (acceptance ≥ 95 %); per-type balanced accuracy, F1 and AUROC with CIs for every arm;
McNemar Cosmos vs Qwen per type ("beats" only if p < 0.05); task B 2AFC accuracy, AUROC and per-corruption detection vs
the physics check; task C hallucination, recall and condition accuracy; measured VRAM and tokens/s.

## References

1. Wu et al. (2025). MonitorVLM: mining-safety VQA. https://arxiv.org/abs/2510.03666
2. Adil et al. (2026). Detector + small VLMs for construction hazards. https://arxiv.org/abs/2604.05210
3. NVIDIA Cosmos Cookbook — worker-safety inference recipe.
   https://nvidia-cosmos.github.io/cosmos-cookbook/recipes/inference/reason2/worker_safety/inference.html
4. NVIDIA. *Cosmos-Reason2-2B* model card. https://huggingface.co/nvidia/Cosmos-Reason2-2B
5. NVIDIA NIM for VLMs — Cosmos Reason 2 API (image/video inputs, reasoning format).
   https://docs.nvidia.com/nim/vision-language-models/1.6.0/examples/cosmos-reason2/api.html
6. Hugging Face API — Cosmos-Reason2-2B (parameters, gating, revision).
   https://huggingface.co/api/models/nvidia/Cosmos-Reason2-2B
7. Qwen. *Qwen3-VL-2B-Instruct* (Apache-2.0; config). https://huggingface.co/api/models/Qwen/Qwen3-VL-2B-Instruct and
   https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct/raw/main/config.json
8. ggml-org. *llama.cpp* releases (b11381) and Qwen3-VL support (PR #16780).
   https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8 and
   https://api.github.com/repos/ggml-org/llama.cpp/pulls/16780
9. Community GGUF metadata (dates, licence tags). https://huggingface.co/api/models/apolo13x/Cosmos-Reason2-2B-GGUF?blobs=true
   and https://huggingface.co/api/models/robertzty/Cosmos-Reason2-2B-GGUF?blobs=true
10. NVIDIA Jetson AI Lab — Cosmos Reason 2 2B (Orin Nano 8 GB, GGUF Q8_0). https://www.jetson-ai-lab.com/models/cosmos-reason2-2b/
11. Community GGUF file sizes. https://huggingface.co/api/models/apolo13x/Cosmos-Reason2-2B-GGUF?blobs=true
12. McNemar, Q. (1947). Note on the sampling error of the difference between correlated proportions or percentages.
    Psychometrika 12(2):153–157. https://doi.org/10.1007/BF02295996
13. Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. JASA 22(158):209–212.
    https://doi.org/10.1080/01621459.1927.10502953
14. NVIDIA Cosmos Cookbook — physical-plausibility post-training recipe (VideoPhy-2).
    https://nvidia-cosmos.github.io/cosmos-cookbook/recipes/post_training/reason2/physical-plausibility-check/post_training.html
15. NVIDIA Open Model License (Oct 24, 2025).
    https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
16. NVIDIA. *cosmos-reason2* repository (limited maintenance). https://github.com/nvidia-cosmos/cosmos-reason2
