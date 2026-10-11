# ruff: noqa: E501, PT018
"""T-008-021: values at the physical bounds are kept; only declared exclusion rules and crops remove records, with counts.

Requirements: FR-008-22, P-008-04.

Spec: specs/008-data-pipeline/spec.md FR-008-22 (no statistical fence; records are removed only through exclusion rules
declared in the recipe parameters, including area-of-interest crops, each rule and the number of records it removed recorded
in the manifest) and P-008-04 (rows inside the bounds, exactly at a bound included, are never removed: rows out = rows in).

Oracle: hand counts on small frames (a ramp 0..9 with the rule "keep 2 <= x <= 7" removes exactly 0, 1, 8, 9; a 5 x 5 point
grid cropped to the box [1, 1, 3, 3] keeps exactly the 9 inner points, boundary points included); the identity (no rule, no
removal) for edge-of-bound generators and for a value 10^6 times the median that a z-score or IQR fence would drop.

Expected API of the implementation:
- `pitstudio_pipeline.ingest.apply_exclusions(frame, rules) -> ExclusionResult` with `.frame` (polars DataFrame) and `.removed`
  (list of dicts `{"rule": <id>, "removed": <int>}` in rule order). A rule is a dict with a unique `id` and either
  `{"column": c, "min": lo_or_None, "max": hi_or_None}` (keep rows with lo <= value <= hi, both bounds inclusive) or
  `{"crop": {"x": cx, "y": cy, "bbox": [xmin, ymin, xmax, ymax]}}` (area-of-interest crop, keep rows inside the box, edges
  inclusive). Rules apply in order; a row is counted by the first rule that removes it. A rule naming a missing column, a
  non-finite bound, a duplicate id or an unknown shape raises an exception and removes nothing. Nothing else removes rows.
"""

from __future__ import annotations

import pandera.polars as pa
import polars as pl
import pytest
from pitstudio_pipeline.ingest import apply_exclusions, validate_table

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st


@pytest.mark.req("FR-008-22")
def test_no_rule_removes_nothing_even_a_value_a_statistical_fence_would_drop() -> None:
    values = [0.001 * i for i in range(1000)] + [
        1.0e6
    ]  # the last is 10^6 times the median scale: a z-score fence drops it
    df = pl.DataFrame({"x": values})
    res = apply_exclusions(df, [])
    assert res.frame.equals(df) and res.removed == []


@pytest.mark.req("FR-008-22")
def test_declared_range_rule_removes_exactly_the_hand_counted_rows_and_keeps_the_bounds() -> None:
    df = pl.DataFrame({"x": [float(i) for i in range(10)], "tag": list("abcdefghij")})
    res = apply_exclusions(df, [{"id": "keep-2-to-7", "column": "x", "min": 2.0, "max": 7.0}])
    assert res.frame["x"].to_list() == [2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert res.frame["tag"].to_list() == list("cdefgh")
    assert res.removed == [{"rule": "keep-2-to-7", "removed": 4}]


@pytest.mark.req("FR-008-22")
def test_open_ended_rules_and_sequential_counts() -> None:
    df = pl.DataFrame({"x": [float(i) for i in range(10)]})
    res = apply_exclusions(
        df,
        [
            {"id": "max-8", "column": "x", "min": None, "max": 8.0},  # removes 9
            {"id": "min-2", "column": "x", "min": 2.0, "max": None},  # removes 0, 1
        ],
    )
    assert res.frame["x"].to_list() == [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    assert res.removed == [{"rule": "max-8", "removed": 1}, {"rule": "min-2", "removed": 2}]


@pytest.mark.req("FR-008-22")
def test_area_of_interest_crop_keeps_the_inner_points_and_the_box_edges() -> None:
    xs = [float(x) for x in range(5) for _ in range(5)]
    ys = [float(y) for _ in range(5) for y in range(5)]
    df = pl.DataFrame({"e": xs, "n": ys})
    res = apply_exclusions(df, [{"id": "aoi", "crop": {"x": "e", "y": "n", "bbox": [1.0, 1.0, 3.0, 3.0]}}])
    assert res.frame.height == 9 and res.removed == [{"rule": "aoi", "removed": 16}]
    assert set(res.frame["e"].to_list()) == {1.0, 2.0, 3.0} and set(res.frame["n"].to_list()) == {1.0, 2.0, 3.0}


@pytest.mark.req("FR-008-22")
@pytest.mark.parametrize(
    "rules",
    [
        [{"id": "r", "column": "missing", "min": 0.0, "max": 1.0}],
        [{"id": "r", "column": "x", "min": float("nan"), "max": 1.0}],
        [{"id": "r", "column": "x", "min": 0.0, "max": float("inf")}],
        [{"id": "r", "column": "x", "min": 0.0}, {"id": "r", "column": "x", "max": 1.0}],
        [{"id": "r"}],
        [{"id": "r", "crop": {"x": "x", "y": "nope", "bbox": [0, 0, 1, 1]}}],
    ],
    ids=["missing-column", "nan-bound", "inf-bound", "duplicate-id", "no-shape", "crop-missing-column"],
)
def test_malformed_rules_raise_and_remove_nothing(rules: list[dict]) -> None:
    df = pl.DataFrame({"x": [0.0, 0.5, 1.0]})
    before = df.clone()
    with pytest.raises(Exception):  # noqa: B017, PT011  (the error class for a malformed rule is not fixed by the spec)
        apply_exclusions(df, rules)
    assert df.equals(before)


@pytest.mark.req("P-008-04")
@settings(max_examples=100, deadline=None)
@given(
    lo=st.sampled_from([-90.0, 0.0, -1e9]),
    width=st.sampled_from([180.0, 360.0, 1e9]),
    picks=st.lists(st.sampled_from(["lo", "hi", "mid", "lo+", "hi-"]), min_size=1, max_size=30),
)
def test_rows_at_and_near_the_bounds_are_never_removed(lo: float, width: float, picks: list[str]) -> None:
    hi = lo + width
    value = {"lo": lo, "hi": hi, "mid": lo + width / 2, "lo+": lo + width * 1e-12, "hi-": hi - width * 1e-12}
    df = pl.DataFrame({"v": [value[p] for p in picks], "k": list(range(len(picks)))})
    schema = pa.DataFrameSchema(
        {
            "v": pa.Column(
                pl.Float64, pa.Check.in_range(lo, hi), nullable=False, metadata={"unit": "deg", "source": "test bound"}
            ),
            "k": pa.Column(pl.Int64, nullable=False),
        },
        strict=True,
        coerce=False,
    )
    validated = validate_table(df, schema, file="raw/t/x.parquet")
    kept = apply_exclusions(validated, [{"id": "declared-bounds", "column": "v", "min": lo, "max": hi}])
    assert kept.frame.height == df.height and kept.removed == [{"rule": "declared-bounds", "removed": 0}]
    assert apply_exclusions(validated, []).frame.equals(df)


@pytest.mark.req("P-008-04")
@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(min_value=-1e300, max_value=1e300, allow_nan=False), min_size=1, max_size=200))
def test_no_statistical_fence_for_any_finite_values(values: list[float]) -> None:
    df = pl.DataFrame({"v": values})
    assert apply_exclusions(df, []).frame.height == len(values)
