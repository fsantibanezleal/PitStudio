"""A tiny Conv → ReLU → GlobalAveragePool ONNX graph with seeded weights, built with onnx.helper (no exporter needed).

Shared by the torch/ONNX Runtime and TensorRT probes so both check numerical parity on the same model and input.
"""

from __future__ import annotations

from typing import Any

BATCH, CH_IN, CH_OUT, SIZE = 4, 3, 16, 224
IR_VERSION = 10


def tiny_conv() -> tuple[bytes, dict[str, Any]]:
    """Return (serialized model, arrays) where arrays holds x, w, b as float32 numpy arrays."""
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    w = (rng.standard_normal((CH_OUT, CH_IN, 3, 3)) * 0.2).astype(np.float32)
    b = (rng.standard_normal(CH_OUT) * 0.1).astype(np.float32)
    x = rng.standard_normal((BATCH, CH_IN, SIZE, SIZE)).astype(np.float32)
    graph = helper.make_graph(
        [
            helper.make_node("Conv", ["x", "w", "b"], ["c"], pads=[1, 1, 1, 1]),
            helper.make_node("Relu", ["c"], ["r"]),
            helper.make_node("GlobalAveragePool", ["r"], ["y"]),
        ],
        "pitstudio_probe",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [BATCH, CH_IN, SIZE, SIZE])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [BATCH, CH_OUT, 1, 1])],
        initializer=[numpy_helper.from_array(w, "w"), numpy_helper.from_array(b, "b")],
    )
    # onnx writes its newest IR (14) by default; ONNX Runtime 1.30 reads <= 13 and TensorRT's parser less
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=IR_VERSION)
    onnx.checker.check_model(model)
    return model.SerializeToString(), {"x": x, "w": w, "b": b}
