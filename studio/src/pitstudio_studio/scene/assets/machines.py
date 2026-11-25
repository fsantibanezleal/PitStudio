# ruff: noqa: E501, RUF005
"""The procedural machines and the person mannequin of `st30_assets` (FR-004-51), as bodies of labelled pieces.

Each builder returns one `Body` per part of the asset specification: the origin of the body (its joint pivot, in the frame
of the asset: x forward, y left, z up, ground at z = 0, footprint centred) and the visible pieces that move with it. The
numbers are the cited dimensions named beside them; a value the source does not give is marked `derived` (from a cited
value) or `design` (a design assumption of this repository), and the catalogue repeats that in the citation strings.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from pitstudio_studio.scene.assets.geometry import Piece, Vec, bounds, box, ellipsoid, lathe, prism, tube

# ---------------------------------------------------------------------------------------------------------------
# haul truck: Caterpillar 793F specification sheet (AEHQ), dimensions table of the 793F with the 162 m3 HP body
# ---------------------------------------------------------------------------------------------------------------
TRUCK_LENGTH = 13.360  # overall length
TRUCK_WHEELBASE = 5.905
TRUCK_REAR_AXLE_TO_TAIL = 3.997
TRUCK_FRONT_TRACK = 5.609  # centreline front tyre width
TRUCK_REAR_PAIR_TRACK = 4.963  # centreline of the rear dual tyres
TRUCK_TYRE_OVERALL = 7.605  # overall tyre width
TRUCK_CANOPY_WIDTH = 8.563  # overall canopy width
TRUCK_BODY_WIDTH = 7.942  # outside body width
TRUCK_CANOPY_HEIGHT = 7.074  # front canopy height
TRUCK_LOADING_HEIGHT = 6.181  # loading height, empty: the top of the body walls
TRUCK_ROPS_HEIGHT = 5.712
TRUCK_GROUND_CLEARANCE = 1.041
TYRE_SECTION = 40.00 * 0.0254  # 40.00R57: section width 1.016 m
TYRE_RADIUS = (57.0 + 2.0 * 40.00) * 0.0254 / 2.0  # derived from the designation 40.00R57 at an aspect ratio of 100
TRUCK_DUAL_OFFSET = (
    TRUCK_TYRE_OVERALL - TRUCK_REAR_PAIR_TRACK - TYRE_SECTION
) / 2.0  # derived: tyre centre to pair centre


@dataclass
class Body:
    """One part of an asset: its pivot and the pieces that move with it (pieces in the frame of the asset)."""

    part_id: str
    origin: Vec
    pieces: list[Piece] = field(default_factory=list)


def _steel_cylinder_y(name: str, part: str, x: float, z: float, y0: float, y1: float, r: float) -> Piece:
    return tube(name, part, "steel", (x, y0, z), (x, y1, z), r, segments=16)


def _wheel(
    prefix: str, x: float, y: float, z: float, radius: float, width: float, hub: float, segs: int
) -> list[Piece]:
    half = width / 2.0
    profile = [
        (hub * 0.9, -half * 0.9),
        (radius * 0.86, -half),
        (radius * 0.97, -half * 0.72),
        (radius, -half * 0.35),
        (radius, half * 0.35),
        (radius * 0.97, half * 0.72),
        (radius * 0.86, half),
        (hub * 0.9, half * 0.9),
    ]
    tyre = lathe(f"{prefix}Tyre", "wheel", "rubber_tyre", (x, y, z), (0.0, 1.0, 0.0), profile, segs, closed=True)
    rim = tube(f"{prefix}Rim", "wheel", "steel_rim", (x, y - half * 0.8, z), (x, y + half * 0.8, z), hub, segments=16)
    cap_side = 1.0 if y >= 0.0 else -1.0
    cap = tube(
        f"{prefix}Cap",
        "wheel",
        "steel_cap",
        (x, y + cap_side * half * 0.8, z),
        (x, y + cap_side * half * 0.95, z),
        hub * 0.45,
        segments=12,
    )
    return [tyre, rim, cap]


def truck_bodies() -> dict[str, Body]:
    half = TRUCK_LENGTH / 2.0
    x_tail, x_front = -half, half
    x_rear_axle = x_tail + TRUCK_REAR_AXLE_TO_TAIL
    x_front_axle = x_rear_axle + TRUCK_WHEELBASE
    zc = TYRE_RADIUS
    bodies: dict[str, Body] = {}
    # chassis frame: two rails, cross members, engine hood, radiator, bumper, deck, hoist cylinders, rear housing
    chassis = Body("chassis", (0.0, 0.0, 2.7))
    for side, y in (("L", 0.75), ("R", -0.75)):
        chassis.pieces.append(
            box(f"Rail{side}", "chassis", "paint_frame", (x_tail + 0.3, y - 0.3, 2.2), (x_front - 0.5, y + 0.3, 3.2))
        )
        chassis.pieces.append(
            tube(
                f"Hoist{side}",
                "chassis",
                "steel_hoist",
                (x_tail + 2.3, y * 1.25, 3.0),
                (x_tail + 1.9, y * 1.25, 4.9),
                0.2,
                segments=10,
            )
        )
    for i, x in enumerate((x_tail + 0.9, x_rear_axle + 1.2, 0.0, x_front_axle - 1.4)):
        chassis.pieces.append(box(f"Cross{i}", "chassis", "paint_frame", (x - 0.25, -1.1, 2.35), (x + 0.25, 1.1, 3.0)))
    chassis.pieces.append(
        box("Hood", "chassis", "paint_hood", (x_front_axle + 0.7, -1.7, 2.4), (x_front - 0.25, 1.1, 4.5))
    )
    chassis.pieces.append(box("Radiator", "chassis", "steel_grille", (x_front - 0.25, -1.6, 2.5), (x_front, 1.0, 4.3)))
    chassis.pieces.append(box("Bumper", "chassis", "steel_bumper", (x_front - 0.55, -2.3, 1.95), (x_front, 2.3, 2.5)))
    chassis.pieces.append(
        box("Deck", "chassis", "paint_deck", (x_front_axle + 0.4, 1.1, 3.1), (x_front - 0.4, 4.2, 3.4))
    )
    chassis.pieces.append(
        box("Stairs", "chassis", "steel_stairs", (x_front_axle + 0.4, 3.7, 0.5), (x_front_axle + 1.0, 4.2, 3.1))
    )
    chassis.pieces.append(
        box("FuelTank", "chassis", "paint_tank", (x_rear_axle + 1.8, -3.0, 1.9), (x_front_axle - 1.5, -1.85, 3.5))
    )
    chassis.pieces.append(box("RearHousing", "chassis", "paint_frame", (x_tail, -2.0, 2.3), (x_tail + 0.5, 2.0, 3.6)))
    bodies["chassis"] = chassis
    # cab on the left of the deck
    cab = Body("cab", (x_front_axle + 1.7, 2.6, 4.7))
    cx0, cx1, cy0, cy1 = x_front_axle + 0.55, x_front - 0.75, 1.45, 3.85
    cab.pieces += [
        box("CabShell", "cab", "paint_cab", (cx0, cy0, 3.4), (cx1, cy1, 6.0)),
        box("CabRoof", "cab", "paint_roof", (cx0 - 0.1, cy0 - 0.1, 6.0), (cx1 + 0.1, cy1 + 0.1, 6.2)),
        box("Windscreen", "cab", "glass_front", (cx1, cy0 + 0.1, 4.3), (cx1 + 0.04, cy1 - 0.1, 5.8)),
        box("WindowOuter", "cab", "glass_side", (cx0 + 0.2, cy1, 4.3), (cx1 - 0.2, cy1 + 0.04, 5.8)),
        box("WindowInner", "cab", "glass_side", (cx0 + 0.2, cy0 - 0.04, 4.3), (cx1 - 0.2, cy0, 5.8)),
        box("WindowRear", "cab", "glass_rear", (cx0 - 0.04, cy0 + 0.1, 4.4), (cx0, cy1 - 0.1, 5.7)),
    ]
    bodies["cab"] = cab
    # dump body (pivot at the rear hinge), floor sloping up to the front wall, canopy over the cab
    z_floor_rear, z_floor_front = 3.5, 4.3
    hinge = (x_tail + 0.4, 0.0, z_floor_rear)
    body = Body("dump-body", hinge)
    wall = TRUCK_BODY_WIDTH / 2.0
    x_wall = x_front_axle - 1.0
    slope = [
        (x_tail, z_floor_rear),
        (x_wall, z_floor_front),
        (x_wall, z_floor_front + 0.25),
        (x_tail, z_floor_rear + 0.25),
    ]
    body.pieces.append(prism("Floor", "dump_body", "steel_floor", slope, -wall, wall))
    side = [
        (x_tail, z_floor_rear),
        (x_wall, z_floor_front),
        (x_wall, TRUCK_LOADING_HEIGHT),
        (x_tail, TRUCK_LOADING_HEIGHT),
    ]
    body.pieces.append(prism("WallL", "dump_body", "paint_body", side, wall - 0.25, wall))
    body.pieces.append(prism("WallR", "dump_body", "paint_body", side, -wall, -wall + 0.25))
    body.pieces.append(
        box(
            "FrontWall",
            "dump_body",
            "paint_body",
            (x_wall - 0.25, -wall, z_floor_front),
            (x_wall, wall, TRUCK_LOADING_HEIGHT + 0.35),
        )
    )
    for i in range(6):
        x = x_tail + 0.7 + i * (x_wall - x_tail - 1.2) / 5.0
        for tag, y0 in (("L", wall), ("R", -wall - 0.14)):
            low = z_floor_rear + (x - x_tail) / (x_wall - x_tail) * (z_floor_front - z_floor_rear)
            body.pieces.append(
                box(
                    f"Rib{tag}{i}",
                    "dump_body",
                    "paint_rib",
                    (x - 0.1, y0, low),
                    (x + 0.1, y0 + 0.14, TRUCK_LOADING_HEIGHT),
                )
            )
    for tag, y in (("L", wall - 0.5), ("R", -wall)):
        body.pieces.append(
            box(
                f"Rim{tag}",
                "dump_body",
                "paint_rim",
                (x_tail, y, TRUCK_LOADING_HEIGHT),
                (x_wall, y + 0.5, TRUCK_LOADING_HEIGHT + 0.12),
            )
        )
    canopy = [
        (x_wall - 0.3, 6.62),
        (x_front - 0.35, 6.85),
        (x_front - 0.35, TRUCK_CANOPY_HEIGHT),
        (x_wall - 0.3, TRUCK_CANOPY_HEIGHT),
    ]
    body.pieces.append(
        prism("Canopy", "dump_body", "paint_canopy", canopy, -TRUCK_CANOPY_WIDTH / 2.0, TRUCK_CANOPY_WIDTH / 2.0)
    )
    bodies["dump-body"] = body
    # axles and the six tyres: two on the front axle, a dual pair on each side of the rear axle
    for aid, x, half_y, r in (
        ("front-axle", x_front_axle, TRUCK_FRONT_TRACK / 2.0, 0.34),
        ("rear-axle", x_rear_axle, TRUCK_REAR_PAIR_TRACK / 2.0, 0.38),
    ):
        axle = Body(aid, (x, 0.0, zc))
        axle.pieces.append(_steel_cylinder_y("Beam", "axle", x, zc, -half_y, half_y, r))
        axle.pieces.append(box("Housing", "axle", "paint_diff", (x - 0.7, -0.9, zc - 0.6), (x + 0.7, 0.9, zc + 0.6)))
        bodies[aid] = axle
    wheels = (
        ("wheel-fl", x_front_axle, TRUCK_FRONT_TRACK / 2.0),
        ("wheel-fr", x_front_axle, -TRUCK_FRONT_TRACK / 2.0),
        ("wheel-rl-o", x_rear_axle, TRUCK_REAR_PAIR_TRACK / 2.0 + TRUCK_DUAL_OFFSET),
        ("wheel-rl-i", x_rear_axle, TRUCK_REAR_PAIR_TRACK / 2.0 - TRUCK_DUAL_OFFSET),
        ("wheel-rr-i", x_rear_axle, -TRUCK_REAR_PAIR_TRACK / 2.0 + TRUCK_DUAL_OFFSET),
        ("wheel-rr-o", x_rear_axle, -TRUCK_REAR_PAIR_TRACK / 2.0 - TRUCK_DUAL_OFFSET),
    )
    for wid, x, y in wheels:
        wheel = Body(wid, (x, y, zc))
        wheel.pieces = _wheel(wid.title().replace("-", ""), x, y, zc, TYRE_RADIUS, TYRE_SECTION, 0.85, 28)
        bodies[wid] = wheel
    return bodies


# ---------------------------------------------------------------------------------------------------------------
# rope shovel: Cat 7495 HD product page (dipper 32 m3, crawler overall width 10 m, upper works 13.5 m, cutting height
# 14.9 m, dumping height 9.4 m, working weight 1,295,777 kg); boom, handle and house lengths are derived from them
# ---------------------------------------------------------------------------------------------------------------
SHOVEL_CRAWLER_OVERALL = 10.0
SHOVEL_SHOE_WIDTH = 2.134  # standard 84 in treads
SHOVEL_CRAWLER_LENGTH = 11.6  # tread length of the 7495 product page snippet (the page body was not read)
SHOVEL_HOUSE_WIDTH = 13.5  # upper works overall width including walkways
SHOVEL_CUTTING_HEIGHT = 14.9
SHOVEL_DUMPING_HEIGHT = 9.4


def shovel_bodies() -> dict[str, Body]:
    bodies: dict[str, Body] = {}
    track_y = (SHOVEL_CRAWLER_OVERALL - SHOVEL_SHOE_WIDTH) / 2.0
    half = SHOVEL_CRAWLER_LENGTH / 2.0
    under = Body("undercarriage", (0.0, 0.0, 2.4))
    under.pieces += [
        box("CarBody", "undercarriage", "paint_carbody", (-4.0, -track_y, 1.0), (4.0, track_y, 3.0)),
        lathe(
            "SwingRing",
            "undercarriage",
            "steel_ring",
            (0.0, 0.0, 3.0),
            (0.0, 0.0, 1.0),
            [(0.0, 0.0), (4.3, 0.0), (4.3, 0.6), (0.0, 0.6)],
            32,
        ),
    ]
    bodies["undercarriage"] = under
    track_profile = [
        (-half + 1.0, 0.0),
        (half - 1.0, 0.0),
        (half, 1.0),
        (half, 1.6),
        (half - 0.8, 2.4),
        (-half + 0.8, 2.4),
        (-half, 1.6),
        (-half, 1.0),
    ]
    for tid, sign in (("track-left", 1.0), ("track-right", -1.0)):
        y0, y1 = sign * track_y - SHOVEL_SHOE_WIDTH / 2.0, sign * track_y + SHOVEL_SHOE_WIDTH / 2.0
        track = Body(tid, (0.0, sign * track_y, 1.2))
        tag = "L" if sign > 0 else "R"
        track.pieces.append(prism(f"Shoes{tag}", "track", "steel_track", track_profile, y0, y1))
        for end, x in (("Front", half - 0.9), ("Rear", -half + 0.9)):
            track.pieces.append(
                tube(
                    f"Drum{end}{tag}",
                    "track",
                    "steel_drum",
                    (x, y0 - 0.12, 1.2),
                    (x, y1 + 0.12, 1.2),
                    1.15,
                    segments=20,
                )
            )
        for i in range(4):
            x = -3.6 + i * 2.4
            track.pieces.append(
                tube(
                    f"Roller{i}{tag}",
                    "track",
                    "steel_roller",
                    (x, y0 - 0.08, 0.6),
                    (x, y1 + 0.08, 0.6),
                    0.5,
                    segments=12,
                )
            )
        bodies[tid] = track
    swing = (0.0, 0.0, 3.6)
    house = Body("house", swing)
    hw = 5.0
    house.pieces += [
        box("Machinery", "house", "paint_house", (-5.8, -hw, 3.6), (3.4, hw, 9.2)),
        prism("Roof", "house", "paint_roof", [(-5.8, 9.2), (3.4, 9.2), (2.6, 9.9), (-5.0, 9.9)], -hw, hw),
        box("Counterweight", "house", "paint_counterweight", (-8.4, -hw + 0.4, 3.9), (-5.8, hw - 0.4, 8.6)),
        box("WalkwayL", "house", "steel_walkway", (-5.8, hw, 3.7), (3.0, SHOVEL_HOUSE_WIDTH / 2.0, 3.9)),
        box("WalkwayR", "house", "steel_walkway", (-5.8, -SHOVEL_HOUSE_WIDTH / 2.0, 3.7), (3.0, -hw, 3.9)),
        box(
            "RailL",
            "house",
            "steel_rail",
            (-5.8, SHOVEL_HOUSE_WIDTH / 2.0 - 0.1, 3.9),
            (3.0, SHOVEL_HOUSE_WIDTH / 2.0, 4.9),
        ),
        box(
            "RailR",
            "house",
            "steel_rail",
            (-5.8, -SHOVEL_HOUSE_WIDTH / 2.0, 3.9),
            (3.0, -SHOVEL_HOUSE_WIDTH / 2.0 + 0.1, 4.9),
        ),
        box("Cab", "cab", "paint_cab", (2.0, 2.2, 7.0), (4.4, 4.6, 9.6)),
        box("CabGlass", "cab", "glass_front", (4.4, 2.3, 7.4), (4.45, 4.5, 9.4)),
        box("CabSide", "cab", "glass_side", (2.2, 4.6, 7.4), (4.2, 4.65, 9.4)),
        tube("MastL", "house", "steel_mast", (-0.5, 3.8, 9.8), (1.2, 0.8, 16.2), 0.3, segments=10),
        tube("MastR", "house", "steel_mast", (-0.5, -3.8, 9.8), (1.2, -0.8, 16.2), 0.3, segments=10),
        tube("Sheave", "house", "steel_sheave", (1.2, -1.0, 16.2), (1.2, 1.0, 16.2), 0.7, segments=18),
    ]
    bodies["house"] = house
    foot = np.array([3.4, 0.0, 5.0])  # boom foot pin
    angle = math.radians(40.0)
    boom_len = 13.0
    direction = np.array([math.cos(angle), 0.0, math.sin(angle)])
    tip = foot + direction * boom_len
    boom = Body("boom", tuple(foot))
    for tag, y in (("L", 1.3), ("R", -1.3)):
        boom.pieces.append(
            tube(
                f"Chord{tag}",
                "boom",
                "paint_boom",
                tuple(foot + (0, y, 0)),
                tuple(tip + (0, y * 0.75, 0)),
                0.32,
                0.26,
                segments=10,
            )
        )
    for i in range(1, 6):
        s = foot + direction * (boom_len * i / 6.0)
        boom.pieces.append(
            tube(
                f"Brace{i}",
                "boom",
                "paint_boom",
                tuple(s + (0, 1.3 - 0.05 * i, 0)),
                tuple(s + (0, -(1.3 - 0.05 * i), 0)),
                0.18,
                segments=8,
            )
        )
    boom.pieces.append(
        tube(
            "PointSheave",
            "boom",
            "steel_sheave",
            tuple(tip + (0, -1.1, 0)),
            tuple(tip + (0, 1.1, 0)),
            0.75,
            segments=18,
        )
    )
    bodies["boom"] = boom
    saddle = foot + direction * 7.0
    handle_dir = np.array([math.cos(math.radians(-38.0)), 0.0, math.sin(math.radians(-38.0))])
    h_back, h_front = saddle - handle_dir * 3.0, saddle + handle_dir * 7.0
    handle = Body("dipper-handle", tuple(saddle))
    for tag, y in (("L", 0.6), ("R", -0.6)):
        handle.pieces.append(
            tube(
                f"Beam{tag}",
                "stick",
                "paint_handle",
                tuple(h_back + (0, y, 0)),
                tuple(h_front + (0, y, 0)),
                0.3,
                segments=10,
            )
        )
    handle.pieces.append(
        box("Saddle", "stick", "steel_saddle", tuple(saddle + (-0.5, -1.2, -0.5)), tuple(saddle + (0.5, 1.2, 0.5)))
    )
    bodies["dipper-handle"] = handle
    dip = h_front
    dipper = Body("dipper", tuple(dip))
    dx0, dx1, dz0, dz1 = dip[0] - 0.6, dip[0] + 3.3, dip[2] - 2.8, dip[2] + 1.0
    dipper.pieces += [
        box("DipperBack", "dipper", "steel_dipper", (dx0, -1.7, dz0), (dx0 + 0.35, 1.7, dz1)),
        box("DipperFloor", "dipper", "steel_dipper", (dx0, -1.7, dz0), (dx1, 1.7, dz0 + 0.35)),
        box("DipperSideL", "dipper", "steel_dipper", (dx0, 1.35, dz0), (dx1, 1.7, dz1)),
        box("DipperSideR", "dipper", "steel_dipper", (dx0, -1.7, dz0), (dx1, -1.35, dz1)),
        box("DipperDoor", "dipper", "steel_door", (dx1 - 0.3, -1.35, dz0), (dx1, 1.35, dz0 + 1.0)),
    ]
    for i in range(5):
        y = -1.4 + i * 0.7
        dipper.pieces.append(
            prism(
                f"Tooth{i}",
                "dipper",
                "steel_tooth",
                [(dx1, dz0), (dx1 + 0.7, dz0 + 0.1), (dx1, dz0 + 0.4)],
                y - 0.15,
                y + 0.15,
            )
        )
    bodies["dipper"] = dipper
    return bodies


# ---------------------------------------------------------------------------------------------------------------
# light vehicle: Toyota Land Cruiser 79 single cab (5,235 x 1,800 x 1,975 mm, wheelbase 3,180 mm, tyre 225/95R16)
# ---------------------------------------------------------------------------------------------------------------
LV_LENGTH, LV_WIDTH, LV_HEIGHT, LV_WHEELBASE = 5.235, 1.800, 1.975, 3.180
LV_TYRE_RADIUS = (16.0 * 25.4 + 2.0 * 0.95 * 225.0) / 2.0 / 1000.0  # derived from 225/95R16
LV_TYRE_WIDTH = 0.225


def light_vehicle_bodies() -> dict[str, Body]:
    half = LV_LENGTH / 2.0
    x_rear = -half + 1.1  # design: rear overhang
    x_front = x_rear + LV_WHEELBASE
    track = LV_WIDTH / 2.0 - LV_TYRE_WIDTH / 2.0  # derived: tyres flush with the body sides
    r = LV_TYRE_RADIUS
    bodies: dict[str, Body] = {}
    ch = Body("chassis", (0.0, 0.0, 0.9))
    w = LV_WIDTH / 2.0
    ch.pieces += [
        box("Frame", "chassis", "paint_frame", (-half + 0.2, -w + 0.15, 0.45), (half - 0.2, w - 0.15, 0.75)),
        box("Hood", "chassis", "paint_white", (x_front - 0.5, -w, 0.75), (half - 0.1, w, 1.25)),
        box("Grille", "chassis", "steel_grille", (half - 0.1, -w + 0.15, 0.8), (half, w - 0.15, 1.15)),
        box("BumperF", "chassis", "steel_bumper", (half - 0.15, -w, 0.45), (half + 0.0, w, 0.75)),
        box("BumperR", "chassis", "steel_bumper", (-half, -w, 0.45), (-half + 0.15, w, 0.75)),
        box("BedFloor", "chassis", "paint_white", (-half + 0.15, -w, 0.75), (-0.95, w, 0.9)),
        box("BedSideL", "chassis", "paint_white", (-half + 0.15, w - 0.1, 0.9), (-0.95, w, 1.3)),
        box("BedSideR", "chassis", "paint_white", (-half + 0.15, -w, 0.9), (-0.95, -w + 0.1, 1.3)),
        box("Tailgate", "chassis", "paint_white", (-half + 0.15, -w, 0.9), (-half + 0.25, w, 1.3)),
        box("Sill", "chassis", "paint_white", (-0.95, -w, 0.75), (x_front - 0.5, w, 1.0)),
        box("HeadlightL", "chassis", "glass_lamp", (half - 0.02, w - 0.45, 0.95), (half + 0.04, w - 0.15, 1.1)),
        box("HeadlightR", "chassis", "glass_lamp", (half - 0.02, -w + 0.15, 0.95), (half + 0.04, -w + 0.45, 1.1)),
    ]
    bodies["chassis"] = ch
    cab = Body("cab", (-0.1, 0.0, 1.5))
    cx0, cx1 = -0.95, x_front - 0.5
    cab.pieces += [
        box("CabShell", "cab", "paint_white", (cx0, -w + 0.02, 1.0), (cx1, w - 0.02, 1.75)),
        box("CabRoof", "cab", "paint_white", (cx0 + 0.05, -w + 0.1, 1.75), (cx1 - 0.1, w - 0.1, LV_HEIGHT)),
        box("Windscreen", "cab", "glass_front", (cx1 - 0.05, -w + 0.12, 1.2), (cx1 + 0.02, w - 0.12, 1.72)),
        box("WindowL", "cab", "glass_side", (cx0 + 0.2, w - 0.03, 1.25), (cx1 - 0.2, w + 0.02, 1.72)),
        box("WindowR", "cab", "glass_side", (cx0 + 0.2, -w - 0.02, 1.25), (cx1 - 0.2, -w + 0.03, 1.72)),
        box("WindowRear", "cab", "glass_rear", (cx0 - 0.02, -w + 0.2, 1.3), (cx0 + 0.04, w - 0.2, 1.7)),
        box("MirrorL", "cab", "paint_mirror", (cx1 - 0.35, w, 1.4), (cx1 - 0.15, w + 0.08, 1.55)),
        box("MirrorR", "cab", "paint_mirror", (cx1 - 0.35, -w - 0.08, 1.4), (cx1 - 0.15, -w, 1.55)),
    ]
    bodies["cab"] = cab
    for wid, x, y in (
        ("wheel-fl", x_front, track),
        ("wheel-fr", x_front, -track),
        ("wheel-rl", x_rear, track),
        ("wheel-rr", x_rear, -track),
    ):
        wheel = Body(wid, (x, y, r))
        wheel.pieces = _wheel(wid.title().replace("-", ""), x, y, r, r, LV_TYRE_WIDTH, 0.2, 20)
        bodies[wid] = wheel
    return bodies


# ---------------------------------------------------------------------------------------------------------------
# person: adult mannequin of stature 1.75 m; segment lengths as fractions of the stature (Drillis and Contini, 1966,
# design values: the table of that report was not read in this repository)
# ---------------------------------------------------------------------------------------------------------------
STATURE = 1.75
PERSON_PART_LABELS = ("head", "torso", "arm", "leg", "hard_hat", "vest")  # outside the closed vocabulary of FR-004-25


def person_pieces() -> list[Piece]:
    h = STATURE
    shoulder_z, hip_z, knee_z, ankle_z = 0.818 * h, 0.53 * h, 0.285 * h, 0.039 * h
    half_shoulder = 0.259 * h / 2.0
    out: list[Piece] = [
        ellipsoid("Head", "head", "skin_face", (0.0, 0.0, 0.936 * h - 0.02), (0.09, 0.075, 0.11)),
        tube(
            "Neck", "head", "skin_neck", (0.0, 0.0, shoulder_z - 0.02), (0.0, 0.0, 0.936 * h - 0.1), 0.05, segments=10
        ),
        lathe(
            "HardHatDome",
            "hard_hat",
            "paint_hat",
            (0.0, 0.0, 0.936 * h + 0.03),
            (0.0, 0.0, 1.0),
            [(0.0, 0.0), (0.12, 0.0), (0.13, 0.05), (0.115, 0.11), (0.07, 0.145), (0.0, 0.155)],
            16,
        ),
        lathe(
            "HardHatBrim",
            "hard_hat",
            "paint_hat",
            (0.0, 0.0, 0.936 * h + 0.025),
            (0.0, 0.0, 1.0),
            [(0.0, 0.0), (0.17, 0.0), (0.17, 0.015), (0.0, 0.015)],
            16,
        ),
        box("Chest", "torso", "fabric_shirt", (-0.1, -half_shoulder, hip_z + 0.25), (0.1, half_shoulder, shoulder_z)),
        box(
            "VestFront",
            "vest",
            "fabric_hivis",
            (0.095, -half_shoulder - 0.01, hip_z + 0.22),
            (0.125, half_shoulder + 0.01, shoulder_z - 0.04),
        ),
        box(
            "VestBack",
            "vest",
            "fabric_hivis",
            (-0.125, -half_shoulder - 0.01, hip_z + 0.22),
            (-0.095, half_shoulder + 0.01, shoulder_z - 0.04),
        ),
        box(
            "VestStripeA",
            "vest",
            "fabric_reflective",
            (0.124, -half_shoulder - 0.011, hip_z + 0.32),
            (0.13, half_shoulder + 0.011, hip_z + 0.38),
        ),
        box(
            "VestStripeB",
            "vest",
            "fabric_reflective",
            (0.124, -half_shoulder - 0.011, hip_z + 0.5),
            (0.13, half_shoulder + 0.011, hip_z + 0.56),
        ),
        box(
            "Pelvis",
            "torso",
            "fabric_trousers",
            (-0.1, -half_shoulder * 0.85, hip_z - 0.04),
            (0.1, half_shoulder * 0.85, hip_z + 0.25),
        ),
    ]
    for tag, sign in (("L", 1.0), ("R", -1.0)):
        sh = (0.0, sign * (half_shoulder + 0.03), shoulder_z - 0.04)
        el = (0.0, sign * (half_shoulder + 0.045), 0.63 * h)
        wr = (0.03, sign * (half_shoulder + 0.045), 0.485 * h)
        out += [
            tube(f"ArmUpper{tag}", "arm", "fabric_shirt", sh, el, 0.045, 0.04, segments=10),
            tube(f"ArmLower{tag}", "arm", "skin_forearm", el, wr, 0.04, 0.032, segments=10),
            ellipsoid(f"Hand{tag}", "arm", "skin_hand", (wr[0] + 0.01, wr[1], wr[2] - 0.07), (0.035, 0.025, 0.08), 8),
        ]
        hip = (0.0, sign * 0.09, hip_z)
        knee = (0.01, sign * 0.09, knee_z)
        ank = (0.0, sign * 0.09, ankle_z)
        out += [
            tube(f"LegUpper{tag}", "leg", "fabric_trousers", hip, knee, 0.085, 0.065, segments=10),
            tube(f"LegLower{tag}", "leg", "fabric_trousers", knee, ank, 0.065, 0.05, segments=10),
            box(
                f"Boot{tag}",
                "leg",
                "rubber_boot",
                (-0.07, sign * 0.09 - 0.05, 0.0),
                (0.26, sign * 0.09 + 0.05, ankle_z + 0.07),
            ),
        ]
    return out


# ---------------------------------------------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------------------------------------------
BUILDERS: dict[str, Callable[[], dict[str, Body]]] = {
    "haul_truck": truck_bodies,
    "shovel": shovel_bodies,
    "light_vehicle": light_vehicle_bodies,
}
REQUIRED_PARTS: dict[str, tuple[str, ...]] = {
    "haul_truck": (
        "chassis",
        "cab",
        "dump-body",
        "front-axle",
        "rear-axle",
        "wheel-fl",
        "wheel-fr",
        "wheel-rl-o",
        "wheel-rl-i",
        "wheel-rr-i",
        "wheel-rr-o",
    ),
    "shovel": ("undercarriage", "track-left", "track-right", "house", "boom", "dipper-handle", "dipper"),
    "light_vehicle": ("chassis", "cab", "wheel-fl", "wheel-fr", "wheel-rl", "wheel-rr"),
}


def centred(bodies: dict[str, Body]) -> dict[str, Body]:
    """The bodies shifted in x and y so the footprint of all pieces is centred on the origin (z is untouched)."""
    pieces = [p for b in bodies.values() for p in b.pieces]
    lo, hi = bounds(pieces)
    shift = np.array([-(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0, 0.0])
    return {
        k: Body(b.part_id, tuple(np.asarray(b.origin) + shift), [p.moved(shift) for p in b.pieces])
        for k, b in bodies.items()
    }


def person_centred() -> list[Piece]:
    pieces = person_pieces()
    lo, hi = bounds(pieces)
    shift = (-(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0, -lo[2])
    return [p.moved(shift) for p in pieces]
