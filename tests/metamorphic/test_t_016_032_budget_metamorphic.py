"""T-016-032: metamorphic tests of the budget accounting (Hypothesis).

Requirements: P-016-08.

Spec: specs/016-export-acceleration/spec.md P-016-08: the budget total of a union of disjoint file sets equals the sum
of their totals, does not depend on file order, and never decreases when a file is added; a passing bake stays
passing when a file is removed (additivity, permutation, monotonicity). Generator: random file lists with sizes 0 to
10^9 bytes and classes from Table B.

Oracles: plain integer arithmetic written in the test (sums by class with `collections.Counter`); the relations
themselves.

Expected API: `pitstudio.export.budgets.budget_report` as in tests/unit/test_t_016_032_budgets.py
(`classes[c]["total"]`, `site_total`, `ok`); sizes up to 10^9 do not raise, over-cap bakes are reported, not raised.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.export.budgets import budget_report

CLASSES = ["videos", "tiles-glb", "shards-clouds", "splats", "onnx", "runtimes", "own-code", "studio-showcase"]

files_strategy = st.lists(st.tuples(st.integers(0, 10**9), st.sampled_from(CLASSES)), min_size=0, max_size=40).map(
    lambda xs: [{"path": f"assets/{c}/f{i}", "bytes": n, "budget_class": c} for i, (n, c) in enumerate(xs)]
)


def _by_class(files: list[dict]) -> Counter:
    c: Counter = Counter()
    for f in files:
        c[f["budget_class"]] += f["bytes"]
    return c


def _totals(report) -> dict[str, int]:
    return {k: v["total"] for k, v in report.classes.items()}


@pytest.mark.req("P-016-08")
@settings(max_examples=200, deadline=None)
@given(a=files_strategy, b=files_strategy)
def test_the_total_of_a_union_of_disjoint_file_sets_is_the_sum_of_their_totals(a, b):
    b = [{**f, "path": "other/" + f["path"]} for f in b]  # disjoint paths
    ra, rb, rab = budget_report(a), budget_report(b), budget_report(a + b)
    for cls in CLASSES:
        assert _totals(rab)[cls] == _totals(ra)[cls] + _totals(rb)[cls]
    assert rab.site_total == ra.site_total + rb.site_total
    assert _totals(ra) == {c: _by_class(a).get(c, 0) for c in CLASSES}  # the hand sum


@pytest.mark.req("P-016-08")
@settings(max_examples=200, deadline=None)
@given(files=files_strategy, seed=st.integers(0, 10**6))
def test_the_totals_and_the_verdict_do_not_depend_on_file_order(files, seed):
    shuffled = list(files)
    random.Random(seed).shuffle(shuffled)
    a, b = budget_report(files), budget_report(shuffled)
    assert (_totals(a), a.site_total, a.ok) == (_totals(b), b.site_total, b.ok)


@pytest.mark.req("P-016-08")
@settings(max_examples=200, deadline=None)
@given(files=files_strategy, size=st.integers(0, 10**9), cls=st.sampled_from(CLASSES))
def test_adding_a_file_never_decreases_any_total(files, size, cls):
    before = budget_report(files)
    after = budget_report([*files, {"path": "assets/new", "bytes": size, "budget_class": cls}])
    assert after.site_total >= before.site_total
    for c in CLASSES:
        assert _totals(after)[c] >= _totals(before)[c]
    assert _totals(after)[cls] == _totals(before)[cls] + size


@pytest.mark.req("P-016-08")
@settings(max_examples=200, deadline=None)
@given(files=files_strategy.filter(lambda fs: len(fs) > 0), idx=st.integers(0, 10**6))
def test_a_passing_bake_stays_passing_when_a_file_is_removed(files, idx):
    if not budget_report(files).ok:
        return
    smaller = [f for i, f in enumerate(files) if i != idx % len(files)]
    assert budget_report(smaller).ok


@pytest.mark.req("P-016-08")
@settings(max_examples=200, deadline=None)
@given(files=files_strategy)
def test_a_failing_bake_reports_the_same_failure_with_a_file_added(files):
    report = budget_report(files)
    bigger = budget_report([*files, {"path": "assets/extra", "bytes": 1, "budget_class": "onnx"}])
    if not report.ok:
        assert not bigger.ok  # monotone: more bytes cannot repair an over-cap class or site
