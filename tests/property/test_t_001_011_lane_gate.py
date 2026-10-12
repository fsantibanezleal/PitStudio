"""T-001-011 · the measured lane gate: FR-001-13, P-001-01, P-001-02, P-001-03.

Oracle: the analytical gate of data-model 2.6 evaluated by hand in this file (never by the code under test):

    live  <=>  web_drivable
               and max_asset_bytes <= 25,000,000
               and ((interaction_ms is not null and interaction_ms <= 16)
                    or (run_ms_t2 is not null and run_ms_t2 <= 1000))
               and (trace_bytes is null or trace_bytes <= 10,000,000)

(MB = 10^6 B, thresholds ``lane_gate.*`` of thresholds.yaml: 25 MB, 16 ms, 1 s, 10 MB.)

Expected API: ``pitstudio.contracts.lane.lane_of(measurements: dict) -> "live" | "replay"`` taking the record of
data-model 2.6 (keys ``web_drivable``, ``max_asset_bytes``, ``interaction_ms``, ``run_ms_t2``, ``trace_bytes``,
``measured``); hostile input (negative or non-finite numbers, missing keys, wrong types) raises ``ContractError``
(a ``ValueError``). ``tools/check_contracts.py`` reports ``rule: FR-001-13`` findings whose pointer starts with
``/artefacts/<i>`` and whose message names the artefact id and the failing measurement (``web_drivable``,
``max_asset_bytes``, ``interaction_ms`` / ``run_ms_t2`` or ``trace_bytes``).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))
import contract_support as cs

MEASURED = {"tier": "T2", "date": "2026-10-07", "browser": "Chromium 141"}
PROP = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])  # ci_examples_per_test


def lane_of(m: dict) -> str:
    from pitstudio.contracts.lane import lane_of as impl

    return impl(m)


def meas(web: bool = True, asset: int = 1000, inter: Any = None, run: Any = None, trace: Any = None) -> dict:
    return {
        "web_drivable": web,
        "max_asset_bytes": asset,
        "interaction_ms": inter,
        "run_ms_t2": run,
        "trace_bytes": trace,
        "measured": dict(MEASURED),
    }


def gate(m: dict) -> str:
    """The analytical gate (oracle), in bytes and milliseconds."""
    times = (m["interaction_ms"] is not None and m["interaction_ms"] <= 16) or (
        m["run_ms_t2"] is not None and m["run_ms_t2"] <= 1000
    )
    traces = m["trace_bytes"] is None or m["trace_bytes"] <= 10_000_000
    return "live" if (m["web_drivable"] and m["max_asset_bytes"] <= 25_000_000 and times and traces) else "replay"


def gate_mb_seconds(m: dict) -> str:
    """The same gate evaluated in MB (10^6 B) and seconds with the thresholds converted (P-001-02)."""
    asset_mb = m["max_asset_bytes"] / 1e6
    inter_s = None if m["interaction_ms"] is None else m["interaction_ms"] / 1000
    run_s = None if m["run_ms_t2"] is None else m["run_ms_t2"] / 1000
    trace_mb = None if m["trace_bytes"] is None else m["trace_bytes"] / 1e6
    times = (inter_s is not None and inter_s <= 0.016) or (run_s is not None and run_s <= 1.0)
    traces = trace_mb is None or trace_mb <= 10.0
    return "live" if (m["web_drivable"] and asset_mb <= 25.0 and times and traces) else "replay"


# ----------------------------------------------------------------------------------------------------------------
# hand-calculated boundary table (every row computed by reading the gate above)
# ----------------------------------------------------------------------------------------------------------------
BOUNDARY_TABLE = [
    # (description, measurements, expected lane)
    ("all conditions met", meas(True, 5_000_000, 3.2, None, None), "live"),
    ("asset exactly 25 MB", meas(True, 25_000_000, 3.2), "live"),
    ("asset one byte over", meas(True, 25_000_001, 3.2), "replay"),
    ("interaction exactly 16 ms", meas(True, 1, 16), "live"),
    ("interaction 16.001 ms", meas(True, 1, 16.001), "replay"),
    ("interaction 0 ms", meas(True, 1, 0), "live"),
    ("run exactly 1000 ms", meas(True, 1, None, 1000), "live"),
    ("run 1000.001 ms", meas(True, 1, None, 1000.001), "replay"),
    ("run 0 ms", meas(True, 1, None, 0), "live"),
    ("trace exactly 10 MB", meas(True, 1, 3, None, 10_000_000), "live"),
    ("trace one byte over", meas(True, 1, 3, None, 10_000_001), "replay"),
    ("trace absent", meas(True, 1, 3, None, None), "live"),
    ("trace 0 B", meas(True, 1, 3, None, 0), "live"),
    ("not web drivable", meas(False, 1, 3), "replay"),
    ("neither time measured", meas(True, 1, None, None), "replay"),
    ("interaction slow but run fast", meas(True, 1, 500, 800), "live"),
    ("interaction fast but run slow", meas(True, 1, 3, 5000), "live"),
    ("both slow", meas(True, 1, 20, 2000), "replay"),
    ("interaction slow, run null", meas(True, 1, 20, None), "replay"),
    ("run slow, interaction null", meas(True, 1, None, 2000), "replay"),
    ("asset 0 B", meas(True, 0, 1), "live"),
    ("everything at its limit", meas(True, 25_000_000, 16, 1000, 10_000_000), "live"),
    ("everything one unit over", meas(True, 25_000_001, 16.001, 1000.001, 10_000_001), "replay"),
    ("huge asset", meas(True, 2**53 - 1, 1), "replay"),
]


@pytest.mark.req("FR-001-13")
@pytest.mark.parametrize(("desc", "m", "expected"), BOUNDARY_TABLE, ids=[r[0] for r in BOUNDARY_TABLE])
def test_fr_001_13_boundary_table(desc: str, m: dict, expected: str) -> None:
    assert gate(m) == expected  # the table agrees with the analytical gate
    assert lane_of(m) == expected, desc


@pytest.mark.req("FR-001-13")
def test_fr_001_13_lane_of_returns_exactly_the_two_artefact_lane_labels() -> None:
    assert {lane_of(m) for _, m, _ in BOUNDARY_TABLE} == {"live", "replay"}


@pytest.mark.req("FR-001-13")
def test_fr_001_13_lane_of_does_not_mutate_its_input() -> None:
    m = meas(True, 5_000_000, 3.2)
    before = copy.deepcopy(m)
    lane_of(m)
    assert m == before


@pytest.mark.req("FR-001-13")
@pytest.mark.parametrize(
    "bad",
    [
        meas(True, -1, 3),
        meas(True, 1, -0.5),
        meas(True, 1, None, -1),
        meas(True, 1, 3, None, -1),
        meas(True, float("nan"), 3),
        meas(True, 1, float("nan")),
        meas(True, 1, float("inf")),
        meas(True, 1, None, float("-inf")),
        meas(True, 1, None, float("nan")),
        meas(True, 1, 3, None, float("inf")),
        meas("yes", 1, 3),
        meas(None, 1, 3),
        meas(1, 1, 3),
        meas(True, "25000000", 3),
        meas(True, None, 3),
        meas(True, 1, "3"),
        meas(True, 1, None, "1000"),
        meas(True, 1.5, 3),
        meas(True, True, 3),
        "live",
        None,
        [],
    ],
    ids=lambda v: str(v)[:60],
)
def test_fr_001_13_hostile_measurements_are_rejected_not_silently_classified(bad: Any) -> None:
    with pytest.raises((ValueError, TypeError, KeyError)):  # ContractError (a ValueError) is the specified one
        lane_of(bad)


@pytest.mark.req("FR-001-13")
@pytest.mark.parametrize("missing", ["web_drivable", "max_asset_bytes", "interaction_ms", "run_ms_t2", "trace_bytes"])
def test_fr_001_13_a_missing_measurement_is_rejected(missing: str) -> None:
    m = meas(True, 1, 3)
    del m[missing]
    with pytest.raises((ValueError, TypeError, KeyError)):
        lane_of(m)


# ----------------------------------------------------------------------------------------------------------------
# properties
# ----------------------------------------------------------------------------------------------------------------
NULLABLE_MS = st.one_of(st.none(), st.integers(0, 10**6).map(lambda x: x / 1000))  # <= 3 decimals
TRACE = st.one_of(st.none(), st.integers(0, 10**10))
MEASUREMENTS = st.builds(
    meas, web=st.booleans(), asset=st.integers(0, 10**10), inter=NULLABLE_MS, run=NULLABLE_MS, trace=TRACE
)


@st.composite
def lower_or_equal(draw: Any, m: dict) -> dict:
    """A measurement set no worse than ``m`` in every component (null time = worst, null trace = best)."""
    out = copy.deepcopy(m)
    out["max_asset_bytes"] = draw(st.integers(0, m["max_asset_bytes"]))
    for key in ("interaction_ms", "run_ms_t2"):
        if m[key] is None:
            out[key] = draw(st.one_of(st.none(), st.integers(0, 10**6).map(lambda x: x / 1000)))
        else:
            out[key] = draw(st.integers(0, round(m[key] * 1000)).map(lambda x: x / 1000))
    out["trace_bytes"] = (
        None if m["trace_bytes"] is None else draw(st.one_of(st.none(), st.integers(0, m["trace_bytes"])))
    )
    return out


@pytest.mark.req("P-001-01")
@PROP
@given(data=st.data(), worse=MEASUREMENTS)
def test_p_001_01_lane_gate_is_monotone(data: st.DataObject, worse: dict) -> None:
    better = data.draw(lower_or_equal(worse))
    if lane_of(worse) == "live":
        assert lane_of(better) == "live"
    assert lane_of(better) == gate(better)
    assert lane_of(worse) == gate(worse)


@pytest.mark.req("P-001-02")
@PROP
@given(m=MEASUREMENTS)
def test_p_001_02_gate_is_invariant_under_the_change_of_units(m: dict) -> None:
    assert gate(m) == gate_mb_seconds(m)  # the oracle in bytes/ms equals the oracle in MB/s (exact, see plan.md)
    assert lane_of(m) == gate_mb_seconds(m)


@pytest.mark.req("P-001-03")
@pytest.mark.parametrize(
    ("field", "limit", "over"),
    [
        ("max_asset_bytes", 25_000_000, 25_000_001),
        ("interaction_ms", 16, 16.001),
        ("trace_bytes", 10_000_000, 10_000_001),
    ],
)
def test_p_001_03_limit_is_live_and_one_unit_beyond_is_replay(field: str, limit: Any, over: Any) -> None:
    base = meas(True, 1000, 1, None, 1000)
    at, beyond = dict(base, **{field: limit}), dict(base, **{field: over})
    assert lane_of(at) == "live"
    assert lane_of(beyond) == "replay"


@pytest.mark.req("P-001-03")
def test_p_001_03_run_time_boundary_is_live_and_one_unit_beyond_is_replay() -> None:
    assert lane_of(meas(True, 1000, None, 1000.0, 1000)) == "live"
    assert lane_of(meas(True, 1000, None, 1000.001, 1000)) == "replay"
    assert lane_of(meas(True, 1000, None, 1000.0, 10_000_001)) == "replay"


@pytest.mark.req("P-001-03")
@PROP
@given(
    inter_ok=st.integers(0, 16000).map(lambda x: x / 1000),
    inter_bad=st.integers(16001, 10**6).map(lambda x: x / 1000),
    run_ok=st.integers(0, 1_000_000).map(lambda x: x / 1000),
    run_bad=st.integers(1_000_001, 10**7).map(lambda x: x / 1000),
    asset=st.integers(0, 25_000_000),
    trace=st.one_of(st.none(), st.integers(0, 10_000_000)),
)
def test_p_001_03_swapping_which_time_satisfies_its_bound_leaves_the_lane_unchanged(
    inter_ok: float, inter_bad: float, run_ok: float, run_bad: float, asset: int, trace: Any
) -> None:
    a = meas(True, asset, inter_ok, run_bad, trace)  # interaction satisfies, run does not
    b = meas(True, asset, inter_bad, run_ok, trace)  # the other way round
    assert lane_of(a) == lane_of(b) == "live"
    both_bad = meas(True, asset, inter_bad, run_bad, trace)
    assert lane_of(both_bad) == "replay"
    both_ok = meas(True, asset, inter_ok, run_ok, trace)
    assert lane_of(both_ok) == "live"


@pytest.mark.req("P-001-01")
@PROP
@given(m=MEASUREMENTS, flip=st.sampled_from(["asset", "inter", "run", "trace", "web"]))
def test_p_001_01_a_single_worsening_step_never_turns_replay_into_live(m: dict, flip: str) -> None:
    worse = copy.deepcopy(m)
    if flip == "asset":
        worse["max_asset_bytes"] += 1
    elif flip == "inter" and worse["interaction_ms"] is not None:
        worse["interaction_ms"] += 0.001
    elif flip == "run" and worse["run_ms_t2"] is not None:
        worse["run_ms_t2"] += 0.001
    elif flip == "trace" and worse["trace_bytes"] is not None:
        worse["trace_bytes"] += 1
    elif flip == "web":
        worse["web_drivable"] = False
    if lane_of(m) == "replay":
        assert lane_of(worse) == "replay"


# ----------------------------------------------------------------------------------------------------------------
# the checker rule (FR-001-13): the declared lane must equal the gate computed from the measurements
# ----------------------------------------------------------------------------------------------------------------
INDEX = "web/public/assets/manifest.json"


def _with_lane(root: Path, lane: str, m: dict) -> None:
    def edit(doc: dict) -> None:
        art = doc["artefacts"][0]  # the video of the clean repository
        art["lane"], art["lane_measurements"] = lane, m

    cs.edit_json(root, INDEX, edit)


@pytest.mark.req("FR-001-13")
@pytest.mark.parametrize(
    ("lane", "m", "failing"),
    [
        ("live", meas(True, 25_000_001, 3.2), ["max_asset_bytes"]),
        ("live", meas(True, 1000, 3.2, None, 10_000_001), ["trace_bytes"]),
        ("live", meas(True, 1000, 16.001, 1000.001), ["interaction_ms", "run_ms_t2"]),
        ("live", meas(True, 1000, None, None), ["interaction_ms", "run_ms_t2"]),
        ("live", meas(False, 1000, 3.2), ["web_drivable"]),
    ],
)
def test_fr_001_13_checker_names_the_artefact_and_the_failing_condition_of_a_live_claim(
    tmp_path: Path, lane: str, m: dict, failing: list[str]
) -> None:
    root = cs.clean_repo(tmp_path)
    _with_lane(root, lane, m)
    res = cs.run_checker(root)
    assert res.code == 1
    hits = res.at("FR-001-13", "/artefacts/0")
    assert hits, res.findings
    text = " ".join(f["message"] for f in hits)
    assert "a2-haul-clip" in text
    assert any(token in text for token in failing), (failing, text)
    assert all(len(f["message"]) <= 300 for f in hits)


@pytest.mark.req("FR-001-13")
def test_fr_001_13_checker_flags_a_replay_claim_that_the_gate_would_make_live(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    _with_lane(root, "replay", meas(True, 5_000_000, 3.2))
    res = cs.run_checker(root)
    hits = res.at("FR-001-13", "/artefacts/0")
    assert hits
    assert "a2-haul-clip" in " ".join(f["message"] for f in hits)


@pytest.mark.req("FR-001-13")
@pytest.mark.parametrize(
    ("lane", "m"),
    [
        ("live", meas(True, 25_000_000, 16, None, 10_000_000)),
        ("live", meas(True, 1, None, 1000.0, None)),
        ("live", meas(True, 1, 3.2, 5000.0, 0)),
        ("replay", meas(True, 25_000_001, 3.2)),
        ("replay", meas(False, 1, 3.2)),
        ("replay", meas(True, 1, None, None)),
        ("replay", meas(True, 1, 16.001, 1000.001, None)),
        ("replay", meas(True, 1, 3.2, None, 10_000_001)),
    ],
)
def test_fr_001_13_checker_accepts_lanes_equal_to_the_gate(tmp_path: Path, lane: str, m: dict) -> None:
    assert gate(m) == lane
    root = cs.clean_repo(tmp_path)
    _with_lane(root, lane, m)
    res = cs.run_checker(root)
    assert res.of("FR-001-13") == []


@pytest.mark.req("FR-001-13")
def test_fr_001_13_checker_flags_the_corpus_fixture_with_a_lane_that_differs_from_the_gate(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    fixture = next(e for e in cs.entries(rule="FR-001-13", tag_in=("cross-file",)))
    doc = cs.fixture_json(fixture)
    cs.write_file(root, INDEX, doc)
    res = cs.run_checker(root)
    assert res.at("FR-001-13", fixture["pointer"])
