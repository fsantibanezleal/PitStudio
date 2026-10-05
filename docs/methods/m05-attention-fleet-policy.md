# M05 — Attention fleet policy (size-invariant dispatch)

> A dispatch policy that treats trucks, shovels and dumps as a set of tokens and decides with attention, so one
> network serves any fleet size; trained like M04 and judged by the same paired-seed rule. · Part of:
> [Methods](README.md) · Related: [M04 PPO dispatch](m04-ppo-dispatch.md) · [M02 DES](m02-haulage-des.md) ·
> [Robot learning theory](../theory/robot-learning.md) · [Dispatch policy cards](../models/dispatch-policies.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Beyond-SOTA | **yes** | precompute → live | [A1](../cases/a1-truck-shovel-dispatch.md) | PyTorch (dense attention) in `pipeline/`; ONNX | not yet implemented |

## What and why

The published RL dispatchers use fixed-length observation vectors: a DQN or PPO network built for one fleet layout
[3][4]. A mine's fleet changes every shift — trucks go to maintenance, a shovel moves. A **graph- or set-structured
policy**, with trucks, shovels and dumps as nodes and roads as relations, is size-invariant by construction, which
the fixed-vector formulations are not. Graph libraries such as PyTorch Geometric make this easy to build [5], but no
mining-specific graph or attention dispatch policy was found in the literature survey behind PitStudio. That makes M05
a frontier extension that PitStudio has to validate itself, which is why it sits on the beyond-SOTA rung.

M05 shares everything with [M04](m04-ppo-dispatch.md) — environment, PPO trainer, evaluation engine, baselines and
decision rule — and changes only the network. That isolates the question "does the architecture matter?".

## The algorithm

### Tokens

At a decision for free truck $i$, the observation is a set of tokens:

- **truck tokens** $h_1 \dots h_{N}$, one per truck (state, location, payload, expected travel times), padded to a
  maximum of 40 with a mask;
- **target tokens** $g_1 \dots g_{M}$, one per shovel or dump (queue length, expected start of service, capacity,
  grade), with a mask for closed targets.

Each token is embedded by a small MLP into $\mathbb{R}^{d}$.

### Attention layers

$L$ layers of scaled dot-product attention mix information across all tokens [1]:

$$
\operatorname{Attention}(Q, K, V) = \operatorname{softmax}\!\left(\frac{Q K^{\top}}{\sqrt{d_k}} + B_{\text{mask}}\right) V
$$

with queries, keys and values $Q = HW_Q$, $K = HW_K$, $V = HW_V$ computed from the token matrix $H$ (one row per
token), key dimension $d_k$, and $B_{\text{mask}}$ a matrix of 0 for valid and a large negative number for padded
tokens. Each layer adds a residual connection and a token-wise MLP.

### Decision head

The free truck's final embedding $h_i$ queries the target embeddings:

$$
\ell_{ij} = \frac{(W_q h_i)^{\top} (W_k g_j)}{\sqrt{d}}, \qquad
\pi_\theta(j \mid s) = \frac{\exp(\ell_{ij})\,\mathbb{1}[j \text{ valid}]}{\sum_{j'} \exp(\ell_{ij'})\,\mathbb{1}[j' \text{ valid}]}
$$

The value head mean-pools the truck tokens and applies an MLP. Because attention and pooling are permutation
equivariant and invariant, relabelling the trucks does not change the decision, and the same weights apply to 10 or
40 trucks.

```text
policy(trucks[N≤40], targets[M], free_truck i):
    H = embed(trucks) ++ embed(targets)                 # tokens
    for layer in 1..L: H = H + MLP(H + Attn(H, mask))
    logits = (Wq H[i]) · (Wk H[targets])ᵀ / sqrt(d)
    logits[invalid] = -inf
    return softmax(logits), value(mean(H[trucks]))
```

### Training, budget and export

- **Training:** identical to [M04](m04-ppo-dispatch.md): PPO with the clipped objective [2] in the GPU-vectorised
  environment; the budget of 1–5 GPU-hours and 2–4 GB covers both policies (estimate; measured by the `studio bench`
  probe before any long run).
- **Export:** the attention is written **densely** (padded MatMul + Softmax), never with scatter/gather message
  passing: `ScatterElements` is registered in the ONNX Runtime 1.30 WebGPU kernel registry [6], but whether that
  kernel honours the `reduction` attribute that message passing needs [7] is unverified, while MatMul and Softmax are
  supported on every tier. Opset 17–19, IR pinned, parity gate as in M04. Size under 2 MB.

## Baseline and comparison

- **Baselines:** SPTF and two-stage LP dispatch ([M03](m03-lp-dispatch.md)), in the independent `minehaulsim` DES
  ([M02](m02-haulage-des.md)), on at least 30 paired seeds; metric tonnes per hour.
- **Architecture comparison:** M05 vs the M04 MLP on the same paired seeds and under the same rule.
- **Fleet-size behaviour:** the paired comparison is reported per fleet size across the trained range, so a reader can
  see whether the size-invariant design pays off where the fleet changes.
- Every "better" follows the [pre-registered decision rule](README.md#how-methods-are-compared).

## Acceptance criterion (pre-registered)

- **At least 30 paired seeds.**
- **"Beats SPTF / LP" only by the decision rule on t/h** (paired 95 % CI of the difference excludes 0; otherwise "no
  significant difference").
- Export parity as for every learned model (fp32 rtol 1e-3 / atol 1e-5; reduced-precision and TensorRT variants
  reported with action agreement; failures reported as rejected).

**Results: Not yet run** — produced in the data-and-models phase. Reported: t/h, queue time and shovel idle vs SPTF,
LP and M04 with paired 95 % CIs, per fleet size.

## Lane and web delivery

**Precompute → live.** Training and the paired evaluation are precomputed. The ONNX policy (< 2 MB) runs in ONNX
Runtime Web (WebGPU, falling back to WASM) inside the TypeScript DES worker; the visitor can switch the dispatcher of
the running simulation and change the fleet size live. Fallback: baked traces.

## Assumptions and limits

- Size invariance holds within the trained range; behaviour far outside it (for example 80 trucks) is not claimed.
- Attention cost grows with the square of the token count; at ≤ 40 trucks plus a few targets this is negligible.
- Same environment caveats as M04: event-tick approximation, generic mine generator, no field validation.

## In PitStudio

- **Cases:** [A1](../cases/a1-truck-shovel-dispatch.md).
- **Code (planned):** a second policy class next to M04 in `pipeline/` (`s30_train`, `s50_evaluate`, `s60_export`);
  live inference in the `web/` DES worker. Model card: [dispatch policies](../models/dispatch-policies.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Vaswani, A. et al. (2017). *Attention Is All You Need*. https://arxiv.org/abs/1706.03762
2. Schulman, J. et al. (2017). *Proximal Policy Optimization Algorithms*. https://arxiv.org/abs/1707.06347
3. Zhang et al. (2020). *Dynamic Dispatching for Large-Scale Heterogeneous Fleet via Multi-agent Deep Reinforcement
   Learning*. https://arxiv.org/abs/2008.10713
4. Meng, Tian & Zhang (2025). Curriculum-guided PPO for truck dispatching on OpenMines.
   https://arxiv.org/abs/2502.20845
5. PyTorch Geometric 2.8.0.post1 (MIT). https://pypi.org/pypi/torch-geometric/json
6. ONNX Runtime 1.30.0 WebGPU execution-provider kernel registry.
   https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/core/providers/webgpu/webgpu_execution_provider.cc
7. ONNX `ScatterElements` operator — `reduction` add/mul since opset 16, max/min since 18.
   https://onnx.ai/onnx/operators/onnx__ScatterElements.html
