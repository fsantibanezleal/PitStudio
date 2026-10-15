# ruff: noqa: E501, PT018
"""T-007-018: metamorphic relations of the reference engine through the adapter: order-preserving relabelling, homogeneous permutation, orientation reversal.

Requirements: P-007-06, P-007-07.

Spec: specs/007-haulage-dispatch/spec.md P-007-06 (a strictly increasing relabelling of truck ids gives the identical trace with the ids mapped; for a homogeneous fleet with one shared start
loader, any permutation of truck ids leaves the fleet KPIs unchanged; random relabellings of golden scenarios) and P-007-07 (in fast mode without direction zones, reversing the stored
orientation of a two-way segment (swap a and b, negate the grade, reverse the polyline) leaves the trace unchanged; exact).

Oracle: the relations themselves (the baseline run is the reference for its transformed twin); the engine's rule that trucks are started in sorted id order, so an order-preserving relabelling
cannot change any draw or any tie; no value is taken from a run of the code under test other than the baseline of the relation.

Expected API: `pitstudio_pipeline.haulage.adapter.run_shift` (test_t_007_013) and the KPI table of test_t_007_016. The relations hold for the `deterministic` and the `engine` profile.
"""

from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_busy as busy
import p007_kit as kit
from pitstudio_pipeline.haulage.adapter import run_shift

SETTINGS = settings(
    max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)


def run(bundle: dict, seed: int):
    with tempfile.TemporaryDirectory() as d:
        return run_shift(kit.write_bundle(Path(d), bundle), seed=seed)


def relabel_trace(res, f):
    ev = [{**e, "truck": None if e["truck"] is None else f[e["truck"]]} for e in res.events]
    cl = [{**r, "truck": f[r["truck"]]} for r in res.cyclelog]
    return ev, cl


def numbers(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update({f"{k}.{kk}": vv for kk, vv in numbers(v).items()})
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    return out


# ---------------------------------------------------------------------------------------------------------------------
# P-007-06: relabelling
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-007-06")
@SETTINGS
@given(
    st.sampled_from(["deterministic", "engine"]),
    st.sampled_from(["fixed", "nearest", "sptf", "sq"]),
    st.sampled_from(["fast", "traffic"]),
    st.integers(0, 50),
    st.lists(st.integers(1, 40), min_size=5, max_size=5),
    st.integers(0, 10**6),
)
def test_a_strictly_increasing_relabelling_gives_the_identical_trace_with_ids_mapped(
    profile, dispatcher, mode, base, gaps, seed
):
    b = busy.busy_bundle(dispatcher, mode, n_trucks=5, horizon=2 * 3600.0, profile=profile)
    ids = [t["id"] for t in b["fleet"]]
    new, acc = [], base
    for g in gaps:
        acc += g
        new.append(acc)
    f = dict(zip(ids, new, strict=True))
    twin = copy.deepcopy(b)
    for t in twin["fleet"]:
        t["id"] = f[t["id"]]
    a, c = run(b, seed), run(twin, seed)
    ev, cl = relabel_trace(a, f)
    assert (
        c.events == ev and c.cyclelog == cl
    )  # the same times, seqs, kinds, nodes, payloads; only the truck ids differ
    assert c.trace["results"] == a.trace["results"]
    assert c.kpis["fleet"] == a.kpis["fleet"] and c.kpis["loaders"] == a.kpis["loaders"]


@pytest.mark.req("P-007-06")
@SETTINGS
@given(
    st.sampled_from(["deterministic", "engine"]),
    st.sampled_from(["sptf", "sq", "nearest"]),
    st.permutations(range(6)),
    st.integers(0, 10**6),
)
def test_permuting_the_ids_of_a_homogeneous_fleet_with_one_start_loader_leaves_the_fleet_kpis_unchanged(
    profile, dispatcher, perm, seed
):
    b = busy.busy_bundle(dispatcher, "fast", n_trucks=6, horizon=2 * 3600.0, profile=profile)
    for t in b["fleet"]:
        t["start_loader"] = 1  # every truck starts at loader 1
    twin = copy.deepcopy(b)
    for i, t in enumerate(twin["fleet"]):
        t["id"] = perm[i] + 1  # a permutation of 1..6 that is generally not order preserving
    ka, kb = run(b, seed).kpis["fleet"], run(twin, seed).kpis["fleet"]
    na, nb = numbers(ka), numbers(kb)
    assert na.keys() == nb.keys()
    for k in na:
        assert nb[k] == pytest.approx(na[k], rel=1e-12, abs=1e-12), k
    assert ka["cost_per_t"] == kb["cost_per_t"]


@pytest.mark.req("P-007-06")
def test_the_relabelling_relation_is_not_vacuous():
    """A non-monotone relabelling is allowed to change the order of the stagger draws: the baseline must have trucks whose draws differ."""
    r = run(busy.busy_bundle("sptf", "fast", n_trucks=4, horizon=3600.0, profile="engine"), 1)
    first = [e["t_s"] for e in r.events if e["kind"] == "arrive-loader"][:4]
    assert len(set(first)) == 4


# ---------------------------------------------------------------------------------------------------------------------
# P-007-07: orientation reversal
# ---------------------------------------------------------------------------------------------------------------------
def reverse_segment(b: dict, sid: int) -> dict:
    out = copy.deepcopy(b)
    s = next(x for x in out["network"]["segments"] if x["id"] == sid)
    assert not s["one_way"] and s["zone_id"] is None
    s["a"], s["b"] = s["b"], s["a"]
    s["polyline_m"] = list(reversed(s["polyline_m"]))
    s["grade_pct"] = -s["grade_pct"]
    return out


@pytest.mark.req("P-007-07")
@SETTINGS
@given(
    st.sampled_from(["deterministic", "engine"]),
    st.sampled_from(["fixed", "nearest", "sptf", "sq"]),
    st.sets(st.sampled_from([1, 2, 3, 4]), min_size=1),
    st.integers(0, 10**6),
)
def test_reversing_the_stored_orientation_of_two_way_segments_leaves_the_trace_unchanged(
    profile, dispatcher, sids, seed
):
    b = busy.busy_bundle(dispatcher, "fast", n_trucks=6, horizon=2 * 3600.0, profile=profile)
    twin = b
    for sid in sorted(sids):
        twin = reverse_segment(twin, sid)
    assert twin != b
    a, c = run(b, seed), run(twin, seed)
    assert c.events == a.events and c.cyclelog == a.cyclelog and c.trace["results"] == a.trace["results"]
    assert c.kpis == a.kpis


@pytest.mark.req("P-007-07")
def test_the_reversed_bundle_is_a_valid_distinct_document():
    b = busy.busy_bundle()
    twin = reverse_segment(b, 1)
    s0, s1 = b["network"]["segments"][0], twin["network"]["segments"][0]
    assert (
        (s1["a"], s1["b"]) == (s0["b"], s0["a"])
        and s1["grade_pct"] == -s0["grade_pct"]
        and s1["polyline_m"][0] == s0["polyline_m"][-1]
    )
    assert s1["length_m"] == s0["length_m"]
