"""T-016-020: fp16 / int8 / fp8 variants, the layer-2 gate and hostile precision requests (unit, hostile).

Requirements: FR-016-08, FR-016-09, FR-016-10.

Spec: specs/016-export-acceleration/spec.md
- FR-016-08: fp16 with ONNX Runtime's `float16.convert_float_to_float16(keep_io_types=True)` with LayerNormalization,
  Softmax, ReduceMean, ReduceSum and ReduceMax kept in fp32; int8 and fp8 with ONNX Runtime's `quantize_static` in QDQ
  format (QInt8 or QFLOAT8E4M3FN), per-channel weights, per-tensor activations, calibrated on 500 seeded training inputs
  disjoint from the golden and evaluation sets;
- FR-016-09: accept a reduced-precision variant only if |metric_variant - metric_fp32| <= 1 percentage point and, for
  mask outputs, mean mask IoU >= 0.99 (and, for detectors, the spec 009 robustness criterion holds); every other variant
  is `rejected` with its numbers and reason;
- FR-016-10: a precision outside {fp32, fp16, int8, fp8}, or fp8 for a graph below opset 19 or not flagged
  `gemm_heavy`, is refused with the reason by `s60_export` and `s62_accel`.
plan.md test strategy rows FR-016-08 (structure: blocked op types stay fp32, weight DequantizeLinear nodes carry an
`axis`, calibration and golden sets disjoint), FR-016-09 (delta 0.99 / 1.01 pp; mask IoU 0.990 / 0.989), FR-016-10
(bf16, fp8 at opset 17, fp8 on a CNN).

Oracles:
- hand-built ONNX graphs (`onnx.helper`) and the structural facts of the ONNX operator specification: tensor element
  types read back with `onnx.shape_inference`, `DequantizeLinear` per-channel `axis`, zero-point element types
  (INT8 = 3, FLOAT8E4M3FN = 17, FLOAT16 = 10, FLOAT = 1), and ONNX Runtime CPU running the fp16 graph against the fp32
  graph (fp16 round-off bound 1e-2 on unit-scale outputs);
- thresholds from `specs/000-foundation/thresholds.yaml` (`models.quantized_task_metric_delta_max_pp` = 1.0,
  `models.mask_iou_min_vs_fp32` = 0.99);
- dyadic percentages so that the 1 pp boundary is exact (50.0 vs 51.0).

Expected public API (`pipeline/` environment):
module `pitstudio.export.variant_rules`            (root, pure Python)
    class VariantRefused(Exception)                # `.reason: str`
    check_variant_request(precision: str, *, opset: int, gemm_heavy: bool) -> None
        accepts exactly the strings fp32, fp16, int8, fp8; fp8 only with opset >= 19 and gemm_heavy true; raises
        VariantRefused otherwise (the reason names the precision or the failing condition).
module `pitstudio_pipeline.export.precision`
    class PrecisionError(Exception)                # `.reason: str`
    make_variant(onnx_path: Path, out_path: Path, precision: str, *, config: dict,
                 calibration_inputs: Sequence[np.ndarray] | None = None, golden_digests: Collection[str] = (),
                 eval_digests: Collection[str] = ()) -> Path
        fp32 returns `onnx_path`; fp16 writes the ORT-converted graph; int8 / fp8 write the QDQ graph. Calls
        `check_variant_request` first (VariantRefused propagates). For int8 / fp8 `calibration_inputs` must hold exactly
        500 arrays whose SHA-256 (raw C-contiguous bytes) is in neither `golden_digests` nor `eval_digests`, else
        PrecisionError (reason contains "calibration").
    select_calibration_inputs(pool: Sequence[Mapping[str, str]], *, golden_digests: Collection[str],
                              eval_digests: Collection[str], n: int = 500, seed: int) -> list[str]
        `pool` items {"sha256", "split"}; returns n unique digests of split "train" items, seeded
        (numpy default_rng(seed)), none in the golden or evaluation digests; PrecisionError when fewer than n eligible.
    layer2_gate(*, metric_fp32: float, metric_variant: float, mask_iou: float | None = None,
                requires_mask_iou: bool = False, requires_robustness: bool = False,
                robustness_ok: bool | None = None) -> GateResult
        GateResult: verdict "pass" | "rejected", reason: str | None (None iff pass), delta_pp: float
        (= metric_variant - metric_fp32), mask_iou: float | None. A non-finite metric or IoU must not give "pass".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import yaml
from pitstudio.export.variant_rules import VariantRefused, check_variant_request
from pitstudio_pipeline.export.precision import (
    PrecisionError,
    layer2_gate,
    make_variant,
    select_calibration_inputs,
)

ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "models"
]
FLOAT, INT8, FLOAT16, FLOAT8E4M3FN = 1, 3, 10, 17
BLOCKED = {"LayerNormalization", "Softmax", "ReduceMean", "ReduceSum", "ReduceMax"}


def _digest(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def _config(**over: object) -> dict:
    import json

    cfg = json.loads(
        (ROOT / "specs/016-export-acceleration/contracts/examples/export-config.valid.json").read_text(encoding="utf-8")
    )
    cfg.update(over)
    return cfg


def _blocked_ops_model(path: Path) -> Path:
    """x -> MatMul(W) -> LayerNormalization -> Softmax -> ReduceMean -> ReduceMax -> y   (opset 17, fp32)."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    w = numpy_helper.from_array(rng.standard_normal((8, 8)).astype(np.float32) * 0.5, "W")
    scale = numpy_helper.from_array(np.ones(8, dtype=np.float32), "ln_scale")
    bias = numpy_helper.from_array(np.zeros(8, dtype=np.float32), "ln_bias")
    nodes = [
        helper.make_node("MatMul", ["x", "W"], ["m"]),
        helper.make_node("LayerNormalization", ["m", "ln_scale", "ln_bias"], ["n"], axis=-1),
        helper.make_node("Softmax", ["n"], ["s"], axis=-1),
        helper.make_node("ReduceMean", ["s"], ["r"], axes=[1], keepdims=1),
        helper.make_node("ReduceMax", ["r"], ["y"], axes=[0], keepdims=1),
    ]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 8])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1])
    graph = helper.make_graph(nodes, "blocked", [x], [y], initializer=[w, scale, bias])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 10
    onnx.save(model, path)
    return path


def _conv_model(path: Path, opset: int = 17) -> Path:
    """x[1,3,8,8] -> Conv(W[4,3,3,3], b) -> Relu -> y   (fp32)."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(3)
    w = numpy_helper.from_array(rng.standard_normal((4, 3, 3, 3)).astype(np.float32), "W")
    b = numpy_helper.from_array(rng.standard_normal(4).astype(np.float32), "b")
    nodes = [
        helper.make_node("Conv", ["x", "W", "b"], ["c"], pads=[1, 1, 1, 1]),
        helper.make_node("Relu", ["c"], ["y"]),
    ]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 3, 8, 8])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4, 8, 8])
    model = helper.make_model(
        helper.make_graph(nodes, "conv", [x], [y], initializer=[w, b]), opset_imports=[helper.make_opsetid("", opset)]
    )
    model.ir_version = 10
    onnx.save(model, path)
    return path


def _matmul_model(path: Path, opset: int = 19) -> Path:
    """x[1,8] -> MatMul(W[8,4]) -> Relu -> y   (fp32; the GEMM-heavy shape that fp8 targets)."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(4)
    w = numpy_helper.from_array(rng.standard_normal((8, 4)).astype(np.float32), "W")
    nodes = [helper.make_node("MatMul", ["x", "W"], ["m"]), helper.make_node("Relu", ["m"], ["y"])]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 8])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    model = helper.make_model(
        helper.make_graph(nodes, "mm", [x], [y], initializer=[w]), opset_imports=[helper.make_opsetid("", opset)]
    )
    model.ir_version = 10
    onnx.save(model, path)
    return path


def _calibration(n: int = 500, shape: tuple[int, ...] = (1, 3, 8, 8)) -> list[np.ndarray]:
    rng = np.random.default_rng(5)
    return [rng.standard_normal(shape).astype(np.float32) for _ in range(n)]


def _elem_types(model) -> dict[str, int]:
    import onnx

    inferred = onnx.shape_inference.infer_shapes(model)
    types = {v.name: v.type.tensor_type.elem_type for v in [*inferred.graph.value_info, *inferred.graph.input]}
    types.update({v.name: v.type.tensor_type.elem_type for v in inferred.graph.output})
    types.update({t.name: t.data_type for t in inferred.graph.initializer})
    return types


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-08: fp16
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-08")
def test_fp16_keeps_io_fp32_converts_weights_and_keeps_the_blocked_op_types_in_fp32(tmp_path: Path) -> None:
    import onnx

    src = _blocked_ops_model(tmp_path / "m.onnx")
    out = make_variant(src, tmp_path / "m16.onnx", "fp16", config=_config(opset=17))
    model = onnx.load(out)
    onnx.checker.check_model(model, full_check=True)
    types = _elem_types(model)
    assert [types[i.name] for i in model.graph.input] == [FLOAT]  # keep_io_types
    assert [types[o.name] for o in model.graph.output] == [FLOAT]
    blocked = [n for n in model.graph.node if n.op_type in BLOCKED]
    assert {n.op_type for n in blocked} == {"LayerNormalization", "Softmax", "ReduceMean", "ReduceMax"}
    for node in blocked:
        for name in [*node.input, *node.output]:
            assert types[name] == FLOAT, f"{node.op_type} tensor {name} is not fp32"
    matmul = next(n for n in model.graph.node if n.op_type == "MatMul")
    assert [types[name] for name in matmul.input] == [FLOAT16, FLOAT16]  # computed in half precision


@pytest.mark.req("FR-016-08")
def test_fp16_graph_runs_on_ort_cpu_and_stays_close_to_fp32(tmp_path: Path) -> None:
    import onnxruntime as ort

    src = _blocked_ops_model(tmp_path / "m.onnx")
    out = make_variant(src, tmp_path / "m16.onnx", "fp16", config=_config(opset=17))
    x = np.random.default_rng(9).standard_normal((1, 8)).astype(np.float32)
    ref = ort.InferenceSession(str(src), providers=["CPUExecutionProvider"])
    var = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    want = ref.run(None, {"x": x})[0]
    got = var.run(None, {"x": x})[0]
    assert got.dtype == np.float32
    np.testing.assert_allclose(got, want, rtol=1e-2, atol=1e-2)


@pytest.mark.req("FR-016-08")
def test_fp32_request_returns_the_exported_graph_unchanged(tmp_path: Path) -> None:
    src = _blocked_ops_model(tmp_path / "m.onnx")
    assert make_variant(src, tmp_path / "unused.onnx", "fp32", config=_config(opset=17)) == src


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-08: int8 / fp8 QDQ
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-08")
def test_int8_is_a_qdq_graph_with_per_channel_weights_and_per_tensor_activations(tmp_path: Path) -> None:
    import onnx
    from onnx import numpy_helper

    src = _conv_model(tmp_path / "c.onnx")
    out = make_variant(
        src, tmp_path / "c8.onnx", "int8", config=_config(opset=17), calibration_inputs=_calibration(500)
    )
    model = onnx.load(out)
    onnx.checker.check_model(model, full_check=True)
    ops = [n.op_type for n in model.graph.node]
    assert "QuantizeLinear" in ops
    assert "DequantizeLinear" in ops
    assert "QLinearConv" not in ops  # QDQ format, not the operator-oriented format
    inits = {t.name: t for t in model.graph.initializer}
    weight_dq = [n for n in model.graph.node if n.op_type == "DequantizeLinear" and inits.get(n.input[0]) is not None]
    per_channel = [n for n in weight_dq if list(inits[n.input[0]].dims) == [4, 3, 3, 3]]
    assert len(per_channel) == 1
    node = per_channel[0]
    assert any(a.name == "axis" and a.i == 0 for a in node.attribute)  # output-channel axis
    assert inits[node.input[0]].data_type == INT8
    assert list(inits[node.input[1]].dims) == [4]  # one scale per output channel
    act_dq = [n for n in model.graph.node if n.op_type == "DequantizeLinear" and n.input[0] not in inits]
    assert act_dq, "activations must be quantised too"
    for n in act_dq:
        scale = numpy_helper.to_array(inits[n.input[1]])
        assert scale.shape == ()  # per-tensor: a scalar scale


@pytest.mark.req("FR-016-08")
def test_int8_qdq_graph_runs_on_ort_cpu_close_to_fp32(tmp_path: Path) -> None:
    import onnxruntime as ort

    src = _conv_model(tmp_path / "c.onnx")
    out = make_variant(
        src, tmp_path / "c8.onnx", "int8", config=_config(opset=17), calibration_inputs=_calibration(500)
    )
    x = _calibration(1)[0]
    want = ort.InferenceSession(str(src), providers=["CPUExecutionProvider"]).run(None, {"x": x})[0]
    got = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"]).run(None, {"x": x})[0]
    scale = float(np.abs(want).max())
    assert float(np.abs(got - want).max()) <= 0.1 * scale  # 8-bit round-off bound on a one-layer network


@pytest.mark.req("FR-016-08")
def test_fp8_uses_float8e4m3fn_qdq_with_per_channel_weights(tmp_path: Path) -> None:
    import onnx

    src = _matmul_model(tmp_path / "c.onnx", opset=19)
    out = make_variant(
        src,
        tmp_path / "c_fp8.onnx",
        "fp8",
        config=_config(opset=19, gemm_heavy=True),
        calibration_inputs=_calibration(500, (1, 8)),
    )
    model = onnx.load(out)
    inits = {t.name: t for t in model.graph.initializer}
    assert any(t.data_type == FLOAT8E4M3FN for t in inits.values())
    assert {n.op_type for n in model.graph.node} >= {"QuantizeLinear", "DequantizeLinear"}
    weight_dq = [n for n in model.graph.node if n.op_type == "DequantizeLinear" and n.input[0] in inits]
    assert weight_dq
    assert all(any(a.name == "axis" for a in n.attribute) for n in weight_dq)  # per-channel weights


@pytest.mark.req("FR-016-08")
def test_calibration_set_overlapping_the_golden_set_is_refused(tmp_path: Path) -> None:
    src = _conv_model(tmp_path / "c.onnx")
    calib = _calibration(500)
    golden = {_digest(calib[123])}
    with pytest.raises(PrecisionError) as info:
        make_variant(
            src,
            tmp_path / "c8.onnx",
            "int8",
            config=_config(opset=17),
            calibration_inputs=calib,
            golden_digests=golden,
        )
    assert "calibration" in info.value.reason
    with pytest.raises(PrecisionError):
        make_variant(
            src,
            tmp_path / "c8.onnx",
            "int8",
            config=_config(opset=17),
            calibration_inputs=calib,
            eval_digests={_digest(calib[0])},
        )
    assert not (tmp_path / "c8.onnx").exists()


@pytest.mark.req("FR-016-08")
@pytest.mark.parametrize("n", [0, 499, 501])
def test_calibration_must_hold_exactly_500_inputs(tmp_path: Path, n: int) -> None:
    src = _conv_model(tmp_path / "c.onnx")
    with pytest.raises(PrecisionError) as info:
        make_variant(src, tmp_path / "c8.onnx", "int8", config=_config(opset=17), calibration_inputs=_calibration(n))
    assert "calibration" in info.value.reason


@pytest.mark.req("FR-016-08")
def test_int8_without_any_calibration_inputs_is_refused(tmp_path: Path) -> None:
    src = _conv_model(tmp_path / "c.onnx")
    with pytest.raises(PrecisionError):
        make_variant(src, tmp_path / "c8.onnx", "int8", config=_config(opset=17), calibration_inputs=None)


@pytest.mark.req("FR-016-08")
def test_calibration_selection_is_seeded_disjoint_from_golden_and_evaluation_and_from_training_only() -> None:
    def digest(i: int) -> str:
        return hashlib.sha256(f"s{i}".encode()).hexdigest()

    pool = [{"sha256": digest(i), "split": "train"} for i in range(1500)]
    pool += [{"sha256": digest(1500 + i), "split": "validation"} for i in range(300)]
    golden = {digest(i) for i in range(0, 200)}  # golden items that (by accident) sit in the training range
    evals = {digest(i) for i in range(200, 400)}
    chosen = select_calibration_inputs(pool, golden_digests=golden, eval_digests=evals, n=500, seed=4)
    assert len(chosen) == 500
    assert len(set(chosen)) == 500
    assert not set(chosen) & golden
    assert not set(chosen) & evals
    assert set(chosen) <= {p["sha256"] for p in pool if p["split"] == "train"}
    assert chosen == select_calibration_inputs(pool, golden_digests=golden, eval_digests=evals, n=500, seed=4)
    assert set(chosen) != set(select_calibration_inputs(pool, golden_digests=golden, eval_digests=evals, n=500, seed=5))
    with pytest.raises(PrecisionError):
        select_calibration_inputs(pool[:600], golden_digests=golden, eval_digests=evals, n=500, seed=4)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-09: the layer-2 gate
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-09")
def test_thresholds_used_by_the_gate_are_the_pre_registered_ones() -> None:
    assert THRESHOLDS["quantized_task_metric_delta_max_pp"] == 1.0
    assert THRESHOLDS["mask_iou_min_vs_fp32"] == 0.99


@pytest.mark.req("FR-016-09")
@pytest.mark.parametrize(
    ("variant", "verdict"),
    [(50.99, "pass"), (49.01, "pass"), (51.0, "pass"), (49.0, "pass"), (51.01, "rejected"), (48.99, "rejected")],
)
def test_task_metric_change_of_at_most_one_percentage_point_in_either_direction_is_accepted(
    variant: float, verdict: str
) -> None:
    r = layer2_gate(metric_fp32=50.0, metric_variant=variant)
    assert r.verdict == verdict
    assert r.delta_pp == pytest.approx(variant - 50.0, abs=1e-12)
    assert (r.reason is None) == (verdict == "pass")


@pytest.mark.req("FR-016-09")
def test_a_rejected_variant_carries_its_numbers_and_a_reason() -> None:
    r = layer2_gate(metric_fp32=70.0, metric_variant=68.5)
    assert r.verdict == "rejected"
    assert r.delta_pp == pytest.approx(-1.5)
    assert r.reason
    assert "1.5" in r.reason or "-1.5" in r.reason


@pytest.mark.req("FR-016-09")
@pytest.mark.parametrize(("iou", "verdict"), [(0.990, "pass"), (0.989, "rejected"), (1.0, "pass"), (0.5, "rejected")])
def test_mask_outputs_need_a_mean_iou_of_at_least_099(iou: float, verdict: str) -> None:
    r = layer2_gate(metric_fp32=80.0, metric_variant=80.0, mask_iou=iou, requires_mask_iou=True)
    assert r.verdict == verdict
    assert r.mask_iou == iou


@pytest.mark.req("FR-016-09")
def test_a_mask_output_without_a_measured_iou_is_rejected() -> None:
    r = layer2_gate(metric_fp32=80.0, metric_variant=80.0, mask_iou=None, requires_mask_iou=True)
    assert r.verdict == "rejected"
    assert r.reason


@pytest.mark.req("FR-016-09")
def test_detector_robustness_criterion_must_hold() -> None:
    ok = layer2_gate(metric_fp32=60.0, metric_variant=60.2, requires_robustness=True, robustness_ok=True)
    bad = layer2_gate(metric_fp32=60.0, metric_variant=60.2, requires_robustness=True, robustness_ok=False)
    missing = layer2_gate(metric_fp32=60.0, metric_variant=60.2, requires_robustness=True, robustness_ok=None)
    assert ok.verdict == "pass"
    assert bad.verdict == "rejected"
    assert missing.verdict == "rejected"  # not evaluated is not accepted


@pytest.mark.req("FR-016-09")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_metrics_are_never_accepted(bad: float) -> None:
    for fp32, var in ((50.0, bad), (bad, 50.0)):
        try:
            verdict = layer2_gate(metric_fp32=fp32, metric_variant=var).verdict
        except ValueError:
            continue
        assert verdict != "pass"


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-10: hostile precision requests
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-10")
@pytest.mark.parametrize("opset", [17, 18, 19])
@pytest.mark.parametrize("precision", ["fp32", "fp16", "int8"])
def test_fp32_fp16_int8_are_accepted_at_every_allowed_opset(precision: str, opset: int) -> None:
    assert check_variant_request(precision, opset=opset, gemm_heavy=False) is None


@pytest.mark.req("FR-016-10")
@pytest.mark.parametrize(
    "precision", ["bf16", "int4", "fp4", "tf32", "FP16", "Int8", "fp8 ", "", "fp64", "float16", "Ã©"]
)
def test_a_precision_outside_the_four_is_refused(precision: str) -> None:
    with pytest.raises(VariantRefused) as info:
        check_variant_request(precision, opset=19, gemm_heavy=True)
    assert info.value.reason


@pytest.mark.req("FR-016-10")
@pytest.mark.parametrize("opset", [17, 18])
def test_fp8_below_opset_19_is_refused(opset: int) -> None:
    with pytest.raises(VariantRefused) as info:
        check_variant_request("fp8", opset=opset, gemm_heavy=True)
    assert "opset" in info.value.reason


@pytest.mark.req("FR-016-10")
def test_fp8_on_a_graph_not_flagged_gemm_heavy_is_refused() -> None:
    with pytest.raises(VariantRefused) as info:
        check_variant_request("fp8", opset=19, gemm_heavy=False)
    assert "gemm_heavy" in info.value.reason
    assert check_variant_request("fp8", opset=19, gemm_heavy=True) is None


@pytest.mark.req("FR-016-10")
def test_make_variant_refuses_hostile_requests_before_writing_anything(tmp_path: Path) -> None:
    src = _conv_model(tmp_path / "c.onnx")
    for precision, cfg in (
        ("bf16", _config(opset=19, gemm_heavy=True)),
        ("fp8", _config(opset=17, gemm_heavy=True)),
        ("fp8", _config(opset=19, gemm_heavy=False)),
    ):
        with pytest.raises(VariantRefused):
            make_variant(src, tmp_path / "v.onnx", precision, config=cfg, calibration_inputs=_calibration(500))
        assert not (tmp_path / "v.onnx").exists()
