"""T-010-100: C1 error results from the scored event rows (C1-U1 of the 2026-11-23 improvement plan).

Requirements: FR-010-23, FR-010-25, FR-010-28, SC-010-02.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-23, FR-010-25, FR-010-28), section 5 (SC-010-02).
Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.c1_errors`):
- `paired_intervals(events, *, seed, resamples=10000) -> list[dict]`: one comparison per (stratum, learned method,
  cut-off) with the paired percentile bootstrap of d_i = e_inverse_velocity(i) - e_method(i) paired by event id
  (FR-010-25); the row is `evaluate.paired_comparison` with its `stratum` replaced by the stratum of the rows. A model
  whose event ids differ from the baseline's raises `evaluate.UnpairedError`; a row with outcome "no forecast" is not an
  error and is left out of both sides.
- `comparison_statement(comparisons) -> dict`: `comparisons` (count made), `per_stratum` (count per stratum, at most 8),
  `family_wise_claim` False.
- `error_distributions(events) -> list[dict]`: per (method, stratum, cutoff) the number of events, the quantiles of the
  relative error at p05, p25, p50, p75, p90, p95, the share of events scored at the horizon cap and the empirical CDF
  on the grid 0, 0.05, ..., 2.0.
"""

from __future__ import annotations

import numpy as np
import pytest

from pitstudio.slope import evaluate as ev
from pitstudio_pipeline.slope import c1_errors

LEARNED = ev.LEARNED


def _rows(stratum="nominal_30", n=40, shift=0.2, drop=None):
    rows = []
    for i in range(n):
        eid = f"voight-test-{stratum}-{i:06d}"
        base = 0.5 + 0.01 * i
        for method in ("inverse_velocity", "bayesian_ttf", *LEARNED):
            for cutoff in (0.5, 0.8):
                if drop is not None and (method, i) == drop:
                    continue
                err = base if method in ("inverse_velocity", "bayesian_ttf") else base - shift
                rows.append(
                    {
                        "event_id": eid,
                        "stratum": stratum,
                        "method": method,
                        "cutoff": cutoff,
                        "outcome": "predicted",
                        "rel_error": err,
                        "scored_at_cap": False,
                    }
                )
    return rows


@pytest.mark.req("FR-010-25")
def test_one_comparison_per_stratum_arm_and_cutoff_with_the_stratum_of_the_rows() -> None:
    events = _rows("nominal_10") + _rows("nominal_30")
    out = c1_errors.paired_intervals(events, seed=7, resamples=200)
    assert len(out) == 2 * 4 * 2
    assert {c["stratum"] for c in out} == {"nominal_10", "nominal_30"}
    assert {(c["method"], c["cutoff"]) for c in out} == {(m, c) for m in LEARNED for c in (0.5, 0.8)}
    assert all(c["n_pairs"] == 40 and c["baseline"] == "inverse_velocity" for c in out)


@pytest.mark.req("FR-010-25")
def test_a_model_better_by_a_constant_has_an_interval_above_zero_and_the_verdict_better() -> None:
    out = c1_errors.paired_intervals(_rows(shift=0.2), seed=3, resamples=500)
    for c in out:
        assert c["mean_difference"] == pytest.approx(0.2)
        assert c["interval"]["lower"] == pytest.approx(0.2) and c["interval"]["upper"] == pytest.approx(0.2)
        assert c["verdict"] == "better"
        assert c["bootstrap"]["method"] == "paired-percentile" and c["bootstrap"]["resample_unit"] == "sorted-event-id"


@pytest.mark.req("FR-010-25")
def test_the_interval_is_the_paired_percentile_bootstrap_of_the_differences() -> None:
    rows = _rows()
    rng_rows = np.random.default_rng(1)
    for r in rows:  # make the differences vary so the interval has width
        if r["method"] == "tcn":
            r["rel_error"] += float(rng_rows.normal(0, 0.1))
    got = next(
        c for c in c1_errors.paired_intervals(rows, seed=11, resamples=1000) if c["method"] == "tcn" and c["cutoff"] == 0.5
    )
    base = {r["event_id"]: r["rel_error"] for r in rows if r["method"] == "inverse_velocity" and r["cutoff"] == 0.5}
    model = {r["event_id"]: r["rel_error"] for r in rows if r["method"] == "tcn" and r["cutoff"] == 0.5}
    ids = sorted(base)
    d = np.array([base[i] - model[i] for i in ids])
    idx = np.random.Generator(np.random.PCG64(np.random.SeedSequence(11))).integers(0, len(ids), size=(1000, len(ids)))
    lo, hi = np.percentile(d[idx].mean(axis=1), [2.5, 97.5])
    assert got["interval"]["lower"] == pytest.approx(lo) and got["interval"]["upper"] == pytest.approx(hi)
    assert got["mean_difference"] == pytest.approx(d.mean())


@pytest.mark.req("FR-010-28")
def test_an_arm_missing_one_event_is_unpaired_never_an_interval_from_unpaired_errors() -> None:
    with pytest.raises(ev.UnpairedError):
        c1_errors.paired_intervals(_rows(drop=("tcn", 5)), seed=1, resamples=50)


@pytest.mark.req("FR-010-25")
def test_the_same_seed_gives_the_same_intervals_and_another_seed_does_not() -> None:
    rows = _rows()
    for r in rows:
        if r["method"] == "patchtst":
            r["rel_error"] += 0.05 * ((hash(r["event_id"]) % 7) - 3) / 3
    a = c1_errors.paired_intervals(rows, seed=5, resamples=300)
    b = c1_errors.paired_intervals(rows, seed=5, resamples=300)
    c = c1_errors.paired_intervals(rows, seed=6, resamples=300)
    assert a == b
    assert a != c


@pytest.mark.req("FR-010-25")
def test_the_statement_counts_the_comparisons_and_makes_no_family_wise_claim() -> None:
    out = c1_errors.paired_intervals(_rows("nominal_10") + _rows("nominal_30"), seed=1, resamples=50)
    s = c1_errors.comparison_statement(out)
    assert s == {"comparisons": 16, "per_stratum": {"nominal_10": 8, "nominal_30": 8}, "family_wise_claim": False}


@pytest.mark.req("FR-010-23")
def test_the_distribution_summary_has_quantiles_cap_share_and_ecdf() -> None:
    rows = []
    errs = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    for i, e in enumerate(errs):
        rows.append(
            {
                "event_id": f"e{i}",
                "stratum": "nominal_30",
                "method": "tcn",
                "cutoff": 0.5,
                "outcome": "no failure predicted" if i >= 8 else "predicted",
                "rel_error": e,
                "scored_at_cap": i >= 8,
            }
        )
    (d,) = c1_errors.error_distributions(rows)
    assert (d["method"], d["stratum"], d["cutoff"], d["n_events"]) == ("tcn", "nominal_30", 0.5, 10)
    assert d["quantiles"]["p50"] == pytest.approx(np.percentile(errs, 50))
    assert d["quantiles"]["p95"] == pytest.approx(np.percentile(errs, 95))
    assert d["share_at_cap"] == pytest.approx(0.2)
    grid = d["ecdf"]["x"]
    assert grid[0] == 0.0 and grid[-1] == 2.0 and len(grid) == 41
    ecdf = dict(zip(grid, d["ecdf"]["p"], strict=True))
    assert ecdf[0.0] == pytest.approx(0.1) and ecdf[0.5] == pytest.approx(0.6) and ecdf[2.0] == pytest.approx(1.0)
    assert all(a <= b for a, b in zip(d["ecdf"]["p"], d["ecdf"]["p"][1:], strict=False))


@pytest.mark.req("FR-010-23")
def test_rows_without_a_forecast_are_left_out_of_the_distribution() -> None:
    rows = [
        {"event_id": "a", "stratum": "s", "method": "tcn", "cutoff": 0.5, "outcome": "predicted", "rel_error": 0.1,
         "scored_at_cap": False},
        {"event_id": "b", "stratum": "s", "method": "tcn", "cutoff": 0.5, "outcome": "no forecast", "reason": "x"},
    ]
    (d,) = c1_errors.error_distributions(rows)
    assert d["n_events"] == 1


@pytest.mark.req("FR-010-24")
def test_the_median_interval_is_the_percentile_bootstrap_of_the_median_per_method_stratum_and_cutoff() -> None:
    rows = _rows("nominal_30", n=30)
    out = c1_errors.median_intervals(rows, seed=9, resamples=500)
    assert len(out) == 6 * 2
    tcn = next(r for r in out if r["method"] == "tcn" and r["cutoff"] == 0.5)
    by_id = {r["event_id"]: r["rel_error"] for r in rows if r["method"] == "tcn" and r["cutoff"] == 0.5}
    values = np.array([by_id[k] for k in sorted(by_id)])  # the bootstrap resamples the sorted event ids
    idx = np.random.Generator(np.random.PCG64(np.random.SeedSequence(9))).integers(0, 30, size=(500, 30))
    lo, hi = np.percentile(np.median(values[idx], axis=1), [2.5, 97.5])
    assert tcn["median_rel_error"] == pytest.approx(np.median(values))
    assert tcn["interval"]["lower"] == pytest.approx(lo) and tcn["interval"]["upper"] == pytest.approx(hi)
    assert tcn["n_events"] == 30 and tcn["bootstrap"]["resamples"] == 500
    assert "verdict" not in tcn and "threshold" not in tcn  # no SC-010-01 verdict outside the observed-SNR stratum
