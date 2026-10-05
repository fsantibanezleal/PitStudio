# M08 — GNS granular surrogate, live in the browser

> A graph network simulator learns the per-step dynamics of the GPU granular solver and replays a dump or pile
> collapse live in the browser at interactive rates, judged on repose angle and run-out against held-out simulations.
> · Part of: [Methods](README.md) · Related: [M07 GPU granular physics](m07-gpu-granular-physics.md) ·
> [Bulk flow theory](../theory/bulk-flow-dem-mpm.md) · [GNS model card](../models/gns-granular.md) ·
> [Case A3](../cases/a3-loading-payload-variance.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Beyond-SOTA | **yes** | precompute → live | [A3](../cases/a3-loading-payload-variance.md) | pure-PyTorch message passing in `pipeline/` → ONNX; ORT-web | not yet implemented |

## What and why

GPU granular solvers ([M07](m07-gpu-granular-physics.md)) cannot run at mining scale in a browser. A learned
surrogate can: Graph Network-based Simulators (GNS) learn particle dynamics by message passing and generalise from
training on thousands of particles to different initial conditions, thousands of time steps and at least an order of
magnitude more particles at test time [1]. For granular flows, Choi and Kumar report a GNS surrogate "hundreds of
times faster" than high-fidelity simulators that generalises to unseen aspect ratios and more than twice the training
particle count [2]; a 3-D version reports a 300× speed-up [3].

GNS, MeshGraphNets and their open implementations are offline Python tools; no fetched source demonstrates live,
in-browser learned granular rollouts. That is the beyond-SOTA claim M08 sets out to *validate, not assert*: a GNS
trained on PitStudio's own Warp/Newton rollouts, exported to ONNX and run in ONNX Runtime Web, judged on the physical
observables a mining engineer cares about.

![GNS: particles to graph, encode-process-decode, predicted acceleration, integration](../assets/diagrams/gns-message-passing.svg)

*The neighbour graph is built outside the ONNX graph; the network encodes, passes messages, decodes an acceleration
per particle, and a semi-implicit Euler step advances the rollout.*

## The algorithm

### Graph

At step $t$ each particle $i$ has position $x_i^t \in \mathbb{R}^2$ (m) and the last $C$ velocities. Particles within
a connectivity radius $r$ (m) are joined by edges. The graph is built **outside** the ONNX model — a cell-list search
in TypeScript or WASM in the browser, in PyTorch during training — and passed in as an `edge_index` tensor, so the
exported network contains no neighbour search.

- **Node features** $v_i$: the last $C$ velocities, a particle-type embedding, and clipped distances to the domain
  walls.
- **Edge features** $e_{ij}$: relative displacement $(x_i - x_j)/r$ and its norm.

### Encode – process – decode

Following the GNS architecture [1]:

$$
\text{Encode:}\quad v_i \leftarrow \phi_v^{\text{enc}}(v_i), \qquad e_{ij} \leftarrow \phi_e^{\text{enc}}(e_{ij})
$$

$$
\text{Process } (m = 1..M):\quad
e_{ij} \leftarrow e_{ij} + \phi_e^{(m)}(e_{ij}, v_i, v_j), \qquad
v_i \leftarrow v_i + \phi_v^{(m)}\Big(v_i, \sum_{j \in \mathcal{N}(i)} e_{ij}\Big)
$$

$$
\text{Decode:}\quad \hat a_i = \phi^{\text{dec}}(v_i)
$$

All $\phi$ are MLPs with layer normalisation; $M$ is the number of message-passing steps and $\mathcal{N}(i)$ the
neighbours of $i$. The sum over neighbours is written in pure PyTorch (`index_add_` / `scatter_reduce`), which exports
to ONNX `ScatterElements` with `reduction="add"` (opset ≥ 16) [6].

### Integration and loss

The predicted acceleration $\hat a_i$ (m/s²) advances the state with a semi-implicit Euler step:

$$
v_i^{t+1} = v_i^{t} + \Delta t\,\hat a_i, \qquad x_i^{t+1} = x_i^{t} + \Delta t\, v_i^{t+1}
$$

Training minimises the mean squared error between normalised predicted and target accelerations over single steps.
Gaussian random-walk noise is added to the input velocities during training so the model learns to correct its own
rollout drift; message-passing depth and this training noise are the two critical choices reported in [1].

```text
train:
    for (window, target_acc) in rollouts_from_M07:          # Warp DEM / Newton MPM, 2-D
        noisy = add_random_walk_noise(window, sigma)
        g = radius_graph(noisy.x, r)                         # same cell list as the web worker
        loss = mse(normalise(gns(noisy, g)), normalise(target_acc))
        step(optimizer, loss)
rollout (web):
    repeat: g = radius_graph(x, r); a = onnx(x, v_hist, g); v += dt*a; x += dt*v
```

### Data, budget and export

- **Data:** 2-D rollouts of dumps, pile formation and column collapse from Warp DEM and Newton MPM
  ([M07](m07-gpu-granular-physics.md)), split by **geometry** so the test set contains initial geometries never seen
  in training. The public `geoelements/gns` code (MIT) and its sand datasets [4][5] serve as a reference
  implementation and baseline; its PyG extension dependencies do not install on PitStudio's PyTorch line, so it is not
  a dependency [7].
- **Budget:** 4–15 GPU-hours, 2–6 GB of VRAM (estimate; measured by the `studio bench` probe first). The engineering
  sketch behind it is about 1–2 k particles, 10 message-passing steps, latent width 128 and about 1.5 M parameters
  (ESTIMATE).
- **Export:** ONNX at opset 17–19 with the IR version pinned; about 3 MB. Two risks are known and tested:
  - whether the ONNX Runtime WebGPU kernel honours the `reduction` attribute of `ScatterElements` is unverified [8];
    for up to about 2 k particles a **dense masked aggregation** (MatMul with an incidence matrix) is the WebGPU-safe
    fallback;
  - TensorRT has a reported `ScatterElements`-with-reduction failure when indices outnumber outputs — exactly the GNS
    case (edges ≫ nodes) [9]; the per-engine parity gate decides, otherwise TensorRT is "not applicable" for GNS.

## Baseline and comparison

- **Ground truth / baseline:** the GPU solver itself ([M07](m07-gpu-granular-physics.md)) on held-out geometries.
- **Observables, not trajectories:** granular flow is chaotic, so particle-by-particle agreement is meaningless after a
  few steps. The comparison is on repose angle, run-out, mass conservation and pile profile.
- **Speed:** wall time per step of the surrogate in the browser vs the GPU solver in the studio, reported with
  hardware and tier.
- **Parity:** ONNX Runtime (CPU, WebGPU, WASM) vs PyTorch on a golden set of single steps.

## Acceptance criterion (pre-registered)

- **Repose angle within ±1.5° and run-out within ±5 % on held-out geometries.**
- Export parity: fp32 rtol 1e-3 / atol 1e-5 on the golden set; reduced-precision and TensorRT variants within the
  task-metric tolerance or reported as rejected
  ([DEC-0010](../architecture/decisions/DEC-0010-tensorrt-per-engine-parity.md)).

**Results: Not yet run** — produced in the data-and-models phase. Reported: repose and run-out errors per held-out
geometry, rollout stability length, ms/step per browser tier, and the parity table.

## Lane and web delivery

**Precompute → live.** The surrogate (about 3 MB) runs in ONNX Runtime Web, WebGPU first and WASM as fallback; the
lane gate requires each live model ≤ 25 MB and ≤ 50 ms per step (estimates; for ≤ 2 k particles the engineering
estimate is 10–50 ms per step on WebGPU). The neighbour search runs in a worker. Fallback: precomputed rollouts.

## Assumptions and limits

- 2-D only in this release; 3-D surrogates are out of scope for the browser budget.
- The surrogate inherits every assumption of its training solver (calibration, reduced stiffness) and adds learning
  error; outside the training distribution (other materials, much larger domains) it is not trusted.
- Repose and run-out are aggregate checks; local stress or force predictions are not claimed.

## In PitStudio

- **Cases:** [A3](../cases/a3-loading-payload-variance.md) (live dump and pile replay).
- **Code (planned):** `pipeline/` stages `s05_synthesize` (rollout export), `s30_train`, `s50_evaluate`,
  `s60_export`; neighbour search and rollout loop in a `web/` worker. Model card:
  [GNS granular](../models/gns-granular.md).
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Sanchez-Gonzalez, A. et al. (2020). *Learning to Simulate Complex Physics with Graph Networks*. ICML.
   https://arxiv.org/abs/2002.09405
2. Choi, Y. & Kumar, K. *Graph Neural Network-based surrogate model for granular flows*.
   https://arxiv.org/abs/2305.05218
3. 3-D granular GNS — 300× speed-up. https://arxiv.org/abs/2311.07416
4. `geoelements/gns` — GNS and MeshNet, sand datasets, MIT. https://github.com/geoelements/gns
5. GNS JOSS paper. https://doi.org/10.21105/joss.05025
6. ONNX `ScatterElements` — `reduction` add/mul since opset 16. https://onnx.ai/onnx/operators/onnx__ScatterElements.html
7. PyTorch Geometric installation — extension wheels listed only up to PyTorch 2.12.
   https://pytorch-geometric.readthedocs.io/en/latest/install/installation.html
8. ONNX Runtime 1.30.0 WebGPU execution-provider kernel registry.
   https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/onnxruntime/core/providers/webgpu/webgpu_execution_provider.cc
9. TensorRT issue #3650 — `ScatterElements` with reduction fails when indices outnumber outputs.
   https://github.com/NVIDIA/TensorRT/issues/3650
