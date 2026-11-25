# ruff: noqa: E501
"""T-015-032: exact ground truth of task-A question types 4 to 6 with the pre-registered ambiguity bands, and the P-015-08
invariances.

Requirements: FR-015-20, FR-015-21, FR-015-22, P-015-08.

Spec: specs/015-vlm/spec.md
- FR-015-20 type 4 "Is visibility reduced by dust?": yes if the median one-way optical depth tau along a 16 x 9 grid of camera
  rays (to their ground-truth distance, or to the dust-field box exit for sky rays) is >= 0.3216 (T1 <= 0.725), no if it is
  <= 0.1054 (T1 >= 0.90); frames in between are not asked.
- FR-015-21 type 5 "Is a light vehicle in the truck's blind zone?": yes iff a light vehicle's footprint centre lies inside the
  blind-zone polygon of the truck asset (truck body frame); asked only for frames with exactly one visible haul truck, whose
  light vehicles within 50 m are all visible (>= 100 px), and not when a centre lies within 1 m of the polygon boundary.
- FR-015-22 type 6 "Is the truck on a ramp steeper than 10 %?": yes iff the road grade under the footprint centre of the single
  visible haul truck, from the terrain along its heading over +-5 m, exceeds 10 %; frames with a grade in [9 %, 11 %] are not asked.
- P-015-08: rigid motion of scene and camera, re-authoring in centimetres (`metersPerUnit` = 0.01), prim permutation leave every
  answer unchanged.

Oracle: (a) hand calculation: tau = sigma * L for a uniform extinction sigma (1/m) over a path of length L, with L the known
range (100 m) or the slab-method exit distance of a box (computed in the test); thresholds -ln(0.725) = 0.3216 and
-ln(0.90) = 0.1054 (Beer-Lambert, T1 = exp(-tau)); the grade of a plane z = gx*x + gy*y along heading phi is
|gx cos(phi) + gy sin(phi)| (directional derivative); (b) a reference implementation of the type-5 rule (ray-casting point in
polygon, point to segment distance) written in the test and compared on random scenes.

Expected API of the implementation (package `pitstudio`, root environment, NumPy), `pitstudio.reason.truth`:
- `truth_type4(frame, *, depth_m, dust) -> "yes" | "no" | None`. `depth_m`: float array (height_px, width_px), the distance in
  metres along each pixel's ray from the camera to the surface (`inf` for sky); `dust`: dict with `origin_m` (3 floats, the
  lower corner of the dust-field box), `spacing_m` (float, cubic cells) and `sigma_per_m` (3-D array, extinction coefficient in
  1/m per cell). The 16 x 9 grid is the 144 pixel-centre rays of a uniform 16-column by 9-row partition of the image. The
  depth semantics (ray distance, not z-depth) and the file formats are not fixed by the contract (reported as an ambiguity).
- `truth_type5(frame, *, blind_zones) -> "yes" | "no" | None`; `blind_zones` maps `asset_id` to the polygon vertices
  `[(x, y), ...]` in the truck body frame (x forward along the heading, y left), metres.
- `truth_type6(frame, *, terrain) -> "yes" | "no" | None`; `terrain(x, y) -> z` returns the terrain height in metres at a
  horizontal point (Z-up world, x and y world metres).
- Camera convention: the OpenGL / USD one of the valid example (see `_p015_kit.camera`). Footprint and heading conventions as in
  test_t_015_031_truth_types_1_3.py; a "visible" truck has >= 400 visible px (as in FR-015-17 and FR-015-19).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pitstudio.reason.truth import truth_type4, truth_type5, truth_type6

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the shared kit lives in tests/unit
import _p015_kit as kit

W, H = 1280, 720
TAU_YES = -math.log(0.725)  # 0.3216: onset of visibility reduction (spec 013)
TAU_NO = -math.log(0.90)  # 0.1054

# ------------------------------------------------------------------------------------------------ type 4 fixtures
CAM_POS = (0.0, 0.0, 10.0)
BOX_MIN = np.array([-10.0, -100.0, -100.0])
BOX_MAX = np.array([200.0, 100.0, 100.0])


def dust_field(sigma: float, origin: tuple[float, float, float] = tuple(BOX_MIN)) -> dict:
    """A uniform dust box of 21 x 20 x 20 cells of 10 m, i.e. [origin, origin + (210, 200, 200)], extinction `sigma` 1/m."""
    return {"origin_m": list(origin), "spacing_m": 10.0, "sigma_per_m": np.full((21, 20, 20), sigma)}


def _frame4(cam_pos=CAM_POS) -> dict:
    return kit.frame_state(
        [kit.truck(100.0, 0.0)], condition="dust", dust=True, cam=kit.camera(cam_pos, 0.0, 0.0), width=W, height=H
    )


def _grid_dirs(frame: dict) -> np.ndarray:
    """World unit directions of the 16 x 9 pixel-centre rays (independent of the code under test; OpenGL camera)."""
    k = frame["camera"]["intrinsics"]
    r = kit.quat_to_matrix(frame["camera"]["pose"]["rotation_xyzw"])
    out = []
    for j in range(9):
        for i in range(16):
            u, v = (i + 0.5) * W / 16, (j + 0.5) * H / 9
            d_cam = np.array([(u - k["cx_px"]) / k["fx_px"], -(v - k["cy_px"]) / k["fy_px"], -1.0])
            d = r @ d_cam
            out.append(d / np.linalg.norm(d))
    return np.array(out)


def _box_exit(origin: np.ndarray, d: np.ndarray, lo: np.ndarray = BOX_MIN, hi: np.ndarray = BOX_MAX) -> float:
    """Slab method: distance along unit direction d from a point inside the box to where the ray leaves it."""
    t = np.inf
    for a in range(3):
        if d[a] > 0:
            t = min(t, (hi[a] - origin[a]) / d[a])
        elif d[a] < 0:
            t = min(t, (lo[a] - origin[a]) / d[a])
    return float(t)


def _depth_const(range_m: float) -> np.ndarray:
    return np.full((H, W), range_m, dtype=np.float32)


@pytest.mark.req("FR-015-20")
@pytest.mark.parametrize(
    ("sigma", "range_m", "expected"),
    [
        (0.0045, 100.0, "yes"),  # tau = 0.45 >= 0.3216
        (0.0005, 100.0, "no"),  # tau = 0.05 <= 0.1054
        (0.0020, 100.0, None),  # tau = 0.20 lies between 0.1054 and 0.3216
        (0.0, 100.0, "no"),  # clear air
        (0.0045, 20.0, "no"),  # tau = 0.09: the same dust over a short range is not a visibility reduction
    ],
)
def test_type_4_uses_the_one_way_optical_depth_to_the_ground_truth_distance(
    sigma: float, range_m: float, expected: str | None
) -> None:
    assert truth_type4(_frame4(), depth_m=_depth_const(range_m), dust=dust_field(sigma)) == expected


@pytest.mark.req("FR-015-20")
@pytest.mark.parametrize(("sigma", "expected"), [(0.0030, "yes"), (0.0003, "no"), (0.0010, None)])
def test_type_4_sky_rays_integrate_to_the_dust_box_exit(sigma: float, expected: str | None) -> None:
    frame = _frame4()
    exits = [_box_exit(np.array(CAM_POS), d) for d in _grid_dirs(frame)]
    median_tau = sigma * float(np.median(exits))
    # hand calculation: the box is about 210 m deep ahead of the camera, so tau is about 0.2 * (sigma / 0.001)
    assert (median_tau >= TAU_YES) == (expected == "yes")
    assert (median_tau <= TAU_NO) == (expected == "no")
    sky = np.full((H, W), np.inf, dtype=np.float32)
    assert truth_type4(frame, depth_m=sky, dust=dust_field(sigma)) == expected


@pytest.mark.req("FR-015-20")
def test_type_4_takes_the_median_over_the_grid_not_the_mean() -> None:
    """10 of the 16 columns hit a surface at 100 m (tau = 0.08), 6 columns see the sky (tau about 0.18): the median
    (0.08 <= 0.1054) answers no; a mean (about 0.113) would leave the band and answer None."""
    frame = _frame4()
    sigma = 0.0008
    depth = _depth_const(100.0)
    depth[:, 10 * W // 16 :] = np.inf  # columns 10..15 are sky
    dirs = _grid_dirs(frame)
    taus = []
    for idx, d in enumerate(dirs):
        col = idx % 16
        taus.append(sigma * (100.0 if col < 10 else _box_exit(np.array(CAM_POS), d)))
    assert float(np.median(taus)) <= TAU_NO < float(np.mean(taus))  # the fixture separates the two statistics
    assert truth_type4(frame, depth_m=depth, dust=dust_field(sigma)) == "no"


@pytest.mark.req("FR-015-20")
@pytest.mark.parametrize(("sigma", "range_m"), [(0.0045, 100.0), (0.0005, 100.0), (0.002, 100.0)])
def test_type_4_is_invariant_to_the_stage_unit_a_translation_and_prim_order(sigma: float, range_m: float) -> None:
    base = truth_type4(_frame4(), depth_m=_depth_const(range_m), dust=dust_field(sigma))
    f = _frame4()
    f["metersPerUnit"] = 0.01
    f["objects"] = [*reversed(f["objects"]), kit.person(5.0, 5.0)]
    assert truth_type4(f, depth_m=_depth_const(range_m), dust=dust_field(sigma)) == base
    shifted = _frame4((250.0, -40.0, 10.0))  # the dust box moves with the camera
    origin = tuple(float(v) for v in BOX_MIN + np.array([250.0, -40.0, 0.0]))
    assert truth_type4(shifted, depth_m=_depth_const(range_m), dust=dust_field(sigma, origin)) == base


# ------------------------------------------------------------------------------------------------ type 5
POLY = [(6.0, -3.0), (14.0, -3.0), (14.0, 3.0), (6.0, 3.0)]  # a blind zone ahead of the cab, truck body frame
ZONES = {"haul-truck-asset": POLY}


def _seg_dist(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def poly_boundary_distance(p: tuple[float, float], poly: list[tuple[float, float]] = POLY) -> float:
    return min(_seg_dist(p, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def inside(p: tuple[float, float], poly: list[tuple[float, float]] = POLY) -> bool:
    """Ray casting (even-odd rule)."""
    x, y = p
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _lv_at(truck_c: tuple[float, float], heading: float, body: tuple[float, float], **kw) -> dict:
    return kit.light_vehicle(*kit.body_to_world(truck_c, heading, body), **kw)


def _t5(body_positions: list[tuple[float, float]], *, heading: float = 37.0, extra=(), lv_px: int = 900) -> str | None:
    c = (100.0, 50.0)
    objs = [
        kit.truck(*c, heading_deg=heading),
        *[_lv_at(c, heading, b, visible_px=lv_px) for b in body_positions],
        *extra,
    ]
    return truth_type5(kit.frame_state(objs), blind_zones=ZONES)


@pytest.mark.req("FR-015-21")
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ((10.0, 0.0), "yes"),  # polygon centre
        ((12.0, 0.0), "yes"),  # 2 m inside the front edge x = 14
        ((10.0, 5.0), "no"),  # 2 m outside the side edge y = 3
        ((-10.0, 0.0), "no"),  # behind the truck
        ((20.0, 0.0), "no"),  # 6 m beyond the front edge
        ((14.5, 0.0), None),  # 0.5 m outside the boundary: within 1 m
        ((13.5, 0.0), None),  # 0.5 m inside the boundary: within 1 m
        ((10.0, 3.8), None),  # 0.8 m outside the side edge
        ((10.0, 2.2), None),  # 0.8 m inside the side edge
        ((15.5, 0.0), "no"),  # 1.5 m outside: decided
    ],
)
def test_type_5_blind_zone_polygon_in_the_truck_body_frame_and_the_one_metre_exclusion(
    body: tuple[float, float], expected: str | None
) -> None:
    assert _t5([body]) == expected


@pytest.mark.req("FR-015-21")
@pytest.mark.parametrize("heading", [0.0, 90.0, -90.0, 180.0, 37.0, -123.0])
def test_type_5_the_polygon_turns_with_the_truck_heading(heading: float) -> None:
    assert _t5([(10.0, 0.0)], heading=heading) == "yes"
    assert _t5([(10.0, 5.0)], heading=heading) == "no"


@pytest.mark.req("FR-015-21")
def test_type_5_without_a_light_vehicle_the_answer_is_no() -> None:
    assert _t5([]) == "no"


@pytest.mark.req("FR-015-21")
def test_type_5_any_light_vehicle_in_the_zone_makes_it_yes_but_any_near_the_boundary_makes_it_unaskable() -> None:
    assert _t5([(10.0, 0.0), (-10.0, 0.0)]) == "yes"
    assert _t5([(10.0, 0.0), (14.5, 0.0)]) is None


@pytest.mark.req("FR-015-21")
def test_type_5_needs_exactly_one_visible_haul_truck() -> None:
    c = (100.0, 50.0)
    lv = _lv_at(c, 0.0, (10.0, 0.0))
    one = kit.frame_state([kit.truck(*c), lv])
    two = kit.frame_state([kit.truck(*c), kit.truck(300.0, 50.0), lv])
    none = kit.frame_state([lv])
    assert truth_type5(one, blind_zones=ZONES) == "yes"
    assert truth_type5(two, blind_zones=ZONES) is None
    assert truth_type5(none, blind_zones=ZONES) is None


@pytest.mark.req("FR-015-21")
def test_type_5_light_vehicles_within_50_m_must_all_be_visible_from_100_px() -> None:
    c = (100.0, 50.0)
    far_hidden = _lv_at(c, 0.0, (-40.0, 0.0), visible_px=99)  # 40 m behind the truck: inside the 50 m radius
    beyond_hidden = _lv_at(c, 0.0, (-65.0, 0.0), visible_px=0)  # 65 m away: ignored
    base = [kit.truck(*c), _lv_at(c, 0.0, (10.0, 0.0))]
    assert truth_type5(kit.frame_state([*base, far_hidden]), blind_zones=ZONES) is None
    assert truth_type5(kit.frame_state([*base, beyond_hidden]), blind_zones=ZONES) == "yes"
    shown = _lv_at(c, 0.0, (-40.0, 0.0), visible_px=100)
    assert truth_type5(kit.frame_state([*base, shown]), blind_zones=ZONES) == "yes"


@st.composite
def scenes5(draw) -> tuple[dict, float, tuple[float, float]]:
    heading = draw(st.floats(-180, 180))
    c = (draw(st.floats(-50, 50)), draw(st.floats(-50, 50)))
    objs = [kit.truck(*c, heading_deg=heading)]
    for _ in range(draw(st.integers(0, 3))):
        body = (draw(st.floats(-25, 25)), draw(st.floats(-25, 25)))
        px = draw(st.sampled_from([0, 50, 99, 100, 900]))
        objs.append(_lv_at(c, heading, body, visible_px=px, in_frustum=px > 0))
    if draw(st.booleans()):
        objs.append(kit.truck(c[0] + 300.0, c[1], visible_px=draw(st.sampled_from([0, 400, 5000]))))
    return kit.frame_state(objs), heading, c


def oracle_type5(frame: dict, heading: float, c: tuple[float, float]) -> str | None:
    trucks = [o for o in frame["objects"] if o["class"] == "haul_truck" and o["visible_px"] >= 400]
    if len(trucks) != 1:
        return None
    t = trucks[0]
    tc = t["footprint"]["centre_m"]
    h = math.radians(t["footprint"]["heading_deg"])
    near = []
    for o in frame["objects"]:
        if o["class"] != "light_vehicle":
            continue
        oc = o["footprint"]["centre_m"]
        if math.hypot(oc[0] - tc[0], oc[1] - tc[1]) <= 50.0:
            near.append(o)
    if any(o["visible_px"] < 100 for o in near):
        return None
    pts = []
    for o in near:
        dx, dy = o["footprint"]["centre_m"][0] - tc[0], o["footprint"]["centre_m"][1] - tc[1]
        pts.append((math.cos(h) * dx + math.sin(h) * dy, -math.sin(h) * dx + math.cos(h) * dy))
    if any(poly_boundary_distance(p) < 1.0 for p in pts):
        return None
    return "yes" if any(inside(p) for p in pts) else "no"


def _margin5(frame: dict) -> bool:
    for o in frame["objects"]:
        if o["class"] == "light_vehicle":
            tc = frame["objects"][0]["footprint"]["centre_m"]
            h = math.radians(frame["objects"][0]["footprint"]["heading_deg"])
            dx, dy = o["footprint"]["centre_m"][0] - tc[0], o["footprint"]["centre_m"][1] - tc[1]
            p = (math.cos(h) * dx + math.sin(h) * dy, -math.sin(h) * dx + math.cos(h) * dy)
            if abs(poly_boundary_distance(p) - 1.0) < 1e-6:
                return False
    return True


@pytest.mark.req("FR-015-21")
@settings(max_examples=300, deadline=None)
@given(scenes5())
def test_property_type_5_truth_equals_the_reference_implementation(scene: tuple) -> None:
    frame, heading, c = scene
    assume(_margin5(frame))
    assert truth_type5(frame, blind_zones=ZONES) == oracle_type5(frame, heading, c)


@pytest.mark.req("P-015-08")
@settings(max_examples=200, deadline=None)
@given(
    scenes5(),
    st.floats(-180, 180),
    st.floats(-500, 500),
    st.floats(-500, 500),
    st.sampled_from([0.01, 0.0254, 1.0]),
    st.randoms(use_true_random=False),
)
def test_type_5_is_invariant_to_rigid_motion_the_stage_unit_and_prim_order(scene, theta, dx, dy, mpu, rnd) -> None:
    frame, _, _ = scene
    assume(_margin5(frame))
    base = truth_type5(frame, blind_zones=ZONES)
    assert truth_type5(kit.move_frame(frame, theta, dx, dy), blind_zones=ZONES) == base
    other = {**frame, "metersPerUnit": mpu, "objects": list(frame["objects"])}
    rnd.shuffle(other["objects"])
    assert truth_type5(other, blind_zones=ZONES) == base


# ------------------------------------------------------------------------------------------------ type 6
def plane(gx: float, gy: float, z0: float = 800.0):
    return lambda x, y: z0 + gx * x + gy * y


def _t6(grade_terrain, heading: float = 0.0, *, trucks=None) -> str | None:
    objs = trucks if trucks is not None else [kit.truck(40.0, -25.0, heading_deg=heading)]
    return truth_type6(kit.frame_state(objs), terrain=grade_terrain)


@pytest.mark.req("FR-015-22")
@pytest.mark.parametrize(
    ("grade", "expected"),
    [
        (0.0, "no"),
        (0.05, "no"),
        (0.0899, "no"),
        (0.0901, None),
        (0.095, None),
        (0.10, None),
        (0.105, None),
        (0.1099, None),
        (0.1101, "yes"),
        (0.20, "yes"),
        (0.45, "yes"),
    ],
)
def test_type_6_grade_bands_along_the_heading(grade: float, expected: str | None) -> None:
    assert _t6(plane(grade, 0.0), heading=0.0) == expected
    assert _t6(plane(-grade, 0.0), heading=0.0) == expected  # downhill is as steep as uphill


@pytest.mark.req("FR-015-22")
@pytest.mark.parametrize(
    ("heading", "expected"),
    [(0.0, "yes"), (90.0, "yes"), (45.0, "yes"), (-45.0, "no"), (135.0, "no"), (180.0, "yes")],
)
def test_type_6_uses_the_slope_along_the_heading_not_the_steepest_slope(heading: float, expected: str) -> None:
    # gradient (0.12, 0.12): the slope along phi is 0.12 (cos phi + sin phi); 0 at -45 and 135 degrees, 0.1697 at 45 degrees
    assert _t6(plane(0.12, 0.12), heading=heading) == expected


@pytest.mark.req("FR-015-22")
def test_type_6_a_slope_across_the_heading_is_not_a_grade() -> None:
    assert _t6(plane(0.0, 0.30), heading=0.0) == "no"  # steep across, flat along
    assert _t6(plane(0.0, 0.30), heading=90.0) == "yes"


@pytest.mark.req("FR-015-22")
def test_type_6_needs_exactly_one_visible_haul_truck() -> None:
    steep = plane(0.2, 0.0)
    assert _t6(steep, trucks=[kit.truck(40.0, -25.0)]) == "yes"
    assert _t6(steep, trucks=[kit.truck(40.0, -25.0), kit.truck(90.0, -25.0)]) is None
    assert _t6(steep, trucks=[kit.person(40.0, -25.0)]) is None


@pytest.mark.req("FR-015-22")
@settings(max_examples=300, deadline=None)
@given(st.floats(-0.4, 0.4), st.floats(-0.4, 0.4), st.floats(-180, 180), st.floats(-80, 80), st.floats(-80, 80))
def test_property_type_6_grade_is_the_directional_derivative_of_a_plane(
    gx: float, gy: float, heading: float, cx: float, cy: float
) -> None:
    g = abs(gx * math.cos(math.radians(heading)) + gy * math.sin(math.radians(heading)))
    assume(abs(g - 0.09) > 1e-6 and abs(g - 0.11) > 1e-6)
    expected = "no" if g < 0.09 else ("yes" if g > 0.11 else None)
    assert _t6(plane(gx, gy), trucks=[kit.truck(cx, cy, heading_deg=heading)]) == expected


@pytest.mark.req("P-015-08")
@settings(max_examples=200, deadline=None)
@given(
    st.floats(-0.4, 0.4), st.floats(-0.4, 0.4), st.floats(-180, 180), st.floats(-80, 80), st.floats(-80, 80),
    st.floats(-180, 180), st.floats(-500, 500), st.floats(-500, 500), st.sampled_from([0.01, 1.0]),
)  # fmt: skip
def test_type_6_is_invariant_to_rigid_motion_of_scene_and_terrain_and_to_the_stage_unit(
    gx, gy, heading, cx, cy, theta, dx, dy, mpu
) -> None:
    g = abs(gx * math.cos(math.radians(heading)) + gy * math.sin(math.radians(heading)))
    assume(abs(g - 0.09) > 1e-6 and abs(g - 0.11) > 1e-6)
    frame = kit.frame_state([kit.truck(cx, cy, heading_deg=heading)])
    base = truth_type6(frame, terrain=plane(gx, gy))
    th = math.radians(theta)
    c, s = math.cos(th), math.sin(th)

    def moved_terrain(x: float, y: float) -> float:  # the same ground, seen after the rigid motion (R, t)
        xo = c * (x - dx) + s * (y - dy)
        yo = -s * (x - dx) + c * (y - dy)
        return plane(gx, gy)(xo, yo)

    moved = {**kit.move_frame(frame, theta, dx, dy), "metersPerUnit": mpu}
    assert truth_type6(moved, terrain=moved_terrain) == base
