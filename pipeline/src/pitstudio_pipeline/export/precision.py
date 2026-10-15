"""fp16, int8 and fp8 variants and the layer-2 gate (FR-016-08, FR-016-09, FR-016-10).

fp16 uses ONNX Runtime's converter with the numerically sensitive operator types kept in fp32; int8 and fp8 use ONNX
Runtime `quantize_static` in QDQ format with per-channel weights and per-tensor activations, calibrated on exactly 500
training inputs that are disjoint from the golden and evaluation sets.
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.export.variant_rules import check_variant_request

FP32_KEPT_OPS = ["LayerNormalization", "Softmax", "ReduceMean", "ReduceSum", "ReduceMax"]
CALIBRATION_N = 500
METRIC_DELTA_MAX_PP = 1.0
MASK_IOU_MIN = 0.99


class PrecisionError(Exception):
    """A variant that cannot be built or accepted; `.reason` is the message."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _check_calibration(
    inputs: Sequence[np.ndarray] | None, golden: Collection[str], evaluation: Collection[str]
) -> list[np.ndarray]:
    if inputs is None or len(inputs) != CALIBRATION_N:
        raise PrecisionError(f"calibration needs exactly {CALIBRATION_N} inputs, got {None if inputs is None else len(inputs)}")
    banned = set(golden) | set(evaluation)
    for i, array in enumerate(inputs):
        if _digest(np.asarray(array)) in banned:
            raise PrecisionError(f"calibration input {i} is in the golden or evaluation set")
    return [np.asarray(a) for a in inputs]


class _Reader:
    def __init__(self, name: str, inputs: Sequence[np.ndarray]) -> None:
        self._iter = iter({name: a} for a in inputs)

    def get_next(self) -> dict[str, np.ndarray] | None:
        return next(self._iter, None)


def _topological(model: Any) -> Any:
    """The converter can emit its boundary Cast nodes after their consumers; put the nodes back in dependency order."""
    graph = model.graph
    ready = {i.name for i in graph.input} | {t.name for t in graph.initializer}
    pending = list(graph.node)
    ordered = []
    while pending:
        progressed = [n for n in pending if all(not name or name in ready for name in n.input)]
        if not progressed:
            raise PrecisionError("fp16 graph has a cycle or a dangling input after conversion")
        for node in progressed:
            ordered.append(node)
            ready.update(node.output)
        done = {id(n) for n in progressed}
        pending = [n for n in pending if id(n) not in done]
    del graph.node[:]
    graph.node.extend(ordered)
    return model


def _atomic_output(out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=out_path.parent, suffix=".tmp")
    os.close(handle)
    return Path(tmp)


def make_variant(
    onnx_path: Path,
    out_path: Path,
    precision: str,
    *,
    config: dict,
    calibration_inputs: Sequence[np.ndarray] | None = None,
    golden_digests: Collection[str] = (),
    eval_digests: Collection[str] = (),
) -> Path:
    """The variant graph of `onnx_path` at `precision`; fp32 returns `onnx_path` itself."""
    import onnx

    check_variant_request(precision, opset=config["opset"], gemm_heavy=config["gemm_heavy"])
    onnx_path, out_path = Path(onnx_path), Path(out_path)
    if precision == "fp32":
        return onnx_path
    if precision == "fp16":
        from onnxruntime.transformers.float16 import convert_float_to_float16

        model = _topological(
            convert_float_to_float16(onnx.load(onnx_path), keep_io_types=True, op_block_list=FP32_KEPT_OPS)
        )
        tmp = _atomic_output(out_path)
        onnx.save(model, tmp)
        os.replace(tmp, out_path)
        return out_path

    from onnxruntime.quantization import CalibrationMethod, QuantFormat, QuantType, quantize_static

    inputs = _check_calibration(calibration_inputs, golden_digests, eval_digests)
    input_name = onnx.load(onnx_path).graph.input[0].name
    qtype = QuantType.QInt8 if precision == "int8" else QuantType.QFLOAT8E4M3FN
    tmp = _atomic_output(out_path)
    try:
        quantize_static(
            str(onnx_path),
            str(tmp),
            _Reader(input_name, inputs),
            quant_format=QuantFormat.QDQ,
            per_channel=True,
            calibrate_method=CalibrationMethod.MinMax if precision == "int8" else CalibrationMethod.Distribution,
            activation_type=qtype,
            weight_type=qtype,
            extra_options={"ActivationSymmetric": precision == "fp8", "WeightSymmetric": True},
        )
        os.replace(tmp, out_path)
    finally:
        tmp.unlink(missing_ok=True)
    return out_path


def select_calibration_inputs(
    pool: Sequence[Mapping[str, str]],
    *,
    golden_digests: Collection[str],
    eval_digests: Collection[str],
    n: int = CALIBRATION_N,
    seed: int,
) -> list[str]:
    """`n` unique training digests, seeded, none in the golden or evaluation digests."""
    banned = set(golden_digests) | set(eval_digests)
    eligible = sorted({p["sha256"] for p in pool if p["split"] == "train" and p["sha256"] not in banned})
    if len(eligible) < n:
        raise PrecisionError(f"calibration needs {n} eligible training inputs, only {len(eligible)} are available")
    chosen = np.random.default_rng(seed).choice(len(eligible), size=n, replace=False)
    return [eligible[i] for i in chosen]


@dataclass(frozen=True)
class GateResult:
    verdict: str
    reason: str | None
    delta_pp: float
    mask_iou: float | None


def layer2_gate(
    *,
    metric_fp32: float,
    metric_variant: float,
    mask_iou: float | None = None,
    requires_mask_iou: bool = False,
    requires_robustness: bool = False,
    robustness_ok: bool | None = None,
) -> GateResult:
    """Accept a reduced-precision variant only within 1 pp of the fp32 metric (and the mask IoU / robustness rules)."""
    delta = metric_variant - metric_fp32
    reasons: list[str] = []
    if not (math.isfinite(metric_fp32) and math.isfinite(metric_variant)):
        reasons.append("task metric is not finite")
    elif abs(delta) > METRIC_DELTA_MAX_PP + 1e-9:
        reasons.append(f"task metric changed by {delta:+.3g} pp, more than {METRIC_DELTA_MAX_PP} pp")
    if requires_mask_iou:
        if mask_iou is None or not math.isfinite(mask_iou):
            reasons.append("mask IoU was not measured")
        elif mask_iou < MASK_IOU_MIN:
            reasons.append(f"mask IoU {mask_iou:.3f} is below {MASK_IOU_MIN}")
    if requires_robustness and robustness_ok is not True:
        reasons.append("detector robustness criterion " + ("failed" if robustness_ok is False else "was not evaluated"))
    if reasons:
        return GateResult("rejected", "; ".join(reasons), delta, mask_iou)
    return GateResult("pass", None, delta, mask_iou)
