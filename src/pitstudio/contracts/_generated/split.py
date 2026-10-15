# Generated from contracts/split.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Seed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9223372036854775807)]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]{1,4}$")]


class RecordId(RootModel[str]):
    root: Annotated[str, Field(max_length=128, pattern="^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")]


class GroupKey(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rule: Literal[
        "mendeley-original-component",
        "scenario-seed",
        "event-seed",
        "muck-pile-id",
        "pit-layout-id",
        "scene-seed",
        "project-spatial-block",
        "single-group",
    ]
    block_size_m: Annotated[float | None, Field(gt=0.0, le=1000000.0)] = None


class Fold(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    index: Annotated[int, Field(ge=0, le=19)]
    test: Annotated[list[RecordId], Field(max_length=100000)]
    train_pool: Annotated[list[RecordId], Field(max_length=1000000)]


class Dataset(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    version: Version
    kind: Literal["real", "synthetic"]


class Link(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    a: RecordId
    b: RecordId


class Group(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: RecordId
    members: Annotated[list[RecordId], Field(max_length=100000, min_length=1)]


class GroupedSplitFile(BaseModel):
    """
    Groups and grouped folds fixed at ingestion by s10_preprocess under data/splits/ (DC-008-04, spec 008-data-pipeline).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    id: Slug
    dataset: Dataset
    group_key: GroupKey
    links: Annotated[list[Link], Field(max_length=4096)]
    groups: Annotated[list[Group], Field(max_length=100000, min_length=1)]
    method: Literal["seeded-greedy-grouped-kfold", "none"]
    seed: Seed | None
    folds: Annotated[list[Fold], Field(max_length=20)]
    membership_sha256: Annotated[
        Sha256,
        Field(description="SHA-256 of the RFC 8785 canonical JSON of {groups, folds}."),
    ]
