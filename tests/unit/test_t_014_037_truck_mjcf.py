# ruff: noqa: E501
"""T-014-037: haul-truck MJCF generator (mass, wheelbase, track within 0.1 %) and its hostile parameter files.

Requirements: FR-014-05, FR-014-07 (truck side).

Spec: specs/014-robot-learning/spec.md FR-014-05: "The truck generator shall write an MJCF model with one chassis body, six wheels (two
steered front, four driven rear) and a steering joint, from a parameter file of published academic dimensions
(`contracts/machine-params.schema.json`), whose total mass, wheelbase and track width equal the parameter file within 0.1 %."
FR-014-07: invalid parameter files (non-finite or non-positive mass or dimension, lower limit >= upper, torque limit <= 0, unknown
key, a mesh reference outside the generated asset folder: URL, absolute path or `..`) raise ValueError naming the JSON pointer and
write no model. The MuJoCo compile check is the GPU-lane task T-014-062; this test needs only the standard library.

Oracle: the parameter file `specs/014-robot-learning/contracts/examples/machine-params.valid.json` (160,000 kg empty, wheel mass 4,000 kg,
wheelbase 5.3 m, track 5.0 m, front axle 2.6 m ahead of the CG, wheel radius 1.7 m, width 1.1 m, chassis 12 x 7.5 x 6 m, steering limit
38 deg) read back from the XML parsed by `xml.etree.ElementTree`: mass = sum over bodies, positions = sums of `pos` along the body
chain; the spec's hostile example corpus (`index.json`) and hand-built mutations.

Expected API of the implementation (module `pitstudio.robots.machines`, see T-014-026):
    truck_mjcf(params) -> str ; write_truck_mjcf(params, out_dir) -> pathlib.Path   (<out_dir>/<id>.xml)
    Model layout (all the tests read exactly this; bodies carry `pos` only, no rotation attributes; rotations are on geoms):
      - <mujoco model="<id>">; optional <compiler angle="degree"|"radian">, default degree
      - exactly one body named "chassis", a child of <worldbody>, whose frame origin is the centre of gravity (x forward, y left, z up),
        with a box geom of half extents (chassis_length / 2, chassis_width / 2, chassis_height / 2)
      - exactly six bodies whose names start with "wheel": wheel_front_left, wheel_front_right, wheel_rear_left_inner,
        wheel_rear_left_outer, wheel_rear_right_inner, wheel_rear_right_outer, all descendants of the chassis; each holds one hinge joint
        named "<body name>_spin" and a cylinder geom of radius wheel_radius_m and half width wheel_width_m / 2
      - exactly one other joint, named "steer", a hinge on a body that is an ancestor of both front wheels and not of any rear wheel,
        with range="-<max_steer_deg> <max_steer_deg>" in the compiler angle unit
      - every body holds an <inertial mass="..."/> (the chassis mass is empty_mass_kg - 6 * wheel_mass_kg and every wheel has
        wheel_mass_kg), so that the sum of all inertial masses is empty_mass_kg
      - front wheel centres at x = +cg_to_front_axle_m and y = +-track_width_m / 2 relative to the chassis; the four rear wheels at
        x = cg_to_front_axle_m - wheelbase_m, with the mean y of the wheels of each side at +-track_width_m / 2
      - actuators: one <motor joint="<wheel>_spin"/> per rear wheel (four), none on a front wheel
      - <asset><mesh name=... file="<path>"/> entries use the relative paths of the `meshes` member unchanged
    ValueError with the JSON pointer of the first offending member, as for the excavator; additionally, a chassis mass that is not
    positive (empty_mass_kg <= 6 * wheel_mass_kg) names "/empty_mass_kg" or "/wheel_mass_kg", and a front axle at or behind the rear
    axle (cg_to_front_axle_m >= wheelbase_m) names "/cg_to_front_axle_m".
"""

from __future__ import annotations

import copy
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pitstudio.robots.machines import truck_mjcf, write_truck_mjcf

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
VALID = json.loads((EXAMPLES / "machine-params.valid.json").read_text(encoding="utf-8"))
FRONT = ("wheel_front_left", "wheel_front_right")
REAR = ("wheel_rear_left_inner", "wheel_rear_left_outer", "wheel_rear_right_inner", "wheel_rear_right_outer")
TOL = 1e-3  # 0.1 %


def parse(text: str) -> ET.Element:
    return ET.fromstring(text)


def parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def bodies(root: ET.Element) -> dict[str, ET.Element]:
    return {b.get("name"): b for b in root.iter("body")}


def chain(root: ET.Element, body: ET.Element) -> list[ET.Element]:
    pm = parent_map(root)
    out = [body]
    while out[-1] in pm and pm[out[-1]].tag == "body":
        out.append(pm[out[-1]])
    return out  # the body first, the top-level body last


def pos_of(root: ET.Element, body: ET.Element) -> tuple[float, float, float]:
    x = y = z = 0.0
    for b in chain(root, body):
        p = [float(v) for v in b.get("pos", "0 0 0").split()]
        x, y, z = x + p[0], y + p[1], z + p[2]
    return x, y, z


def rel_pos(root: ET.Element, body: ET.Element, ref: ET.Element) -> tuple[float, float, float]:
    a, b = pos_of(root, body), pos_of(root, ref)
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def total_mass(root: ET.Element) -> float:
    return sum(float(i.get("mass")) for i in root.iter("inertial"))


@pytest.fixture(scope="module")
def model() -> ET.Element:
    return parse(truck_mjcf(VALID))


# ------------------------------------------------------------------------------------------------ FR-014-05
@pytest.mark.req("FR-014-05")
def test_one_chassis_body_and_six_wheel_bodies(model) -> None:
    bs = bodies(model)
    assert model.tag == "mujoco"
    assert model.get("model") == VALID["id"]
    assert [n for n in bs if n == "chassis"] == ["chassis"]
    assert sorted(n for n in bs if n.startswith("wheel")) == sorted(FRONT + REAR)
    pm = parent_map(model)
    assert pm[bs["chassis"]].tag == "worldbody"
    for w in FRONT + REAR:
        assert bs["chassis"] in chain(model, bs[w])


@pytest.mark.req("FR-014-05")
def test_two_steered_front_wheels_share_one_steering_joint(model) -> None:
    bs = bodies(model)
    steer = [j for j in model.iter("joint") if j.get("name") == "steer"]
    assert len(steer) == 1
    assert steer[0].get("type", "hinge") == "hinge"
    pm = parent_map(model)
    owner = pm[steer[0]]
    assert owner.tag == "body"
    for w in FRONT:
        assert owner in chain(model, bs[w])
    for w in REAR:
        assert owner not in chain(model, bs[w])
    non_wheel = [j.get("name") for j in model.iter("joint") if not j.get("name", "").endswith("_spin")]
    assert non_wheel == ["steer"]  # the only joint besides the six wheel spins


@pytest.mark.req("FR-014-05")
def test_steering_range_is_the_parameter_file_limit(model) -> None:
    compiler = model.find("compiler")
    unit = compiler.get("angle", "degree") if compiler is not None else "degree"
    factor = 1.0 if unit == "degree" else 180.0 / math.pi
    steer = next(j for j in model.iter("joint") if j.get("name") == "steer")
    lo, hi = (float(v) * factor for v in steer.get("range").split())
    assert lo == pytest.approx(-VALID["max_steer_deg"], rel=1e-9)
    assert hi == pytest.approx(VALID["max_steer_deg"], rel=1e-9)


@pytest.mark.req("FR-014-05")
def test_each_wheel_has_a_spin_joint_and_a_cylinder_of_the_parameter_file(model) -> None:
    bs = bodies(model)
    for w in FRONT + REAR:
        joints = [j for j in bs[w].findall("joint")]
        assert [j.get("name") for j in joints] == [f"{w}_spin"]
        geoms = [g for g in bs[w].findall("geom") if g.get("type") == "cylinder"]
        assert len(geoms) == 1
        size = [float(v) for v in geoms[0].get("size").split()]
        assert size[0] == pytest.approx(VALID["wheel_radius_m"], rel=TOL)
        assert size[1] == pytest.approx(VALID["wheel_width_m"] / 2.0, rel=TOL)


@pytest.mark.req("FR-014-05")
def test_total_mass_equals_the_parameter_file_within_a_tenth_of_a_percent(model) -> None:
    assert total_mass(model) == pytest.approx(VALID["empty_mass_kg"], rel=TOL)
    bs = bodies(model)
    assert float(bs["chassis"].find("inertial").get("mass")) == pytest.approx(
        VALID["empty_mass_kg"] - 6 * VALID["wheel_mass_kg"], rel=TOL
    )
    for w in FRONT + REAR:
        assert float(bs[w].find("inertial").get("mass")) == pytest.approx(VALID["wheel_mass_kg"], rel=TOL)


@pytest.mark.req("FR-014-05")
def test_wheelbase_equals_the_parameter_file_within_a_tenth_of_a_percent(model) -> None:
    bs = bodies(model)
    fx = [rel_pos(model, bs[w], bs["chassis"])[0] for w in FRONT]
    rx = [rel_pos(model, bs[w], bs["chassis"])[0] for w in REAR]
    assert fx[0] == pytest.approx(fx[1], abs=1e-9)
    assert max(rx) - min(rx) < 1e-9  # the four rear wheels share one axle line
    assert fx[0] - rx[0] == pytest.approx(VALID["wheelbase_m"], rel=TOL)
    assert fx[0] == pytest.approx(VALID["cg_to_front_axle_m"], rel=TOL)


@pytest.mark.req("FR-014-05")
def test_track_width_equals_the_parameter_file_within_a_tenth_of_a_percent(model) -> None:
    bs = bodies(model)
    ys = {w: rel_pos(model, bs[w], bs["chassis"])[1] for w in FRONT + REAR}
    assert ys["wheel_front_left"] - ys["wheel_front_right"] == pytest.approx(VALID["track_width_m"], rel=TOL)
    left = [ys["wheel_rear_left_inner"], ys["wheel_rear_left_outer"]]
    right = [ys["wheel_rear_right_inner"], ys["wheel_rear_right_outer"]]
    assert sum(left) / 2 - sum(right) / 2 == pytest.approx(VALID["track_width_m"], rel=TOL)
    assert sum(left) / 2 == pytest.approx(VALID["track_width_m"] / 2, rel=TOL)
    # dual rear wheels: inner and outer are one wheel width apart
    assert abs(left[0] - left[1]) == pytest.approx(VALID["wheel_width_m"], rel=TOL)


@pytest.mark.req("FR-014-05")
def test_the_chassis_box_has_the_parameter_file_dimensions(model) -> None:
    chassis = bodies(model)["chassis"]
    boxes = [g for g in chassis.findall("geom") if g.get("type") == "box"]
    assert len(boxes) == 1
    half = [float(v) for v in boxes[0].get("size").split()]
    want = [VALID["chassis_length_m"] / 2, VALID["chassis_width_m"] / 2, VALID["chassis_height_m"] / 2]
    assert half == pytest.approx(want, rel=TOL)


@pytest.mark.req("FR-014-05")
def test_the_four_rear_wheels_are_driven_and_the_front_wheels_are_not(model) -> None:
    driven = sorted(m.get("joint") for m in model.iter("motor"))
    assert driven == sorted(f"{w}_spin" for w in REAR)
    assert not any(m.get("joint", "").startswith("wheel_front") for m in model.iter("motor"))


@pytest.mark.req("FR-014-05")
def test_mesh_assets_use_the_relative_paths_of_the_parameter_file(model) -> None:
    files = sorted(m.get("file") for m in model.iter("mesh"))
    assert files == sorted(VALID["meshes"].values())


@pytest.mark.req("FR-014-05")
def test_different_parameters_flow_through_within_the_tolerance() -> None:
    doc = copy.deepcopy(VALID)
    doc["id"] = "variant-truck"
    doc["empty_mass_kg"] = 250_000
    doc["wheel_mass_kg"] = 5_000
    doc["wheelbase_m"] = 6.4
    doc["cg_to_front_axle_m"] = 3.1
    doc["track_width_m"] = 5.6
    root = parse(truck_mjcf(doc))
    bs = bodies(root)
    assert root.get("model") == "variant-truck"
    assert total_mass(root) == pytest.approx(250_000, rel=TOL)
    fx = rel_pos(root, bs["wheel_front_left"], bs["chassis"])[0]
    rx = rel_pos(root, bs["wheel_rear_left_inner"], bs["chassis"])[0]
    assert fx - rx == pytest.approx(6.4, rel=TOL)
    fy = [rel_pos(root, bs[w], bs["chassis"])[1] for w in FRONT]
    assert abs(fy[0] - fy[1]) == pytest.approx(5.6, rel=TOL)


@pytest.mark.req("FR-014-05")
def test_generation_is_deterministic_and_the_writer_matches_it(tmp_path: Path) -> None:
    assert truck_mjcf(VALID) == truck_mjcf(copy.deepcopy(VALID))
    path = write_truck_mjcf(VALID, tmp_path / "out")
    assert path == tmp_path / "out" / f"{VALID['id']}.xml"
    data = path.read_bytes()
    assert b"\r" not in data
    assert data.decode("utf-8") == truck_mjcf(VALID)


# ------------------------------------------------------------------------------------------------ FR-014-07
def corpus() -> list:
    index = json.loads((EXAMPLES / "index.json").read_text(encoding="utf-8"))["examples"]
    out = []
    for entry in index:
        if entry["schema"] != "machine-params.schema.json" or entry["valid"]:
            continue
        doc = json.loads((EXAMPLES / entry["file"]).read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("kind") != "excavator":
            out.append(pytest.param(entry["file"], entry["pointer"], entry["keyword"], doc, id=entry["file"]))
    return out


@pytest.mark.req("FR-014-07")
def test_the_spec_corpus_holds_the_truck_hostile_examples_this_test_relies_on() -> None:
    files = {p.values[0] for p in corpus()}
    assert {
        "machine-params.hostile-non-positive-mass.json", "machine-params.hostile-url-scheme.json",
        "machine-params.hostile-absolute-path.json", "machine-params.hostile-path-traversal.json",
        "machine-params.hostile-unknown-field.json", "machine-params.hostile-unknown-enum.json",
    } <= files  # fmt: skip


@pytest.mark.req("FR-014-07")
@pytest.mark.parametrize(("file", "pointer", "keyword", "doc"), corpus())
def test_every_hostile_truck_example_of_the_spec_raises_and_writes_nothing(
    file, pointer, keyword, doc, tmp_path: Path
) -> None:
    out = tmp_path / "model"
    # an unknown key at the root has the empty pointer: the message then names the key itself
    # an unknown key or a missing required member at the root has the empty pointer: the message then names that member
    named = (
        ({k for k in doc if k not in VALID} | {k for k in VALID if k not in doc}) if isinstance(doc, dict) else set()
    )
    pattern = pointer if pointer else "|".join(sorted(named)) if named else r".+"
    with pytest.raises(ValueError, match=pattern):
        write_truck_mjcf(doc, out)
    assert not out.exists() or list(out.rglob("*")) == []
    with pytest.raises(ValueError, match=pattern):
        truck_mjcf(doc)


def mutate(path: list, value) -> dict:
    doc = copy.deepcopy(VALID)
    node = doc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return doc


HAND_BUILT = [
    (["empty_mass_kg"], math.nan, "/empty_mass_kg"),
    (["empty_mass_kg"], -1.0, "/empty_mass_kg"),
    (["rated_payload_kg"], 0.0, "/rated_payload_kg"),
    (["wheel_mass_kg"], math.inf, "/wheel_mass_kg"),
    (["wheel_mass_kg"], 0.0, "/wheel_mass_kg"),
    (["wheelbase_m"], 0.0, "/wheelbase_m"),
    (["wheelbase_m"], math.nan, "/wheelbase_m"),
    (["track_width_m"], -5.0, "/track_width_m"),
    (["wheel_radius_m"], math.inf, "/wheel_radius_m"),
    (["wheel_width_m"], 0.0, "/wheel_width_m"),
    (["chassis_length_m"], -12.0, "/chassis_length_m"),
    (["yaw_inertia_kg_m2"], 0.0, "/yaw_inertia_kg_m2"),
    (["max_steer_deg"], 0.0, "/max_steer_deg"),
    (["max_rimpull_n"], -1.0, "/max_rimpull_n"),
    (["max_retarder_n"], 0.0, "/max_retarder_n"),
    (["meshes", "chassis"], "../outside/chassis.obj", "/meshes/chassis"),
    (["meshes", "wheel"], "/etc/wheel.obj", "/meshes/wheel"),
    (["meshes", "wheel"], "C:\\models\\wheel.obj", "/meshes/wheel"),
    (["meshes", "chassis"], "https://example.org/chassis.obj", "/meshes/chassis"),
    (["meshes", "chassis"], "file:///tmp/chassis.obj", "/meshes/chassis"),
    (["meshes", "wheel"], "meshes/../../wheel.obj", "/meshes/wheel"),
    (["kind"], "excavator", "/kind"),
    (["zz_unknown_key"], 1.0, "zz_unknown_key"),
    (["empty_mass_kg"], 20_000, "empty_mass_kg|wheel_mass_kg"),  # 6 wheels of 4,000 kg leave a negative chassis mass
    (["cg_to_front_axle_m"], 5.3, "/cg_to_front_axle_m"),  # the front axle is not ahead of the rear axle
    (["cg_to_front_axle_m"], 6.0, "/cg_to_front_axle_m"),
]


@pytest.mark.req("FR-014-07")
@pytest.mark.parametrize(
    ("path", "value", "pointer"), HAND_BUILT, ids=[f"{'/'.join(map(str, p))}={v}" for p, v, _ in HAND_BUILT]
)
def test_hand_built_invalid_truck_files_raise_naming_the_json_pointer_and_write_nothing(
    path, value, pointer, tmp_path: Path
) -> None:
    doc = mutate(path, value)
    out = tmp_path / "model"
    with pytest.raises(ValueError, match=pointer):
        write_truck_mjcf(doc, out)
    assert not out.exists() or list(out.rglob("*")) == []
    with pytest.raises(ValueError, match=pointer):
        truck_mjcf(doc)


@pytest.mark.req("FR-014-07")
@pytest.mark.parametrize("missing", ["empty_mass_kg", "wheelbase_m", "track_width_m", "provenance", "sources"])
def test_a_missing_required_member_is_rejected_naming_it(missing, tmp_path: Path) -> None:
    doc = copy.deepcopy(VALID)
    del doc[missing]
    with pytest.raises(ValueError, match=missing):
        write_truck_mjcf(doc, tmp_path / "model")
    assert not (tmp_path / "model").exists()


@pytest.mark.req("FR-014-07")
@pytest.mark.parametrize(
    "bad", [None, [], "haul-truck", 3.5, [VALID]], ids=["none", "list", "str", "float", "list-of-doc"]
)
def test_a_document_that_is_not_an_object_is_rejected(bad, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r".+"):
        write_truck_mjcf(bad, tmp_path / "model")
    assert not (tmp_path / "model").exists()


@pytest.mark.req("FR-014-07")
def test_unicode_in_a_text_field_is_escaped_and_a_control_character_in_the_id_is_rejected(tmp_path: Path) -> None:
    doc = copy.deepcopy(VALID)
    doc["name"] = "Cami\u00f3n <220 t> & \u4e2d\u6587"
    ET.parse(write_truck_mjcf(doc, tmp_path / "ok"))
    bad = copy.deepcopy(VALID)
    bad["id"] = "bad id\n<x>"
    with pytest.raises(ValueError, match="/id"):
        write_truck_mjcf(bad, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
