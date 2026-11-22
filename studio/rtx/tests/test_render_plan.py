# SPDX-License-Identifier: Apache-2.0
"""Pose plan, spline and camera/sun matrices of `pitstudio_rtx.render.plan`."""

from __future__ import annotations

import math

import numpy as np
import pytest
from conftest import RECIPE_PATH
from pitstudio_rtx.render.plan import camera_matrix, plan, sun_matrix
from pitstudio_rtx.render.recipe import load_recipe


@pytest.fixture(scope="module")
def full():
    return plan(load_recipe(RECIPE_PATH))


def test_counts_and_order(full):
    stills = [p for p in full if p.kind == "still"]
    frames = [p for p in full if p.kind == "flyover"]
    assert [p.kind for p in full] == ["still"] * len(stills) + ["flyover"] * len(frames)
    assert len(stills) >= 6
    assert len(frames) == 600  # 20 s at 30 fps
    assert [p.index for p in frames] == list(range(600))
    assert frames[7].out == "flyover/frame_00007.png"
    assert stills[0].out == f"stills/{stills[0].id}.png"


def test_required_views_present(full):
    ids = {p.id for p in full if p.kind == "still"}
    required = {
        "pit-overview-north",
        "haul-road-ramp",
        "east-wall-c1",
        "pit-floor-loading",
        "sunrise-oblique",
        "plan-view",
    }
    assert required <= ids


def test_plan_is_deterministic():
    recipe = load_recipe(RECIPE_PATH)
    assert plan(recipe) == plan(load_recipe(RECIPE_PATH))


def test_spline_hits_first_and_last_control_point(full):
    pts = load_recipe(RECIPE_PATH).data["flyover"]["control_points"]
    frames = [p for p in full if p.kind == "flyover"]
    assert frames[0].eye == pytest.approx(pts[0]["eye"], abs=1e-6)
    assert frames[-1].eye == pytest.approx(pts[-1]["eye"], abs=1e-6)
    assert frames[-1].target == pytest.approx(pts[-1]["target"], abs=1e-6)


def test_spline_passes_near_every_control_point(full):
    eyes = np.array([p.eye for p in full if p.kind == "flyover"])
    step = np.linalg.norm(np.diff(eyes, axis=0), axis=1).max()
    for point in load_recipe(RECIPE_PATH).data["flyover"]["control_points"]:
        assert np.linalg.norm(eyes - np.array(point["eye"]), axis=1).min() <= step


def test_spline_is_continuous_and_constant_speed(full):
    eyes = np.array([p.eye for p in full if p.kind == "flyover"])
    d = np.diff(eyes, axis=0)
    steps = np.linalg.norm(d, axis=1)
    assert steps.min() > 0
    assert steps.max() / steps.min() < 1.08  # arc-length parametrisation: no jump, no stall
    cos = (d[:-1] * d[1:]).sum(axis=1) / (steps[:-1] * steps[1:])
    assert (
        np.degrees(np.arccos(np.clip(cos, -1, 1))).max() < 4.0
    )  # C1: a bounded turn rate, no kink between consecutive frames


def test_view_direction_changes_smoothly(full):
    frames = [p for p in full if p.kind == "flyover"]
    forward = np.array([np.subtract(p.target, p.eye) for p in frames])
    forward /= np.linalg.norm(forward, axis=1)[:, None]
    cos = (forward[:-1] * forward[1:]).sum(axis=1)
    assert np.degrees(np.arccos(np.clip(cos, -1, 1))).max() < 3.0  # no whip between consecutive frames


def test_overrides_and_steps(full):
    by_id = {p.id: p for p in full if p.kind == "still"}
    assert by_id["sunrise-oblique"].sun_elevation_deg == 6.0
    assert by_id["sunrise-oblique"].sun_azimuth_deg == 95.0
    assert by_id["pit-overview-north"].sun_elevation_deg == 55.0
    assert by_id["plan-view"].focal_length_mm == 16.0
    assert by_id["plan-view"].up == (0.0, 1.0, 0.0)
    assert by_id["pit-overview-north"].focal_length_mm == 24.0
    assert full[0].steps == 24 + 16  # warm-up plus the cut settle
    assert full[1].steps == 16
    frames = [p for p in full if p.kind == "flyover"]
    assert frames[0].steps == 16  # a cut after the stills
    assert frames[1].steps == 2


def test_reduced_plan_shape():
    small = plan(load_recipe(RECIPE_PATH).reduced(resolution=(320, 180), stills=2, flyover_frames=3))
    assert [p.kind for p in small] == ["still", "still", "flyover", "flyover", "flyover"]


def test_camera_matrix_looks_at_target():
    eye, target = (10.0, 20.0, 30.0), (110.0, 20.0, 30.0)
    m = camera_matrix(eye, target, (0.0, 0.0, 1.0))
    assert m[:3, 3] == pytest.approx(eye)
    assert -m[:3, 2] == pytest.approx([1.0, 0.0, 0.0])  # USD cameras look down their -Z
    assert m[:3, 1] == pytest.approx([0.0, 0.0, 1.0])  # +Y is up
    assert m[:3, :3].T @ m[:3, :3] == pytest.approx(np.eye(3))
    assert np.linalg.det(m[:3, :3]) == pytest.approx(1.0)


def test_camera_matrix_plan_view_north_up():
    m = camera_matrix((0.0, 0.0, 1000.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert -m[:3, 2] == pytest.approx([0.0, 0.0, -1.0])
    assert m[:3, 1] == pytest.approx([0.0, 1.0, 0.0])
    assert m[:3, 0] == pytest.approx([1.0, 0.0, 0.0])


def test_camera_matrix_rejects_degenerate_view():
    with pytest.raises(ValueError, match="parallel"):
        camera_matrix((0.0, 0.0, 10.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    with pytest.raises(ValueError, match="same point"):
        camera_matrix((1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (0.0, 0.0, 1.0))


@pytest.mark.parametrize(("az", "el"), [(0, 30), (90, 6), (135, 55), (270, 89.9)])
def test_sun_matrix_shines_away_from_the_sun(az, el):
    a, e = math.radians(az), math.radians(el)
    toward_sun = np.array([math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e)])
    m = sun_matrix(az, el)
    assert m[:3, :3] @ np.array([0.0, 0.0, -1.0]) == pytest.approx(-toward_sun, abs=1e-9)
    assert m[:3, :3].T @ m[:3, :3] == pytest.approx(np.eye(3))
