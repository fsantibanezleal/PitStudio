# Generated from contracts/replay-shard.schema.json by tools/gen_types.py. Do not edit.

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


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class CodeType(RootModel[Literal["int16", "uint16"]]):
    root: Annotated[
        Literal["int16", "uint16"],
        Field(
            description="integer type of the quantised codes; decoding maps the 65,536 codes affinely onto [min, max] of each channel"
        ),
    ]


class Fps(RootModel[float]):
    root: Annotated[float, Field(description="frames per second", gt=0.0, le=240.0)]


class BboxM(BaseModel):
    """
    axis-aligned bounding box in metres (x, y, z)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    min: Annotated[list[float], Field(max_length=3, min_length=3)]
    max: Annotated[list[float], Field(max_length=3, min_length=3)]


class FrameRange(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    start: Annotated[int, Field(ge=0, le=10000000)]
    count: Annotated[int, Field(ge=1, le=10000000)]


class CodeRange(BaseModel):
    """
    smallest and largest code present in the payload; the reader rejects a shard with a code outside it (FR-018-45)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    min: Annotated[int, Field(ge=-32768, le=65535)]
    max: Annotated[int, Field(ge=-32768, le=65535)]


class Channel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9_]{0,31}$")]
    unit: Literal["m", "m/s", "m/s2", "rad", "s", "1", "ug/m3", "kg/m3", "kg/m2", "Pa"]
    min: Annotated[float, Field(description="value of the lowest code, in the channel unit")]
    max: Annotated[float, Field(description="value of the highest code, in the channel unit")]


class Payload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Annotated[Relpath, Field(description="payload file, relative to the header's folder")]
    bytes: Annotated[
        int,
        Field(
            description="payload size; shards and tiles are at most 10 MB (10^7 bytes)",
            ge=1,
            le=10000000,
        ),
    ]
    sha256: Sha256


class Grid(BaseModel):
    """
    tile size in cells (field tiles only)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    width: Annotated[int, Field(ge=1, le=4096)]
    height: Annotated[int, Field(ge=1, le=4096)]


class ShardHeader(BaseModel):
    """
    JSON header of one shard or field tile (DC-018-03)
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
    document: Literal["replay-shard-header"]
    schema_version: SchemaVersion
    kind: Literal["pose", "particle", "point", "field"]
    encoding: Annotated[
        Literal["raw16", "png16", "float32"],
        Field(
            description="raw16: little-endian 16-bit codes in frame, item, channel order; png16: 16-bit greyscale PNG tile; float32: little-endian Float32 tile"
        ),
    ]
    code_type: CodeType | None = None
    code_range: CodeRange | None = None
    fps: Fps
    frames: FrameRange
    items: Annotated[
        int,
        Field(description="poses, particles, points or cells per frame", ge=1, le=5000000),
    ]
    channels: Annotated[list[Channel], Field(max_length=16, min_length=1)]
    bbox_m: BboxM
    grid: Annotated[Grid | None, Field(description="tile size in cells (field tiles only)")] = None
    payload: Payload


class ShardEntry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    header: Annotated[
        Relpath,
        Field(description="shard header JSON, relative to the manifest's folder"),
    ]
    payload: Annotated[Relpath, Field(description="shard payload, relative to the manifest's folder")]
    bytes: Annotated[int, Field(ge=1, le=10000000)]
    sha256: Annotated[Sha256, Field(description="SHA-256 of the payload bytes")]
    frames: FrameRange


class Solver(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Slug
    version: Version


class ReplayManifest(BaseModel):
    """
    replay manifest listing the shards of one replay (FR-005-45)
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
    document: Literal["replay-manifest"]
    schema_version: SchemaVersion
    kind: Literal["particle", "pose", "point"]
    units: Annotated[
        Literal["m"],
        Field(description="length unit of positions and of the bounding box"),
    ]
    bbox_m: BboxM
    fps: Fps
    frames: Annotated[int, Field(description="frame count", ge=1, le=10000000)]
    items: Annotated[
        int,
        Field(
            description="particle (or pose, point) count per frame; one frame of three 16-bit channels fits one shard",
            ge=1,
            le=1666666,
        ),
    ]
    code_type: CodeType
    solver: Solver
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    shards: Annotated[list[ShardEntry], Field(max_length=1000, min_length=1)]


class PitstudioReplayShardHeaderAndReplayManifest(RootModel[ShardHeader | ReplayManifest]):
    root: Annotated[
        ShardHeader | ReplayManifest,
        Field(
            description="Replay shard headers and replay manifests written by st50_physics, s60_export and studio publish (DC-018-03, spec 018-web-cases; also DC-005-04, spec 005-physics).",
            title="PitStudio replay shard header and replay manifest",
        ),
    ]
