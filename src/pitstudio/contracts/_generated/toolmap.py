# Generated from contracts/toolmap.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Bands(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class ArtefactKind(
    RootModel[
        Literal[
            "video",
            "image",
            "figure",
            "point-cloud",
            "mesh",
            "tiles",
            "splat",
            "onnx",
            "table",
            "trace",
            "shard",
            "field",
            "text",
            "model-card",
            "telemetry",
            "usd",
        ]
    ]
):
    root: Literal[
        "video",
        "image",
        "figure",
        "point-cloud",
        "mesh",
        "tiles",
        "splat",
        "onnx",
        "table",
        "trace",
        "shard",
        "field",
        "text",
        "model-card",
        "telemetry",
        "usd",
    ]


class BandId(
    RootModel[Literal["scene", "physics", "sensors-synthetic-data", "training", "acceleration", "encoding", "web"]]
):
    root: Literal["scene", "physics", "sensors-synthetic-data", "training", "acceleration", "encoding", "web"]


class ToolId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class Band(BaseModel):
    """
    One band of the map; tools are listed in drawing order.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: BandId
    tools: Annotated[list[ToolId], Field(max_length=32, min_length=1)]


class Edge(BaseModel):
    """
    A declared file handoff from one tool to another, labelled with the artefact kind it carries.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    from_: Annotated[ToolId, Field(alias="from")]
    to: ToolId
    kind: ArtefactKind


class StudioToolMapSource(BaseModel):
    """
    Band order, tool order within each band and declared handoff edges of studio/toolmap.yaml (DC-019-02, spec 019-web-studio).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    bands: Annotated[list[Band] | Bands, Field(max_length=7, min_length=7)]
    edges: Annotated[list[Edge], Field(max_length=128, min_length=0)]
