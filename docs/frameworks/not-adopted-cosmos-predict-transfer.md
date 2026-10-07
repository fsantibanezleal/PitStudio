# Cosmos Predict and Cosmos Transfer (evaluated, not adopted)

> NVIDIA's world-foundation models that generate or restyle video, evaluated for sim-to-real augmentation of synthetic
> images and not adopted locally because they need 32.5 to 65.4 GB of GPU memory. · Part of: [Frameworks](README.md) ·
> Related: [Cosmos Reason 2](cosmos-reason-2.md) · [B2 synthetic perception](../cases/b2-synthetic-perception.md) ·
> [Sim-to-real](../theory/sim-to-real.md) · [Maintainer acts and licences](../studio/owner-acts-and-licences.md)

## What and why

**Cosmos Predict 2.5** generates future video frames; **Cosmos Transfer 2.5** turns a control video (for example a
segmentation or depth render) into photorealistic video. Transfer is the interesting one for PitStudio: it could make
Replicator renders look more like real pit footage and shrink the synthetic-to-real gap of the equipment and people
detector in case B2 [1][2].

## What we evaluated

| Check | Finding |
|---|---|
| Memory | Predict 2.5-2B needs 32.54 GB of GPU memory; Transfer 2.5-2B needs 65.4 GB; BF16 only [1][2] |
| Platform | Linux; "not tested on other operating systems" [1] |
| Speed (NVIDIA's model cards) | a 5 s 720p clip (1280 × 704 at 16 FPS) takes about 124 s on a B200 to 2,567 s on an L40S for Predict, and 286 s on a B200 for Transfer [1][2] |
| Maintenance | both repositories are in limited maintenance; NVIDIA points users to Cosmos 3 [3] |
| Licence | NVIDIA Open Model License: "Built on NVIDIA Cosmos" on redistribution or on products using the model; rights end if guardrails are bypassed [4] |
| Cosmos 3 | released under OpenMDW-1.1 (no obligations on outputs); the 4B Edge model is BF16-only and lists Ampere, Hopper and Blackwell, not Ada [5][6] |

## Why not adopted

The reference GPU has 16 GB. Neither model fits, so local use is impossible, and quantised variants are not officially
supported. The core cases must never depend on an external paid service, so cloud generation cannot be the default.

## The optional cloud run

A one-day rental could run Transfer 2.5 on our control clips and add one arm to the B2 study: "Replicator" vs
"Replicator + Transfer". By arithmetic from public list prices (L40S from USD 1.55, B200 USD 7.15 per GPU-hour [7]) one
Transfer clip costs about USD 0.57 on a B200, and roughly 50 clips with setup and idle time fit **about USD 30–80 per
day** (estimate). An L40S cannot hold Transfer's 65.4 GB. The run is proposed **only** if the B2 synthetic-to-real gap
turns out large, and it is the maintainer's decision; the default is no
([Maintainer acts and licences](../studio/owner-acts-and-licences.md)). Outputs would be publishable with "Built on
NVIDIA Cosmos" and guardrails on [4].

## Assumptions and limits

- The arithmetic above uses prices read once; they change, and any spend is re-quoted first.
- Whether Cosmos 3 offers a control-conditioned mode equivalent to Transfer is **UNVERIFIED**.

## When to re-assess

- If the B2 equipment/people gap is large after the data-and-models phase and the maintainer approves a cloud budget.
- If a Cosmos 3 model supports Ada GPUs, or quantised local use, inside 16 GB.
- On a Linux host with a 48–80 GB GPU (see [Scaling to Linux](../studio/scaling-to-linux.md)).

## In PitStudio

- Status: **evaluated, not adopted.** No Cosmos Predict or Transfer output exists in the project.

## References

1. NVIDIA. *Cosmos-Predict2.5-2B model card*. https://huggingface.co/nvidia/Cosmos-Predict2.5-2B
2. NVIDIA. *Cosmos-Transfer2.5-2B model card*. https://huggingface.co/nvidia/Cosmos-Transfer2.5-2B
3. NVIDIA. *cosmos-predict2.5 README*. https://raw.githubusercontent.com/nvidia-cosmos/cosmos-predict2.5/main/README.md
4. NVIDIA. *NVIDIA Open Model License*. https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
5. NVIDIA. *Cosmos 3 repository*. https://github.com/NVIDIA/cosmos
6. NVIDIA. *Cosmos3-Edge model card*. https://huggingface.co/nvidia/Cosmos3-Edge
7. Nebius. *AI Cloud prices*. https://nebius.com/prices
