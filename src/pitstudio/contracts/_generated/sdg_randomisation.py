# Generated from contracts/sdg-randomisation.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr
from typing_extensions import TypeAliasType


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Seed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9223372036854775807)]


class Arm(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    family: Literal["pit", "crusher"]
    arm: Literal["structured", "unstructured"]
    image_count: Annotated[int, Field(ge=1, le=100000)]
    seed_source: Literal["own", "structured-pit-train"]


class Sun(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source: Literal["solar-position"]
    year: Annotated[int, Field(ge=1900, le=2100)]
    min_elevation_deg: Literal[5]


class Dust(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source: Literal["plume-field"]


class WetRoads(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source: Literal["watering-schedule"]


class Placement(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source: Literal["pit-design"]
    max_base_offset_m: float


LithologiesAdditionalProperty = TypeAliasType(
    "LithologiesAdditionalProperty",
    Annotated[list[ArtefactId], Field(max_length=256, min_length=1)],
)


class RockTextures(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source: Literal["lithology-cc0"]
    lithologies: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,31}$", max_length=32), LithologiesAdditionalProperty],
        Field(max_length=32, min_length=1),
    ]


class Structured(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sun: Sun
    dust: Dust
    wet_roads: WetRoads
    placement: Placement
    rock_textures: RockTextures


class FactorRange(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    distribution: Literal["log-uniform"]
    min: Annotated[float, Field(ge=0.1, le=10.0)]
    max: Annotated[float, Field(ge=0.1, le=10.0)]


class KelvinRange(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    distribution: Literal["uniform"]
    min: Annotated[float, Field(ge=2000.0, le=12000.0)]
    max: Annotated[float, Field(ge=2000.0, le=12000.0)]


class CountRange(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    distribution: Literal["uniform-integer"]
    min: Annotated[int, Field(ge=0, le=20)]
    max: Annotated[int, Field(ge=0, le=20)]


class Unstructured(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    textures: Literal["whole-pool-uniform"]
    light_intensity_factor: FactorRange
    colour_temperature_k: KelvinRange
    sun_direction: Literal["upper-hemisphere-uniform"]
    object_positions: Literal["visible-ground-uniform"]
    distractors: CountRange


class Texture(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: ArtefactId
    source_id: Slug
    sha256: Sha256
    spdx: Literal["CC0-1.0"]


class SdgRandomisationConfig(BaseModel):
    """
    Domain-randomisation config of the perception SDG (arms, counts, structured parameter sources, unstructured ranges, texture pool, drying time, oversize limit) read by the DR sampler and st55_sdg (DC-009-03, spec 009-perception).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    seed: Seed
    x_os_m: Annotated[float, Field(gt=0.0, le=10.0)]
    drying_time_min: Annotated[float, Field(gt=0.0, le=1440.0)]
    arms: Annotated[list[Arm], Field(max_length=3, min_length=1)]
    structured: Structured
    unstructured: Unstructured
    texture_pool: Annotated[list[Texture], Field(max_length=4096, min_length=1)]
