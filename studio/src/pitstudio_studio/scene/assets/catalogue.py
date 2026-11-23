# ruff: noqa: E501
"""The asset specification of the SDG scene (DC-004-01 `assets`, `parts`, `fleet`, `labels`) with a citation per value.

The haul truck follows the Caterpillar 793F specification sheet (nominal payload 226.8 t, chassis 124,586 kg, body
26,862 kg and up, dimensions table with the 162 m3 HP body, tyres 40.00R57); the rope shovel the Cat 7495 HD product page
(dipper 32 m3, working weight 1,295,777 kg, crawler overall width 10 m, upper works 13.5 m, cutting height 14.9 m);
the light vehicle the Toyota Land Cruiser 79 single cab sheet (5,235 x 1,800 x 1,975 mm, wheelbase 3,180 mm, tyres
225/95R16); the person an adult mannequin of stature 1.75 m. A value that the source does not give is written `derived`
(computed from a cited value) or `design` (an assumption of this repository) in its citation. Part dimensions are the
bounding boxes of the parametrised geometry of `machines`; the asset dimensions are the bounding boxes of all parts, which
is the footprint the parameter table places (`ENVELOPES`).
"""

from __future__ import annotations

from typing import Any

from pitstudio_studio.scene.assets import machines
from pitstudio_studio.scene.assets.geometry import bounds

ASSET_IDS = {
    "haul_truck": "haul-truck-220t",
    "shovel": "rope-shovel-32m3",
    "light_vehicle": "light-vehicle-4x4",
    "person": "person-mannequin",
}
CLASSES = [
    "terrain",
    "bench",
    "berm",
    "ramp",
    "windrow",
    "haul_road",
    "haul_truck",
    "shovel",
    "light_vehicle",
    "person",
]
PART_VOCABULARY = [
    "chassis", "cab", "dump_body", "axle", "wheel", "track", "undercarriage", "house", "boom", "stick", "dipper",
]  # fmt: skip
FLEET = {"haul_truck": 3, "shovel": 1, "light_vehicle": 2}
PEOPLE = 2

_CAT793 = "Caterpillar 793F Mining Truck specification sheet (AEHQ), dimensions table, 162 m3 HP body"
_CAT7495 = "Cat 7495 HD electric rope shovel product page, 32 m3 dipper, 84 in treads"
_LC79 = "Toyota Land Cruiser 79 single cab specification sheet"

# (joint, axis, lower, upper) of every part below the root: revolute limits in degrees
_FIXED = ("revolute", "Z", 0.0, 0.0)
_SPIN = ("revolute", "Y", -360.0, 360.0)
_TRUCK = {
    "chassis": (
        None,
        53586.0,
        "Frame, hood, radiator, bumper, deck and hoist cylinders: chassis weight 124,586 kg minus cab, axles and tyres (design split)",
    ),
    "cab": (
        "chassis",
        3000.0,
        "ROPS cab on the left of the deck (design estimate); position from the 793F deck layout, ROPS height 5,712 mm",
    ),
    "dump-body": (
        "chassis",
        26862.0,
        "Body weight, lower end of the 793F body weight range 26,862 kg; width 7,942 mm, loading height 6,181 mm, canopy height 7,074 mm",
    ),
    "front-axle": ("chassis", 6000.0, "Front axle beam at wheelbase 5,905 mm from the rear axle (design mass)"),
    "rear-axle": (
        "chassis",
        14000.0,
        "Rear axle housing 4,000 mm from the tail (rear axle to tail 3,997 mm; design mass)",
    ),
}
_TRUCK_WHEELS = ("wheel-fl", "wheel-fr", "wheel-rl-o", "wheel-rl-i", "wheel-rr-i", "wheel-rr-o")


def _part(
    asset: str, pid: str, label: str, parent: str | None, mass: float, citation: str, body: machines.Body, joint=None
) -> dict[str, Any]:
    lo, hi = bounds(body.pieces)
    size = [round(float(v), 3) for v in hi - lo]
    out: dict[str, Any] = {
        "asset": asset,
        "id": pid,
        "part": label,
        "parent": parent,
        "mass_kg": float(mass),
        "length_m": size[0],
        "width_m": size[1],
        "height_m": size[2],
        "citation": citation[:256],
    }
    if parent is not None:
        kind, axis, lower, upper = joint
        out.update(joint=kind, axis=axis, lower_deg=lower, upper_deg=upper)
    return out


def _asset(
    cls: str,
    parts: list[dict[str, Any]],
    bodies: dict[str, machines.Body],
    dim_cite: str,
    mass_cite: str,
    mid_axle: float | None,
) -> dict[str, Any]:
    lo, hi = bounds([p for b in bodies.values() for p in b.pieces])
    size = [round(float(v), 3) for v in hi - lo]
    out = {
        "id": ASSET_IDS[cls],
        "class_label": cls,
        "length_m": size[0],
        "width_m": size[1],
        "height_m": size[2],
        "mass_kg": float(sum(p["mass_kg"] for p in parts)),
        "dimensions_citation": dim_cite[:256],
        "mass_citation": mass_cite[:256],
    }
    if mid_axle is not None:
        out["mid_axle_height_m"] = round(mid_axle, 3)
    return out


def _truck() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, machines.Body]]:
    bodies = machines.centred(machines.truck_bodies())
    aid = ASSET_IDS["haul_truck"]
    parts = []
    for pid, (parent, mass, cite) in _TRUCK.items():
        label = {"dump-body": "dump_body", "front-axle": "axle", "rear-axle": "axle"}.get(pid, pid)
        joint = None if parent is None else (("revolute", "Y", 0.0, 50.0) if pid == "dump-body" else _FIXED)
        parts.append(_part(aid, pid, label, parent, mass, f"{_CAT793}; {cite}", bodies[pid], joint))
    for wid in _TRUCK_WHEELS:
        parent = "front-axle" if wid in ("wheel-fl", "wheel-fr") else "rear-axle"
        cite = f"{_CAT793}; tyre 40.00R57, section 1,016 mm, radius derived from the designation (3.48 m outer diameter); design mass 8,000 kg"
        parts.append(_part(aid, wid, "wheel", parent, 8000.0, cite, bodies[wid], _SPIN))
    asset = _asset(
        "haul_truck", parts, bodies,
        f"{_CAT793}: length 13,360, wheelbase 5,905, canopy width 8,563, canopy height 7,074, tyre widths 5,609, 4,963, 7,605 mm",
        f"{_CAT793}: chassis 124,586 kg plus the lowest body weight 26,862 kg (empty machine)",
        machines.TYRE_RADIUS,
    )  # fmt: skip
    return asset, parts, bodies


def _shovel() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, machines.Body]]:
    bodies = machines.centred(machines.shovel_bodies())
    aid = ASSET_IDS["shovel"]
    c = _CAT7495
    spec = [
        ("undercarriage", "undercarriage", None, 280000.0, f"{c}; carbody between the crawlers, width from the 10 m crawler overall width (design mass)", None),
        ("track-left", "track", "undercarriage", 160000.0, f"{c}; crawler 11.6 m long (page snippet, body UNVERIFIED), shoe width 2,134 mm (84 in treads); design mass", _SPIN),
        ("track-right", "track", "undercarriage", 160000.0, f"{c}; crawler 11.6 m long (page snippet, body UNVERIFIED), shoe width 2,134 mm (84 in treads); design mass", _SPIN),
        ("house", "house", "undercarriage", 515777.0, f"{c}; upper works width 13.5 m with walkways, ballast 260,362 kg; length and height design", ("revolute", "Z", -180.0, 180.0)),
        ("boom", "boom", "house", 110000.0, f"{c}; boom length 15 m at 40 deg derived so the dipper reaches the cutting height 14.9 m (design mass)", ("revolute", "Y", -10.0, 20.0)),
        ("dipper-handle", "stick", "boom", 45000.0, f"{c}; handle length 11 m derived from dumping height 9.4 m (design mass)", ("revolute", "Y", -25.0, 25.0)),
        ("dipper", "dipper", "dipper-handle", 25000.0, f"{c}; dipper 32 m3: 3.4 m wide, 3.8 m deep, 3.8 m high (derived); design mass", ("revolute", "Y", -10.0, 60.0)),
    ]  # fmt: skip
    parts = [
        _part(aid, pid, label, parent, mass, cite, bodies[pid], joint) for pid, label, parent, mass, cite, joint in spec
    ]
    asset = _asset(
        "shovel", parts, bodies,
        f"{_CAT7495}: crawler overall width 10 m, upper works 13.5 m, cutting height 14.9 m, dumping height 9.4 m; boom, handle and house lengths derived",
        f"{_CAT7495}: working weight 1,295,777 kg, split among the parts by design",
        None,
    )  # fmt: skip
    return asset, parts, bodies


def _light_vehicle() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, machines.Body]]:
    bodies = machines.centred(machines.light_vehicle_bodies())
    aid = ASSET_IDS["light_vehicle"]
    c = _LC79
    parts = [
        _part(
            aid,
            "chassis",
            "chassis",
            None,
            2000.0,
            f"{c}: 5,235 x 1,800 mm body, wheelbase 3,180 mm; design mass",
            bodies["chassis"],
        ),
        _part(aid, "cab", "cab", "chassis", 320.0, f"{c}: height 1,975 mm; design mass", bodies["cab"], _FIXED),
    ]
    cite = f"{c}: tyres 225/95R16, radius derived from the designation; design mass"
    parts.extend(
        _part(aid, wid, "wheel", "chassis", 45.0, cite, bodies[wid], _SPIN)
        for wid in ("wheel-fl", "wheel-fr", "wheel-rl", "wheel-rr")
    )
    asset = _asset(
        "light_vehicle", parts, bodies,
        f"{c}: 5,235 x 1,800 x 1,975 mm, wheelbase 3,180 mm, tyres 225/95R16",
        "Design assumption (kerb mass of the sheet was not read); the pickup of the scene kit uses 2,500 kg",
        machines.LV_TYRE_RADIUS,
    )  # fmt: skip
    return asset, parts, bodies


_BUILT: dict[str, Any] = {}


def _built() -> dict[str, Any]:
    if not _BUILT:
        for cls, make in (("haul_truck", _truck), ("shovel", _shovel), ("light_vehicle", _light_vehicle)):
            _BUILT[cls] = make()
        pieces = machines.person_centred()
        lo, hi = bounds(pieces)
        size = [round(float(v), 3) for v in hi - lo]
        _BUILT["person"] = tuple(size)
    return _BUILT


def machine_specification() -> dict[str, Any]:
    """The `assets`, `parts`, `fleet`, `people_count` and `labels` of the scene specification (a fresh dict each call)."""
    import copy

    built = _built()
    assets, parts = [], []
    for cls in ("haul_truck", "shovel", "light_vehicle"):
        asset, asset_parts, _ = built[cls]
        assets.append(asset)
        parts.extend(asset_parts)
    return copy.deepcopy(
        {
            "assets": assets,
            "parts": parts,
            "fleet": [{"asset": ASSET_IDS[c], "count": n} for c, n in FLEET.items()],
            "people_count": PEOPLE,
            "labels": {"classes": list(CLASSES), "parts": list(PART_VOCABULARY)},
            "materials": [],
        }
    )


def bodies_of(cls: str) -> dict[str, machines.Body]:
    """The centred bodies of a machine class (pieces in the frame of the asset)."""
    return _built()[cls][2]


def _envelopes() -> dict[str, tuple[float, float, float]]:
    built = _built()
    out = {
        cls: (a["length_m"], a["width_m"], a["height_m"])
        for cls, (a, _, _) in ((c, built[c]) for c in ("haul_truck", "shovel", "light_vehicle"))
    }
    sx, sy, sz = built["person"]
    out["person"] = (max(sx, 0.6), max(sy, 0.6), sz)
    return out


ENVELOPES: dict[str, tuple[float, float, float]] = _envelopes()
