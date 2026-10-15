# Generated from contracts/fragment-split.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ValidationOriginal(RootModel[int]):
    root: Annotated[int, Field(description="original file number", ge=1, le=240)]


class Fold(BaseModel):
    """
    one fold of the spec 008 split file; the validation files are k + 240 m (m = 0..3) of the listed originals, carved by whole groups from that fold's training pool (FR-012-05)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    fold: Annotated[int, Field(ge=0, le=4)]
    validation_originals: Annotated[list[ValidationOriginal], Field(max_length=240, min_length=1)]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class MendeleyPerFoldValidationSubsets(BaseModel):
    """
    Validation subsets recorded on top of the spec 008 split file (DC-008-04): groups, folds and test lists live only there (DC-012-02, spec 012-fragmentation).
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
    kind: Literal["folds"]
    source_id: Literal["mendeley-78ht3pjsr4"]
    archive_sha256: Literal["7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d"]
    split_id: Annotated[
        str,
        Field(
            description="id of the spec 008 split file data/splits/<id>.json (DC-008-04) the validation subsets are carved from",
            max_length=128,
            pattern="^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$",
        ),
    ]
    split_membership_sha256: Annotated[
        Sha256,
        Field(description="membership_sha256 recorded in that split file; the 012 file is stale if it differs"),
    ]
    validation_fraction: float
    validation_seed: Annotated[int, Field(ge=0, le=4294967295)]
    expansion: Annotated[
        Literal["dihedral-4"],
        Field(description="files of an original k: k, k + 240, k + 480, k + 720"),
    ]
    folds: Annotated[list[Fold], Field(max_length=5, min_length=5)]
