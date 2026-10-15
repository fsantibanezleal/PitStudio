# ruff: noqa: E501, RUF046
"""Shared test fixtures and independent oracles for the scene-pipeline red tests (spec 004).

Test-only helper, locked together with the tests that use it. Third-party libraries (rasterio, laspy, pyproj,
shapely, pxr) are imported inside the functions, so that importing this module never needs them.

Nothing here calls the code under test. Everything that produces an expected value is written from the spec text, a
closed form, or a reference library called directly (PROJ through pyproj, shapely, OpenUSD).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = ROOT / "specs" / "004-scene-pipeline"
EXAMPLES = SPEC_DIR / "contracts" / "examples"

# Definitions: 1 US survey foot = 1200/3937 m exactly; 1 international foot = 0.3048 m exactly (spec 004 section 7).
FT_US = 1200 / 3937
FT_INTL = 0.3048

# Scene stage keys and the sub-package of `pitstudio_studio.scene` that implements each (plan.md "Design").
STAGE_PACKAGE = {
    "st10_terrain": "terrain",
    "st20_pit_design": "design",
    "st30_assets": "assets",
    "st40_compose": "compose",
    "st45_validate": "validate",
}

# Site origin of the contract example (UTM 12N, NAD83): used by every terrain test.
E0, N0, Z0 = 406500.0, 4484500.0, 1800.0


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def scene_spec(**overrides: Any) -> dict[str, Any]:
    """A deep copy of the contract example `scene-spec.valid.json` (DC-004-01), with top-level overrides."""
    spec = json.loads((EXAMPLES / "scene-spec.valid.json").read_text(encoding="utf-8"))
    spec = copy.deepcopy(spec)
    spec.update(overrides)
    return spec


def with_aoi(spec: dict[str, Any], x0: float, y0: float, x1: float, y1: float, cell: float = 1.0) -> dict[str, Any]:
    """Return `spec` with a rectangular AOI (site frame, m, counter-clockwise) and a cell size."""
    spec = copy.deepcopy(spec)
    spec["terrain"]["aoi_xy_m"] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    spec["terrain"]["cell_size_m"] = cell
    return spec


def with_origin(spec: dict[str, Any], e: float, n: float, z: float, epsg: int = 26912) -> dict[str, Any]:
    spec = copy.deepcopy(spec)
    spec["site"]["origin"] = {"epsg": epsg, "easting_m": e, "northing_m": n, "z0_m": z}
    return spec


# --------------------------------------------------------------------------------------------------------------
# Raster and point-cloud writers (fixtures generated in the test, never committed data)
# --------------------------------------------------------------------------------------------------------------


def crs_wkt(kind: str) -> str:
    """WKT of the CRS kinds the tests need (compound horizontal + vertical)."""
    import pyproj

    if kind == "utm12-m":  # NAD83 / UTM 12N + NAVD88 height, metres
        return pyproj.CRS.from_user_input("EPSG:26912+5703").to_wkt()
    if kind == "utm13-m":
        return pyproj.CRS.from_user_input("EPSG:26913+5703").to_wkt()
    if kind == "utm12-2011-m":  # NAD83(2011) / UTM 12N + NAVD88: another datum realisation
        return pyproj.CRS.from_user_input("EPSG:6341+5703").to_wkt()
    if kind == "utm12-ftus":  # UTM 12N in US survey feet (no EPSG code) + NAVD88 height (ftUS)
        h = pyproj.CRS.from_proj4("+proj=utm +zone=12 +datum=NAD83 +units=us-ft +no_defs")
        v = pyproj.CRS.from_epsg(6360)
        return pyproj.crs.CompoundCRS(name="UTM12N ftUS + NAVD88 ftUS", components=[h, v]).to_wkt()
    if kind == "utm12-ftintl-vm":  # UTM 12N in international feet, vertical NAVD88 in metres
        h = pyproj.CRS.from_proj4("+proj=utm +zone=12 +datum=NAD83 +units=ft +no_defs")
        v = pyproj.CRS.from_epsg(5703)
        return pyproj.crs.CompoundCRS(name="UTM12N ft + NAVD88 m", components=[h, v]).to_wkt()
    if kind == "utm12-horizontal-only":
        return pyproj.CRS.from_epsg(26912).to_wkt()
    raise ValueError(kind)


def write_dem(
    path: Path,
    array: np.ndarray,
    *,
    x_min: float,
    y_max: float,
    cell: float,
    wkt: str | None,
    nodata: float | None = -9999.0,
) -> Path:
    """Write a float32 single-band GeoTIFF; row 0 is the northern edge (rasterio `from_origin`)."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_origin

    rows, cols = array.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs=CRS.from_wkt(wkt) if wkt else None,
        transform=from_origin(x_min, y_max, cell, cell),
        nodata=nodata,
    ) as dst:
        dst.write(array.astype("float32"), 1)
    return Path(path)


def write_laz(
    path: Path,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    classification: np.ndarray,
    *,
    crs: str = "EPSG:26912+5703",
) -> Path:
    """Write a LAS 1.4 (point format 6) file compressed as LAZ with a WKT CRS record."""
    import laspy
    import pyproj

    hdr = laspy.LasHeader(point_format=6, version="1.4")
    hdr.offsets = np.array([math.floor(float(np.min(x))), math.floor(float(np.min(y))), math.floor(float(np.min(z)))])
    hdr.scales = np.array([0.001, 0.001, 0.001])
    hdr.add_crs(pyproj.CRS.from_user_input(crs))
    las = laspy.LasData(hdr)
    las.x, las.y, las.z = x, y, z
    las.classification = np.asarray(classification, dtype=np.uint8)
    las.write(str(path))
    return Path(path)


def fbm_grid(k: int, seed: int, amplitude: float = 50.0, base: float = 0.0) -> np.ndarray:
    """(2^k + 1)^2 fractal height grid by midpoint-free spectral synthesis; deterministic in `seed`."""
    n = 2**k + 1
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(n)
    kx, ky = np.meshgrid(f, f)
    radius = np.hypot(kx, ky)
    radius[0, 0] = 1.0
    spectrum = (rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))) / radius**1.6
    spectrum[0, 0] = 0.0
    z = np.real(np.fft.ifft2(spectrum))
    z = z / (np.abs(z).max() or 1.0)
    return base + amplitude * z


def stepped_bench_grid(k: int, height: float = 15.0, steps: int = 4) -> np.ndarray:
    """(2^k + 1)^2 grid of concentric square benches: a staircase of `steps` levels `height` metres apart."""
    n = 2**k + 1
    yy, xx = np.mgrid[0:n, 0:n]
    ring = np.maximum(np.abs(xx - n // 2), np.abs(yy - n // 2))
    level = np.minimum(ring * steps // (n // 2 + 1), steps - 1)
    return (level * height).astype(np.float64)


# --------------------------------------------------------------------------------------------------------------
# Pit-design fixtures
# --------------------------------------------------------------------------------------------------------------


def regular_polygon(n: int, circumradius: float, centre: tuple[float, float] = (0.0, 0.0)) -> list[list[float]]:
    """Counter-clockwise regular n-gon with a vertex on the +x axis, as a list of [x, y] (not closed)."""
    ang = 2.0 * math.pi * np.arange(n) / n
    return [[centre[0] + circumradius * math.cos(a), centre[1] + circumradius * math.sin(a)] for a in ang]


def star_polygon(seed: int, n: int, r_min: float, r_max: float) -> list[list[float]]:
    """A simple star-shaped polygon: n vertices at sorted angles with radii in [r_min, r_max] (deterministic)."""
    rng = np.random.default_rng(seed)
    ang = 2.0 * math.pi * (np.arange(n) + rng.uniform(-0.3, 0.3, n)) / n  # strictly increasing: star-shaped
    r = rng.uniform(r_min, r_max, n)
    return [[float(r[i] * math.cos(ang[i])), float(r[i] * math.sin(ang[i]))] for i in range(n)]


def flat_grid(
    half_extent_m: float, cell: float = 1.0, z: float = 0.0, x_min: float | None = None, y_max: float | None = None
) -> Any:
    """A minimal terrain grid (duck-typed): `elevation` float32 [rows, cols], `x_min_m`, `y_max_m`, `cell_size_m`."""
    from types import SimpleNamespace

    n = int(round(2 * half_extent_m / cell))
    return SimpleNamespace(
        elevation=np.full((n, n), z, dtype=np.float32),
        x_min_m=-half_extent_m if x_min is None else x_min,
        y_max_m=half_extent_m if y_max is None else y_max,
        cell_size_m=cell,
    )


def param(value: float, lo: float, hi: float, verification: str = "verified") -> dict[str, Any]:
    """A DC-004-01 design parameter {value, code_min, code_max, citation, verification}."""
    return {
        "value": value,
        "code_min": lo,
        "code_max": hi,
        "citation": "test design-code range",
        "verification": verification,
    }


def design_block(
    h: float = 15.0,
    alpha: float = 70.0,
    b: float = 10.0,
    g: float = 8.0,
    w: float = 30.0,
    windrow: float = 2.5,
    rim_z: float = 0.0,
    floor_z: float = -150.0,
) -> dict[str, Any]:
    """The `design` block of a SceneSpec with wide declared design-code ranges (the hard domain of FR-004-22)."""
    return {
        "outline_source": "rim-contour",
        "rim_z_m": rim_z,
        "floor_z_m": floor_z,
        "bench_height_m": param(h, 5.0, 30.0),
        "face_angle_deg": param(alpha, 40.0, 85.0),
        "berm_width_m": param(b, 3.0, 60.0),
        "ramp_grade_pct": param(g, 0.0, 15.0),
        "ramp_width_m": param(w, 8.0, 60.0),
        "windrow_height_m": param(windrow, 0.001, 5.0),
    }


def design_spec(**kw: float) -> dict[str, Any]:
    """The contract example SceneSpec with the design block replaced (see `design_block`)."""
    spec = scene_spec()
    spec["design"] = design_block(**kw)
    return spec


SPEC_ROOT = ROOT / "specs"


def validator(schema_name: str, spec_dir: Path | None = None):
    """A jsonschema Draft 2020-12 validator for a draft schema of spec 004, with every sibling schema resolvable.

    Draft schemas of the foundation contracts (specs 001 and 002), which spec 002's job schema refers to, are also
    registered, so cross-spec `$ref`s resolve.
    """
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    d = spec_dir or (SPEC_DIR / "contracts")
    resources = []
    for folder in (d, SPEC_ROOT / "001-contracts" / "contracts", SPEC_ROOT / "002-runner" / "contracts"):
        for p in folder.glob("*.schema.json"):
            doc = json.loads(p.read_text(encoding="utf-8"))
            resources.append((doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012)))
    registry = Registry().with_resources(resources)
    schema = json.loads((d / schema_name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, registry=registry)


def without_fixture_flag(node: Any) -> Any:
    """A copy of `node` without any boolean `fixture` member: the draft schemas have `additionalProperties: false` and no such member
    (FR-004-44 and FR-013-43 add it), so schema checks of fixture-aware documents ignore that one member."""
    if isinstance(node, dict):
        return {k: without_fixture_flag(v) for k, v in node.items() if not (k == "fixture" and isinstance(v, bool))}
    if isinstance(node, list):
        return [without_fixture_flag(v) for v in node]
    return node


def schema_errors(schema_name: str, instance: Any, spec_dir: Path | None = None) -> list[str]:
    instance = without_fixture_flag(instance)
    v = validator(schema_name, spec_dir)
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(instance))


def polyline_length_3d(c: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(np.asarray(c, dtype=np.float64), axis=0), axis=1)))


def segment_grades_pct(c: np.ndarray) -> np.ndarray:
    """Absolute grade (percent, rise over horizontal run) of every consecutive sample pair of an (n, 3) polyline."""
    c = np.asarray(c, dtype=np.float64)
    run = np.hypot(np.diff(c[:, 0]), np.diff(c[:, 1]))
    rise = np.abs(np.diff(c[:, 2]))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(run > 0, 100.0 * rise / run, np.where(rise > 0, np.inf, 0.0))


# --------------------------------------------------------------------------------------------------------------
# Asset fixtures (st30_assets)
# --------------------------------------------------------------------------------------------------------------

ALL_CLASSES = [
    "terrain",
    "bench",
    "berm",
    "ramp",
    "windrow",
    "haul_road",
    "haul_truck",
    "shovel",
    "excavator",
    "wheel_loader",
    "water_truck",
    "light_vehicle",
    "crusher",
    "person",
    "boulder",
]
ALL_PARTS = [
    "chassis",
    "cab",
    "dump_body",
    "wheel",
    "axle",
    "track",
    "undercarriage",
    "house",
    "boom",
    "stick",
    "bucket",
    "dipper",
    "lift_arm",
    "front_frame",
    "rear_frame",
    "tank",
    "spray_bar",
    "hopper",
]


def _asset(aid: str, cls: str, dims: tuple[float, float, float], mass: float, mid_axle: float | None) -> dict[str, Any]:
    a: dict[str, Any] = {
        "id": aid,
        "class_label": cls,
        "length_m": dims[0],
        "width_m": dims[1],
        "height_m": dims[2],
        "mass_kg": mass,
        "dimensions_citation": "test fixture dimensions",
        "mass_citation": "test fixture mass",
    }
    if mid_axle is not None:
        a["mid_axle_height_m"] = mid_axle
    return a


def _part(
    asset: str,
    pid: str,
    label: str,
    parent: str | None,
    mass: float,
    dims: tuple[float, float, float],
    joint: str | None = None,
    axis: str | None = None,
    lo: float = 0.0,
    hi: float = 0.0,
) -> dict[str, Any]:
    p: dict[str, Any] = {
        "asset": asset,
        "id": pid,
        "part": label,
        "parent": parent,
        "mass_kg": mass,
        "length_m": dims[0],
        "width_m": dims[1],
        "height_m": dims[2],
        "citation": "test fixture",
    }
    if joint:
        p["joint"], p["axis"] = joint, axis
        if joint == "revolute":
            p["lower_deg"], p["upper_deg"] = lo, hi
        else:
            p["lower_m"], p["upper_m"] = lo, hi
    return p


def machine_spec(classes: tuple[str, ...] | None = None) -> dict[str, Any]:
    """The contract example SceneSpec with one test machine per class (articulated parts, joints, limits, masses)."""
    spec = scene_spec()
    spec["labels"] = {"classes": list(ALL_CLASSES), "parts": list(ALL_PARTS)}
    spec["materials"] = []  # tests that need materials set their own list and pass the texture files
    chains: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    a = "haul-truck-220t"
    chains["haul_truck"] = (
        _asset(a, "haul_truck", (12.8, 7.3, 6.6), 162000.0, 1.6),
        [
            _part(a, "chassis", "chassis", None, 112000.0, (12.8, 7.3, 4.5)),
            _part(a, "dump-body", "dump_body", "chassis", 50000.0, (9.5, 7.0, 2.8), "revolute", "Y", 0.0, 50.0),
        ],
    )
    a = "shovel-90m3"
    chains["shovel"] = (
        _asset(a, "shovel", (20.0, 12.0, 18.0), 1000000.0, None),
        [
            _part(a, "undercarriage", "undercarriage", None, 400000.0, (14.0, 10.0, 3.0)),
            _part(a, "house", "house", "undercarriage", 350000.0, (12.0, 9.0, 6.0), "revolute", "Z", -180.0, 180.0),
            _part(a, "boom", "boom", "house", 120000.0, (14.0, 2.0, 2.0), "revolute", "Y", -10.0, 60.0),
            _part(a, "stick", "stick", "boom", 80000.0, (9.0, 1.5, 1.5), "revolute", "Y", -90.0, 10.0),
            _part(a, "bucket", "bucket", "stick", 50000.0, (4.0, 5.0, 3.0), "revolute", "Y", -80.0, 80.0),
        ],
    )
    a = "excavator-400t"
    chains["excavator"] = (
        _asset(a, "excavator", (15.0, 8.0, 7.0), 400000.0, None),
        [
            _part(a, "track", "track", None, 150000.0, (10.0, 8.0, 2.0)),
            _part(a, "house", "house", "track", 150000.0, (8.0, 6.0, 4.0), "revolute", "Z", -180.0, 180.0),
            _part(a, "boom", "boom", "house", 50000.0, (9.0, 1.5, 1.5), "revolute", "Y", -20.0, 70.0),
            _part(a, "stick", "stick", "boom", 30000.0, (5.0, 1.2, 1.2), "revolute", "Y", -100.0, 0.0),
            _part(a, "bucket", "bucket", "stick", 20000.0, (3.0, 3.5, 2.5), "revolute", "Y", -90.0, 90.0),
        ],
    )
    a = "loader-l1350"
    chains["wheel_loader"] = (
        _asset(a, "wheel_loader", (20.0, 7.0, 7.0), 260000.0, 1.9),
        [
            _part(a, "front-frame", "front_frame", None, 90000.0, (9.0, 6.0, 3.0)),
            _part(
                a, "rear-frame", "rear_frame", "front-frame", 110000.0, (9.0, 6.0, 3.5), "revolute", "Z", -40.0, 40.0
            ),
            _part(a, "lift-arm", "lift_arm", "front-frame", 40000.0, (6.0, 1.0, 1.5), "revolute", "Y", -10.0, 50.0),
            _part(a, "bucket", "bucket", "lift-arm", 20000.0, (3.5, 6.0, 2.0), "revolute", "Y", -45.0, 45.0),
        ],
    )
    a = "water-truck-100"
    chains["water_truck"] = (
        _asset(a, "water_truck", (9.0, 4.5, 4.0), 60000.0, 1.1),
        [
            _part(a, "chassis", "chassis", None, 40000.0, (9.0, 4.5, 2.0)),
            _part(a, "tank", "tank", "chassis", 15000.0, (6.0, 3.5, 2.5), "revolute", "X", 0.0, 0.0),
            _part(a, "spray-bar", "spray_bar", "chassis", 5000.0, (0.5, 4.0, 0.3), "prismatic", "Z", 0.0, 0.5),
        ],
    )
    a = "pickup-4x4"
    chains["light_vehicle"] = (
        _asset(a, "light_vehicle", (5.3, 1.9, 1.9), 2500.0, 0.35),
        [_part(a, "chassis", "chassis", None, 2500.0, (5.3, 1.9, 1.9))],
    )
    a = "crusher-primary"
    chains["crusher"] = (
        _asset(a, "crusher", (15.0, 10.0, 12.0), 500000.0, None),
        [_part(a, "hopper", "hopper", None, 500000.0, (15.0, 10.0, 12.0))],
    )
    chosen = classes or tuple(chains)
    spec["assets"] = [chains[c][0] for c in chosen]
    spec["parts"] = [p for c in chosen for p in chains[c][1]]
    spec["fleet"] = [{"asset": chains[c][0]["id"], "count": 1} for c in chosen]
    return spec


def tiny_png(path: Path, rgb: tuple[int, int, int] = (120, 110, 90)) -> Path:
    """A valid 4 x 4 RGB PNG (written with the standard library only)."""
    import struct
    import zlib

    raw = b"".join(b"\x00" + bytes(rgb) * 4 for _ in range(4))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    Path(path).write_bytes(png)
    return Path(path)


# --------------------------------------------------------------------------------------------------------------
# Compose / validate fixtures: hand-written upstream layers (no first-party code involved)
# --------------------------------------------------------------------------------------------------------------


def canonical_json(obj: Any) -> str:
    """RFC 8785 (JCS) canonical JSON for the value kinds of a SceneSpec: objects, arrays, strings, ints, floats < 1e16."""
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if obj is None:
        return "null"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        if obj == int(obj) and abs(obj) < 1e16:
            return str(int(obj))
        return repr(obj)
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(canonical_json(x) for x in obj) + "]"
    if isinstance(obj, dict):
        return (
            "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + canonical_json(obj[k]) for k in sorted(obj)) + "}"
        )
    raise TypeError(type(obj))


def params_sha256(spec: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(spec).encode("utf-8")).hexdigest()


# Expected world transform of /World/Fleet/Truck_00/Body/Chassis (USD row-vector convention, hand calculation):
# local matrices: Truck_00 translate (10, 20, 5); Body rotateZ 90 degrees; Chassis translate (1, 0, 0).
# world = L_chassis . L_body . L_truck; the origin maps to (1,0,0) -> rotated to (0,1,0) -> translated to (10,21,5).
CHASSIS_WORLD = [0.0, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 10.0, 21.0, 5.0, 1.0]
IDENTITY16 = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def new_usd_stage(path: Path, *, up: str = "Z", mpu: float | None = 1.0, kpu: float | None = 1.0):
    from pxr import Usd, UsdGeom, UsdPhysics

    st = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(st, up)
    if mpu is not None:
        UsdGeom.SetStageMetersPerUnit(st, mpu)
    if kpu is not None:
        UsdPhysics.SetStageKilogramsPerUnit(st, kpu)
    return st


def define_quad(stage: Any, path: str, size: float, cls: str, part: str | None = None) -> Any:
    """A two-triangle quad (4 vertices, 2 faces) with the class (and part) labels."""
    from pxr import UsdGeom, UsdSemantics

    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr([(0.0, 0.0, 0.0), (size, 0.0, 0.0), (size, size, 0.0), (0.0, size, 0.0)])
    mesh.CreateFaceVertexCountsAttr([3, 3])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 0, 2, 3])
    mesh.CreateExtentAttr([(0.0, 0.0, 0.0), (size, size, 0.0)])
    mesh.CreateSubdivisionSchemeAttr("none")
    mesh.CreateNormalsAttr([(0.0, 0.0, 1.0)] * 4)
    mesh.SetNormalsInterpolation("vertex")
    prim = mesh.GetPrim()
    UsdSemantics.LabelsAPI.Apply(prim, "class").CreateLabelsAttr([cls])
    if part:
        UsdSemantics.LabelsAPI.Apply(prim, "part").CreateLabelsAttr([part])
    return mesh


def fixture_upstream(root: Path) -> dict[str, Any]:
    """Hand-written upstream layers (terrain with a `lod` variant set, design, fleet) plus the upstream records.

    Layout under `root`: layers/terrain.usdc, layers/design.usda, layers/fleet.usda. Returns the `upstream` mapping of
    `compose.compose_scene`: `layers`, `layer_sha256`, `assets` (empty) and `records` (the sources, inputs, terrain,
    design, textures, people_route and site records of the DC-004-02 contract example).
    """
    from pxr import Gf, UsdGeom

    layers = root / "layers"
    layers.mkdir(parents=True, exist_ok=True)
    # terrain: variant set `lod` with one tile per lod
    st = new_usd_stage(layers / "terrain.usdc")
    world = UsdGeom.Xform.Define(st, "/World")
    st.SetDefaultPrim(world.GetPrim())
    terrain = UsdGeom.Xform.Define(st, "/World/Terrain")
    vset = terrain.GetPrim().GetVariantSets().AddVariantSet("lod")
    for i in range(3):
        vset.AddVariant(f"lod{i}")
        vset.SetVariantSelection(f"lod{i}")
        with vset.GetVariantEditContext():
            UsdGeom.Xform.Define(st, f"/World/Terrain/Lod{i}")
            define_quad(st, f"/World/Terrain/Lod{i}/Tile_{i}_0_0_0", 100.0 * (i + 1), "terrain")
    vset.SetVariantSelection("lod0")
    st.GetRootLayer().Save()
    # design
    st = new_usd_stage(layers / "design.usda")
    st.SetDefaultPrim(UsdGeom.Xform.Define(st, "/World").GetPrim())
    UsdGeom.Xform.Define(st, "/World/Design")
    define_quad(st, "/World/Design/Bench_00", 50.0, "bench")
    st.GetRootLayer().Save()
    # fleet: a three-level transform hierarchy
    st = new_usd_stage(layers / "fleet.usda")
    st.SetDefaultPrim(UsdGeom.Xform.Define(st, "/World").GetPrim())
    UsdGeom.Xform.Define(st, "/World/Fleet")
    UsdGeom.Xform.Define(st, "/World/Fleet/Truck_00").AddTranslateOp().Set(Gf.Vec3d(10.0, 20.0, 5.0))
    UsdGeom.Xform.Define(st, "/World/Fleet/Truck_00/Body").AddRotateZOp().Set(90.0)
    chassis = define_quad(st, "/World/Fleet/Truck_00/Body/Chassis", 4.0, "haul_truck", "chassis")
    chassis.AddTranslateOp().Set(Gf.Vec3d(1.0, 0.0, 0.0))
    st.GetRootLayer().Save()
    paths = {"terrain": layers / "terrain.usdc", "design": layers / "design.usda", "fleet": layers / "fleet.usda"}
    assets_dir = root / "assets"
    assets_dir.mkdir(exist_ok=True)
    write_machine_asset(assets_dir / "truck.usda")
    # record files (copied by compose to the same relative paths of the scene folder)
    files: dict[str, Path] = {}
    grid_attrs = json.loads((EXAMPLES / "terrain-grid.valid.json").read_text(encoding="utf-8"))
    sources = {
        "terrain/grid.zarr/zarr.json": json.dumps({"zarr_format": 3, "node_type": "group", "attributes": grid_attrs}),
        "terrain/tiles.json": (EXAMPLES / "terrain-tiles.valid.json").read_text(encoding="utf-8"),
        "design/pit-design-report.json": (EXAMPLES / "pit-design-report.valid.json").read_text(encoding="utf-8"),
        "design/road-network.geojson": (EXAMPLES / "road-network.valid.json").read_text(encoding="utf-8"),
    }
    for rel, text in sources.items():
        target = root / "records" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        files[rel] = target
    manifest = json.loads((EXAMPLES / "scene-manifest.valid.json").read_text(encoding="utf-8"))
    records = {k: manifest[k] for k in ("sources", "inputs", "terrain", "design", "textures", "people_route", "site")}
    records["terrain"] = {
        **records["terrain"],
        "grid": {"path": "terrain/grid.zarr/zarr.json", "sha256": sha256_file(files["terrain/grid.zarr/zarr.json"])},
        "tiles": {"path": "terrain/tiles.json", "sha256": sha256_file(files["terrain/tiles.json"])},
    }
    records["design"] = {
        **records["design"],
        "report": {
            "path": "design/pit-design-report.json",
            "sha256": sha256_file(files["design/pit-design-report.json"]),
        },
        "road_network": {
            "path": "design/road-network.geojson",
            "sha256": sha256_file(files["design/road-network.geojson"]),
        },
    }
    return {
        "layers": paths,
        "layer_sha256": {k: sha256_file(v) for k, v in paths.items()},
        "assets": [assets_dir / "truck.usda"],
        "files": files,
        "records": records,
    }


def write_machine_asset(
    path: Path, *, roots: int = 1, masses: tuple[float, float] = (112000.0, 50000.0), cycle: bool = False
) -> Path:
    """A hand-written two-body machine layer: `roots` articulation roots, body masses, optionally a joint cycle."""
    from pxr import UsdGeom, UsdPhysics, UsdSemantics

    st = new_usd_stage(path)
    truck = UsdGeom.Xform.Define(st, "/Truck")
    st.SetDefaultPrim(truck.GetPrim())
    UsdSemantics.LabelsAPI.Apply(truck.GetPrim(), "class").CreateLabelsAttr(["haul_truck"])
    bodies = []
    for name, part, mass in (("Chassis", "chassis", masses[0]), ("DumpBody", "dump_body", masses[1])):
        mesh = define_quad(st, f"/Truck/{name}", 4.0, "haul_truck", part)
        prim = mesh.GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(prim)
        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(mass)
        UsdPhysics.CollisionAPI.Apply(prim)
        UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr("convexHull")
        bodies.append(prim)
    UsdGeom.Scope.Define(st, "/Truck/Joints")
    for i in range(2 if cycle else 1):
        joint = UsdPhysics.RevoluteJoint.Define(st, f"/Truck/Joints/Hinge{i}")
        joint.CreateBody0Rel().SetTargets([bodies[0].GetPath()])
        joint.CreateBody1Rel().SetTargets([bodies[1].GetPath()])
        joint.CreateAxisAttr("Y")
        joint.CreateLowerLimitAttr(0.0)
        joint.CreateUpperLimitAttr(50.0)
        UsdPhysics.LimitAPI.Apply(joint.GetPrim(), "rotY")
        UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "angular")
    if roots >= 1:
        UsdPhysics.ArticulationRootAPI.Apply(truck.GetPrim())
    if roots >= 2:
        UsdPhysics.ArticulationRootAPI.Apply(bodies[0])
    st.GetRootLayer().Save()
    return Path(path)


def make_link(link: Path, target: Path) -> None:
    """A directory link `link` -> `target`: a symbolic link, or a junction on Windows without the symlink privilege."""
    import os
    import subprocess

    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def make_job(
    store: Path,
    stage: str,
    params: dict[str, Any],
    inputs: list[tuple[str, Path]],
    *,
    run_id: str = "20261011T120000Z-scenetest",
    seed: int = 1,
) -> dict[str, Any]:
    """A DC-002-02 job spec for a scene stage: `inputs` are (input name, file path) pairs with their real SHA-256."""
    out = store / "runs" / run_id / "tmp" / stage / "0"
    scratch = store / "scratch" / run_id / stage
    out.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "stage": stage,
        "entry": f"pitstudio_studio.scene.{STAGE_PACKAGE[stage]}",
        "params": params,
        "seed": seed,
        "shard": None,
        "inputs": [{"name": n, "path": Path(p).as_posix(), "sha256": sha256_file(Path(p))} for n, p in inputs],
        "output_dir": out.as_posix(),
        "scratch_dir": scratch.as_posix(),
        "resume": False,
        "rerun": False,
        "profiling": False,
        "profile": {"id": "test-profile", "cpu_slots": 2},
        "vram_fraction": None,
        "nvtx_range": stage,
    }


def mesh_errors(
    rc: np.ndarray, z: np.ndarray, triangles: np.ndarray, heights: np.ndarray
) -> tuple[float, np.ndarray, float]:
    """Brute-force check of a grid-index triangle mesh against its height grid (float64, independent of the mesher).

    `rc` (n, 2) int (row, col) vertex positions on the sample grid, `z` (n,) vertex heights, `triangles` (m, 3).
    Returns (max |mesh - sample| over covered finite samples, covered mask [rows, cols], sum of triangle areas).
    A sample is covered when it lies in the closed triangle (barycentric tolerance 1e-9); the mesh height there is the
    barycentric interpolation of the three vertex heights.
    """
    rows, cols = heights.shape
    covered = np.zeros((rows, cols), dtype=bool)
    worst, area_sum = 0.0, 0.0
    pts = np.stack([rc[:, 1], rc[:, 0]], axis=1).astype(np.float64)  # (x = col, y = row)
    zz = z.astype(np.float64)
    for tri in np.asarray(triangles):
        p = pts[tri]
        h = zz[tri]
        det = (p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (p[1, 1] - p[0, 1])
        area_sum += abs(det) / 2.0
        if det == 0.0:
            continue
        c0, c1 = int(np.floor(p[:, 0].min())), int(np.ceil(p[:, 0].max()))
        r0, r1 = int(np.floor(p[:, 1].min())), int(np.ceil(p[:, 1].max()))
        cc, rr = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
        l1 = ((cc - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (rr - p[0, 1])) / det
        l2 = ((p[1, 0] - p[0, 0]) * (rr - p[0, 1]) - (cc - p[0, 0]) * (p[1, 1] - p[0, 1])) / det
        l0 = 1.0 - l1 - l2
        inside = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9) & (cc < cols) & (rr < rows)
        if not inside.any():
            continue
        ci, ri = cc[inside], rr[inside]
        interp = l0[inside] * h[0] + l1[inside] * h[1] + l2[inside] * h[2]
        sample = heights[ri, ci]
        covered[ri, ci] = True
        finite = np.isfinite(sample)
        if finite.any():
            worst = max(worst, float(np.max(np.abs(interp[finite] - sample[finite]))))
    return worst, covered, area_sum


# --------------------------------------------------------------------------------------------------------------
# Privacy scan (FR-004-41): the test machine's own identifiers, read at test time
# --------------------------------------------------------------------------------------------------------------


def machine_identifiers() -> list[str]:
    import getpass
    import os
    import socket

    ids = {getpass.getuser(), socket.gethostname(), str(Path.home()), os.path.expanduser("~")}
    return sorted(i for i in ids if i and len(i) >= 3)


def has_absolute_path_text(text: str) -> bool:
    """True when `text` contains a drive-letter, UNC or POSIX-home absolute path."""
    import re

    return bool(
        re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[A-Za-z0-9]|(?<![A-Za-z0-9._-])/(home|Users|tmp|var)/", text)
    )
