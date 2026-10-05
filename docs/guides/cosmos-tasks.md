# Cosmos tasks

> Run the three Cosmos Reason 2 tasks — pit-safety hazard questions scored against exact USD ground truth, a
> physics-plausibility critic of PitStudio's own simulations, and hallucination-scored captions of synthetic images —
> with a self-converted GGUF in llama.cpp, a BF16 reference and two controls. · Part of: [Guides](README.md) ·
> Related: [Cosmos Reason 2](../frameworks/cosmos-reason-2.md) ·
> [M22 Cosmos VLM tasks](../methods/m22-cosmos-vlm-tasks.md) ·
> [vision-language reasoning](../theory/vision-language-reasoning.md) ·
> [DEC-0009 VLM via llama.cpp GGUF](../architecture/decisions/DEC-0009-vlm-llamacpp-gguf.md)

## What and why

**Goal:** measure, against exact answers, what a 2-billion-parameter vision-language model gets right about open-pit
safety. Cosmos Reason 2 (2B) is a post-trained Qwen3-VL-2B-Instruct [1]. PitStudio's synthetic scenes know the truth of
every pixel (which object, where, how far from the truck), so questions such as "is a person inside the haul truck's
blind zone?" have exact answers computed from USD prims, and the model can be scored without human labels.

| Task | Input | Scored against | Controls |
|---|---|---|---|
| A — hazard questions | ~6.5k binary and multiple-choice questions on synthetic frames and clips | exact answers from USD prims | Qwen3-VL-2B base model; PitStudio's detector + a geometric rule |
| B — physics-plausibility critic | 100 pairs of simulation clips, one with one controlled corruption | which clip of the pair is physical (two-alternative forced choice) | chance; Qwen3-VL base |
| C — captions of synthetic images | ~2k images | object mentions and conditions vs the scene graph (hallucination and omission rates) | template captions from the scene graph |

**Status:** optional, never a headline KPI. The tasks run in stage group `st59_*` (`st59_reason_bench`, `st59a_vqa`,
`st59b_plausibility`, `st59c_captions`), written in the build phase. The weights are gated: without the maintainer's
acceptance of the terms and a read token, the Cosmos tool page says "not run".

## Prerequisites

- [Set up the studio](set-up-the-studio.md); llama.cpp b11381, CUDA build, unpacked outside the repository with its
  matching `cudart` archive [2]. llama.cpp gained Qwen3-VL support in October 2025 [3] and accepts a vision projector
  with `--mmproj` [4].
- **Maintainer acts:** accept the gated terms of `nvidia/Cosmos-Reason2-2B` on Hugging Face and create a **read**
  token [5]; set `HF_HOME` to a folder with room. Tokens are never committed and CI never needs them.
- Synthetic frames and clips with ground truth from [synthetic data generation](synthetic-data-generation.md) and the
  physics stages.
- GPU memory: the Q8_0 weights plus the F16 projector are about 3.0 GB [6]; the BF16 weights are about 4.9 GB by
  arithmetic from 2,438,696,960 parameters [7]. NVIDIA's card states a 24 GB minimum for its own serving setup [1], so the
  BF16 reference's fit on 16 GB is **measured, not assumed**.

## Steps

1. **Download the official revision** (pinned by commit) into `HF_HOME`, then **convert it to GGUF Q8_0 yourself** with
   llama.cpp's converter. Third-party GGUF files exist but their provenance and licence labels vary, so PitStudio uses
   only its own conversion and records the SHA-256 of every file [6]. The GGUF files are never published.

   ```bash run deferred=P6
   uv run --extra runner studio run recipes/b1-traffic.yaml --stage st59_reason_bench
   ```

2. **Check Q8_0 against BF16.** On a fixed question subset, the quantised model must agree with the BF16 reference on
   ≥ 95 % of binary questions before any task result counts.

3. **Run tasks A, B and C**, then the controls with the same prompts.

   ```bash run deferred=P6
   uv run --extra runner studio run recipes/b1-traffic.yaml --stage st59a_vqa
   uv run --extra runner studio run recipes/b1-traffic.yaml --stage st59b_plausibility
   uv run --extra runner studio run recipes/b2-perception.yaml --stage st59c_captions
   ```

   Video input: the model card asks for 4 fps video [1]; whether llama.cpp feeds Qwen3-VL native video tokens is
   unconfirmed, so frames are sampled at 4 fps and sent as an ordered image list, and results say so.

4. **Publish** the answer tables, sample Q&A cards (text) and the licence notice.

   ```bash run deferred=P6
   uv run --extra runner studio publish <run_id>
   ```

## Expected output and acceptance (pre-registered)

| Measure | Criterion | Today |
|---|---|---|
| Q8_0 vs BF16 agreement on binary questions | ≥ 95 % | **Not yet run** |
| Per-question-type balanced accuracy | reported with confidence intervals | **Not yet run** |
| "Cosmos beats the Qwen base" | only if McNemar's test gives p < 0.05 | **Not yet run** |
| Plausibility critic (task B) | 2AFC accuracy with CI vs chance | **Not yet run** |
| Caption hallucination / omission (task C) | rates vs the scene graph | **Not yet run** |

On the web, answers and captions are **text only, display-only**, with the attribution "Built on NVIDIA Cosmos" that
the NVIDIA Open Model License requires for Cosmos models [8].

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| HTTP 401 on download | the gated terms are not accepted, or the token lacks read access | the maintainer accepts the terms and creates a read token |
| llama.cpp fails to load CUDA | the `cudart` archive does not match the build | unpack the matching `cudart-…-cuda-13.4` archive next to the binaries |
| Q8_0 and BF16 disagree above 5 % | quantisation or prompt-format drift | fix the prompt template first; the task does not run until agreement passes |
| Out of memory on the BF16 reference | long context plus video frames | reduce frames per query; record the limit in the manifest |

## Assumptions and limits

- Zero-shot only: no fine-tuning. Results describe this model on these synthetic scenes, not real pits.
- The licence of the weights (NVIDIA Open Model License) is not an OSI licence; PitStudio publishes outputs, never the
  weights or their conversions.
- Cosmos Predict and Transfer are not run: they need about 32.5 and 65.4 GB of VRAM
  ([not adopted](../frameworks/not-adopted-cosmos-predict-transfer.md)).

## In PitStudio

- Cases [B1](../cases/b1-traffic-proximity.md) (hazard questions) and [B2](../cases/b2-synthetic-perception.md)
  (captions); method [M22](../methods/m22-cosmos-vlm-tasks.md); model card [Cosmos Reason 2](../models/cosmos-reason-2.md);
  spec `015-vlm`.

## References

1. NVIDIA, "Cosmos-Reason2-2B" model card — base model Qwen3-VL-2B-Instruct, 4 fps video input, 24 GB minimum for its serving setup, gated, licence. https://huggingface.co/nvidia/Cosmos-Reason2-2B
2. ggml-org, llama.cpp releases — b11381 with Windows CUDA 12.4 / 13.4 builds and `cudart` archives. https://github.com/ggml-org/llama.cpp/releases
3. ggml-org, llama.cpp PR #16780 "add support for qwen3vl series" — merged 2025-10-30. https://github.com/ggml-org/llama.cpp/pull/16780
4. ggml-org, llama.cpp "Multimodal" documentation — `--mmproj`, GPU offload. https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md
5. Hugging Face API, `nvidia/Cosmos-Reason2-2B` — gated access. https://huggingface.co/api/models/nvidia/Cosmos-Reason2-2B
6. Hugging Face API, community GGUF conversion files with sizes and SHA-256 (Q8_0 2,165,040,800 B; mmproj F16 819,395,424 B). https://huggingface.co/api/models/apolo13x/Cosmos-Reason2-2B-GGUF?blobs=true
7. Hugging Face API, `nvidia/Cosmos-Reason2-2B` — 2,438,696,960 BF16 parameters. https://huggingface.co/api/models/nvidia/Cosmos-Reason2-2B
8. NVIDIA, "NVIDIA Open Model License Agreement" — notice and "Built on NVIDIA Cosmos". https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
