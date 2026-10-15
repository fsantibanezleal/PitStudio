"""T-016-041: the ONNX Runtime TensorRT-provider input rule (unit, hostile).

Requirements: FR-016-25.

Spec: specs/016-export-acceleration/spec.md FR-016-25: if a graph whose float tensors were pre-cast to fp16 is given to
the ONNX Runtime TensorRT provider, `s64_bench` refuses that cell with `precast-fp16-to-ort-trt`; that provider
receives fp32 graphs (with its fp16 flag for the fp16 cell) or QDQ graphs only. plan.md test strategy row FR-016-25 (a
graph with fp16 initialisers sent to the TensorRT provider -> refused).

Oracles:
- graphs built by hand with `onnx.helper` (fp32; fp16 initialisers; fp16 inputs and outputs; QDQ with int8 weights and
  fp32 activations), element types read back with `onnx` itself;
- the ONNX Runtime converter `onnxruntime.transformers.float16.convert_float_to_float16` as the reference producer of
  a pre-cast fp16 graph (it inserts Cast nodes at the graph inputs and outputs and converts initialisers);
- the TensorRT-provider option names of ONNX Runtime (`trt_fp16_enable`, `trt_int8_enable`), as documented for the
  TensorRT execution provider.

Expected public API (module `pitstudio_pipeline.bench.ort_trt_inputs`, `pipeline/` environment):
    class OrtTrtRefused(Exception)            # `.code == "precast-fp16-to-ort-trt"`; str(exc) contains the code
    graph_kind(model_path: Path) -> str       # "fp32" | "fp16-precast" | "qdq"
        "fp16-precast": any float16 initialiser, or any float16 graph input / output / value type, or a Cast node to
        float16; "qdq": contains QuantizeLinear and DequantizeLinear and is not fp16-precast; "fp32" otherwise.
    prepare_ort_trt_cell(model_path: Path, precision: str) -> dict
        returns {"graph": Path, "provider_options": dict}: fp32 -> the fp32 graph with provider_options
        {"trt_fp16_enable": False}; fp16 -> the fp32 graph with {"trt_fp16_enable": True}; int8 / fp8 -> the QDQ graph
        (provider_options without an fp16 flag set to True). Raises OrtTrtRefused when the graph is "fp16-precast"
        (for any precision), ValueError for a precision outside the four, for fp32 / fp16 given a QDQ graph, and for
        int8 / fp8 given a graph that is not QDQ.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.bench.ort_trt_inputs import OrtTrtRefused, graph_kind, prepare_ort_trt_cell

CODE = "precast-fp16-to-ort-trt"


def _save(model, path: Path) -> Path:
    import onnx

    model.ir_version = 10
    onnx.save(model, path)
    return path


def _fp32(path: Path) -> Path:
    from onnx import TensorProto, helper, numpy_helper

    w = numpy_helper.from_array(np.ones((8, 4), dtype=np.float32), "W")
    nodes = [helper.make_node("MatMul", ["x", "W"], ["m"]), helper.make_node("Relu", ["m"], ["y"])]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 8])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    graph = helper.make_graph(nodes, "g", [x], [y], initializer=[w])
    return _save(helper.make_model(graph, opset_imports=[helper.make_opsetid("", 19)]), path)


def _fp16_initialisers_keep_io(path: Path) -> Path:
    """The ORT converter's output: Cast nodes at the I/O, fp16 initialisers (reference producer)."""
    import onnx
    from onnxruntime.transformers.float16 import convert_float_to_float16

    src = _fp32(path.with_name("src.onnx"))
    return _save(convert_float_to_float16(onnx.load(src), keep_io_types=True), path)


def _fp16_everywhere(path: Path) -> Path:
    from onnx import TensorProto, helper, numpy_helper

    w = numpy_helper.from_array(np.ones((8, 4), dtype=np.float16), "W")
    nodes = [helper.make_node("MatMul", ["x", "W"], ["y"])]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT16, [1, 8])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT16, [1, 4])
    graph = helper.make_graph(nodes, "g16", [x], [y], initializer=[w])
    return _save(helper.make_model(graph, opset_imports=[helper.make_opsetid("", 19)]), path)


def _cast_to_fp16_node_only(path: Path) -> Path:
    """fp32 initialisers and I/O, but the graph casts its activations to float16 in the middle."""
    from onnx import TensorProto, helper, numpy_helper

    w = numpy_helper.from_array(np.ones((8, 4), dtype=np.float16), "W")
    nodes = [
        helper.make_node("Cast", ["x"], ["xh"], to=TensorProto.FLOAT16),
        helper.make_node("MatMul", ["xh", "W"], ["mh"]),
        helper.make_node("Cast", ["mh"], ["y"], to=TensorProto.FLOAT),
    ]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 8])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    graph = helper.make_graph(nodes, "gc", [x], [y], initializer=[w])
    return _save(helper.make_model(graph, opset_imports=[helper.make_opsetid("", 19)]), path)


def _qdq(path: Path) -> Path:
    from onnx import TensorProto, helper, numpy_helper

    inits = [
        numpy_helper.from_array(np.array(0.1, dtype=np.float32), "x_scale"),
        numpy_helper.from_array(np.array(0, dtype=np.int8), "x_zp"),
        numpy_helper.from_array(np.ones((8, 4), dtype=np.int8), "Wq"),
        numpy_helper.from_array(np.array(0.05, dtype=np.float32), "w_scale"),
        numpy_helper.from_array(np.array(0, dtype=np.int8), "w_zp"),
    ]
    nodes = [
        helper.make_node("QuantizeLinear", ["x", "x_scale", "x_zp"], ["xq"]),
        helper.make_node("DequantizeLinear", ["xq", "x_scale", "x_zp"], ["xd"]),
        helper.make_node("DequantizeLinear", ["Wq", "w_scale", "w_zp"], ["Wd"]),
        helper.make_node("MatMul", ["xd", "Wd"], ["y"]),
    ]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 8])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    graph = helper.make_graph(nodes, "gq", [x], [y], initializer=inits)
    return _save(helper.make_model(graph, opset_imports=[helper.make_opsetid("", 19)]), path)


# ----------------------------------------------------------------------------------------------------------------------
# classification
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-25")
def test_graph_kinds_by_hand(tmp_path: Path) -> None:
    assert graph_kind(_fp32(tmp_path / "a.onnx")) == "fp32"
    assert graph_kind(_qdq(tmp_path / "b.onnx")) == "qdq"
    assert graph_kind(_fp16_initialisers_keep_io(tmp_path / "c.onnx")) == "fp16-precast"
    assert graph_kind(_fp16_everywhere(tmp_path / "d.onnx")) == "fp16-precast"
    assert graph_kind(_cast_to_fp16_node_only(tmp_path / "e.onnx")) == "fp16-precast"


# ----------------------------------------------------------------------------------------------------------------------
# refusal and acceptance
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-25")
@pytest.mark.parametrize("make", [_fp16_initialisers_keep_io, _fp16_everywhere, _cast_to_fp16_node_only])
@pytest.mark.parametrize("precision", ["fp32", "fp16", "int8", "fp8"])
def test_a_precast_fp16_graph_is_refused_for_every_precision(make, precision: str, tmp_path: Path) -> None:
    graph = make(tmp_path / "g.onnx")
    with pytest.raises(OrtTrtRefused) as info:
        prepare_ort_trt_cell(graph, precision)
    assert info.value.code == CODE
    assert CODE in str(info.value)


@pytest.mark.req("FR-016-25")
def test_the_fp32_graph_is_accepted_for_the_fp32_cell_with_the_fp16_flag_off(tmp_path: Path) -> None:
    graph = _fp32(tmp_path / "a.onnx")
    cell = prepare_ort_trt_cell(graph, "fp32")
    assert cell["graph"] == graph
    assert cell["provider_options"]["trt_fp16_enable"] is False


@pytest.mark.req("FR-016-25")
def test_the_fp16_cell_receives_the_fp32_graph_with_the_provider_fp16_flag(tmp_path: Path) -> None:
    graph = _fp32(tmp_path / "a.onnx")
    cell = prepare_ort_trt_cell(graph, "fp16")
    assert cell["graph"] == graph
    assert cell["provider_options"]["trt_fp16_enable"] is True


@pytest.mark.req("FR-016-25")
@pytest.mark.parametrize("precision", ["int8", "fp8"])
def test_reduced_precision_cells_receive_qdq_graphs(precision: str, tmp_path: Path) -> None:
    graph = _qdq(tmp_path / "q.onnx")
    cell = prepare_ort_trt_cell(graph, precision)
    assert cell["graph"] == graph
    assert cell["provider_options"].get("trt_fp16_enable") is not True


@pytest.mark.req("FR-016-25")
def test_graph_and_precision_mismatches_are_refused_with_value_error(tmp_path: Path) -> None:
    fp32, qdq = _fp32(tmp_path / "a.onnx"), _qdq(tmp_path / "q.onnx")
    with pytest.raises(ValueError, match=r"qdq|QDQ"):
        prepare_ort_trt_cell(qdq, "fp32")
    with pytest.raises(ValueError, match=r"qdq|QDQ"):
        prepare_ort_trt_cell(qdq, "fp16")
    with pytest.raises(ValueError, match=r"qdq|QDQ"):
        prepare_ort_trt_cell(fp32, "int8")
    for bad in ("bf16", "int4", "", "FP16"):
        with pytest.raises(ValueError, match="precision"):
            prepare_ort_trt_cell(fp32, bad)
