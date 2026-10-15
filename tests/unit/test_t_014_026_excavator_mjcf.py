# ruff: noqa: E501
"""T-014-026: excavator MJCF generator and hostile parameter files.

Requirements: FR-014-06, FR-014-07 (excavator side).

Spec: specs/014-robot-learning/spec.md FR-014-06: "The excavator generator shall write an MJCF model with four revolute joints
(swing, boom, stick, bucket) whose limits, torque limits tau_max, bucket width w and rated heaped volume V_h equal the
parameter file exactly." FR-014-07: "If a machine parameter file is invalid against its schema (non-finite or non-positive mass
or dimension, joint lower limit >= upper limit, torque limit <= 0, unknown key, or a mesh reference outside the generated asset
folder) then the generator shall raise ValueError naming the JSON pointer and write no model."

Oracle: the parameter file itself (`specs/014-robot-learning/contracts/examples/machine-params.valid-excavator.json`, a spec
example) compared with the XML parsed by the standard library (`xml.etree.ElementTree`): the test reads back what the
generator wrote and compares it to the numbers in the file; the hostile corpus is the spec's example index
(`index.json`, entries of `machine-params.schema.json` with `valid: false`, each with its JSON pointer) plus hand-built
mutations of the valid file. No MuJoCo is needed (the compile check is the GPU-lane task T-014-062).

Expected API of the implementation (module `pitstudio.robots.machines`):
    excavator_mjcf(params) -> str
        MJCF text for a machine-params document of kind "excavator" (a dict as loaded from JSON). Deterministic: the same
        document gives the same text. The model has the root element <mujoco model="<id>">; exactly four <joint> elements,
        named swing, boom, stick and bucket, each a hinge (type="hinge" or no type attribute, MuJoCo's default) with
        range="<lower> <upper>" equal to the file's lower_deg and upper_deg in the unit of <compiler angle="..."> (degree is
        the default when the attribute is absent); the torque limit of each joint is carried by the joint attribute
        actuatorfrcrange="-<tau> <tau>" or by a <motor joint="<name>" forcerange="-<tau> <tau>"> actuator, equal to
        torque_max_n_m; <custom> holds <numeric name="bucket_width_m" data="<w>"/> and
        <numeric name="heaped_volume_m3" data="<V_h>"/>.
    write_excavator_mjcf(params, out_dir) -> pathlib.Path
        validates first, then writes <out_dir>/<id>.xml (UTF-8, LF) holding exactly excavator_mjcf(params) and returns its
        path; on any invalid input nothing is created under out_dir.
    Both raise ValueError whose message contains the JSON pointer of the first offending member (for example
    "/joints/boom/torque_max_n_m", "/boom_pivot_m", "/kind"); for an unknown key the pointer is "/<key>"; for a document that
    is not a JSON object the message is non-empty.
"""

from __future__ import annotations

import copy
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pitstudio.robots.machines import excavator_mjcf, write_excavator_mjcf

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
JOINTS = ("swing", "boom", "stick", "bucket")


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


VALID = load("machine-params.valid-excavator.json")


def parse(text: str) -> ET.Element:
    return ET.fromstring(text)


def angle_factor(root: ET.Element) -> float:
    """Degrees per MJCF angle unit (1 for degree, 180/pi for radian)."""
    compiler = root.find("compiler")
    unit = compiler.get("angle", "degree") if compiler is not None else "degree"
    return 1.0 if unit == "degree" else 180.0 / math.pi


def joints(root: ET.Element) -> dict[str, ET.Element]:
    return {j.get("name"): j for j in root.iter("joint")}


def torque_limit(root: ET.Element, name: str) -> float:
    joint = joints(root)[name]
    if joint.get("actuatorfrcrange"):
        lo, hi = (float(v) for v in joint.get("actuatorfrcrange").split())
        assert lo == -hi
        return hi
    for motor in root.iter("motor"):
        if motor.get("joint") == name and motor.get("forcerange"):
            lo, hi = (float(v) for v in motor.get("forcerange").split())
            assert lo == -hi
            return hi
    raise AssertionError(f"no torque limit found for joint {name}")


def numeric(root: ET.Element, name: str) -> float:
    for n in root.iter("numeric"):
        if n.get("name") == name:
            return float(n.get("data"))
    raise AssertionError(f"no <numeric name={name!r}> in the model")


# ------------------------------------------------------------------------------------------------ FR-014-06
@pytest.mark.req("FR-014-06")
def test_the_model_has_four_hinge_joints_named_swing_boom_stick_bucket() -> None:
    root = parse(excavator_mjcf(VALID))
    assert root.tag == "mujoco"
    assert root.get("model") == VALID["id"]
    found = list(root.iter("joint"))
    assert sorted(j.get("name") for j in found) == sorted(JOINTS)
    assert len(found) == 4
    assert all(j.get("type", "hinge") == "hinge" for j in found)


@pytest.mark.req("FR-014-06")
@pytest.mark.parametrize("name", JOINTS)
def test_joint_limits_equal_the_parameter_file_exactly(name) -> None:
    root = parse(excavator_mjcf(VALID))
    lo, hi = (float(v) * angle_factor(root) for v in joints(root)[name].get("range").split())
    assert lo == pytest.approx(VALID["joints"][name]["lower_deg"], rel=1e-12, abs=1e-12)
    assert hi == pytest.approx(VALID["joints"][name]["upper_deg"], rel=1e-12, abs=1e-12)


@pytest.mark.req("FR-014-06")
@pytest.mark.parametrize("name", JOINTS)
def test_torque_limits_equal_the_parameter_file_exactly(name) -> None:
    root = parse(excavator_mjcf(VALID))
    assert torque_limit(root, name) == VALID["joints"][name]["torque_max_n_m"]


@pytest.mark.req("FR-014-06")
def test_bucket_width_and_rated_heaped_volume_equal_the_parameter_file_exactly() -> None:
    root = parse(excavator_mjcf(VALID))
    assert numeric(root, "bucket_width_m") == VALID["bucket_width_m"]
    assert numeric(root, "heaped_volume_m3") == VALID["heaped_volume_m3"]


@pytest.mark.req("FR-014-06")
def test_different_parameter_values_flow_through_to_the_model() -> None:
    doc = copy.deepcopy(VALID)
    doc["id"] = "variant-excavator"
    doc["bucket_width_m"] = 2.37
    doc["heaped_volume_m3"] = 4.25
    doc["joints"]["boom"]["lower_deg"] = -33.5
    doc["joints"]["boom"]["upper_deg"] = 71.25
    doc["joints"]["stick"]["torque_max_n_m"] = 333_333.5
    root = parse(excavator_mjcf(doc))
    assert root.get("model") == "variant-excavator"
    assert numeric(root, "bucket_width_m") == 2.37
    assert numeric(root, "heaped_volume_m3") == 4.25
    lo, hi = (float(v) * angle_factor(root) for v in joints(root)["boom"].get("range").split())
    assert (lo, hi) == pytest.approx((-33.5, 71.25), rel=1e-12)
    assert torque_limit(root, "stick") == 333_333.5


@pytest.mark.req("FR-014-06")
def test_generation_is_deterministic_and_does_not_modify_the_input() -> None:
    doc = copy.deepcopy(VALID)
    first = excavator_mjcf(doc)
    assert excavator_mjcf(doc) == first
    assert doc == VALID


@pytest.mark.req("FR-014-06")
def test_the_writer_writes_the_same_text_to_a_file_named_after_the_id(tmp_path: Path) -> None:
    path = write_excavator_mjcf(VALID, tmp_path / "out")
    assert path == tmp_path / "out" / f"{VALID['id']}.xml"
    data = path.read_bytes()
    assert b"\r" not in data
    assert data.decode("utf-8") == excavator_mjcf(VALID)
    ET.parse(path)  # well-formed XML


# ------------------------------------------------------------------------------------------------ FR-014-07
def hostile_corpus_entries() -> list[dict]:
    index = json.loads((EXAMPLES / "index.json").read_text(encoding="utf-8"))["examples"]
    out = []
    for entry in index:
        if entry["schema"] != "machine-params.schema.json" or entry["valid"]:
            continue
        doc = json.loads((EXAMPLES / entry["file"]).read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("kind") == "excavator":
            out.append(pytest.param(entry["file"], entry["pointer"], doc, id=entry["file"]))
    return out


@pytest.mark.req("FR-014-07")
def test_the_spec_corpus_holds_the_excavator_hostile_examples_this_test_relies_on() -> None:
    files = [p.values[0] for p in hostile_corpus_entries()]
    assert "machine-params.hostile-non-positive-torque.json" in files
    assert "machine-params.hostile-wrong-shape.json" in files


@pytest.mark.req("FR-014-07")
@pytest.mark.parametrize(("file", "pointer", "doc"), hostile_corpus_entries())
def test_every_hostile_excavator_example_of_the_spec_raises_at_its_pointer_and_writes_nothing(
    file, pointer, doc, tmp_path: Path
) -> None:
    out = tmp_path / "model"
    with pytest.raises(ValueError, match=pointer):
        write_excavator_mjcf(doc, out)
    assert not out.exists() or list(out.rglob("*")) == []
    with pytest.raises(ValueError, match=pointer):
        excavator_mjcf(doc)


def mutate(path: list[str | int], value) -> dict:
    doc = copy.deepcopy(VALID)
    node = doc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return doc


HAND_BUILT = [
    (["operating_mass_kg"], math.nan, "/operating_mass_kg"),
    (["operating_mass_kg"], -1.0, "/operating_mass_kg"),
    (["base_mass_kg"], 0.0, "/base_mass_kg"),
    (["bucket_width_m"], math.inf, "/bucket_width_m"),
    (["bucket_width_m"], 0.0, "/bucket_width_m"),
    (["heaped_volume_m3"], -0.5, "/heaped_volume_m3"),
    (["heaped_volume_m3"], math.nan, "/heaped_volume_m3"),
    (["links", "boom", "length_m"], 0.0, "/links/boom/length_m"),
    (["links", "stick", "mass_kg"], -3.0, "/links/stick/mass_kg"),
    (["joints", "boom", "torque_max_n_m"], 0.0, "/joints/boom/torque_max_n_m"),
    (["joints", "swing", "torque_max_n_m"], -120_000.0, "/joints/swing/torque_max_n_m"),
    (["joints", "bucket", "torque_max_n_m"], math.nan, "/joints/bucket/torque_max_n_m"),
    (["joints", "stick", "upper_deg"], -150.0, "/joints/stick"),  # lower_deg == upper_deg
    (["joints", "stick", "upper_deg"], -170.0, "/joints/stick"),  # lower_deg > upper_deg
    (["joints", "swing", "lower_deg"], 180.0, "/joints/swing"),
    (["joints", "boom", "lower_deg"], math.nan, "/joints/boom"),
    (["boom_pivot_m"], [0.2], "/boom_pivot_m"),
    (["kind"], "haul-truck", "/kind"),
    (["kind"], "dozer", "/kind"),
    (["zz_unknown_key"], 1.0, "zz_unknown_key"),
]


@pytest.mark.req("FR-014-07")
@pytest.mark.parametrize(
    ("path", "value", "pointer"), HAND_BUILT, ids=[f"{'/'.join(map(str, p))}={v}" for p, v, _ in HAND_BUILT]
)
def test_hand_built_invalid_excavator_files_raise_naming_the_json_pointer_and_write_nothing(
    path, value, pointer, tmp_path: Path
) -> None:
    doc = mutate(path, value)
    out = tmp_path / "model"
    with pytest.raises(ValueError, match=pointer):
        write_excavator_mjcf(doc, out)
    assert not out.exists() or list(out.rglob("*")) == []
    with pytest.raises(ValueError, match=pointer):
        excavator_mjcf(doc)


@pytest.mark.req("FR-014-07")
@pytest.mark.parametrize("missing", ["bucket_width_m", "heaped_volume_m3", "joints", "links", "boom_pivot_m"])
def test_a_missing_required_member_is_rejected_naming_it(missing, tmp_path: Path) -> None:
    doc = copy.deepcopy(VALID)
    del doc[missing]
    with pytest.raises(ValueError, match=missing):
        write_excavator_mjcf(doc, tmp_path / "model")


@pytest.mark.req("FR-014-07")
@pytest.mark.parametrize("bad", [None, [], "excavator", 7, [VALID]], ids=["none", "list", "str", "int", "list-of-doc"])
def test_a_document_that_is_not_an_object_is_rejected(bad, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r".+"):
        write_excavator_mjcf(bad, tmp_path / "model")
    assert not (tmp_path / "model").exists()


@pytest.mark.req("FR-014-07")
def test_unicode_and_control_characters_in_a_text_field_do_not_break_the_xml(tmp_path: Path) -> None:
    doc = copy.deepcopy(VALID)
    doc["name"] = "Excavadora <30 t> & ñandú 中文"
    path = write_excavator_mjcf(doc, tmp_path / "model")
    ET.parse(path)  # the name is escaped or omitted, never emitted raw
    bad = copy.deepcopy(VALID)
    bad["id"] = "bad id\n<x>"
    with pytest.raises(ValueError, match="/id"):
        write_excavator_mjcf(bad, tmp_path / "model2")
    assert not (tmp_path / "model2").exists()
