"""The SDG parameter table of `st55_sdg`: one row per image, every randomisation value drawn on the CPU (plan 009).

`python -m pitstudio_studio.sdg.table plan|build` runs in the studio environment (Python 3.14); the Isaac Sim stage
(Python 3.12) only reads the rows. Per scenario seed the camera site is drawn first (a road edge, a position on it, a
heading, a pose and a field of view: the layout id is the edge id), then the structured draws (FR-009-04..07) or the
unstructured draws (FR-009-08) from their own streams. The unstructured arm reuses the seeds and layouts of the
structured pit training split: image `i` takes training seed `i mod n_train`, so its camera is the structured camera of
that seed and only the randomisation differs. The crusher family is not rendered by this stage (its frames are the
ovrtx S3 handoff of spec 013) and is reported as skipped in the table manifest.
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
MIN_VISIBLE_M2 = 100.0
_COUNTS = {"haul_truck": (1, 3), "shovel": (0, 1), "light_vehicle": (0, 2), "person": (0, 3)}  # inclusive ranges
_DISTRACTORS = ("cube", "sphere", "cylinder")
_PLACEMENT_TRIES = 25
_WATERING_WINDOW_H = (36.0, 12.0)  # schedule horizon before and after the instant


def scenario_seed(recipe_seed: int, index: int) -> int:
    """Scenario seed `index` of a recipe: a 63-bit value that depends only on the recipe seed and the index."""
    state = np.random.SeedSequence([int(recipe_seed), 7, int(index)]).generate_state(1, dtype=np.uint64)
    return int(state[0]) >> 1


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
        cam_z = z + float(rng.uniform(*CAMERA_HEIGHT_M))
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


def _object_records(placements: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, p in enumerate(placements):
        dims = dimensions(p["class"])
        out.append({"prim_id": f"/World/Sdg/Obj_{i:02d}", "class": p["class"], **dims})
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
    for _ in range(_PLACEMENT_TRIES):
        drawn = placement.sample_structured_placements(
            rng,
            areas=areas,
            terrain_height=scene.height_at,
            object_classes=classes,
            max_base_offset_m=spec["placement"]["max_base_offset_m"],
        )
        kept = _non_overlapping(drawn)
        if len(kept) == len(drawn):
            break
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
        "objects": _object_records(kept),
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
    light, temperature = spec["light_intensity_factor"], spec["colour_temperature_k"]
    drawn = placement.sample_unstructured(
        rng,
        texture_ids=[t["id"] for t in recipe["texture_pool"]],
        ground_region=region,
        terrain_height=scene.height_at,
        object_classes=classes,
        light_range=(light["min"], light["max"]),
        colour_temperature_range_k=(temperature["min"], temperature["max"]),
        max_distractors=spec["distractors"]["max"],
    )
    dr = {k: v for k, v in drawn.items()}
    return {
        "dr": dr,
        "objects": _object_records(drawn["placements"]),
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
    scene = load_scene_inputs(scene_dir)
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
    scene = load_scene_inputs(scene_dir)
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
                "placement": "road polygons only; design surface height from the road centre line",
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
