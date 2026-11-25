"""T-010-025: time and displacement invariances of the inverse-velocity and Bayesian forecasts.

Requirements: P-010-09, P-010-10.
Spec: specs/010-slope/spec.md section 4; plan.md "Numerical cores" (preprocessor + baselines + read-out) and the
"Learned-model invariance |de| <= 1e-5" tolerance note. The learned arms are covered by the pipeline-environment twin
`tests/pipeline/test_t_010_025_learned_invariance.py` (PyTorch, random fixed weights).

Expected API: `pitstudio.slope.preprocess.preprocess_window`, `pitstudio.slope.baselines.inverse_velocity` and
`bayesian_ttf` (T-010-023, T-010-024), `pitstudio.slope.evaluate.relative_error(t_hat, t_f, t_c)` (T-010-030). A
window the
baselines cannot use raises `InvalidWindowError` and is skipped by the property (no relation is claimed there).

Relations (for a noisy Voight event, cut-offs 0.5 and 0.8, both baselines, same Bayesian seed):
- time translation: adding Delta (|Delta| <= 1e6 h) to every timestamp shifts t_hat_f by Delta (|error| <= span x
  (1e-9 + 1e-12 |Delta|): the spec's 1e-9 plus the float64
  quantisation of the shifted timestamps; the cap t_c + 1,024 delta moves with it);
- time scaling about t_0 by k in [0.01, 100]: the relative error e = |t_hat - t_f| / (t_f - t_c) is unchanged (1e-9);
- displacement scaling by k in [1e-3, 1e3]: t_hat_f is unchanged (rtol 1e-9 of the span).
No absolute oracle is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_ttf_ref as k
from pitstudio.slope import baselines, evaluate, preprocess
from pitstudio.slope.errors import InvalidWindowError

PROP = settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))


@st.composite
def _event(draw):
    n = 10 * draw(st.integers(100, 300))
    s = k.terminal_series(
        alpha=draw(st.floats(1.7, 2.3)),
        v_onset_per_day=10.0 ** draw(st.floats(-1.0, 1.0)),
        terminal_h=draw(st.floats(24.0, 720.0)),
        steady_fraction=draw(st.floats(0.1, 0.5)),
        n=n,
    )
    noise = 2e-3 * s["omega"][-1] * np.random.default_rng(draw(st.integers(0, 2**32 - 1))).standard_normal(n)
    return s["t"], s["omega"] + noise, s["t_f"], draw(st.sampled_from([0.5, 0.8]))


def _forecasts(t, omega, cutoff):
    """t_c and the baselines' t_hat_f for the observed window up to the sample at the cut-off (n is a multiple of
    10)."""
    idx = round(cutoff * len(t))
    t_c = float(t[idx])
    w = preprocess.preprocess_window(t[: idx + 1], omega[: idx + 1], t_c)
    try:
        return t_c, {
            "inverse_velocity": baselines.inverse_velocity(w).t_hat_f,
            "bayesian_ttf": baselines.bayesian_ttf(w, seed=11).t_hat_f,
        }
    except InvalidWindowError:
        assume(False)
        raise


@pytest.mark.req("P-010-09")
@PROP
@given(_event(), st.floats(-1e6, 1e6))
def test_adding_a_constant_to_every_timestamp_shifts_every_forecast_by_it(ev, delta) -> None:
    t, omega, t_f, c = ev
    span = t_f - t[0]
    _, base = _forecasts(t, omega, c)
    _, moved = _forecasts(t + delta, omega, c)
    for method in base:
        # spec tolerance 1e-9 of the span plus the quantisation of the shifted timestamps themselves: at |delta| = 1e6
        # h the
        # float64 spacing (1.2e-10 h) is 1e-9 of a sample step and the extrapolation to the root amplifies it ~100x;
        # measured on 80
        # noisy events: 3e-9 of the span at 1e5 h, 1.8e-7 at 1e6 h, so span x (1e-9 + 1e-12 |delta|) (a finding, see
        # the report)
        tol = span * (1e-9 + 1e-12 * abs(delta))
        assert moved[method] - delta == pytest.approx(base[method], abs=tol), method


@pytest.mark.req("P-010-09")
@PROP
@given(_event(), st.floats(0.01, 100.0))
def test_scaling_the_time_axis_about_t0_leaves_the_relative_error_unchanged(ev, scale) -> None:
    t, omega, t_f, c = ev
    t0 = t[0]
    t_c, base = _forecasts(t, omega, c)
    t_c2, scaled = _forecasts(t0 + scale * (t - t0), omega, c)
    for method in base:
        e1 = evaluate.relative_error(base[method], t_f, t_c)
        e2 = evaluate.relative_error(scaled[method], t0 + scale * (t_f - t0), t_c2)
        assert e2 == pytest.approx(e1, rel=1e-9, abs=1e-9), method


@pytest.mark.req("P-010-10")
@PROP
@given(_event(), st.floats(1e-3, 1e3))
def test_scaling_the_displacement_leaves_every_forecast_unchanged(ev, scale) -> None:
    t, omega, t_f, c = ev
    span = t_f - t[0]
    _, base = _forecasts(t, omega, c)
    _, scaled = _forecasts(t, scale * omega, c)
    for method in base:
        assert scaled[method] == pytest.approx(base[method], abs=1e-9 * span, rel=1e-9), method
