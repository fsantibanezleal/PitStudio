# Generated from contracts/studio-index.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


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


class Date(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=10, pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"),
    ]


class Driver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+(\\.[0-9]+)+$")]


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class Checks(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class JsonPointer(RootModel[str]):
    root: Annotated[str, Field(max_length=512, pattern="^(/([A-Za-z0-9_.$-]|~[01]){1,64}){1,32}$")]


class LocalOnly(RootModel[Literal["measured locally, not published (licence)"]]):
    root: Literal["measured locally, not published (licence)"]


class Metrics(RootModel[dict[constr(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$"), float | constr(max_length=200)]]):
    root: Annotated[
        dict[constr(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$"), float | constr(max_length=200)],
        Field(max_length=64),
    ]


class BandId(
    RootModel[Literal["scene", "physics", "sensors-synthetic-data", "training", "acceleration", "encoding", "web"]]
):
    root: Literal["scene", "physics", "sensors-synthetic-data", "training", "acceleration", "encoding", "web"]


class ToolId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class Probe(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9_]{0,31}$")]


class ProbeStatus(BaseModel):
    """
    Capability-probe status from studio/capabilities.json; never 'pass' without a passing probe.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["pass", "fail", "skip", "not-probed"]
    name: Probe | None = None
    date: Date | None = None
    gpu: Annotated[str | None, Field(max_length=128, min_length=1)] = None
    driver: Driver | None = None
    metrics: Metrics | LocalOnly | None = None
    error: Annotated[str | None, Field(max_length=300, min_length=1)] = None


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class VersionRef(BaseModel):
    """
    Version resolved from the lock, the pinned binary record, the git tag or VERSION; release_date null when the source records none.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: Version
    release_date: Date | None
    from_: Annotated[Literal["lock", "binary", "git-tag", "own"], Field(alias="from")]
    lock: (
        Literal[
            "uv.lock",
            "studio/uv.lock",
            "studio/isaac/uv.lock",
            "studio/rtx/uv.lock",
            "studio/isaaclab/uv.lock",
            "pipeline/uv.lock",
            "pipeline/accel/uv.lock",
            "web/pnpm-lock.yaml",
        ]
        | None
    ) = None


class Violation1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    message: Annotated[str, Field(max_length=300, min_length=1)]
    tool: ToolId
    artefact: ArtefactId | None = None
    file: Relpath | None = None
    field: JsonPointer | None = None


class Violation2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    message: Annotated[str, Field(max_length=300, min_length=1)]
    tool: ToolId | None = None
    artefact: ArtefactId
    file: Relpath | None = None
    field: JsonPointer | None = None


class Violation3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    message: Annotated[str, Field(max_length=300, min_length=1)]
    tool: ToolId | None = None
    artefact: ArtefactId | None = None
    file: Relpath
    field: JsonPointer | None = None


class Violation(RootModel[Violation1 | Violation2 | Violation3]):
    root: Violation1 | Violation2 | Violation3


class Check(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Literal[
        "done-needs-artefact",
        "not-yet-run-has-artefact",
        "outputs-only",
        "our-scenes",
        "local-only-scrub",
        "file-guards",
    ]
    status: Literal["pass", "fail"]
    violations: Annotated[list[Violation], Field(max_length=500, min_length=0)]


class Evidence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    run_id: RunId
    from_artefact: ArtefactId
    to_artefact: ArtefactId


class Edge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    from_: Annotated[ToolId, Field(alias="from")]
    to: ToolId
    kind: ArtefactKind
    state: Literal["observed", "planned"]
    evidence: Evidence | None = None


class DefinitionOfDone(BaseModel):
    """
    SC-019-01: each studio tool has a published artefact or an evaluated-not-adopted page.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    studio_tools: Annotated[int, Field(ge=0, le=64)]
    satisfied: Annotated[int, Field(ge=0, le=64)]
    missing: Annotated[list[ToolId], Field(max_length=64, min_length=0)]
    met: bool


class Honesty(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    checks: Annotated[list[Check] | Checks, Field(max_length=6, min_length=6)]
    definition_of_done: Annotated[
        DefinitionOfDone,
        Field(description="SC-019-01: each studio tool has a published artefact or an evaluated-not-adopted page."),
    ]


class Position(BaseModel):
    """
    Build-time layout: integer pixel coordinates so that identical inputs give identical bytes.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band: BandId
    order: Annotated[int, Field(ge=0, le=31)]
    group: Literal["map", "not-adopted"]
    x_px: Annotated[int, Field(ge=0, le=20000)]
    y_px: Annotated[int, Field(ge=0, le=20000)]


class Band(BaseModel):
    """
    One band of the map; tools are listed in drawing order.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: BandId
    tools: Annotated[list[ToolId], Field(max_length=32, min_length=1)]


class Edge1(BaseModel):
    """
    A declared file handoff from one tool to another, labelled with the artefact kind it carries.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    from_: Annotated[ToolId, Field(alias="from")]
    to: ToolId
    kind: ArtefactKind


class Tool(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: ToolId
    position: Position
    version: VersionRef
    probe: ProbeStatus
    artefacts: Annotated[list[ArtefactId], Field(max_length=2000, min_length=0)]


class StudioIndex(BaseModel):
    """
    Studio index web/public/studio/index.json generated by build-studio-index.mjs (DC-019-03, spec 019-web-studio).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    git_sha: GitSha
    tools: Annotated[list[Tool], Field(max_length=64, min_length=1)]
    edges: Annotated[list[Edge], Field(max_length=128, min_length=0)]
    honesty: Honesty
