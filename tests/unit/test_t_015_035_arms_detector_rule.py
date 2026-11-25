# ruff: noqa: E501
"""T-015-035: the arm plan of task A, the detector + geometric rule, hostile query sets and detector inputs.

Requirements: FR-015-28, FR-015-29, FR-015-47, P-015-09.

Spec: specs/015-vlm/spec.md
- FR-015-28: task A runs these arms on the same queries: Cosmos Q8_0 (reasoning off; reasoning on for the 300-query subset),
  Cosmos BF16 (the 500-query gate subset), Qwen3-VL-2B-Instruct, the detector + geometric rule (types 1, 3 and 5; "not applicable"
  for 2, 4 and 6) and a constant arm ("no" for binary types, "1" for type 3).
- FR-015-29: the rule uses the detections with score >= 0.5, the known camera calibration and the terrain model: type 1 by
  ground-plane back-projection of box bottom-centres and the 30 m test; type 3 by counting truck boxes; type 5 by projecting the
  light-vehicle box into the truck's body frame and testing the polygon.
- FR-015-47: if a query set fails `contracts/vlm-queries.schema.json` or its SHA-256, references a frame absent from the frame
  states, or the detector rule receives a missing camera calibration, a non-finite box or a box outside the image, then the stage or
  rule refuses that input (the rule answers "not applicable" for that query and the count is reported) and never guesses.
- P-015-09: projecting a ground point through the camera and back-projecting the pixel onto the terrain model returns the point,
  to 1e-6 m, for points 5 to 300 m from the camera.

Oracle: closed-form geometry written in the test: the ray through the principal point of a camera at height h pitched down by
alpha meets level ground at h / tan(alpha) (12 / tan 20 degrees = 32.969 m); pinhole projection of known ground points
(`_p015_kit.project`, OpenGL camera, independent of the code under test) to build boxes; ground distances computed by
Pythagoras from the chosen ground coordinates; counting for the arm plan; the schema of the query set (`jsonschema`) and the
spec's hostile example corpus (`specs/015-vlm/contracts/examples/vlm-queries.hostile-*.json`, rejected at the schema level).

Expected API of the implementation (package `pitstudio`, root environment):
- `pitstudio.reason.arms.arm_plan(queries) -> list[dict]`: one entry per (arm, reasoning) in this order: ("cosmos-q8_0", False),
  ("cosmos-q8_0", True), ("cosmos-bf16", False), ("qwen-base", False), ("detector-rule", False), ("constant", False); each entry
  `{"arm", "reasoning", "query_ids", "not_applicable_ids"}`; `queries` are DC-015-02 query dicts. `arms.constant_answer(qtype)`
  returns "no" for the binary types and "1" for type 3.
- `pitstudio.reason.detector_rule.NOT_APPLICABLE == "not applicable"`;
  `backproject(camera, uv, *, ground_z) -> (x, y)` (pixel to the horizontal plane z = ground_z, Z-up world, OpenGL camera of
  `_p015_kit.camera`; ValueError when the ray does not reach the plane);
  `detector_answer(qtype, detections, camera, *, image_size, ground_z, blind_zone=None, truck_heading_deg=None) -> str` returns
  "yes" | "no" | "0" | "1" | "2" | "3+" | NOT_APPLICABLE; `detections` are dicts `{"class", "score", "box": [x1, y1, x2, y2]}` in
  pixels (classes "person", "haul_truck", "light_vehicle"), `image_size` = (width, height), `blind_zone` = polygon in the truck
  body frame, `truck_heading_deg` the truck heading (a 2D box has none; reported as an ambiguity);
  `run_detector_rule(items) -> {"answers": {query_id: label}, "not_applicable_bad_input": int}` where each item is the keyword set of
  `detector_answer` plus `query_id` and `qtype` (`detections`, `camera`, ... may be missing or invalid: that item is
  NOT_APPLICABLE and counted).
- `pitstudio.reason.queries.load_query_set(path, *, expected_sha256, frames) -> dict` and
  `pitstudio.reason.queries.QuerySetInvalid(ValueError)`: the file is read, its SHA-256 compared with `expected_sha256`, the document
  validated against the schema, and every `frame_id` looked up in `frames` (mapping frame id to frame state); any failure raises.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pitstudio.reason.arms import arm_plan, constant_answer
from pitstudio.reason.detector_rule import NOT_APPLICABLE, backproject, detector_answer, run_detector_rule
from pitstudio.reason.queries import QuerySetInvalid, load_query_set

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _p015_contracts as contracts
import _p015_kit as kit

W, H = 1280, 720
CAM = kit.camera((0.0, 0.0, 12.0), heading_deg=0.0, pitch_down_deg=20.0)
POLY = [(6.0, -3.0), (14.0, -3.0), (14.0, 3.0), (6.0, 3.0)]


# ------------------------------------------------------------------------------------------------ arm plan
def _queries() -> list[dict]:
    return [
        {
            "query_id": f"t{t}-q{i}",
            "type": t,
            "gate_subset": t != 3 and i < 2,
            "reasoning_subset": i == 3,
            "truth": "1" if t == 3 else "yes",
        }
        for t in range(1, 7)
        for i in range(4)
    ]


def _entry(plan: list[dict], arm: str, reasoning: bool = False) -> dict:
    (e,) = [e for e in plan if e["arm"] == arm and e["reasoning"] is reasoning]
    return e


@pytest.mark.req("FR-015-28")
def test_the_arm_plan_runs_every_arm_on_the_prescribed_queries() -> None:
    qs = _queries()
    plan = arm_plan(qs)
    assert [(e["arm"], e["reasoning"]) for e in plan] == [
        ("cosmos-q8_0", False),
        ("cosmos-q8_0", True),
        ("cosmos-bf16", False),
        ("qwen-base", False),
        ("detector-rule", False),
        ("constant", False),
    ]
    all_ids = [q["query_id"] for q in qs]
    assert _entry(plan, "cosmos-q8_0")["query_ids"] == all_ids  # reasoning off on every query
    assert _entry(plan, "qwen-base")["query_ids"] == all_ids  # same queries, same prompts
    assert _entry(plan, "constant")["query_ids"] == all_ids
    assert _entry(plan, "cosmos-q8_0", True)["query_ids"] == [q["query_id"] for q in qs if q["reasoning_subset"]]
    assert _entry(plan, "cosmos-bf16")["query_ids"] == [q["query_id"] for q in qs if q["gate_subset"]]


@pytest.mark.req("FR-015-28")
def test_the_detector_rule_covers_types_1_3_and_5_and_is_not_applicable_to_2_4_and_6() -> None:
    qs = _queries()
    e = _entry(arm_plan(qs), "detector-rule")
    assert e["query_ids"] == [q["query_id"] for q in qs if q["type"] in (1, 3, 5)]
    assert e["not_applicable_ids"] == [q["query_id"] for q in qs if q["type"] in (2, 4, 6)]
    for arm in ("cosmos-q8_0", "qwen-base", "constant", "cosmos-bf16"):
        assert _entry(arm_plan(qs), arm)["not_applicable_ids"] == []


@pytest.mark.req("FR-015-28")
@pytest.mark.parametrize(("qtype", "answer"), [(1, "no"), (2, "no"), (3, "1"), (4, "no"), (5, "no"), (6, "no")])
def test_the_constant_arm_answers_no_for_binary_types_and_one_for_type_3(qtype: int, answer: str) -> None:
    assert constant_answer(qtype) == answer


@pytest.mark.req("FR-015-28")
def test_the_arm_plan_uses_only_the_given_query_ids() -> None:
    qs = _queries()
    ids = {q["query_id"] for q in qs}
    for e in arm_plan(qs):
        assert set(e["query_ids"]) | set(e["not_applicable_ids"]) <= ids
        assert len(set(e["query_ids"])) == len(e["query_ids"])


# ------------------------------------------------------------------------------------------------ geometry helpers
def _box_at(
    x: float, y: float, *, w: float = 40.0, h: float = 80.0, cam: dict = CAM, ground_z: float = 0.0
) -> list[float]:
    """Pixel box whose bottom-centre is the projection of the ground point (x, y, ground_z)."""
    u, v, depth = kit.project(cam, (x, y, ground_z))
    assert depth > 0
    box = [u - w / 2, v - h, u + w / 2, v]
    inside = box[0] >= 0 and box[2] <= W and box[1] >= 0 and box[3] <= H
    assert inside, f"fixture box outside the image: {box}"
    return box


def _det(cls: str, x: float, y: float, score: float = 0.9, **kw) -> dict:
    return {"class": cls, "score": score, "box": _box_at(x, y, **kw)}


def _ans(qtype: int, dets: list[dict], **kw) -> str:
    kw.setdefault("camera", CAM)
    kw.setdefault("image_size", (W, H))
    kw.setdefault("ground_z", 0.0)
    return detector_answer(qtype, dets, **kw)


# ------------------------------------------------------------------------------------------------ back-projection
@pytest.mark.req("P-015-09")
def test_the_principal_point_ray_meets_level_ground_at_height_over_tangent_of_the_pitch() -> None:
    x, y = backproject(CAM, (640.0, 360.0), ground_z=0.0)
    assert x == pytest.approx(12.0 / math.tan(math.radians(20.0)), abs=1e-6)  # 32.969 m ahead
    assert y == pytest.approx(0.0, abs=1e-6)


@pytest.mark.req("P-015-09")
def test_a_ray_above_the_horizon_has_no_ground_point() -> None:
    cam = kit.camera((0.0, 0.0, 12.0), 0.0, 5.0)
    with pytest.raises(ValueError):  # noqa: PT011
        backproject(cam, (640.0, 10.0), ground_z=0.0)  # 17.5 degrees above the axis, 5 degrees down: 12.5 degrees up


@pytest.mark.req("P-015-09")
@settings(max_examples=300, deadline=None)
@given(
    st.floats(-180, 180),
    st.floats(15, 40),
    st.floats(3, 30),
    st.floats(-5, 5),
    st.floats(5, 300),
    st.floats(-35, 35),
)
def test_property_projecting_a_ground_point_and_back_projecting_the_pixel_returns_the_point(
    heading: float, pitch: float, height: float, ground_z: float, dist: float, bearing: float
) -> None:
    cam = kit.camera((10.0, -20.0, ground_z + height), heading, pitch, fx=300.0)
    th = math.radians(heading + bearing)
    point = (10.0 + dist * math.cos(th), -20.0 + dist * math.sin(th), ground_z)
    u, v, depth = kit.project(cam, point)
    assume(depth > 0 and 0 <= u <= W and 0 <= v <= H)
    x, y = backproject(cam, (u, v), ground_z=ground_z)
    assert (x, y) == pytest.approx((point[0], point[1]), abs=1e-6)


# ------------------------------------------------------------------------------------------------ the rule per type
@pytest.mark.req("FR-015-29")
@pytest.mark.parametrize(
    ("person_xy", "truck_xy", "expected"),
    [
        ((30.0, 0.0), (50.0, 0.0), "yes"),  # ground distance 20 m
        ((30.0, 0.0), (45.0, 15.0), "yes"),  # hypot(15, 15) = 21.2 m
        ((30.0, 0.0), (65.0, 0.0), "no"),  # 35 m
        ((30.0, -10.0), (62.0, 14.0), "no"),  # hypot(32, 24) = 40 m
        ((40.0, 3.0), (40.0, 3.0), "yes"),  # same place: 0 m
    ],
)
def test_type_1_tests_the_30_m_distance_between_back_projected_bottom_centres(
    person_xy: tuple, truck_xy: tuple, expected: str
) -> None:
    dets = [_det("person", *person_xy), _det("haul_truck", *truck_xy)]
    assert _ans(1, dets) == expected


@pytest.mark.req("FR-015-29")
def test_type_1_without_a_person_or_a_truck_detection_is_no() -> None:
    assert _ans(1, [_det("haul_truck", 50.0, 0.0)]) == "no"
    assert _ans(1, [_det("person", 40.0, 0.0)]) == "no"
    assert _ans(1, []) == "no"


@pytest.mark.req("FR-015-29")
def test_only_detections_with_score_at_least_0_5_count() -> None:
    near = [_det("person", 30.0, 0.0, 0.9), _det("haul_truck", 50.0, 0.0, 0.5)]
    assert _ans(1, near) == "yes"  # a score of exactly 0.5 counts
    assert _ans(1, [_det("person", 30.0, 0.0, 0.9), _det("haul_truck", 50.0, 0.0, 0.49)]) == "no"
    assert _ans(1, [_det("person", 30.0, 0.0, 0.2), _det("haul_truck", 50.0, 0.0, 0.9)]) == "no"
    trucks = [_det("haul_truck", 40.0 + 10 * i, 0.0, s) for i, s in enumerate([0.95, 0.6, 0.49, 0.1])]
    assert _ans(3, trucks) == "2"


@pytest.mark.req("FR-015-29")
@pytest.mark.parametrize(("n_trucks", "expected"), [(0, "0"), (1, "1"), (2, "2"), (3, "3+"), (4, "3+")])
def test_type_3_counts_the_truck_boxes_in_the_classes_0_1_2_3_plus(n_trucks: int, expected: str) -> None:
    dets = [_det("haul_truck", 35.0 + 8.0 * i, 6.0 * ((-1) ** i)) for i in range(n_trucks)]
    dets += [_det("person", 30.0, 0.0), _det("light_vehicle", 45.0, -3.0)]  # other classes are not counted
    assert _ans(3, dets) == expected


@pytest.mark.req("FR-015-29")
@pytest.mark.parametrize(
    ("lv_body", "expected"),
    [((10.0, 0.0), "yes"), ((12.0, 2.0), "yes"), ((10.0, 6.0), "no"), ((-10.0, 0.0), "no"), ((20.0, 0.0), "no")],
)
def test_type_5_projects_the_light_vehicle_into_the_truck_body_frame_and_tests_the_polygon(
    lv_body: tuple, expected: str
) -> None:
    truck = (60.0, 0.0)
    lv = kit.body_to_world(truck, 0.0, lv_body)
    dets = [_det("haul_truck", *truck), _det("light_vehicle", *lv)]
    assert _ans(5, dets, blind_zone=POLY, truck_heading_deg=0.0) == expected


@pytest.mark.req("FR-015-29")
def test_type_5_follows_the_truck_heading() -> None:
    truck, heading = (60.0, 5.0), 90.0  # the truck faces +y: its front zone is at larger y
    lv_in = kit.body_to_world(truck, heading, (10.0, 0.0))
    lv_out = kit.body_to_world(truck, heading, (10.0, 6.0))
    assert (
        _ans(5, [_det("haul_truck", *truck), _det("light_vehicle", *lv_in)], blind_zone=POLY, truck_heading_deg=heading)
        == "yes"
    )
    assert (
        _ans(
            5, [_det("haul_truck", *truck), _det("light_vehicle", *lv_out)], blind_zone=POLY, truck_heading_deg=heading
        )
        == "no"
    )


@pytest.mark.req("FR-015-28")
@pytest.mark.parametrize("qtype", [2, 4, 6])
def test_the_rule_has_no_answer_for_types_2_4_and_6(qtype: int) -> None:
    assert _ans(qtype, [_det("haul_truck", 50.0, 0.0)]) == NOT_APPLICABLE


# ------------------------------------------------------------------------------------------------ hostile detector inputs
_GOOD_BOX = _box_at(40.0, 0.0)


def _hostile_cases() -> list[tuple[str, dict]]:
    good = [
        {"class": "person", "score": 0.9, "box": _GOOD_BOX},
        {"class": "haul_truck", "score": 0.9, "box": _box_at(50.0, 0.0)},
    ]

    def with_box(box) -> list[dict]:
        return [{"class": "person", "score": 0.9, "box": box}, good[1]]

    high_cam = kit.camera((0.0, 0.0, 12.0), 0.0, 5.0)
    return [
        ("no-camera", {"detections": good, "camera": None}),
        ("empty-camera", {"detections": good, "camera": {}}),
        ("camera-without-pose", {"detections": good, "camera": {"intrinsics": CAM["intrinsics"]}}),
        ("camera-without-intrinsics", {"detections": good, "camera": {"pose": CAM["pose"]}}),
        (
            "camera-zero-focal-length",
            {"detections": good, "camera": {**CAM, "intrinsics": {**CAM["intrinsics"], "fx_px": 0.0}}},
        ),
        (
            "camera-nan-pose",
            {"detections": good, "camera": {**CAM, "pose": {**CAM["pose"], "translation_m": [math.nan, 0.0, 12.0]}}},
        ),
        ("nan-box", {"detections": with_box([math.nan, 100.0, 200.0, 300.0]), "camera": CAM}),
        ("inf-box", {"detections": with_box([100.0, 100.0, math.inf, 300.0]), "camera": CAM}),
        ("box-left-of-image", {"detections": with_box([-500.0, 100.0, -100.0, 300.0]), "camera": CAM}),
        ("box-below-image", {"detections": with_box([100.0, 800.0, 200.0, 900.0]), "camera": CAM}),
        ("box-beyond-right-edge", {"detections": with_box([2000.0, 100.0, 2100.0, 300.0]), "camera": CAM}),
        ("inverted-box", {"detections": with_box([300.0, 300.0, 200.0, 100.0]), "camera": CAM}),
        ("zero-area-box", {"detections": with_box([300.0, 300.0, 300.0, 300.0]), "camera": CAM}),
        ("short-box", {"detections": with_box([300.0, 300.0]), "camera": CAM}),
        (
            "nan-score",
            {"detections": [{"class": "person", "score": math.nan, "box": _GOOD_BOX}, good[1]], "camera": CAM},
        ),
        ("detections-none", {"detections": None, "camera": CAM}),
        ("ray-above-horizon", {"detections": with_box([600.0, 0.0, 700.0, 10.0]), "camera": high_cam}),
    ]


@pytest.mark.req("FR-015-47")
@pytest.mark.parametrize(("name", "kw"), _hostile_cases(), ids=[c[0] for c in _hostile_cases()])
def test_the_rule_answers_not_applicable_for_missing_calibration_non_finite_or_outside_boxes_and_never_guesses(
    name: str, kw: dict
) -> None:
    assert detector_answer(1, image_size=(W, H), ground_z=0.0, **kw) == NOT_APPLICABLE, name


@pytest.mark.req("FR-015-47")
def test_the_batch_runner_counts_the_refused_inputs() -> None:
    good = [_det("person", 30.0, 0.0), _det("haul_truck", 50.0, 0.0)]
    base = {"camera": CAM, "image_size": (W, H), "ground_z": 0.0}
    items = [
        {"query_id": "a", "qtype": 1, "detections": good, **base},
        {"query_id": "b", "qtype": 1, "detections": good, **{**base, "camera": None}},
        {
            "query_id": "c",
            "qtype": 3,
            "detections": [{"class": "haul_truck", "score": 0.9, "box": [math.nan, 0, 1, 1]}],
            **base,
        },
        {"query_id": "d", "qtype": 2, "detections": good, **base},  # not applicable by design: not a bad input
        {"query_id": "e", "qtype": 3, "detections": [_det("haul_truck", 50.0, 0.0)], **base},
    ]
    out = run_detector_rule(items)
    assert out["answers"] == {"a": "yes", "b": NOT_APPLICABLE, "c": NOT_APPLICABLE, "d": NOT_APPLICABLE, "e": "1"}
    assert out["not_applicable_bad_input"] == 2


# ------------------------------------------------------------------------------------------------ hostile query sets
def _frames_and_set(tmp_path: Path) -> tuple[dict, Path, str]:
    kit.write_frame_files(tmp_path)
    frames = {
        f"b2-pit-s0001-f{i:04d}": kit.frame_state(
            [kit.truck(100.0, 0.0), kit.person(110.0, 5.0)], frame_id=f"b2-pit-s0001-f{i:04d}"
        )
        for i in range(4)
    }
    queries = [
        {
            "query_id": f"q{i}",
            "frame_id": fid,
            "frame_state_sha256": kit.canonical_sha256(f),
            "type": 1 + i,
            "condition": "day",
            "location": "haul_road",
            "truth": "no" if i != 2 else "1",
            "gate_subset": False,
            "reasoning_subset": False,
        }
        for i, (fid, f) in enumerate(frames.items())
    ]
    doc = {"schema_version": "1.0", "seed": 7, "source_run_id": "20261012T013000Z-b2", "queries": queries}
    assert contracts.errors(doc, "vlm-queries.schema.json") == []
    p = tmp_path / "queries.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return frames, p, hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.req("FR-015-47")
def test_a_valid_query_set_with_its_digest_and_all_frames_is_loaded(tmp_path: Path) -> None:
    frames, p, sha = _frames_and_set(tmp_path)
    doc = load_query_set(p, expected_sha256=sha, frames=frames)
    assert [q["query_id"] for q in doc["queries"]] == ["q0", "q1", "q2", "q3"]


@pytest.mark.req("FR-015-47")
def test_a_query_set_whose_sha256_differs_is_refused(tmp_path: Path) -> None:
    frames, p, sha = _frames_and_set(tmp_path)
    with pytest.raises(QuerySetInvalid):
        load_query_set(p, expected_sha256="0" * 64, frames=frames)
    p.write_bytes(p.read_bytes() + b" ")  # one extra byte after the digest was taken
    with pytest.raises(QuerySetInvalid):
        load_query_set(p, expected_sha256=sha, frames=frames)


@pytest.mark.req("FR-015-47")
def test_a_query_set_that_references_a_frame_absent_from_the_frame_states_is_refused(tmp_path: Path) -> None:
    frames, p, sha = _frames_and_set(tmp_path)
    missing = dict(list(frames.items())[:-1])
    with pytest.raises(QuerySetInvalid, match="b2-pit-s0001-f0003"):
        load_query_set(p, expected_sha256=sha, frames=missing)
    with pytest.raises(QuerySetInvalid):
        load_query_set(p, expected_sha256=sha, frames={})


@pytest.mark.req("FR-015-47")
@pytest.mark.parametrize(
    "text", ["", "{", "null", "[]", '{"queries": []}', '{"schema_version": "1.0"}', "﻿{}", '{"a": NaN}']
)
def test_a_malformed_or_schema_invalid_query_file_is_refused(tmp_path: Path, text: str) -> None:
    frames, _, _ = _frames_and_set(tmp_path)
    p = tmp_path / "bad.json"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(QuerySetInvalid):
        load_query_set(p, expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest(), frames=frames)


_HOSTILE_SETS = sorted((kit.SPEC015 / "contracts" / "examples").glob("vlm-queries.hostile-*.json"))


@pytest.mark.req("FR-015-47")
@pytest.mark.parametrize("path", _HOSTILE_SETS, ids=[p.stem for p in _HOSTILE_SETS])
def test_every_hostile_query_set_of_the_spec_corpus_is_refused_even_with_a_matching_digest(
    tmp_path: Path, path: Path
) -> None:
    frames, _, _ = _frames_and_set(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    for q in doc.get("queries", []) if isinstance(doc, dict) else []:
        if isinstance(q, dict) and isinstance(q.get("frame_id"), str):
            frames.setdefault(q["frame_id"], kit.frame_state([kit.truck(0.0, 0.0)], frame_id="b2-pit-s0001-f0000"))
    p = tmp_path / "hostile.json"
    p.write_bytes(path.read_bytes())
    with pytest.raises(QuerySetInvalid):
        load_query_set(p, expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest(), frames=frames)
