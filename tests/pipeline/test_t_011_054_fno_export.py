"""T-011-054 - FR-011-36, FR-011-37, SC-011-04, NFR-011-03: FNO export, operator whitelist, parity, fp16 rule.

Oracles (independent of the code under test; plan 011 test strategy FR-011-36 / FR-011-37):
- ONNX graph inspection with the reference implementation `onnx`: opset import of the default domain (19), IR
    version (10), the
  operator list of the exported graph against the whitelist written in spec section 7 (MatMul, Add, Sub, Mul, Div,
      Erf, Reshape,
  Transpose, Concat, Slice, Gather, Unsqueeze, Squeeze, Constant, Identity, Cast), no DFT, no Einsum, no
      complex-typed tensor;
- hand-made graphs for the verifier (built here with onnx.helper): a graph with an Einsum node, a DFT node, a Relu
    node (a legal
  operator that is not on the whitelist), a Gemm node, a complex64 value, must each be refused with the operator
      named; a MatMul + Add
  graph is accepted;
- the DC-011-02 draft schema (jsonschema): the description of the exported FNO validates, carries opset 19, IR 10,
    the channel order
  and units of the example `surrogate-io.valid-fno.json`, the input shape [1, 5, 64, 64] and the output shape [1,
      9, 64, 64] and names,
  dtypes and shapes equal those of the graph; `onnx.sha256` and `onnx.bytes` equal hashlib and the file size;
- ONNX Runtime CPU against PyTorch fp32 on the golden fields (tolerances `models.onnx_cpu_fp32` of
    thresholds.yaml), recomputed here,
  and a perturbed graph (a bias shifted by 0.05) that must fail;
- the fp16 rule of FR-011-37 by hand (`models.quantized_task_metric_delta_max_pp` = 1.0): every field's mean
    relative L2 changes by
  <= 1 percentage point, else fp32; exactly 1.0 passes, 1.0001 fails, NaN fails, no evidence fails;
- NFR-011-03 by hand: 2.36 x 10^6 parameters x 2 bytes = 4.7 MB at fp16 (spec "about 5 MB"), well below 25 x 10^6 bytes.

Expected public API (module `pitstudio_pipeline.surrogates.fno.export`, package under `pipeline/src/`; errors in
`pitstudio_pipeline.surrogates.errors`):

    OPERATOR_WHITELIST: frozenset[str]            the 16 operators above
    verify_graph(path) -> None                    raises ExportError naming the operator or tensor type for any
        DFT, Einsum, complex-typed
                                                  tensor or operator outside the whitelist; returns None for a
                                                      conforming graph
    export_fno(model, out_dir, *, model_id, inputs, outputs, envelope, cases=("C2",)) -> FnoExport
        model: an `FnoModel`; inputs / outputs: the `channels` lists of the DC-011-02 tensors (name, unit, optional
            normalisation);
        envelope: the training_envelope object (>= 1 range). Writes `<model_id>-fp32.onnx` and
            `<model_id>-fp16.onnx` (opset 19, IR 10,
        input `fields` [1, C_in, 64, 64], output `depth` [1, C_out, 64, 64] float32 at the interface), runs
            verify_graph on both, and
        returns FnoExport(paths {"fp32", "fp16"}, io {"fp32", "fp16"} DC-011-02 documents, model_id). Raises
            TypeError for a non-FnoModel,
        ValueError for an empty envelope, an invalid slug model_id or channel lists whose length differs from the
            model's channels.
    check_parity(model, onnx_path, *, n_golden=200, seed=0) -> ParityReport     as in
        tests/pipeline/test_t_011_016_gns_parity.py
        (attributes passed, n_golden, max_abs, max_rel, tolerances, worst_step) on n_golden random [1, C_in, 64,
            64] fields;
        ValueError for n_golden < 200.
    choose_live_precision(delta_pp: dict[str, float]) -> str     "fp16" iff non-empty and every |delta| finite and
        <= 1.0 percentage point
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

torch = pytest.importorskip("torch")
onnx = pytest.importorskip("onnx")
ort = pytest.importorskip("onnxruntime")
jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.errors import ExportError  # noqa: E402
from pitstudio_pipeline.surrogates.fno import export  # noqa: E402
from pitstudio_pipeline.surrogates.fno.model import FnoModel  # noqa: E402

CONTRACTS = ROOT / "specs" / "011-surrogates" / "contracts"
VALIDATOR = jsonschema.Draft202012Validator(
    json.loads((CONTRACTS / "surrogate-io.schema.json").read_text(encoding="utf-8"))
)
EXAMPLE = json.loads((CONTRACTS / "examples" / "surrogate-io.valid-fno.json").read_text(encoding="utf-8"))
MODELS = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))["models"]
TOL = MODELS["onnx_cpu_fp32"]
FP16_PP = MODELS["quantized_task_metric_delta_max_pp"]
WHITELIST = {
    "MatMul",
    "Add",
    "Sub",
    "Mul",
    "Div",
    "Erf",
    "Reshape",
    "Transpose",
    "Concat",
    "Slice",
    "Gather",
    "Unsqueeze",
    "Squeeze",
    "Constant",
    "Identity",
    "Cast",
}
IN_CHANNELS = EXAMPLE["inputs"][0]["channels"]
OUT_CHANNELS = EXAMPLE["outputs"][0]["channels"]
ELEM = {onnx.TensorProto.FLOAT: "float32", onnx.TensorProto.FLOAT16: "float16"}


def small_model(seed: int = 0) -> FnoModel:
    torch.manual_seed(seed)
    return FnoModel(5, 9, width=8, layers=2).eval()


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    model = small_model()
    out = tmp_path_factory.mktemp("fno_export") / "models"
    res = export.export_fno(
        model, out, model_id="fno-test", inputs=IN_CHANNELS, outputs=OUT_CHANNELS, envelope=EXAMPLE["training_envelope"]
    )
    return model, res, out


def ops(m) -> set[str]:
    return {n.op_type for n in m.graph.node}


def default_opset(m) -> int:
    return next(o.version for o in m.opset_import if o.domain in ("", "ai.onnx"))


# ------------------------------------------------------------------ FR-011-36 graph structure


@pytest.mark.req("FR-011-36")
def test_the_whitelist_is_the_spec_section_7_list() -> None:
    assert set(export.OPERATOR_WHITELIST) == WHITELIST


@pytest.mark.req("FR-011-36")
@pytest.mark.parametrize("key", ["fp32", "fp16"])
def test_every_exported_graph_has_opset_19_ir_version_10_and_passes_the_onnx_checker(exported, key: str) -> None:
    _, res, _ = exported
    m = onnx.load(str(res.paths[key]))
    assert default_opset(m) == 19
    assert m.ir_version == 10
    onnx.checker.check_model(m)


@pytest.mark.req("FR-011-36")
@pytest.mark.parametrize("key", ["fp32", "fp16"])
def test_the_graph_contains_only_whitelisted_operators_and_no_dft_einsum_or_complex_tensor(exported, key: str) -> None:
    _, res, _ = exported
    m = onnx.load(str(res.paths[key]))
    types = ops(m)
    assert types <= WHITELIST, sorted(types - WHITELIST)
    assert "MatMul" in types
    assert "Einsum" not in types
    assert "DFT" not in types
    complex_types = {onnx.TensorProto.COMPLEX64, onnx.TensorProto.COMPLEX128}
    assert not any(i.data_type in complex_types for i in m.graph.initializer)
    for vi in list(m.graph.input) + list(m.graph.output) + list(m.graph.value_info):
        assert vi.type.tensor_type.elem_type not in complex_types
    for node in m.graph.node:
        for attr in node.attribute:
            if attr.type == onnx.AttributeProto.TENSOR:
                assert attr.t.data_type not in complex_types


@pytest.mark.req("FR-011-36")
@pytest.mark.parametrize("key", ["fp32", "fp16"])
def test_the_verifier_accepts_the_exported_graph(exported, key: str) -> None:
    _, res, _ = exported
    assert export.verify_graph(res.paths[key]) is None


def handmade(tmp_path: Path, nodes, *, name: str, extra_value_info=None, initializers=None) -> Path:
    from onnx import TensorProto, helper

    x = helper.make_tensor_value_info("X", TensorProto.FLOAT, [4, 4])
    y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [4, 4])
    graph = helper.make_graph(nodes, name, [x], [y], initializer=initializers or [], value_info=extra_value_info or [])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 19)])
    model.ir_version = 10
    path = tmp_path / f"{name}.onnx"
    onnx.save(model, str(path))
    return path


@pytest.mark.req("FR-011-36")
@pytest.mark.parametrize(
    ("op", "extra"),
    [
        ("Einsum", {"equation": "ij,jk->ik"}),
        ("DFT", {}),
        ("Relu", {}),
        ("Gemm", {}),
        ("Softmax", {}),
        ("ReduceSum", {}),
        ("Shape", {}),
    ],
)
def test_a_graph_with_an_operator_outside_the_whitelist_is_refused_naming_it(
    tmp_path: Path, op: str, extra: dict
) -> None:
    from onnx import helper

    inputs = ["X", "X"] if op in {"Einsum", "Gemm"} else ["X"]
    node = helper.make_node(op, inputs, ["Y"], **extra)
    path = handmade(tmp_path, [node], name=f"bad_{op}")
    with pytest.raises(ExportError, match=op):
        export.verify_graph(path)


@pytest.mark.req("FR-011-36")
def test_a_graph_with_a_complex_typed_tensor_is_refused(tmp_path: Path) -> None:
    from onnx import TensorProto, helper

    c = helper.make_tensor_value_info("C", TensorProto.COMPLEX64, [4, 4])
    path = handmade(tmp_path, [helper.make_node("Identity", ["X"], ["Y"])], name="complex_vi", extra_value_info=[c])
    with pytest.raises(ExportError, match="complex"):
        export.verify_graph(path)


@pytest.mark.req("FR-011-36")
def test_a_matmul_add_graph_is_accepted(tmp_path: Path) -> None:
    from onnx import helper, numpy_helper

    w = numpy_helper.from_array(np.eye(4, dtype=np.float32), "W")
    nodes = [helper.make_node("MatMul", ["X", "W"], ["Z"]), helper.make_node("Add", ["Z", "X"], ["Y"])]
    assert export.verify_graph(handmade(tmp_path, nodes, name="good", initializers=[w])) is None


# ------------------------------------------------------------------ FR-011-36 the DC-011-02 description


@pytest.mark.req("FR-011-36")
@pytest.mark.parametrize("key", ["fp32", "fp16"])
def test_the_description_validates_and_carries_the_fno_contract(exported, key: str) -> None:
    _, res, _ = exported
    io = res.io[key]
    assert [e.message for e in VALIDATOR.iter_errors(io)] == []
    assert (io["engine"], io["opset"], io["ir_version"], io["delivery"]) == ("fno", 19, 10, "live")
    assert io["precision"] == key
    assert "aggregation" not in io
    inp, out = io["inputs"][0], io["outputs"][0]
    assert (inp["name"], inp["dtype"], inp["shape"], inp["channel_axis"]) == ("fields", "float32", [1, 5, 64, 64], 1)
    assert [c["name"] for c in inp["channels"]] == [c["name"] for c in IN_CHANNELS]
    assert [c["unit"] for c in inp["channels"]] == [c["unit"] for c in IN_CHANNELS]
    assert [c["normalisation"]["rule"] for c in inp["channels"]] == [c["normalisation"]["rule"] for c in IN_CHANNELS]
    assert (out["name"], out["dtype"], out["shape"]) == ("depth", "float32", [1, 9, 64, 64])
    assert [c["name"] for c in out["channels"]] == [c["name"] for c in OUT_CHANNELS]
    assert io["training_envelope"] == EXAMPLE["training_envelope"]


@pytest.mark.req("FR-011-36")
@pytest.mark.parametrize("key", ["fp32", "fp16"])
def test_names_types_and_dimensions_of_the_description_equal_those_of_the_graph(exported, key: str) -> None:
    _, res, _ = exported
    m = onnx.load(str(res.paths[key]))
    io = res.io[key]

    def describe(vi) -> tuple:
        tt = vi.type.tensor_type
        return vi.name, [d.dim_value for d in tt.shape.dim]

    initializers = {i.name for i in m.graph.initializer}
    assert [describe(v) for v in m.graph.input if v.name not in initializers] == [
        (t["name"], t["shape"]) for t in io["inputs"]
    ]
    assert [describe(v) for v in m.graph.output] == [(t["name"], t["shape"]) for t in io["outputs"]]
    assert ELEM[m.graph.input[0].type.tensor_type.elem_type] == io["inputs"][0]["dtype"]


@pytest.mark.req("FR-011-36")
@pytest.mark.parametrize("key", ["fp32", "fp16"])
def test_digest_size_and_relative_path_of_the_file_are_described(exported, key: str) -> None:
    _, res, out = exported
    path = res.paths[key]
    desc = res.io[key]["onnx"]
    assert desc["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert desc["bytes"] == path.stat().st_size
    assert desc["path"] == f"{out.name}/{path.name}"
    assert path.name == f"fno-test-{key}.onnx"


@pytest.mark.req("FR-011-36")
def test_the_fp16_file_is_smaller_than_the_fp32_file(exported) -> None:
    _, res, _ = exported
    assert res.paths["fp16"].stat().st_size < 0.7 * res.paths["fp32"].stat().st_size


# ------------------------------------------------------------------ FR-011-37 / SC-011-04 parity


def run_ort(path: Path, x: np.ndarray) -> np.ndarray:
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return sess.run(None, {"fields": x})[0]


@pytest.mark.req("SC-011-04")
@pytest.mark.req("FR-011-37")
def test_ort_cpu_fp32_matches_pytorch_fp32_on_200_golden_fields(exported) -> None:
    model, res, _ = exported
    report = export.check_parity(model, res.paths["fp32"], n_golden=200, seed=0)
    assert report.passed is True
    assert report.n_golden == 200
    assert report.tolerances == {"rtol": TOL["rtol"], "atol": TOL["atol"], "max_abs": TOL["max_abs"]}
    assert report.max_abs <= TOL["max_abs"]
    sess = ort.InferenceSession(str(res.paths["fp32"]), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(1)
    for _ in range(5):  # an independent spot check on fresh fields
        x = rng.normal(size=(1, 5, 64, 64)).astype(np.float32)
        with torch.no_grad():
            ref = model(torch.from_numpy(x)).numpy()
        got = sess.run(None, {"fields": x})[0]
        assert np.all(np.abs(got - ref) <= TOL["atol"] + TOL["rtol"] * np.abs(ref))


@pytest.mark.req("SC-011-04")
def test_a_perturbed_graph_fails_the_parity_check(exported, tmp_path: Path) -> None:
    model, res, _ = exported
    m = onnx.load(str(res.paths["fp32"]))
    for init in m.graph.initializer:
        if init.data_type == onnx.TensorProto.FLOAT and init.name.endswith("bias"):
            init.CopyFrom(onnx.numpy_helper.from_array(onnx.numpy_helper.to_array(init) + 0.05, init.name))
            break
    else:
        pytest.fail("no float bias initializer found")
    bad = tmp_path / "perturbed.onnx"
    onnx.save(m, str(bad))
    assert export.check_parity(model, bad, n_golden=200).passed is False


@pytest.mark.req("FR-011-37")
@pytest.mark.parametrize("n", [0, 1, 199, -1])
def test_fewer_than_200_golden_fields_are_refused(exported, n: int) -> None:
    model, res, _ = exported
    with pytest.raises(ValueError, match="200"):
        export.check_parity(model, res.paths["fp32"], n_golden=n)


# ------------------------------------------------------------------ FR-011-37 fp16 rule


def pp(value: float) -> dict[str, float]:
    return {**{f"depth_t{k}": 0.2 for k in range(1, 9)}, "depth_max": value}


@pytest.mark.req("FR-011-37")
def test_the_threshold_is_one_percentage_point() -> None:
    assert FP16_PP == 1.0


@pytest.mark.req("FR-011-37")
@pytest.mark.parametrize(
    ("worst", "expected"),
    [(0.0, "fp16"), (0.99, "fp16"), (1.0, "fp16"), (1.0001, "fp32"), (3.0, "fp32"), (-1.5, "fp32")],
)
def test_fp16_is_live_only_when_every_field_changes_by_at_most_one_point(worst: float, expected: str) -> None:
    assert export.choose_live_precision(pp(worst)) == expected


@pytest.mark.req("FR-011-37")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_changes_never_accept_fp16(bad: float) -> None:
    assert export.choose_live_precision(pp(bad)) == "fp32"


@pytest.mark.req("FR-011-37")
def test_the_change_of_a_single_field_decides_and_no_evidence_means_fp32() -> None:
    one_bad = {f"depth_t{k}": 0.1 for k in range(1, 9)}
    one_bad["depth_t5"] = 1.2
    assert export.choose_live_precision(one_bad) == "fp32"
    assert export.choose_live_precision({}) == "fp32"


# ------------------------------------------------------------------ hostile arguments


@pytest.mark.req("FR-011-36")
def test_hostile_export_arguments_are_refused_before_writing(exported, tmp_path: Path) -> None:
    model, _, _ = exported
    out = tmp_path / "m"
    common = {"inputs": IN_CHANNELS, "outputs": OUT_CHANNELS, "envelope": EXAMPLE["training_envelope"]}
    with pytest.raises(TypeError):
        export.export_fno(torch.nn.Linear(2, 2), out, model_id="fno-x", **common)
    with pytest.raises(ValueError, match="envelope"):
        export.export_fno(model, out, model_id="fno-x", inputs=IN_CHANNELS, outputs=OUT_CHANNELS, envelope={})
    for bad_id in ("", "FNO X", "fno/../x", "fno-é", "f" * 70):
        with pytest.raises(ValueError, match="model_id"):
            export.export_fno(model, out, model_id=bad_id, **common)
    with pytest.raises(ValueError, match="channels"):
        export.export_fno(
            model,
            out,
            model_id="fno-x",
            inputs=IN_CHANNELS[:4],
            outputs=OUT_CHANNELS,
            envelope=EXAMPLE["training_envelope"],
        )
    with pytest.raises(ValueError, match="channels"):
        export.export_fno(
            model,
            out,
            model_id="fno-x",
            inputs=IN_CHANNELS,
            outputs=OUT_CHANNELS[:8],
            envelope=EXAMPLE["training_envelope"],
        )
    assert not out.exists() or not any(out.iterdir())


# ------------------------------------------------------------------ NFR-011-03 size of the full model


@pytest.mark.req("NFR-011-03")
@pytest.mark.slow
def test_the_full_tailings_model_is_about_5_megabytes_at_fp16_and_below_25_megabytes(tmp_path: Path) -> None:
    from pitstudio_pipeline.surrogates.fno.model import build_tailings_model

    res = export.export_fno(
        build_tailings_model().eval(),
        tmp_path / "full",
        model_id="fno-full",
        inputs=IN_CHANNELS,
        outputs=OUT_CHANNELS,
        envelope=EXAMPLE["training_envelope"],
    )
    fp16 = res.paths["fp16"].stat().st_size
    fp32 = res.paths["fp32"].stat().st_size
    assert fp16 <= 25_000_000
    assert fp32 <= 25_000_000
    assert 4_000_000 <= fp16 <= 6_500_000  # 2.36e6 parameters x 2 bytes = 4.7 MB (about 5 MB)
    assert 8_000_000 <= fp32 <= 12_500_000  # x 4 bytes = 9.4 MB
    assert res.io["fp16"]["onnx"]["bytes"] == fp16
