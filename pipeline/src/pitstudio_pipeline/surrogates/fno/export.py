"""FNO export (s60_export; FR-011-36, FR-011-37, SC-011-04, NFR-011-03): MatMul-only graphs, the operator whitelist, parity, fp16.

`export_fno` writes `<model_id>-fp32.onnx` and `<model_id>-fp16.onnx` at opset 19 and IR version 10 with the float32 interface
`fields` [1, C_in, 64, 64] -> `depth` [1, C_out, 64, 64] (the fp16 graph keeps float32 inputs and outputs through Cast nodes), runs
`verify_graph` on both and describes each with a DC-011-02 document. The graph may hold only the operators of the whitelist of
spec 011 section 7 (no DFT, no Einsum, no tensor of a two-component number type): anything else fails FR-011-36 with the operator
named. The fp16 graph is the live one only when the mean relative L2 of every field changes by at most 1 percentage point.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import re
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import torch

from pitstudio_pipeline.surrogates.errors import ExportError
from pitstudio_pipeline.surrogates.fno.model import FnoModel
from pitstudio_pipeline.surrogates.gns.export import sort_topologically
from pitstudio_pipeline.surrogates.gns.parity import MIN_GOLDEN, ParityReport
from pitstudio_pipeline.surrogates.thresholds import model_threshold

OPSET = 19
IR_VERSION = 10
GRID = 64
LIVE_BYTES_MAX = 25_000_000  # NFR-011-03
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
OPERATOR_WHITELIST = frozenset(
    {
        "MatMul", "Add", "Sub", "Mul", "Div", "Erf", "Reshape", "Transpose", "Concat", "Slice", "Gather", "Unsqueeze",
        "Squeeze", "Constant", "Identity", "Cast",
    }
)  # fmt: skip
_COMPLEX = {onnx.TensorProto.COMPLEX64, onnx.TensorProto.COMPLEX128}


@dataclass(frozen=True)
class FnoExport:
    model_id: str
    paths: dict[str, Path]
    io: dict[str, dict[str, Any]]


def verify_graph(path: str | Path) -> None:
    """Raise ExportError naming the operator or tensor type when the graph leaves the whitelist (FR-011-36)."""
    proto = onnx.load(str(path))
    bad = sorted({n.op_type for n in proto.graph.node} - OPERATOR_WHITELIST)
    if bad:
        raise ExportError(f"the graph holds operators outside the whitelist: {bad}")
    if any(i.data_type in _COMPLEX for i in proto.graph.initializer):
        raise ExportError("the graph holds a complex-typed initializer")
    for value in [*proto.graph.input, *proto.graph.output, *proto.graph.value_info]:
        if value.type.tensor_type.elem_type in _COMPLEX:
            raise ExportError(f"tensor {value.name} has a complex element type")
    for node in proto.graph.node:
        for attr in node.attribute:
            if attr.type == onnx.AttributeProto.TENSOR and attr.t.data_type in _COMPLEX:
                raise ExportError(f"node {node.name or node.op_type} carries a complex-typed constant")


def _trace(model: FnoModel, input_name: str, output_name: str) -> bytes:
    work = copy.deepcopy(model).cpu().float().eval()
    example = torch.zeros(1, model.in_channels, GRID, GRID)
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        torch.onnx.export(
            work,
            (example,),
            buffer,
            input_names=[input_name],
            output_names=[output_name],
            opset_version=OPSET,
            dynamo=False,
            do_constant_folding=True,
        )
    proto = onnx.load_from_string(buffer.getvalue())
    proto.ir_version = IR_VERSION
    onnx.checker.check_model(proto)
    return proto.SerializeToString()


def _to_fp16(fp32: bytes) -> bytes:
    from onnxruntime.transformers.float16 import convert_float_to_float16

    proto = convert_float_to_float16(onnx.load_from_string(fp32), keep_io_types=True, disable_shape_infer=False)
    sort_topologically(proto.graph)
    proto.ir_version = IR_VERSION
    onnx.checker.check_model(proto)
    return proto.SerializeToString()


def export_fno(
    model: FnoModel,
    out_dir: str | Path,
    *,
    model_id: str,
    inputs: Sequence[Mapping[str, Any]],
    outputs: Sequence[Mapping[str, Any]],
    envelope: Mapping[str, Any],
    cases: Sequence[str] = ("C2",),
    input_name: str = "fields",
    output_name: str = "depth",
) -> FnoExport:
    """Write the fp32 and fp16 graphs and their DC-011-02 descriptions under `out_dir`; see the module docstring."""
    if not isinstance(model, FnoModel):
        raise TypeError(f"model must be an FnoModel, got {type(model).__name__}")
    if not envelope:
        raise ValueError("envelope must hold at least one parameter range (DC-011-02 training_envelope)")
    if not SLUG.fullmatch(model_id or ""):
        raise ValueError(f"model_id must be a slug of lower-case letters, digits and hyphens, got {model_id!r}")
    if len(inputs) != model.in_channels or len(outputs) != model.out_channels:
        raise ValueError(
            f"the channels lists ({len(inputs)} in, {len(outputs)} out) differ from the model's "
            f"({model.in_channels} in, {model.out_channels} out)"
        )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fp32 = _trace(model, input_name, output_name)
    files = {"fp32": fp32, "fp16": _to_fp16(fp32)}
    paths: dict[str, Path] = {}
    docs: dict[str, dict[str, Any]] = {}
    for key, raw in files.items():
        path = out / f"{model_id}-{key}.onnx"
        path.write_bytes(raw)
        verify_graph(path)
        paths[key] = path
        docs[key] = {
            "model_id": model_id,
            "engine": "fno",
            "cases": list(cases),
            "description": "2-D FNO direct map, spectral layers as real matrix products, live graph",
            "onnx": {"path": f"{out.name}/{path.name}", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)},
            "opset": OPSET,
            "ir_version": IR_VERSION,
            "precision": key,
            "delivery": "live",
            "inputs": [
                {
                    "name": input_name,
                    "dtype": "float32",
                    "shape": [1, model.in_channels, GRID, GRID],
                    "unit": "per-channel",
                    "channel_axis": 1,
                    "channels": copy.deepcopy([dict(c) for c in inputs]),
                }
            ],
            "outputs": [
                {
                    "name": output_name,
                    "dtype": "float32",
                    "shape": [1, model.out_channels, GRID, GRID],
                    "unit": "per-channel",
                    "channel_axis": 1,
                    "channels": copy.deepcopy([dict(c) for c in outputs]),
                }
            ],
            "training_envelope": copy.deepcopy(dict(envelope)),
        }
        if len(raw) > LIVE_BYTES_MAX:
            raise ValueError(f"live graph {key} is {len(raw)} bytes, above the {LIVE_BYTES_MAX} byte limit (NFR-011-03)")
        (out / f"{model_id}-{key}.io.json").write_text(json.dumps(docs[key], indent=2) + "\n", encoding="utf-8")
    return FnoExport(model_id=model_id, paths=paths, io=docs)


def check_parity(model: FnoModel, onnx_path: str | Path, *, n_golden: int = MIN_GOLDEN, seed: int = 0) -> ParityReport:
    """ONNX Runtime CPU against PyTorch fp32 on `n_golden` random fields (`models.onnx_cpu_fp32`, SC-011-04)."""
    if n_golden < MIN_GOLDEN:
        raise ValueError(f"at least {MIN_GOLDEN} golden fields are required, got {n_golden}")
    tol = model_threshold("onnx_cpu_fp32")
    tolerances = {"rtol": float(tol["rtol"]), "atol": float(tol["atol"]), "max_abs": float(tol["max_abs"])}
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name
    model = model.eval().float().cpu()
    rng = np.random.default_rng(seed)
    max_abs = max_rel = 0.0
    worst, worst_step, passed = -1.0, 0, True
    for k in range(n_golden):
        x = rng.normal(size=(1, model.in_channels, GRID, GRID)).astype(np.float32)
        got = np.asarray(session.run(None, {name: x})[0], dtype=np.float64)
        with torch.no_grad():
            want = model(torch.from_numpy(x)).numpy().astype(np.float64)
        diff = np.abs(got - want)
        if not (np.isfinite(got).all() and bool((diff <= tolerances["atol"] + tolerances["rtol"] * np.abs(want)).all())):
            passed = False
        step_max = float(diff.max()) if np.isfinite(diff).all() else math.inf
        max_abs = max(max_abs, step_max)
        max_rel = max(max_rel, float((diff / np.maximum(np.abs(want), 1e-12)).max()))
        if step_max > worst:
            worst, worst_step = step_max, k
    if max_abs > tolerances["max_abs"]:
        passed = False
    return ParityReport(passed=passed, n_golden=n_golden, max_abs=max_abs, max_rel=max_rel, tolerances=tolerances, worst_step=worst_step)


def choose_live_precision(delta_pp: Mapping[str, float]) -> str:
    """"fp16" iff every field's mean relative L2 changes by at most 1 percentage point (FR-011-37), else "fp32"."""
    if not delta_pp:
        return "fp32"
    limit = float(model_threshold("quantized_task_metric_delta_max_pp"))
    for value in delta_pp.values():
        if not isinstance(value, int | float) or not math.isfinite(value) or abs(value) > limit:
            return "fp32"
    return "fp16"
