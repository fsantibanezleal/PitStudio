"""Which graph the ONNX Runtime TensorRT provider may receive (FR-016-25).

The provider takes fp32 graphs (its fp16 flag makes the fp16 cell) or QDQ graphs only; a graph whose float tensors were
pre-cast to fp16 is refused with `precast-fp16-to-ort-trt`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

CODE = "precast-fp16-to-ort-trt"
PRECISIONS = ("fp32", "fp16", "int8", "fp8")


class OrtTrtRefused(Exception):
    """The cell is refused; `.code` is `precast-fp16-to-ort-trt` and the message contains it."""

    code = CODE

    def __init__(self, detail: str) -> None:
        super().__init__(f"{CODE}: {detail}")


def _is_precast_fp16(model: Any) -> bool:
    from onnx import TensorProto

    half = TensorProto.FLOAT16
    graph = model.graph
    if any(t.data_type == half for t in graph.initializer):
        return True
    if any(v.type.tensor_type.elem_type == half for v in [*graph.input, *graph.output, *graph.value_info]):
        return True
    for node in graph.node:
        if node.op_type == "Cast" and any(a.name == "to" and a.i == half for a in node.attribute):
            return True
        if node.op_type == "Constant" and any(a.t.data_type == half for a in node.attribute if a.HasField("t")):
            return True
    return False


def graph_kind(model_path: Path) -> str:
    """`fp16-precast`, `qdq` or `fp32`."""
    import onnx

    model = onnx.load(model_path, load_external_data=False)
    if _is_precast_fp16(model):
        return "fp16-precast"
    ops = {n.op_type for n in model.graph.node}
    return "qdq" if {"QuantizeLinear", "DequantizeLinear"} <= ops else "fp32"


def prepare_ort_trt_cell(model_path: Path, precision: str) -> dict[str, Any]:
    """The graph and TensorRT-provider options of one ONNX Runtime TensorRT cell."""
    if precision not in PRECISIONS:
        raise ValueError(f"precision {precision!r} is not one of {', '.join(PRECISIONS)}")
    kind = graph_kind(Path(model_path))
    if kind == "fp16-precast":
        raise OrtTrtRefused(f"{Path(model_path).name} has float tensors pre-cast to fp16; give the provider the fp32 graph")
    if precision in ("fp32", "fp16"):
        if kind == "qdq":
            raise ValueError(f"{precision} cells take the fp32 graph, not a QDQ graph")
        return {"graph": Path(model_path), "provider_options": {"trt_fp16_enable": precision == "fp16"}}
    if kind != "qdq":
        raise ValueError(f"{precision} cells take a QDQ graph, not an {kind} graph")
    # int8 QDQ graphs need the provider's int8 flag; the fp8 QDQ graph carries its precision in the Q/DQ nodes
    options = {"trt_fp16_enable": False, **({"trt_int8_enable": True} if precision == "int8" else {})}
    return {"graph": Path(model_path), "provider_options": options}
