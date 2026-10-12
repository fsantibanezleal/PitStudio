# Generated from contracts/physics-field.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class Solver(RootModel[Literal["dem", "mpm-newton", "mlsmpm2d", "swe", "dust", "vehicles", "rigid-newton"]]):
    root: Annotated[
        Literal["dem", "mpm-newton", "mlsmpm2d", "swe", "dust", "vehicles", "rigid-newton"],
        Field(
            description="own Warp DEM, Newton implicit MPM, own explicit 2-D MLS-MPM twin, own shallow water, own Lagrangian dust, reduced-order vehicles, Newton rigid bodies"
        ),
    ]


class BenchmarkId(
    RootModel[
        Literal[
            "dem-contact-law",
            "dem-impact",
            "dem-restitution",
            "dem-rolling",
            "dem-slide-roll",
            "dem-beverloo-silo",
            "dem-beverloo-slot",
            "dem-repose",
            "dem-collapse-axi",
            "dem-mass",
            "mpm-newton-collapse-axi",
            "mpm-newton-silo",
            "mpm-newton-mass",
            "mpm-newton-rerun",
            "mlsmpm2d-p2g",
            "mlsmpm2d-collapse-planar",
            "mlsmpm2d-mass",
            "swe-ritter",
            "swe-stoker",
            "swe-lake-at-rest",
            "swe-volume",
            "swe-bingham-sheet",
            "swe-hydrograph",
            "dust-stokes",
            "dust-diffusion",
            "dust-plume",
            "dust-mass-budget",
            "vehicles-steady-speed",
            "vehicles-energy",
            "rigid-newton-incline",
        ]
    ]
):
    root: Annotated[
        Literal[
            "dem-contact-law",
            "dem-impact",
            "dem-restitution",
            "dem-rolling",
            "dem-slide-roll",
            "dem-beverloo-silo",
            "dem-beverloo-slot",
            "dem-repose",
            "dem-collapse-axi",
            "dem-mass",
            "mpm-newton-collapse-axi",
            "mpm-newton-silo",
            "mpm-newton-mass",
            "mpm-newton-rerun",
            "mlsmpm2d-p2g",
            "mlsmpm2d-collapse-planar",
            "mlsmpm2d-mass",
            "swe-ritter",
            "swe-stoker",
            "swe-lake-at-rest",
            "swe-volume",
            "swe-bingham-sheet",
            "swe-hydrograph",
            "dust-stokes",
            "dust-diffusion",
            "dust-plume",
            "dust-mass-budget",
            "vehicles-steady-speed",
            "vehicles-energy",
            "rigid-newton-incline",
        ],
        Field(description="physics benchmark ids; the prefix is the solver id"),
    ]


class Twin(RootModel[Literal["dem-pile", "mlsmpm2d-collapse", "swe-dam-break", "dust-release"]]):
    root: Annotated[
        Literal["dem-pile", "mlsmpm2d-collapse", "swe-dam-break", "dust-release"],
        Field(description="browser-twin scenario of FR-005-22"),
    ]


class Status(RootModel[Literal["verified", "unverified", "calibrated", "reduced", "assumed"]]):
    root: Annotated[
        Literal["verified", "unverified", "calibrated", "reduced", "assumed"],
        Field(
            description="verification status of a value: verified (primary source read), unverified (secondary or unreadable source), calibrated (fitted), reduced (deliberately lowered Young's modulus, FR-005-09), assumed (modelling choice)"
        ),
    ]


class Vec3MItem(RootModel[float]):
    root: Annotated[float, Field(ge=-100000.0, le=100000.0)]


class Vec3M(RootModel[list[Vec3MItem]]):
    root: Annotated[list[Vec3MItem], Field(max_length=3, min_length=3)]


class OrificeMItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000.0)]


class AspectRatio(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=50.0)]


class Geometry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    shape: Literal[
        "two-body",
        "plane",
        "incline",
        "silo-cylinder",
        "slot-quasi2d",
        "column-axisymmetric",
        "column-planar",
        "box",
        "channel",
        "benched-crop",
        "terrain-crop",
        "open-field",
        "grade-segment",
        "road-network",
    ]
    domain_min_m: Vec3M
    domain_max_m: Vec3M
    diameter_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    height_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    width_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    thickness_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    length_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    orifice_m: Annotated[list[OrificeMItem] | None, Field(max_length=16, min_length=1)] = None
    aspect_ratios: Annotated[list[AspectRatio] | None, Field(max_length=16, min_length=1)] = None
    incline_deg: Annotated[float | None, Field(ge=0.0, lt=90.0)] = None
    bed_slope: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    grade_pct: Annotated[float | None, Field(ge=-30.0, le=30.0)] = None
    periodic_axes: Annotated[list[Literal["x", "y", "z"]] | None, Field(max_length=3)] = None
    outflow: Annotated[
        list[Literal["x-min", "x-max", "y-min", "y-max", "z-min", "z-max", "orifice"]] | None,
        Field(max_length=7),
    ] = None


class Counts(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    particles: Annotated[int | None, Field(ge=1, le=100000000)] = None
    cells_x: Annotated[int | None, Field(ge=1, le=16384)] = None
    cells_y: Annotated[int | None, Field(ge=1, le=16384)] = None
    cells_z: Annotated[int | None, Field(ge=1, le=1024)] = None
    vehicles: Annotated[int | None, Field(ge=1, le=4096)] = None


class TimeStep1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dt_s: Annotated[
        float | None,
        Field(
            description="fixed step; the shallow-water solver uses the CFL step instead (FR-005-23)",
            gt=0.0,
            le=10.0,
        ),
    ] = None
    steps: Annotated[int, Field(ge=1, le=1000000000)]
    end_time_s: Annotated[float | None, Field(gt=0.0, le=10000000.0)] = None


class TimeStep2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dt_s: Annotated[
        float | None,
        Field(
            description="fixed step; the shallow-water solver uses the CFL step instead (FR-005-23)",
            gt=0.0,
            le=10.0,
        ),
    ] = None
    steps: Annotated[int | None, Field(ge=1, le=1000000000)] = None
    end_time_s: Annotated[float, Field(gt=0.0, le=10000000.0)]


class TimeStep(RootModel[TimeStep1 | TimeStep2]):
    root: TimeStep1 | TimeStep2


class Output(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    every_steps: Annotated[int, Field(ge=1, le=1000000000)]
    fields: bool
    replay: bool
    replay_fps: Annotated[float | None, Field(gt=0.0, le=240.0)] = None
    shard_bytes_max: Annotated[int | None, Field(description="replay shard cap (FR-005-45)", ge=1, le=10000000)] = None


class Hydrograph(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    volume_m3: Annotated[float, Field(gt=0.0, le=10000000000.0)]
    peak_m3_s: Annotated[float, Field(gt=0.0, le=10000000.0)]
    peak_fraction: Annotated[float, Field(gt=0.0, lt=1.0)]


class Breach(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    y_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    width_m: Annotated[float, Field(gt=0.0, le=10000.0)]


class DustSource(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["continuous", "instantaneous"]
    x_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    y_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    z_m: Annotated[float, Field(ge=-5000.0, le=5000.0)]
    rate_kg_s: Annotated[float | None, Field(ge=0.0, le=1000000.0)] = None
    mass_kg: Annotated[float | None, Field(ge=0.0, le=1000000000.0)] = None
    start_s: Annotated[float, Field(ge=0.0, le=10000000.0)]
    end_s: Annotated[float | None, Field(gt=0.0, le=10000000.0)] = None


class WindM(RootModel[float]):
    root: Annotated[float, Field(ge=-100.0, le=100.0)]


class SizeMItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=100.0)]


class RigidNewtonBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    friction_coefficient: Annotated[float, Field(ge=0.0, le=10.0)]
    mass_kg: Annotated[float, Field(gt=0.0, le=2000000.0)]
    size_m: Annotated[list[SizeMItem], Field(max_length=3, min_length=3)]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class HttpsUrl(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=2048,
            pattern="^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$",
        ),
    ]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Verdict(RootModel[Literal["pass", "fail", "not run"]]):
    root: Literal["pass", "fail", "not run"]


class Tolerance(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Annotated[
        Literal["abs", "rel", "interval", "factor"],
        Field(
            description="abs: |measured - oracle| <= value; rel: <= value x |oracle|; interval: lower <= measured <= upper; factor: lower <= measured / oracle <= upper"
        ),
    ]
    value: Annotated[float | None, Field(ge=0.0, le=1000000000000.0)] = None
    lower: float | None = None
    upper: float | None = None


class Unit(
    RootModel[
        Literal[
            "1",
            "1/s",
            "s",
            "m",
            "m2",
            "m3",
            "m/s",
            "m/s2",
            "m2/s",
            "m3/s",
            "kg",
            "kg/s",
            "kg/m2",
            "kg/m3",
            "Pa",
            "Pa.s",
            "N",
            "N/m",
            "N.m",
            "W",
            "J",
            "deg",
            "rad/s",
        ]
    ]
):
    root: Annotated[
        Literal[
            "1",
            "1/s",
            "s",
            "m",
            "m2",
            "m3",
            "m/s",
            "m/s2",
            "m2/s",
            "m3/s",
            "kg",
            "kg/s",
            "kg/m2",
            "kg/m3",
            "Pa",
            "Pa.s",
            "N",
            "N/m",
            "N.m",
            "W",
            "J",
            "deg",
            "rad/s",
        ],
        Field(description="UCUM case-sensitive unit codes; 1 is dimensionless (also counts)"),
    ]


class ParamKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class Parameters(RootModel[str]):
    root: Annotated[str, Field(max_length=200)]


class Overhead(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    solver: Literal["dem", "mlsmpm2d", "swe", "dust", "vehicles"]
    device: Literal["cpu", "cuda"]
    factor: Annotated[
        float,
        Field(
            description="wall time in deterministic mode divided by wall time in the default mode",
            gt=0.0,
            le=1000.0,
        ),
    ]


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class UtcTimestamp(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=32,
            pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\\.[0-9]{1,6})?Z$",
        ),
    ]


class ShapeItem(RootModel[int]):
    root: Annotated[int, Field(ge=1, le=100000000)]


class OriginMItem(RootModel[float]):
    root: Annotated[float, Field(ge=-100000.0, le=100000.0)]


class Grid(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["regular-2d", "regular-3d", "particles"]
    shape: Annotated[
        list[ShapeItem],
        Field(
            description="spatial shape: (y, x), (z, y, x) or (particle)",
            max_length=3,
            min_length=1,
        ),
    ]
    cell_size_m: Annotated[float | None, Field(description="horizontal cell size", gt=0.0, le=1000.0)] = None
    cell_height_m: Annotated[
        float | None,
        Field(description="vertical cell size of a 3-D grid", gt=0.0, le=1000.0),
    ] = None
    origin_m: Annotated[
        list[OriginMItem] | None,
        Field(
            description="site-local (x, y) or (x, y, z) of the first cell centre",
            max_length=3,
            min_length=2,
        ),
    ] = None


class Epsg(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description="EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)",
            ge=6328,
            le=6348,
        ),
    ]


class Epsg1(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description="EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)",
            ge=25828,
            le=25838,
        ),
    ]


class Epsg2(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description="EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)",
            ge=26901,
            le=26923,
        ),
    ]


class Epsg3(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description="EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)",
            ge=32601,
            le=32660,
        ),
    ]


class Epsg4(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description="EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)",
            ge=32701,
            le=32760,
        ),
    ]


class SiteOrigin(BaseModel):
    """
    site origin of the site-local frame (FR-004-02)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    epsg: Annotated[
        Epsg | Epsg1 | Epsg2 | Epsg3 | Epsg4,
        Field(description="EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)"),
    ]
    easting_m: Annotated[float, Field(ge=100000.0, le=900000.0)]
    northing_m: Annotated[float, Field(ge=0.0, le=10000000.0)]
    z0_m: Annotated[
        float,
        Field(
            description="origin elevation z0 in the vertical datum of the inputs, m",
            ge=-500.0,
            le=9000.0,
        ),
    ]


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class SpdxId(
    RootModel[
        Literal[
            "LicenseRef-USGov-PD",
            "CC0-1.0",
            "DL-DE-ZERO-2.0",
            "CC-BY-4.0",
            "LicenseRef-Copernicus-CLMS",
            "CC-BY-SA-3.0",
            "CC-BY-SA-4.0",
            "Apache-2.0",
            "MIT",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "MPL-2.0",
            "LGPL-2.1-or-later",
            "LicenseRef-TOST-1.0",
            "LicenseRef-NVIDIA-Open-Model",
            "LicenseRef-NVIDIA-SLA",
            "LicenseRef-NvidiaProprietary",
            "LicenseRef-NVIDIA-Omniverse",
            "LicenseRef-TensorRT-SLA",
            "LicenseRef-TensorRT-RTX-SLA",
        ]
    ]
):
    root: Literal[
        "LicenseRef-USGov-PD",
        "CC0-1.0",
        "DL-DE-ZERO-2.0",
        "CC-BY-4.0",
        "LicenseRef-Copernicus-CLMS",
        "CC-BY-SA-3.0",
        "CC-BY-SA-4.0",
        "Apache-2.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "MPL-2.0",
        "LGPL-2.1-or-later",
        "LicenseRef-TOST-1.0",
        "LicenseRef-NVIDIA-Open-Model",
        "LicenseRef-NVIDIA-SLA",
        "LicenseRef-NvidiaProprietary",
        "LicenseRef-NVIDIA-Omniverse",
        "LicenseRef-TensorRT-SLA",
        "LicenseRef-TensorRT-RTX-SLA",
    ]


class ClassLabel(
    RootModel[
        Literal[
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
    ]
):
    root: Annotated[
        Literal[
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
        ],
        Field(description="closed class-label vocabulary (SemanticsLabelsAPI `class`, FR-004-25)"),
    ]


class MachineClass(
    RootModel[Literal["haul_truck", "shovel", "excavator", "wheel_loader", "water_truck", "light_vehicle", "crusher"]]
):
    root: Annotated[
        Literal["haul_truck", "shovel", "excavator", "wheel_loader", "water_truck", "light_vehicle", "crusher"],
        Field(description="class labels of the machines st30_assets builds (FR-004-24)"),
    ]


class PartLabel(
    RootModel[
        Literal[
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
    ]
):
    root: Annotated[
        Literal[
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
        ],
        Field(description="closed part-label vocabulary for articulated sub-parts (FR-004-25)"),
    ]


class SceneSourceId(
    RootModel[
        Literal[
            "usgs-3dep-bingham",
            "ot-mckinley-2023",
            "nrw-hambach-dgm1",
            "tang-werner-footprint",
            "maus-v2",
            "polyhaven",
            "ambientcg",
            "makehuman-exports",
        ]
    ]
):
    root: Annotated[
        Literal[
            "usgs-3dep-bingham",
            "ot-mckinley-2023",
            "nrw-hambach-dgm1",
            "tang-werner-footprint",
            "maus-v2",
            "polyhaven",
            "ambientcg",
            "makehuman-exports",
        ],
        Field(description="data/sources.yaml ids a scene may use (closed list, FR-004-40)"),
    ]


class VariantName(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="a free variant name (pushback, scenario); a USD identifier",
            max_length=32,
            pattern="^[a-z][a-z0-9_]{0,31}$",
        ),
    ]


class TimeOfDay(RootModel[Literal["dawn", "morning", "noon", "afternoon", "dusk", "night"]]):
    root: Literal["dawn", "morning", "noon", "afternoon", "dusk", "night"]


class Weather(RootModel[Literal["clear", "overcast", "rain", "dust", "fog"]]):
    root: Literal["clear", "overcast", "rain", "dust", "fog"]


class LodName(RootModel[Literal["lod0", "lod1", "lod2"]]):
    root: Annotated[
        Literal["lod0", "lod1", "lod2"],
        Field(description="name of a `lod` variant; one per terrain LOD (FR-004-08)"),
    ]


class LodIndex(RootModel[Literal[0, 1, 2]]):
    root: Annotated[
        Literal[0, 1, 2],
        Field(description="terrain level of detail (FR-004-06: LOD 0-2)"),
    ]


class Site(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str,
        Field(max_length=128, min_length=1, pattern="^[A-Za-z0-9][A-Za-z0-9 ,.'-]{0,127}$"),
    ]
    origin: SiteOrigin
    polygon_sources: Annotated[
        list[Literal["tang-werner-footprint", "maus-v2"]],
        Field(
            description="mine-polygon datasets for FR-004-15",
            max_length=2,
            min_length=1,
        ),
    ]


class TerrainSource(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Literal["usgs-3dep-bingham", "ot-mckinley-2023", "nrw-hambach-dgm1"]
    kind: Literal["dem", "laz"]
    project: Annotated[
        str,
        Field(
            description="3DEP or survey project name (one project per terrain grid)",
            max_length=128,
            min_length=1,
        ),
    ]
    epoch: Annotated[int, Field(description="survey year", ge=1990, le=2100)]
    optional: Annotated[bool, Field(description="FR-004-09: optional sources may end 'not run'")]


class LodSpec(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lod: LodIndex
    max_error_m: Annotated[
        float,
        Field(
            description="RTIN vertical error bound (FR-004-06, P-004-01 domain 0.05-8 m)",
            ge=0.05,
            le=8.0,
        ),
    ]
    skirt_depth_m: Annotated[
        float,
        Field(
            description="skirt depth (FR-004-07; default 2 x max_error)",
            gt=0.0,
            le=16.0,
        ),
    ]


class Transformation(BaseModel):
    """
    a CRS or datum transformation the recipe declares (FR-004-11)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    component: Literal["horizontal", "vertical"]
    from_epsg: Annotated[int, Field(ge=1024, le=32767)]
    to_epsg: Annotated[int, Field(ge=1024, le=32767)]


class AoiXyMItemItem(RootModel[float]):
    root: Annotated[
        float,
        Field(
            description="site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)",
            ge=-100000.0,
            le=100000.0,
        ),
    ]


class AoiXyMItem(RootModel[list[AoiXyMItemItem]]):
    root: Annotated[list[AoiXyMItemItem], Field(max_length=2, min_length=2)]


class Terrain(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sources: Annotated[list[TerrainSource], Field(max_length=3, min_length=1)]
    cell_size_m: Annotated[
        float,
        Field(description="grid cell size (FR-004-04; default 1.0 m)", ge=0.25, le=10.0),
    ]
    max_fill_cells: Annotated[
        int,
        Field(
            description="largest hole filled (FR-004-05; default and cap 16)",
            ge=0,
            le=16,
        ),
    ]
    max_nodata_frac: Annotated[
        float,
        Field(
            description="largest nodata fraction after filling (FR-004-12; default 0.05)",
            ge=0.0,
            le=0.05,
        ),
    ]
    max_cells: Annotated[
        int,
        Field(description="grid cell cap (FR-004-13; default 1.0e8)", ge=1, le=100000000),
    ]
    aoi_xy_m: Annotated[
        list[AoiXyMItem],
        Field(
            description="AOI polygon vertices [x, y] in the site frame, m; >= 3 vertices (FR-004-13)",
            max_length=1024,
            min_length=3,
        ),
    ]
    lods: Annotated[list[LodSpec], Field(max_length=3, min_length=1)]
    transformations: Annotated[list[Transformation] | None, Field(max_length=8)] = None


class BenchHeightM(BaseModel):
    """
    bench height H, m (hard domain [5, 30])
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=5.0, le=30.0)]
    code_min: Annotated[float, Field(ge=5.0, le=30.0)]
    code_max: Annotated[float, Field(ge=5.0, le=30.0)]
    citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]
    verification: Literal["verified", "unverified"]


class FaceAngleDeg(BaseModel):
    """
    bench face angle alpha, degrees (hard domain [40, 85])
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=40.0, le=85.0)]
    code_min: Annotated[float, Field(ge=40.0, le=85.0)]
    code_max: Annotated[float, Field(ge=40.0, le=85.0)]
    citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]
    verification: Literal["verified", "unverified"]


class BermWidthM(BaseModel):
    """
    berm width b, m (hard domain [3, 60])
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=3.0, le=60.0)]
    code_min: Annotated[float, Field(ge=3.0, le=60.0)]
    code_max: Annotated[float, Field(ge=3.0, le=60.0)]
    citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]
    verification: Literal["verified", "unverified"]


class RampGradePct(BaseModel):
    """
    ramp grade g, percent rise over run (hard domain [0, 15])
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=15.0)]
    code_min: Annotated[float, Field(ge=0.0, le=15.0)]
    code_max: Annotated[float, Field(ge=0.0, le=15.0)]
    citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]
    verification: Literal["verified", "unverified"]


class RampWidthM(BaseModel):
    """
    ramp width W, m (hard domain [8, 60])
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=8.0, le=60.0)]
    code_min: Annotated[float, Field(ge=8.0, le=60.0)]
    code_max: Annotated[float, Field(ge=8.0, le=60.0)]
    citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]
    verification: Literal["verified", "unverified"]


class WindrowHeightM(BaseModel):
    """
    windrow height, m (hard domain (0, 5])
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=5.0)]
    code_min: Annotated[float, Field(gt=0.0, le=5.0)]
    code_max: Annotated[float, Field(gt=0.0, le=5.0)]
    citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]
    verification: Literal["verified", "unverified"]


class Design(BaseModel):
    """
    design parameters with their design-code ranges and citations (FR-004-16 ... FR-004-22)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    outline_source: Literal["rim-contour", "upstream-shell"]
    rim_z_m: Annotated[
        float | None,
        Field(
            description="site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)",
            ge=-5000.0,
            le=5000.0,
        ),
    ] = None
    floor_z_m: Annotated[
        float,
        Field(
            description="site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)",
            ge=-5000.0,
            le=5000.0,
        ),
    ]
    bench_height_m: Annotated[BenchHeightM, Field(description="bench height H, m (hard domain [5, 30])")]
    face_angle_deg: Annotated[
        FaceAngleDeg,
        Field(description="bench face angle alpha, degrees (hard domain [40, 85])"),
    ]
    berm_width_m: Annotated[BermWidthM, Field(description="berm width b, m (hard domain [3, 60])")]
    ramp_grade_pct: Annotated[
        RampGradePct,
        Field(description="ramp grade g, percent rise over run (hard domain [0, 15])"),
    ]
    ramp_width_m: Annotated[RampWidthM, Field(description="ramp width W, m (hard domain [8, 60])")]
    windrow_height_m: Annotated[WindrowHeightM, Field(description="windrow height, m (hard domain (0, 5])")]


class Asset(BaseModel):
    """
    one machine model (FR-004-24, FR-004-27)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    class_label: MachineClass
    length_m: Annotated[float, Field(gt=0.0, le=50.0)]
    width_m: Annotated[float, Field(gt=0.0, le=50.0)]
    height_m: Annotated[float, Field(gt=0.0, le=50.0)]
    mass_kg: Annotated[float, Field(gt=0.0, le=2000000.0)]
    mid_axle_height_m: Annotated[
        float | None,
        Field(description="mid-axle height (30 CFR 56.9300(b), FR-004-18)", gt=0.0, le=5.0),
    ] = None
    dimensions_citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]
    mass_citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]


class Part(BaseModel):
    """
    one rigid body of an asset and the joint to its parent (FR-004-24, FR-004-27)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    asset: Slug
    id: Slug
    part: PartLabel
    parent: Annotated[Slug | None, Field(description="parent part id; null for the articulation root")]
    joint: Literal["revolute", "prismatic"] | None = None
    axis: Literal["X", "Y", "Z"] | None = None
    lower_deg: Annotated[float | None, Field(ge=-360.0, le=360.0)] = None
    upper_deg: Annotated[float | None, Field(ge=-360.0, le=360.0)] = None
    lower_m: Annotated[float | None, Field(ge=-50.0, le=50.0)] = None
    upper_m: Annotated[float | None, Field(ge=-50.0, le=50.0)] = None
    mass_kg: Annotated[float, Field(gt=0.0, le=2000000.0)]
    length_m: Annotated[float, Field(gt=0.0, le=50.0)]
    width_m: Annotated[float, Field(gt=0.0, le=50.0)]
    height_m: Annotated[float, Field(gt=0.0, le=50.0)]
    exclude_from_articulation: Annotated[
        bool | None,
        Field(description="true for a joint that closes a kinematic loop (FR-004-24)"),
    ] = None
    citation: Annotated[
        str,
        Field(
            description="source of the value (document, table or page); at most 256 characters (FR-004-40)",
            max_length=256,
            min_length=1,
        ),
    ]


class FleetEntry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset: Slug
    count: Annotated[int, Field(ge=1, le=64)]


class Material(BaseModel):
    """
    a UsdPreviewSurface material: CC0 textures from a source, or our own (CC-BY-4.0) (FR-004-26)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    source: Literal["polyhaven", "ambientcg"] | None
    spdx: Literal[
        "LicenseRef-USGov-PD",
        "CC0-1.0",
        "DL-DE-ZERO-2.0",
        "CC-BY-4.0",
        "LicenseRef-Copernicus-CLMS",
        "CC-BY-SA-3.0",
        "CC-BY-SA-4.0",
        "Apache-2.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "MPL-2.0",
        "LGPL-2.1-or-later",
        "LicenseRef-TOST-1.0",
        "LicenseRef-NVIDIA-Open-Model",
        "LicenseRef-NVIDIA-SLA",
        "LicenseRef-NvidiaProprietary",
        "LicenseRef-NVIDIA-Omniverse",
        "LicenseRef-TensorRT-SLA",
        "LicenseRef-TensorRT-RTX-SLA",
        "CC0-1.0",
        "CC-BY-4.0",
    ]


class Labels(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    classes: Annotated[list[ClassLabel], Field(max_length=15, min_length=1)]
    parts: Annotated[list[PartLabel], Field(max_length=18)]


class Variants(BaseModel):
    """
    variant names per variant set; the first name is the default selection (FR-004-29)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    pushback: Annotated[list[VariantName], Field(max_length=16, min_length=1)]
    scenario: Annotated[list[VariantName], Field(max_length=16, min_length=1)]
    time_of_day: Annotated[list[TimeOfDay], Field(max_length=6, min_length=1)]
    weather: Annotated[list[Weather], Field(max_length=5, min_length=1)]
    lod: Annotated[list[LodName], Field(max_length=3, min_length=1)]


class RuleId(RootModel[str]):
    root: Annotated[str, Field(max_length=128, pattern="^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]


class Waiver(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rule: RuleId
    reason: Annotated[str, Field(max_length=256, min_length=10)]


class Validation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    waivers: Annotated[list[Waiver] | None, Field(max_length=32)] = None


class CrsRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    epsg: Annotated[
        int | None,
        Field(
            description="EPSG code read from the file; null when none exists",
            ge=1024,
            le=32767,
        ),
    ]
    wkt: Annotated[
        str | None,
        Field(
            description="WKT read from the file; required when no EPSG code exists",
            max_length=8192,
            min_length=1,
        ),
    ] = None


class LinearUnit(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["metre", "us-survey-foot", "international-foot"]
    factor_to_m: Annotated[
        float,
        Field(description="factor applied to reach metres (FR-004-03)", gt=0.0, le=1.0),
    ]


class TimeAxis(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Annotated[
        Literal["series", "reduced", "static"],
        Field(description="series: a time dimension; reduced: maps over [start_s, end_s]; static: time-invariant"),
    ]
    start_s: Annotated[float | None, Field(ge=0.0, le=10000000.0)] = None
    end_s: Annotated[float | None, Field(ge=0.0, le=10000000.0)] = None
    step_s: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    count: Annotated[int | None, Field(ge=1, le=1000000)] = None


class Variable(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal[
        "depth",
        "momentum_x",
        "momentum_y",
        "velocity_x",
        "velocity_y",
        "velocity_z",
        "bed_elevation",
        "arrival_time",
        "max_depth",
        "max_speed",
        "concentration",
        "deposition",
        "wind_u",
        "wind_v",
        "wind_w",
        "position_x",
        "position_y",
        "position_z",
        "radius",
        "mass",
        "particle_id",
    ]
    unit: Unit
    dtype: Literal["float32", "float64", "int32", "int64", "uint32", "uint8"]
    dims: Annotated[
        list[Literal["time", "z", "y", "x", "particle"]],
        Field(max_length=4, min_length=1),
    ]
    fill_value: Annotated[
        float | Literal["NaN"] | None,
        Field(description="Zarr v3 JSON fill value; NaN marks never-reached cells of arrival_time"),
    ] = None
    description: Annotated[str | None, Field(max_length=200)] = None


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Quantity(BaseModel):
    """
    a material or vehicle value with its citation and verification status; the unit is the suffix of the field name
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: float
    status: Status
    source: Annotated[
        str | None,
        Field(description="citation with table or page", max_length=300, min_length=3),
    ] = None
    url: HttpsUrl | None = None
    note: Annotated[str | None, Field(max_length=300, min_length=3)] = None


class DensityKgM3(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=25000.0)]


class YoungsModulusPa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1000000000000.0)]


class YoungsModulusRealPa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1000000000000.0)]


class PoissonRatio(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=-1.0, lt=0.5)]


class Restitution(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class FrictionStatic(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=10.0)]


class FrictionRolling(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=10.0)]


class DiameterM(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=10.0)]


class DiameterMinM(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=10.0)]


class DiameterMaxM(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=10.0)]


class ReposeTargetDeg(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, lt=90.0)]


class FrictionCoefficient(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=10.0)]


class YieldPressurePa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000000000.0)]


class ViscosityPaS(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000000.0)]


class FrictionAngleDeg(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, lt=90.0)]


class CohesionPa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000000.0)]


class YieldStressPa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000.0)]


class BinghamViscosityPaS(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000.0)]


class ParticleRadiusM(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=0.001)]


class DynamicViscosityPaS(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class MaterialCard(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: Annotated[str | None, Field(max_length=120, min_length=1)] = None
    model: Literal["dem-sphere", "mpm-granular", "mpm-drucker-prager-2d", "bingham-tailings", "dust-particle", "air"]
    density_kg_m3: DensityKgM3 | None = None
    youngs_modulus_pa: YoungsModulusPa | None = None
    youngs_modulus_real_pa: YoungsModulusRealPa | None = None
    poisson_ratio: PoissonRatio | None = None
    restitution: Restitution | None = None
    friction_static: FrictionStatic | None = None
    friction_rolling: FrictionRolling | None = None
    diameter_m: DiameterM | None = None
    diameter_min_m: DiameterMinM | None = None
    diameter_max_m: DiameterMaxM | None = None
    repose_target_deg: ReposeTargetDeg | None = None
    repose_method: Literal["lifted-cylinder", "poured-cone"] | None = None
    friction_coefficient: FrictionCoefficient | None = None
    yield_pressure_pa: YieldPressurePa | None = None
    viscosity_pa_s: ViscosityPaS | None = None
    friction_angle_deg: FrictionAngleDeg | None = None
    cohesion_pa: CohesionPa | None = None
    yield_stress_pa: YieldStressPa | None = None
    bingham_viscosity_pa_s: BinghamViscosityPaS | None = None
    particle_radius_m: ParticleRadiusM | None = None
    dynamic_viscosity_pa_s: DynamicViscosityPaS | None = None


class MassKg(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=2000000.0)]


class PowerW(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=20000000.0)]


class Efficiency(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class TractionCoefficient(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=2.0)]


class DriveWeightFraction(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class RollingResistancePct(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=30.0)]


class RetarderPowerW(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=20000000.0)]


class RetarderEfficiency(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class DragCoefficient(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=5.0)]


class FrontalAreaM2(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=200.0)]


class VehicleCard(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: Annotated[str | None, Field(max_length=120, min_length=1)] = None
    mass_kg: MassKg
    power_w: PowerW
    efficiency: Efficiency
    traction_coefficient: TractionCoefficient
    drive_weight_fraction: DriveWeightFraction
    rolling_resistance_pct: RollingResistancePct
    retarder_power_w: RetarderPowerW
    retarder_efficiency: RetarderEfficiency
    drag_coefficient: DragCoefficient
    frontal_area_m2: FrontalAreaM2


class DemBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    material: Slug
    contact_capacity: Annotated[
        int,
        Field(
            description="per-particle contact-list capacity (FR-005-06, default 12)",
            ge=1,
            le=64,
        ),
    ]
    rayleigh_fraction: Annotated[
        float,
        Field(
            description="f_R of the time-step guard (FR-005-08, default 0.2)",
            gt=0.0,
            le=1.0,
        ),
    ]


class MpmNewtonBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    material: Slug
    voxel_size_m: Annotated[float, Field(gt=0.0, le=10.0)]
    grid_type: Literal["sparse", "fixed", "dense"]
    max_iterations: Annotated[int, Field(ge=1, le=100000)]
    tolerance: Annotated[float, Field(gt=0.0, lt=1.0)]


class Mlsmpm2dBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    material: Slug
    grid_cells: Annotated[int, Field(description="cells per axis of the square grid", ge=16, le=4096)]
    particles_per_cell: Annotated[int, Field(ge=1, le=64)]


class SweBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rheology: Literal["frictionless", "bingham"]
    material: Slug | None = None
    cfl: Annotated[
        float,
        Field(description="C_CFL in (0, 0.5] (FR-005-23, default 0.45)", gt=0.0, le=0.5),
    ]
    h_dry_m: Annotated[float, Field(gt=0.0, le=1.0)]
    h_thr_m: Annotated[float, Field(gt=0.0, le=100.0)]
    boundary: Literal["closed", "open"]
    initial: Literal["dam-break", "lake-at-rest", "dry", "sheet-flow"]
    dam_x_m: Annotated[float | None, Field(ge=-100000.0, le=100000.0)] = None
    depth_left_m: Annotated[float | None, Field(ge=0.0, le=1000.0)] = None
    depth_right_m: Annotated[float | None, Field(ge=0.0, le=1000.0)] = None
    surface_z_m: Annotated[float | None, Field(ge=-5000.0, le=5000.0)] = None
    inflow_depth_m: Annotated[float | None, Field(ge=0.0, le=1000.0)] = None
    hydrograph: Hydrograph | None = None
    breach: Breach | None = None


class DustBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    particle_material: Slug
    air_material: Slug
    diffusivity_m2_s: Annotated[float, Field(description="K >= 0 (FR-005-39)", ge=0.0, le=10000.0)]
    settling: bool
    ground: Literal["terrain", "reflecting", "none"]
    wind: Literal["uniform", "gridded"]
    wind_m_s: Annotated[list[WindM] | None, Field(max_length=3, min_length=3)] = None
    sources: Annotated[list[DustSource], Field(max_length=64, min_length=1)]


class VehiclesBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    road: Annotated[
        Literal["grade-segment", "network"],
        Field(description="a constant-grade segment (geometry.grade_pct) or the road network (DC-004-06)"),
    ]
    air_density_kg_m3: Annotated[float, Field(gt=0.0, le=2.0)]
    fleet: Annotated[list[Slug], Field(max_length=64, min_length=1)]


class Stamp(BaseModel):
    """
    the stamp every rollout output carries: the benchmark report of its solver version and its verdict (FR-005-47)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    report_id: ArtefactId
    report_sha256: Sha256
    verdict: Verdict


class MaterialRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    card_sha256: Annotated[
        Sha256,
        Field(description="SHA-256 of the RFC 8785 canonical JSON of the material card"),
    ]
    youngs_modulus_pa: Annotated[float | None, Field(gt=0.0, le=1000000000000.0)] = None
    youngs_modulus_real_pa: Annotated[float | None, Field(gt=0.0, le=1000000000000.0)] = None


class Oracle(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["analytical", "published", "reference-implementation", "hand-calculation", "material-card"]
    source: Annotated[
        str,
        Field(
            description="citation with section, table or page",
            max_length=300,
            min_length=3,
        ),
    ]
    url: HttpsUrl | None = None
    status: Status


class Check(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    quantity: ParamKey
    unit: Unit
    measured: float
    oracle: float | None
    tolerance: Tolerance
    pass_: Annotated[bool, Field(alias="pass")]


class Column(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: ParamKey
    unit: Unit
    dtype: Literal["float32", "float64", "int32", "int64", "uint32", "uint64", "bool"]
    role: Annotated[
        Literal["time", "step", "observable", "budget", "parameter"],
        Field(description="time axis, step index, observable, budget series term, swept parameter"),
    ]
    description: Annotated[str | None, Field(max_length=200)] = None


class Row(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    benchmark: BenchmarkId
    solver: Solver
    solver_version: Version
    material: MaterialRef | None
    parameters: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), float | bool | Parameters],
        Field(max_length=64),
    ]
    oracle: Oracle
    checks: Annotated[list[Check], Field(max_length=64)]
    verdict: Verdict
    reason: Annotated[str | None, Field(max_length=300, min_length=3)] = None
    gpu_only: bool
    deterministic: bool
    outputs_sha256: Annotated[
        Sha256 | None,
        Field(description="SHA-256 of the run's outputs, reproduced on a re-run in deterministic mode (FR-005-48)"),
    ] = None


class CrsRecord(BaseModel):
    """
    CRS and axis units read from the input's own metadata (FR-004-01, FR-004-03)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    horizontal: CrsRef
    vertical: CrsRef
    horizontal_unit: LinearUnit
    vertical_unit: LinearUnit


class Input(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    role: Literal["terrain-grid", "wind-field", "initial-state"]
    path: Relpath
    sha256: Sha256


class Crs(BaseModel):
    """
    site-local frame (x east, y north, z up, metres) relative to the site origin of the scene (DC-004-01, DC-004-03), or the local frame of a synthetic benchmark
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    frame: Literal["site-enu", "benchmark-local"]
    origin: SiteOrigin | None = None
    source: Annotated[
        CrsRecord | None,
        Field(description="CRS record of the terrain inputs, copied from the terrain grid"),
    ] = None


class PhysicsFieldStoreMetadata(BaseModel):
    """
    Root-group attributes of a Zarr v3 field store (grid, CRS record, time axis, variables with units) written by st50_physics or supplied as a wind field (DC-005-02, spec 005-physics).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    kind: Literal["physics-field"]
    schema_version: SchemaVersion
    field_set: Annotated[
        Literal["swe-state", "c2-maps", "dust-concentration", "dust-deposition", "wind", "particle-state"],
        Field(
            description="shallow-water state, C2 maps (FR-005-30), dust concentration or deposition, wind field (FR-005-33), particle state"
        ),
    ]
    scenario: Slug | None = None
    run_id: RunId | None = None
    solver: Solver | None = None
    solver_version: Version | None = None
    seed: Annotated[int | None, Field(ge=0, le=9223372036854775807)] = None
    source: Annotated[
        str | None,
        Field(description="origin of a supplied wind field", max_length=300, min_length=3),
    ] = None
    grid: Grid
    crs: Crs
    time: TimeAxis
    variables: Annotated[list[Variable], Field(max_length=32, min_length=1)]
    h_thr_m: Annotated[
        float | None,
        Field(
            description="depth threshold of the C2 maps (FR-005-30, default 0.05 m)",
            gt=0.0,
            le=100.0,
        ),
    ] = None
    inundated_area_m2: Annotated[float | None, Field(ge=0.0, le=100000000000.0)] = None
    inputs: Annotated[list[Input] | None, Field(max_length=8)] = None
    stamp: Stamp | None = None
