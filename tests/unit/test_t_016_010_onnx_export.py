"""T-016-010: dynamo export, cleanup, IR pin, checks (unit, hostile).

Requirements: FR-016-01, FR-016-02, P-016-11.

Spec: specs/016-export-acceleration/ (spec.md FR-016-01/02, section 4 P-016-11; plan.md test strategy rows FR-016-01,
FR-016-02, P-016-11; the export-config examples in contracts/examples/).

Oracles (independent of the code under test):
- reference implementations: `onnx.checker.check_model(full_check=True)`, `onnx.load`, ONNX Runtime CPU
  (`InferenceSession`) and the PyTorch module itself evaluated in eval mode (plan 016: tiny Conv -> ReLU ->
  GlobalAveragePool fixture);
- hand calculation: the read-back `ir_version` is 10 and the default-domain opset equals the configured opset;
- hostile cases written here by hand (plan 016): opset 16 and 20 configs, `ir_version` 11, a custom-domain node, a web
  graph with GridSample at since-version >= 20 (GridSample has since-version 16 for opsets 16-19 and 20 from opset 20,
  ONNX operator changelog), unknown model;
- the spec's own hostile export-config examples (every one must be refused).

Expected public API of the implementation (module `pitstudio_pipeline.export.onnx_export`, `pipeline/` environment):
    class ExportError(Exception)                      # `.reason: str` (also the message), never empty
    @dataclass ExportResult                           # path: Path, sha256: str, opset: int, opset_reason: str,
                                                      # ir_version: int
    export_model(model: torch.nn.Module, example_inputs: tuple, config: dict, out_path: Path, *,
                 known_models: Collection[str] | None = None) -> ExportResult
        validates `config` against contracts/export-config.schema.json (jsonschema), refuses a `config["model"]` that is
        not in `known_models` (when given), runs `torch.onnx.export(dynamo=True, verify=True)` at `config["opset"]`,
        cleans the graph with onnxslim, pins `ir_version` to 10, checks with `onnx.checker.check_model(full_check=True)`
        and loads it with ONNX Runtime CPU; on any refusal raises ExportError and leaves NO file at `out_path`.
    pin_ir_version(model: onnx.ModelProto, version: int = 10) -> onnx.ModelProto
        pure: a copy that differs from the input only in `ir_version`; idempotent.
    check_graph(model: onnx.ModelProto, config: dict) -> None
        raises ExportError when `model.ir_version != 10`, a node's domain is outside `config["domains"]` (the empty
        string is the default domain `ai.onnx`), or `config["web"]` is true and a GridSample node resolves to
        since-version >= 20 (reason contains "GridSample"; an opset-import mismatch reason is also acceptable there).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio_pipeline.export.onnx_export import (
    ExportError,
    check_graph,
    export_model,
    pin_ir_version,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"
CI_EXAMPLES = 200  # thresholds.yaml property_tests.ci_examples_per_test


def _config(**over: object) -> dict:
    base = json.loads((EXAMPLES / "export-config.valid-gns.json").read_text(encoding="utf-8"))
    base.update(over)
    return base


def _tiny_cnn():
    import torch

    torch.manual_seed(0)

    class Tiny(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv = torch.nn.Conv2d(3, 4, 3, padding=1)
            self.drop = torch.nn.Identity()  # onnxslim must not leave an Identity node behind
            self.act = torch.nn.ReLU()
            self.pool = torch.nn.AdaptiveAvgPool2d(1)

        def forward(self, x):
            return self.pool(self.act(self.drop(self.conv(x))))

    return Tiny().eval(), (torch.zeros(1, 3, 8, 8),)


def _graph(*, opset: int = 18, ir: int = 10, domain: str = "", op: str = "Relu", extra_imports=()):
    from onnx import TensorProto, helper

    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    node = helper.make_node(op, ["x"], ["y"], domain=domain)
    graph = helper.make_graph([node], "g", [x], [y])
    imports = [helper.make_opsetid("", opset), *extra_imports]
    model = helper.make_model(graph, opset_imports=imports)
    model.ir_version = ir
    return model


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-01: the accepted export
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-01")
def test_export_writes_checked_ir10_graph_at_configured_opset_and_ort_matches_torch(tmp_path: Path) -> None:
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch

    model, inputs = _tiny_cnn()
    config = _config(opset=18, opset_reason="fixture: the plain default-domain operators exist at opset 18")
    out = tmp_path / "tiny.onnx"
    result = export_model(model, inputs, config, out)

    loaded = onnx.load(out)
    onnx.checker.check_model(loaded, full_check=True)  # reference implementation
    assert loaded.ir_version == 10
    default_domain = [o.version for o in loaded.opset_import if o.domain in ("", "ai.onnx")]
    assert default_domain == [18]
    assert result.path == out
    assert result.opset == 18
    assert result.ir_version == 10
    assert result.opset_reason == config["opset_reason"]
    assert len(result.sha256) == 64

    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    x = np.random.default_rng(1).standard_normal((1, 3, 8, 8)).astype(np.float32)
    got = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    with torch.no_grad():
        want = model(torch.from_numpy(x)).numpy()
    np.testing.assert_allclose(got, want, rtol=1e-4, atol=1e-5)


@pytest.mark.req("FR-016-01")
def test_export_leaves_no_identity_nodes_after_onnxslim(tmp_path: Path) -> None:
    import onnx

    model, inputs = _tiny_cnn()
    export_model(model, inputs, _config(opset=17), tmp_path / "t.onnx")
    ops = [n.op_type for n in onnx.load(tmp_path / "t.onnx").graph.node]
    assert "Identity" not in ops
    assert "Conv" in ops
    assert "Relu" in ops


@pytest.mark.req("FR-016-01")
@pytest.mark.parametrize("opset", [17, 18, 19])
def test_export_records_each_allowed_opset(tmp_path: Path, opset: int) -> None:
    model, inputs = _tiny_cnn()
    result = export_model(model, inputs, _config(opset=opset), tmp_path / "t.onnx")
    assert result.opset == opset


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-02: hostile configurations and graphs; nothing is published for a refused model
# ----------------------------------------------------------------------------------------------------------------------


def _hostile_config_files() -> list[Path]:
    return sorted(EXAMPLES.glob("export-config.hostile-*.json"))


@pytest.mark.req("FR-016-02")
@pytest.mark.parametrize("path", _hostile_config_files(), ids=lambda p: p.stem)
def test_every_hostile_export_config_example_is_refused_and_no_file_is_written(path: Path, tmp_path: Path) -> None:
    model, inputs = _tiny_cnn()
    config = json.loads(path.read_text(encoding="utf-8"))
    out = tmp_path / "t.onnx"
    with pytest.raises(ExportError) as info:
        export_model(model, inputs, config, out)
    assert info.value.reason
    assert not out.exists()


@pytest.mark.req("FR-016-02")
@pytest.mark.parametrize("opset", [16, 20])
def test_opset_outside_17_to_19_is_refused(opset: int, tmp_path: Path) -> None:
    model, inputs = _tiny_cnn()
    out = tmp_path / "t.onnx"
    with pytest.raises(ExportError):
        export_model(model, inputs, _config(opset=opset), out)
    assert not out.exists()


@pytest.mark.req("FR-016-02")
def test_unknown_model_name_is_refused(tmp_path: Path) -> None:
    model, inputs = _tiny_cnn()
    out = tmp_path / "t.onnx"
    with pytest.raises(ExportError) as info:
        export_model(model, inputs, _config(model="no-such-model"), out, known_models={"d-fine-n", "gns"})
    assert "no-such-model" in info.value.reason
    assert not out.exists()


@pytest.mark.req("FR-016-02")
def test_written_ir_version_other_than_10_is_refused() -> None:
    with pytest.raises(ExportError) as info:
        check_graph(_graph(ir=11), _config())
    assert "ir_version" in info.value.reason


@pytest.mark.req("FR-016-02")
def test_ir10_graph_with_default_domain_passes_the_check() -> None:
    assert check_graph(_graph(ir=10, opset=18), _config(opset=18)) is None


@pytest.mark.req("FR-016-02")
def test_node_domain_outside_the_allow_list_is_refused() -> None:
    from onnx import helper

    model = _graph(domain="custom.ops", op="Magic", extra_imports=[helper.make_opsetid("custom.ops", 1)])
    with pytest.raises(ExportError) as info:
        check_graph(model, _config(domains=["ai.onnx"]))
    assert "custom.ops" in info.value.reason


@pytest.mark.req("FR-016-02")
def test_allow_listed_extra_domain_is_accepted() -> None:
    from onnx import helper

    model = _graph(domain="com.microsoft", op="Gelu", extra_imports=[helper.make_opsetid("com.microsoft", 1)])
    assert check_graph(model, _config(domains=["ai.onnx", "com.microsoft"])) is None


@pytest.mark.req("FR-016-02")
def test_web_graph_with_gridsample_since_version_20_is_refused() -> None:
    import onnx
    from onnx import TensorProto, helper

    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1, 4, 4])
    g = helper.make_tensor_value_info("g", TensorProto.FLOAT, [1, 2, 2, 2])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1, 2, 2])
    node = helper.make_node("GridSample", ["x", "g"], ["y"], mode="bilinear", align_corners=0)
    for opset, must_refuse in ((19, False), (20, True)):
        graph = helper.make_graph([node], "gs", [x, g], [y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", opset)])
        model.ir_version = 10
        assert onnx.defs.get_schema("GridSample", opset).since_version == (20 if must_refuse else 16)  # oracle
        if must_refuse:
            with pytest.raises(ExportError) as info:
                check_graph(model, _config(web=True, live=False))
            assert "GridSample" in info.value.reason or "opset" in info.value.reason.lower()
        else:
            assert check_graph(model, _config(web=True, live=False, opset=19)) is None


@pytest.mark.req("FR-016-02")
def test_gridsample_since_version_20_is_allowed_when_the_graph_is_not_flagged_web() -> None:
    from onnx import TensorProto, helper

    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1, 4, 4])
    g = helper.make_tensor_value_info("g", TensorProto.FLOAT, [1, 2, 2, 2])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1, 2, 2])
    node = helper.make_node("GridSample", ["x", "g"], ["y"], mode="bilinear", align_corners=0)
    graph = helper.make_graph([node], "gs", [x, g], [y])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 20)])
    model.ir_version = 10
    # not flagged web: the GridSample rule does not apply (an opset-import mismatch may still refuse the graph)
    reason = ""
    try:
        check_graph(model, _config(web=False, live=False, opset=19))
    except ExportError as err:
        reason = err.reason
    assert "GridSample" not in reason


# ----------------------------------------------------------------------------------------------------------------------
# P-016-11: pinning the IR version is idempotent and changes nothing but ir_version
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-016-11")
@settings(max_examples=CI_EXAMPLES, deadline=None)
@given(
    opset=st.sampled_from([17, 18, 19]),
    ir=st.integers(min_value=3, max_value=14),
    ops=st.lists(st.sampled_from(["Relu", "Neg", "Abs", "Sigmoid", "Tanh"]), min_size=1, max_size=6),
    scale=st.floats(min_value=-4, max_value=4, allow_nan=False, allow_infinity=False, width=32),
)
def test_pin_ir_version_is_idempotent_and_touches_only_ir_version(opset: int, ir: int, ops: list[str], scale: float):
    import numpy as np
    from onnx import TensorProto, helper, numpy_helper

    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])
    nodes, prev = [], "x"
    for i, op in enumerate(ops):
        nodes.append(helper.make_node(op, [prev], [f"t{i}"]))
        prev = f"t{i}"
    nodes.append(helper.make_node("Mul", [prev, "k"], ["y"]))
    k = numpy_helper.from_array(np.full((1, 4), scale, dtype=np.float32), "k")
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    model = helper.make_model(
        helper.make_graph(nodes, "g", [x], [y], initializer=[k]), opset_imports=[helper.make_opsetid("", opset)]
    )
    model.ir_version = ir

    once = pin_ir_version(model)
    twice = pin_ir_version(once)
    assert once.ir_version == 10
    assert twice.SerializeToString() == once.SerializeToString()  # idempotence

    def without_ir(m):
        c = type(m)()
        c.CopyFrom(m)
        c.ir_version = 0
        return c.SerializeToString()

    assert without_ir(once) == without_ir(model)  # same nodes, initialisers and opset imports
    assert model.ir_version == ir  # the input is not modified
