"""T-011-012 - FR-011-07, P-011-05: padded-layout GNS export (opset 17, IR version 10), bench-only ScatterElements
    variant.

Oracles (independent of the code under test; plan 011 test strategy FR-011-07):
- ONNX graph inspection with the reference implementation `onnx`: the opset import of the default domain (17), the
    IR version
  (10), the operator types of the live graphs (no ScatterElements, no ScatterND; Gather plus ReduceSum present) and
      of the bench
  variant (ScatterElements with attribute reduction = "add"), the initializer element types (FLOAT for fp32,
      FLOAT16 for fp16);
- the DC-011-02 draft schema (`specs/011-surrogates/contracts/surrogate-io.schema.json`) with `jsonschema`: every
    description
  validates; the live documents carry delivery "live" and aggregation "padded-gather", the bench document delivery
      "bench-only"
  and aggregation "scatter-add" with a reason (the schema's own conditional rules);
- the description is checked against the graph: names, element types and dimensions of the graph inputs and outputs
    equal the
  document's (symbolic dimension N), and `onnx.sha256` and `onnx.bytes` equal the SHA-256 (hashlib) and size of the
      file;
- P-011-05 at graph level: ONNX Runtime CPU on the live fp32 graph and on the bench graph, same inputs, equal
    within rtol 1e-5.

Expected public API (module `pitstudio_pipeline.surrogates.gns.export`, package under `pipeline/src/`):

    export_gns(model, out_dir, *, model_id, particle_diameter_m, envelope, normalisation, cases=("A3",),
               categories=("grain",)) -> GnsExport
        model: a `GnsStep` (aggregation "padded"); out_dir: created if missing; envelope: the `training_envelope`
            object of
        DC-011-02 (>= 1 range); normalisation: {"velocities": {"mean": [2], "std": [2]}, "acceleration": {"mean":
            [2], "std": [2]}}
        (applied in the graph, as in the DC-011-02 example).
        Writes `<model_id>-fp32.onnx`, `<model_id>-fp16.onnx` (the live padded-layout graph, Gather plus masked
            ReduceSum, no
        ScatterElements) and `<model_id>-scatter-bench.onnx` (the ScatterElements(reduction = add) variant, fp32)
            under out_dir.
        GnsExport attributes: paths (dict "fp32" | "fp16" | "scatter-bench" -> Path), io (dict of the same keys ->
            the DC-011-02
        document of that file; `onnx.path` is `<out_dir name>/<file name>`, relative), model_id.
        Raises ValueError for an empty envelope, and TypeError when `model` is not a GnsStep.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
onnx = pytest.importorskip("onnx")
ort = pytest.importorskip("onnxruntime")
jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.gns import export  # noqa: E402
from pitstudio_pipeline.surrogates.gns.model import GnsStep  # noqa: E402

from pitstudio.granular.graph import build_radius_graph  # noqa: E402

CONTRACTS = ROOT / "specs" / "011-surrogates" / "contracts"
VALIDATOR = jsonschema.Draft202012Validator(
    json.loads((CONTRACTS / "surrogate-io.schema.json").read_text(encoding="utf-8"))
)
EXAMPLE = json.loads((CONTRACTS / "examples" / "surrogate-io.valid.json").read_text(encoding="utf-8"))
D = 0.004
R = 2.5 * D
DT = 0.01
NORM = {
    "velocities": {"mean": [0.0, -0.02], "std": [0.08, 0.09]},
    "acceleration": {"mean": [0.0, -1.2], "std": [3.1, 4.2]},
}
ELEM = {
    onnx.TensorProto.FLOAT: "float32",
    onnx.TensorProto.INT64: "int64",
    onnx.TensorProto.BOOL: "bool",
    onnx.TensorProto.FLOAT16: "float16",
}


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("gns_export") / "models"
    torch.manual_seed(0)
    model = GnsStep(connectivity_radius=R, frame_interval=DT, n_particle_types=1, latent=16, steps=2)
    with torch.no_grad():
        for p in model.parameters():
            p.normal_(0.0, 0.1)
    model.eval()
    result = export.export_gns(
        model,
        out,
        model_id="gns-test",
        particle_diameter_m=D,
        envelope=EXAMPLE["training_envelope"],
        normalisation=NORM,
        cases=("A3",),
    )
    return result, model, out


def load(result, key: str):
    return onnx.load(str(result.paths[key]))


def ops(m) -> set[str]:
    return {n.op_type for n in m.graph.node}


def default_opset(m) -> int:
    return next(o.version for o in m.opset_import if o.domain in ("", "ai.onnx"))


def initializer_types(m) -> set[int]:
    return {i.data_type for i in m.graph.initializer}


# ------------------------------------------------------------------ FR-011-07 graph structure


@pytest.mark.req("FR-011-07")
@pytest.mark.parametrize("key", ["fp32", "fp16", "scatter-bench"])
def test_every_exported_graph_has_opset_17_and_ir_version_10_and_passes_the_onnx_checker(exported, key: str) -> None:
    result, _, _ = exported
    m = load(result, key)
    assert default_opset(m) == 17
    assert m.ir_version == 10
    onnx.checker.check_model(m)


@pytest.mark.req("FR-011-07")
@pytest.mark.parametrize("key", ["fp32", "fp16"])
def test_the_live_graphs_use_gather_and_a_masked_reducesum_and_no_scatter(exported, key: str) -> None:
    result, _, _ = exported
    types = ops(load(result, key))
    assert "ScatterElements" not in types
    assert "ScatterND" not in types
    assert "Scatter" not in types
    assert "Gather" in types
    assert "ReduceSum" in types


@pytest.mark.req("FR-011-07")
def test_the_bench_variant_uses_scatter_elements_with_add_reduction(exported) -> None:
    result, _, _ = exported
    nodes = [n for n in load(result, "scatter-bench").graph.node if n.op_type == "ScatterElements"]
    assert nodes
    for node in nodes:
        attrs = {a.name: a for a in node.attribute}
        assert attrs["reduction"].s == b"add"


@pytest.mark.req("FR-011-07")
def test_precision_shows_in_the_initializer_types(exported) -> None:
    result, _, _ = exported
    assert onnx.TensorProto.FLOAT16 in initializer_types(load(result, "fp16"))
    assert onnx.TensorProto.FLOAT16 not in initializer_types(load(result, "fp32"))
    assert onnx.TensorProto.FLOAT in initializer_types(load(result, "fp32"))


# ------------------------------------------------------------------ FR-011-07 the DC-011-02 description


@pytest.mark.req("FR-011-07")
@pytest.mark.parametrize("key", ["fp32", "fp16", "scatter-bench"])
def test_the_description_validates_against_the_dc_011_02_schema(exported, key: str) -> None:
    result, _, _ = exported
    assert [e.message for e in VALIDATOR.iter_errors(result.io[key])] == []


@pytest.mark.req("FR-011-07")
def test_live_and_bench_documents_carry_their_delivery_aggregation_precision_and_opset(exported) -> None:
    result, _, _ = exported
    for key, precision in (("fp32", "fp32"), ("fp16", "fp16")):
        io = result.io[key]
        assert (io["engine"], io["opset"], io["ir_version"]) == ("gns", 17, 10)
        assert (io["delivery"], io["aggregation"], io["precision"]) == ("live", "padded-gather", precision)
        assert io["cases"] == ["A3"]
        assert io["model_id"] == "gns-test"
    bench = result.io["scatter-bench"]
    assert (bench["delivery"], bench["aggregation"], bench["precision"]) == ("bench-only", "scatter-add", "fp32")
    assert bench["delivery_reason"]


@pytest.mark.req("FR-011-07")
def test_inputs_and_outputs_follow_fr_011_01_with_units_and_the_symbolic_dimension(exported) -> None:
    io = exported[0].io["fp32"]
    expected_inputs = [
        ("positions", "float32", ["N", 2], "m"),
        ("velocities", "float32", ["N", 5, 2], "m/s"),
        ("particle_type", "int64", ["N"], "1"),
        ("bounds", "float32", [4], "m"),
        ("neighbour_index", "int64", ["N", 32], "1"),
        ("neighbour_mask", "bool", ["N", 32], "1"),
    ]
    assert [(t["name"], t["dtype"], t["shape"], t["unit"]) for t in io["inputs"]] == expected_inputs
    out = io["outputs"][0]
    assert (out["name"], out["dtype"], out["shape"], out["unit"]) == ("acceleration", "float32", ["N", 2], "m/s^2")
    assert io["symbolic_dims"]["N"]["min"] == 1
    assert io["constants"]["particle_diameter_m"] == pytest.approx(D)
    assert io["constants"]["connectivity_radius_m"] == pytest.approx(R)
    assert io["constants"]["max_neighbours"] == 32
    assert io["constants"]["velocity_history"] == 5
    assert io["constants"]["frame_interval_s"] == pytest.approx(DT)
    assert io["training_envelope"] == EXAMPLE["training_envelope"]
    assert io["inputs"][1]["normalisation"]["mean"] == NORM["velocities"]["mean"]
    assert io["outputs"][0]["normalisation"]["std"] == NORM["acceleration"]["std"]
    assert io["inputs"][2]["categories"] == ["grain"]


@pytest.mark.req("FR-011-07")
@pytest.mark.parametrize("key", ["fp32", "fp16", "scatter-bench"])
def test_names_types_and_dimensions_of_the_description_equal_those_of_the_graph(exported, key: str) -> None:
    result, _, _ = exported
    m = load(result, key)
    io = result.io[key]

    def describe(vi) -> tuple:
        tt = vi.type.tensor_type
        dims = [d.dim_param if d.dim_param else d.dim_value for d in tt.shape.dim]
        return vi.name, ELEM[tt.elem_type], dims

    graph_inputs = [describe(v) for v in m.graph.input if v.name not in {i.name for i in m.graph.initializer}]
    assert graph_inputs == [(t["name"], t["dtype"], t["shape"]) for t in io["inputs"]]
    graph_outputs = [describe(v) for v in m.graph.output]
    assert [(n, d) for n, _, d in graph_outputs] == [(t["name"], t["shape"]) for t in io["outputs"]]


@pytest.mark.req("FR-011-07")
@pytest.mark.parametrize("key", ["fp32", "fp16", "scatter-bench"])
def test_the_description_names_the_file_by_a_relative_path_with_its_digest_and_size(exported, key: str) -> None:
    result, _, out = exported
    path = result.paths[key]
    desc = result.io[key]["onnx"]
    assert desc["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert desc["bytes"] == path.stat().st_size
    assert desc["path"] == f"{out.name}/{path.name}"
    assert not Path(desc["path"]).is_absolute()
    assert ".." not in Path(desc["path"]).parts
    assert re.fullmatch(r"[0-9a-f]{64}", desc["sha256"])


@pytest.mark.req("FR-011-07")
def test_file_names_follow_the_model_id(exported) -> None:
    result, _, out = exported
    assert result.paths["fp32"].name == "gns-test-fp32.onnx"
    assert result.paths["fp16"].name == "gns-test-fp16.onnx"
    assert result.paths["scatter-bench"].name == "gns-test-scatter-bench.onnx"
    assert all(p.parent == out for p in result.paths.values())


# ------------------------------------------------------------------ P-011-05 at graph level and dynamic N


def feeds(n: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    side = max(0.05, 0.012 * np.sqrt(n))
    pos = rng.uniform(0.0, side, (n, 2)).astype(np.float32)
    graph = build_radius_graph(pos, R)
    return {
        "positions": pos,
        "velocities": rng.normal(0.0, 0.05, (n, 5, 2)).astype(np.float32),
        "particle_type": np.zeros(n, dtype=np.int64),
        "bounds": np.array([0.0, 0.0, side, side], dtype=np.float32),
        "neighbour_index": graph.neighbour_index.astype(np.int64),
        "neighbour_mask": graph.neighbour_mask,
    }


def run_ort(path: Path, feed: dict[str, np.ndarray]) -> np.ndarray:
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return sess.run(None, feed)[0]


@pytest.mark.req("FR-011-07")
@pytest.mark.parametrize("n", [1, 7, 53])
def test_the_live_graph_runs_for_any_particle_count_and_returns_n_by_2(exported, n: int) -> None:
    result, _, _ = exported
    out = run_ort(result.paths["fp32"], feeds(n, n))
    assert out.shape == (n, 2)
    assert np.isfinite(out).all()


@pytest.mark.req("P-011-05")
@pytest.mark.parametrize("n", [20, 60, 120])
def test_the_padded_gather_graph_equals_the_scatter_add_graph_on_the_same_inputs(exported, n: int) -> None:
    result, _, _ = exported
    feed = feeds(n, 100 + n)
    a = run_ort(result.paths["fp32"], feed)
    b = run_ort(result.paths["scatter-bench"], feed)
    assert np.abs(a).max() > 1e-6
    assert np.allclose(a, b, rtol=1e-5, atol=1e-6 * np.abs(a).max())


@pytest.mark.req("FR-011-07")
def test_the_exported_graph_applies_the_normalisation_inside_the_graph(exported) -> None:
    """Acceleration = decoder output * std + mean: with a zero network the graph returns the mean, hand value (0,
    -1.2)."""
    _, _, out = exported
    zero = GnsStep(
        connectivity_radius=R,
        frame_interval=DT,
        n_particle_types=1,
        latent=16,
        steps=2,
        acceleration_mean=tuple(NORM["acceleration"]["mean"]),
        acceleration_std=tuple(NORM["acceleration"]["std"]),
    )
    with torch.no_grad():
        for p in zero.parameters():
            p.zero_()
    res = export.export_gns(
        zero,
        out.parent / "zero_models",
        model_id="gns-zero",
        particle_diameter_m=D,
        envelope=EXAMPLE["training_envelope"],
        normalisation=NORM,
    )
    acc = run_ort(res.paths["fp32"], feeds(9, 5))
    assert np.allclose(acc, np.array(NORM["acceleration"]["mean"], dtype=np.float32), atol=1e-6)


# ------------------------------------------------------------------ hostile arguments


@pytest.mark.req("FR-011-07")
def test_an_empty_envelope_is_refused(exported, tmp_path: Path) -> None:
    _, model, _ = exported
    with pytest.raises(ValueError, match="envelope"):
        export.export_gns(
            model, tmp_path / "m", model_id="gns-x", particle_diameter_m=D, envelope={}, normalisation=NORM
        )


@pytest.mark.req("FR-011-07")
def test_a_model_that_is_not_a_gns_step_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        export.export_gns(
            torch.nn.Linear(2, 2),
            tmp_path / "m",
            model_id="gns-x",
            particle_diameter_m=D,
            envelope=EXAMPLE["training_envelope"],
            normalisation=NORM,
        )


@pytest.mark.req("FR-011-07")
@pytest.mark.parametrize("model_id", ["", "GNS A3", "gns/../x", "gns-é", "g" * 70])
def test_a_model_id_that_is_not_a_slug_is_refused_before_writing(exported, tmp_path: Path, model_id: str) -> None:
    _, model, _ = exported
    with pytest.raises(ValueError, match="model_id"):
        export.export_gns(
            model,
            tmp_path / "m",
            model_id=model_id,
            particle_diameter_m=D,
            envelope=EXAMPLE["training_envelope"],
            normalisation=NORM,
        )
    assert not (tmp_path / "m").exists() or not any((tmp_path / "m").iterdir())
