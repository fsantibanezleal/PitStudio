# Generated from contracts/people-asset-record.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


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


class Semver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+\\.[0-9]+\\.[0-9]+$")]


class Seed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9223372036854775807)]


class SettingId(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9_-]{0,63}$")]


class Asset(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["skin", "clothes", "hair", "eyebrows", "eyelashes", "eyes", "teeth", "tongue", "proxy", "material"]
    name: Annotated[str, Field(max_length=128, pattern="^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$")]
    origin: Literal["system"]


class ExportSettings(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    format: Literal["fbx", "dae", "obj"]
    scale_unit: Literal["m", "dm", "cm", "mm"]
    skeleton: SettingId
    pose: SettingId | None = None
    feet_on_ground: bool | None = None
    subdivide: bool | None = None
    hide_faces_under_clothes: bool | None = None


class Licence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    spdx: Literal["CC0-1.0"]
    licence_class: Literal["open-no-attribution"]


class Makehuman(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    source: Literal["makehuman"]
    character_id: ArtefactId
    application: Literal["MakeHuman"]
    application_version: Literal["1.3.0"]
    build: Literal["official-unmodified"]
    zip_sha256: Sha256
    assets: Annotated[list[Asset], Field(max_length=256, min_length=1)]
    export_settings: ExportSettings
    seed: Seed
    export_path: Relpath
    export_sha256: Sha256
    exported_utc: UtcTimestamp | None = None
    licence: Licence


class Licence1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    spdx: Literal["CC-BY-4.0"]
    licence_class: Literal["own"]


class Mannequin(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    source: Literal["mannequin"]
    character_id: ArtefactId
    generator: Literal["procedural-mannequin"]
    generator_version: Semver
    git_sha: GitSha
    seed: Seed
    export_path: Relpath
    export_sha256: Sha256
    exported_utc: UtcTimestamp | None = None
    licence: Licence1


class PeopleAssetRecord(RootModel[Makehuman | Mannequin]):
    root: Annotated[
        Makehuman | Mannequin,
        Field(
            description="Provenance record of one person character for the SDG scenes, either a MakeHuman 1.3.0 export or a procedural mannequin, read by the st30_assets handoff and the dataset card (DC-009-04, spec 009-perception).",
            title="People asset record",
        ),
    ]
