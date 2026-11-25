"""T-010-101: C1 event curves baked from seeded events and the on-disk ONNX forecasters (C1-U2 of the 2026-11-23 plan).

Requirements: FR-010-18, FR-010-19, FR-010-20, FR-010-21, FR-010-22, FR-010-32.
Spec: specs/010-slope/spec.md section 3.3. Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.c1_curves`):
- `select_events(rows, *, per_stratum=4, quantiles=(0.1, 0.4, 0.7, 0.95), method="tcn", cutoff=0.5) -> list[str]`:
  per stratum (in sorted stratum order, whatever the row order) the event ids at those quantiles of the relative
  error of `method` at
  `cutoff`, picked by rank so that good and poor cases are both shown; deterministic.
- `event_seed(event_id) -> int` and `rebuild_event(event_id, stratum, config) -> dict`: the synthetic test event of its
  seed, the same document the evaluation scored (`events.synthesize_event`, split "test", no observed SNR).
- `iv_fit(window) -> dict` with `t_hat_f_h`, `fit_t_h`, `fit_y`: the ordinary-least-squares line of FR-010-19 over the
  last 25 % of the unmasked samples, its root equal to `baselines.inverse_velocity`.
- `bayes_band(window, *, seed) -> dict` with `t_hat_f_h`, `t_h`, `y_median`, `y_lo`, `y_hi`: the 10 / 50 / 90 percent
  envelope of the posterior lines of FR-010-20, the median root equal to `baselines.bayesian_ttf`.
- `bake_event(doc, forecasters, *, cutoffs=(0.5, 0.8), seed) -> dict`: the curves of one event at each cut-off; a
  forecaster that raises `InvalidWindowError` gives an arm with `status` "no forecast" and its reason.
- `load_onnx_forecasters(onnx_dir) -> dict[str, OrtForecaster]`: exactly the files `tcn-c1.onnx`, `patchtst-c1.onnx` and
  `chronos_bolt_fine_tuned-c1.onnx`; a missing file is reported by `OnnxMissing` naming the file, never replaced.
"""

from __future__ import annotations

import numpy as np
import pytest

from pitstudio.slope import baselines, events, preprocess
from pitstudio.slope.errors import InvalidWindowError
from pitstudio_pipeline.slope import c1_curves, data
import itertools


def _config():
    cfg = events.default_config(None)
    cfg["n_samples"] = 2000
    cfg["splits"] = {
        "train": {"start": 0, "count": 20_000},
        "validation": {"start": 1_000_000, "count": 1_000},
        "test": {"start": 2_000_000, "count_per_stratum": 500},
    }
    return cfg


def _doc(seed=2_000_003, stratum="nominal_30"):
    return events.synthesize_event(seed, stratum=stratum, snr_obs=None, n_samples=2000, split="test", config=_config())


def _window(doc, cutoff=0.5):
    return data.window_at(doc, cutoff)[0]


def _rows():
    return [
        {
            "event_id": f"voight-test-{stratum.replace('_', '-')}-{2_000_000 + i:06d}",
            "stratum": stratum,
            "method": "tcn",
            "cutoff": 0.5,
            "outcome": "predicted",
            "rel_error": 0.01 * (20 - i),
        }
        for stratum in ("nominal_10", "nominal_30")
        for i in range(20)
    ]


@pytest.mark.req("FR-010-23")
def test_selection_is_by_rank_in_each_stratum_and_deterministic() -> None:
    a = c1_curves.select_events(_rows())
    assert a == c1_curves.select_events(list(reversed(_rows())))
    assert len(a) == 8
    assert len(set(a)) == 8
    first = a[:4]
    assert all("nominal-10" in e for e in first)
    assert all("nominal-30" in e for e in a[4:])
    errs = {r["event_id"]: r["rel_error"] for r in _rows()}
    ranked = sorted(errs[e] for e in first)
    assert ranked == sorted(ranked)
    assert ranked[0] < ranked[-1]


@pytest.mark.req("FR-010-11")
def test_the_event_seed_and_the_rebuilt_event_match_the_scored_id() -> None:
    doc = _doc(2_000_003)
    assert c1_curves.event_seed(doc["event_id"]) == 2_000_003
    again = c1_curves.rebuild_event(doc["event_id"], "nominal_30", _config())
    assert again["los_displacement_mm"] == doc["los_displacement_mm"]
    assert again["t_f_h"] == doc["t_f_h"]
    with pytest.raises(ValueError, match=r"\w"):
        c1_curves.event_seed("not-an-event")


@pytest.mark.req("FR-010-19")
def test_the_inverse_velocity_fit_line_has_the_root_of_the_baseline() -> None:
    w = _window(_doc())
    fit = c1_curves.iv_fit(w)
    assert fit["t_hat_f_h"] == pytest.approx(baselines.inverse_velocity(w).t_hat_f)
    assert len(fit["fit_t_h"]) == len(fit["fit_y"]) >= 10
    slope = np.polyfit(fit["fit_t_h"], fit["fit_y"], 1)
    assert -slope[1] / slope[0] == pytest.approx(fit["t_hat_f_h"])


@pytest.mark.req("FR-010-20")
def test_the_bayesian_band_median_root_is_the_baseline_and_the_band_is_ordered() -> None:
    w = _window(_doc())
    band = c1_curves.bayes_band(w, seed=5)
    assert band["t_hat_f_h"] == pytest.approx(baselines.bayesian_ttf(w, seed=5).t_hat_f)
    lo, med, hi = (np.asarray(band[k]) for k in ("y_lo", "y_median", "y_hi"))
    assert np.all(lo <= med + 1e-12)
    assert np.all(med <= hi + 1e-12)
    assert len(band["t_h"]) == len(med)


class _Fake:
    """A forecaster that continues the inverse velocity down to zero: median path y = scaled ramp (1 -> -0.2)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, context):
        self.calls += 1
        steps = np.linspace(0.9, -0.2, 64)
        out = np.stack([steps + 0.05 * (q - 4) for q in range(9)])[None].astype(np.float32)
        return out


@pytest.mark.req("FR-010-21")
def test_a_baked_event_has_both_cutoffs_every_method_and_the_true_failure_time() -> None:
    doc = _doc()
    fake = _Fake()
    baked = c1_curves.bake_event(doc, {"tcn": fake}, seed=3)
    assert baked["event_id"] == doc["event_id"]
    assert baked["t_f_h"] == doc["t_f_h"]
    assert [c["cutoff"] for c in baked["cutoffs"]] == [0.5, 0.8]
    for c in baked["cutoffs"]:
        assert c["t_c_h"] == pytest.approx(c["cutoff"] * doc["t_f_h"])
        assert set(c["methods"]) == {"inverse_velocity", "bayesian_ttf", "tcn"}
        assert c["methods"]["tcn"]["status"] == "ok"
        assert c["methods"]["tcn"]["t_hat_f_h"] > c["t_c_h"] - 1e-6
        assert len(c["methods"]["tcn"]["t_h"]) == len(c["methods"]["tcn"]["y_median"])
    assert fake.calls >= 2


@pytest.mark.req("FR-010-29")
def test_a_forecaster_that_rejects_the_window_is_reported_not_run_with_its_reason() -> None:
    def reject(_ctx):
        raise InvalidWindowError("no positive velocity at all")

    baked = c1_curves.bake_event(_doc(), {"tcn": reject}, seed=3)
    arm = baked["cutoffs"][0]["methods"]["tcn"]
    assert arm["status"] == "no forecast"
    assert "no positive velocity" in arm["reason"]
    assert "t_hat_f_h" not in arm


@pytest.mark.req("FR-010-30")
def test_only_the_on_disk_onnx_files_are_loaded_and_a_missing_one_is_named(tmp_path) -> None:
    with pytest.raises(c1_curves.OnnxMissing) as exc:
        c1_curves.load_onnx_forecasters(tmp_path)
    assert "tcn-c1.onnx" in str(exc.value)
    assert c1_curves.ONNX_FILES == {
        "tcn": "tcn-c1.onnx",
        "patchtst": "patchtst-c1.onnx",
        "chronos_bolt_fine_tuned": "chronos_bolt_fine_tuned-c1.onnx",
    }


@pytest.mark.req("FR-010-18")
def test_decimation_keeps_the_ends_and_the_order_and_never_exceeds_the_limit() -> None:
    t = np.linspace(0, 100, 2000)
    y = t**2
    dt, dy = c1_curves.decimate(t, y, 300)
    assert len(dt) == len(dy) <= 300
    assert dt[0] == t[0]
    assert dt[-1] == t[-1]
    assert all(a < b for a, b in itertools.pairwise(dt))
    short = c1_curves.decimate(t[:10], y[:10], 300)
    assert len(short[0]) == 10
    assert preprocess.L == 512
