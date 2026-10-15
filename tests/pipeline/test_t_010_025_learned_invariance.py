"""T-010-025 (learned arms): time and displacement invariances of the TCN and PatchTST forecasts (random fixed weights).

Requirements: P-010-09, P-010-10.
Spec: specs/010-slope/spec.md section 4 ("learned: |de| <= 1e-5"); plan.md "Learned-model invariance |de| <= 1e-5":
inputs are rescaled
by the context's mean |y| in fp32, a forward pass of <= 1 M parameters changes outputs by <= 1e-6 relative under an
exact input
rescaling, and the read-out maps that to <= 1e-5 of the lead. The baselines are in
tests/metamorphic/test_t_010_025_ttf_invariance.py.
Runs in the `pipeline/` environment (PyTorch).

Expected API: `pitstudio_pipeline.slope.models.build_model` and `pitstudio_pipeline.slope.infer.TorchForecaster`
(T-010-027/028),
`pitstudio.slope.forecast.learned_forecast` (T-010-027), `pitstudio.slope.evaluate.relative_error` (T-010-030). Each
arm is a freshly
built network with a fixed seed (no training): the relations hold for any weights because the forecast depends on the
window only
through the context normalised by its mean |y|.

Relations (noisy Voight events, cut-offs 0.5 and 0.8; a window the forecaster cannot use is skipped):
- time translation: adding Delta (|Delta| <= 1e6 h) to every timestamp shifts t_hat_f by Delta (|error| <= 1e-5 of the
  lead time t_f - t_c,
  plus 1e-12 |Delta| of timestamp quantisation);
- time scaling about t_0 by k in [0.01, 100]: the relative error e is unchanged (|de| <= 1e-5);
- displacement scaling by k in [1e-3, 1e3]: t_hat_f is unchanged (|de| <= 1e-5).
Oracle: the invariance relations themselves.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_ttf_ref as k  # noqa: E402
from pitstudio.slope import evaluate, forecast, preprocess  # noqa: E402
from pitstudio.slope.errors import InvalidWindowError  # noqa: E402
from pitstudio_pipeline.slope import infer, models  # noqa: E402

torch = pytest.importorskip("torch")

PROP = settings(max_examples=25, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
ARMS = ["tcn", "patchtst"]
_FORECASTERS: dict = {}


def _forecaster(arm):
    if arm not in _FORECASTERS:
        _FORECASTERS[arm] = infer.TorchForecaster(models.build_model(arm, seed=4).eval())
    return _FORECASTERS[arm]


@st.composite
def _event(draw):
    n = 10 * draw(st.integers(100, 250))
    s = k.terminal_series(
        alpha=draw(st.floats(1.7, 2.3)),
        v_onset_per_day=10.0 ** draw(st.floats(-1.0, 1.0)),
        terminal_h=draw(st.floats(24.0, 720.0)),
        steady_fraction=draw(st.floats(0.1, 0.5)),
        n=n,
    )
    noise = 2e-3 * s["omega"][-1] * np.random.default_rng(draw(st.integers(0, 2**32 - 1))).standard_normal(n)
    return s["t"], s["omega"] + noise, s["t_f"], draw(st.sampled_from([0.5, 0.8]))


def _ttf(arm, t, omega, cutoff):
    idx = round(cutoff * len(t))
    t_c = float(t[idx])
    window = preprocess.preprocess_window(t[: idx + 1], omega[: idx + 1], t_c)
    try:
        return t_c, forecast.learned_forecast(_forecaster(arm), window).t_hat_f
    except InvalidWindowError:
        assume(False)
        raise


@pytest.mark.req("P-010-09")
@pytest.mark.parametrize("arm", ARMS)
@PROP
@given(_event(), st.floats(-1e6, 1e6))
def test_adding_a_constant_to_every_timestamp_shifts_the_learned_forecast_by_it(arm, ev, delta) -> None:
    t, omega, t_f, c = ev
    t_c, base = _ttf(arm, t, omega, c)
    _, moved = _ttf(arm, t + delta, omega, c)
    lead = t_f - t_c
    assert moved - delta == pytest.approx(base, abs=1e-5 * lead + 1e-12 * abs(delta))


@pytest.mark.req("P-010-09")
@pytest.mark.parametrize("arm", ARMS)
@PROP
@given(_event(), st.floats(0.01, 100.0))
def test_scaling_the_time_axis_leaves_the_learned_relative_error_unchanged(arm, ev, scale) -> None:
    t, omega, t_f, c = ev
    t0 = t[0]
    t_c, base = _ttf(arm, t, omega, c)
    t_c2, scaled = _ttf(arm, t0 + scale * (t - t0), omega, c)
    e1 = evaluate.relative_error(base, t_f, t_c)
    e2 = evaluate.relative_error(scaled, t0 + scale * (t_f - t0), t_c2)
    assert abs(e2 - e1) <= 1e-5


@pytest.mark.req("P-010-10")
@pytest.mark.parametrize("arm", ARMS)
@PROP
@given(_event(), st.floats(1e-3, 1e3))
def test_scaling_the_displacement_leaves_the_learned_forecast_unchanged(arm, ev, scale) -> None:
    t, omega, t_f, c = ev
    t_c, base = _ttf(arm, t, omega, c)
    _, scaled = _ttf(arm, t, scale * omega, c)
    assert abs(evaluate.relative_error(scaled, t_f, t_c) - evaluate.relative_error(base, t_f, t_c)) <= 1e-5
