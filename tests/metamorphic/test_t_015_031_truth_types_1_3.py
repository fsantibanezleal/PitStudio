# ruff: noqa: E501, PT018
"""T-015-031: exact ground truth of task-A question types 1 to 3 with the pre-registered ambiguity bands, and the P-015-08
invariances.

Requirements: FR-015-17, FR-015-18, FR-015-19, P-015-08.

Spec: specs/015-vlm/spec.md
- FR-015-17 type 1 "Is a person within 30 m of a haul truck?": yes iff a visible person (>= 100 visible px) is within 30 m
  horizontally of the nearest point of a visible haul truck's oriented footprint (>= 400 visible px); frames with any such
  distance in [27, 33] m, or with a person or truck inside the camera frustum but below its visibility threshold, are not asked.
- FR-015-18 type 2 "Is a berm present along the bench edge in view?": yes iff the berm design-variant flag is on for the bench
  edge in view; asked only when that edge has >= 2,000 visible px.
- FR-015-19 type 3 "How many haul trucks are visible?": the count of haul trucks with >= 400 visible px in {0, 1, 2, >= 3}
  (label "3+" in the contracts); frames with any truck in [100, 400) visible px are not asked.
- P-015-08: (MR1) a common rigid motion of scene and camera leaves every answer unchanged; (MR2) re-authoring the stage in
  centimetres (`metersPerUnit` = 0.01; the transforms of the frame state are already in metres) leaves every answer unchanged;
  (MR3) permuting prims leaves every answer unchanged; moving the person monotonically away flips the type-1 truth at most once.

Oracle: (a) hand-computed distances written out per case (a person at (7.5 + d, 0) is at distance d from a truck centred at the
origin with half length 7.5 and heading 0; boundary values 27.0, 30.0 and 33.0 are exact in binary floating point there);
(b) an independent reference implementation of the three rules, `oracle_type1/2/3` below, written from the spec text (point to
oriented rectangle distance by the body-frame clamp), compared with the code under test on random scenes (Hypothesis).

Expected API of the implementation (package `pitstudio`, root environment, NumPy), `pitstudio.reason.truth`:
- `truth_type1(frame) -> "yes" | "no" | None`, `truth_type2(frame) -> "yes" | "no" | None`,
  `truth_type3(frame) -> "0" | "1" | "2" | "3+" | None`; `frame` is a validated frame-state document (dict); None means "not
  asked" (ambiguity band or unaskable frame).
- Footprint convention (the contract does not state it; reported as an ambiguity): `footprint.centre_m` is the horizontal
  position (x, y for Z up; x, z for Y up), `heading_deg` is counter-clockwise from the first horizontal axis towards the second,
  `half_extents_m` = (half length along the heading, half width across it). `metersPerUnit` is NOT applied again: transforms
  are already in metres.
"""

from __future__ import annotations

import math
import sys
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pitstudio.reason.truth import truth_type1, truth_type2, truth_type3

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the shared kit lives in tests/unit
import _p015_kit as kit

TRUCK_HALF = (7.5, 4.6)


# ------------------------------------------------------------------------------------------------ reference implementation
def rect_distance(frame_obj: dict, point: tuple[float, float]) -> float:
    """Distance from a horizontal point to the nearest point of an object's oriented rectangle (body-frame clamp)."""
    fp = frame_obj["footprint"]
    h = math.radians(fp["heading_deg"])
    dx, dy = point[0] - fp["centre_m"][0], point[1] - fp["centre_m"][1]
    bx = math.cos(h) * dx + math.sin(h) * dy
    by = -math.sin(h) * dx + math.cos(h) * dy
    ex = max(abs(bx) - fp["half_extents_m"][0], 0.0)
    ey = max(abs(by) - fp["half_extents_m"][1], 0.0)
    return math.hypot(ex, ey)


def oracle_type1(frame: dict) -> str | None:
    persons = [o for o in frame["objects"] if o["class"] == "person"]
    trucks = [o for o in frame["objects"] if o["class"] == "haul_truck"]
    if any(p["in_frustum"] and p["visible_px"] < 100 for p in persons):
        return None
    if any(t["in_frustum"] and t["visible_px"] < 400 for t in trucks):
        return None
    vp = [p for p in persons if p["visible_px"] >= 100]
    vt = [t for t in trucks if t["visible_px"] >= 400]
    dists = [rect_distance(t, tuple(p["footprint"]["centre_m"])) for p in vp for t in vt]
    if any(27.0 <= d <= 33.0 for d in dists):
        return None
    return "yes" if any(d < 27.0 for d in dists) else "no"


def oracle_type2(frame: dict) -> str | None:
    seen = [e for e in frame["bench_edges"] if e["visible_px"] >= 2000]
    assert len(seen) <= 1, "the strategies build at most one edge in view"
    return None if not seen else ("yes" if seen[0]["berm_present"] else "no")


def oracle_type3(frame: dict) -> str | None:
    px = [o["visible_px"] for o in frame["objects"] if o["class"] == "haul_truck"]
    if any(100 <= v < 400 for v in px):
        return None
    n = sum(1 for v in px if v >= 400)
    return ["0", "1", "2", "3+"][min(n, 3)]


# ------------------------------------------------------------------------------------------------ hand cases: type 1
def _t1(person_xy: tuple[float, float], **truck_kw) -> str | None:
    return truth_type1(kit.frame_state([kit.truck(0.0, 0.0, **truck_kw), kit.person(*person_xy)]))


@pytest.mark.req("FR-015-17")
@pytest.mark.parametrize(
    ("d", "expected"),
    [(0.0, "yes"), (10.0, "yes"), (26.9, "yes"), (27.0, None), (30.0, None), (33.0, None), (33.1, "no"), (80.0, "no")],
)
def test_type_1_distance_bands_ahead_of_the_truck(d: float, expected: str | None) -> None:
    # person on the truck axis, d metres beyond the front face (half length 7.5): the nearest point of the footprint is at d
    assert _t1((TRUCK_HALF[0] + d, 0.0)) == expected


@pytest.mark.req("FR-015-17")
@pytest.mark.parametrize(
    ("xy", "expected"),
    [
        ((7.5 + 15.0, 4.6 + 20.0), "yes"),  # corner: hypot(15, 20) = 25 m
        ((7.5 + 24.0, 4.6 + 18.0), None),  # hypot(24, 18) = 30 m, inside the band
        ((7.5 + 24.0, 4.6 + 32.0), "no"),  # hypot(24, 32) = 40 m
        ((0.0, 4.6 + 26.9), "yes"),  # beside the truck
        ((0.0, -(4.6 + 33.2)), "no"),
        ((-(7.5 + 20.0), 0.0), "yes"),  # behind
        ((3.0, 1.0), "yes"),  # inside the footprint: distance 0
    ],
)
def test_type_1_uses_the_nearest_point_of_the_oriented_footprint_not_its_centre(
    xy: tuple[float, float], expected: str | None
) -> None:
    assert _t1(xy) == expected


@pytest.mark.req("FR-015-17")
@pytest.mark.parametrize("heading", [30.0, 90.0, -135.0, 180.0])
def test_type_1_follows_the_truck_heading(heading: float) -> None:
    for d, expected in [(26.95, "yes"), (27.05, None), (32.95, None), (33.05, "no")]:
        p = kit.body_to_world((0.0, 0.0), heading, (TRUCK_HALF[0] + d, 0.0))
        assert _t1(tuple(p), heading_deg=heading) == expected, (heading, d)


@pytest.mark.req("FR-015-17")
def test_type_1_visibility_thresholds_are_100_px_for_a_person_and_400_px_for_a_truck() -> None:
    near = (20.0, 0.0)  # 12.5 m from the footprint

    def f(pp: int, tp: int) -> str | None:
        return truth_type1(kit.frame_state([kit.truck(0.0, 0.0, visible_px=tp), kit.person(*near, visible_px=pp)]))

    assert f(100, 400) == "yes"
    assert f(99, 400) is None  # person in the frustum but below 100 px: not asked
    assert f(100, 399) is None  # truck in the frustum but below 400 px: not asked
    assert f(5000, 18000) == "yes"


@pytest.mark.req("FR-015-17")
def test_type_1_an_occluded_object_inside_the_frustum_is_not_asked_but_one_outside_is_ignored() -> None:
    near = (20.0, 0.0)
    inside = kit.person(*near, visible_px=0, in_frustum=True)
    outside = kit.person(*near, visible_px=0, in_frustum=False)
    assert truth_type1(kit.frame_state([kit.truck(0.0, 0.0), inside])) is None
    assert truth_type1(kit.frame_state([kit.truck(0.0, 0.0), outside])) == "no"  # no visible person, so no hazard


@pytest.mark.req("FR-015-17")
def test_type_1_without_a_visible_person_or_without_a_visible_truck_is_no() -> None:
    assert truth_type1(kit.frame_state([kit.truck(0.0, 0.0)])) == "no"
    assert truth_type1(kit.frame_state([kit.person(1.0, 1.0)])) == "no"
    assert truth_type1(kit.frame_state([kit.obj("boulder", 0.0, 0.0, visible_px=900)])) == "no"


@pytest.mark.req("FR-015-17")
def test_type_1_any_pair_in_the_band_makes_the_frame_unaskable_even_if_another_pair_is_close() -> None:
    f = kit.frame_state([kit.truck(0.0, 0.0), kit.person(15.0, 0.0), kit.person(7.5 + 30.0, 0.0)])
    assert truth_type1(f) is None


@pytest.mark.req("FR-015-17")
def test_type_1_with_two_trucks_the_nearest_truck_decides() -> None:
    f = kit.frame_state([kit.truck(0.0, 0.0), kit.truck(200.0, 0.0), kit.person(200.0 - 7.5 - 12.0, 0.0)])
    assert truth_type1(f) == "yes"
    g = kit.frame_state([kit.truck(0.0, 0.0), kit.truck(200.0, 0.0), kit.person(100.0, 0.0)])
    assert truth_type1(g) == "no"  # 92.5 m from both


# ------------------------------------------------------------------------------------------------ hand cases: type 2 and 3
@pytest.mark.req("FR-015-18")
@pytest.mark.parametrize(
    ("edges", "expected"),
    [
        ([kit.bench_edge(berm=True, visible_px=5120)], "yes"),
        ([kit.bench_edge(berm=False, visible_px=5120)], "no"),
        ([kit.bench_edge(berm=True, visible_px=2000)], "yes"),  # exactly the threshold
        ([kit.bench_edge(berm=True, visible_px=1999)], None),
        ([kit.bench_edge(berm=False, visible_px=0)], None),
        ([], None),
        (
            [
                kit.bench_edge("bench-07-crest", berm=False, visible_px=3000),
                kit.bench_edge("bench-08-toe", berm=True, visible_px=500),
            ],
            "no",
        ),
    ],
)
def test_type_2_follows_the_berm_flag_of_the_edge_in_view_and_the_2000_px_threshold(
    edges: list[dict], expected: str | None
) -> None:
    assert truth_type2(kit.frame_state([kit.truck(0.0, 0.0)], bench_edges=edges)) == expected


@pytest.mark.req("FR-015-19")
@pytest.mark.parametrize(
    ("pxs", "expected"),
    [
        ([], "0"),
        ([18000], "1"),
        ([400], "1"),  # exactly the threshold counts
        ([400, 401], "2"),
        ([500, 600, 700], "3+"),
        ([500] * 5, "3+"),
        ([399], None),
        ([100], None),
        ([250, 18000], None),
        ([18000, 18000, 399], None),
    ],
)
def test_type_3_counts_trucks_from_400_px_and_excludes_frames_with_a_truck_in_100_to_399_px(
    pxs: list[int], expected: str | None
) -> None:
    objs = [kit.truck(30.0 * i, 0.0, visible_px=v) for i, v in enumerate(pxs)]
    assert truth_type3(kit.frame_state([*objs, kit.person(5.0, 5.0)])) == expected


@pytest.mark.req("FR-015-19")
def test_type_3_counts_only_haul_trucks() -> None:
    objs = [
        kit.light_vehicle(10.0, 0.0, visible_px=9000),
        kit.obj("shovel", 40.0, 0.0, visible_px=9000, half=(6.0, 3.0)),
        kit.obj("boulder", 60.0, 0.0, visible_px=9000),
        kit.person(70.0, 0.0, visible_px=9000),
        kit.truck(90.0, 0.0),
    ]
    assert truth_type3(kit.frame_state(objs)) == "1"


# ------------------------------------------------------------------------------------------------ property tests
_PX_T = st.sampled_from([0, 50, 99, 100, 399, 400, 401, 5000, 18432])
_PX_P = st.sampled_from([0, 40, 99, 100, 101, 640])
_XY = st.tuples(st.floats(-90, 90), st.floats(-90, 90))


@st.composite
def scenes(draw, *, with_edge: bool = False) -> dict:
    objs = []
    for _ in range(draw(st.integers(0, 3))):
        px = draw(_PX_T)
        objs.append(
            kit.truck(
                *draw(_XY),
                visible_px=px,
                heading_deg=draw(st.floats(-180, 180)),
                in_frustum=px > 0 or draw(st.booleans()),
            )
        )
    for _ in range(draw(st.integers(0, 3))):
        px = draw(_PX_P)
        objs.append(kit.person(*draw(_XY), visible_px=px, in_frustum=px > 0 or draw(st.booleans())))
    objs.extend(kit.light_vehicle(*draw(_XY)) for _ in range(draw(st.integers(0, 2))))
    edges = []
    if with_edge and draw(st.booleans()):
        edges = [kit.bench_edge(berm=draw(st.booleans()), visible_px=draw(st.sampled_from([0, 1999, 2000, 6000])))]
    return kit.frame_state(objs, bench_edges=edges, condition=draw(st.sampled_from(["day", "night", "dust", "rain"])))


def _band_margin_ok(frame: dict) -> bool:
    """True when no person-truck distance is within 1e-6 m of a band edge (rounding of a rigid motion could flip it)."""
    vp = [o for o in frame["objects"] if o["class"] == "person"]
    vt = [o for o in frame["objects"] if o["class"] == "haul_truck"]
    for p in vp:
        for t in vt:
            d = rect_distance(t, tuple(p["footprint"]["centre_m"]))
            if abs(d - 27.0) < 1e-6 or abs(d - 33.0) < 1e-6:
                return False
    return True


@pytest.mark.req("FR-015-17")
@pytest.mark.req("FR-015-19")
@pytest.mark.req("FR-015-18")
@settings(max_examples=300, deadline=None)
@given(scenes(with_edge=True))
def test_property_the_truth_equals_the_reference_implementation_on_random_scenes(frame: dict) -> None:
    assume(_band_margin_ok(frame))
    assert truth_type1(frame) == oracle_type1(frame)
    assert truth_type2(frame) == oracle_type2(frame)
    assert truth_type3(frame) == oracle_type3(frame)


@pytest.mark.req("P-015-08")
@settings(max_examples=200, deadline=None)
@given(scenes(with_edge=True), st.floats(-180, 180), st.floats(-500, 500), st.floats(-500, 500))
def test_mr1_a_common_rigid_motion_of_scene_and_camera_leaves_every_answer_unchanged(
    frame: dict, theta: float, dx: float, dy: float
) -> None:
    assume(_band_margin_ok(frame))
    moved = kit.move_frame(frame, theta, dx, dy)
    assert truth_type1(moved) == truth_type1(frame)
    assert truth_type2(moved) == truth_type2(frame)
    assert truth_type3(moved) == truth_type3(frame)


@pytest.mark.req("P-015-08")
@settings(max_examples=200, deadline=None)
@given(scenes(with_edge=True), st.sampled_from([0.01, 0.0254, 0.3048, 1.0, 100.0]))
def test_mr2_the_stage_unit_does_not_change_an_answer_because_transforms_are_already_in_metres(
    frame: dict, mpu: float
) -> None:
    other = {**frame, "metersPerUnit": mpu}
    assert truth_type1(other) == truth_type1(frame)
    assert truth_type2(other) == truth_type2(frame)
    assert truth_type3(other) == truth_type3(frame)


@pytest.mark.req("P-015-08")
@settings(max_examples=200, deadline=None)
@given(scenes(with_edge=True), st.randoms(use_true_random=False))
def test_mr3_permuting_the_prims_leaves_every_answer_unchanged(frame: dict, rnd) -> None:
    objs = list(frame["objects"])
    rnd.shuffle(objs)
    edges = list(frame["bench_edges"])
    rnd.shuffle(edges)
    perm = {**frame, "objects": objs, "bench_edges": edges}
    assert truth_type1(perm) == truth_type1(frame)
    assert truth_type2(perm) == truth_type2(frame)
    assert truth_type3(perm) == truth_type3(frame)


@pytest.mark.req("P-015-08")
@settings(max_examples=100, deadline=None)
@given(st.floats(-180, 180), st.floats(-180, 180))
def test_moving_the_person_monotonically_away_flips_the_type_1_truth_at_most_once(
    truck_heading: float, bearing: float
) -> None:
    answers = []
    for i in range(1, 260):
        d = i * 0.35  # 0.35 .. 90.65 m from the truck centre along `bearing`
        p = (d * math.cos(math.radians(bearing)), d * math.sin(math.radians(bearing)))
        a = truth_type1(kit.frame_state([kit.truck(0.0, 0.0, heading_deg=truck_heading), kit.person(*p)]))
        if a is not None:
            answers.append(a)
    assert answers[0] == "yes" and answers[-1] == "no"  # the sweep starts inside the footprint and ends 80+ m away
    flips = sum(1 for a, b in pairwise(answers) if a != b)
    assert flips == 1
