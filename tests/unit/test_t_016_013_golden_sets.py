"""T-016-013: post-processed graphs, golden sets and their guards (unit, hostile).

Requirements: FR-016-05, FR-016-06, FR-016-07.

Spec: specs/016-export-acceleration/spec.md
- FR-016-05: where a graph has an in-graph post-processor (top-K, box scaling) layer 1 compares the `parity` variant,
  exported from the same weights without the post-processor, and the deployed graph reproduces the PyTorch
  post-processed task metric on the golden set within 0.1 percentage point;
- FR-016-06: the golden set holds >= 200 inputs drawn (seeded) from validation or held-out data, never from training
  data, listed by SHA-256 in the parity report (DC-016-03);
- FR-016-07: fewer than 200 inputs, a non-finite input or reference output, or an input shape or dtype that differs
  from the graph's declared input makes the parity stage refuse with `golden-invalid` and the reason.
plan.md test strategy rows FR-016-05 (two-query tied-score fixture), FR-016-06 (golden list with SHA-256, provenance
split), FR-016-07 (199 inputs, a NaN input, a wrong shape).

Oracles (hand calculation and reference implementations):
- SHA-256 digests by `hashlib` over the raw C-contiguous array bytes (written here);
- the DC-016-03 `golden_set` definition validated with `jsonschema` against the spec's draft schema
  `specs/016-export-acceleration/contracts/export-parity-report.schema.json` (>= 200 unique digests, split in
  {validation, held-out});
- top-K and the tied-score behaviour: `torch.topk` on the PyTorch module is the reference; the structural facts
  checked with `onnx` (the parity graph has no TopK node, the deployed graph has one);
- the 0.1 pp bound on dyadic percentages (50.0 vs 50.09375 passes, 50.125 fails; both differences are exact in
  binary64).

Expected public API (`pipeline/` environment):
module `pitstudio_pipeline.export.golden`
    class GoldenInvalid(Exception)    # `.code == "golden-invalid"`, `.reason: str`; str(exc) contains both
    select_golden_inputs(pool: Sequence[Mapping[str, str]], *, split: str, n: int = 200, seed: int) -> list[str]
        `pool` items are {"sha256": hex, "split": "train" | "validation" | "held-out"}; returns the `n` unique digests
        drawn with numpy `default_rng(seed)` from the items whose split equals `split` (split must be "validation" or
        "held-out"; the same pool and seed give the same list; training items are never returned); raises
        GoldenInvalid for split "train", n < 200 or fewer than n eligible items.
    golden_set_record(golden_id: str, split: str, inputs: Sequence[np.ndarray]) -> dict
        the DC-016-03 `golden_set` object {"id", "split", "inputs": [sha256 of the raw C-contiguous bytes of each
        input, in order]}; raises GoldenInvalid for a split other than validation / held-out and for duplicate inputs.
    validate_golden(inputs: Sequence[np.ndarray], references: Sequence[Sequence[np.ndarray]], *,
                    input_shape: tuple[int, ...], input_dtype: str) -> None
        raises GoldenInvalid for: fewer than 200 inputs; len(references) != len(inputs); a non-finite value in any
        input or reference output; an input whose shape differs from `input_shape` or dtype name from `input_dtype`.
module `pitstudio_pipeline.export.variants`
    export_variants(backbone, postprocessor, example_inputs: tuple, config: dict, out_dir: Path)
        -> dict[str, ExportResult | None]
        keys "deployed" (postprocessor(backbone(x)) exported as in onnx_export.export_model) and "parity" (the backbone
        alone, same weights); "parity" is None when `config["post_processor_in_graph"]` is false, in which case
        "deployed" is the backbone.
module `pitstudio_pipeline.export.metric_gate`
    check_deployed_metric(pytorch_pct: float, deployed_pct: float, *, tol_pp: float = 0.1) -> MetricCheck
        MetricCheck.verdict "pass" | "fail" and .delta_pp = deployed_pct - pytorch_pct; pass iff |delta| <= tol_pp;
        non-finite or out-of-[0, 100] inputs raise ValueError.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.export.golden import (
    GoldenInvalid,
    golden_set_record,
    select_golden_inputs,
    validate_golden,
)
from pitstudio_pipeline.export.metric_gate import check_deployed_metric
from pitstudio_pipeline.export.variants import export_variants

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs" / "016-export-acceleration" / "contracts"
SHAPE = (3, 8, 8)


def _digest(i: int) -> str:
    return hashlib.sha256(f"sample-{i}".encode()).hexdigest()


def _pool(n_train: int = 600, n_val: int = 300, n_held: int = 300) -> list[dict[str, str]]:
    items, k = [], 0
    for split, count in (("train", n_train), ("validation", n_val), ("held-out", n_held)):
        for _ in range(count):
            items.append({"sha256": _digest(k), "split": split})
            k += 1
    return items


def _inputs(n: int, *, shape: tuple[int, ...] = SHAPE, dtype=np.float32) -> list[np.ndarray]:
    rng = np.random.default_rng(0)
    return [rng.standard_normal(shape).astype(dtype) for _ in range(n)]


def _refs(n: int) -> list[list[np.ndarray]]:
    rng = np.random.default_rng(1)
    return [[rng.standard_normal(5).astype(np.float32)] for _ in range(n)]


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-06: selection and the recorded list
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-06")
@pytest.mark.parametrize("split", ["validation", "held-out"])
def test_selection_draws_200_unique_inputs_only_from_the_requested_split(split: str) -> None:
    pool = _pool()
    by_digest = {p["sha256"]: p["split"] for p in pool}
    chosen = select_golden_inputs(pool, split=split, n=200, seed=11)
    assert len(chosen) == 200
    assert len(set(chosen)) == 200
    assert {by_digest[d] for d in chosen} == {split}


@pytest.mark.req("FR-016-06")
def test_selection_never_returns_training_data_and_refuses_the_train_split() -> None:
    pool = _pool()
    train = {p["sha256"] for p in pool if p["split"] == "train"}
    for split in ("validation", "held-out"):
        assert not set(select_golden_inputs(pool, split=split, seed=3)) & train
    with pytest.raises(GoldenInvalid) as info:
        select_golden_inputs(pool, split="train", seed=3)
    assert info.value.code == "golden-invalid"


@pytest.mark.req("FR-016-06")
def test_selection_is_seeded_same_seed_same_list_other_seed_other_list() -> None:
    pool = _pool()
    a = select_golden_inputs(pool, split="held-out", seed=5)
    assert a == select_golden_inputs(pool, split="held-out", seed=5)
    assert set(a) != set(select_golden_inputs(pool, split="held-out", seed=6))  # 200 of 300: collision is negligible


@pytest.mark.req("FR-016-06")
def test_selection_needs_at_least_200_requested_and_that_many_eligible() -> None:
    with pytest.raises(GoldenInvalid):
        select_golden_inputs(_pool(), split="held-out", n=199, seed=1)
    with pytest.raises(GoldenInvalid):
        select_golden_inputs(_pool(n_held=199), split="held-out", n=200, seed=1)
    assert len(select_golden_inputs(_pool(n_held=200), split="held-out", n=200, seed=1)) == 200


@pytest.mark.req("FR-016-06")
def test_golden_set_record_lists_the_sha256_of_each_input_and_validates_against_the_dc_016_03_schema() -> None:
    from jsonschema import Draft202012Validator

    inputs = _inputs(200)
    record = golden_set_record("b2-pit-golden-v1", "held-out", inputs)
    assert record["id"] == "b2-pit-golden-v1"
    assert record["split"] == "held-out"
    assert record["inputs"] == [hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest() for a in inputs]
    schema = json.loads((CONTRACTS / "export-parity-report.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator({"$ref": "#/$defs/golden_set", "$defs": schema["$defs"]})
    assert list(validator.iter_errors(record)) == []


@pytest.mark.req("FR-016-06")
def test_golden_set_record_refuses_a_training_split_and_duplicate_inputs() -> None:
    with pytest.raises(GoldenInvalid):
        golden_set_record("g", "train", _inputs(200))
    dup = _inputs(200)
    dup[10] = dup[3].copy()
    with pytest.raises(GoldenInvalid):
        golden_set_record("g", "validation", dup)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-07: hostile golden sets
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-07")
def test_a_valid_golden_set_of_200_inputs_is_accepted() -> None:
    assert validate_golden(_inputs(200), _refs(200), input_shape=SHAPE, input_dtype="float32") is None


@pytest.mark.req("FR-016-07")
def test_199_inputs_are_refused_with_golden_invalid_and_the_reason() -> None:
    with pytest.raises(GoldenInvalid) as info:
        validate_golden(_inputs(199), _refs(199), input_shape=SHAPE, input_dtype="float32")
    assert info.value.code == "golden-invalid"
    assert "golden-invalid" in str(info.value)
    assert "199" in info.value.reason


@pytest.mark.req("FR-016-07")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_a_non_finite_input_is_refused(bad: float) -> None:
    inputs = _inputs(200)
    inputs[17][0, 0, 0] = bad
    with pytest.raises(GoldenInvalid) as info:
        validate_golden(inputs, _refs(200), input_shape=SHAPE, input_dtype="float32")
    assert info.value.code == "golden-invalid"


@pytest.mark.req("FR-016-07")
@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_a_non_finite_reference_output_is_refused(bad: float) -> None:
    refs = _refs(200)
    refs[42][0][2] = bad
    with pytest.raises(GoldenInvalid) as info:
        validate_golden(_inputs(200), refs, input_shape=SHAPE, input_dtype="float32")
    assert info.value.code == "golden-invalid"


@pytest.mark.req("FR-016-07")
def test_an_input_with_the_wrong_shape_is_refused() -> None:
    inputs = _inputs(200)
    inputs[5] = np.zeros((3, 8, 9), dtype=np.float32)
    with pytest.raises(GoldenInvalid) as info:
        validate_golden(inputs, _refs(200), input_shape=SHAPE, input_dtype="float32")
    assert "shape" in info.value.reason


@pytest.mark.req("FR-016-07")
def test_an_input_with_the_wrong_dtype_is_refused() -> None:
    with pytest.raises(GoldenInvalid) as info:
        validate_golden(_inputs(200, dtype=np.float64), _refs(200), input_shape=SHAPE, input_dtype="float32")
    assert "dtype" in info.value.reason


@pytest.mark.req("FR-016-07")
def test_references_must_match_the_inputs_one_to_one() -> None:
    with pytest.raises(GoldenInvalid):
        validate_golden(_inputs(200), _refs(199), input_shape=SHAPE, input_dtype="float32")


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-05: the parity variant and the deployed-graph task metric
# ----------------------------------------------------------------------------------------------------------------------


def _backbone_and_topk():
    import torch

    torch.manual_seed(0)

    class Backbone(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.fc = torch.nn.Linear(6, 4)

        def forward(self, x):
            return self.fc(x)  # class scores (N, 4)

    class TopK(torch.nn.Module):
        def forward(self, scores):
            values, indices = torch.topk(scores, k=2, dim=-1)
            return values, indices

    return Backbone().eval(), TopK().eval(), (torch.zeros(2, 6),)


def _config(**over: object) -> dict:
    cfg = json.loads((CONTRACTS / "examples" / "export-config.valid-gns.json").read_text(encoding="utf-8"))
    cfg.update(over)
    return cfg


@pytest.mark.req("FR-016-05")
def test_parity_variant_has_no_post_processor_and_the_deployed_graph_has_it(tmp_path: Path) -> None:
    import onnx

    backbone, topk, example = _backbone_and_topk()
    out = export_variants(backbone, topk, example, _config(post_processor_in_graph=True), tmp_path)
    assert set(out) == {"deployed", "parity"}
    parity_ops = {n.op_type for n in onnx.load(out["parity"].path).graph.node}
    deployed_ops = {n.op_type for n in onnx.load(out["deployed"].path).graph.node}
    assert "TopK" not in parity_ops
    assert "TopK" in deployed_ops
    assert out["parity"].path != out["deployed"].path


@pytest.mark.req("FR-016-05")
def test_parity_variant_outputs_equal_the_backbone_raw_outputs_on_ort_cpu(tmp_path: Path) -> None:
    import onnxruntime as ort
    import torch

    backbone, topk, example = _backbone_and_topk()
    out = export_variants(backbone, topk, example, _config(post_processor_in_graph=True), tmp_path)
    x = np.random.default_rng(2).standard_normal((2, 6)).astype(np.float32)
    sess = ort.InferenceSession(str(out["parity"].path), providers=["CPUExecutionProvider"])
    got = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    with torch.no_grad():
        want = backbone(torch.from_numpy(x)).numpy()
    np.testing.assert_allclose(got, want, rtol=1e-3, atol=1e-5)


@pytest.mark.req("FR-016-05")
def test_tied_scores_make_the_deployed_index_output_ill_posed_but_the_parity_variant_is_exact(tmp_path: Path) -> None:
    """Two queries with tied scores: top-K indices of any two correct runtimes may differ, raw scores cannot."""
    import onnxruntime as ort
    import torch

    backbone, topk, example = _backbone_and_topk()
    with torch.no_grad():
        backbone.fc.weight.zero_()
        backbone.fc.bias.copy_(torch.tensor([0.5, 0.5, 0.25, 0.0]))  # every query: scores tie at 0.5 for classes 0, 1
    out = export_variants(backbone, topk, example, _config(post_processor_in_graph=True), tmp_path)
    x = np.zeros((2, 6), dtype=np.float32)
    parity = ort.InferenceSession(str(out["parity"].path), providers=["CPUExecutionProvider"])
    raw = parity.run(None, {parity.get_inputs()[0].name: x})[0]
    np.testing.assert_array_equal(raw, np.tile(np.float32([0.5, 0.5, 0.25, 0.0]), (2, 1)))  # hand values, exact


@pytest.mark.req("FR-016-05")
def test_without_an_in_graph_post_processor_only_the_deployed_variant_exists(tmp_path: Path) -> None:
    backbone, topk, example = _backbone_and_topk()
    out = export_variants(backbone, topk, example, _config(post_processor_in_graph=False), tmp_path)
    assert out["parity"] is None
    assert out["deployed"] is not None


@pytest.mark.req("FR-016-05")
def test_deployed_task_metric_within_0_1_pp_passes_and_beyond_fails() -> None:
    ok = check_deployed_metric(50.0, 50.09375)
    assert (ok.verdict, ok.delta_pp) == ("pass", 0.09375)
    low = check_deployed_metric(50.0, 49.90625)
    assert (low.verdict, low.delta_pp) == ("pass", -0.09375)
    bad = check_deployed_metric(50.0, 50.125)
    assert (bad.verdict, bad.delta_pp) == ("fail", 0.125)
    assert check_deployed_metric(50.0, 50.0).verdict == "pass"


@pytest.mark.req("FR-016-05")
@pytest.mark.parametrize(("pt", "dep"), [(float("nan"), 50.0), (50.0, float("inf")), (-1.0, 50.0), (50.0, 100.5)])
def test_deployed_metric_gate_refuses_non_finite_and_out_of_range_percentages(pt: float, dep: float) -> None:
    with pytest.raises(ValueError, match=r"."):
        check_deployed_metric(pt, dep)
