# ruff: noqa: E501, PT018
"""T-013-024: radar configuration guard, detection contract, sign normalisation, dust independence.

Requirements: FR-013-21, FR-013-22, FR-013-24.

Oracle: the band limits written from the spec (76-81 GHz, wavelength 3.70-3.95 mm) with the boundary values on both sides;
hand-written scripted detections with a known native sign (positive = range increasing is the PitStudio convention, so a
native "approaching-positive" value v is stored as -v, and a native "approaching-negative" value is stored unchanged); the
detection row schema `$defs/radar_detection` of DC-013-03 (draft); byte equality of the shards of two runs, one of which
carries a dust block in its recipe.

Expected API (see test_t_013_012, test_t_013_014): an S4a recipe goes through `lane.run_stage("st53_sensors", ...)`.
- A radar with a wavelength outside 3.70 mm to 3.95 mm, with `motion_bvh` false, or in a session that also holds a camera is
  refused with `exit_code` 2 before rendering (the backend is not opened), the pointer naming the offending value.
- A radar frame from the backend is a dict (`kind: "radar"`) with equal-length 1-D arrays `x`, `y`, `z` (float32, sensor
  frame, m), `rcs_dbsm` (float32), `radial_velocity_native` (float32), `object_id` (uint32) and `native_sign` ("approaching-
  positive": positive velocity means approaching, or "approaching-negative"). The lane writes the detections as Parquet shards
  of content `radar-detections` with the columns `frame, x_m, y_m, z_m, rcs_dbsm, radial_velocity_m_per_s, object_id`, the
  velocity normalised to "positive = range increasing"; every row is valid against `$defs/radar_detection`.
- The shards of an S4a run are the same bytes whatever `dust` setting the recipe carries.
"""

from __future__ import annotations

import copy
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


def _rec(**radar: object) -> dict:
    rec = kit.recipe("valid-s4a")
    rec["sensors"][0].update(radar)
    return rec


def _run(tmp: Path, rec: dict, script=None):
    be = fake.FakeBackend(script, versions=kit.OVRTX_VERSIONS)
    out = tmp / "out"
    out.mkdir()
    inputs = {rec["poses"]: kit.write_poses(tmp / "poses.parquet", 2)}
    for extra in (rec.get("dust") or {}).get("extinction_fields", []):
        inputs[extra] = tmp
    return lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, backend=be), be, out


@pytest.mark.req("FR-013-21")
@pytest.mark.parametrize(
    ("wavelength", "accepted"),
    [(0.0037, True), (0.00395, True), (0.0039, True), (0.00369, False), (0.00396, False), (0.0, False), (3.9, False)],
)
def test_the_wavelength_must_be_in_the_76_to_81_ghz_band(tmp_path: Path, wavelength: float, accepted: bool) -> None:
    outcome, be, _ = _run(tmp_path, _rec(wavelength_m=wavelength))
    if accepted:
        assert outcome.exit_code == 0, outcome.message
    else:
        assert outcome.exit_code == 2 and outcome.pointer == "/sensors/0/wavelength_m" and be.open_calls == 0


@pytest.mark.req("FR-013-21")
def test_motion_bvh_must_be_enabled(tmp_path: Path) -> None:
    outcome, be, out = _run(tmp_path, _rec(motion_bvh=False))
    assert outcome.exit_code == 2 and outcome.pointer == "/sensors/0/motion_bvh" and be.open_calls == 0
    assert list(out.rglob("*")) == []


@pytest.mark.req("FR-013-21")
def test_a_camera_in_the_radar_session_is_refused(tmp_path: Path) -> None:
    rec = _rec()
    camera = copy.deepcopy(kit.recipe("valid-s3")["sensors"][0])
    rec["sensors"].append(camera)
    outcome, be, _ = _run(tmp_path, rec)
    assert outcome.exit_code == 2 and outcome.pointer == "/sensors/1/kind" and be.open_calls == 0 and be.step_calls == 0


def _script(native: list[float], sign: str):
    n = len(native)

    def script(sensor: dict, i: int) -> dict:
        return {
            "kind": "radar",
            "x": np.linspace(20, 80, n, dtype=np.float32),
            "y": np.zeros(n, np.float32),
            "z": np.ones(n, np.float32),
            "rcs_dbsm": np.linspace(-5, 15, n, dtype=np.float32),
            "radial_velocity_native": np.array(native, dtype=np.float32),
            "object_id": np.arange(n, dtype=np.uint32),
            "native_sign": sign,
        }

    return script


@pytest.mark.req("FR-013-22")
@pytest.mark.parametrize(
    ("sign", "native", "expected"),
    [
        ("approaching-positive", [5.0, -3.0, 0.0, 11.11], [-5.0, 3.0, -0.0, -11.11]),
        ("approaching-negative", [5.0, -3.0, 0.0, -11.11], [5.0, -3.0, 0.0, -11.11]),
    ],
)
def test_radial_velocity_is_stored_as_positive_when_the_range_increases(
    tmp_path: Path, sign: str, native: list[float], expected: list[float]
) -> None:
    import pyarrow.parquet as pq

    outcome, _, out = _run(tmp_path, _rec(), _script(native, sign))
    assert outcome.exit_code == 0, outcome.message
    (entry,) = [e for e in outcome.index["files"] if e["content"] == "radar-detections"]
    table = pq.read_table(out / entry["path"])
    got = table.column("radial_velocity_m_per_s").to_numpy()
    # two frames of the same scripted detections: the second half repeats the first
    np.testing.assert_allclose(got[: len(native)], expected, atol=1e-6)
    assert table.num_rows == 2 * len(native)


@pytest.mark.req("FR-013-22")
def test_detections_are_parquet_rows_valid_against_the_row_schema(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    outcome, _, out = _run(tmp_path, _rec(), _script([1.0, -2.0, 3.0], "approaching-positive"))
    assert outcome.exit_code == 0 and kit.schema_errors("sensor-shard.schema.json", outcome.index) == []
    (entry,) = [e for e in outcome.index["files"] if e["content"] == "radar-detections"]
    assert entry["format"] == "parquet"
    table = pq.read_table(out / entry["path"])
    assert table.column_names == ["frame", "x_m", "y_m", "z_m", "rcs_dbsm", "radial_velocity_m_per_s", "object_id"]
    assert set(table.column("frame").to_pylist()) == {0, 1}
    for row in table.to_pylist():
        assert kit.def_errors("sensor-shard.schema.json", "radar_detection", row) == []
    assert (
        outcome.index["scenario"] == "S4a" and outcome.index["frames"] == []
    )  # radar rows are not lidar frame records


@pytest.mark.req("FR-013-24")
def test_the_radar_shards_do_not_depend_on_any_dust_setting(tmp_path: Path) -> None:
    plain = _rec()
    dusty = _rec()
    dusty["dust"] = {"transmittance_grid": [1.0, 0.5, 0.02], "beta_spacing_m": 0.25, "dust_return_intensity": 0.5}
    heavy = copy.deepcopy(dusty)
    heavy["dust"]["transmittance_grid"] = [0.02]
    digests = []
    for name, rec in (("a", plain), ("b", dusty), ("c", heavy)):
        (tmp_path / name).mkdir()
        outcome, _, _ = _run(tmp_path / name, rec, _script([4.0, -1.0], "approaching-negative"))
        assert outcome.exit_code == 0, outcome.message
        digests.append([(e["path"], e["sha256"], e["bytes"]) for e in outcome.index["files"]])
    assert digests[0] == digests[1] == digests[2]
