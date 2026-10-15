# Generated from contracts/slope-section.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class ParamKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


class PofSeed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=18446744073709551615)]


class CoordinateM(RootModel[float]):
    root: Annotated[float, Field(ge=-1000000.0, le=1000000.0)]


class PointXzM(RootModel[list[CoordinateM]]):
    root: Annotated[list[CoordinateM], Field(max_length=2, min_length=2)]


class MapPointMItem(RootModel[float]):
    root: Annotated[float, Field(ge=-100000000.0, le=100000000.0)]


class MapPointM(RootModel[list[MapPointMItem]]):
    root: Annotated[list[MapPointMItem], Field(max_length=2, min_length=2)]


class Source(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["dem", "editor", "fixture"]
    source_id: Slug | None = None
    dem_sha256: Sha256 | None = None
    crs: Annotated[str | None, Field(max_length=10, pattern="^EPSG:[0-9]{4,5}$")] = None
    profile_start_m: MapPointM | None = None
    profile_end_m: MapPointM | None = None
    sample_spacing_m: Literal[1] | None = None
    simplify_tolerance_m: float = None
    site_label: Annotated[
        str | None,
        Field(max_length=120, pattern="^[A-Za-z0-9][A-Za-z0-9 ,.()'-]{0,119}$"),
    ] = None


class Material(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: ParamKey
    model: Literal["mohr-coulomb", "hoek-brown"]
    unit_weight_kn_per_m3: Annotated[float, Field(gt=0.0, le=40.0)]
    cohesion_kpa: Annotated[float | None, Field(ge=0.0, le=100000.0)] = None
    friction_angle_deg: Annotated[float | None, Field(ge=0.0, le=60.0)] = None
    gsi: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    m_i: Annotated[float | None, Field(gt=0.0, le=100.0)] = None
    sigma_ci_mpa: Annotated[float | None, Field(gt=0.0, le=1000.0)] = None
    disturbance_d: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    bottom_z_m: CoordinateM | None = None


class Distribution(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    material_id: ParamKey | None = None
    parameter: Literal[
        "cohesion_kpa",
        "friction_angle_deg",
        "gsi",
        "sigma_ci_mpa",
        "m_i",
        "disturbance_d",
        "unit_weight_kn_per_m3",
        "pore_pressure_ratio",
    ]
    distribution: Literal["normal", "lognormal", "uniform"]
    mean: Annotated[float | None, Field(ge=-1000000.0, le=1000000.0)] = None
    sd: Annotated[float | None, Field(gt=0.0, le=1000000.0)] = None
    cv: Annotated[float | None, Field(gt=0.0, le=10.0)] = None
    truncate_lower: Annotated[float | None, Field(ge=-1000000.0, le=1000000.0)] = None
    truncate_upper: Annotated[float | None, Field(ge=-1000000.0, le=1000000.0)] = None
    lower: Annotated[float | None, Field(ge=-1000000.0, le=1000000.0)] = None
    upper: Annotated[float | None, Field(ge=-1000000.0, le=1000000.0)] = None


class Search(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    entry_points: Annotated[int, Field(ge=2, le=1000)]
    exit_points: Annotated[int, Field(ge=2, le=1000)]
    radius_ratios: Annotated[int, Field(ge=1, le=100)]
    rho_min: Annotated[float, Field(gt=1.0, le=100.0)]
    rho_max: Annotated[float, Field(gt=1.0, le=100.0)]


class Pof(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    samples: Annotated[int, Field(ge=1, le=1000000)]
    candidates: Annotated[int, Field(ge=1, le=100000)]
    seed: PofSeed
    distributions: Annotated[list[Distribution], Field(max_length=32, min_length=1)]


class Analysis(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["live", "baked"]
    methods: Annotated[list[Literal["bishop", "spencer"]], Field(max_length=2, min_length=1)]
    slices: Annotated[int, Field(ge=10, le=500)]
    search: Search
    pof: Pof | None = None


class C1SlopeSection(BaseModel):
    """
    Two-dimensional C1 slope section (ground polyline, Mohr-Coulomb or Hoek-Brown materials, pore-pressure ratio, input distributions, search, slice and PoF settings, methods, source DEM digest) written by s10_preprocess and the web section editor (DC-010-01, spec 010-slope).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    section_id: ArtefactId
    source: Source
    ground: Annotated[list[PointXzM], Field(max_length=10000, min_length=2)]
    crest_x_m: CoordinateM
    toe_x_m: CoordinateM
    materials: Annotated[list[Material], Field(max_length=8, min_length=1)]
    pore_pressure_ratio: Annotated[float, Field(ge=0.0, lt=1.0)]
    analysis: Analysis
