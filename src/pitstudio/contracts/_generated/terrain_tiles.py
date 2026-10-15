# Generated from contracts/terrain-tiles.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


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


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class LodIndex(RootModel[Literal[0, 1, 2]]):
    root: Annotated[
        Literal[0, 1, 2],
        Field(description="terrain level of detail (FR-004-06: LOD 0-2)"),
    ]


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


class Bbox(BaseModel):
    """
    site-frame bounding box including skirts, m
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x_min_m: Annotated[
        float,
        Field(
            description="site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)",
            ge=-100000.0,
            le=100000.0,
        ),
    ]
    y_min_m: Annotated[
        float,
        Field(
            description="site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)",
            ge=-100000.0,
            le=100000.0,
        ),
    ]
    z_min_m: Annotated[float, Field(ge=-5100.0, le=5100.0)]
    x_max_m: Annotated[
        float,
        Field(
            description="site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)",
            ge=-100000.0,
            le=100000.0,
        ),
    ]
    y_max_m: Annotated[
        float,
        Field(
            description="site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)",
            ge=-100000.0,
            le=100000.0,
        ),
    ]
    z_max_m: Annotated[float, Field(ge=-5100.0, le=5100.0)]


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


class Lod(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lod: LodIndex
    max_error_m: Annotated[float, Field(ge=0.05, le=8.0)]
    skirt_depth_m: Annotated[float, Field(gt=0.0, le=16.0)]
    tile_count: Annotated[int, Field(ge=1, le=4096)]


class Tile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description="<lod>-<quadtree level>-<x>-<y>",
            max_length=16,
            pattern="^[0-2]-[0-9]{1,2}-[0-9]{1,5}-[0-9]{1,5}$",
        ),
    ]
    lod: LodIndex
    level: Annotated[int, Field(ge=0, le=16)]
    x: Annotated[int, Field(ge=0, le=65535)]
    y: Annotated[int, Field(ge=0, le=65535)]
    prim: PrimPath
    bbox: Bbox
    max_error_m: Annotated[float, Field(ge=0.05, le=8.0)]
    vertices: Annotated[
        int,
        Field(
            description="<= 257^2 grid vertices + 4 x 257 skirt vertices",
            ge=3,
            le=67077,
        ),
    ]
    triangles: Annotated[
        int,
        Field(description="<= 2 x 256^2 + 8 x 256 skirt triangles", ge=1, le=133120),
    ]
    sha256: Annotated[
        Sha256,
        Field(description="of the tile's float32 positions followed by its uint32 indices, little-endian"),
    ]


class TerrainTileIndex(BaseModel):
    """
    Quadtree tile index of the terrain meshes per level of detail, written by st10_terrain (DC-004-04, spec 004-scene-pipeline). Version 1.1: optional `fixture` member.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    kind: Literal["terrain-tiles"]
    frame: Literal["site-enu"]
    tile_samples: Annotated[Literal[257], Field(description="tiles of 257 x 257 grid samples (FR-004-07)")]
    grid_elevation_sha256: Annotated[Sha256, Field(description="elevation array digest of the source grid")]
    layer_path: Annotated[Relpath, Field(description="the USD terrain layer holding the tile meshes")]
    lods: Annotated[list[Lod], Field(max_length=3, min_length=1)]
    tiles: Annotated[list[Tile], Field(max_length=4096, min_length=1)]
    fixture: Annotated[
        bool | None,
        Field(
            description="True while the document derives from a contract fixture (ADR-0040, FR-004-44); no stage that consumes it may publish a result from it. Absent means false."
        ),
    ] = False
