# Generated from contracts/tools.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ToolId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Package(RootModel[str]):
    root: Annotated[str, Field(max_length=100, pattern="^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class BinaryId(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9-]{1,31}$")]


class HttpsUrl(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=2048,
            pattern="^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$",
        ),
    ]


class SpdxId(
    RootModel[
        Literal[
            "LicenseRef-USGov-PD",
            "CC0-1.0",
            "DL-DE-ZERO-2.0",
            "CC-BY-4.0",
            "LicenseRef-Copernicus-CLMS",
            "CC-BY-SA-3.0",
            "CC-BY-SA-4.0",
            "Apache-2.0",
            "MIT",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "MPL-2.0",
            "LGPL-2.1-or-later",
            "LicenseRef-TOST-1.0",
            "LicenseRef-NVIDIA-Open-Model",
            "LicenseRef-NVIDIA-SLA",
            "LicenseRef-NvidiaProprietary",
            "LicenseRef-NVIDIA-Omniverse",
            "LicenseRef-TensorRT-SLA",
            "LicenseRef-TensorRT-RTX-SLA",
        ]
    ]
):
    root: Literal[
        "LicenseRef-USGov-PD",
        "CC0-1.0",
        "DL-DE-ZERO-2.0",
        "CC-BY-4.0",
        "LicenseRef-Copernicus-CLMS",
        "CC-BY-SA-3.0",
        "CC-BY-SA-4.0",
        "Apache-2.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "MPL-2.0",
        "LGPL-2.1-or-later",
        "LicenseRef-TOST-1.0",
        "LicenseRef-NVIDIA-Open-Model",
        "LicenseRef-NVIDIA-SLA",
        "LicenseRef-NvidiaProprietary",
        "LicenseRef-NVIDIA-Omniverse",
        "LicenseRef-TensorRT-SLA",
        "LicenseRef-TensorRT-RTX-SLA",
    ]


class LicenceClass(
    RootModel[
        Literal[
            "public-domain",
            "open-no-attribution",
            "own",
            "attribution",
            "share-alike",
            "display-only",
            "reference-only",
        ]
    ]
):
    root: Literal[
        "public-domain", "open-no-attribution", "own", "attribution", "share-alike", "display-only", "reference-only"
    ]


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


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


class ToolEnv(
    RootModel[
        Literal[
            "root",
            "runner",
            "studio",
            "isaac",
            "rtx",
            "isaaclab",
            "kit",
            "reason",
            "pipeline",
            "accel",
            "web",
            "external",
        ]
    ]
):
    root: Literal[
        "root", "runner", "studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "web", "external"
    ]


class VersionRef1(BaseModel):
    """
    a version reference resolved by the checker (data-model §4.2); never a literal string
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    from_lock: Literal[
        "uv.lock",
        "studio/uv.lock",
        "studio/isaac/uv.lock",
        "studio/rtx/uv.lock",
        "studio/isaaclab/uv.lock",
        "pipeline/uv.lock",
        "pipeline/accel/uv.lock",
        "web/pnpm-lock.yaml",
    ]
    package: Package


class VersionRef2(BaseModel):
    """
    a version reference resolved by the checker (data-model §4.2); never a literal string
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    from_binary: BinaryId
    release: Version
    sha256: Sha256


class VersionRef3(BaseModel):
    """
    a version reference resolved by the checker (data-model §4.2); never a literal string
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    from_git_tag: Version
    repository: HttpsUrl


class VersionRef4(BaseModel):
    """
    a version reference resolved by the checker (data-model §4.2); never a literal string
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    own: Literal[True]


class VersionRef(RootModel[VersionRef1 | VersionRef2 | VersionRef3 | VersionRef4]):
    root: Annotated[
        VersionRef1 | VersionRef2 | VersionRef3 | VersionRef4,
        Field(description="a version reference resolved by the checker (data-model §4.2); never a literal string"),
    ]


class AlternativesRejectedItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(max_length=64, min_length=1)]
    reason: Annotated[str, Field(max_length=300, min_length=1)]


class Entry(BaseModel):
    """
    tool registry entry (data-model §4.1)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: ToolId
    name: Annotated[str, Field(max_length=64, min_length=1)]
    category: Literal["studio-tool", "component"]
    envs: Annotated[list[ToolEnv], Field(max_length=4, min_length=1)]
    version: VersionRef
    spdx: Annotated[list[SpdxId], Field(max_length=4, min_length=1)]
    osi: bool
    licence_class: LicenceClass
    ring: Literal["Adopt", "Trial", "Assess", "Hold"]
    lane: Literal["live", "replay", "local-only"]
    performance: Literal["public", "local-only"]
    role: Annotated[str, Field(max_length=300, min_length=1)]
    cases: Annotated[list[CaseId], Field(max_length=12)]
    produces: Annotated[list[ArtefactKind], Field(max_length=16)]
    status: Literal["not-yet-run", "done", "evaluated-not-adopted"]
    reason: Annotated[str | None, Field(max_length=600, min_length=20)] = None
    docs_page: Annotated[
        str | None,
        Field(
            max_length=96,
            pattern="^docs/frameworks/(not-adopted-)?[a-z0-9-]{1,64}\\.md$",
        ),
    ] = None
    alternatives_rejected: Annotated[list[AlternativesRejectedItem] | None, Field(max_length=8)] = None
    notice: Annotated[str | None, Field(max_length=300)] = None


class PitstudioToolRegistry(BaseModel):
    """
    The studio tool registry studio/tools.yaml (DC-001-03, spec 001-contracts).
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
    tools: Annotated[list[Entry], Field(max_length=64, min_length=1)]
