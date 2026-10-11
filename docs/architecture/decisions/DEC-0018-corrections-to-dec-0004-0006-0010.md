# DEC-0018: Corrections to DEC-0004, DEC-0006 and DEC-0010

> Three accepted records stated details that differ from the approved plan or from the reviewed specifications. This
> record amends them rather than rewriting them:
> - DEC-0004 now uses separate licence and redistribution classes;
> - DEC-0006 sets ONNX opset 17–19 as the export range;
> - DEC-0010 compares every engine with the stored PyTorch fp32 reference outputs.
>
> · Part of: [decisions](README.md) · Related: [DEC-0004](DEC-0004-proprietary-sdks-reference-only.md) ·
> [DEC-0006](DEC-0006-3d-and-simulation-on-static-web.md) · [DEC-0010](DEC-0010-tensorrt-per-engine-parity.md)

**Status:** Accepted, 2026-10-07. Amends DEC-0004 (decision 4), DEC-0006 (decision 6) and DEC-0010 (its summary and
the parity reference).

## Context

While the specifications were written, three accepted decision records were checked against the approved plan and the
data contracts. Each one contradicted them in one detail. Accepted records are not rewritten, so the corrections are
recorded here, and each amended record's status line points to this record.

## Decision

1. **DEC-0004, decision 4 — two separate classes per source.**
   - The **licence class** is one of `public-domain`, `open-no-attribution`, `attribution`, `share-alike` (kept in
     separate manifest entries), `own`, `display-only` or `reference-only` (proprietary: named, never copied).
   - The **redistribution class** is one of `redistributable`, `derived-only` or `no-redistribution`.

   Both are defined in [sources and licences](../../data-contract/sources-and-licences.md). DEC-0004 had listed values
   from the two sets as if they were one. Whether performance data may be published is still decided by
   [DEC-0005](DEC-0005-performance-data-licence-rule.md).
2. **DEC-0006, decision 6 — ONNX opset 17–19.**
   - Models export at opset 17–19, as the approved plan states, not at PyTorch's default opset 20.
   - The reason is that WebGPU kernels such as `GridSample` are registered only for opsets 16–19 [1].
   - The opset chosen for each model and its reason are recorded in the manifest.
   - Parity is checked against the stored PyTorch fp32 outputs (see decision 3). DEC-0006 had said "default opset 20,
     with 17–19 allowed when needed".
3. **DEC-0010 — the parity reference.**
   - Every engine, on every TensorRT version and execution provider, is compared with the **stored PyTorch fp32 outputs
     of the golden set**: parity layer 4, fp32 within rtol 1e-3 / atol 1e-5.
   - ONNX Runtime CPU already matches those outputs by parity layer 1, so a single reference serves all layers (see
     [export, parity and acceleration](../../models/export-parity-acceleration.md)).
   - DEC-0010 had named "the ONNX reference", which would be a second reference.

## Alternatives considered

| Alternative | Why it was not taken |
|---|---|
| Rewrite DEC-0004, DEC-0006 and DEC-0010 in place | The decision-record rules forbid rewriting accepted records except for typos and broken links |
| Keep the old wording and fix only the other pages | The records would keep contradicting the plan and the specifications they govern |

## Consequences

- Readers of DEC-0004, DEC-0006 or DEC-0010 are pointed here by their status lines.
- The specifications follow the corrected wording: 001-contracts for the classes, 016-export-acceleration for the opset
  and the parity reference.

## References

1. ONNX Runtime Web. WebGPU operator list. https://github.com/microsoft/onnxruntime/blob/main/js/web/docs/webgpu-operators.md
