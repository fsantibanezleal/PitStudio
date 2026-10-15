"""T-010-052: the S4b report of `s50_evaluate`.

Requirement: FR-010-35 ("`s50_evaluate` shall report the S4b result: for radar positions with psi = 0, 45 and 70
degrees at the
peak pixel, the median relative TTF error of every method on the LOS series of the 500 SNR_obs test events at c in
{0.5, 0.8},
next to the same methods on the noise-free full-vector series; no threshold applies").
Spec: specs/010-slope/spec.md section 3.4; plan.md row FR-010-35 ("contract of the S4b block; psi = 0 reproduces the
full-vector
series when the noise is off"). Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.s50`, see T-010-033):
- `s4b_rows(*, los_errors, full_vector_errors, excluded_ambiguous) -> list[dict]`: `los_errors` maps (psi_deg, method,
  cutoff) to
  {event_id: relative error} of the events whose LOS series is usable (pixels flagged ambiguous are already excluded);
  `full_vector_errors` maps (method, cutoff) to {event_id: relative error} on the noise-free full-vector series;
  `excluded_ambiguous` maps psi_deg to the number of ambiguous pixels excluded. One row per available combination,
  shaped as
  `ttf-results.schema.json#/$defs/s4b` ({psi_deg, cutoff, method, series "los" | "full-vector-noise-free", n_events,
  median_rel_error, excluded_ambiguous_pixels}), ordered by psi (0, 45, 70), cut-off (0.5, 0.8), method
  (inverse_velocity,
  bayesian_ttf, tcn, patchtst, chronos_bolt_zero_shot, chronos_bolt_fine_tuned) and series (los first). The
  full-vector rows are
  repeated under every psi with excluded_ambiguous_pixels 0. No row has a threshold, verdict, interval or rank field.
- `evaluate(..., s4b=rows)` puts the rows into the document's `s4b` array (schema-valid).

Oracles: hand medians of planted errors; the noise-free identity: the LOS displacement of a peak pixel moving at angle
psi to the
line of sight is cos(psi) x the event displacement, and the forecasts (inverse velocity, Bayesian) are invariant under a
positive scaling of the displacement (P-010-10), so on noise-free series every psi reproduces the full-vector forecast.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_lem_ref as lem_ref  # noqa: E402
import _slope_ttf_ref as k  # noqa: E402
from pitstudio.slope import baselines, preprocess, radar  # noqa: E402
from pitstudio_pipeline.slope import s50  # noqa: E402

METHODS = ["inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"]
PSIS = (0, 45, 70)


def _errors(base: float, n=5):
    return {f"voight-test-snr-obs-{i:06d}": base + 0.01 * i for i in range(n)}  # median base + 0.02


def _inputs(skip=()):
    los, full = {}, {}
    for psi in PSIS:
        for c in (0.5, 0.8):
            for mi, m in enumerate(METHODS):
                if (psi, m, c) in skip:
                    continue
                los[(psi, m, c)] = _errors(0.05 * (mi + 1) + psi / 1000 + c / 10)
    for c in (0.5, 0.8):
        for mi, m in enumerate(METHODS):
            full[(m, c)] = _errors(0.01 * (mi + 1) + c / 100)
    return los, full, {0: 0, 45: 2, 70: 7}


@pytest.mark.req("FR-010-35")
def test_rows_are_ordered_and_carry_the_median_of_each_error_set() -> None:
    los, full, excluded = _inputs()
    rows = s50.s4b_rows(los_errors=los, full_vector_errors=full, excluded_ambiguous=excluded)
    assert len(rows) == 3 * 2 * 6 * 2
    order = [(r["psi_deg"], r["cutoff"], r["method"], r["series"]) for r in rows]
    expected = [
        (psi, c, m, s) for psi in PSIS for c in (0.5, 0.8) for m in METHODS for s in ("los", "full-vector-noise-free")
    ]
    assert order == expected
    for r in rows:
        errs = (
            los[(r["psi_deg"], r["method"], r["cutoff"])] if r["series"] == "los" else full[(r["method"], r["cutoff"])]
        )
        assert r["n_events"] == 5
        assert r["median_rel_error"] == pytest.approx(float(np.median(list(errs.values()))), rel=1e-12)
        assert r["excluded_ambiguous_pixels"] == (excluded[r["psi_deg"]] if r["series"] == "los" else 0)
        assert lem_ref.schema_errors(r, "ttf-results", "s4b") == []


@pytest.mark.req("FR-010-35")
def test_no_threshold_verdict_interval_or_rank_appears_in_the_block() -> None:
    los, full, excluded = _inputs()
    rows = s50.s4b_rows(los_errors=los, full_vector_errors=full, excluded_ambiguous=excluded)
    keys = {key for r in rows for key in r}
    assert keys == {
        "psi_deg",
        "cutoff",
        "method",
        "series",
        "n_events",
        "median_rel_error",
        "excluded_ambiguous_pixels",
    }


@pytest.mark.req("FR-010-35")
def test_a_missing_combination_is_omitted_and_events_dropped_for_ambiguity_reduce_n() -> None:
    los, full, excluded = _inputs(skip={(45, "chronos_bolt_fine_tuned", 0.5), (70, "chronos_bolt_fine_tuned", 0.5)})
    los[(70, "tcn", 0.8)] = {f"voight-test-snr-obs-{i:06d}": 0.1 for i in range(3)}  # two events lost to wrapping
    rows = s50.s4b_rows(los_errors=los, full_vector_errors=full, excluded_ambiguous=excluded)
    los_rows = {(r["psi_deg"], r["cutoff"], r["method"]): r for r in rows if r["series"] == "los"}
    assert (45, 0.5, "chronos_bolt_fine_tuned") not in los_rows
    assert (45, 0.8, "chronos_bolt_fine_tuned") in los_rows
    assert los_rows[(70, 0.8, "tcn")]["n_events"] == 3
    assert los_rows[(70, 0.8, "tcn")]["median_rel_error"] == pytest.approx(0.1)


@pytest.mark.req("FR-010-35")
def test_the_block_goes_into_the_document_and_validates() -> None:
    los, full, excluded = _inputs()
    rows = s50.s4b_rows(los_errors=los, full_vector_errors=full, excluded_ambiguous=excluded)
    res = s50.evaluate(
        run_id="20261115T101500Z-c1",
        snr_basis="observed",
        snr_obs=63.5,
        predictions=[],
        seeds={"acceptance": 1, "comparison": 2},
        s4b=rows,
    )
    assert res.document["s4b"] == rows
    assert lem_ref.schema_errors(res.document, "ttf-results") == []


@pytest.mark.req("FR-010-35")
@pytest.mark.parametrize("psi", PSIS)
def test_without_noise_every_psi_reproduces_the_full_vector_forecast(psi) -> None:
    s = k.terminal_series(alpha=2.0, v_onset_per_day=1.5, terminal_h=240.0, steady_fraction=0.2, n=1500)
    n = len(s["t"])
    r_dist = 1500.0
    e = np.array(
        [math.cos(math.radians(psi)), math.sin(math.radians(psi)), 0.0]
    )  # LOS unit vector at angle psi to the dip
    pixel = np.array([0.0, 0.0, 0.0])
    cfg = {"position_m": (pixel - r_dist * e).tolist(), "wavelength_mm": 17.4, "scan_interval_min": 6.0}
    u = np.column_stack([s["omega"], np.zeros(n), np.zeros(n)])  # the peak pixel moves along +x (the dip direction)
    px = {"pixel_id": 1, "position_m": pixel.tolist(), "displacement_mm": u}
    d = radar.build_radar_series(
        event_id="voight-test-snr-obs-000010", t_h=s["t"], radar=cfg, pixels=[px], snr=None, run_seed=1
    )[1].d_mm
    assert d == pytest.approx(math.cos(math.radians(psi)) * s["omega"], rel=1e-9, abs=1e-12)
    idx = round(0.8 * n)
    t_c = float(s["t"][idx])
    full = preprocess.preprocess_window(s["t"][: idx + 1], s["omega"][: idx + 1], t_c)
    los = preprocess.preprocess_window(s["t"][: idx + 1], d[: idx + 1], t_c)
    assert baselines.inverse_velocity(los).t_hat_f == pytest.approx(baselines.inverse_velocity(full).t_hat_f, rel=1e-9)
    assert baselines.bayesian_ttf(los, seed=3).t_hat_f == pytest.approx(
        baselines.bayesian_ttf(full, seed=3).t_hat_f, rel=1e-6
    )
