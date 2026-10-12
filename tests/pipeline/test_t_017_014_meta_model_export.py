"""T-017-014: meta-model export, IO description, parity (pipeline).

Requirements: FR-017-07, SC-017-02, NFR-017-01.

Spec: specs/017-planning-survey/spec.md
- FR-017-07: `s60_export` exports the selected meta-model at opset 17 with IR version 10 (MLP: dynamo export with
  verification; trees: the locked `ai.onnx.ml` converter) with the input/output description of DC-011-02
  (`contracts/surrogate-io.schema.json`), and checks ONNX Runtime CPU fp32 against the Python model on >= 200 golden
  inputs with `models.onnx_cpu_fp32`;
- SC-017-02: export parity fp32 rtol 1e-3, atol 1e-5, max abs 1e-4;
- NFR-017-01: meta-model ONNX size < 10^6 bytes (`models.meta_model_onnx_bytes_max`).
plan.md test strategy rows FR-017-07 (ONNX Runtime CPU fp32 against the Python model on 200 golden inputs, reference
implementation), SC-017-02 (as FR-017-07), NFR-017-01 (file sizes).

Oracles:
- the Python model itself evaluated in eval mode on the golden inputs (torch), with the normalisation of the spec's
  valid meta-model IO example written out in the test: log-standardise the 15 inputs, run the MLP, un-standardise the 3
  outputs (the graph applies both, `applied_in_graph: true`);
- `onnx.load` / `onnx.checker` for the IR version and the default-domain opset; ONNX Runtime CPU for the parity numbers;
- the DC-011-02 schema (`jsonschema`, with the contract schemas as a `referencing` registry) and the spec 011 valid
  meta-model example for the expected description (model_id `d2-meta-mlp`, engine `meta-model`, opset 17, IR 10, fp32,
  input `x` of shape [B, 15], output `y` of shape [B, 3], symbolic dim B in [1, 1024]);
- sizes by hand: a 15-64-64-64-3 float32 MLP has 9,539 parameters (about 38 KB); a 15-512-512-512-3 one about 2.1 MB;
- `thresholds.yaml` `models.meta_model_onnx_bytes_max` = 1,000,000 and `models.onnx_cpu_fp32`.

Expected public API (module `pitstudio_pipeline.mine_to_mill.export`, `pipeline/` environment):
    class MetaModelTooLarge(Exception)
    class ConverterUnavailable(Exception)
    check_meta_model_size(nbytes: int) -> None            # MetaModelTooLarge unless nbytes < 1_000_000
    converter_available() -> bool                        # whether the ai.onnx.ml tree converter is importable
    @dataclass MetaModelExport: onnx_path: Path, bytes: int, sha256: str, opset: int, ir_version: int, parity (the
        `pitstudio.export.comparator.ComparisonResult` of ORT CPU vs the Python model), io: dict (DC-011-02 document)
    export_mlp(net: torch.nn.Module, *, input_log_mean, input_log_std, output_mean, output_std, golden_inputs:
               np.ndarray, out_path: Path, model_id: str, onnx_relpath: str, input_channels: Sequence[Mapping],
               output_channels: Sequence[Mapping], envelope: Mapping) -> MetaModelExport
        the exported graph takes x (B, 15) in physical units and returns y (B, 3) in physical units
        (log-standardise inside, un-standardise inside), opset 17, IR 10, dynamic batch B; refuses fewer than 200 golden
        inputs, non-finite golden inputs and a wrong width (pitstudio_pipeline.export.golden.GoldenInvalid) and a file
        of 10^6 bytes or more (MetaModelTooLarge, no file left).
    export_gbm(models: Sequence, *, golden_inputs, out_path, ...) -> MetaModelExport
        converts one HistGradientBoostingRegressor per output with the ai.onnx.ml converter; raises
        ConverterUnavailable when `converter_available()` is false.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from pitstudio_pipeline.export.golden import GoldenInvalid
from pitstudio_pipeline.mine_to_mill.export import (
    ConverterUnavailable,
    MetaModelTooLarge,
    check_meta_model_size,
    converter_available,
    export_gbm,
    export_mlp,
)

ROOT = Path(__file__).resolve().parents[2]
MODELS = yaml.safe_load((ROOT / "specs/000-foundation/thresholds.yaml").read_text("utf-8"))["models"]
EXAMPLE = json.loads(
    (ROOT / "specs/011-surrogates/contracts/examples/surrogate-io.valid-meta-model.json").read_text("utf-8")
)
LOW = np.array([3.0, 1.0, 0.3, 89.0, 8.0, 4.0, 8.0, 100.0, 75.0, 5000.0, 0.8, 8.0, 0.6, 0.05, 0.5])
HIGH = np.array([9.0, 1.5, 1.2, 311.0, 15.0, 14.0, 22.0, 200.0, 212.0, 20000.0, 0.95, 25.0, 1.2, 0.15, 2.0])
IN_CHANNELS = [{"name": c["name"], "unit": c["unit"]} for c in EXAMPLE["inputs"][0]["channels"]]
OUT_CHANNELS = EXAMPLE["outputs"][0]["channels"]
ENVELOPE = EXAMPLE["training_envelope"]


def _net(width: int = 64):
    import torch

    torch.manual_seed(0)
    return torch.nn.Sequential(
        torch.nn.Linear(15, width), torch.nn.SiLU(),
        torch.nn.Linear(width, width), torch.nn.SiLU(),
        torch.nn.Linear(width, width), torch.nn.SiLU(),
        torch.nn.Linear(width, 3),
    ).eval()  # fmt: skip


def _stats():
    rng = np.random.default_rng(0)
    x = rng.uniform(LOW, HIGH, (2000, 15))
    lx = np.log(x)
    return lx.mean(axis=0), lx.std(axis=0), np.array([11.5, 11.8, 4.2]), np.array([3.2, 3.1, 1.1])


def _golden(n: int = 200, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).uniform(LOW, HIGH, (n, 15)).astype(np.float32)


def _export(tmp_path: Path, net=None, golden=None, name: str = "d2-meta-mlp.onnx"):
    m, s, om, os_ = _stats()
    return export_mlp(
        net if net is not None else _net(),
        input_log_mean=m,
        input_log_std=s,
        output_mean=om,
        output_std=os_,
        golden_inputs=_golden() if golden is None else golden,
        out_path=tmp_path / name,
        model_id="d2-meta-mlp",
        onnx_relpath="web/public/models/d2-meta-mlp.onnx",
        input_channels=IN_CHANNELS,
        output_channels=OUT_CHANNELS,
        envelope=ENVELOPE,
    )


def _reference(net, x: np.ndarray) -> np.ndarray:
    import torch

    m, s, om, os_ = (torch.from_numpy(a.astype(np.float32)) for a in _stats())
    with torch.no_grad():  # the Python model in float32, the precision of the exported graph
        z = (torch.log(torch.from_numpy(x.astype(np.float32))) - m) / s
        y = net(z) * os_ + om
    return y.numpy().astype(np.float64)


def _validator():
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "contracts").glob("*.schema.json")}
    registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in schemas.values()])
    return Draft202012Validator(schemas["surrogate-io.schema.json"], registry=registry)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-07
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-07")
def test_the_mlp_is_exported_at_opset_17_ir_10_and_checks_out(tmp_path: Path) -> None:
    import onnx

    result = _export(tmp_path)
    model = onnx.load(result.onnx_path)
    onnx.checker.check_model(model, full_check=True)
    assert model.ir_version == 10 == result.ir_version
    assert [o.version for o in model.opset_import if o.domain in ("", "ai.onnx")] == [17] == [result.opset]
    assert result.sha256
    assert result.bytes == result.onnx_path.stat().st_size


@pytest.mark.req("FR-017-07")
def test_ort_cpu_fp32_matches_the_python_model_on_the_golden_inputs_within_the_layer1_tolerances(
    tmp_path: Path,
) -> None:
    import onnxruntime as ort

    net = _net()
    result = _export(tmp_path, net)
    golden = _golden()
    sess = ort.InferenceSession(str(result.onnx_path), providers=["CPUExecutionProvider"])
    got = sess.run(None, {"x": golden})[0].astype(np.float64)
    want = _reference(net, golden)
    tol = MODELS["onnx_cpu_fp32"]
    assert np.all(np.abs(got - want) <= tol["atol"] + tol["rtol"] * np.abs(want))  # element-wise, by hand
    assert float(np.max(np.abs(got - want))) <= tol["max_abs"]
    assert result.parity.verdict == "pass"
    assert result.parity.max_abs_error == pytest.approx(float(np.max(np.abs(got - want))), abs=1e-5)


@pytest.mark.req("FR-017-07")
def test_the_graph_takes_physical_units_with_a_dynamic_batch(tmp_path: Path) -> None:
    import onnxruntime as ort

    net = _net()
    result = _export(tmp_path, net)
    sess = ort.InferenceSession(str(result.onnx_path), providers=["CPUExecutionProvider"])
    for batch in (1, 7, 256):
        x = _golden(batch, seed=batch)
        y = sess.run(None, {"x": x})[0]
        assert y.shape == (batch, 3)
        np.testing.assert_allclose(y, _reference(net, x), rtol=1e-3, atol=1e-5)


@pytest.mark.req("FR-017-07")
def test_the_io_description_validates_against_dc_011_02_and_matches_the_spec_example(tmp_path: Path) -> None:
    result = _export(tmp_path)
    io = result.io
    assert list(_validator().iter_errors(io)) == []
    assert io["model_id"] == EXAMPLE["model_id"]
    assert io["engine"] == "meta-model"
    assert (io["opset"], io["ir_version"], io["precision"]) == (17, 10, "fp32")
    assert io["onnx"] == {
        "path": "web/public/models/d2-meta-mlp.onnx",
        "sha256": result.sha256,
        "bytes": result.bytes,
    }
    assert io["inputs"][0]["name"] == "x"
    assert io["inputs"][0]["shape"] == ["B", 15]
    assert io["outputs"][0]["name"] == "y"
    assert io["outputs"][0]["shape"] == ["B", 3]
    assert io["symbolic_dims"] == EXAMPLE["symbolic_dims"]
    assert io["training_envelope"] == EXAMPLE["training_envelope"]


@pytest.mark.req("FR-017-07")
def test_fewer_than_200_golden_inputs_non_finite_inputs_and_a_wrong_width_are_refused(tmp_path: Path) -> None:
    with pytest.raises(GoldenInvalid):
        _export(tmp_path, golden=_golden(199))
    bad = _golden()
    bad[3, 4] = np.nan
    with pytest.raises(GoldenInvalid):
        _export(tmp_path, golden=bad)
    with pytest.raises(GoldenInvalid):
        _export(tmp_path, golden=np.ones((200, 14), dtype=np.float32))
    assert not (tmp_path / "d2-meta-mlp.onnx").exists()


@pytest.mark.req("FR-017-07")
def test_the_tree_family_export_uses_the_locked_ml_converter_or_reports_that_it_is_missing(tmp_path: Path) -> None:
    from sklearn.ensemble import HistGradientBoostingRegressor

    x = _golden(400)
    models = [HistGradientBoostingRegressor(max_iter=20).fit(x, x[:, j] * 0.1) for j in range(3)]
    if not converter_available():
        with pytest.raises(ConverterUnavailable):
            export_gbm(models, golden_inputs=_golden(), out_path=tmp_path / "gbm.onnx")
        assert not (tmp_path / "gbm.onnx").exists()
        return
    import onnx

    result = export_gbm(models, golden_inputs=_golden(), out_path=tmp_path / "gbm.onnx")
    model = onnx.load(result.onnx_path)
    assert model.ir_version == 10
    assert "ai.onnx.ml" in {o.domain for o in model.opset_import}
    assert result.parity.verdict == "pass"


# ----------------------------------------------------------------------------------------------------------------------
# SC-017-02 and NFR-017-01
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("SC-017-02")
def test_the_parity_tolerances_are_the_models_onnx_cpu_fp32_ones() -> None:
    assert MODELS["onnx_cpu_fp32"] == {"rtol": 1.0e-3, "atol": 1.0e-5, "max_abs": 1.0e-4}


@pytest.mark.req("NFR-017-01")
def test_the_threshold_and_the_size_rule_are_strictly_below_one_million_bytes() -> None:
    assert MODELS["meta_model_onnx_bytes_max"] == 1_000_000
    assert check_meta_model_size(999_999) is None
    for n in (1_000_000, 1_000_001):
        with pytest.raises(MetaModelTooLarge):
            check_meta_model_size(n)


@pytest.mark.req("NFR-017-01")
def test_the_3x64_mlp_is_far_below_the_budget_and_a_3x512_one_is_refused_without_leaving_a_file(tmp_path: Path) -> None:
    small = _export(tmp_path)
    assert 30_000 < small.bytes < 100_000  # 9,539 float32 parameters plus the normalisation constants
    with pytest.raises(MetaModelTooLarge):
        _export(tmp_path, net=_net(512), name="wide.onnx")
    assert not (tmp_path / "wide.onnx").exists()
