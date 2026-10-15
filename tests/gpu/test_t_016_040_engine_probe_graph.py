"""T-016-040 (GPU): a real TensorRT 11.3 engine of the probe graph matches ONNX Runtime CPU (gpu).

Requirements: FR-016-20.

Spec: specs/016-export-acceleration/spec.md FR-016-20 (strongly typed TensorRT 11.3 engine built with Polygraphy after
pointing `CUDA_PATH` and the DLL search path at the CUDA 13 runtime wheel; engine SHA-256, TensorRT version, builder
configuration and build time recorded); plan.md test strategy row FR-016-20 (analytical: the probe-graph engine matches
ONNX Runtime CPU within 1e-4).

Marked `gpu`: not run in CI and not run by the red author (the GPU belongs to the scheduled jobs, FR-000-18 / FR-000-19
evidence record). Run later in the `pipeline/accel/` environment (TensorRT 11.3.0.99 cu13 libs and bindings, Polygraphy,
nvidia-cuda-runtime 13, onnxruntime-gpu), with `pitstudio` installed editable in that environment.

Oracles: ONNX Runtime CPU on the same probe graph (reference implementation, the graph is a Conv -> ReLU ->
GlobalAveragePool fixture built here with `onnx.helper`; IR version 10, opset 19), and the plan's bound 1e-4 on the
maximum absolute difference for fp32 with TF32 cleared.

Expected public API of the implementation (module `pitstudio_accel.trt`, `pipeline/accel/`):
    class TensorRTBackend                    # satisfies the EngineBackend protocol of pitstudio.accel.engines
        version: str                         # "11.3.x.y"
        build(onnx_path, *, precision, profile, flags, out_path) -> None
        load(engine_path: Path) -> Engine    # Engine.infer(x: np.ndarray) -> list[np.ndarray]
    resolve_cuda13_runtime() -> Path         # the nvidia-cuda-runtime 13 wheel folder (site-packages/nvidia/...)
The orchestration is `pitstudio.accel.engines.build_engines` (see tests/unit/test_t_016_040_engine_builds.py).
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from pitstudio.accel.engines import build_engines, configure_cuda_env
from pitstudio_accel.trt import TensorRTBackend, resolve_cuda13_runtime

pytestmark = pytest.mark.gpu


class _Clock:
    def monotonic(self) -> float:
        import time

        return time.monotonic()


def _probe_graph(path: Path) -> Path:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    w = numpy_helper.from_array(rng.standard_normal((4, 3, 3, 3)).astype(np.float32), "W")
    b = numpy_helper.from_array(rng.standard_normal(4).astype(np.float32), "b")
    nodes = [
        helper.make_node("Conv", ["x", "W", "b"], ["c"], pads=[1, 1, 1, 1]),
        helper.make_node("Relu", ["c"], ["r"]),
        helper.make_node("GlobalAveragePool", ["r"], ["y"]),
    ]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, ["N", 3, 16, 16])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, ["N", 4, 1, 1])
    model = helper.make_model(
        helper.make_graph(nodes, "probe", [x], [y], initializer=[w, b]), opset_imports=[helper.make_opsetid("", 19)]
    )
    model.ir_version = 10
    onnx.save(model, path)
    return path


@pytest.mark.req("FR-016-20")
def test_probe_graph_engine_matches_onnx_runtime_cpu_within_1e_minus_4(tmp_path: Path) -> None:
    import onnxruntime as ort

    runtime = resolve_cuda13_runtime()
    cuda = configure_cuda_env(os.environ, runtime)
    os.environ.update(cuda.env)
    onnx_path = _probe_graph(tmp_path / "probe.onnx")
    variant = {
        "model": "probe",
        "precision": "fp32",
        "onnx": onnx_path,
        "config": {"opset": 19, "gemm_heavy": False},
        "batch_sizes": (1, 4, 16, 64),
    }
    backend = TensorRTBackend()
    (record,) = build_engines([variant], backend, run_dir=tmp_path / "run", clock=_Clock(), onnx_guard=lambda _p: None)
    assert record.status == "built"
    assert record.tensorrt_version.startswith("11.3")
    assert record.builder_config["tf32"] is False
    engine = backend.load(Path(record.engine_path))
    x = np.random.default_rng(1).standard_normal((4, 3, 16, 16)).astype(np.float32)
    got = engine.infer(x)[0]
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    want = sess.run(None, {"x": x})[0]
    assert got.shape == want.shape
    assert float(np.max(np.abs(got - want))) <= 1e-4
