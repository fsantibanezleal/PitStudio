# ruff: noqa: E501, PT018
"""T-013-013: elevation-fan envelope guard and the `ovrtx` probe writer (no performance fields).

Requirements: FR-013-05, FR-013-06 (the CPU part: the schema and content of the envelope the probe writes), DC-013-08.

Oracle: envelope fixtures with pass, fail and missing entries and a version mismatch (plan.md "FR-013-05"); the envelope
schema DC-013-02 (draft); the versions the probe must record are read from `studio/rtx/uv.lock` with `tomllib`; ovrtx issue
#3 values of spec section 7 A2 (a +/-80 deg fan with mount rotation (90, 0, -90) returned 0 points, a +/-45 deg fan with no
rotation about 150,000 points).

Expected API:
- `pitstudio_rtx.lane.run_stage(...)` (test_t_013_012): for every lidar of the recipe, the envelope must list its
  configuration (`scan_type`, `elevation_fan_deg`, `azimuth_fan_deg`, `mount_rotation_deg`, all equal) with `status: pass`, for
  the `ovrtx` and `ovstage` versions equal to `backend.describe().versions`; otherwise (entry missing, entry `fail`,
  versions differ, envelope file missing, unreadable, not JSON or invalid against `lidar-envelope.schema.json`) the stage
  returns `exit_code` 2 before opening the backend, with a message naming the sensor id and the untested configuration
  (its `elevation_fan_deg` and `mount_rotation_deg`), and writes no output. A recipe without a lidar needs no envelope.
- `pitstudio_rtx.lane.check_envelope(params, envelope, versions)`: the same rule on a parsed envelope dict; raises
  `lane.EnvelopeError` (a `ValueError`) with `.sensor` (sensor id) and `.configuration` (the offending configuration dict).
- `studio/bench/probe_ovrtx.py` (importable with `sys.path` including `studio/bench`; it must not import `ovrtx` at module
  level): `referenced_configurations(recipes)` returns the distinct lidar configurations of the given recipe blocks, in order
  of first appearance; `build_envelope(results, *, lock_path, generated=None)` builds the DC-013-02 document from probe results
  (`{scan_type, elevation_fan_deg, azimuth_fan_deg, mount_rotation_deg, valid_points}`), `status` `pass` exactly when
  `valid_points > 0`, versions read from the lock file, the probe scene `{cube_edge_m: 2, cube_range_m: 20}`, and no timing,
  throughput or memory field anywhere; `write_envelope(doc, path)` writes it as JSON with a trailing newline.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "bench"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import lane  # noqa: E402
from pitstudio_rtx.backends import fake  # noqa: E402

LOCK = ROOT / "studio" / "rtx" / "uv.lock"


def _setup(tmp: Path, rec: dict, envelope: object | None):
    poses = kit.write_poses(tmp / "poses.parquet", 2)
    inputs = {rec["poses"]: poses}
    for field in (rec.get("dust") or {}).get("extinction_fields", []):
        (tmp / "field").mkdir(exist_ok=True)
        inputs[field] = tmp / "field"
    env_path = None
    if envelope is not None:
        env_path = tmp / "lidar-envelope.json"
        env_path.write_text(envelope if isinstance(envelope, str) else json.dumps(envelope), encoding="utf-8")
    be = fake.FakeBackend(versions=kit.OVRTX_VERSIONS)
    return inputs, env_path, be


def _run(tmp: Path, rec: dict, envelope: object | None):
    inputs, env_path, be = _setup(tmp, rec, envelope)
    out = tmp / "out"
    out.mkdir()
    outcome = lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, envelope_path=env_path, backend=be)
    return outcome, be, out


@pytest.mark.req("FR-013-05")
def test_a_recipe_whose_lidars_are_all_listed_as_pass_runs(tmp_path: Path) -> None:
    rec = kit.recipe("valid")
    outcome, be, _ = _run(tmp_path, rec, kit.envelope_for(rec))
    assert outcome.exit_code == 0 and outcome.status == "succeeded", outcome.message
    assert be.open_calls == 1


@pytest.mark.req("FR-013-05")
def test_a_recipe_without_a_lidar_needs_no_envelope(tmp_path: Path) -> None:
    rec = kit.recipe("valid-s3")
    outcome, _, _ = _run(tmp_path, rec, None)
    assert outcome.exit_code == 0, outcome.message


def _expect_refused(tmp: Path, rec: dict, envelope: object | None, sensor_id: str | None) -> None:
    outcome, be, out = _run(tmp, rec, envelope)
    assert outcome.exit_code == 2 and outcome.status == "failed", outcome.message
    assert be.open_calls == 0 and be.step_calls == 0  # refused before rendering
    assert list(out.rglob("*")) == []  # nothing promoted
    if sensor_id:
        assert sensor_id in outcome.message  # names the sensor


@pytest.mark.req("FR-013-05")
def test_a_missing_configuration_is_refused_and_names_the_sensor_and_the_fan(tmp_path: Path) -> None:
    rec = kit.recipe("valid")
    env = kit.envelope_for(rec)
    env["configurations"] = [c for c in env["configurations"] if c["scan_type"] != "solid-state"]
    outcome, be, _ = _run(tmp_path, rec, env)
    assert outcome.exit_code == 2 and "solid-state-120" in outcome.message and "-15" in outcome.message
    assert be.open_calls == 0


@pytest.mark.req("FR-013-05")
@pytest.mark.parametrize("field", ["scan_type", "elevation_fan_deg", "azimuth_fan_deg", "mount_rotation_deg"])
def test_any_difference_in_the_configuration_key_makes_it_untested(tmp_path: Path, field: str) -> None:
    rec = kit.recipe("valid")
    env = kit.envelope_for(rec)
    changes = {
        "scan_type": "solid-state",
        "elevation_fan_deg": [-22.5, 21.5],
        "azimuth_fan_deg": [-180, 179],
        "mount_rotation_deg": [1.0, 0.0, 0.0],
    }
    env["configurations"][0][field] = changes[field]  # the first entry is the rotary-64 configuration
    _expect_refused(tmp_path, rec, env, "rotary-64")


@pytest.mark.req("FR-013-05")
def test_a_failing_entry_is_refused_even_when_other_entries_pass(tmp_path: Path) -> None:
    rec = kit.recipe("valid")
    env = kit.envelope_for(rec)
    env["configurations"][1]["status"] = "fail"
    env["configurations"][1]["valid_points"] = 0
    _expect_refused(tmp_path, rec, env, "solid-state-120")


@pytest.mark.req("FR-013-05")
@pytest.mark.parametrize("which", ["ovrtx", "ovstage"])
def test_versions_that_differ_from_the_environment_lock_invalidate_the_envelope(tmp_path: Path, which: str) -> None:
    rec = kit.recipe("valid")
    env = kit.envelope_for(rec, versions={**kit.OVRTX_VERSIONS, which: kit.OVRTX_VERSIONS[which] + "1"})
    _expect_refused(tmp_path, rec, env, None)


@pytest.mark.req("FR-013-05")
@pytest.mark.parametrize("content", ["not json {", "", "[]", '{"schema_version": "1.0"}', "null"])
def test_a_unreadable_or_invalid_envelope_is_refused(tmp_path: Path, content: str) -> None:
    _expect_refused(tmp_path, kit.recipe("valid"), content, None)


@pytest.mark.req("FR-013-05")
def test_a_missing_envelope_file_is_refused(tmp_path: Path) -> None:
    rec = kit.recipe("valid")
    inputs, _, be = _setup(tmp_path, rec, None)
    out = tmp_path / "out"
    out.mkdir()
    outcome = lane.run_stage(
        "st53_sensors", rec, out_dir=out, inputs=inputs, envelope_path=tmp_path / "nope.json", backend=be
    )
    assert outcome.exit_code == 2 and be.open_calls == 0
    outcome = lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, envelope_path=None, backend=be)
    assert outcome.exit_code == 2 and be.open_calls == 0  # no envelope given at all, and the recipe has lidars


@pytest.mark.req("FR-013-05")
def test_the_issue_3_fans_are_untested_unless_the_probe_listed_them(tmp_path: Path) -> None:
    """Spec 7 A2: -45..+45 with no rotation passed (about 150,000 points); -80..+80 with rotation (90, 0, -90) gave 0."""
    rec = kit.recipe("valid")
    passing = {
        "scan_type": "rotary",
        "elevation_fan_deg": [-45, 45],
        "azimuth_fan_deg": [-180, 180],
        "mount_rotation_deg": [0, 0, 0],
    }
    rec["sensors"] = [{**rec["sensors"][0], **{k: v for k, v in passing.items() if k != "scan_type"}}]
    env = kit.envelope_for(rec)
    (tmp_path / "a").mkdir()
    outcome, _, _ = _run(tmp_path / "a", rec, env)
    assert outcome.exit_code == 0, outcome.message
    with pytest.raises(lane.EnvelopeError) as exc:
        lane.check_envelope(
            rec,
            {**env, "configurations": [{**env["configurations"][0], "mount_rotation_deg": [90, 0, -90]}]},
            kit.OVRTX_VERSIONS,
        )
    assert exc.value.sensor == "rotary-64" and exc.value.configuration["mount_rotation_deg"] == [0, 0, 0]


@pytest.mark.req("FR-013-05")
def test_check_envelope_accepts_a_complete_envelope_and_returns_none() -> None:
    rec = kit.recipe("valid")
    assert lane.check_envelope(rec, kit.envelope_for(rec), kit.OVRTX_VERSIONS) is None


# ------------------------------------------------------------------------------------------------------- probe writer
def _lock_versions() -> dict[str, str]:
    packages = tomllib.loads(LOCK.read_text(encoding="utf-8"))["package"]
    return {p["name"]: p["version"] for p in packages if p["name"] in ("ovrtx", "ovstage")}


def _walk_keys(node: object):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_keys(v)


@pytest.mark.req("FR-013-06")
def test_the_probe_writes_a_valid_envelope_with_versions_from_the_lock_and_no_performance_field() -> None:
    import probe_ovrtx

    recipes = [kit.recipe("valid"), kit.recipe("valid-rain")]
    configs = probe_ovrtx.referenced_configurations(recipes)
    assert configs == kit.lidar_configs(recipes[0])  # the rain recipe repeats the rotary configuration: listed once
    results = [{**configs[0], "valid_points": 15872}, {**configs[1], "valid_points": 0}]
    doc = probe_ovrtx.build_envelope(results, lock_path=LOCK, generated="2026-10-11T08:00:00Z")
    assert kit.schema_errors("lidar-envelope.schema.json", doc) == []
    assert doc["versions"] == _lock_versions() and doc["generated"] == "2026-10-11T08:00:00Z"
    assert doc["probe_scene"] == {"cube_edge_m": 2, "cube_range_m": 20}
    assert [c["status"] for c in doc["configurations"]] == [
        "pass",
        "fail",
    ]  # pass exactly when more than 0 valid points
    forbidden = ("time", "ms", "fps", "hz", "throughput", "latency", "memory", "mem", "duration", "wall", "speed")
    assert not [k for k in _walk_keys(doc) if any(f in k.lower() for f in forbidden)]


@pytest.mark.req("FR-013-06")
@pytest.mark.parametrize(("points", "status"), [(0, "fail"), (1, "pass"), (150_000, "pass")])
def test_status_follows_the_valid_point_count_exactly(points: int, status: str) -> None:
    import probe_ovrtx

    cfg = kit.lidar_configs(kit.recipe("valid"))[0]
    doc = probe_ovrtx.build_envelope([{**cfg, "valid_points": points}], lock_path=LOCK)
    assert doc["configurations"][0]["status"] == status and doc["configurations"][0]["valid_points"] == points
    assert kit.schema_errors("lidar-envelope.schema.json", doc) == []


@pytest.mark.req("FR-013-06")
def test_the_written_file_is_the_json_document(tmp_path: Path) -> None:
    import probe_ovrtx

    cfg = kit.lidar_configs(kit.recipe("valid"))[0]
    doc = probe_ovrtx.build_envelope([{**cfg, "valid_points": 10}], lock_path=LOCK)
    path = tmp_path / "lidar-envelope.json"
    probe_ovrtx.write_envelope(doc, path)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and json.loads(text) == doc
    assert "ovrtx" not in sys.modules  # importing the probe module never imports the runtime
