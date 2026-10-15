"""T-010-027 (root part): the 128-value context of the learned forecasters and the forecast loop with the shared
read-out.

Requirement: FR-010-21 (and the read-out of FR-010-22 applied inside the loop).
Spec: specs/010-slope/spec.md section 3.3 (FR-010-21: "a context of 128 values of y (block means of 4 consecutive
preprocessed
values, masked values forward-filled, scaled by the context's mean |y|; a mask channel for TCN and PatchTST) to the
quantiles
0.1, 0.2, ..., 0.9 of the next 64 steps of 4 delta, extend the forecast by feeding back the median up to 4 blocks (the
cap of 1,024
delta)"); DC-010-05 example `surrogate-io.valid-forecaster.json` (input `context` float32 [1, 2, 128], output
`quantiles`
float32 [1, 9, 64], normalisation outside the graph). The model classes and training are tested in the pipeline
environment
(tests/pipeline/test_t_010_027_forecasters.py); this file needs no PyTorch: the model is a callable.

Expected API (numpy only; shared with the `forecasters` web worker and the PyTorch / ONNX Runtime wrappers):
- module `pitstudio.slope.context`: `build_context(window) -> Context` with `context` (float32, shape (2, 128):
  channel 0 the
  scaled inverse velocity, channel 1 the mask) and `scale` (float, the mean |y| of the 128 filled block values, > 0).
  Block b is the mean of the valid y values among window samples 4b .. 4b + 3; a block with no valid sample is masked
  (mask 0) and
  filled with the previous block's value (a leading masked block takes the first valid value: the spec says only
  "forward-filled",
  see the report); `context[0] = filled / scale`; mean |context[0]| = 1; `context[1]` is 1 for blocks with data, 0
  otherwise.
  InvalidWindowError (`pitstudio.slope.errors`) when the window has no positive velocity at all or a non-finite filled
  value.
- module `pitstudio.slope.forecast`: `learned_forecast(model, window, *, max_blocks=4) -> LearnedForecast`, where
  `model(context)` maps a float32 array (1, 2, 128) to float32 quantiles (1, 9, 64) in the units of the scaled
  context. The
  loop: call the model on the window's context; the quantile paths times `scale` are the forecast of the next 64 steps
  of 4 delta,
  at times t_c + k 4 delta, k = 1 .. 64; while the median path has no step <= 0 and fewer than `max_blocks` blocks
  have been
  produced, the next context is the previous channel 0 shifted left by 64 with the 64 median values (scaled units)
  appended
  (mask channel 1 for the appended values, the previous mask shifted likewise) and the model is called again; the
  quantile paths
  of the blocks are concatenated. The TTF read-out of `pitstudio.slope.readout` is applied to the concatenated median
  path and,
  for the 80 % interval, to the 0.1 and 0.9 paths, with the cap time t_c + 1,024 delta. Result attributes: `outcome`,
  `t_hat_f`,
  `scored_at_cap`, `interval_80` (None or a (lower, upper) pair of t values, "no failure" ends at the cap),
  `n_model_calls`,
  `times` (the step times), `median_y` (the median path in the units of y: scaled values x scale). ValueError for
  max_blocks outside 1 .. 4; a model output of the wrong shape or with a non-finite value raises InvalidWindowError.

Oracles: hand construction (a window of constant velocity has a constant y: its blocks are 1 after scaling), hand
block means,
fake models with closed-form paths whose zero crossing is known (k = 50, 40 and 60 steps; slopes -0.004 and -0.0045
per step).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pitstudio.slope import context as ctx_mod
from pitstudio.slope import forecast, preprocess
from pitstudio.slope.errors import InvalidWindowError

T = np.linspace(0.0, 200.0, 801)


def _window(omega, t_c=200.0):
    return preprocess.preprocess_window(T, omega, t_c)


def _constant_velocity_window():
    return _window(0.5 * T)  # v = 0.5 mm/h everywhere: y = 2 h/mm, constant (first/last 4 samples masked)


# ---------------------------------------------------------------------------------------------------------------------
# context


@pytest.mark.req("FR-010-21")
def test_a_constant_velocity_window_gives_unit_blocks_a_unit_scale_factor_and_the_mask_channel() -> None:
    c = ctx_mod.build_context(_constant_velocity_window())
    assert c.context.dtype == np.float32
    assert c.context.shape == (2, 128)
    assert c.scale == pytest.approx(2.0, rel=1e-6)  # mean |y| = 2 h/mm
    assert c.context[0] == pytest.approx(
        1.0, rel=1e-6
    )  # every block is 2 / 2, the masked end blocks filled by their neighbours
    mask = c.context[1]
    assert set(np.unique(mask)) <= {0.0, 1.0}
    assert mask[0] == 0.0  # samples 0..3 have no velocity (the 9-point window is incomplete)
    assert mask[127] == 0.0  # samples 508..511 likewise
    assert mask[1:127].min() == 1.0


@pytest.mark.req("FR-010-21")
def test_block_values_are_the_means_of_four_consecutive_inverse_velocities_by_hand() -> None:
    # v(t) = 0.2 + 0.001 t  ->  y = 1 / v; displacement 0.2 t + 0.0005 t^2 (a quadratic: the LS velocity is exact)
    w = _window(0.2 * T + 0.0005 * T**2)
    c = ctx_mod.build_context(w)
    y = 1.0 / (0.2 + 0.001 * w.t)
    for b in (1, 17, 64, 100, 126):
        mean = float(y[4 * b : 4 * b + 4].mean())
        assert c.context[0, b] * c.scale == pytest.approx(mean, rel=1e-5), b
    assert float(np.abs(c.context[0]).mean()) == pytest.approx(1.0, rel=1e-5)


@pytest.mark.req("FR-010-21")
def test_masked_blocks_are_filled_from_the_previous_block_and_flagged_in_the_mask_channel() -> None:
    t = np.linspace(0.0, 200.0, 801)
    omega = np.where(
        t < 100.0, 0.5 * t, np.where(t < 140.0, 50.0, 50.0 + 0.5 * (t - 140.0))
    )  # a plateau: v = 0, masked
    w = preprocess.preprocess_window(t, omega, 200.0)
    c = ctx_mod.build_context(w)
    mask = c.context[1]
    plateau = [b for b in range(128) if not np.isfinite(w.y[4 * b : 4 * b + 4]).any()]
    assert len(plateau) >= 15
    inner = [b for b in plateau if 2 <= b <= 125]
    assert inner
    for b in inner:
        assert mask[b] == 0.0
        # forward fill: a masked block repeats the previous block (itself filled when several in a row are masked)
        assert c.context[0, b] == pytest.approx(c.context[0, b - 1], rel=1e-6)
    assert np.all(np.isfinite(c.context))


@pytest.mark.req("FR-010-21")
def test_the_context_is_invariant_to_the_scale_of_the_inverse_velocity_and_the_scale_follows_it() -> None:
    rng = np.random.default_rng(2)
    omega = np.cumsum(rng.uniform(0.2, 1.0, len(T)))
    a = ctx_mod.build_context(_window(omega))
    b = ctx_mod.build_context(_window(omega / 7.0))  # displacement / 7: velocity / 7, y x 7
    assert b.context == pytest.approx(a.context, rel=1e-5, abs=1e-6)
    assert b.scale == pytest.approx(7.0 * a.scale, rel=1e-5)


@pytest.mark.req("FR-010-21")
def test_a_window_without_any_positive_velocity_has_no_context() -> None:
    with pytest.raises(InvalidWindowError):
        ctx_mod.build_context(_window(-T))
    with pytest.raises(InvalidWindowError):
        ctx_mod.build_context(_window(np.zeros_like(T)))


# ---------------------------------------------------------------------------------------------------------------------
# the forecast loop with fake models


def _paths(median_fn):
    """A fake model: quantile j of step k = median(k) + offset_j (scaled units)."""
    calls: list[np.ndarray] = []
    offsets = np.linspace(-0.1, 0.1, 9)

    def model(context):
        assert context.dtype == np.float32
        assert context.shape == (1, 2, 128)
        calls.append(context.copy())
        base = median_fn(context)  # (64,)
        return (base[None, None, :] + offsets[None, :, None]).astype(np.float32)

    return model, calls


@pytest.mark.req("FR-010-21")
def test_a_crossing_in_the_first_block_is_read_at_the_hand_computed_time_with_the_80_percent_interval() -> None:
    w = _constant_velocity_window()
    k = np.arange(1, 65)

    calls: list[np.ndarray] = []
    # shift the quantile paths so that the 0.1 path crosses at k = 40 and the 0.9 path at k = 60
    offsets = np.zeros(9)
    offsets[0], offsets[8] = -0.1, 0.1

    def model2(context):
        calls.append(context.copy())
        out = (0.5 - 0.01 * k)[None, None, :] + offsets[None, :, None]
        return out.astype(np.float32)

    f = forecast.learned_forecast(model2, w)  # the median reaches 0 exactly at k = 50
    delta, t_c = w.delta, w.t[-1]
    assert f.n_model_calls == 1
    assert (f.outcome, f.scored_at_cap) == ("predicted", False)
    assert f.t_hat_f == pytest.approx(t_c + 4 * 50 * delta, rel=1e-6)
    lo, hi = f.interval_80
    assert lo == pytest.approx(t_c + 4 * 40 * delta, rel=1e-6)
    assert hi == pytest.approx(t_c + 4 * 60 * delta, rel=1e-6)
    assert f.times[:2] == pytest.approx([t_c + 4 * delta, t_c + 8 * delta], rel=1e-12)
    assert len(f.times) == 64
    assert f.median_y == pytest.approx((0.5 - 0.01 * k) * 2.0, rel=1e-5)  # unscaled: x the scale 2 h/mm
    assert len(calls) == 1


@pytest.mark.req("FR-010-21")
def test_without_a_crossing_the_median_is_fed_back_block_by_block_up_to_four_blocks() -> None:
    w = _constant_velocity_window()
    state = {"blocks": 0}

    def median(context):
        # a path that falls by 0.004 per step from the last context value: global y_k = 1 - 0.004 k
        last = float(context[0, 0, -1])
        state["blocks"] += 1
        return last - 0.0045 * np.arange(1, 65)

    model, calls = _paths(median)
    f = forecast.learned_forecast(model, w)
    assert f.n_model_calls == len(calls) == 4  # the root 1 / 0.0045 = 222 steps lies in block 4
    assert (f.outcome, f.scored_at_cap) == ("predicted", False)
    delta, t_c = w.delta, w.t[-1]
    assert f.t_hat_f == pytest.approx(t_c + 4 * (1.0 / 0.0045) * delta, rel=2e-4)
    assert len(f.times) == 256
    # feedback: context of call 2 = channel 0 of call 1 shifted left by 64 with the median of block 1 appended
    c1, c2 = calls[0], calls[1]
    assert c2[0, 0, :64] == pytest.approx(c1[0, 0, 64:], rel=1e-6)
    assert c2[0, 0, 64:] == pytest.approx(1.0 - 0.0045 * np.arange(1, 65), rel=1e-5)
    assert c2[0, 1, 64:] == pytest.approx(1.0)  # the appended values carry mask 1
    assert c2[0, 1, :64] == pytest.approx(c1[0, 1, 64:])
    assert f.median_y[:64] == pytest.approx(2.0 * (1.0 - 0.0045 * np.arange(1, 65)), rel=1e-5)


@pytest.mark.req("FR-010-21")
def test_a_path_that_never_crosses_within_the_cap_is_no_failure_predicted_scored_at_the_cap() -> None:
    w = _constant_velocity_window()
    model, calls = _paths(lambda c: float(c[0, 0, -1]) - 0.003 * np.arange(1, 65))  # root at step 333 > 256
    f = forecast.learned_forecast(model, w)
    assert len(calls) == 4
    assert (f.outcome, f.scored_at_cap) == ("no failure predicted", True)
    assert f.t_hat_f == pytest.approx(w.t[-1] + 1024 * w.delta, rel=1e-9)  # the cap 1,024 delta = 256 steps of 4 delta


@pytest.mark.req("FR-010-21")
def test_with_fewer_blocks_the_last_16_steps_are_extrapolated_inside_the_cap() -> None:
    w = _constant_velocity_window()
    model, calls = _paths(lambda c: float(c[0, 0, -1]) - 0.004 * np.arange(1, 65))  # root at step 250 <= 256
    f = forecast.learned_forecast(model, w, max_blocks=2)
    assert len(calls) == 2
    assert (f.outcome, f.scored_at_cap) == ("predicted", False)
    assert f.t_hat_f == pytest.approx(
        w.t[-1] + 4 * 250 * w.delta, rel=2e-4
    )  # extrapolated beyond the 128 steps produced
    assert len(f.times) == 128


@pytest.mark.req("FR-010-21")
@pytest.mark.parametrize("blocks", [0, 5, -1])
def test_max_blocks_outside_one_to_four_is_rejected(blocks) -> None:
    model, calls = _paths(lambda c: 0.5 - 0.01 * np.arange(1, 65))
    with pytest.raises(ValueError, match=r"."):
        forecast.learned_forecast(model, _constant_velocity_window(), max_blocks=blocks)
    assert calls == []


@pytest.mark.req("FR-010-21")
def test_a_model_output_with_the_wrong_shape_or_a_non_finite_value_is_refused() -> None:
    w = _constant_velocity_window()
    with pytest.raises(InvalidWindowError):
        forecast.learned_forecast(lambda c: np.zeros((1, 9, 63), dtype=np.float32), w)
    with pytest.raises(InvalidWindowError):
        forecast.learned_forecast(lambda c: np.full((1, 9, 64), np.nan, dtype=np.float32), w)
    with pytest.raises(InvalidWindowError):
        forecast.learned_forecast(lambda c: np.full((1, 9, 64), np.inf, dtype=np.float32), w)


@pytest.mark.req("FR-010-21")
def test_the_forecast_is_unchanged_by_a_positive_scaling_of_the_displacement() -> None:
    omega = 0.5 * T + 0.002 * T**2
    model, _ = _paths(lambda c: float(c[0, 0, -1]) - 0.0045 * np.arange(1, 65))
    a = forecast.learned_forecast(model, _window(omega))
    b = forecast.learned_forecast(model, _window(omega * 13.0))
    assert b.t_hat_f == pytest.approx(a.t_hat_f, rel=1e-6)
    assert b.outcome == a.outcome
