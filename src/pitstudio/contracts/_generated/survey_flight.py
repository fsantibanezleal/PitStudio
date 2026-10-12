# Generated from contracts/survey-flight.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Design(BaseModel):
    """
    Survey design of FR-017-36; overlap_pct is both the forward and the side overlap.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    gsd_cm_per_px: Literal[2, 4, 8]
    overlap_pct: Literal[70, 80]
    sun_elevation_deg: Literal[30, 60]


class Camera(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Literal["pinhole"]
    distortion: Literal["none"]
    width_px: Annotated[int, Field(ge=16, le=16384)]
    height_px: Annotated[int, Field(ge=16, le=16384)]
    fx_px: Annotated[float, Field(gt=0.0, le=1000000.0)]
    fy_px: Annotated[float, Field(gt=0.0, le=1000000.0)]
    cx_px: Annotated[float, Field(ge=0.0, le=16384.0)]
    cy_px: Annotated[float, Field(ge=0.0, le=16384.0)]


class RotationWxyzItem(RootModel[float]):
    root: Annotated[float, Field(ge=-1.0, le=1.0)]


class Pose(BaseModel):
    """
    Camera-to-world pose; camera axes x right, y down, z forward; unit quaternion.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    position_m: Annotated[list[float], Field(max_length=3, min_length=3)]
    rotation_wxyz: Annotated[list[RotationWxyzItem], Field(max_length=4, min_length=4)]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Stockpile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    shape: Literal["conical-frustum"]
    centre_m: Annotated[list[float], Field(max_length=2, min_length=2)]
    radius_bottom_m: Annotated[float, Field(gt=0.0, le=1000.0)]
    radius_top_m: Annotated[float, Field(ge=0.0, le=1000.0)]
    height_m: Annotated[float, Field(gt=0.0, le=1000.0)]
    volume_m3: Annotated[float, Field(gt=0.0, le=1000000000.0)]


class Cut(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    shape: Literal["trapezoidal-prism"]
    centre_m: Annotated[list[float], Field(max_length=2, min_length=2)]
    length_m: Annotated[float, Field(gt=0.0, le=10000.0)]
    depth_m: Annotated[float, Field(gt=0.0, le=1000.0)]
    width_bottom_m: Annotated[float, Field(ge=0.0, le=10000.0)]
    width_top_m: Annotated[float, Field(gt=0.0, le=10000.0)]
    volume_m3: Annotated[float, Field(gt=0.0, le=1000000000.0)]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class FileRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Relpath
    sha256: Sha256


class Image(BaseModel):
    """
    One rendered image with its exact pose and its planar z-depth map (metres).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Relpath
    sha256: Sha256
    tilt_deg: Literal[-30, 0, 30]
    pose: Annotated[
        Pose,
        Field(description="Camera-to-world pose; camera axes x right, y down, z forward; unit quaternion."),
    ]
    depth: FileRef


class ExactSurface(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Relpath
    sha256: Sha256
    cell_m: float


class Scene(BaseModel):
    """
    Known-volume scene of FR-017-35 with its exact closed-form volumes.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    usd: FileRef
    exact_surface: ExactSurface
    base_z_m: Annotated[float, Field(ge=-1000.0, le=10000.0)]
    stockpile: Stockpile
    cut: Cut


class E2SurveyFlightRecord(BaseModel):
    """
    One rendered drone flight and sensor-noise seed with exact intrinsics, poses and depth (DC-017-05, spec 017-planning-survey).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    synthetic: Literal[True]
    flight: Slug
    design: Annotated[
        Design,
        Field(description="Survey design of FR-017-36; overlap_pct is both the forward and the side overlap."),
    ]
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    camera: Camera
    images: Annotated[list[Image], Field(max_length=20000, min_length=1)]
    scene: Scene
