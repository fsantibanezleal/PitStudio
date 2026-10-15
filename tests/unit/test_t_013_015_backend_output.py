# ruff: noqa: E501, PT018, RUF059
"""T-013-015: backend-output validation against a malformed-frame corpus.

Requirements: FR-013-09.

Oracle: a hand-written malformed-frame corpus, one defect per case (wrong dtype, wrong shape, non-finite coordinates,
intensities, RCS or radial velocities on valid entries, a valid-point count that disagrees with the flags, an image whose size
differs from the configured resolution); Hypothesis corrupts random valid entries (plan.md "FR-013-09").

Expected API (see test_t_013_014): when a frame returned by the backend violates the output contract the stage fails with
`error_class` `"backend-output-invalid"`, `exit_code` 1, `status` `"failed"`, a message that names the offending field and
the sensor, and promotes no output. The contract: lidar arrays `x`, `y`, `z`, `range_m`, `intensity` float32; `flags`,
`material_class` uint8; `object_id`, `beam` uint32; all 1-D with equal length; every field present; `valid_count` equal to
the number of entries with bit 0x40; `0 <= valid_count <= beams_emitted`; the values of valid entries finite (invalid entries
may hold anything). Camera outputs: `hdr` (height, width, 3), `distance` and `semantic` (height, width), `ldr` (height,
width, 3) for the configured resolution (a non-finite `distance` is allowed: no hit). Radar outputs: 1-D `x`, `y`, `z`,
`rcs_dbsm`, `radial_velocity_native` float32 and `object_id` uint32 of equal length, finite values.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import lane  # noqa: E402
from pitstudio_rtx.backends import fake  # noqa: E402


def _run_lidar(tmp: Path, bad):
    """Frame 0 is clean, frame 1 is `bad(frame)`; returns (outcome, backend, out_dir)."""
    rec = kit.recipe("valid")
    rec["sensors"] = rec["sensors"][:1]

    def script(sensor: dict, i: int) -> dict:
        frame = kit.lidar_output(n=100, n_valid=80, seed=i)
        return bad(frame) if i == 1 else frame

    be = fake.FakeBackend(script, versions=kit.OVRTX_VERSIONS)
    inputs = {rec["poses"]: kit.write_poses(tmp / "poses.parquet", 3)}
    for f in rec["dust"]["extinction_fields"]:
        (tmp / "field").mkdir(exist_ok=True)
        inputs[f] = tmp / "field"
    env = tmp / "env.json"
    env.write_text(json.dumps(kit.envelope_for(rec)), encoding="utf-8")
    out = tmp / "out"
    out.mkdir()
    return lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, envelope_path=env, backend=be), be, out


def _set(field: str, value):
    def apply(frame: dict) -> dict:
        frame[field] = value(frame) if callable(value) else value
        return frame

    return apply


def _nan_at(field: str, idx: int, bad: float = np.nan):
    def apply(frame: dict) -> dict:
        arr = frame[field].copy()
        arr[idx] = bad
        frame[field] = arr
        return frame

    return apply


def _drop(field: str):
    def apply(frame: dict) -> dict:
        del frame[field]
        return frame

    return apply


LIDAR_CASES = [
    ("x-float64", _set("x", lambda f: f["x"].astype(np.float64)), "x"),
    ("range-float64", _set("range_m", lambda f: f["range_m"].astype(np.float64)), "range_m"),
    ("intensity-int", _set("intensity", lambda f: (f["intensity"] * 255).astype(np.uint8)), "intensity"),
    ("flags-int32", _set("flags", lambda f: f["flags"].astype(np.int32)), "flags"),
    ("object-id-int64", _set("object_id", lambda f: f["object_id"].astype(np.int64)), "object_id"),
    ("y-shorter", _set("y", lambda f: f["y"][:-1]), "y"),
    ("z-2d", _set("z", lambda f: f["z"].reshape(10, 10)), "z"),
    ("beam-longer", _set("beam", lambda f: np.concatenate([f["beam"], f["beam"][:3]])), "beam"),
    ("x-nan-valid", _nan_at("x", 3), "x"),
    ("y-inf-valid", _nan_at("y", 0, np.inf), "y"),
    ("z-neg-inf-valid", _nan_at("z", 79, -np.inf), "z"),
    ("range-nan-valid", _nan_at("range_m", 10), "range_m"),
    ("intensity-nan-valid", _nan_at("intensity", 40), "intensity"),
    ("valid-count-too-high", _set("valid_count", 100), "valid_count"),
    ("valid-count-too-low", _set("valid_count", 79), "valid_count"),
    ("valid-count-negative", _set("valid_count", -1), "valid_count"),
    ("beams-below-valid", _set("beams_emitted", 10), "beams_emitted"),
    ("missing-intensity", _drop("intensity"), "intensity"),
    ("missing-flags", _drop("flags"), "flags"),
]


@pytest.mark.req("FR-013-09")
@pytest.mark.parametrize(("bad", "field"), [c[1:] for c in LIDAR_CASES], ids=[c[0] for c in LIDAR_CASES])
def test_a_malformed_lidar_frame_fails_the_stage_naming_the_field(tmp_path: Path, bad, field: str) -> None:
    outcome, be, out = _run_lidar(tmp_path, bad)
    assert outcome.status == "failed" and outcome.error_class == "backend-output-invalid" and outcome.exit_code == 1
    assert re.search(rf"(?<![A-Za-z_]){re.escape(field)}(?![A-Za-z_])", outcome.message), outcome.message
    assert "rotary-64" in outcome.message
    assert list(out.rglob("*")) == [] and outcome.index is None  # no partial output


@pytest.mark.req("FR-013-09")
def test_non_finite_values_on_invalid_entries_are_allowed(tmp_path: Path) -> None:
    def bad(frame: dict) -> dict:
        for field in ("x", "y", "z", "range_m", "intensity"):
            arr = frame[field].copy()
            arr[80:] = np.nan  # the 20 invalid slots (flags without 0x40) hold NaN
            frame[field] = arr
        return frame

    outcome, _, _ = _run_lidar(tmp_path, bad)
    assert outcome.exit_code == 0 and outcome.status == "succeeded", outcome.message


@pytest.mark.req("FR-013-09")
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    field=st.sampled_from(["x", "y", "z", "range_m", "intensity"]),
    idx=st.integers(0, 79),
    bad=st.sampled_from([np.nan, np.inf, -np.inf]),
)
def test_any_non_finite_value_on_a_valid_entry_is_rejected(
    tmp_path_factory: pytest.TempPathFactory, field: str, idx: int, bad: float
) -> None:
    tmp = tmp_path_factory.mktemp("nf")
    outcome, _, out = _run_lidar(tmp, _nan_at(field, idx, bad))
    assert outcome.error_class == "backend-output-invalid" and field in outcome.message
    assert list(out.rglob("*")) == []


def _run_camera(tmp: Path, bad):
    rec = kit.recipe("valid-s3")
    cam = rec["sensors"][0]
    w, h = cam["width_px"], cam["height_px"]

    def script(sensor: dict, i: int) -> dict:
        frame = kit.camera_output(w, h, i, tuple(cam["outputs"]))
        return bad(frame) if i == 1 else frame

    be = fake.FakeBackend(script, versions=kit.OVRTX_VERSIONS)
    inputs = {rec["poses"]: kit.write_poses(tmp / "poses.parquet", 3)}
    inputs[rec["haze"]["extinction_field"]] = tmp  # a declared stage input (the C3 extinction field)
    out = tmp / "out"
    out.mkdir()
    return lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, backend=be), out, cam


@pytest.mark.req("FR-013-09")
@pytest.mark.parametrize("field", ["hdr", "distance", "semantic", "ldr"])
@pytest.mark.parametrize("how", ["width-minus-one", "height-minus-one", "transposed"])
def test_an_image_whose_size_differs_from_the_configured_resolution_is_rejected(
    tmp_path: Path, field: str, how: str
) -> None:
    def bad(frame: dict) -> dict:
        arr = frame[field]
        frame[field] = {"width-minus-one": arr[:, :-1], "height-minus-one": arr[:-1], "transposed": arr.swapaxes(0, 1)}[
            how
        ]
        return frame

    outcome, out, _ = _run_camera(tmp_path, bad)  # the S3 example outputs HdrColor, LdrColor, distance and semantic
    assert outcome.error_class == "backend-output-invalid" and field in outcome.message, outcome.message
    assert list(out.rglob("*")) == []


@pytest.mark.req("FR-013-09")
def test_a_non_finite_distance_is_a_pixel_without_a_hit_and_is_accepted(tmp_path: Path) -> None:
    def sky(frame: dict) -> dict:
        if "distance" in frame:
            d = frame["distance"].copy()
            d[:5] = np.inf
            frame["distance"] = d
        return frame

    outcome, _, _ = _run_camera(tmp_path, sky)
    assert outcome.exit_code == 0, outcome.message


@pytest.mark.req("FR-013-09")
@pytest.mark.parametrize("field", ["rcs_dbsm", "radial_velocity_native"])
@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_non_finite_radar_values_are_rejected(tmp_path: Path, field: str, bad: float) -> None:
    rec = kit.recipe("valid-s4a")

    def script(sensor: dict, i: int) -> dict:
        frame = kit.radar_output(30, i)
        if i == 1:
            frame[field] = frame[field].copy()
            frame[field][7] = bad
        return frame

    be = fake.FakeBackend(script, versions=kit.OVRTX_VERSIONS)
    out = tmp_path / "out"
    out.mkdir()
    inputs = {rec["poses"]: kit.write_poses(tmp_path / "poses.parquet", 3)}
    outcome = lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, backend=be)
    assert outcome.error_class == "backend-output-invalid" and field in outcome.message
    assert list(out.rglob("*")) == []
