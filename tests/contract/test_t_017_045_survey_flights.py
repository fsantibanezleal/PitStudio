"""T-017-045: survey flight records (contract).

Requirements: FR-017-36.

Spec: specs/017-planning-survey/spec.md FR-017-36: the survey comprises 12 rendered flights, ground sampling
distance {2, 4,
8} cm/px x forward/side overlap {70, 80} % x sun elevation {30, 60} degrees, each with nadir and +-30 degree
oblique images
and 3 sensor-noise seeds, recorded with exact intrinsics, poses and depth per `survey-flight.schema.json` (DC-017-05).
plan.md test strategy row FR-017-36: DC-017-05 valid and invalid flight records.

Oracles:
- the full factorial of the three design factors written in the test (3 x 2 x 2 = 12 designs, x 3 seeds = 36 records);
- the pinhole relation GSD = altitude / fx_px: with fx = 6,000 px the altitudes are 0.02 x 6,000 = 120 m, 240 m and
  480 m for 2, 4 and 8 cm/px (the spec's valid example, GSD 2, has its nadir image at z = 120 m); the ground
  footprint of an
  image is altitude x (width_px / fx, height_px / fy) = 120 x (4000 / 6000, 3000 / 6000) = 80 m x 60 m at 2 cm/px; the
  spacing between image centres is footprint x (1 - overlap) (the long image side across the track: the forward
  spacing
  uses the 60 m side, the side spacing the 80 m side; UNVERIFIED reading of "forward/side");
- the optical axis of a camera-to-world pose (x right, y down, z forward; unit quaternion w, x, y, z) is the
  rotated unit
  vector R (0, 0, 1); a nadir camera looks along world -z, an oblique one is tilted by 30 degrees from it: the
  angle between
  the axis and (0, 0, -1) is |tilt| (by `numpy`, independent of the code under test);
- the schema `contracts/survey-flight.schema.json` with `jsonschema`, and the spec's valid example for the scene
  block.

Expected public API (module `pitstudio.survey.flights`, root environment, numpy only):
    DESIGNS: the 12 (gsd_cm_per_px, overlap_pct, sun_elevation_deg) triples as FlightSpec objects in `plan_flights()`
    SEEDS = (0, 1, 2); TILTS_DEG = (-30, 0, 30)
    @dataclass FlightSpec: id (str "f01" .. "f12"), gsd_cm_per_px, overlap_pct, sun_elevation_deg, altitude_m (float),
        camera (dict as DC-017-05 `camera`), images (list of {"tilt_deg", "position_m": [x, y, z], "rotation_wxyz"})
    plan_flights(*, extent_m: tuple[float, float] = (200.0, 200.0)) -> list[FlightSpec]
        12 specs; each has at least one nadir image and at least one image of each oblique tilt; positions are
        inside the
        extent expanded by one footprint; camera = pinhole, distortion none, 4000 x 3000 px, fx = fy = 6,000, cx
        2,000,
        cy 1,500.
    flight_geometry(gsd_cm_per_px: float, overlap_pct: float, camera: Mapping) -> dict
        {"altitude_m", "footprint_m": [w, h], "forward_spacing_m", "side_spacing_m"} by the relations above.
    make_record(spec: FlightSpec, seed: int, *, scene: Mapping, digest: Callable[[str], str]) -> dict
        the DC-017-05 document: synthetic true, flight id, design, seed, camera, images (name
        "renders/e2/<flight>/s<seed>/img_NNNN.png" and depth name ".../depth_NNNN.exr", sha256 from `digest(name)`,
        tilt,
        pose), scene as given; ValueError for a seed outside SEEDS.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pytest
from pitstudio.survey.flights import SEEDS, TILTS_DEG, flight_geometry, make_record, plan_flights

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads(
    (ROOT / "specs/017-planning-survey/contracts/examples/survey-flight.valid.json").read_text("utf-8")
)
SCHEMA = json.loads((ROOT / "contracts" / "survey-flight.schema.json").read_text("utf-8"))
CAMERA = EXAMPLE["camera"]
FACTORIAL = set(itertools.product((2, 4, 8), (70, 80), (30, 60)))


def _digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def _errors(doc: dict) -> list:
    from jsonschema import Draft202012Validator

    return list(Draft202012Validator(SCHEMA).iter_errors(doc))


def _axis(q) -> np.ndarray:
    """The optical axis (camera z) of a camera-to-world unit quaternion (w, x, y, z)."""
    w, x, y, z = q
    return np.array([2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)])


# ----------------------------------------------------------------------------------------------------------------------
# the design
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-36")
def test_the_survey_has_the_12_designs_of_the_full_factorial_and_3_seeds() -> None:
    specs = plan_flights()
    assert len(specs) == 12
    assert {(s.gsd_cm_per_px, s.overlap_pct, s.sun_elevation_deg) for s in specs} == FACTORIAL
    assert sorted(s.id for s in specs) == [f"f{i:02d}" for i in range(1, 13)]
    assert SEEDS == (0, 1, 2)
    assert TILTS_DEG == (-30, 0, 30)


@pytest.mark.req("FR-017-36")
def test_the_pinhole_relation_gives_the_flight_altitudes() -> None:
    assert CAMERA["fx_px"] == 6000.0
    for gsd, altitude in ((2, 120.0), (4, 240.0), (8, 480.0)):
        geometry = flight_geometry(gsd, 80, CAMERA)
        assert geometry["altitude_m"] == pytest.approx(altitude, rel=1e-12)
    assert EXAMPLE["images"][0]["pose"]["position_m"][2] == 120.0  # the example's nadir image at GSD 2 cm/px
    for spec in plan_flights():
        assert spec.altitude_m == pytest.approx(spec.gsd_cm_per_px / 100 * 6000.0, rel=1e-12)


@pytest.mark.req("FR-017-36")
@pytest.mark.parametrize(("overlap", "forward", "side"), [(70, 18.0, 24.0), (80, 12.0, 16.0)])
def test_footprint_and_image_spacing_follow_the_overlap_by_hand(overlap: int, forward: float, side: float) -> None:
    g = flight_geometry(2, overlap, CAMERA)
    assert g["footprint_m"] == pytest.approx([80.0, 60.0], rel=1e-12)  # 120 x 4000 / 6000, 120 x 3000 / 6000
    assert g["forward_spacing_m"] == pytest.approx(forward, rel=1e-12)  # 60 m x (1 - overlap)
    assert g["side_spacing_m"] == pytest.approx(side, rel=1e-12)  # 80 m x (1 - overlap)


@pytest.mark.req("FR-017-36")
def test_every_flight_has_nadir_and_both_oblique_images_with_poses_that_look_the_right_way() -> None:
    down = np.array([0.0, 0.0, -1.0])
    for spec in plan_flights():
        tilts = {img["tilt_deg"] for img in spec.images}
        assert tilts == set(TILTS_DEG), spec.id
        for img in spec.images:
            q = np.array(img["rotation_wxyz"], dtype=float)
            assert float(np.linalg.norm(q)) == pytest.approx(1.0, abs=1e-12)  # a unit quaternion
            angle = math.degrees(math.acos(max(-1.0, min(1.0, float(_axis(q) @ down)))))
            assert angle == pytest.approx(abs(img["tilt_deg"]), abs=1e-9)
            if img["tilt_deg"] == 0:
                assert img["position_m"][2] == pytest.approx(spec.altitude_m, rel=1e-12)  # nadir images at the altitude


@pytest.mark.req("FR-017-36")
def test_the_nadir_pose_of_the_spec_example_looks_straight_down() -> None:
    q = EXAMPLE["images"][0]["pose"]["rotation_wxyz"]
    assert q == [0.0, 1.0, 0.0, 0.0]
    assert _axis(q).tolist() == [0.0, 0.0, -1.0]  # the oracle function agrees with the example


@pytest.mark.req("FR-017-36")
def test_the_camera_is_a_pinhole_without_distortion_with_exact_intrinsics() -> None:
    for spec in plan_flights():
        assert spec.camera == {
            "model": "pinhole",
            "distortion": "none",
            "width_px": 4000,
            "height_px": 3000,
            "fx_px": 6000.0,
            "fy_px": 6000.0,
            "cx_px": 2000.0,
            "cy_px": 1500.0,
        }


# ----------------------------------------------------------------------------------------------------------------------
# the records
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-36")
def test_all_36_flight_seed_records_validate_against_dc_017_05_and_are_distinct() -> None:
    names: set[str] = set()
    for spec in plan_flights():
        for seed in SEEDS:
            doc = make_record(spec, seed, scene=EXAMPLE["scene"], digest=_digest)
            assert _errors(doc) == [], (spec.id, seed)
            assert doc["synthetic"] is True
            assert (doc["flight"], doc["seed"]) == (spec.id, seed)
            assert doc["design"] == {
                "gsd_cm_per_px": spec.gsd_cm_per_px,
                "overlap_pct": spec.overlap_pct,
                "sun_elevation_deg": spec.sun_elevation_deg,
            }
            for img in doc["images"]:
                assert img["name"].startswith(f"renders/e2/{spec.id}/s{seed}/img_")
                assert img["depth"]["name"].startswith(f"renders/e2/{spec.id}/s{seed}/depth_")
                assert img["sha256"] == _digest(img["name"])
                names.add(img["name"])
    assert len(names) == sum(len(s.images) for s in plan_flights()) * 3  # no image name is shared between records


@pytest.mark.req("FR-017-36")
def test_a_seed_outside_the_three_noise_seeds_is_refused() -> None:
    spec = plan_flights()[0]
    for bad in (3, -1, 17):
        with pytest.raises(ValueError, match="seed"):
            make_record(spec, bad, scene=EXAMPLE["scene"], digest=_digest)


@pytest.mark.req("FR-017-36")
def test_the_schema_rejects_records_outside_the_design_grid() -> None:
    doc = make_record(plan_flights()[0], 0, scene=EXAMPLE["scene"], digest=_digest)
    for key, value in (("gsd_cm_per_px", 3), ("overlap_pct", 75), ("sun_elevation_deg", 45)):
        bad = copy.deepcopy(doc)
        bad["design"][key] = value
        assert _errors(bad), key
    bad = copy.deepcopy(doc)
    bad["images"][0]["tilt_deg"] = 15
    assert _errors(bad)
    bad = copy.deepcopy(doc)
    bad["camera"]["distortion"] = "brown"
    assert _errors(bad)
