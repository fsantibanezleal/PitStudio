"""T-017-015: hostile meta-model inputs in Python and ONNX Runtime (pipeline; the web engine is in
web/src/cases/d2/metaModelGuards.test.ts).

Requirements: FR-017-11.

Spec: specs/017-planning-survey/spec.md FR-017-11: if the meta-model (Python, ONNX Runtime or the web engine
`meta-model`) receives an input row whose width or order differs from DC-011-02 or that contains a non-finite value,
it raises `InvalidInputError` (Python) or shows "no answer -- <reason>" (web) and returns no output. plan.md test
strategy row FR-017-11: invalid rows written in the test.

Oracles: the input vector of DC-011-02 as in the spec 011 valid meta-model example (15 columns in a fixed order, `x` of
shape [B, 15]); hand-written invalid rows: width 14 and 16, a one-dimensional row, an empty batch, NaN, +inf, -inf,
a permutation of two columns (given as column names), a string or object dtype; a hand-built ONNX graph (`onnx.helper`,
x[B, 15] -> MatMul(W[15, 3]) -> y) as the ONNX Runtime model, whose output for a valid row is the matrix product
computed with numpy in the test.

Expected public API (module `pitstudio_pipeline.mine_to_mill.model_io`, `pipeline/` environment):
    INPUT_NAMES: tuple[str, ...]            # the 15 section-7 names of T-017-010 (same order as DC-011-02)
    class InvalidInputError(ValueError)     # `.reason: str`
    check_input_rows(rows, *, names: Sequence[str] | None = None) -> np.ndarray
        returns float64 (n, 15) for a valid float matrix with n >= 1; raises InvalidInputError for a non-numeric
        dtype, a number of dimensions other than 2, a width other than 15, an empty batch, a non-finite value, and
        (when `names` is given) names that are not exactly INPUT_NAMES in order. The reason names the cause
        ("width", "order", "finite", "dtype", "empty" or "shape").
    class OrtMetaModel: OrtMetaModel(onnx_path: Path); predict(rows, *, names=None) -> np.ndarray (n, 3)
        validates with check_input_rows BEFORE running the session; the session is never called for a bad input. The
        `onnxruntime.InferenceSession` is kept in the attribute `session` (its `run` is the only call that executes
        the graph).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.mine_to_mill.model_io import INPUT_NAMES, InvalidInputError, OrtMetaModel, check_input_rows

W = np.arange(45, dtype=np.float32).reshape(15, 3) / 10.0


def _model(tmp_path: Path) -> Path:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    node = helper.make_node("MatMul", ["x", "W"], ["y"])
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, ["B", 15])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, ["B", 3])
    graph = helper.make_graph([node], "g", [x], [y], initializer=[numpy_helper.from_array(W, "W")])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 10
    path = tmp_path / "meta.onnx"
    onnx.save(model, path)
    return path


def _ok(n: int = 2) -> np.ndarray:
    return np.random.default_rng(0).uniform(1.0, 10.0, (n, 15))


@pytest.mark.req("FR-017-11")
def test_the_input_vector_has_the_15_names_of_the_io_description() -> None:
    assert len(INPUT_NAMES) == len(set(INPUT_NAMES)) == 15


@pytest.mark.req("FR-017-11")
def test_a_valid_batch_passes_and_is_returned_as_float64() -> None:
    out = check_input_rows(_ok(3).astype(np.float32), names=INPUT_NAMES)
    assert out.shape == (3, 15)
    assert out.dtype == np.float64
    assert check_input_rows(_ok(1)).shape == (1, 15)


@pytest.mark.req("FR-017-11")
@pytest.mark.parametrize(("width", "word"), [(14, "width"), (16, "width"), (0, "width"), (30, "width")])
def test_a_wrong_width_is_refused(width: int, word: str) -> None:
    with pytest.raises(InvalidInputError) as info:
        check_input_rows(np.ones((2, width)))
    assert word in info.value.reason


@pytest.mark.req("FR-017-11")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_a_non_finite_value_is_refused_anywhere_in_the_batch(bad: float) -> None:
    rows = _ok(5)
    rows[4, 14] = bad
    with pytest.raises(InvalidInputError) as info:
        check_input_rows(rows)
    assert "finite" in info.value.reason


@pytest.mark.req("FR-017-11")
def test_columns_in_another_order_are_refused() -> None:
    swapped = list(INPUT_NAMES)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(InvalidInputError) as info:
        check_input_rows(_ok(), names=swapped)
    assert "order" in info.value.reason
    with pytest.raises(InvalidInputError):
        check_input_rows(_ok(), names=list(INPUT_NAMES)[:-1])
    with pytest.raises(InvalidInputError):
        check_input_rows(_ok(), names=[*INPUT_NAMES[:-1], "unknown_column"])


@pytest.mark.req("FR-017-11")
@pytest.mark.parametrize(
    "rows",
    [
        np.ones(15),
        np.ones((2, 15, 1)),
        np.ones((0, 15)),
        np.array([["a"] * 15]),
        np.array([[None] * 15], dtype=object),
        np.ones((2, 15), dtype=bool),
        "not an array",
        None,
    ],
    ids=["1-d", "3-d", "empty", "strings", "objects", "bool", "text", "none"],
)
def test_other_malformed_batches_are_refused(rows) -> None:
    with pytest.raises(InvalidInputError):
        check_input_rows(rows)


@pytest.mark.req("FR-017-11")
def test_the_onnx_runtime_model_answers_a_valid_row_with_the_matrix_product(tmp_path: Path) -> None:
    model = OrtMetaModel(_model(tmp_path))
    rows = _ok(4)
    np.testing.assert_allclose(model.predict(rows, names=INPUT_NAMES), rows.astype(np.float32) @ W, rtol=1e-5)


@pytest.mark.req("FR-017-11")
@pytest.mark.parametrize(
    "rows",
    [np.full((1, 15), np.nan), np.ones((1, 14)), np.ones((1, 16)), np.full((2, 15), np.inf), np.ones((0, 15))],
    ids=["nan", "narrow", "wide", "inf", "empty"],
)
def test_the_onnx_runtime_model_refuses_bad_rows_and_never_runs_the_session(tmp_path: Path, rows: np.ndarray) -> None:
    model = OrtMetaModel(_model(tmp_path))
    calls = {"n": 0}

    class Spy:
        def run(self, *a, **k):
            calls["n"] += 1
            raise AssertionError("the session must not run")

    model.session = Spy()  # the wrapper exposes its session as an attribute
    with pytest.raises(InvalidInputError):
        model.predict(rows)
    assert calls["n"] == 0
