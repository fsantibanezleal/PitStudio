# Generated from contracts/perception-dataset.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


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


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Seed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9223372036854775807)]


class SizeBytes(RootModel[int]):
    root: Annotated[int, Field(ge=1, le=67108864)]


class ClassName(RootModel[Literal["haul_truck", "shovel", "light_vehicle", "person", "boulder"]]):
    root: Literal["haul_truck", "shovel", "light_vehicle", "person", "boulder"]


class File(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    size_bytes: SizeBytes


class ImageFile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    size_bytes: SizeBytes
    width_px: Annotated[int, Field(ge=16, le=1920)]
    height_px: Annotated[int, Field(ge=16, le=1080)]
    format: Literal["png"]
    colour_space: Literal["srgb"]


class MaskFile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    size_bytes: SizeBytes
    width_px: Annotated[int, Field(ge=16, le=1920)]
    height_px: Annotated[int, Field(ge=16, le=1080)]
    format: Literal["png"]


class DepthFile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    size_bytes: SizeBytes
    width_px: Annotated[int, Field(ge=16, le=1920)]
    height_px: Annotated[int, Field(ge=16, le=1080)]
    format: Literal["npy"]
    dtype: Literal["float32"]
    unit: Literal["m"]
    quantity: Literal["distance-to-image-plane", "distance-to-camera"]


class Intrinsics(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Literal["pinhole"]
    fx_px: Annotated[float, Field(gt=0.0, le=100000.0)]
    fy_px: Annotated[float, Field(gt=0.0, le=100000.0)]
    cx_px: Annotated[float, Field(ge=0.0, le=1920.0)]
    cy_px: Annotated[float, Field(ge=0.0, le=1080.0)]


class Placement(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[ClassName, Field(alias="class")]
    x_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    y_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    z_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    yaw_deg: Annotated[float, Field(ge=0.0, lt=360.0)]


class WetSegment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    segment_id: ArtefactId
    wet: bool
    minutes_since_watering: Annotated[float | None, Field(ge=0.0, le=527040.0)] = None


class DrStructured(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sun_utc: UtcTimestamp
    sun_elevation_deg: Annotated[float, Field(ge=5.0, le=90.0)]
    sun_azimuth_deg: Annotated[float, Field(ge=0.0, lt=360.0)]
    dust_extinction_per_km: Annotated[float, Field(ge=0.0, le=1000.0)]
    wet_segments: Annotated[list[WetSegment], Field(max_length=1024)]
    rock_texture_ids: Annotated[list[ArtefactId], Field(max_length=64, min_length=1)]
    placements: Annotated[list[Placement], Field(max_length=512)]


class DrUnstructured(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    texture_ids: Annotated[list[ArtefactId], Field(max_length=256, min_length=1)]
    light_intensity_factor: Annotated[float, Field(ge=0.1, le=10.0)]
    colour_temperature_k: Annotated[float, Field(ge=2000.0, le=12000.0)]
    sun_elevation_deg: Annotated[float, Field(ge=0.0, le=90.0)]
    sun_azimuth_deg: Annotated[float, Field(ge=0.0, lt=360.0)]
    distractor_count: Annotated[int, Field(ge=0, le=20)]
    placements: Annotated[list[Placement], Field(max_length=512)]


class Licence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    spdx: Literal["CC-BY-4.0"]
    licence_class: Literal["own"]


class PerceptionDatasetIndexRecord(BaseModel):
    """
    One dataset-index record per synthetic image (one JSON Lines line of the index) written by st55_sdg and the crusher handoff (DC-009-01, spec 009-perception).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    record_id: ArtefactId
    synthetic: Literal[True]
    family: Literal["pit", "crusher"]
    arm: Literal["structured", "unstructured"]
    split: Literal["train", "validation", "test"]
    scenario_seed: Seed
    layout_id: ArtefactId
    image: ImageFile
    coco: File
    coco_image_id: Annotated[int, Field(ge=1, le=2147483647)]
    semantic_mask: MaskFile
    instance_mask: MaskFile | None = None
    depth: DepthFile
    intrinsics: Intrinsics
    frame_state: File | None = None
    instance_source: Literal["replicator", "connected-components"]
    dr: DrStructured | DrUnstructured
    licence: Licence
