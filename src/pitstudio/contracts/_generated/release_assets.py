# Generated from contracts/release-assets.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ReleaseTag(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^assets-v[0-9]+\\.[0-9]{2}\\.[0-9]{3}$")]


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


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class Entry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    bytes: Annotated[int, Field(ge=0, le=2147483647)]
    sha256: Sha256


class ReleaseAssetUploadList(BaseModel):
    """
    Release-asset upload list written by s60_export: tag and the release-hosted files with path, bytes and SHA-256, sorted by path (DC-016-02, spec 016-export-acceleration).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    tag: ReleaseTag
    entries: Annotated[list[Entry], Field(max_length=2000)]
