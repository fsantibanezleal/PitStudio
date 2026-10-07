# DEC-0009: Cosmos Reason 2 through llama.cpp, from our own GGUF

> The vision-language tasks run Cosmos Reason 2 (2B) as a Q8_0 GGUF converted by PitStudio from the official revision,
> in a portable CUDA build of llama.cpp on Windows, with the official BF16 weights in transformers as the reference and
> Qwen3-VL-2B as the control. · Part of: [decisions](README.md) · Related: [Cosmos Reason 2](../../frameworks/cosmos-reason-2.md) ·
> [M22 Cosmos VLM tasks](../../methods/m22-cosmos-vlm-tasks.md) · [vision-language reasoning](../../theory/vision-language-reasoning.md)

**Status:** Accepted, 2026-10-04

## Context

PitStudio asks a vision-language model three kinds of question: hazard questions about rendered pit scenes, whose
answers are computed exactly from USD prims; physics-plausibility judgements of its own simulations; and captions of
synthetic images, scored for hallucination. Cosmos Reason 2 is the natural candidate, but:

- its model card lists 24 GB of GPU memory and Linux [1], while the reference GPU has 16 GB and runs Windows;
- vLLM, the usual server, has no native Windows support [2]; NVIDIA's NIM containers target Linux (with WSL2 for some
  RTX NIMs) and an enterprise licence [3]; TensorRT-LLM deprecated Windows as of v0.18.0 [4];
- NVIDIA's Jetson AI Lab lists Cosmos-Reason2-2B on an 8 GB Jetson Orin Nano through llama.cpp with a Q8_0 GGUF [5],
  and llama.cpp publishes Windows CUDA 13.4 builds (b11381) [6] with multimodal support through a vision projector [7];
- the public Q8_0 GGUF is a third-party conversion, which is a provenance risk [8];
- the weights are gated on Hugging Face under the NVIDIA Open Model License, which requires the licence notice and
  "Built on NVIDIA Cosmos" on redistribution [9].

## Decision

- **Runtime.** llama.cpp b11381, portable CUDA build, downloaded and verified by SHA-256, run as an external tool from
  `studio/reason/` (configuration, prompts, evaluation and hash pins only).
- **Weights.** PitStudio converts the official Cosmos-Reason2-2B revision to GGUF Q8_0 itself and pins the SHA-256. The
  download needs the maintainer's acceptance of the gated terms and a read token; without them, the Cosmos tasks show
  "not run".
- **Reference and control.** The official BF16 weights in transformers are the quality reference; Qwen3-VL-2B
  (Apache-2.0), the base model, is the control; PitStudio's detector plus a geometric rule is a third comparator.
- **Acceptance.** Q8_0 versus BF16 agreement ≥ 95 % on binary questions; balanced accuracy per question type with a
  confidence interval; "Cosmos beats Qwen base" only if McNemar's test gives $p < 0.05$; never a headline KPI.
- **Publication.** Answers and captions are precomputed text, display-only, with "Built on NVIDIA Cosmos" and the licence
  notice. Weights, including PitStudio's own GGUF, are never redistributed.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| vLLM or a NIM container | The vendor-documented serving paths | No native Windows; NIM needs Linux and an enterprise licence; the BF16 model card asks for ≥ 24 GB [1] [2] [3] | Does not run on the reference machine |
| TensorRT-LLM | Fast inference | Windows deprecated as of v0.18.0 [4] | Unsupported platform |
| A third-party GGUF from Hugging Face | Ready to use | Provenance of the conversion cannot be verified [8] | Convert from the official revision instead |
| Skip the VLM tasks | Simplest | Loses the only test of what a VLM gets right about pit safety | The tasks are optional, not dropped; they degrade to "not run" without the owner act |

## Consequences

**Positive.** A native Windows path without elevation; provenance under PitStudio's control; a quantisation-quality
check built into the evaluation.

**Negative, accepted.** Fit in 16 GB, throughput and multimodal behaviour on Windows are unmeasured until the probe runs;
an owner act is needed for the weights.

**Watch.** llama.cpp support for the model's vision projector; the Cosmos licence (newer Cosmos 3 models use OpenMDW);
Cosmos Reason releases.

**Status.** The llama.cpp binary is downloaded and verified; the smoke test waits for the reference machine and for
the gated weights.

## References

1. NVIDIA. Cosmos-Reason2-2B model card. https://huggingface.co/nvidia/Cosmos-Reason2-2B
2. vLLM GPU installation (no native Windows). https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html
3. NVIDIA NIM for vision-language models, getting started. https://docs.nvidia.com/nim/vision-language-models/1.7.0/getting-started.html
4. TensorRT-LLM release notes (Windows deprecated as of v0.18.0). https://nvidia.github.io/TensorRT-LLM/release-notes.html
5. NVIDIA Jetson AI Lab. Cosmos-Reason2-2B. https://www.jetson-ai-lab.com/models/cosmos-reason2-2b/
6. llama.cpp releases. https://github.com/ggml-org/llama.cpp/releases
7. llama.cpp multimodal documentation. https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md
8. A third-party Cosmos-Reason2-2B GGUF repository. https://huggingface.co/Kbenkhaled/Cosmos-Reason2-2B-GGUF
9. NVIDIA Open Model License. https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
