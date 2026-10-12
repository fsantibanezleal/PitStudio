# Generated from contracts/dispatch-policy-io.schema.json by tools/gen_types.py. Do not edit.

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


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]{1,4}$")]


class Onnx(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    bytes: Annotated[int, Field(ge=1, lt=2000000)]
    opset: Annotated[int, Field(ge=17, le=19)]
    ir_version: Literal[10]


class Policy(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Literal["ppo", "attention"]
    architecture: Literal["shared-mlp", "dense-attention"]
    artefact_id: ArtefactId
    onnx: Onnx


class TruckFeatures(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["truck_features"]
    dtype: Literal["float32"]
    shape: list[int]
    features: list[dict[str, int | str]]


class TargetFeatures(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["target_features"]
    dtype: Literal["float32"]
    shape: list[int]
    features: list[dict[str, int | str]]


class TruckMask(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["truck_mask"]
    dtype: Literal["bool"]
    shape: list[int]
    meaning: Literal["true = real truck slot"]


class TargetMask(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["target_mask"]
    dtype: Literal["bool"]
    shape: list[int]
    meaning: Literal["true = serviceable and reachable for the deciding truck"]


class Inputs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    truck_features: TruckFeatures
    target_features: TargetFeatures
    truck_mask: TruckMask
    target_mask: TargetMask


class Output(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["logits"]
    dtype: Literal["float32"]
    shape: list[int]
    meaning: Literal["one logit per target slot"]


class Decision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    masking: Literal["masked target has probability 0"]
    applied_by: Literal["des"]
    selection: Literal["argmax"]
    tie_rule: Literal["lowest-target-index"]


class Padding(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    max_trucks: Literal[40]
    max_targets: Literal[16]


class DispatchPolicyInputOutputLayout(BaseModel):
    """
    Tensor layout, feature order, units, normalisation, masks and tie rule of an exported dispatch policy, written by s60_export (DC-007-04, spec 007-haulage-dispatch).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    layout_version: Literal[1]
    policy: Policy
    inputs: Inputs
    output: Output
    decision: Decision
    padding: Padding
    time_unit: Literal["h"]
