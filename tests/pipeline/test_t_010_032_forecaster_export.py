"""T-010-032: export, parity, IO description and the Chronos-Bolt fallback of the forecasters.

Requirements: FR-010-30, FR-010-31, SC-010-04, NFR-010-04, DC-010-05.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-30, FR-010-31), section 5 (NFR-010-04, SC-010-04), section 6
(DC-010-05);
plan.md rows FR-010-30 ("ONNX Runtime CPU fp32 against PyTorch fp32 (reference implementation) on 200 golden
contexts") and
FR-010-31 ("fault injection: an export that raises, and one with a perturbed weight that breaks parity");
thresholds.yaml
`models.onnx_cpu_fp32` (rtol 1e-3, atol 1e-5, max abs 1e-4) and `models.onnx_live_each_mb_max` (25). Runs in the
`pipeline/`
environment (PyTorch, onnx, ONNX Runtime).

Expected API (module `pitstudio_pipeline.slope.export`):
- `export_forecaster(model, arm, out_dir, *, golden_contexts) -> ExportResult`: exports the forecasting graph of one
  64-step block
  (input `context` float32 [1, 2, 128], output `quantiles` float32 [1, 9, 64]) to `<out_dir>/<arm>-c1.onnx` at opset
  17 with
  IR version 10 by the dynamo exporter, with verification, then checks parity (below). `ExportResult`: `onnx_path`,
  `size_bytes`,
  `io` (the DC-010-05 document: model_id "<arm>-c1", engine "forecasters", cases ["C1"], onnx {path, sha256, bytes},
  opset 17,
  ir_version 10, precision "fp32", delivery "live", constants {context_length 128, block_mean_width 4, horizon_steps 64,
  max_blocks 4}, inputs, outputs with the quantiles 0.1 .. 0.9 on axis 1 and the normalisation rule "context-mean-abs"
  applied
  outside the graph, training_envelope) and `parity` ({"n_contexts", "max_abs", "max_rel_excess", "passed",
  "thresholds"}).
  ValueError for fewer than 200 golden contexts, a context that is not float32 (N, 2, 128) or has a non-finite value,
  or an unknown arm.
- check_parity(torch_fn, ort_fn, contexts) -> dict`: runs both on every context and returns the same parity record;
  `passed` is True
  iff for every element |ort - torch| <= atol + rtol |torch| (rtol 1e-3, atol 1e-5) and the max abs difference <= 1e-4.
- `ParityError(ValueError)`: raised by an exporter whose graph misses parity (`export_all` makes that arm PRECOMPUTE).
- `export_all(jobs, *, out_dir, windows, cutoffs) -> ExportReport`: `jobs` maps an arm (tcn, patchtst,
  chronos_bolt_fine_tuned,
  chronos_bolt_zero_shot) to {"model": module or None, "contexts": golden contexts, "exporter": callable (default
  `export_forecaster`)}. `ExportReport.arms[arm]` = {"lane": "LIVE" | "PRECOMPUTE", "reason": str | None, "onnx_path":
  str | None,
  "baked_path": str | None}; `ExportReport.model_card_notes` lists the reason of every PRECOMPUTE arm. TCN and
  PatchTST stay LIVE when
  they export and pass; Chronos-Bolt (fine-tuned) whose export raises or misses parity becomes PRECOMPUTE with the
  reason, its
  forecasts baked for every `windows` entry ({event_id: window}) at every cut-off of `cutoffs` (the baked file maps
  event id ->
  cut-off -> forecast), while the other arms stay live; the zero-shot arm is always PRECOMPUTE ("published as baked
  forecasts only").

Oracles: the ONNX file inspected with `onnx` (opset, IR version, input and output names and shapes); ORT CPU against
PyTorch fp32 as the
reference implementation recomputed in the test on the golden contexts; file sizes against NFR-010-04 (4 x 10^6 bytes
for TCN and
PatchTST, 25 x 10^6 for Chronos-Bolt); hashlib for the digest; the DC-010-05 schema (jsonschema); a perturbed export
that must fail parity.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_lem_ref as lem_ref  # noqa: E402
from pitstudio.slope import preprocess  # noqa: E402
from pitstudio_pipeline.slope import export, models  # noqa: E402

torch = pytest.importorskip("torch")
onnx = pytest.importorskip("onnx")
ort = pytest.importorskip("onnxruntime")

TH = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))["models"]
RTOL, ATOL, MAX_ABS = TH["onnx_cpu_fp32"]["rtol"], TH["onnx_cpu_fp32"]["atol"], TH["onnx_cpu_fp32"]["max_abs"]


def _threshold(key: str):
    stack = [yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if key in node:
                return node[key]
            stack.extend(node.values())
    raise KeyError(key)


def _golden(n=200, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(1.0, 0.3, size=(n, 2, 128)).astype(np.float32)
    x[:, 1] = (rng.random((n, 128)) > 0.05).astype(np.float32)
    return x


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("export")
    results = {}
    for arm in ("tcn", "patchtst"):
        model = models.build_model(arm, seed=3).eval()
        results[arm] = (model, export.export_forecaster(model, arm, out, golden_contexts=_golden()))
    return results


@pytest.mark.req("FR-010-30")
@pytest.mark.parametrize("arm", ["tcn", "patchtst"])
def test_the_graph_is_opset_17_ir_10_with_the_documented_names_and_shapes(exported, arm) -> None:
    _, res = exported[arm]
    m = onnx.load(str(res.onnx_path))
    assert Path(res.onnx_path).name == f"{arm}-c1.onnx"
    assert {o.domain: o.version for o in m.opset_import}.get("") == 17
    assert m.ir_version == 10
    assert [i.name for i in m.graph.input] == ["context"]
    assert [o.name for o in m.graph.output] == ["quantiles"]
    dims = [d.dim_value for d in m.graph.input[0].type.tensor_type.shape.dim]
    assert dims == [1, 2, 128]
    onnx.checker.check_model(m)
    out = ort.InferenceSession(str(res.onnx_path), providers=["CPUExecutionProvider"]).run(
        None, {"context": _golden(1)[:1]}
    )[0]
    assert out.shape == (1, 9, 64)
    assert out.dtype == np.float32


@pytest.mark.req("SC-010-04")
@pytest.mark.parametrize("arm", ["tcn", "patchtst"])
def test_ort_cpu_fp32_matches_pytorch_fp32_on_200_golden_contexts_within_the_thresholds(exported, arm) -> None:
    model, res = exported[arm]
    sess = ort.InferenceSession(str(res.onnx_path), providers=["CPUExecutionProvider"])
    ctx = _golden(200, seed=11)  # contexts the export never saw
    worst = 0.0
    for c in ctx:
        got = sess.run(None, {"context": c[None]})[0]
        with torch.no_grad():
            want = model(torch.from_numpy(c[None])).numpy()
        assert np.allclose(got, want, rtol=RTOL, atol=ATOL)
        worst = max(worst, float(np.abs(got - want).max()))
    assert worst <= MAX_ABS
    p = res.parity
    assert p["n_contexts"] >= 200
    assert p["passed"] is True
    assert p["max_abs"] <= MAX_ABS
    assert p["thresholds"] == {"rtol": RTOL, "atol": ATOL, "max_abs": MAX_ABS}


@pytest.mark.req("NFR-010-04")
@pytest.mark.parametrize("arm", ["tcn", "patchtst"])
def test_the_exported_files_are_smaller_than_4_megabytes(exported, arm) -> None:
    _, res = exported[arm]
    assert res.size_bytes == Path(res.onnx_path).stat().st_size
    assert res.size_bytes < 4_000_000
    assert res.size_bytes < _threshold("onnx_live_each_mb_max") * 1_000_000  # and far below the 25 MB live cap


@pytest.mark.req("FR-010-30")
@pytest.mark.parametrize("arm", ["tcn", "patchtst"])
def test_the_io_description_validates_and_matches_the_graph_and_the_file(exported, arm) -> None:
    _, res = exported[arm]
    io = res.io
    assert lem_ref.schema_errors(io, "surrogate-io") == []
    assert (io["model_id"], io["engine"], io["cases"]) == (f"{arm}-c1", "forecasters", ["C1"])
    assert (io["opset"], io["ir_version"], io["precision"], io["delivery"]) == (17, 10, "fp32", "live")
    assert io["constants"] == {"context_length": 128, "block_mean_width": 4, "horizon_steps": 64, "max_blocks": 4}
    raw = Path(res.onnx_path).read_bytes()
    assert io["onnx"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert io["onnx"]["bytes"] == len(raw)
    assert io["inputs"][0]["name"] == "context"
    assert io["inputs"][0]["shape"] == [1, 2, 128]
    assert [c["name"] for c in io["inputs"][0]["channels"]] == ["inverse_velocity", "mask"]
    out = io["outputs"][0]
    assert (out["name"], out["shape"], out["quantile_axis"]) == ("quantiles", [1, 9, 64], 1)
    assert out["quantiles"] == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    assert out["normalisation"] == {"rule": "context-mean-abs", "applied_in_graph": False}
    json.dumps(io)


@pytest.mark.req("FR-010-30")
def test_hostile_golden_contexts_are_rejected(tmp_path: Path) -> None:
    model = models.build_model("tcn").eval()
    for bad in (
        _golden(199),
        _golden(200).astype(np.float64),
        _golden(200)[:, :, :127],
        np.full((200, 2, 128), np.nan, np.float32),
    ):
        with pytest.raises(ValueError, match=r"."):
            export.export_forecaster(model, "tcn", tmp_path, golden_contexts=bad)
    with pytest.raises(ValueError, match=r"."):
        export.export_forecaster(model, "lstm", tmp_path, golden_contexts=_golden())


@pytest.mark.req("SC-010-04")
def test_a_perturbed_graph_fails_the_parity_check() -> None:
    model = models.build_model("tcn", seed=1).eval()

    def torch_fn(c):
        with torch.no_grad():
            return model(torch.from_numpy(c)).numpy()

    ctx = _golden(200)
    exact = export.check_parity(torch_fn, torch_fn, ctx)
    assert exact["passed"] is True
    assert exact["max_abs"] == 0.0
    assert exact["n_contexts"] == 200
    off = export.check_parity(torch_fn, lambda c: torch_fn(c) + np.float32(2e-4), ctx)  # a perturbed weight's effect
    assert off["passed"] is False
    assert off["max_abs"] == pytest.approx(2e-4, rel=1e-3)
    inside = export.check_parity(torch_fn, lambda c: torch_fn(c) + np.float32(5e-6), ctx)  # within atol 1e-5
    assert inside["passed"] is True


def _windows(n_events=2):
    out = {}
    for i in range(n_events):
        t = np.linspace(0.0, 200.0, 801)
        out[f"voight-test-snr-obs-{i:06d}"] = preprocess.preprocess_window(t, (0.4 + 0.1 * i) * t + 0.002 * t**2, 200.0)
    return out


CUTOFFS = [round(0.30 + 0.01 * i, 2) for i in range(66)]  # 0.30 .. 0.95


@pytest.mark.req("FR-010-31")
def test_chronos_bolt_that_fails_to_export_becomes_precompute_with_baked_forecasts_while_tcn_and_patchtst_stay_live(
    tmp_path: Path,
) -> None:
    def raising(model, arm, out_dir, *, golden_contexts):
        raise RuntimeError("dynamo export failed: unsupported operator")

    jobs = {
        "tcn": {"model": models.build_model("tcn", seed=1).eval(), "contexts": _golden()},
        "patchtst": {"model": models.build_model("patchtst", seed=1).eval(), "contexts": _golden()},
        "chronos_bolt_fine_tuned": {
            "model": models.build_model("tcn", seed=2).eval(),
            "contexts": _golden(),
            "exporter": raising,
        },
        "chronos_bolt_zero_shot": {"model": None, "contexts": _golden()},
    }
    windows = _windows()
    rep = export.export_all(jobs, out_dir=tmp_path, windows=windows, cutoffs=CUTOFFS)
    assert rep.arms["tcn"]["lane"] == rep.arms["patchtst"]["lane"] == "LIVE"
    assert rep.arms["tcn"]["onnx_path"]
    assert Path(rep.arms["tcn"]["onnx_path"]).is_file()
    ft = rep.arms["chronos_bolt_fine_tuned"]
    assert ft["lane"] == "PRECOMPUTE"
    assert "dynamo export failed" in ft["reason"]
    assert ft["onnx_path"] is None
    baked = json.loads(Path(ft["baked_path"]).read_text(encoding="utf-8"))
    assert set(baked) == set(windows)  # every published event
    for per_event in baked.values():
        assert {float(c) for c in per_event} == set(CUTOFFS)  # the whole cut-off grid
    zs = rep.arms["chronos_bolt_zero_shot"]
    assert zs["lane"] == "PRECOMPUTE"
    assert "baked forecasts only" in zs["reason"]
    assert zs["onnx_path"] is None
    assert any("dynamo export failed" in note for note in rep.model_card_notes)


@pytest.mark.req("FR-010-31")
def test_chronos_bolt_that_misses_parity_is_precompute_with_the_reason(tmp_path: Path) -> None:
    def perturbed(model, arm, out_dir, *, golden_contexts):
        # an export of a different set of weights than the model it claims to be: its parity against `model` cannot pass
        other = models.build_model("tcn", seed=99).eval()
        res = export.export_forecaster(other, arm, out_dir, golden_contexts=golden_contexts)
        torch_fn = lambda c: model(torch.from_numpy(c)).detach().numpy()  # noqa: E731
        sess = ort.InferenceSession(str(res.onnx_path), providers=["CPUExecutionProvider"])
        rep = export.check_parity(torch_fn, lambda c: sess.run(None, {"context": c})[0], golden_contexts)
        if not rep["passed"]:
            raise export.ParityError(f"parity missed: max abs {rep['max_abs']:.3g}")
        return res

    jobs = {
        "chronos_bolt_fine_tuned": {
            "model": models.build_model("tcn", seed=2).eval(),
            "contexts": _golden(),
            "exporter": perturbed,
        }
    }
    rep = export.export_all(jobs, out_dir=tmp_path, windows=_windows(1), cutoffs=CUTOFFS)
    ft = rep.arms["chronos_bolt_fine_tuned"]
    assert ft["lane"] == "PRECOMPUTE"
    assert "parity" in ft["reason"]
    assert Path(ft["baked_path"]).is_file()
    assert any("parity" in note for note in rep.model_card_notes)


@pytest.mark.req("FR-010-31")
def test_a_clean_run_has_no_precompute_note_for_the_live_arms(tmp_path: Path) -> None:
    jobs = {"tcn": {"model": models.build_model("tcn", seed=1).eval(), "contexts": _golden()}}
    rep = export.export_all(jobs, out_dir=tmp_path, windows=_windows(1), cutoffs=CUTOFFS)
    assert rep.arms["tcn"] == {
        "lane": "LIVE",
        "reason": None,
        "onnx_path": rep.arms["tcn"]["onnx_path"],
        "baked_path": None,
    }
    assert rep.model_card_notes == []
