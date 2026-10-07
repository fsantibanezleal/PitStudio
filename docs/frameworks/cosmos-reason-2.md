# Cosmos Reason 2

> NVIDIA's 2-billion-parameter vision-language reasoning model, run locally through llama.cpp on a self-converted
> GGUF, and scored against exact scene ground truth on pit-safety questions. · Part of: [Frameworks](README.md) ·
> Related: [M22 Cosmos VLM tasks](../methods/m22-cosmos-vlm-tasks.md) · [Cosmos Reason 2 model card](../models/cosmos-reason-2.md) ·
> [Vision-language reasoning](../theory/vision-language-reasoning.md) · [DEC-0009](../architecture/decisions/DEC-0009-vlm-llamacpp-gguf.md)

## What and why

Cosmos-Reason2-2B is a post-trained Qwen3-VL-2B-Instruct with 2,438,696,960 BF16 parameters [1][2]. It takes images,
video and text and answers in a `<think>…</think><answer>…</answer>` format [1]. Its card reports 62.21 % on its
"General" category against 59.60 % for Qwen3-VL-2B [1].

PitStudio uses it for three **zero-shot, measurable** tasks, all scored against answers computed from the USD scene,
never against another model's opinion:

| Task | Data | Metric |
|---|---|---|
| A. Hazard questions | ~6.5k templated questions over SDG renders ("is a person within 30 m of a haul truck?", "is visibility reduced by dust?") | balanced accuracy and F1 per question type with 95 % CI; McNemar test against the Qwen3-VL base |
| B. Physics-plausibility critic | 100 clip pairs: a calibrated granular run and the same run with one controlled corruption | pairwise accuracy, AUROC, detection rate per corruption; a physics-check baseline |
| C. Captions of synthetic images | ~2k SDG frames | object hallucination and omission rates against the scene graph |

It is a frontier extra, not a safety system: no headline KPI depends on it, and its answers are shown with the wrong
ones included. The detector + geometric rule baseline carries the product claim.

Why llama.cpp ([DEC-0009](../architecture/decisions/DEC-0009-vlm-llamacpp-gguf.md)):

| Path | Verdict |
|---|---|
| **llama.cpp, own GGUF Q8_0** | chosen: portable Windows CUDA builds, no admin; Qwen3-VL support merged 2025-10-30 [3][4] |
| transformers BF16 | kept as the un-quantised reference and for native video [1] |
| vLLM / NIM | no native Windows; the NIM matrix starts at 24 GB [5][6] |
| TensorRT-LLM | "Windows platform support is deprecated as of v0.18.0" [7] |
| third-party GGUFs | provenance: the repo NVIDIA's Jetson page points to predates the improved checkpoint, and one copy is mislabelled Apache-2.0 [8][9] |

## Identity

| Item | Value |
|---|---|
| Model | `nvidia/Cosmos-Reason2-2B`, revision `9ce19a1` (last modified 2026-04-30); gated, contact sharing required [2] |
| Runtime | llama.cpp build **b11381** (2026-10-03), Windows CUDA 13.4 x64 zip + matching cudart, verified and extracted per user [3] |
| Lock | none: an external tool; zip and GGUF files pinned by SHA-256 at use |
| Licence | NVIDIA Open Model License (2025-10-24) for the weights; llama.cpp MIT [10][11] |
| Class | reference-only (weights never published; outputs display-only) |
| Ring | Assess (optional lane) |
| Environment | `studio/reason/` (llama.cpp external tool; no Python project) |
| Control model | Qwen3-VL-2B-Instruct, Apache-2.0 [12] |

## How PitStudio uses it

1. The maintainer accepts the gated terms on Hugging Face; a read token stays in the environment.
2. Convert the official revision to GGUF F16 → Q8_0 plus an F16 vision projector with the pinned llama.cpp build;
   record every SHA-256. By arithmetic the Q8_0 weights plus projector are about 3 GB [9].
3. `st59_reason_bench`: on 200 mixed queries, compare Q8_0 with BF16. Gate: **≥ 95 % agreement on binary questions**,
   or BF16 replaces the Q8_0 path.
4. `st59a_vqa`, `st59b_plausibility`, `st59c_captions`: tasks A–C, 8–16 GPU-hours in one or two overnight slots
   (estimate; VRAM of about 3–5 GB to be measured).

Artefacts: precomputed JSON records per question (frames shown, question, full model output, ground-truth answer,
correct/incorrect badge, model revision, GGUF hash, runtime build, sampling seed). The site shows them under
"Built on NVIDIA Cosmos".

## Licence and redistribution

The NVIDIA Open Model License grants a "revocable license" to use and create derivative models; a quantisation is a
derivative model. Distributing the model needs the licence and the notice "Licensed by NVIDIA Corporation under the
NVIDIA Open Model License" [10]. Making available "a product or service … that contains or uses a NVIDIA Cosmos Model",
or using its outputs to train another model, requires "Built on NVIDIA Cosmos" on a related page [10]. Rights end
automatically if a guardrail is bypassed [10]. PitStudio therefore: never publishes weights; shows outputs
display-only with "Built on NVIDIA Cosmos"; never uses Cosmos captions to filter training data; never uses
"abliterated" variants. NVIDIA "claims no ownership rights in outputs" [10].

## Assumptions and limits

- NVIDIA's card states a 24 GB minimum, BF16 tested on Linux only [1]; NVIDIA's Jetson AI Lab runs the same 2B model as
  Q8_0 GGUF on an 8 GB Orin Nano [13]. Fit and quality on the 16 GB laptop are an **open measurement**.
- Native video for Qwen3-VL in llama.cpp is **UNVERIFIED**: frames sampled at 4 fps go in as an ordered image list,
  labelled as such; native-video questions use transformers.
- The card names challenging cases (fast camera motion, overlapping interactions, low light) [1] — exactly the dust and
  night conditions of B2. A result near chance is reported, not hidden.
- The cosmos-reason2 repo is in limited maintenance; NVIDIA's focus moved to Cosmos 3 [14].

## In PitStudio

- Probe: llama.cpp smoke after the GPU hold; the binary is already verified and extracted. The Cosmos weights wait for
  the maintainer's gated-terms acceptance ([Maintainer acts and licences](../studio/owner-acts-and-licences.md)).
- Guide: [Cosmos tasks](../guides/cosmos-tasks.md). Cases: [B1](../cases/b1-traffic-proximity.md),
  [B2](../cases/b2-synthetic-perception.md).
- Status: **not yet run** — produced in the data-and-models phase. If the terms are not accepted, the tasks run on Qwen3-VL-2B only and this page stays "not run".

## References

1. NVIDIA. *Cosmos-Reason2-2B model card*. https://huggingface.co/nvidia/Cosmos-Reason2-2B
2. Hugging Face API. *nvidia/Cosmos-Reason2-2B* (parameters, gating, last modified). https://huggingface.co/api/models/nvidia/Cosmos-Reason2-2B
3. ggml-org. *llama.cpp releases (API)*. https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8
4. ggml-org. *Pull request #16780: Qwen3-VL support*. https://api.github.com/repos/ggml-org/llama.cpp/pulls/16780
5. vLLM. *GPU installation* (no native Windows). https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html
6. NVIDIA. *NIM for VLMs 1.7.0 support matrix*. https://docs.nvidia.com/nim/vision-language-models/1.7.0/support-matrix.html
7. NVIDIA. *TensorRT-LLM release notes*. https://nvidia.github.io/TensorRT-LLM/release-notes.html
8. Hugging Face. *Kbenkhaled/Cosmos-Reason2-2B-GGUF*. https://huggingface.co/Kbenkhaled/Cosmos-Reason2-2B-GGUF
9. Hugging Face API. *apolo13x/Cosmos-Reason2-2B-GGUF* (dates, file sizes). https://huggingface.co/api/models/apolo13x/Cosmos-Reason2-2B-GGUF?blobs=true
10. NVIDIA. *NVIDIA Open Model License* (2025-10-24). https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
11. ggml-org. *llama.cpp repository (API)*. https://api.github.com/repos/ggml-org/llama.cpp
12. Hugging Face API. *Qwen/Qwen3-VL-2B-Instruct*. https://huggingface.co/api/models/Qwen/Qwen3-VL-2B-Instruct
13. NVIDIA. *Jetson AI Lab: Cosmos Reason 2 2B*. https://www.jetson-ai-lab.com/models/cosmos-reason2-2b/
14. NVIDIA. *cosmos-reason2 repository*. https://github.com/nvidia-cosmos/cosmos-reason2
