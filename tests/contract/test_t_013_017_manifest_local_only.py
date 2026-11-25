# ruff: noqa: E501, PT018, PT011
"""T-013-017: manifest marker `performance: local-only`, licence classes, no performance field in committed copies.

Requirements: FR-013-32, SC-013-02, DC-013-07.

Oracle: the literals of the spec (`performance: local-only`; outputs licence class `own` with SPDX `CC-BY-4.0`; runtime class
`reference-only`; the replacement text "measured locally, not published (licence)") and the DC-001-01 manifest rules for a
published stage with `performance: local-only` (no `wall_s`, no `throughput`, `telemetry` equal to the replacement text, no
`duration_s` in an attempt), written here as hand-built hostile manifests.

Expected API (package `pitstudio_rtx.lane`, first-party code importable from `studio/rtx/src`):
- `lane.manifest_fields(stage) -> dict` for `"st53_sensors"` and `"st57_rain_lidar"` (else `ValueError`):
  `{"performance": "local-only", "artefact": {"licence_class": "own", "spdx": "CC-BY-4.0"}, "runtime_licence_class":
  "reference-only"}`; a successful `run_stage` returns it (and possibly more keys) as `StageOutcome.manifest_fields`.
- `lane.scrub_performance(stage_entry) -> dict`: a copy of a run-manifest stage entry without `wall_s`, without `throughput`,
  with `telemetry` set to "measured locally, not published (licence)" and without `duration_s` in every attempt; other keys
  unchanged; the argument is not modified.
- `lane.check_published_manifest(manifest) -> list[str]`: the violations (one text each, naming the stage or artefact) of a
  published run manifest dict: any stage `st53_sensors` or `st57_rain_lidar` whose `performance` is not `local-only` or that holds
  a `wall_s`, `throughput`, a `telemetry` other than the replacement text or an attempt `duration_s`; any artefact produced by
  those stages (`producer.stage.id`) whose `licence_class` is not `own` or `spdx` not `CC-BY-4.0`. Other stages are not checked.
- `lane.check_published_manifests(runs_dir) -> dict[str, list[str]]`: the violations of every `<runs_dir>/*/manifest.json`
  (empty dict when there is none or all are clean).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import lane  # noqa: E402
from pitstudio_rtx.backends import fake  # noqa: E402

REPLACEMENT = "measured locally, not published (licence)"
EXPECTED = {
    "performance": "local-only",
    "artefact": {"licence_class": "own", "spdx": "CC-BY-4.0"},
    "runtime_licence_class": "reference-only",
}


def _stage(stage_id: str = "st53_sensors", **extra: object) -> dict:
    return {
        "key": {"id": stage_id},
        "status": "succeeded",
        "performance": "local-only",
        "telemetry": REPLACEMENT,
        "attempts": [{"n": 1, "exit_code": 0}],
        **extra,
    }


def _artefact(stage_id: str = "st53_sensors", licence: str = "own", spdx: str = "CC-BY-4.0") -> dict:
    return {
        "id": "s1-rotary-0",
        "producer": {"tool": "ovrtx", "stage": {"id": stage_id}},
        "licence_class": licence,
        "spdx": spdx,
    }


def _manifest(stages: list[dict] | None = None, artefacts: list[dict] | None = None) -> dict:
    return {
        "kind": "run",
        "stages": stages if stages is not None else [_stage()],
        "artefacts": artefacts if artefacts is not None else [_artefact()],
    }


@pytest.mark.req("FR-013-32")
@pytest.mark.parametrize("stage", ["st53_sensors", "st57_rain_lidar"])
def test_the_manifest_fields_are_the_spec_literals(stage: str) -> None:
    assert lane.manifest_fields(stage) == EXPECTED
    with pytest.raises(ValueError):
        lane.manifest_fields("st10_terrain")


@pytest.mark.req("FR-013-32")
def test_a_run_returns_the_marker_fields_and_its_index_holds_counts_only(tmp_path: Path) -> None:
    rec = kit.recipe("valid")
    rec["sensors"] = rec["sensors"][:1]
    be = fake.FakeBackend(versions=kit.OVRTX_VERSIONS)
    inputs = {rec["poses"]: kit.write_poses(tmp_path / "poses.parquet", 2)}
    (tmp_path / "field").mkdir()
    inputs.update({f: tmp_path / "field" for f in rec["dust"]["extinction_fields"]})
    env = tmp_path / "env.json"
    env.write_text(json.dumps(kit.envelope_for(rec)), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    outcome = lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, envelope_path=env, backend=be)
    assert outcome.exit_code == 0, outcome.message
    assert {
        k: outcome.manifest_fields[k] for k in EXPECTED
    } == EXPECTED  # (it may carry further keys, such as `publish`)
    forbidden = ("time", "fps", "throughput", "latency", "wall", "memory", "duration", "speed", "telemetry")

    def keys(node: object):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    assert not [k for k in keys(outcome.index) if any(f in k.lower() for f in forbidden)]
    assert np.isfinite(outcome.index["frames"][0]["valid_points"])  # counts are outputs, not performance data


@pytest.mark.req("FR-013-32")
def test_scrubbing_replaces_every_performance_value() -> None:
    entry = _stage(
        wall_s=123.4,
        throughput={"value": 31.5, "unit": "fps"},
        thermal_flag=False,
        attempts=[{"n": 1, "exit_code": 0, "duration_s": 120.0}, {"n": 2, "exit_code": 0, "duration_s": 3.4}],
    )
    entry["telemetry"] = {"sample_hz": 2, "n_samples": 240, "mem_used_peak_bytes": 7_000_000_000}
    original = copy.deepcopy(entry)
    scrubbed = lane.scrub_performance(entry)
    assert entry == original  # not modified
    assert "wall_s" not in scrubbed and "throughput" not in scrubbed
    assert scrubbed["telemetry"] == REPLACEMENT
    assert all("duration_s" not in a for a in scrubbed["attempts"]) and [a["n"] for a in scrubbed["attempts"]] == [1, 2]
    assert (
        scrubbed["key"] == entry["key"]
        and scrubbed["performance"] == "local-only"
        and scrubbed["thermal_flag"] is False
    )


@pytest.mark.req("SC-013-02")
def test_a_clean_manifest_has_no_violation_and_other_stages_are_not_checked() -> None:
    other = {
        "key": {"id": "st10_terrain"},
        "status": "succeeded",
        "performance": "public",
        "wall_s": 12.0,
        "throughput": {"value": 1.0, "unit": "x"},
        "telemetry": {"n_samples": 3},
    }
    assert lane.check_published_manifest(_manifest([_stage(), _stage("st57_rain_lidar"), other])) == []


@pytest.mark.req("SC-013-02")
@pytest.mark.parametrize(
    ("stage_extra", "what"),
    [
        ({"wall_s": 5.0}, "wall_s"),
        ({"throughput": {"value": 1.0, "unit": "fps"}}, "throughput"),
        ({"telemetry": {"n_samples": 3}}, "telemetry"),
        ({"attempts": [{"n": 1, "duration_s": 3.0}]}, "duration_s"),
        ({"performance": "public"}, "performance"),
    ],
)
def test_a_performance_value_in_a_sensor_stage_is_a_violation(stage_extra: dict, what: str) -> None:
    for stage_id in ("st53_sensors", "st57_rain_lidar"):
        problems = lane.check_published_manifest(_manifest([_stage(stage_id, **stage_extra)], []))
        assert len(problems) >= 1 and any(stage_id in p and what in p for p in problems), problems


@pytest.mark.req("SC-013-02")
@pytest.mark.parametrize(
    ("licence", "spdx"),
    [
        ("attribution", "CC-BY-4.0"),
        ("own", "MIT"),
        ("reference-only", "CC-BY-4.0"),
        ("display-only", "LicenseRef-NVIDIA-SLA"),
    ],
)
def test_sensor_artefacts_must_be_own_cc_by_4(licence: str, spdx: str) -> None:
    problems = lane.check_published_manifest(_manifest(artefacts=[_artefact(licence=licence, spdx=spdx)]))
    assert problems and any("s1-rotary-0" in p for p in problems)
    assert lane.check_published_manifest(_manifest(artefacts=[_artefact("st10_terrain", licence, spdx)])) == []


@pytest.mark.req("SC-013-02")
def test_the_published_manifests_of_the_repository_are_clean() -> None:
    assert lane.check_published_manifests(ROOT / "web" / "public" / "assets" / "runs") == {}
    assert lane.check_published_manifests(ROOT / "no-such-folder") == {}
