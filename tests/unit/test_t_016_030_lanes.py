"""T-016-030: manifest entries and measured lanes (unit, hostile, property).

Requirements: FR-016-11, FR-016-12, FR-016-13, P-016-09.

Spec: specs/016-export-acceleration/spec.md
- FR-016-11: a manifest entry (DC-000-01) for every exported or baked artefact: path, bytes, SHA-256, measured lane and
  lane measurements, asset host and release tag, budget class, licence class, SPDX id, attribution, producer tool and
  stage;
- FR-016-12: LIVE iff the artefact is web-drivable, its bytes <= 25 x 10^6, (its interaction time <= 16 ms or its run
  time <= 1 s on T2) and its trace <= 10 x 10^6 bytes, with times from the web timing record of that artefact's SHA-256
  (spec 018); an artefact without a valid timing record is not LIVE;
- FR-016-13: a timing record with a non-finite or negative time, a SHA-256 different from the artefact's, or a date
  earlier than the artefact's creation is ignored with the reason, and the lane is non-LIVE;
- P-016-09: increasing bytes, interaction time, run time or trace size never turns a non-LIVE lane into LIVE.
plan.md test strategy rows FR-016-11 (jsonschema against contracts/manifest.schema.json), FR-016-12 (25,000,000 /
25,000,001 bytes; 16 / 17 ms; 1.0 / 1.001 s; missing record), FR-016-13 (NaN, negative, wrong SHA-256, stale date).

Oracles:
- hand tables of the thresholds above (all boundary values are exact in binary64);
- the reference JSON Schema validation of `contracts/manifest.schema.json` (`$defs/artefact` and
  `$defs/lane_measurements`); the schema itself fixes that a release-hosted entry has a bare file name as `path` and a
  `release_tag`, that a git-hosted entry has fewer than 10,485,760 bytes and no tag, and that every non-`static` lane
  carries `lane_measurements`;
- the repository's own gate `pitstudio.contracts.lane.lane_of` (spec 001 FR-001-13, already implemented and tested)
  as a cross-check: the lane recorded in an entry is the lane that gate computes from the recorded measurements.

Expected public API (root environment):
module `pitstudio.export.lanes`
    derive_lane(artefact: Mapping, timing: Mapping | None, *, measured: Mapping) -> LaneResult
        artefact: {"sha256": hex, "bytes": int, "web_drivable": bool, "trace_bytes": int | None,
            "created": "YYYY-MM-DD"}
        timing (web timing record of spec 018, as read by s60_export): {"sha256": hex, "date": "YYYY-MM-DD",
            "tier": "T2", "browser": str, "interaction_ms": float | None, "run_ms_t2": float | None}
        measured: the context of the lane-gate run that supplies sizes when no valid timing record exists:
            {"tier": "T2", "date": "YYYY-MM-DD", "browser": str}
        LaneResult: `lane` "live" | "replay" (computed by the spec 001 gate from `measurements` when a valid record
            was used; "replay" when the record is missing or ignored), `measurements`: always the manifest
            `lane_measurements` object {web_drivable, max_asset_bytes = artefact bytes, interaction_ms, run_ms_t2,
            trace_bytes, measured}, with both times null and `measured` = the argument when no valid record exists,
            else the record's times and its own tier / date / browser as `measured`; `ignored_reason`: str | None (set
            exactly when a timing record was given and ignored; names "sha256", "date" or "time" for those causes).
module `pitstudio.export.manifest_entries`
    build_entry(spec: Mapping, *, run_id: str, git_sha: str, tool: str, measured: Mapping,
                timing: Mapping | None = None) -> dict
        spec: id, path, bytes, sha256, media_type, kind, inputs, cases, budget_class, licence_class, spdx,
        attribution (optional), web_drivable, trace_bytes, created, asset_host ("git" | "release"), release_tag
        (release only). Returns an artefact object that validates against manifest `$defs/artefact`, with
        `producer == {"tool": tool, "stage": {"id": "s60_export"}}`, `lane` and `lane_measurements` from derive_lane,
        the host (and tag), the budget class, the licence class, the SPDX id and the attribution copied from `spec`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.export.lanes import derive_lane
from pitstudio.export.manifest_entries import build_entry

from pitstudio.contracts.lane import lane_of

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "contracts" / "manifest.schema.json").read_text(encoding="utf-8"))
SHA = hashlib.sha256(b"d-fine-n.onnx").hexdigest()
MEASURED = {"tier": "T2", "date": "2026-10-22", "browser": "Chromium 141"}


def _artefact(**over: object) -> dict:
    base = {"sha256": SHA, "bytes": 8_234_567, "web_drivable": True, "trace_bytes": None, "created": "2026-10-20"}
    base.update(over)
    return base


def _timing(**over: object) -> dict:
    base = {
        "sha256": SHA,
        "date": "2026-10-21",
        "tier": "T2",
        "browser": "Chromium 140",
        "interaction_ms": None,
        "run_ms_t2": 850.0,
    }
    base.update(over)
    return base


def _lane(art: dict, tim: dict | None):
    return derive_lane(art, tim, measured=MEASURED)


def _validator(def_name: str):
    from jsonschema import Draft202012Validator

    return Draft202012Validator({"$ref": f"#/$defs/{def_name}", "$defs": MANIFEST["$defs"]})


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-12: the gate, boundary by boundary
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-12")
@pytest.mark.parametrize(
    ("art", "tim", "lane_is_live"),
    [
        ({"bytes": 25_000_000}, {}, True),
        ({"bytes": 25_000_001}, {}, False),
        ({}, {"interaction_ms": 16.0, "run_ms_t2": None}, True),
        ({}, {"interaction_ms": 17.0, "run_ms_t2": None}, False),
        ({}, {"interaction_ms": None, "run_ms_t2": 1000.0}, True),
        ({}, {"interaction_ms": None, "run_ms_t2": 1001.0}, False),
        ({}, {"interaction_ms": 17.0, "run_ms_t2": 1000.0}, True),  # the two time conditions are alternatives
        ({}, {"interaction_ms": 16.0, "run_ms_t2": 5000.0}, True),
        ({}, {"interaction_ms": 17.0, "run_ms_t2": 1001.0}, False),
        ({}, {"interaction_ms": None, "run_ms_t2": None}, False),  # nothing measured: not LIVE
        ({"trace_bytes": 10_000_000}, {}, True),
        ({"trace_bytes": 10_000_001}, {}, False),
        ({"trace_bytes": 0}, {}, True),
        ({"web_drivable": False}, {}, False),
    ],
)
def test_lane_gate_boundaries(art: dict, tim: dict, lane_is_live: bool) -> None:
    result = _lane(_artefact(**art), _timing(**tim))
    assert result.lane == ("live" if lane_is_live else "replay")
    assert result.ignored_reason is None  # the record is valid; the gate itself decided


@pytest.mark.req("FR-016-12")
def test_an_artefact_without_a_timing_record_is_never_live_and_keeps_size_only_measurements() -> None:
    result = _lane(_artefact(), None)
    assert result.lane == "replay"
    assert result.ignored_reason is None
    assert result.measurements == {
        "web_drivable": True,
        "max_asset_bytes": 8_234_567,
        "interaction_ms": None,
        "run_ms_t2": None,
        "trace_bytes": None,
        "measured": MEASURED,
    }
    assert list(_validator("lane_measurements").iter_errors(result.measurements)) == []


@pytest.mark.req("FR-016-12")
def test_a_valid_record_gives_measurements_that_match_the_repository_gate_and_the_manifest_schema() -> None:
    result = _lane(_artefact(), _timing(interaction_ms=12.0, run_ms_t2=None))
    assert result.lane == "live"
    assert result.ignored_reason is None
    m = result.measurements
    assert m == {
        "web_drivable": True,
        "max_asset_bytes": 8_234_567,
        "interaction_ms": 12.0,
        "run_ms_t2": None,
        "trace_bytes": None,
        "measured": {"tier": "T2", "date": "2026-10-21", "browser": "Chromium 140"},
    }
    assert list(_validator("lane_measurements").iter_errors(m)) == []
    assert lane_of(m) == result.lane  # cross-check with the spec 001 gate


@pytest.mark.req("FR-016-12")
def test_a_non_live_result_with_a_valid_record_is_consistent_with_the_repository_gate() -> None:
    result = _lane(_artefact(bytes=30_000_000), _timing())
    assert result.lane == "replay"
    assert lane_of(result.measurements) == "replay"
    assert result.measurements["max_asset_bytes"] == 30_000_000


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-13: hostile timing records
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-13")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -1.0, -0.001])
@pytest.mark.parametrize("field", ["interaction_ms", "run_ms_t2"])
def test_a_non_finite_or_negative_time_makes_the_record_ignored_and_the_lane_non_live(field: str, bad: float) -> None:
    good_other = {"interaction_ms": 5.0, "run_ms_t2": 500.0}  # the other time is fine; the whole record is dropped
    result = _lane(_artefact(), _timing(**{**good_other, field: bad}))
    assert result.lane == "replay"
    assert result.ignored_reason
    assert "time" in result.ignored_reason.lower()
    assert result.measurements["interaction_ms"] is None  # nothing of the ignored record is used
    assert result.measurements["run_ms_t2"] is None
    assert result.measurements["measured"] == MEASURED


@pytest.mark.req("FR-016-13")
def test_a_timing_record_of_another_sha256_is_ignored_with_the_reason() -> None:
    other = hashlib.sha256(b"another-artefact").hexdigest()
    result = _lane(_artefact(), _timing(sha256=other, interaction_ms=1.0))
    assert result.lane == "replay"
    assert result.ignored_reason
    assert "sha256" in result.ignored_reason.lower()
    assert result.measurements["interaction_ms"] is None


@pytest.mark.req("FR-016-13")
def test_a_record_dated_before_the_artefact_was_created_is_ignored_with_the_reason() -> None:
    result = _lane(_artefact(created="2026-10-20"), _timing(date="2026-10-19", interaction_ms=1.0))
    assert result.lane == "replay"
    assert result.ignored_reason
    assert "date" in result.ignored_reason.lower()


@pytest.mark.req("FR-016-13")
def test_a_record_dated_the_same_day_as_the_creation_is_valid() -> None:
    assert _lane(_artefact(created="2026-10-20"), _timing(date="2026-10-20")).lane == "live"


@pytest.mark.req("FR-016-13")
@pytest.mark.parametrize(
    "tim",
    [
        {"interaction_ms": "5"},
        {"interaction_ms": True},
        {"run_ms_t2": "fast"},
        {"date": "yesterday"},
        {"date": None},
        {"sha256": None},
    ],
)
def test_malformed_timing_fields_are_ignored_never_trusted(tim: dict) -> None:
    result = _lane(_artefact(), _timing(**tim))
    assert result.lane == "replay"
    assert result.ignored_reason


# ----------------------------------------------------------------------------------------------------------------------
# P-016-09: monotonicity
# ----------------------------------------------------------------------------------------------------------------------

times = st.one_of(st.none(), st.floats(min_value=0, max_value=5000, allow_nan=False, allow_infinity=False))


@pytest.mark.req("P-016-09")
@settings(max_examples=200, deadline=None)
@given(
    nbytes=st.integers(0, 60_000_000),
    interaction=times,
    run=times,
    trace=st.one_of(st.none(), st.integers(0, 30_000_000)),
    d_bytes=st.integers(0, 30_000_000),
    d_interaction=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
    d_run=st.floats(min_value=0, max_value=3000, allow_nan=False, allow_infinity=False),
    d_trace=st.integers(0, 20_000_000),
)
def test_increasing_bytes_times_or_trace_never_turns_a_non_live_lane_live(
    nbytes, interaction, run, trace, d_bytes, d_interaction, d_run, d_trace
):
    before = _lane(_artefact(bytes=nbytes, trace_bytes=trace), _timing(interaction_ms=interaction, run_ms_t2=run))
    after = _lane(
        _artefact(bytes=nbytes + d_bytes, trace_bytes=None if trace is None else trace + d_trace),
        _timing(
            interaction_ms=None if interaction is None else interaction + d_interaction,
            run_ms_t2=None if run is None else run + d_run,
        ),
    )
    if before.lane != "live":
        assert after.lane != "live"


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-11: the manifest entry
# ----------------------------------------------------------------------------------------------------------------------


def _spec(**over: object) -> dict:
    base = {
        "id": "d-fine-n-fp16",
        "path": "assets/models/d-fine-n-fp16.onnx",
        "bytes": 8_234_567,
        "sha256": SHA,
        "media_type": "application/octet-stream",
        "kind": "onnx",
        "inputs": [{"id": "d-fine-n-checkpoint", "sha256": hashlib.sha256(b"ckpt").hexdigest(), "kind": "artefact"}],
        "cases": ["B2"],
        "budget_class": "onnx",
        "licence_class": "own",
        "spdx": "Apache-2.0",
        "attribution": "PitStudio contributors",
        "web_drivable": True,
        "trace_bytes": None,
        "created": "2026-10-20",
        "asset_host": "git",
    }
    base.update(over)
    return base


RUN = {"run_id": "20261020T010000Z-b2-export", "git_sha": "c" * 40, "tool": "torch-onnx-export", "measured": MEASURED}


@pytest.mark.req("FR-016-11")
def test_a_git_hosted_live_artefact_entry_validates_and_carries_every_field() -> None:
    entry = build_entry(_spec(), timing=_timing(interaction_ms=10.0, run_ms_t2=None), **RUN)
    assert list(_validator("artefact").iter_errors(entry)) == []
    assert entry["path"] == "assets/models/d-fine-n-fp16.onnx"
    assert entry["bytes"] == 8_234_567
    assert entry["sha256"] == SHA
    assert entry["lane"] == "live"
    assert entry["lane_measurements"]["max_asset_bytes"] == 8_234_567
    assert entry["asset_host"] == "git"
    assert "release_tag" not in entry
    assert entry["budget_class"] == "onnx"
    assert entry["licence_class"] == "own"
    assert entry["spdx"] == "Apache-2.0"
    assert entry["attribution"] == "PitStudio contributors"
    assert entry["producer"] == {"tool": "torch-onnx-export", "stage": {"id": "s60_export"}}
    assert entry["run_id"] == RUN["run_id"]
    assert entry["git_sha"] == RUN["git_sha"]


@pytest.mark.req("FR-016-11")
def test_a_release_hosted_artefact_entry_carries_the_release_tag_and_a_bare_file_name() -> None:
    spec = _spec(
        asset_host="release",
        release_tag="assets-v1.00.001",
        bytes=41_000_000,
        kind="shard",
        path="a1-replay.tar",
        budget_class="shards-clouds",
    )
    entry = build_entry(spec, timing=None, **RUN)
    assert list(_validator("artefact").iter_errors(entry)) == []
    assert entry["asset_host"] == "release"
    assert entry["release_tag"] == "assets-v1.00.001"
    assert entry["lane"] == "replay"  # no valid timing record
    assert entry["lane_measurements"]["interaction_ms"] is None


@pytest.mark.req("FR-016-11")
def test_an_ignored_timing_record_still_gives_a_valid_non_live_entry() -> None:
    entry = build_entry(_spec(), timing=_timing(interaction_ms=float("nan")), **RUN)
    assert list(_validator("artefact").iter_errors(entry)) == []
    assert entry["lane"] == "replay"


@pytest.mark.req("FR-016-11")
def test_entry_lane_equals_the_lane_the_repository_gate_computes_from_the_recorded_measurements() -> None:
    entry = build_entry(
        _spec(bytes=26_000_000, asset_host="release", release_tag="assets-v1.00.001", path="x.onnx"),
        timing=_timing(),
        **RUN,
    )
    assert entry["lane"] == lane_of(entry["lane_measurements"]) == "replay"
