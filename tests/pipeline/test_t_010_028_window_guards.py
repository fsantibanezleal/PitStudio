"""T-010-028: hostile forecaster contexts in Python (PyTorch and ONNX Runtime); the C1 tab twin is
web/src/cases/c1/forecastGuards.test.ts.

Requirement: FR-010-29 ("If a forecaster (PyTorch, ONNX Runtime or the web engine `forecasters`) receives a context
whose length is
not 128, whose shape or dtype differs from `surrogate-io.schema.json`, that contains a non-finite value after
preprocessing, or that
has no positive velocity at all, then it shall return 'no forecast - <reason>' in the web app or raise
`InvalidWindowError` in
Python, and never a TTF").
Spec: specs/010-slope/spec.md section 3.3; DC-010-05 (input `context` float32 [1, 2, 128]); plan.md row FR-010-29
("invalid
contexts written in the test"). Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.infer`):
- `TorchForecaster(model)` and `OrtForecaster(onnx_path)`: callables `f(context) -> np.ndarray (1, 9, 64) float32`
  (the `model`
  argument of `pitstudio.slope.forecast.learned_forecast`); both raise `InvalidWindowError` (`pitstudio.slope.errors`,
  a ValueError)
  before running the network for: a context that is not a NumPy array of dtype float32 and shape (1, 2, 128) (any
  other length,
  rank, channel count, dtype), a non-finite value in either channel, a mask channel (channel 1) that is all zero (no
  valid block:
  no positive velocity at all). The message names the property (length, shape, dtype, non-finite, positive velocity).
- `learned_forecast(forecaster, window)` returns a TTF only for a valid context; for a window without positive
  velocity it raises
  InvalidWindowError from the context builder and the network is never called.

Oracles: invalid contexts written in the test (one per class, 24 in all, each run against both back ends); a spy that
proves the
network was not called; the ONNX file is exported in the test with `torch.onnx.export` (opset 17) from the product's
TCN so that
the two back ends are the same graph.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from pitstudio.slope import forecast, preprocess  # noqa: E402
from pitstudio.slope.errors import InvalidWindowError  # noqa: E402
from pitstudio_pipeline.slope import infer, models  # noqa: E402

torch = pytest.importorskip("torch")  # first-party imports come first: the red failure is a missing module
ort = pytest.importorskip("onnxruntime")


def _valid() -> np.ndarray:
    x = np.zeros((1, 2, 128), dtype=np.float32)
    x[0, 0] = 1.0 + 0.001 * np.arange(128)
    x[0, 1] = 1.0
    return x


def _bad_cases():
    nan = _valid()
    nan[0, 0, 7] = np.nan
    inf = _valid()
    inf[0, 0, 9] = np.inf
    ninf = _valid()
    ninf[0, 1, 3] = -np.inf
    nomask = _valid()
    nomask[0, 1] = 0.0
    return [
        ("length-127", np.zeros((1, 2, 127), dtype=np.float32), "length"),
        ("length-129", np.zeros((1, 2, 129), dtype=np.float32), "length"),
        ("length-0", np.zeros((1, 2, 0), dtype=np.float32), "length"),
        ("length-256", np.zeros((1, 2, 256), dtype=np.float32), "length"),
        ("rank-2", np.zeros((2, 128), dtype=np.float32), "shape"),
        ("rank-4", np.zeros((1, 1, 2, 128), dtype=np.float32), "shape"),
        ("channels-1", np.zeros((1, 1, 128), dtype=np.float32), "shape"),
        ("channels-3", np.zeros((1, 3, 128), dtype=np.float32), "shape"),
        ("batch-2", np.zeros((2, 2, 128), dtype=np.float32), "shape"),
        ("dtype-float64", _valid().astype(np.float64), "dtype"),
        ("dtype-int32", _valid().astype(np.int32), "dtype"),
        ("dtype-float16", _valid().astype(np.float16), "dtype"),
        ("not-an-array-list", _valid().tolist(), "dtype"),
        ("not-an-array-none", None, "dtype"),
        ("nan", nan, "non-finite"),
        ("inf", inf, "non-finite"),
        ("minus-inf-in-mask", ninf, "non-finite"),
        ("no-positive-velocity-mask-zero", nomask, "positive velocity"),
    ]


@pytest.fixture(scope="module")
def backends(tmp_path_factory):
    model = models.build_model("tcn", seed=0).eval()
    path = tmp_path_factory.mktemp("onnx") / "tcn.onnx"
    torch.onnx.export(
        model,
        (torch.zeros(1, 2, 128),),
        str(path),
        opset_version=17,
        input_names=["context"],
        output_names=["quantiles"],
        dynamo=False,
    )
    return {"torch": infer.TorchForecaster(model), "ort": infer.OrtForecaster(path)}, model


@pytest.mark.req("FR-010-29")
@pytest.mark.parametrize("backend", ["torch", "ort"])
def test_a_valid_context_gives_the_9_by_64_quantiles_on_both_backends(backends, backend) -> None:
    fs, _ = backends
    out = fs[backend](_valid())
    assert out.shape == (1, 9, 64)
    assert out.dtype == np.float32
    assert np.isfinite(out).all()


@pytest.mark.req("FR-010-29")
def test_the_two_backends_agree_on_a_valid_context(backends) -> None:
    fs, _ = backends
    np.testing.assert_allclose(fs["torch"](_valid()), fs["ort"](_valid()), rtol=1e-3, atol=1e-5)


@pytest.mark.req("FR-010-29")
@pytest.mark.parametrize("backend", ["torch", "ort"])
@pytest.mark.parametrize(("name", "context", "word"), _bad_cases(), ids=[c[0] for c in _bad_cases()])
def test_a_hostile_context_raises_invalid_window_error_naming_the_property(
    backends, backend, name, context, word
) -> None:
    fs, _ = backends
    with pytest.raises(InvalidWindowError) as exc:
        fs[backend](context)
    assert word in str(exc.value), (name, str(exc.value))
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-010-29")
def test_the_network_is_never_run_for_a_hostile_context(backends) -> None:
    _, model = backends
    calls: list[int] = []
    model.register_forward_hook(lambda *_: calls.append(1))
    f = infer.TorchForecaster(model)
    for _name, context, _word in _bad_cases():
        with pytest.raises(InvalidWindowError):
            f(context)
    assert calls == []
    f(_valid())
    assert calls == [1]


@pytest.mark.req("FR-010-29")
def test_a_window_with_no_positive_velocity_gives_no_ttf(backends) -> None:
    fs, _ = backends
    t = np.linspace(0.0, 100.0, 401)
    window = preprocess.preprocess_window(t, -t, 100.0)  # a wall moving back
    seen: list[int] = []

    def spy(context):
        seen.append(1)
        return fs["torch"](context)

    with pytest.raises(InvalidWindowError):
        forecast.learned_forecast(spy, window)
    assert seen == []
