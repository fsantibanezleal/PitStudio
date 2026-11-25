# ruff: noqa: E501, PT011, PT018
"""T-008-050: causal window features, transforms fitted on training groups only, the three metamorphic relations, hostile
series rejected.

Requirements: FR-008-39, FR-008-42, FR-008-48, P-008-10, FR-008-15.

Spec: specs/008-data-pipeline/spec.md FR-008-39 (window features computed causally: a feature stamped at time t uses only
samples with time <= t), FR-008-42 (features per record; normalisers and other transforms fitted only on the training groups
of the split they serve and stored with the split id; never fitted on test-fold records), FR-008-48 (non-increasing
timestamps, a non-finite sample, fewer samples than the longest window, or a window length <= 0 reject the series with a
report naming the series and the first offending index and compute no feature), P-008-10 (causality; translation
equivariance on uniform sampling; scaling c > 0 multiplies displacement and velocity by c and leaves ratio features
unchanged, rtol 1e-12), FR-008-15 (unsafe data root).

Oracle: a hand-computed example (series x = i^2 at t = i, windows 3 and 5, step 2; every number is worked out in the
test); the numpy mean / standard deviation of the training rows for the normaliser; the three relations of P-008-10 on
generated creep-like series (monotone cumulative sums of increments in [1, 2], so that differences do not cancel and rtol
1e-12 is attainable); hand-built hostile series.

Expected API of the implementation (module `pitstudio_pipeline.features`; samples are in order, windows are counts of samples):
- `window_features(t, x, *, windows, step=1, features, series="series") -> dict[str, numpy.ndarray]`: for each stamp index
  i = L - 1, L - 1 + step, ... (L = the longest window) and each window w, with the window being the samples i - w + 1 .. i:
  `displacement_w<w>` = x[i] - x[i-w+1]; `velocity_w<w>` = displacement / (t[i] - t[i-w+1]); `velocity_ratio_w<w>` =
  `velocity_w<w>` / `velocity_w<L>`; the key `t` holds the stamps t[i]. Only the requested `features` (names `displacement`,
  `velocity`, `velocity_ratio`) are returned, all float64. A hostile series raises `pitstudio_pipeline.errors.IngestionRejected`
  whose first violation has `file == series`-based relpath, `field` in {`t`, `x`, `windows`} and, where an index is
  meaningful, `row` = the first offending 0-based index.
- `run_series_stage(path, *, windows, step, features, source, data_root, run_id, now, repo_root=None, fixture=None,
  samples_dir=None) -> dict`: reads the JSON file `path` (`{"t": [...], "x": [...]}` under `<data_root>/raw/<source>/`), applies
  the shared series validator and `window_features`, and returns an ingestion report (stage `s20_feature_extraction`,
  validator `series`) valid against the schema: accepted = features written to `processed/<source>/<stem>.features.parquet`
  (columns as the dict above) and listed in `outputs`; rejected = status `rejected`, the violations, `outputs: []`, nothing
  written under `processed`.
- `fit_normaliser(X, record_ids, split, fold) -> Normaliser`: `X` an array (n_records, n_features) whose rows follow
  `record_ids`, `split` a split document, `fold` an index; fits the z-score (`mean`, `std` with ddof = 0, per column) on the rows
  whose record is in the fold's `train_pool`; the rows of other records (the fold's test list) are ignored; an unknown record id
  raises `ValueError`; `.split_id` is `split["id"]`, `.fold` the fold index, `.transform(X)` applies (X - mean) / std.
"""

from __future__ import annotations

import json
from pathlib import Path

import _p008_kit as kit
import numpy as np
import polars as pl
import pytest
from pitstudio_pipeline.errors import IngestionRejected, UnsafeDataRoot
from pitstudio_pipeline.features import fit_normaliser, run_series_stage, window_features

# isort: split
from hypothesis import (
    assume,
    given,
    settings,
)
from hypothesis import strategies as st

T10 = np.arange(10, dtype=float)
X10 = T10**2  # x_i = i^2


# ------------------------------------------------------------------------------------------------ FR-008-39 hand example
@pytest.mark.req("FR-008-39")
def test_hand_computed_windows_steps_and_features() -> None:
    out = window_features(T10, X10, windows=[3, 5], step=2, features=["displacement", "velocity", "velocity_ratio"])
    # longest window 5: stamps at i = 4, 6, 8; w = 3 uses i-2..i, w = 5 uses i-4..i (hand calculation)
    np.testing.assert_array_equal(out["t"], [4.0, 6.0, 8.0])
    np.testing.assert_array_equal(out["displacement_w3"], [16 - 4, 36 - 16, 64 - 36])  # 12, 20, 28
    np.testing.assert_array_equal(out["displacement_w5"], [16 - 0, 36 - 4, 64 - 16])  # 16, 32, 48
    np.testing.assert_allclose(out["velocity_w3"], [12 / 2, 20 / 2, 28 / 2], rtol=1e-15)  # 6, 10, 14
    np.testing.assert_allclose(out["velocity_w5"], [16 / 4, 32 / 4, 48 / 4], rtol=1e-15)  # 4, 8, 12
    np.testing.assert_allclose(out["velocity_ratio_w3"], [6 / 4, 10 / 8, 14 / 12], rtol=1e-15)
    np.testing.assert_array_equal(out["velocity_ratio_w5"], [1.0, 1.0, 1.0])
    assert all(v.dtype == np.float64 for v in out.values())


@pytest.mark.req("FR-008-39")
def test_single_window_unit_step_covers_every_complete_window() -> None:
    out = window_features(T10, X10, windows=[4], step=1, features=["displacement"])
    np.testing.assert_array_equal(out["t"], np.arange(3.0, 10.0))
    np.testing.assert_array_equal(out["displacement_w4"], X10[3:] - X10[:-3])
    assert set(out) == {"t", "displacement_w4"}


@pytest.mark.req("FR-008-39")
def test_non_uniform_timestamps_use_the_actual_time_span() -> None:
    t = np.array([0.0, 1.0, 3.0, 6.0, 10.0])
    x = np.array([0.0, 2.0, 2.0, 8.0, 20.0])
    out = window_features(t, x, windows=[3], step=1, features=["velocity"])
    # windows i = 2, 3, 4: (2-0)/(3-0), (8-2)/(6-1), (20-2)/(10-3)  (hand calculation)
    np.testing.assert_allclose(out["velocity_w3"], [2 / 3, 6 / 5, 18 / 7], rtol=1e-15)


# ------------------------------------------------------------------------------------------------ P-008-10
creep = st.tuples(
    st.lists(st.floats(min_value=1.0, max_value=2.0), min_size=12, max_size=120),
    st.sampled_from([0.5, 1.0, 10.0]),
)


def series(incr: list[float], dt: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(incr)
    return np.arange(n, dtype=float) * dt, np.cumsum(np.asarray(incr, dtype=float))


KW = {"windows": [3, 6], "step": 1, "features": ["displacement", "velocity", "velocity_ratio"]}


@pytest.mark.req("P-008-10")
@settings(max_examples=60, deadline=None)
@given(creep, st.data())
def test_causality_changing_later_samples_changes_no_earlier_feature(data, draw) -> None:
    incr, dt = data
    t, x = series(incr, dt)
    cut = draw.draw(st.integers(min_value=6, max_value=len(t) - 2))
    base = window_features(t, x, **KW)
    x2, t2 = x.copy(), t.copy()
    x2[cut + 1 :] += draw.draw(st.floats(min_value=-500, max_value=500))
    t2[cut + 1 :] += draw.draw(
        st.floats(min_value=0.0, max_value=3.0)
    )  # later samples may also move in time (still increasing)
    changed = window_features(t2, x2, **KW)
    keep = base["t"] <= t[cut]
    assert keep.any()
    for key in base:
        np.testing.assert_array_equal(base[key][keep], changed[key][: len(base[key])][keep])


@pytest.mark.req("P-008-10")
@settings(max_examples=60, deadline=None)
@given(creep, st.integers(min_value=1, max_value=5))
def test_translation_equivariance_on_uniform_sampling(data, m: int) -> None:
    incr, dt = data
    t, x = series(incr, dt)
    assume(len(t) - m >= 8)
    full = window_features(t, x, **KW)
    shifted = window_features(t[m:], x[m:], **KW)
    for key in full:
        np.testing.assert_array_equal(shifted[key], full[key][m:])


@pytest.mark.req("P-008-10")
@settings(max_examples=60, deadline=None)
@given(creep, st.floats(min_value=1e-3, max_value=1e3))
def test_scaling_the_displacement_scales_linear_features_and_leaves_ratios(data, c: float) -> None:
    incr, dt = data
    t, x = series(incr, dt)
    base = window_features(t, x, **KW)
    scaled = window_features(t, c * x, **KW)
    for key in base:
        if key == "t" or key.startswith("velocity_ratio"):
            np.testing.assert_allclose(scaled[key], base[key], rtol=1e-12)
        else:
            np.testing.assert_allclose(scaled[key], c * base[key], rtol=1e-12)
    np.testing.assert_array_equal(scaled["t"], base["t"])


# ------------------------------------------------------------------------------------------------ FR-008-48
def _bad(t, x, **kw):
    with pytest.raises(IngestionRejected) as info:
        window_features(
            np.asarray(t, dtype=float),
            np.asarray(x, dtype=float),
            windows=kw.pop("windows", [3]),
            step=1,
            features=["displacement"],
            series="s1",
        )
    return info.value.violations


@pytest.mark.req("FR-008-48")
@pytest.mark.parametrize(
    ("t", "row"),
    [
        ([0, 1, 2, 2, 4, 5, 6], 3),  # equal timestamps
        ([0, 1, 2, 1.5, 4, 5, 6], 3),  # going back
        ([0, 1, 2, 3, 4, 5, 4], 6),
        ([5, 4, 3, 2, 1, 0, -1], 1),  # entirely decreasing: first offence at index 1
    ],
)
def test_non_increasing_timestamps_name_the_first_offending_index(t: list[float], row: int) -> None:
    v = _bad(t, np.arange(len(t)))
    assert v[0]["row"] == row and v[0]["field"] == "t" and v[0]["field_kind"] == "column"


@pytest.mark.req("FR-008-48")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_samples_name_the_first_offending_index(bad: float) -> None:
    x = [0.0, 1.0, 2.0, bad, 4.0, bad, 6.0]
    v = _bad(np.arange(7), x)
    assert v[0]["row"] == 3 and v[0]["field"] == "x"
    assert isinstance(v[0]["value"], str), "non-finite values are text"


@pytest.mark.req("FR-008-48")
def test_non_finite_timestamp_is_rejected_at_its_index() -> None:
    v = _bad([0, 1, 2, float("nan"), 4, 5, 6], np.arange(7))
    assert v[0]["row"] == 3 and v[0]["field"] == "t"


@pytest.mark.req("FR-008-48")
@pytest.mark.parametrize("n", [0, 1, 4])
def test_fewer_samples_than_the_longest_window_is_rejected(n: int) -> None:
    assert _bad(np.arange(n), np.arange(n), windows=[3, 5])


@pytest.mark.req("FR-008-48")
@pytest.mark.parametrize("windows", [[0], [-3], [3, 0], [3, -1, 5]])
def test_window_length_not_positive_is_rejected(windows: list[int]) -> None:
    assert _bad(np.arange(10), np.arange(10), windows=windows)


@pytest.mark.req("FR-008-48")
def test_length_mismatch_between_t_and_x_is_rejected() -> None:
    with pytest.raises(IngestionRejected):
        window_features(np.arange(10.0), np.arange(9.0), windows=[3], step=1, features=["displacement"], series="s1")


# ------------------------------------------------------------------------------------------------ the stage
def _write_series(tmp: Path, t, x, name: str = "s1.json") -> Path:
    raw = tmp / "data" / "raw" / "t"
    raw.mkdir(parents=True, exist_ok=True)
    p = raw / name
    p.write_text(json.dumps({"t": list(map(float, t)), "x": list(map(float, x))}), encoding="utf-8")
    return p


def _stage(tmp: Path, p: Path, **over):
    kw = dict(
        windows=[3, 5],
        step=2,
        features=["displacement", "velocity", "velocity_ratio"],
        source="t",
        data_root=tmp / "data",
        run_id="20261011T120000Z-t",
        now=kit.NOW,
    )
    kw.update(over)
    return run_series_stage(p, **kw)


@pytest.mark.req("FR-008-39")
def test_stage_accepts_a_good_series_and_writes_the_hand_computed_features(tmp_path: Path) -> None:
    report = _stage(tmp_path, _write_series(tmp_path, T10, X10))
    assert kit.schema_errors("ingestion-report.schema.json", report) == []
    assert report["stage"] == "s20_feature_extraction" and report["status"] == "accepted"
    (out,) = report["outputs"]
    df = pl.read_parquet(tmp_path / "data" / out["path"])
    assert (
        out["path"].startswith("processed/t/")
        and kit.sha256_hex((tmp_path / "data" / out["path"]).read_bytes()) == out["sha256"]
    )
    assert df["t"].to_list() == [4.0, 6.0, 8.0] and df["displacement_w3"].to_list() == [12.0, 20.0, 28.0]


@pytest.mark.req("FR-008-48")
def test_stage_rejects_a_hostile_series_with_a_report_and_no_output(tmp_path: Path) -> None:
    t = [0, 1, 2, 2, 4, 5, 6, 7]
    report = _stage(tmp_path, _write_series(tmp_path, t, range(8)))
    assert kit.schema_errors("ingestion-report.schema.json", report) == []
    assert report["status"] == "rejected" and report["outputs"] == []
    assert report["violations"][0]["row"] == 3 and report["files"][0]["validator"] == "series"
    assert kit.files_under(tmp_path / "data" / "processed") == []


@pytest.mark.req("FR-008-15")
def test_stage_refuses_an_unsafe_data_root(tmp_path: Path) -> None:
    repo = kit.make_repo(tmp_path)
    p = _write_series(tmp_path, T10, X10)
    with pytest.raises(UnsafeDataRoot):
        run_series_stage(
            p,
            windows=[3],
            step=1,
            features=["displacement"],
            source="t",
            data_root=repo / "data",
            repo_root=repo,
            run_id="20261011T120000Z-t",
            now=kit.NOW,
        )


# ------------------------------------------------------------------------------------------------ FR-008-42
SPLIT = json.loads((kit.SPEC008 / "contracts" / "examples" / "split.valid.json").read_text(encoding="utf-8"))
RECORDS = [m for g in SPLIT["groups"] for m in g["members"]]


def _matrix(test_value: float = 1.0e6) -> tuple[np.ndarray, list[str]]:
    test_ids = set(SPLIT["folds"][0]["test"])
    rng = np.random.default_rng(5)
    X = rng.normal(10.0, 2.0, size=(len(RECORDS), 3))
    for i, r in enumerate(RECORDS):
        if r in test_ids:
            X[i] = test_value
    return X, RECORDS


@pytest.mark.req("FR-008-42")
def test_normaliser_is_fitted_on_the_training_pool_only() -> None:
    X, ids = _matrix()
    train_rows = [i for i, r in enumerate(ids) if r in set(SPLIT["folds"][0]["train_pool"])]
    assert len(train_rows) == 16
    norm = fit_normaliser(X, ids, SPLIT, 0)
    np.testing.assert_allclose(norm.mean, X[train_rows].mean(axis=0), rtol=1e-12)
    np.testing.assert_allclose(norm.std, X[train_rows].std(axis=0, ddof=0), rtol=1e-12)
    assert norm.split_id == SPLIT["id"] and norm.fold == 0
    np.testing.assert_allclose(
        norm.transform(X[train_rows]), (X[train_rows] - X[train_rows].mean(0)) / X[train_rows].std(0), rtol=1e-12
    )


@pytest.mark.req("FR-008-42")
def test_changing_the_test_fold_records_never_changes_the_fit() -> None:
    a = fit_normaliser(*_matrix(1.0e6)[:1], _matrix()[1], SPLIT, 0)
    b = fit_normaliser(*_matrix(-3.5)[:1], _matrix()[1], SPLIT, 0)
    np.testing.assert_array_equal(a.mean, b.mean)
    np.testing.assert_array_equal(a.std, b.std)


@pytest.mark.req("FR-008-42")
def test_each_fold_is_fitted_on_its_own_pool_and_carries_its_index() -> None:
    X, ids = _matrix(0.0)
    for f in range(5):
        pool = set(SPLIT["folds"][f]["train_pool"])
        rows = [i for i, r in enumerate(ids) if r in pool]
        norm = fit_normaliser(X, ids, SPLIT, f)
        np.testing.assert_allclose(norm.mean, X[rows].mean(axis=0), rtol=1e-12)
        assert norm.fold == f


@pytest.mark.req("FR-008-42")
def test_hostile_normaliser_inputs_are_rejected() -> None:
    X, ids = _matrix()
    with pytest.raises(ValueError):
        fit_normaliser(X, [*ids[:-1], "not-in-the-split"], SPLIT, 0)
    with pytest.raises((ValueError, IndexError)):
        fit_normaliser(X, ids, SPLIT, 9)
    with pytest.raises(ValueError):
        fit_normaliser(X[:-1], ids, SPLIT, 0)  # rows do not follow the ids
