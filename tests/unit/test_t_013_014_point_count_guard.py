# ruff: noqa: E501, PT018
"""T-013-014: warm-up discard, point-count guard (stop at frame k) and per-frame counts in the index.

Requirements: FR-013-07, FR-013-08, FR-013-10.

Oracle: the fake backend counts its own `step` calls (plan.md "FR-013-07", "FR-013-08": an empty frame at index k means
`step` is called exactly k + 1 times, plus the warm-up frames when the backend declares them), tags every step's output with
its step number (so a warm-up frame in a shard is detectable), and returns frames with known beam and valid-point counts
(plan.md "FR-013-10").

Expected API (see test_t_013_010 and test_t_013_012):
- `FakeBackend(script, versions=..., warmup_frames=n)`: `describe().capabilities["warmup_frames"] == n`. The lane calls
  `step` that many times right after `open`, discards those outputs (they reach no shard, no count, no guard), then calls `step`
  once per pose of the pose trace; recorded frame indices are 0-based and exclude the warm-up.
- Lidar frame output (the backend side of the adapter): a dict with `kind: "lidar"`, `beams_emitted`, `valid_count`
  and equal-length arrays `x`, `y`, `z`, `range_m`, `intensity`, `flags` (bit 0x40 = valid), `material_class` (0 diffuse,
  1 retro), `object_id`, `beam`, `echo` (see `sensor_kit.lidar_output`).
- A recorded clean lidar frame with no valid point stops the stage at once (no further `step`), with `error_class`
  `"lidar-zero-points"`, `exit_code` 1, a message naming the sensor id and the frame index, `status` `"failed"`, and no file under
  `out_dir` (nothing of the run is promoted, not even earlier frames).
- On success `outcome.index` is the DC-013-03 shard index: `frames` lists `{sensor, frame, beams_emitted, valid_points,
  file}` for every recorded lidar frame, in order (the sensors of a step in recipe order), and each `file` is a Parquet
  shard of `files` holding exactly the valid rows (columns of `$defs/lidar_return`: frame, beam, echo, x_m, y_m, z_m,
  range_m, intensity, flags, material_class ("retro"/"diffuse"), object_id).
"""

from __future__ import annotations

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

COLUMNS = ["frame", "beam", "echo", "x_m", "y_m", "z_m", "range_m", "intensity", "flags", "material_class", "object_id"]


def _recipe(n_lidars: int = 1) -> dict:
    rec = kit.recipe("valid")
    rec["sensors"] = rec["sensors"][:n_lidars]
    return rec


def _run(tmp: Path, script, *, poses: int = 4, warmup: int = 0, n_lidars: int = 1, **fake_kw):
    rec = _recipe(n_lidars)
    be = fake.FakeBackend(script, versions=kit.OVRTX_VERSIONS, warmup_frames=warmup, **fake_kw)
    inputs = {rec["poses"]: kit.write_poses(tmp / "poses.parquet", poses)}
    for f in rec["dust"]["extinction_fields"]:
        (tmp / "field").mkdir(exist_ok=True)
        inputs[f] = tmp / "field"
    env = tmp / "env.json"
    import json

    env.write_text(json.dumps(kit.envelope_for(rec)), encoding="utf-8")
    out = tmp / "out"
    out.mkdir()
    outcome = lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, envelope_path=env, backend=be)
    return outcome, be, out


def _tagged(step_index: int, n: int = 120, n_valid: int = 100) -> dict:
    frame = kit.lidar_output(n=n, n_valid=n_valid, seed=step_index)
    frame["intensity"] = np.full(n, (step_index + 1) / 1000.0, dtype=np.float32)  # the step number, readable in a shard
    return frame


@pytest.mark.req("FR-013-07")
def test_without_warm_up_every_step_is_recorded(tmp_path: Path) -> None:
    outcome, be, _ = _run(tmp_path, lambda sensor, i: _tagged(i), poses=4, warmup=0)
    assert outcome.exit_code == 0, outcome.message
    assert be.step_calls == 4 and [f["frame"] for f in outcome.index["frames"]] == [0, 1, 2, 3]


@pytest.mark.req("FR-013-07")
def test_forty_warm_up_frames_are_rendered_and_discarded_before_the_first_recorded_frame(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    outcome, be, out = _run(tmp_path, lambda sensor, i: _tagged(i), poses=3, warmup=40)
    assert outcome.exit_code == 0, outcome.message
    assert be.step_calls == 40 + 3  # 40 discarded + 3 recorded
    assert [f["frame"] for f in outcome.index["frames"]] == [0, 1, 2]
    seen = set()
    for entry in outcome.index["files"]:
        table = pq.read_table(out / entry["path"])
        seen |= {round(float(v), 3) for v in table.column("intensity").to_pylist()}
    assert seen == {0.041, 0.042, 0.043}  # steps 40, 41, 42; no warm-up frame (0.001 ... 0.040) reached a shard


@pytest.mark.req("FR-013-07")
def test_empty_frames_during_warm_up_are_discarded_not_guarded(tmp_path: Path) -> None:
    def script(sensor: dict, i: int) -> dict:
        return _tagged(i, n_valid=0) if i < 5 else _tagged(i)  # a renderer may return nothing while it warms up

    outcome, be, _ = _run(tmp_path, script, poses=2, warmup=40)
    assert outcome.exit_code == 0 and be.step_calls == 42, outcome.message


@pytest.mark.req("FR-013-08")
@pytest.mark.parametrize("k", [0, 1, 3])
def test_an_empty_clean_frame_stops_the_run_at_that_frame(tmp_path: Path, k: int) -> None:
    outcome, be, out = _run(tmp_path, lambda sensor, i: _tagged(i, n_valid=0 if i == k else 100), poses=5, warmup=0)
    assert be.step_calls == k + 1  # `step` is never called again after the empty frame
    assert outcome.status == "failed" and outcome.error_class == "lidar-zero-points" and outcome.exit_code == 1
    assert "rotary-64" in outcome.message and str(k) in outcome.message
    assert list(out.rglob("*")) == [] and outcome.index is None  # nothing of the run is promoted


@pytest.mark.req("FR-013-08")
def test_the_guard_counts_recorded_frames_and_names_the_sensor_that_failed(tmp_path: Path) -> None:
    def script(sensor: dict, i: int) -> dict:
        empty = sensor["id"] == "solid-state-120" and i == 40 + 2  # recorded frame 2 of the second lidar
        return _tagged(i, n_valid=0 if empty else 100)

    outcome, be, out = _run(tmp_path, script, poses=5, warmup=40, n_lidars=2)
    assert be.step_calls == 40 + 3
    assert (
        outcome.error_class == "lidar-zero-points" and "solid-state-120" in outcome.message and "2" in outcome.message
    )
    assert list(out.rglob("*")) == []


@pytest.mark.req("FR-013-08")
def test_flags_without_the_valid_bit_count_as_no_point(tmp_path: Path) -> None:
    def script(sensor: dict, i: int) -> dict:
        frame = _tagged(i)
        if i == 1:
            frame["flags"] = np.full(120, 0x3F, dtype=np.uint8)  # points present, none flagged valid (0x40)
            frame["valid_count"] = 0
        return frame

    outcome, be, _ = _run(tmp_path, script, poses=3)
    assert outcome.error_class == "lidar-zero-points" and be.step_calls == 2


@pytest.mark.req("FR-013-08")
def test_the_guard_applies_to_lidar_only_a_radar_frame_without_detections_is_fine(tmp_path: Path) -> None:
    rec = kit.recipe("valid-s4a")
    empty = {
        "kind": "radar",
        "native_sign": "approaching-positive",
        **{
            k: np.zeros(0, dtype=t)
            for k, t in (
                ("x", np.float32),
                ("y", np.float32),
                ("z", np.float32),
                ("rcs_dbsm", np.float32),
                ("radial_velocity_native", np.float32),
                ("object_id", np.uint32),
            )
        },
    }
    be = fake.FakeBackend(lambda sensor, i: empty, versions=kit.OVRTX_VERSIONS)
    out = tmp_path / "out"
    out.mkdir()
    inputs = {rec["poses"]: kit.write_poses(tmp_path / "poses.parquet", 3)}
    outcome = lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, backend=be)
    assert outcome.exit_code == 0 and be.step_calls == 3, outcome.message


@pytest.mark.req("FR-013-10")
def test_the_index_records_the_beam_and_valid_point_counts_of_every_frame(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    def script(sensor: dict, i: int) -> dict:
        n_valid = 100 + 10 * i
        return {**kit.lidar_output(n=200, n_valid=n_valid, seed=i), "beams_emitted": 1000 + i}

    outcome, _, out = _run(tmp_path, script, poses=4, n_lidars=2)
    assert outcome.exit_code == 0, outcome.message
    index = outcome.index
    assert kit.schema_errors("sensor-shard.schema.json", index) == []
    frames = index["frames"]
    assert [(f["sensor"], f["frame"]) for f in frames] == [
        (s, k) for k in range(4) for s in ("rotary-64", "solid-state-120")
    ]
    for f in frames:
        assert f["beams_emitted"] == 1000 + f["frame"] and f["valid_points"] == 100 + 10 * f["frame"]
    files = {e["path"]: e for e in index["files"]}
    assert all(f["file"] in files for f in frames)
    total_rows = 0
    for entry in files.values():
        table = pq.read_table(out / entry["path"])
        assert table.column_names == COLUMNS and table.num_rows == entry["rows"]
        total_rows += table.num_rows
    assert total_rows == sum(f["valid_points"] for f in frames)  # only valid returns are written
    assert index["backend"] == "fake" and index["stage"] == "st53_sensors" and index["scenario"] == "S1"


@pytest.mark.req("FR-013-10")
def test_rows_round_trip_the_valid_returns_of_the_frame(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    frame = kit.lidar_output(n=200, n_valid=150, seed=5)
    outcome, _, out = _run(tmp_path, lambda sensor, i: frame, poses=1)
    entry = outcome.index["files"][0]
    table = pq.read_table(out / entry["path"]).to_pydict()
    valid = (frame["flags"] & 0x40) != 0
    np.testing.assert_allclose(table["x_m"], frame["x"][valid], rtol=1e-6)
    np.testing.assert_allclose(table["range_m"], frame["range_m"][valid], rtol=1e-6)
    np.testing.assert_allclose(table["intensity"], frame["intensity"][valid], rtol=1e-6)
    assert table["beam"] == frame["beam"][valid].tolist() and table["object_id"] == frame["object_id"][valid].tolist()
    assert table["material_class"] == ["retro" if m else "diffuse" for m in frame["material_class"][valid]]
    assert set(table["frame"]) == {0}
