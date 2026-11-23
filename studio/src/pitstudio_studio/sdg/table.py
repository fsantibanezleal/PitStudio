"""The SDG parameter table of `st55_sdg`: one row per image, every randomisation value drawn on the CPU (plan 009).

`python -m pitstudio_studio.sdg.table plan|build` runs in the studio environment (Python 3.14); the Isaac Sim stage
(Python 3.12) only reads the rows. Per scenario seed the camera site is drawn first (a road edge, a position on it, a
heading, a pose and a field of view: the layout id is the edge id), then the structured draws (FR-009-04..07) or the
unstructured draws (FR-009-08) from their own streams. The unstructured arm reuses the seeds and layouts of the
structured pit training split: image `i` takes training seed `i mod n_train`, so its camera is the structured camera of
that seed and only the randomisation differs. The crusher family is not rendered by this stage (its frames are the
ovrtx S3 handoff of spec 013) and is reported as skipped in the table manifest.

Every height comes from the carved surface of `st20_pit_design` (FR-004-50), the surface the renderer shows
(FR-009-54): a camera pose is accepted only when the ray along its optical axis meets the surface farther than
`VIEW_NEAR_M` or not at all, and an object is visible only when the camera sees its footprint centroid at mid-height
and its top centre. An object that is not visible is drawn again within the placement tries and then recorded with
`visible: false` in the row. A scene without a carved surface (built before FR-004-50) keeps the road-centre-line height
and every object is visible.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from pitstudio_studio.sdg import dust_field, dust_wet, placement, sun
from pitstudio_studio.sdg._schemas import schema_errors
from pitstudio_studio.sdg.config import load_config
from pitstudio_studio.sdg.objects import dimensions, footprint
from pitstudio_studio.sdg.scene_inputs import SceneInputs, load_scene_inputs, wedge

IMAGE_W, IMAGE_H = 1280, 720
FAMILY = "pit"
DUST_CONDITION_PER_KM = 2.0  # sigma at or above which the frame state condition is "dust" (visibility under ~2 km)
CAMERA_HEIGHT_M = (2.5, 6.0)  # above the design surface: cab to gantry height
CAMERA_PITCH_DEG = (2.0, 8.0)  # looking down
CAMERA_HFOV_DEG = (60.0, 90.0)
VIEW_NEAR_M, VIEW_FAR_M = 10.0, 250.0
MIN_INSTANCE_PX = 16  # the renderer's `scene_render.MIN_INSTANCE_PX`: a smaller instance gets no annotation
VIEW_MAX_RANGE_M = 4000.0  # the camera's far clipping distance in the renderer
MIN_VISIBLE_M2 = 100.0
_COUNTS = {"haul_truck": (1, 3), "shovel": (0, 1), "light_vehicle": (0, 2), "person": (0, 3)}  # inclusive ranges
_DISTRACTORS = ("cube", "sphere", "cylinder")
_PLACEMENT_TRIES = 25
_WATERING_WINDOW_H = (36.0, 12.0)  # schedule horizon before and after the instant


def scenario_seed(recipe_seed: int, index: int) -> int:
    """Scenario seed `index` of a recipe: a 63-bit value that depends only on the recipe seed and the index."""
    state = np.random.SeedSequence([int(recipe_seed), 7, int(index)]).generate_state(1, dtype=np.uint64)
    return int(state[0]) >> 1


def camera_clear(scene: SceneInputs, camera: dict[str, Any]) -> bool:
    """FR-009-54: the optical axis meets the carved surface farther than `VIEW_NEAR_M` or not at all."""
    if scene.carved is None:
        return True
    hit = scene.carved.first_hit(camera["position_m"], camera["forward"], VIEW_MAX_RANGE_M)
    return hit is None or hit > VIEW_NEAR_M


def object_visible(scene: SceneInputs, camera: dict[str, Any], placement: dict[str, Any], dims: dict[str, Any]) -> bool:
    """FR-009-54: the segments from the camera centre to the footprint centroid at mid-height and to the top centre meet
    the carved surface nowhere."""
    if scene.carved is None:
        return True
    x, y, z, height = placement["x_m"], placement["y_m"], placement["z_m"], dims["height_m"]
    eye = camera["position_m"]
    return scene.carved.segment_clear(eye, (x, y, z + height / 2.0)) and scene.carved.segment_clear(
        eye, (x, y, z + height)
    )


def _box_frame(placement: dict[str, Any], dims: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Centre of the base, the two horizontal unit axes (along the heading and across it) and the height of a box."""
    yaw = math.radians(placement["yaw_deg"])
    origin = np.array([placement["x_m"], placement["y_m"], placement["z_m"]], dtype=np.float64)
    along = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    across = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    return origin, along, across, float(dims["height_m"])


def _camera_axes(camera: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    eye = np.asarray(camera["position_m"], dtype=np.float64)
    forward = np.asarray(camera["forward"], dtype=np.float64)
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, np.asarray(camera.get("up", (0.0, 0.0, 1.0)), dtype=np.float64))
    right = right / np.linalg.norm(right)
    return eye, forward, right, np.cross(right, forward)


def _project(camera: dict[str, Any], points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pixel column, pixel row and depth along the optical axis of world points (pinhole of the row's camera)."""
    eye, forward, right, up = _camera_axes(camera)
    rel = points - eye
    depth = rel @ forward
    safe = np.maximum(depth, 0.1)
    if "fx_px" not in camera:  # a camera without intrinsics (a unit-test pose): the view cone is the half space ahead
        return (
            np.full(len(points), camera.get("width_px", 1.0) / 2.0),
            np.full(len(points), camera.get("height_px", 1.0) / 2.0),
            depth,
        )
    fx = camera["fx_px"]
    u = camera.get("cx_px", camera["width_px"] / 2.0) + fx * (rel @ right) / safe
    v = camera.get("cy_px", camera["height_px"] / 2.0) - camera.get("fy_px", fx) * (rel @ up) / safe
    return u, v, depth


def object_too_near(camera: dict[str, Any], placement: dict[str, Any], dims: dict[str, Any]) -> bool:
    """FR-009-55: some point of the object's box is closer than `VIEW_NEAR_M` to the camera centre inside the view cone.

    The distance of the box to the camera centre decides at once when it is at least `VIEW_NEAR_M`; otherwise the box
    surface is sampled every half metre and each sample in front of the camera that projects into the image counts.
    """
    origin, along, across, height = _box_frame(placement, dims)
    eye = _camera_axes(camera)[0]
    half_l, half_w = dims["length_m"] / 2.0, dims["width_m"] / 2.0
    rel = eye - origin
    local = np.array([rel @ along, rel @ across, rel[2]])
    lo, hi = np.array([-half_l, -half_w, 0.0]), np.array([half_l, half_w, height])
    if float(np.linalg.norm(local - np.clip(local, lo, hi))) >= VIEW_NEAR_M:
        return False
    xs = np.linspace(-half_l, half_l, max(int(dims["length_m"] / 0.5) + 1, 2))
    ys = np.linspace(-half_w, half_w, max(int(dims["width_m"] / 0.5) + 1, 2))
    zs = np.linspace(0.0, height, max(int(height / 0.5) + 1, 2))
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    on_surface = (
        np.isclose(np.abs(gx), half_l) | np.isclose(np.abs(gy), half_w) | np.isclose(gz, 0.0) | np.isclose(gz, height)
    )
    local_pts = np.stack([gx[on_surface], gy[on_surface], gz[on_surface]], axis=1)
    world = (
        origin + local_pts[:, :1] * along + local_pts[:, 1:2] * across + local_pts[:, 2:3] * np.array([0.0, 0.0, 1.0])
    )
    u, v, depth = _project(camera, world)
    width, height_px = camera.get("width_px", 1e9), camera.get("height_px", 1e9)
    inside = (depth > 0.0) & (u >= 0.0) & (u <= width) & (v >= 0.0) & (v <= height_px)
    return bool(np.any(inside & (np.linalg.norm(world - eye, axis=1) < VIEW_NEAR_M)))


def camera_accepts(camera: dict[str, Any], placements: Sequence[dict[str, Any]]) -> bool:
    """FR-009-55: a camera is accepted only when no placed object is too near it (`object_too_near`)."""
    return not any(object_too_near(camera, p, dimensions(p["class"])) for p in placements)


def projected_box_px(camera: dict[str, Any], placement: dict[str, Any], dims: dict[str, Any]) -> float:
    """FR-009-55: the area in pixels of the object's box projected into the image, clipped to it (0 if behind)."""
    if "fx_px" not in camera:
        return math.inf  # no intrinsics: the size cannot be measured and excludes nothing
    origin, along, across, height = _box_frame(placement, dims)
    corners = np.array(
        [
            origin
            + sx * dims["length_m"] / 2.0 * along
            + sy * dims["width_m"] / 2.0 * across
            + np.array([0.0, 0.0, sz * height])
            for sx in (-1, 1)
            for sy in (-1, 1)
            for sz in (0, 1)
        ]
    )
    u, v, depth = _project(camera, corners)
    if not np.any(depth > 0.1):
        return 0.0
    u0, u1 = max(float(u.min()), 0.0), min(float(u.max()), float(camera["width_px"]))
    v0, v1 = max(float(v.min()), 0.0), min(float(v.max()), float(camera["height_px"]))
    return max(u1 - u0, 0.0) * max(v1 - v0, 0.0)


def _segment_hits_box(p0: np.ndarray, p1: np.ndarray, placement: dict[str, Any]) -> bool:
    dims = dimensions(placement["class"])
    origin, along, across, height = _box_frame(placement, dims)
    lo = np.array([-dims["length_m"] / 2.0, -dims["width_m"] / 2.0, 0.0])
    hi = np.array([dims["length_m"] / 2.0, dims["width_m"] / 2.0, height])
    a = np.array([(p0 - origin) @ along, (p0 - origin) @ across, p0[2] - origin[2]])
    b = np.array([(p1 - origin) @ along, (p1 - origin) @ across, p1[2] - origin[2]])
    d = b - a
    t0, t1 = 0.0, 1.0
    for k in range(3):
        if abs(d[k]) < 1e-12:
            if a[k] < lo[k] or a[k] > hi[k]:
                return False
            continue
        s0, s1 = (lo[k] - a[k]) / d[k], (hi[k] - a[k]) / d[k]
        t0, t1 = max(t0, min(s0, s1)), min(t1, max(s0, s1))
        if t0 > t1:
            return False
    return True


def object_occluded(camera: dict[str, Any], placement: dict[str, Any], others: Sequence[dict[str, Any]]) -> bool:
    """FR-009-55: a sight line to the object (centroid at mid-height, top centre) meets another object's box."""
    eye = _camera_axes(camera)[0]
    height = dimensions(placement["class"])["height_m"]
    aims = [
        np.array([placement["x_m"], placement["y_m"], placement["z_m"] + height / 2.0]),
        np.array([placement["x_m"], placement["y_m"], placement["z_m"] + height]),
    ]
    return any(_segment_hits_box(eye, aim, other) for aim in aims for other in others if other is not placement)


def objects_seen(scene: SceneInputs, camera: dict[str, Any], placements: Sequence[dict[str, Any]]) -> list[bool]:
    """FR-009-55 for each placement: line of sight over the carved surface (FR-009-54), a projected box of at least
    `MIN_INSTANCE_PX` pixels and no occlusion by another placed object."""
    out = []
    for i, p in enumerate(placements):
        dims = dimensions(p["class"])
        others = [q for j, q in enumerate(placements) if j != i]
        out.append(
            object_visible(scene, camera, p, dims)
            and projected_box_px(camera, p, dims) >= MIN_INSTANCE_PX
            and not object_occluded(camera, p, others)
        )
    return out


def _assess(
    scene: SceneInputs, camera: dict[str, Any], drawn: dict[str, Any], kept: Sequence[dict[str, Any]]
) -> tuple[bool, bool]:
    """(FR-009-54 line of sight on the carved surface, size and occlusion by `kept` pass) of `drawn`."""
    dims = dimensions(drawn["class"])
    carved = bool(object_visible(scene, camera, drawn, dims))
    return carved, bool(
        carved and projected_box_px(camera, drawn, dims) >= MIN_INSTANCE_PX and not object_occluded(camera, drawn, kept)
    )


def _seen_with(
    scene: SceneInputs,
    camera: dict[str, Any],
    drawn: dict[str, Any],
    kept: Sequence[dict[str, Any]],
    kept_seen: Sequence[bool],
    carved_out: list[bool] | None = None,
) -> bool:
    """`drawn` is seen (FR-009-55) among the already placed objects and hides none of those that are seen."""
    carved, seen = _assess(scene, camera, drawn, kept)
    if carved_out is not None:
        carved_out.append(carved)
    return seen and not any(
        flag and object_occluded(camera, k, [drawn]) for k, flag in zip(kept, kept_seen, strict=True)
    )


def _hide_occluded(camera: dict[str, Any], placements: Sequence[dict[str, Any]], flags: list[bool]) -> None:
    """Clear the flag of every object that another object of `placements` hides (a later fallback draw can hide one)."""
    for i, p in enumerate(placements):
        if flags[i] and object_occluded(camera, p, [q for j, q in enumerate(placements) if j != i]):
            flags[i] = False


def _final_flags(camera: dict[str, Any], placements: Sequence[dict[str, Any]], carved: Sequence[bool]) -> list[bool]:
    """`visible` of every placed object: carved-surface line of sight, projected size and no occluding object."""
    return [
        bool(
            carved[i]
            and projected_box_px(camera, p, dimensions(p["class"])) >= MIN_INSTANCE_PX
            and not object_occluded(camera, p, [q for j, q in enumerate(placements) if j != i])
        )
        for i, p in enumerate(placements)
    ]


def _stream(recipe_seed: int, seed: int, *tag: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([int(recipe_seed), int(seed), *tag]))


def scenario_geometry(scene: SceneInputs, recipe_seed: int, seed: int) -> dict[str, Any]:
    """Layout id, camera and visible road areas of a scenario seed (deterministic; shared by both arms)."""
    rng = _stream(recipe_seed, seed, 0)
    lengths = np.array([e.length_m for e in scene.edges])
    for _ in range(200):
        edge = scene.edges[int(rng.choice(len(scene.edges), p=lengths / lengths.sum()))]
        x, y, z, heading = scene.position_on_edge(edge.edge_id, float(rng.uniform(0.0, 1.0)))
        if rng.uniform() < 0.5:
            heading += 180.0
        heading += float(rng.normal(0.0, 10.0))
        hfov = float(rng.uniform(*CAMERA_HFOV_DEG))
        pitch = float(rng.uniform(*CAMERA_PITCH_DEG))
        ground = scene.height_at(x, y) if scene.carved is not None else z
        cam_z = ground + float(rng.uniform(*CAMERA_HEIGHT_M))
        visible = scene.road_union().intersection(wedge((x, y), heading, hfov / 2.0, VIEW_NEAR_M, VIEW_FAR_M))
        areas = [g for g in getattr(visible, "geoms", [visible]) if g.geom_type == "Polygon" and g.area > 1.0]
        if sum(a.area for a in areas) < MIN_VISIBLE_M2:
            continue
        yaw, tilt = math.radians(heading), math.radians(pitch)
        forward = [math.cos(yaw) * math.cos(tilt), math.sin(yaw) * math.cos(tilt), -math.sin(tilt)]
        fx = 0.5 * IMAGE_W / math.tan(math.radians(hfov) / 2.0)
        camera = {
            "position_m": [x, y, cam_z],
            "forward": forward,
            "up": [0.0, 0.0, 1.0],
            "width_px": IMAGE_W,
            "height_px": IMAGE_H,
            "fx_px": fx,
            "fy_px": fx,
            "cx_px": IMAGE_W / 2.0,
            "cy_px": IMAGE_H / 2.0,
        }
        if not camera_clear(scene, camera):
            continue
        return {"layout_id": edge.edge_id, "camera": camera, "areas": areas, "heading_deg": heading, "hfov_deg": hfov}
    raise ValueError(f"no camera site with a visible road found for seed {seed}")


def _class_list(rng: np.random.Generator) -> list[str]:
    out: list[str] = []
    for cls, (lo, hi) in _COUNTS.items():
        out.extend([cls] * int(rng.integers(lo, hi + 1)))
    return out


def _non_overlapping(placements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Greedy filter in order: a placement whose footprint overlaps an accepted one is dropped (the first is kept)."""
    kept: list[dict[str, Any]] = []
    shapes: list[BaseGeometry] = []
    for p in placements:
        shape = footprint(p["class"], p["x_m"], p["y_m"], p["yaw_deg"])
        if not any(shape.intersects(s) for s in shapes):
            kept.append(p)
            shapes.append(shape)
    return kept


def _object_records(placements: Sequence[dict[str, Any]], visible: Sequence[bool]) -> list[dict[str, Any]]:
    out = []
    for i, (p, seen) in enumerate(zip(placements, visible, strict=True)):
        dims = dimensions(p["class"])
        out.append({"prim_id": f"/World/Sdg/Obj_{i:02d}", "class": p["class"], **dims, "visible": bool(seen)})
    return out


def _watering_schedule(
    rng: np.random.Generator, edge_ids: Sequence[str], when: dt.datetime
) -> dict[str, list[dt.datetime]]:
    """Watering passes of every edge around `when`: a pass every 1.5 to 5 h from a random phase (design assumption)."""
    schedule: dict[str, list[dt.datetime]] = {}
    interval_h = float(rng.uniform(1.5, 5.0))
    start = when - dt.timedelta(hours=_WATERING_WINDOW_H[0])
    end = when + dt.timedelta(hours=_WATERING_WINDOW_H[1])
    for edge_id in edge_ids:
        t = start + dt.timedelta(hours=float(rng.uniform(0.0, interval_h)))
        passes = []
        while t <= end:
            passes.append(t)
            t += dt.timedelta(hours=interval_h)
        schedule[edge_id] = passes
    return schedule


def _utc(when: dt.datetime) -> str:
    return when.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def structured_row(scene: SceneInputs, recipe: dict[str, Any], seed: int, geometry: dict[str, Any]) -> dict[str, Any]:
    """DC-009-01 `dr_structured` and the scene description of one structured image."""
    spec = recipe["structured"]
    rng = _stream(recipe["seed"], seed, 1)
    sample = sun.sample_sun(
        rng,
        latitude_deg=scene.latitude_deg,
        longitude_deg=scene.longitude_deg,
        year=spec["sun"]["year"],
        elevation_m=scene.z0_m,
        min_elevation_deg=spec["sun"]["min_elevation_deg"],
    )
    scenario = dust_field.draw_scenario(rng)
    field = dust_field.RoadPlumeField(scene, scenario, ground=scene.height_at)
    sigma = dust_wet.dust_extinction_per_km(
        field,
        geometry["camera"]["position_m"],
        particle_diameter_m=dust_field.PARTICLE_DIAMETER_M,
        particle_density_kg_m3=dust_field.PARTICLE_DENSITY_KG_M3,
    )
    schedule = _watering_schedule(rng, [e.edge_id for e in scene.edges], sample.utc)
    wet = dust_wet.wet_segments(schedule, sample.utc, drying_time_min=recipe["drying_time_min"])
    lithologies = spec["rock_textures"]["lithologies"]
    litho = sorted(lithologies)[int(rng.integers(0, len(lithologies)))]
    rock = placement.sample_rock_textures(rng, litho, lithologies, count=3)
    classes = _class_list(rng)
    if not classes:
        classes = ["haul_truck"]
    areas = geometry["areas"]
    kept: list[dict[str, Any]] = []
    flags: list[bool] = []
    camera = geometry["camera"]
    carved: list[bool] = []
    for cls in classes:
        chosen: tuple[dict[str, Any], bool] | None = None
        chosen_carved = False
        for _ in range(_PLACEMENT_TRIES):
            drawn = placement.sample_structured_placements(
                rng,
                areas=areas,
                terrain_height=scene.height_at,
                object_classes=[cls],
                max_base_offset_m=spec["placement"]["max_base_offset_m"],
            )[0]
            carved_try: list[bool] = []
            seen = _seen_with(scene, camera, drawn, kept, flags, carved_try)
            if object_too_near(camera, drawn, dimensions(cls)):
                continue  # closer than VIEW_NEAR_M inside the view cone: never placed (FR-009-55)
            if len(_non_overlapping([*kept, drawn])) == len(kept):
                continue  # its footprint overlaps an object already placed: draw again
            chosen = (drawn, seen)
            chosen_carved = carved_try[0]
            if seen:
                break
        if chosen is not None:
            kept.append(chosen[0])
            flags.append(chosen[1])
            carved.append(chosen_carved)
            _hide_occluded(camera, kept, flags)
    flags[:] = _final_flags(camera, kept, carved)
    dr = {
        "sun_utc": _utc(sample.utc),
        "sun_elevation_deg": sample.elevation_deg,
        "sun_azimuth_deg": sample.azimuth_deg,
        "dust_extinction_per_km": sigma,
        "wet_segments": wet,
        "rock_texture_ids": rock,
        "placements": kept,
    }
    return {
        "dr": dr,
        "objects": _object_records(kept, flags),
        "distractors": [],
        "condition": "dust" if sigma >= DUST_CONDITION_PER_KM else "day",
        "dust_scenario": scenario.as_dict() | {"lithology": litho},
    }


def _distractors(rng: np.random.Generator, count: int, region: BaseGeometry, ground: Any) -> list[dict[str, Any]]:
    out = []
    for i in range(count):
        x, y = placement._point_in(rng, region)
        size = float(rng.uniform(0.3, 3.0))
        shape = str(rng.choice(_DISTRACTORS))
        out.append(
            {
                "prim_id": f"/World/Sdg/Distractor_{i:02d}",
                "shape": shape,
                "centre_m": [x, y, float(ground(x, y)) + size / 2.0],
                "size_m": size,
                "colour_rgb": [float(c) for c in rng.uniform(0.05, 0.95, size=3)],
            }
        )
    return out


def unstructured_row(
    scene: SceneInputs, recipe: dict[str, Any], seed: int, repeat: int, geometry: dict[str, Any]
) -> dict[str, Any]:
    """DC-009-01 `dr_unstructured` and the scene description of one unstructured image (FR-009-08)."""
    spec = recipe["unstructured"]
    rng = _stream(recipe["seed"], seed, 2, repeat)
    region = shapely.union_all(geometry["areas"])
    classes = _class_list(rng) or ["haul_truck"]
    flags: list[bool] = []
    light, temperature = spec["light_intensity_factor"], spec["colour_temperature_k"]
    camera = geometry["camera"]
    placed: list[dict[str, Any]] = []

    carved_of: dict[int, bool] = {}

    def seen(p: dict[str, Any]) -> bool:
        result: list[bool] = []
        ok = _seen_with(scene, camera, p, placed, flags, result)
        carved_of[id(p)] = result[0]
        return ok

    drawn = placement.sample_unstructured(
        rng,
        texture_ids=[t["id"] for t in recipe["texture_pool"]],
        ground_region=region,
        terrain_height=scene.height_at,
        object_classes=classes,
        light_range=(light["min"], light["max"]),
        colour_temperature_range_k=(temperature["min"], temperature["max"]),
        max_distractors=spec["distractors"]["max"],
        visible=seen,
        visibility_out=flags,
        reject=lambda p: object_too_near(camera, p, dimensions(p["class"])),
        placed_out=placed,
        tries=_PLACEMENT_TRIES,
    )
    flags[:] = _final_flags(camera, drawn["placements"], [carved_of[id(p)] for p in drawn["placements"]])
    dr = {k: v for k, v in drawn.items()}
    return {
        "dr": dr,
        "objects": _object_records(drawn["placements"], flags),
        "distractors": _distractors(rng, dr["distractor_count"], region, scene.height_at),
        "condition": "day",
        "dust_scenario": None,
    }


def check_dr(row: dict[str, Any]) -> None:
    """Raise when the row's DR object does not validate against its DC-009-01 definition."""
    definition = "dr_structured" if row["arm"] == "structured" else "dr_unstructured"
    errors = schema_errors("perception-dataset", row["dr"], definition)
    if errors:
        raise ValueError(f"{row['record_id']}: {definition} {errors[0][0] or '<root>'}: {errors[0][1]}")


def plan_scenarios(scene: SceneInputs, recipe: dict[str, Any], count: int) -> list[dict[str, Any]]:
    """The (seed, layout id) pairs of the structured pit arm, in image order."""
    return [
        {"seed": s, "layout_id": scenario_geometry(scene, recipe["seed"], s)["layout_id"]}
        for s in (scenario_seed(recipe["seed"], i) for i in range(count))
    ]


def build_rows(
    scene: SceneInputs, recipe: dict[str, Any], splits: dict[str, list[int]], counts: dict[str, int]
) -> Iterator[dict[str, Any]]:
    """Rows of the pit structured arm, then of the pit unstructured arm; `counts` holds the images per arm."""
    split_of = {int(s): name for name, seeds in splits.items() for s in seeds}
    structured_seeds = [scenario_seed(recipe["seed"], i) for i in range(counts["structured"])]
    for i, seed in enumerate(structured_seeds):
        geometry = scenario_geometry(scene, recipe["seed"], seed)
        row = {
            "schema_version": "1.0",
            "index": i,
            "record_id": f"pit-s-{i:05d}",
            "family": FAMILY,
            "arm": "structured",
            "split": split_of[seed],
            "scenario_seed": seed,
            "layout_id": geometry["layout_id"],
            "camera": geometry["camera"],
            **structured_row(scene, recipe, seed, geometry),
        }
        check_dr(row)
        yield row
    train = [s for s in structured_seeds if split_of[s] == "train"]
    for i in range(counts["unstructured"]):
        seed, repeat = train[i % len(train)], i // len(train)
        geometry = scenario_geometry(scene, recipe["seed"], seed)
        row = {
            "schema_version": "1.0",
            "index": i,
            "record_id": f"pit-u-{i:05d}",
            "family": FAMILY,
            "arm": "unstructured",
            "split": "train",
            "scenario_seed": seed,
            "layout_id": geometry["layout_id"],
            "camera": geometry["camera"],
            **unstructured_row(scene, recipe, seed, repeat, geometry),
        }
        check_dr(row)
        yield row


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _arm_counts(recipe: dict[str, Any], images: int | None) -> tuple[dict[str, int], list[dict[str, str]]]:
    counts: dict[str, int] = {}
    skipped: list[dict[str, str]] = []
    for arm in recipe["arms"]:
        if arm["family"] != FAMILY:
            skipped.append(
                {
                    "family": arm["family"],
                    "arm": arm["arm"],
                    "reason": "not rendered by st55_sdg: the crusher frames are the ovrtx S3 handoff of spec 013",
                }
            )
            continue
        counts[arm["arm"]] = int(arm["image_count"]) if images is None else int(images)
    return counts, skipped


def _paths(data: Path, scene_id: str) -> tuple[Path, Path]:
    scene = data / "processed" / "scene" / scene_id / "st45_validate" / "scene"
    return scene, data / "processed" / "perception" / "recipe.json"


def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def cmd_plan(args: argparse.Namespace) -> int:
    data = Path(args.data)
    scene_dir, recipe_path = _paths(data, args.scene_id)
    recipe = load_config(recipe_path)
    scene = load_scene_inputs(scene_dir, require_carved=True)
    counts, skipped = _arm_counts(recipe, args.images)
    scenarios = plan_scenarios(scene, recipe, counts["structured"])
    _write_json(
        Path(args.out), {"recipe_seed": recipe["seed"], "counts": counts, "skipped": skipped, "scenarios": scenarios}
    )
    print(f"[plan] {len(scenarios)} structured pit scenarios on {len({s['layout_id'] for s in scenarios})} layouts")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    data = Path(args.data)
    scene_dir, recipe_path = _paths(data, args.scene_id)
    recipe = load_config(recipe_path)
    scene = load_scene_inputs(scene_dir, require_carved=True)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    splits = json.loads(Path(args.splits).read_text(encoding="utf-8"))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts = plan["counts"]
    files: dict[str, dict[str, Any]] = {}
    handles = {arm: (out / f"pit-{arm}.jsonl.tmp").open("w", encoding="utf-8", newline="\n") for arm in counts}
    try:
        for row in build_rows(scene, recipe, splits, counts):
            handles[row["arm"]].write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    finally:
        for handle in handles.values():
            handle.close()
    for arm in counts:
        tmp = out / f"pit-{arm}.jsonl.tmp"
        final = out / f"pit-{arm}.jsonl"
        os.replace(tmp, final)
        files[arm] = {"path": final.name, "sha256": _sha256(final), "rows": counts[arm]}
    _write_json(
        out / "table.manifest.json",
        {
            "schema_version": "1.0",
            "scene_manifest_id": scene.manifest_id,
            "scene_id": args.scene_id,
            "recipe_sha256": _sha256(recipe_path),
            "recipe_seed": recipe["seed"],
            "files": files,
            "skipped_arms": plan["skipped"],
            "splits": {name: len(seeds) for name, seeds in splits.items()},
            "assumptions": {
                "dust": "AP-42 unpaved haul road emission on every edge, ISC3 finite line sources, Pasquill-Gifford "
                "sigmas; scenario draws within the AP-42 Table 13.2.2-3 ranges (design assumptions)",
                "watering": "a pass every 1.5 to 5 h on every edge from a random phase (design assumption)",
                "placement": "road polygons only; every height from the carved surface of st20_pit_design (FR-004-50), "
                "cameras with clear ground ahead and objects in line of sight (FR-009-54)",
                "dust_condition_threshold_per_km": DUST_CONDITION_PER_KM,
            },
        },
    )
    print(f"[build] wrote {sum(counts.values())} rows to {out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    for name, fn in (("plan", cmd_plan), ("build", cmd_build)):
        p = sub.add_parser(name)
        p.add_argument("--data", default=os.environ.get("PITSTUDIO_DATA", ""))
        p.add_argument("--scene-id", default="a1-bingham")
        p.add_argument("--images", type=int, default=None, help="images per arm instead of the recipe's count")
        p.set_defaults(fn=fn)
        if name == "plan":
            p.add_argument("--out", required=True)
        else:
            p.add_argument("--plan", required=True)
            p.add_argument("--splits", required=True)
            p.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
