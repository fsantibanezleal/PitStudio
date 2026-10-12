# Generated from contracts/granular-rollout.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Geometry(BaseModel):
    """
    recorded geometry parameters of the family (spec §7)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    aspect_ratio: Annotated[float | None, Field(description="column collapse: H0 / L0", ge=0.5, le=4.0)] = None
    column_width_m: Annotated[float | None, Field(description="column collapse: L0", gt=0.0, le=10.0)] = None
    pour_point_x_m: Annotated[float | None, Field(ge=-1000.0, le=1000.0)] = None
    pour_height_m: Annotated[float | None, Field(gt=0.0, le=10.0)] = None
    pour_rate_m2_per_s: Annotated[float | None, Field(description="2-D area rate", gt=0.0, le=10.0)] = None
    crest_x_m: Annotated[float | None, Field(ge=-1000.0, le=1000.0)] = None
    crest_height_m: Annotated[float | None, Field(gt=0.0, le=10.0)] = None
    dump_rate_m2_per_s: Annotated[float | None, Field(description="2-D area rate", gt=0.0, le=10.0)] = None


class BoundsMItem(RootModel[float]):
    root: Annotated[float, Field(ge=-1000.0, le=1000.0)]


class FrameTimes(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=3600.0)]


class MaterialValue(BaseModel):
    """
    one material parameter with its provenance
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: float
    source: Literal["knowledge-table", "calibration", "recipe"]
    ref: Annotated[
        str | None,
        Field(
            description="knowledge-table row id or calibration trial id",
            max_length=128,
            min_length=1,
            pattern="^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        ),
    ] = None
    verification: Literal["verified", "UNVERIFIED"] | None = None


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Store(BaseModel):
    """
    payload store; sha256 of the file (Parquet) or of the sorted chunk-digest listing (Zarr)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    format: Literal["zarr", "parquet"]
    path: Relpath
    sha256: Sha256


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class DensityKgPerM3(MaterialValue):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=500.0, le=20000.0)]


class SlidingFriction(MaterialValue):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.05, le=2.0)]


class RollingFriction(MaterialValue):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1.0)]


class Restitution(MaterialValue):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1.0)]


class YoungsModulusPa(MaterialValue):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1000000000000.0)]


class PoissonRatio(MaterialValue):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=0.5)]


class FrictionAngleDeg(MaterialValue):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=90.0)]


class CohesionPa(MaterialValue):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000000.0)]


class Material(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    density_kg_per_m3: DensityKgPerM3
    sliding_friction: SlidingFriction
    rolling_friction: RollingFriction | None = None
    restitution: Restitution | None = None
    youngs_modulus_pa: YoungsModulusPa | None = None
    poisson_ratio: PoissonRatio | None = None
    friction_angle_deg: FrictionAngleDeg | None = None
    cohesion_pa: CohesionPa | None = None


class GranularRolloutMetadata(BaseModel):
    """
    Metadata of one 2-D granular rollout payload (Zarr or Parquet) written by st50_physics (DC-011-01, spec 011-surrogates).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[
        str | None,
        Field(
            alias="$schema",
            description="editor hint; ignored by consumers",
            max_length=200,
        ),
    ] = None
    family: Literal["column-collapse", "pile-formation", "dump-over-crest"]
    geometry_id: Slug
    geometry: Annotated[
        Geometry,
        Field(description="recorded geometry parameters of the family (spec §7)"),
    ]
    packing_seed: Annotated[int, Field(ge=0, le=4294967295)]
    solver: Literal["warp-dem", "newton-mpm"]
    solver_version: Version
    dimensions: Literal[2]
    particle_diameter_m: Annotated[float, Field(description="d", gt=0.0, le=1.0)]
    connectivity_radius_m: Annotated[float, Field(description="R = 2.5 d", gt=0.0, le=10.0)]
    frame_interval_s: Annotated[float, Field(description="dataset frame interval", gt=0.0, le=1.0)]
    bounds_m: Annotated[
        list[BoundsMItem],
        Field(description="x_min, y_min, x_max, y_max", max_length=4, min_length=4),
    ]
    frame_times_s: Annotated[
        list[FrameTimes],
        Field(description="strictly increasing", max_length=20000, min_length=2),
    ]
    particle_count: Annotated[int, Field(description="constant over every frame", ge=1, le=1000000)]
    particle_types: Annotated[
        list[Slug],
        Field(description="type names in type-index order", max_length=16, min_length=1),
    ]
    material: Material
    rest_time_s: Annotated[float, Field(description="T_end of the reference rollout", gt=0.0, le=3600.0)]
    store: Store
    label: Literal["calibrated synthetic — not validated against real data"]
