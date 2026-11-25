# ruff: noqa: E501, PT018, PT011
"""T-013-043: pinhole intrinsics, poses and the GSD worked example.

Requirements: FR-013-19, P-013-14 (the GPU marker check of FR-013-19 belongs to T-013-070).

Oracle: the hand-calculated GSD worked example (p_x = 4 um, f = 8.8 mm, H_agl = 100 m: GSD = p_x H / f = 4.545 cm, "about 4.5 cm"),
the intrinsic matrix K = [[f/p, 0, c_x], [0, f/p, c_y], [0, 0, 1]] by hand (f/p = 2200 px), an analytic projection (the point (1, 0.5, 10) m in
front of an identity camera falls at (960 + 2200/10, 540 + 2200 x 0.05) = (1180, 650) px), and the metamorphic relations P-013-14
(MR1 project then back-project with the ground-truth distance returns the point, atol 1e-6 m; MR2 the GSD is linear in H_agl and p_x and inversely
proportional to f, rtol 1e-12; MR3 a common rigid motion of camera and scene leaves the pixels unchanged).

Expected API:
- `pitstudio.sensors.camera.intrinsics(focal_length_m, pixel_pitch_m, width_px, height_px, principal_point_px) -> float64 (3, 3)` (fx = fy = f / p).
- `camera.gsd_m(pixel_pitch_m, h_agl_m, focal_length_m)` = p H / f.
- `camera.project(K, world_from_camera, points_world) -> (pixels (n, 2), depth (n,))`: `world_from_camera` a 4 x 4 pose in the column-vector
  convention (rotation block and translation in the last column); camera axes x right, y down, z forward (OpenCV); a point behind the camera
  (depth <= 0) raises `ValueError`.
- `camera.backproject(K, world_from_camera, pixels, depth) -> points_world (n, 3)`.
- `pitstudio_rtx.shards.image_record(camera, *, image, file, world_from_camera, h_agl_m=None) -> dict`: the DC-013-03 image record of a camera
  block (`camera` a recipe camera dict): `image`, `sensor` (its id), `file`, `width_px`, `height_px`, `fx_px` = `fy_px` = f / p, `cx_px`, `cy_px`,
  `world_from_camera` as 16 floats (row-major), and, when `h_agl_m` is given, `h_agl_m` and `gsd_m`.
"""

from __future__ import annotations

import math
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
from pitstudio.sensors import camera  # noqa: E402
from pitstudio_rtx import shards  # noqa: E402


def _pose(rotvec: np.ndarray, t: np.ndarray) -> np.ndarray:
    """4 x 4 pose from a rotation vector (Rodrigues) and a translation (column-vector convention)."""
    theta = float(np.linalg.norm(rotvec))
    if theta < 1e-12:
        r = np.eye(3)
    else:
        k = rotvec / theta
        kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        r = np.eye(3) + math.sin(theta) * kx + (1 - math.cos(theta)) * kx @ kx
    out = np.eye(4)
    out[:3, :3], out[:3, 3] = r, t
    return out


@pytest.mark.req("FR-013-19")
def test_intrinsics_from_focal_length_pixel_pitch_and_principal_point() -> None:
    k = camera.intrinsics(0.0088, 4e-6, 1920, 1080, (960.0, 540.0))
    np.testing.assert_allclose(k, [[2200.0, 0, 960.0], [0, 2200.0, 540.0], [0, 0, 1.0]], rtol=1e-12)
    assert k.dtype == np.float64 and k.shape == (3, 3)
    other = camera.intrinsics(0.006, 3e-6, 1280, 720, (640.0, 360.0))  # the S3 example camera: f / p = 2000
    assert other[0, 0] == pytest.approx(2000.0, rel=1e-12) and other[1, 1] == pytest.approx(2000.0, rel=1e-12)


@pytest.mark.req("FR-013-19")
def test_gsd_worked_example_is_4_5_cm() -> None:
    gsd = camera.gsd_m(4e-6, 100.0, 0.0088)
    assert gsd == pytest.approx(4e-6 * 100.0 / 0.0088, rel=1e-12)
    assert gsd == pytest.approx(0.0454545454545, rel=1e-9) and round(gsd * 100, 1) == 4.5  # about 4.5 cm


@pytest.mark.req("FR-013-19")
def test_a_point_in_front_of_an_identity_camera_projects_by_hand() -> None:
    k = camera.intrinsics(0.0088, 4e-6, 1920, 1080, (960.0, 540.0))
    px, depth = camera.project(k, np.eye(4), np.array([[1.0, 0.5, 10.0], [0.0, 0.0, 5.0]]))
    np.testing.assert_allclose(px, [[1180.0, 650.0], [960.0, 540.0]], atol=1e-9)
    np.testing.assert_allclose(depth, [10.0, 5.0], atol=1e-12)
    moved = camera.project(
        k, _pose(np.zeros(3), np.array([100.0, -20.0, 7.0])), np.array([[101.0, -19.5, 17.0]])
    )  # same point, shifted
    np.testing.assert_allclose(moved[0], [[1180.0, 650.0]], atol=1e-9)


@pytest.mark.req("FR-013-19")
def test_a_point_behind_the_camera_is_rejected() -> None:
    k = camera.intrinsics(0.0088, 4e-6, 1920, 1080, (960.0, 540.0))
    for z in (0.0, -3.0):
        with pytest.raises(ValueError):
            camera.project(k, np.eye(4), np.array([[0.0, 0.0, z]]))


@pytest.mark.req("FR-013-19")
def test_the_image_record_holds_k_pose_and_gsd() -> None:
    cam = kit.recipe("valid-s2")["sensors"][0]
    pose = [1, 0, 0, 12.5, 0, 1, 0, -3.0, 0, 0, 1, 100.0, 0, 0, 0, 1]
    rec = shards.image_record(cam, image=4, file="images/survey-cam/000004.zarr", world_from_camera=pose, h_agl_m=100.0)
    assert kit.def_errors("sensor-shard.schema.json", "image_record", rec) == []
    assert (rec["image"], rec["sensor"], rec["width_px"], rec["height_px"]) == (4, "survey-cam", 1920, 1080)
    assert rec["fx_px"] == pytest.approx(2200.0, rel=1e-12) and rec["fy_px"] == pytest.approx(2200.0, rel=1e-12)
    assert (rec["cx_px"], rec["cy_px"]) == (960.0, 540.0) and rec["world_from_camera"] == [float(x) for x in pose]
    assert rec["h_agl_m"] == 100.0 and rec["gsd_m"] == pytest.approx(0.0454545454545, rel=1e-9)
    assert "gsd_m" not in shards.image_record(
        cam, image=0, file="images/survey-cam/000000.zarr", world_from_camera=pose
    )


_POSE = st.tuples(
    st.lists(st.floats(-2.0, 2.0), min_size=3, max_size=3), st.lists(st.floats(-500.0, 500.0), min_size=3, max_size=3)
)


@pytest.mark.req("P-013-14")
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), pose=_POSE, f=st.floats(0.004, 0.05), p=st.floats(2e-6, 8e-6))
def test_project_then_backproject_returns_the_point(seed: int, pose: tuple, f: float, p: float) -> None:
    rng = np.random.default_rng(seed)
    t_pose = _pose(np.array(pose[0]), np.array(pose[1]))
    k = camera.intrinsics(f, p, 1920, 1080, (960.0, 540.0))
    cam_pts = np.column_stack([rng.uniform(-0.3, 0.3, 20), rng.uniform(-0.2, 0.2, 20), np.ones(20)]) * rng.uniform(
        1.0, 1000.0, (20, 1)
    )
    world = (t_pose[:3, :3] @ cam_pts.T).T + t_pose[:3, 3]
    px, depth = camera.project(k, t_pose, world)
    back = camera.backproject(k, t_pose, px, depth)
    np.testing.assert_allclose(back, world, atol=1e-6, rtol=1e-12)  # MR1


@pytest.mark.req("P-013-14")
@settings(max_examples=60, deadline=None)
@given(
    h=st.floats(1.0, 500.0),
    p=st.floats(1e-6, 1e-5),
    f=st.floats(0.002, 0.1),
    factor=st.sampled_from([2.0, 4.0, 0.5, 8.0]),
)
def test_gsd_is_linear_in_height_and_pitch_and_inversely_proportional_to_the_focal_length(
    h: float, p: float, f: float, factor: float
) -> None:
    base = camera.gsd_m(p, h, f)
    assert camera.gsd_m(p, h * factor, f) == pytest.approx(factor * base, rel=1e-12)  # MR2
    assert camera.gsd_m(p * factor, h, f) == pytest.approx(factor * base, rel=1e-12)
    assert camera.gsd_m(p, h, f * factor) == pytest.approx(base / factor, rel=1e-12)


@pytest.mark.req("P-013-14")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), pose=_POSE, motion=_POSE)
def test_a_common_rigid_motion_of_camera_and_scene_leaves_the_pixels_unchanged(
    seed: int, pose: tuple, motion: tuple
) -> None:
    rng = np.random.default_rng(seed)
    cam_pose = _pose(np.array(pose[0]), np.array(pose[1]))
    m = _pose(np.array(motion[0]), np.array(motion[1]))
    k = camera.intrinsics(0.0088, 4e-6, 1920, 1080, (960.0, 540.0))
    cam_pts = np.column_stack([rng.uniform(-0.3, 0.3, 15), rng.uniform(-0.2, 0.2, 15), np.ones(15)]) * rng.uniform(
        1.0, 800.0, (15, 1)
    )
    world = (cam_pose[:3, :3] @ cam_pts.T).T + cam_pose[:3, 3]
    moved_world = (m[:3, :3] @ world.T).T + m[:3, 3]
    px0, d0 = camera.project(k, cam_pose, world)
    px1, d1 = camera.project(k, m @ cam_pose, moved_world)  # MR3
    np.testing.assert_allclose(px1, px0, atol=1e-6)
    np.testing.assert_allclose(d1, d0, atol=1e-6)
