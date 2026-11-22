# Generated from contracts/pit-design-report.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Parameters(BaseModel):
    """
    declared design parameters (hard domain of FR-004-22)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    bench_height_m: Annotated[float, Field(ge=5.0, le=30.0)]
    face_angle_deg: Annotated[float, Field(ge=40.0, le=85.0)]
    berm_width_m: Annotated[float, Field(ge=3.0, le=60.0)]
    ramp_grade_pct: Annotated[float, Field(ge=0.0, le=15.0)]
    ramp_width_m: Annotated[float, Field(ge=8.0, le=60.0)]
    windrow_height_m: Annotated[float, Field(gt=0.0, le=5.0)]


class Ramp(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    length_m: Annotated[float, Field(gt=0.0, le=1000000.0)]
    max_grade_pct: Annotated[
        float,
        Field(description="measured on the centreline sampled at <= 1 m", ge=0.0, le=100.0),
    ]
    min_width_m: Annotated[float, Field(ge=0.0, le=1000.0)]
    sample_spacing_m: Annotated[float, Field(gt=0.0, le=1.0)]
    connected: Annotated[
        Literal[True],
        Field(description="the centreline is one connected polyline (FR-004-17)"),
    ]


class Volumes(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    cut_m3: Annotated[float, Field(ge=0.0)]
    fill_m3: Annotated[float, Field(ge=0.0)]
    carved_sum_m3: Annotated[
        float,
        Field(description="sum over cells of (z_terrain - z_final) x cell area (P-004-07)"),
    ]
    cell_area_m2: Annotated[float, Field(gt=0.0, le=100.0)]
    identity_residual_rel: Annotated[
        float,
        Field(
            description="|V_cut - V_fill - carved_sum| / max(V_cut, V_fill, 1 m^3)",
            ge=0.0,
        ),
    ]


class OutlineStepM(BaseModel):
    """
    height step across the pit outline: carved height of a cell inside minus that of its 4-neighbour outside, over every such pair
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    pairs: Annotated[int, Field(ge=0)]
    median_abs_m: Annotated[float, Field(ge=0.0, le=10000.0)]
    max_abs_m: Annotated[float, Field(ge=0.0, le=10000.0)]
    mean_signed_m: Annotated[float, Field(ge=-10000.0, le=10000.0)]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class Bench(BaseModel):
    """
    measured geometry of one bench (FR-004-19); tolerance checks belong to FR-004-35
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    index: Annotated[int, Field(ge=0, le=511)]
    crest_z_m: Annotated[
        float,
        Field(
            description="site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)",
            ge=-5000.0,
            le=5000.0,
        ),
    ]
    toe_z_m: Annotated[
        float,
        Field(
            description="site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)",
            ge=-5000.0,
            le=5000.0,
        ),
    ]
    height_m: Annotated[float, Field(description="measured bench height", gt=0.0, le=100.0)]
    face_angle_deg: Annotated[float, Field(description="measured face angle", gt=0.0, le=90.0)]
    berm_width_m: Annotated[
        float | None,
        Field(
            description="measured berm width; null for the floor bench",
            ge=0.0,
            le=1000.0,
        ),
    ]
    crest_perimeter_m: Annotated[float, Field(gt=0.0, le=1000000.0)]
    widened_for_ramp: bool


class Outline(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source: Literal["rim-contour", "upstream-shell"]
    shell_sha256: Sha256 | None = None
    vertices: Annotated[int, Field(ge=3, le=100000)]
    area_m2: Annotated[float, Field(gt=0.0, le=40000000000.0)]
    perimeter_m: Annotated[float, Field(gt=0.0, le=1000000.0)]
    rim_z_m: Annotated[
        float,
        Field(
            description="site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)",
            ge=-5000.0,
            le=5000.0,
        ),
    ]
    floor_z_m: Annotated[
        float,
        Field(
            description="site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)",
            ge=-5000.0,
            le=5000.0,
        ),
    ]


class Windrows(BaseModel):
    """
    windrow height and the mid-axle height of the largest haul unit (FR-004-18)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    height_m: Annotated[float, Field(gt=0.0, le=5.0)]
    mid_axle_height_m: Annotated[float, Field(gt=0.0, le=5.0)]
    governing_asset: Slug


class CarvedSurface(BaseModel):
    """
    the carved surface written next to the report (FR-004-50): the design meshes inside the pit outline, the source terrain outside it
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    grid_sha256: Annotated[
        Sha256,
        Field(description="SHA-256 of the carved elevation array, float32 little-endian, row 0 north"),
    ]
    cells_inside: Annotated[
        int,
        Field(description="grid cells whose centre lies inside the pit outline", ge=1),
    ]
    outline_step_m: Annotated[
        OutlineStepM,
        Field(
            description="height step across the pit outline: carved height of a cell inside minus that of its 4-neighbour outside, over every such pair"
        ),
    ]


class PitDesignReport(BaseModel):
    """
    Per-bench table, ramp and windrow measures, cut/fill volumes and identity residual written by st20_pit_design (DC-004-05, spec 004-scene-pipeline). Version 1.1: optional `fixture` member. Version 1.2: optional `carved_surface` member (FR-004-50).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    kind: Literal["pit-design-report"]
    provenance: Literal["design-code"]
    label: Literal["regenerated by design code, not observed"]
    terrain_grid_sha256: Sha256
    parameters: Annotated[
        Parameters,
        Field(description="declared design parameters (hard domain of FR-004-22)"),
    ]
    outline: Outline
    benches: Annotated[list[Bench], Field(max_length=512, min_length=1)]
    ramp: Ramp
    windrows: Annotated[
        Windrows,
        Field(description="windrow height and the mid-axle height of the largest haul unit (FR-004-18)"),
    ]
    volumes: Volumes
    fixture: Annotated[
        bool | None,
        Field(
            description="True while the document derives from a contract fixture (ADR-0040, FR-004-44); no stage that consumes it may publish a result from it. Absent means false."
        ),
    ] = False
    carved_surface: Annotated[
        CarvedSurface | None,
        Field(
            description="the carved surface written next to the report (FR-004-50): the design meshes inside the pit outline, the source terrain outside it"
        ),
    ] = None
