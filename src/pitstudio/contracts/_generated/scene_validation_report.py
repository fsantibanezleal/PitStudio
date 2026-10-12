# Generated from contracts/scene-validation-report.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


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


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


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


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class PrimPath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="absolute USD prim path",
            max_length=1024,
            pattern="^/[A-Za-z_][A-Za-z0-9_]{0,127}(/[A-Za-z_][A-Za-z0-9_]{0,127}){0,31}$",
        ),
    ]


class TransformItem(RootModel[float]):
    root: Annotated[float, Field(ge=-100000.0, le=100000.0)]


class Prim(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: PrimPath
    transform: Annotated[
        list[TransformItem],
        Field(
            description="world transform, row-major 4 x 4, float64 (USD row-vector convention: translation in 12-14)",
            max_length=16,
            min_length=16,
        ),
    ]
    vertices: Annotated[int, Field(ge=3, le=16777216)]
    faces: Annotated[int, Field(ge=1, le=33554432)]
    class_: Annotated[ClassLabel, Field(alias="class")]
    part: PartLabel | None = None


class LodDigest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lod: LodName
    prims: Annotated[list[Prim], Field(max_length=20000, min_length=1)]


class Selection(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    pushback: VariantName
    scenario: VariantName
    time_of_day: TimeOfDay
    weather: Weather
    lod: LodName


class FirstDifference(BaseModel):
    """
    first differing line of the two text exports (FR-004-39)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    line: Annotated[int, Field(ge=1, le=100000000)]
    first: Annotated[str, Field(max_length=300)]
    second: Annotated[str, Field(max_length=300)]


class LayerRole(
    RootModel[Literal["root", "anim", "sensors", "weather", "lights", "fleet", "design", "terrain", "asset"]]
):
    root: Literal["root", "anim", "sensors", "weather", "lights", "fleet", "design", "terrain", "asset"]


class LicenceClass(
    RootModel[
        Literal[
            "public-domain",
            "open-no-attribution",
            "own",
            "attribution",
            "share-alike",
            "display-only",
            "reference-only",
        ]
    ]
):
    root: Literal[
        "public-domain", "open-no-attribution", "own", "attribution", "share-alike", "display-only", "reference-only"
    ]


class Confirmation(BaseModel):
    """
    mine-polygon check: share of the polygon's area inside the AOI
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    source: Slug
    overlap_frac: Annotated[float, Field(ge=0.0, le=1.0)]


class Site1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str,
        Field(
            max_length=160,
            min_length=1,
            pattern="^[A-Za-z0-9][A-Za-z0-9 ,.'()-]{0,159}$",
        ),
    ]
    provisional: Annotated[bool, Field(description="true until FR-004-15 confirms the AOI")]
    confirmation: Annotated[
        Confirmation | None,
        Field(description="mine-polygon check: share of the polygon's area inside the AOI"),
    ]
    origin: SiteOrigin


class Source(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    role: Literal["terrain", "mine-polygon", "texture", "people"]
    spdx: SpdxId
    licence_class: LicenceClass
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    attribution: Annotated[str, Field(max_length=1000, min_length=1)]
    project: Annotated[str | None, Field(max_length=128, min_length=1)] = None
    epoch: Annotated[int | None, Field(ge=1990, le=2100)] = None
    status: Literal["used", "not_run"]
    reason: Annotated[
        str | None,
        Field(
            description="why an enabled optional source did not run (FR-004-09)",
            max_length=256,
            min_length=1,
        ),
    ] = None


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


class FileRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256


class Terrain1(BaseModel):
    """
    terrain outputs and the holes left as nodata (FR-004-05, FR-004-12)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    grid: FileRef
    tiles: FileRef
    cell_size_m: Annotated[float, Field(ge=0.25, le=10.0)]
    unfilled_holes: Annotated[int, Field(ge=0, le=100000000)]
    unfilled_cells: Annotated[int, Field(ge=0, le=100000000)]
    nodata_frac: Annotated[float, Field(ge=0.0, le=0.05)]


class Design1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    report: FileRef
    road_network: FileRef
    provenance: Literal["design-code"]


class Layer(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    role: LayerRole
    path: Relpath
    format: Literal["usda", "usdc"]
    sha256: Sha256
    bytes: Annotated[int, Field(ge=0, le=9007199254740991)]
    up_axis: Literal["Z"]
    meters_per_unit: float
    kilograms_per_unit: float
    label: Literal["regenerated by design code, not observed"] | None = None


class Texture(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    source: Annotated[Slug | None, Field(description="null for our own textures")]
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
    sha256: Sha256


class Validation1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["pending", "complete", "incomplete"]
    report: FileRef | None = None


class InvLayerUnitsAxis(BaseModel):
    """
    layers whose upAxis, metersPerUnit or kilogramsPerUnit is wrong or unauthored (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[int, Field(ge=0)]
    unit: Literal["count"]
    limit: Literal[0]
    comparison: Literal["le"]
    passed: bool


class InvClassLabelCoverage(BaseModel):
    """
    share of geometry prims carrying exactly one class label (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[float, Field(ge=0.0, le=1.0)]
    unit: Literal["fraction"]
    limit: float
    comparison: Literal["ge"]
    passed: bool


class InvTimeSampledLabels(BaseModel):
    """
    label attributes with time samples (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[int, Field(ge=0)]
    unit: Literal["count"]
    limit: Literal[0]
    comparison: Literal["le"]
    passed: bool


class InvArticulationRoots(BaseModel):
    """
    machines without exactly one articulation root (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[int, Field(ge=0)]
    unit: Literal["count"]
    limit: Literal[0]
    comparison: Literal["le"]
    passed: bool


class InvCyclicJointGraphs(BaseModel):
    """
    machines whose joint graph is not a tree (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[int, Field(ge=0)]
    unit: Literal["count"]
    limit: Literal[0]
    comparison: Literal["le"]
    passed: bool


class InvNonPositiveMasses(BaseModel):
    """
    bodies with mass <= 0 (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[int, Field(ge=0)]
    unit: Literal["count"]
    limit: Literal[0]
    comparison: Literal["le"]
    passed: bool


class InvBenchHeightDeviation(BaseModel):
    """
    largest |measured bench height - H| (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[float, Field(ge=0.0, le=1000.0)]
    unit: Literal["m"]
    limit: float
    comparison: Literal["le"]
    passed: bool


class InvFaceAngleDeviation(BaseModel):
    """
    largest |measured face angle - alpha| (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[float, Field(ge=0.0, le=90.0)]
    unit: Literal["deg"]
    limit: float
    comparison: Literal["le"]
    passed: bool


class InvRampGradeMax(BaseModel):
    """
    largest ramp centreline grade; limit g + 0.1 % (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[float, Field(ge=0.0, le=100.0)]
    unit: Literal["pct"]
    limit: Annotated[float, Field(description="g + 0.1 %", ge=0.1, le=15.1)]
    comparison: Literal["le"]
    passed: bool


class InvWindrowMargin(BaseModel):
    """
    smallest windrow height minus the largest mid-axle height (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[float, Field(ge=-5.0, le=5.0)]
    unit: Literal["m"]
    limit: Literal[0]
    comparison: Literal["ge"]
    passed: bool


class InvTerrainRangeExcess(BaseModel):
    """
    largest excess of terrain z over the source range +/- max_error (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[float, Field(ge=0.0, le=10000.0)]
    unit: Literal["m"]
    limit: Literal[0]
    comparison: Literal["le"]
    passed: bool


class InvCutFillIdentityResidual(BaseModel):
    """
    relative residual of the P-004-07 identity (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[float, Field(ge=0.0)]
    unit: Literal["rel"]
    limit: float
    comparison: Literal["le"]
    passed: bool


class InvForbiddenPaths(BaseModel):
    """
    forbidden asset paths in any layer (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[int, Field(ge=0)]
    unit: Literal["count"]
    limit: Literal[0]
    comparison: Literal["le"]
    passed: bool


class InvLayerSizeMax(BaseModel):
    """
    largest small .usda layer (NFR-004-05: <= 10 MB) (FR-004-35)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    measured: Annotated[int, Field(ge=0, le=9007199254740991)]
    unit: Literal["bytes"]
    limit: Literal[10000000]
    comparison: Literal["le"]
    passed: bool


class Invariants(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    layer_units_axis: InvLayerUnitsAxis
    class_label_coverage: InvClassLabelCoverage
    time_sampled_labels: InvTimeSampledLabels
    articulation_roots: InvArticulationRoots
    cyclic_joint_graphs: InvCyclicJointGraphs
    non_positive_masses: InvNonPositiveMasses
    bench_height_deviation: InvBenchHeightDeviation
    face_angle_deviation: InvFaceAngleDeviation
    ramp_grade_max: InvRampGradeMax
    windrow_margin: InvWindrowMargin
    terrain_range_excess: InvTerrainRangeExcess
    cut_fill_identity_residual: InvCutFillIdentityResidual
    forbidden_paths: InvForbiddenPaths
    layer_size_max: InvLayerSizeMax


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


class Result(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rule: RuleId
    severity: Literal["error", "warning", "info"]
    prim: PrimPath | None
    message: Annotated[
        str,
        Field(description="scrubbed validator message", max_length=300, min_length=1),
    ]
    waived: bool


class ValidatorRun(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Literal["usd-validation-nvidia", "simready-validate"]
    version: Annotated[Version | None, Field(description="read from studio/uv.lock")]
    status: Literal["ran", "not_run"]
    reason: Annotated[
        str | None,
        Field(
            description="why the validator did not run (FR-004-38)",
            max_length=300,
            min_length=1,
        ),
    ] = None
    results: Annotated[list[Result], Field(max_length=5000)]


class DeterminismLayer(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    role: LayerRole
    path: Relpath
    format: Literal["usda", "usdc"]
    method: Literal["bytes", "flattened-text"]
    first_sha256: Sha256
    second_sha256: Sha256
    equal: bool
    first_difference: Annotated[
        FirstDifference | None,
        Field(description="first differing line of the two text exports (FR-004-39)"),
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


class Determinism(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[Literal["bitwise"], Field(alias="class")]
    layers: Annotated[list[DeterminismLayer], Field(max_length=64, min_length=1)]
    identical: bool
    stage_hash: Annotated[
        Sha256,
        Field(description="SHA-256 of the sorted (role, sha256) list (FR-004-36)"),
    ]


class SceneValidationReport(BaseModel):
    """
    Validator results, scene invariants, waivers and the build-twice hashes written by st45_validate (DC-004-07, spec 004-scene-pipeline).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    kind: Literal["scene-validation-report"]
    case: CaseId
    manifest_id: Slug
    params_sha256: Sha256
    status: Annotated[
        Literal["complete", "incomplete"],
        Field(description="incomplete when a validator did not run"),
    ]
    passed: bool
    validators: Annotated[list[ValidatorRun], Field(max_length=2, min_length=2)]
    selections: Annotated[
        list[Selection],
        Field(
            description="variant selections validated (FR-004-34)",
            max_length=1024,
            min_length=1,
        ),
    ]
    invariants: Invariants
    waivers: Annotated[list[Waiver], Field(max_length=32)]
    determinism: Determinism


class Input(BaseModel):
    """
    one DEM or LAZ file and the CRS read from it (FR-004-01)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    source: Slug
    file: Relpath
    kind: Literal["dem", "laz"]
    sha256: Sha256
    crs: CrsRecord
