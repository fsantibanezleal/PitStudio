# Generated from contracts/reason-pins.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class ReleaseUrl(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=200,
            pattern="^https://github\\.com/ggml-org/llama\\.cpp/releases/download/b11381/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        ),
    ]


class ArchiveBytes(RootModel[int]):
    root: Annotated[int, Field(ge=1, le=2147483647)]


class BinariesArchive(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["llama-b11381-bin-win-cuda-13.4-x64.zip"]
    url: ReleaseUrl
    bytes: ArchiveBytes
    sha256: Sha256


class CudartArchive(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["cudart-llama-bin-win-cuda-13.4-x64.zip"]
    url: ReleaseUrl
    bytes: ArchiveBytes
    sha256: Sha256


class FilePin(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sha256: Sha256
    bytes: Annotated[int, Field(ge=0, le=9007199254740991)]


class ModelFiles(
    RootModel[
        dict[
            constr(
                pattern=r"^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
                max_length=255,
            ),
            FilePin,
        ]
    ]
):
    root: Annotated[
        dict[
            constr(
                pattern=r"^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
                max_length=255,
            ),
            FilePin,
        ],
        Field(max_length=64, min_length=1),
    ]


class CosmosRevision(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^9ce19a1[0-9a-f]{33}$")]


class PromptPin(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Annotated[
        str,
        Field(
            max_length=100,
            pattern="^studio/reason/prompts/[a-z0-9][a-z0-9_-]{0,62}\\.txt$",
        ),
    ]
    sha256: Sha256


class Archives(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    binaries: BinariesArchive
    cudart: CudartArchive


class Converter(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source_tag: Literal["b11381"]
    path: Literal["convert_hf_to_gguf.py"]
    sha256: Sha256


class Llamacpp(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    build: Literal["b11381"]
    archives: Archives
    executables: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9-]{0,58}\.exe$", max_length=64), Sha256],
        Field(max_length=32, min_length=2),
    ]
    converter: Converter


class Cosmos(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    repository: Literal["nvidia/Cosmos-Reason2-2B"]
    revision: CosmosRevision
    files: ModelFiles


class Qwen(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    repository: Literal["Qwen/Qwen3-VL-2B-Instruct"]
    revision: GitSha
    files: ModelFiles


class Models(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    cosmos: Cosmos
    qwen: Qwen


class Prompts(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    system: PromptPin
    task_a_type_1: PromptPin
    task_a_type_2: PromptPin
    task_a_type_3: PromptPin
    task_a_type_4: PromptPin
    task_a_type_5: PromptPin
    task_a_type_6: PromptPin
    task_b_pair: PromptPin
    task_b_single: PromptPin
    task_c_caption: PromptPin


class ReasonLanePins(BaseModel):
    """
    Pins of the reason lane in studio/reason/pins.json: llama.cpp archives and executables, model repositories, revisions, file SHA-256 and prompt hashes (DC-015-03, spec 015-vlm).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    llamacpp: Llamacpp
    models: Models
    prompts: Prompts
