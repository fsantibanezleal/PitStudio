# SPDX-License-Identifier: Apache-2.0
"""MJCF generators for the haul truck and the excavator (FR-014-05, FR-014-06, FR-014-07).

The machine parameter file (``contracts/machine-params.schema.json``) is validated first: any violation raises
``ValueError`` whose message holds the JSON pointer of the offending member, and nothing is written. The model text is a
pure function of the document. ``write_*`` also writes the procedural mesh assets (a box and a cylinder) that the
document's ``meshes`` member names, inside the output folder, so that the model compiles.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from pitstudio.contracts.validate import CONTRACTS_DIR

__all__ = ["excavator_mjcf", "truck_mjcf", "validate_machine", "write_excavator_mjcf", "write_truck_mjcf"]

_MAX_LISTED = 12
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_QUOTED = re.compile(r"'([^']+)'")
JOINTS = ("swing", "boom", "stick", "bucket")
_WHEELS_FRONT = ("wheel_front_left", "wheel_front_right")
_WHEELS_REAR = ("wheel_rear_left_inner", "wheel_rear_left_outer", "wheel_rear_right_inner", "wheel_rear_right_outer")
_KIND_DEF = {"haul-truck": "haul_truck", "excavator": "excavator"}


@cache
def _registry() -> Registry:
    resources = []
    for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


@cache
def _validator(kind: str) -> Draft202012Validator:
    schema = json.loads((CONTRACTS_DIR / "machine-params.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": f"{schema['$id']}#/$defs/{_KIND_DEF[kind]}"}, registry=_registry())


def _pointer(path: Any) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in path]
    return "/" + "/".join(parts) if parts else ""


def _non_finite(node: Any, path: tuple[Any, ...], out: list[str]) -> None:
    if isinstance(node, float) and not math.isfinite(node):
        out.append(f"{_pointer(path)}: must be finite")
    elif isinstance(node, Mapping):
        for key, value in node.items():
            _non_finite(value, (*path, key), out)
    elif isinstance(node, list | tuple):
        for i, value in enumerate(node):
            _non_finite(value, (*path, i), out)


def validate_machine(doc: Any, kind: str) -> None:
    """Raise ValueError naming the JSON pointer of each offending member of a machine parameter document."""
    if not isinstance(doc, Mapping):
        raise ValueError(f"machine parameters must be a JSON object, got {type(doc).__name__}")
    if doc.get("kind") != kind:
        raise ValueError(f"/kind: expected {kind!r}, got {doc.get('kind')!r}")
    problems: list[str] = []
    _non_finite(doc, (), problems)
    if not problems:
        for error in sorted(_validator(kind).iter_errors(dict(doc)), key=lambda e: [str(p) for p in e.absolute_path]):
            base = _pointer(error.absolute_path)
            if error.validator in ("required", "additionalProperties"):
                for name in _QUOTED.findall(error.message):
                    problems.append(f"{base}/{name}: {error.message}")
            else:
                problems.append(f"{base or '/'}: {error.message}")
    if not problems:
        problems.extend(_semantic(doc, kind))
    if problems:
        shown = [p[:200] for p in problems[:_MAX_LISTED]]
        raise ValueError("invalid machine parameters: " + "; ".join(shown))


def _semantic(doc: Mapping[str, Any], kind: str) -> list[str]:
    out: list[str] = []
    if kind == "excavator":
        for name in JOINTS:
            joint = doc["joints"][name]
            if not joint["lower_deg"] < joint["upper_deg"]:
                out.append(f"/joints/{name}: lower_deg must be below upper_deg")
    else:
        if not doc["empty_mass_kg"] > 6.0 * doc["wheel_mass_kg"]:
            out.append("/empty_mass_kg: must exceed six times /wheel_mass_kg (the chassis mass would not be positive)")
        if not doc["cg_to_front_axle_m"] < doc["wheelbase_m"]:
            out.append("/cg_to_front_axle_m: the front axle must be ahead of the rear axle (below /wheelbase_m)")
    return out


def _f(x: float) -> str:
    return repr(float(x))


def _attr(text: str) -> str:
    return quoteattr(_CONTROL.sub(" ", text))


def _name_element(doc: Mapping[str, Any]) -> str:
    return f'    <text name="display_name" data={_attr(str(doc["name"]))}/>\n'


# ------------------------------------------------------------------------------------------------------- truck
def truck_mjcf(params: Mapping[str, Any]) -> str:
    """MJCF text of the six-wheel haul truck (x forward, y left, z up, origin at the centre of gravity)."""
    validate_machine(params, "haul-truck")
    p = params
    wheel_m = float(p["wheel_mass_kg"])
    chassis_m = float(p["empty_mass_kg"]) - 6.0 * wheel_m
    r, ww = float(p["wheel_radius_m"]), float(p["wheel_width_m"])
    track, base = float(p["track_width_m"]), float(p["wheelbase_m"])
    x_front = float(p["cg_to_front_axle_m"])
    x_rear = x_front - base
    z_axle = r - float(p["cg_height_m"])
    cl, cw, ch = (float(p[k]) for k in ("chassis_length_m", "chassis_width_m", "chassis_height_m"))
    ixx = chassis_m * (cw * cw + ch * ch) / 12.0
    iyy = chassis_m * (cl * cl + ch * ch) / 12.0
    izz = float(p["yaw_inertia_kg_m2"])
    wi_t = wheel_m * (3.0 * r * r + ww * ww) / 12.0
    wi_a = 0.5 * wheel_m * r * r
    steer = float(p["max_steer_deg"])

    def wheel(name: str, y: float, x: float = 0.0) -> str:
        return (
            f'        <body name="{name}" pos="{_f(x)} {_f(y)} 0.0">\n'
            f'          <inertial pos="0 0 0" mass="{_f(wheel_m)}" diaginertia="{_f(wi_t)} {_f(wi_a)} {_f(wi_t)}"/>\n'
            f'          <joint name="{name}_spin" type="hinge" axis="0 1 0"/>\n'
            f'          <geom type="cylinder" size="{_f(r)} {_f(ww / 2.0)}" euler="90 0 0" friction="1.0 0.005 0.0001"/>\n'
            "        </body>\n"
        )

    wheels_front = wheel("wheel_front_left", track / 2.0) + wheel("wheel_front_right", -track / 2.0)
    wheels_rear = ""
    for side, sign in (("left", 1.0), ("right", -1.0)):
        for slot, offset in (("inner", -ww / 2.0), ("outer", ww / 2.0)):
            wheels_rear += wheel(f"wheel_rear_{side}_{slot}", sign * (track / 2.0 + offset))
    meshes = p.get("meshes") or {}
    assets = ""
    if meshes:
        assets = "  <asset>\n" + "".join(
            f'    <mesh name="{part}" file={_attr(str(meshes[part]))}/>\n' for part in sorted(meshes)
        ) + "  </asset>\n"
    motors = "".join(
        f'    <motor name="drive_{w}" joint="{w}_spin" gear="{_f(float(p["max_rimpull_n"]) * r / 4.0)}" ctrlrange="-1 1"/>\n'
        for w in _WHEELS_REAR
    )
    return (
        f"<mujoco model={_attr(str(p['id']))}>\n"
        '  <compiler angle="degree" meshdir="." autolimits="true"/>\n'
        '  <option timestep="0.005" integrator="implicitfast"/>\n'
        f"{assets}"
        "  <worldbody>\n"
        f'    <body name="chassis" pos="0 0 {_f(float(p["cg_height_m"]))}">\n'
        f'      <inertial pos="0 0 0" mass="{_f(chassis_m)}" diaginertia="{_f(ixx)} {_f(iyy)} {_f(izz)}"/>\n'
        f'      <geom type="box" size="{_f(cl / 2.0)} {_f(cw / 2.0)} {_f(ch / 2.0)}"/>\n'
        f'      <body name="front_axle" pos="{_f(x_front)} 0.0 {_f(z_axle)}">\n'
        '        <inertial pos="0 0 0" mass="1.0" diaginertia="1 1 1"/>\n'
        f'        <joint name="steer" type="hinge" axis="0 0 1" range="{_f(-steer)} {_f(steer)}"/>\n'
        f"{wheels_front}"
        "      </body>\n"
        f'      <body name="rear_axle" pos="{_f(x_rear)} 0.0 {_f(z_axle)}">\n'
        '        <inertial pos="0 0 0" mass="1.0" diaginertia="1 1 1"/>\n'
        f"{wheels_rear}"
        "      </body>\n"
        "    </body>\n"
        "  </worldbody>\n"
        "  <actuator>\n"
        f"{motors}"
        "  </actuator>\n"
        "  <custom>\n"
        f"{_name_element(p)}"
        f'    <numeric name="max_rimpull_n" data="{_f(float(p["max_rimpull_n"]))}"/>\n'
        f'    <numeric name="max_retarder_n" data="{_f(float(p["max_retarder_n"]))}"/>\n'
        f'    <numeric name="max_steer_rate_deg_per_s" data="{_f(float(p["max_steer_rate_deg_per_s"]))}"/>\n'
        "  </custom>\n"
        "</mujoco>\n"
    )


# --------------------------------------------------------------------------------------------------- excavator
def excavator_mjcf(params: Mapping[str, Any]) -> str:
    """MJCF text of the excavator: swing, boom, stick and bucket hinges, torque limits and the bucket numerics."""
    validate_machine(params, "excavator")
    p = params
    joints = p["joints"]
    links = p["links"]
    pivot_x, pivot_z = (float(v) for v in p["boom_pivot_m"])

    def joint(name: str, axis: str) -> str:
        j = joints[name]
        tau = _f(j["torque_max_n_m"])
        return (
            f'<joint name="{name}" type="hinge" axis="{axis}" range="{_f(j["lower_deg"])} {_f(j["upper_deg"])}" '
            f'actuatorfrclimited="true" actuatorfrcrange="-{tau} {tau}"/>'
        )

    def link(name: str, parent_len: float, axis: str, nxt: str) -> str:
        length, mass = float(links[name]["length_m"]), float(links[name]["mass_kg"])
        inertia = mass * length * length / 12.0
        return (
            f'        <body name="{name}_link" pos="{_f(parent_len)} 0.0 0.0">\n'
            f'          <inertial pos="{_f(length / 2.0)} 0 0" mass="{_f(mass)}" diaginertia="{_f(inertia)} {_f(inertia)} 1.0"/>\n'
            f"          {joint(name, axis)}\n"
            f'          <geom type="capsule" fromto="0 0 0 {_f(length)} 0 0" size="0.15"/>\n'
            f"{nxt}"
            f"        </body>\n"
        )

    bucket_w = float(p["bucket_width_m"])
    bucket_len = float(links["bucket"]["length_m"])
    bucket_mass = float(links["bucket"]["mass_kg"])
    bucket_i = bucket_mass * bucket_len * bucket_len / 12.0
    bucket = (
        f'          <body name="bucket_link" pos="{_f(float(links["stick"]["length_m"]))} 0.0 0.0">\n'
        f'            <inertial pos="{_f(bucket_len / 2.0)} 0 0" mass="{_f(bucket_mass)}" '
        f'diaginertia="{_f(bucket_i)} {_f(bucket_i)} 1.0"/>\n'
        f"            {joint('bucket', '0 1 0')}\n"
        f'            <geom type="box" pos="{_f(bucket_len / 2.0)} 0 0" size="{_f(bucket_len / 2.0)} {_f(bucket_w / 2.0)} 0.1"/>\n'
        f'            <site name="bucket_tip" pos="{_f(bucket_len)} 0 0"/>\n'
        "          </body>\n"
    )
    stick_len = float(links["stick"]["length_m"])
    stick_mass = float(links["stick"]["mass_kg"])
    stick_i = stick_mass * stick_len * stick_len / 12.0
    stick = (
        f'        <body name="stick_link" pos="{_f(float(links["boom"]["length_m"]))} 0.0 0.0">\n'
        f'          <inertial pos="{_f(stick_len / 2.0)} 0 0" mass="{_f(stick_mass)}" diaginertia="{_f(stick_i)} {_f(stick_i)} 1.0"/>\n'
        f"          {joint('stick', '0 1 0')}\n"
        f'          <geom type="capsule" fromto="0 0 0 {_f(stick_len)} 0 0" size="0.12"/>\n'
        f"{bucket}"
        "        </body>\n"
    )
    boom_len = float(links["boom"]["length_m"])
    boom_mass = float(links["boom"]["mass_kg"])
    boom_i = boom_mass * boom_len * boom_len / 12.0
    boom = (
        f'      <body name="boom_link" pos="{_f(pivot_x)} 0.0 {_f(pivot_z)}">\n'
        f'        <inertial pos="{_f(boom_len / 2.0)} 0 0" mass="{_f(boom_mass)}" diaginertia="{_f(boom_i)} {_f(boom_i)} 1.0"/>\n'
        f"        {joint('boom', '0 1 0')}\n"
        f'        <geom type="capsule" fromto="0 0 0 {_f(boom_len)} 0 0" size="0.18"/>\n'
        f"{stick}"
        "      </body>\n"
    )
    base_mass = float(p["base_mass_kg"])
    base_i = base_mass / 12.0 * 16.0
    motors = "".join(
        f'    <motor name="drive_{name}" joint="{name}" gear="{_f(joints[name]["torque_max_n_m"])}" ctrlrange="-1 1"/>\n'
        for name in JOINTS
    )
    return (
        f"<mujoco model={_attr(str(p['id']))}>\n"
        '  <compiler angle="degree" autolimits="true"/>\n'
        '  <option timestep="0.005" integrator="implicitfast"/>\n'
        "  <worldbody>\n"
        '    <body name="base" pos="0 0 0">\n'
        f'      <inertial pos="0 0 0.8" mass="{_f(base_mass)}" diaginertia="{_f(base_i)} {_f(base_i)} {_f(base_i)}"/>\n'
        f'      <geom type="box" pos="0 0 0.8" size="2.0 1.5 0.8"/>\n'
        f'      <body name="turret" pos="0 0 1.6">\n'
        '        <inertial pos="0 0 0" mass="1.0" diaginertia="1 1 1"/>\n'
        f"        {joint('swing', '0 0 1')}\n"
        f"{boom}"
        "      </body>\n"
        "    </body>\n"
        "  </worldbody>\n"
        "  <actuator>\n"
        f"{motors}"
        "  </actuator>\n"
        "  <custom>\n"
        f"{_name_element(p)}"
        f'    <numeric name="bucket_width_m" data="{_f(bucket_w)}"/>\n'
        f'    <numeric name="heaped_volume_m3" data="{_f(float(p["heaped_volume_m3"]))}"/>\n'
        "  </custom>\n"
        "</mujoco>\n"
    )


# ------------------------------------------------------------------------------------------------- mesh assets
def _box_obj(sx: float, sy: float, sz: float) -> str:
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    verts = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz), (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    faces = [
        (1, 3, 2), (1, 4, 3),  # bottom (-z)
        (5, 6, 7), (5, 7, 8),  # top (+z)
        (1, 2, 6), (1, 6, 5),  # -y
        (3, 4, 8), (3, 8, 7),  # +y
        (2, 3, 7), (2, 7, 6),  # +x
        (4, 1, 5), (4, 5, 8),  # -x
    ]  # fmt: skip
    return _obj(verts, faces)


def _cylinder_obj(radius: float, width: float, segments: int = 24) -> str:
    hw = width / 2.0
    verts = []
    for sign in (-1.0, 1.0):
        for k in range(segments):
            a = 2.0 * math.pi * k / segments
            verts.append((radius * math.cos(a), sign * hw, radius * math.sin(a)))
    verts.append((0.0, -hw, 0.0))
    verts.append((0.0, hw, 0.0))
    c_lo, c_hi = 2 * segments + 1, 2 * segments + 2
    faces = []
    for k in range(segments):
        n = (k + 1) % segments
        a0, a1, b0, b1 = k + 1, n + 1, segments + k + 1, segments + n + 1
        faces += [(a0, a1, b1), (a0, b1, b0)]  # side (outward)
        faces.append((c_lo, a1, a0))  # -y cap
        faces.append((c_hi, b0, b1))  # +y cap
    return _obj(verts, faces)


def _obj(verts: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]) -> str:
    lines = [f"v {_f(x)} {_f(y)} {_f(z)}" for x, y, z in verts] + [f"f {a} {b} {c}" for a, b, c in faces]
    return "\n".join(lines) + "\n"


def _write(text: str, out_dir: Path, name: str, meshes: Mapping[str, str], mesh_text: Mapping[str, str]) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for part, rel in meshes.items():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(mesh_text.get(part, mesh_text["chassis"]).encode("utf-8"))
    path = out / f"{name}.xml"
    path.write_bytes(text.encode("utf-8"))
    return path


def write_truck_mjcf(params: Mapping[str, Any], out_dir: Path | str) -> Path:
    """Validate, then write ``<out_dir>/<id>.xml`` and the procedural meshes it names."""
    text = truck_mjcf(params)
    meshes = params.get("meshes") or {}
    mesh_text = {
        "chassis": _box_obj(params["chassis_length_m"], params["chassis_width_m"], params["chassis_height_m"]),
        "wheel": _cylinder_obj(params["wheel_radius_m"], params["wheel_width_m"]),
    }
    return _write(text, Path(out_dir), params["id"], meshes, mesh_text)


def write_excavator_mjcf(params: Mapping[str, Any], out_dir: Path | str) -> Path:
    """Validate, then write ``<out_dir>/<id>.xml`` (and any mesh the document names, as a unit box)."""
    text = excavator_mjcf(params)
    meshes = params.get("meshes") or {}
    mesh_text = {"chassis": _box_obj(1.0, 1.0, 1.0)}
    return _write(text, Path(out_dir), params["id"], meshes, mesh_text)
