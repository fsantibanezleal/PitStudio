# Generated from contracts/vlm-queries.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class AnswerLabel(RootModel[Literal["yes", "no", "0", "1", "2", "3+"]]):
    root: Literal["yes", "no", "0", "1", "2", "3+"]


class Condition(RootModel[Literal["day", "night", "dust", "rain"]]):
    root: Literal["day", "night", "dust", "rain"]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class ObjectClass(RootModel[Literal["haul_truck", "shovel", "light_vehicle", "person", "boulder"]]):
    root: Literal["haul_truck", "shovel", "light_vehicle", "person", "boulder"]


class Location(RootModel[Literal["haul_road", "bench", "loading_area"]]):
    root: Literal["haul_road", "bench", "loading_area"]


class FileRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256


class CoordinateM(RootModel[float]):
    root: Annotated[float, Field(ge=-100000.0, le=100000.0)]


class Vec3M(RootModel[list[CoordinateM]]):
    root: Annotated[list[CoordinateM], Field(max_length=3, min_length=3)]


class Vec2M(RootModel[list[CoordinateM]]):
    root: Annotated[list[CoordinateM], Field(max_length=2, min_length=2)]


class RotationXyzwItem(RootModel[float]):
    root: Annotated[float, Field(ge=-1.0, le=1.0)]


class Pose(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    translation_m: Vec3M
    rotation_xyzw: Annotated[list[RotationXyzwItem], Field(max_length=4, min_length=4)]


class PrimId(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=512,
            pattern="^/[A-Za-z_][A-Za-z0-9_]{0,63}(/[A-Za-z_][A-Za-z0-9_]{0,63}){0,15}$",
        ),
    ]


class VisiblePx(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=67108864)]


class HalfExtentsMItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=100.0)]


class Footprint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    centre_m: Vec2M
    half_extents_m: Annotated[list[HalfExtentsMItem], Field(max_length=2, min_length=2)]
    heading_deg: Annotated[float, Field(ge=-180.0, le=180.0)]


class Object(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    prim_id: PrimId
    class_: Annotated[ObjectClass, Field(alias="class")]
    asset_id: ArtefactId | None = None
    pose: Pose
    footprint: Footprint
    visible_px: VisiblePx
    in_frustum: bool


class BenchEdge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    edge_id: ArtefactId
    berm_present: bool
    visible_px: VisiblePx


class Image(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    width_px: Annotated[int, Field(ge=16, le=8192)]
    height_px: Annotated[int, Field(ge=16, le=8192)]


class Intrinsics(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    fx_px: Annotated[float, Field(gt=0.0, le=100000.0)]
    fy_px: Annotated[float, Field(gt=0.0, le=100000.0)]
    cx_px: Annotated[float, Field(ge=0.0, le=8192.0)]
    cy_px: Annotated[float, Field(ge=0.0, le=8192.0)]


class Camera(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    intrinsics: Intrinsics
    pose: Pose


class Query(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query_id: ArtefactId
    frame_id: ArtefactId
    frame_state_sha256: Sha256
    type: Annotated[int, Field(ge=1, le=6)]
    condition: Condition
    location: Location
    truth: AnswerLabel
    gate_subset: bool
    reasoning_subset: bool


class TaskAQuerySet(BaseModel):
    """
    Task-A hazard query set written by the query builder: one query per (frame, type) with its exact answer (DC-015-02, spec 015-vlm).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    source_run_id: RunId
    queries: Annotated[list[Query], Field(max_length=6480, min_length=1)]
