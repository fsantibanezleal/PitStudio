# Generated from contracts/fetch-record.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class PublisherChecksum(RootModel[str]):
    root: Annotated[str, Field(max_length=71, pattern="^(md5:[0-9a-f]{32}|sha256:[0-9a-f]{64})$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class HttpsUrl(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=2048,
            pattern="^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$",
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


class Relglob(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_*?]([A-Za-z0-9._*? -]{0,98}[A-Za-z0-9_*?])?(/[A-Za-z0-9_*?]([A-Za-z0-9._*? -]{0,98}[A-Za-z0-9_*?])?){0,15}$",
        ),
    ]


class EnvVar(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Z][A-Z0-9_]{2,63}$")]


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


class Bytes(RootModel[int]):
    root: Annotated[int, Field(ge=1, le=68719476736)]


class File(BaseModel):
    """
    file record (data-model §5.1.1); null sha256 / bytes = not yet pinned / known
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    url: HttpsUrl
    sha256: Sha256 | None
    bytes: Bytes | None
    name: Relpath | None = None
    spdx: SpdxId | None = None
    kind: Literal["raster", "point-cloud", "vector", "image-set", "table", "document", "archive"]
    publisher_checksum: Annotated[
        str | None,
        Field(max_length=71, pattern="^(md5:[0-9a-f]{32}|sha256:[0-9a-f]{64})$"),
    ] = None
    uncompressed_bytes: Annotated[int | None, Field(ge=1, le=68719476736)] = None
    extract: Annotated[list[Relglob] | None, Field(max_length=64, min_length=1)] = None


class Entry1(BaseModel):
    """
    licence class allowed for (spdx, kind) by data-model §5.2
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["real"]
    spdx: Literal["LicenseRef-USGov-PD"]
    licence_class: Literal["public-domain"]


class Entry2(BaseModel):
    """
    licence class allowed for (spdx, kind) by data-model §5.2
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["real"]
    spdx: Literal["CC0-1.0", "DL-DE-ZERO-2.0"]
    licence_class: Literal["open-no-attribution"]


class Entry3(BaseModel):
    """
    licence class allowed for (spdx, kind) by data-model §5.2
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["real"]
    spdx: Literal["CC-BY-4.0", "LicenseRef-Copernicus-CLMS"]
    licence_class: Literal["attribution"]


class Entry4(BaseModel):
    """
    licence class allowed for (spdx, kind) by data-model §5.2
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["real"]
    spdx: Literal["CC-BY-SA-3.0", "CC-BY-SA-4.0"]
    licence_class: Literal["share-alike"]


class Entry5(BaseModel):
    """
    licence class allowed for (spdx, kind) by data-model §5.2
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["synthetic"]
    spdx: Literal["CC-BY-4.0", "Apache-2.0"]
    licence_class: Literal["own"]


class Entry6(BaseModel):
    """
    licence class allowed for (spdx, kind) by data-model §5.2
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["synthetic"]
    spdx: Literal["LicenseRef-NVIDIA-Open-Model"]
    licence_class: Literal["display-only"]


class Account(BaseModel):
    """
    `env_var` is the name of the variable holding the key, never a credential value
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    needed: bool
    env_var: EnvVar | None = None
    note: Annotated[str | None, Field(max_length=300)] = None


class Fallback(BaseModel):
    """
    substitute sources in order of preference; [] = no substitute data
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    sources: Annotated[list[Slug], Field(max_length=8)]
    text: Annotated[str, Field(max_length=300, min_length=1)]


class Entry7(BaseModel):
    """
    source registry entry (data-model §5.1)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    kind: Literal["real", "synthetic"]
    title: Annotated[str, Field(max_length=300, min_length=1)]
    landing_url: HttpsUrl
    access: Literal["direct", "api", "account", "manual"]
    files: Annotated[list[File], Field(max_length=512)]
    spdx: SpdxId
    licence_url: HttpsUrl
    licence_class: LicenceClass
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    citation: Annotated[str, Field(max_length=1000, min_length=1)]
    card: Annotated[str, Field(max_length=80, pattern="^data/cards/[a-z0-9-]{1,64}\\.md$")]
    account: Annotated[
        Account,
        Field(description="`env_var` is the name of the variable holding the key, never a credential value"),
    ]
    fallback: Annotated[
        Fallback | None,
        Field(description="substitute sources in order of preference; [] = no substitute data"),
    ] = None
    optional: bool | None = False


class Entry8(Entry1, Entry7):
    """
    source registry entry (data-model §5.1)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    kind: Literal["real", "synthetic"]
    title: Annotated[str, Field(max_length=300, min_length=1)]
    landing_url: HttpsUrl
    access: Literal["direct", "api", "account", "manual"]
    files: Annotated[list[File], Field(max_length=512)]
    spdx: SpdxId
    licence_url: HttpsUrl
    licence_class: LicenceClass
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    citation: Annotated[str, Field(max_length=1000, min_length=1)]
    card: Annotated[str, Field(max_length=80, pattern="^data/cards/[a-z0-9-]{1,64}\\.md$")]
    account: Annotated[
        Account,
        Field(description="`env_var` is the name of the variable holding the key, never a credential value"),
    ]
    fallback: Annotated[
        Fallback | None,
        Field(description="substitute sources in order of preference; [] = no substitute data"),
    ] = None
    optional: bool | None = False


class Entry9(Entry2, Entry7):
    """
    source registry entry (data-model §5.1)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    kind: Literal["real", "synthetic"]
    title: Annotated[str, Field(max_length=300, min_length=1)]
    landing_url: HttpsUrl
    access: Literal["direct", "api", "account", "manual"]
    files: Annotated[list[File], Field(max_length=512)]
    spdx: SpdxId
    licence_url: HttpsUrl
    licence_class: LicenceClass
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    citation: Annotated[str, Field(max_length=1000, min_length=1)]
    card: Annotated[str, Field(max_length=80, pattern="^data/cards/[a-z0-9-]{1,64}\\.md$")]
    account: Annotated[
        Account,
        Field(description="`env_var` is the name of the variable holding the key, never a credential value"),
    ]
    fallback: Annotated[
        Fallback | None,
        Field(description="substitute sources in order of preference; [] = no substitute data"),
    ] = None
    optional: bool | None = False


class Entry10(Entry3, Entry7):
    """
    source registry entry (data-model §5.1)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    kind: Literal["real", "synthetic"]
    title: Annotated[str, Field(max_length=300, min_length=1)]
    landing_url: HttpsUrl
    access: Literal["direct", "api", "account", "manual"]
    files: Annotated[list[File], Field(max_length=512)]
    spdx: SpdxId
    licence_url: HttpsUrl
    licence_class: LicenceClass
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    citation: Annotated[str, Field(max_length=1000, min_length=1)]
    card: Annotated[str, Field(max_length=80, pattern="^data/cards/[a-z0-9-]{1,64}\\.md$")]
    account: Annotated[
        Account,
        Field(description="`env_var` is the name of the variable holding the key, never a credential value"),
    ]
    fallback: Annotated[
        Fallback | None,
        Field(description="substitute sources in order of preference; [] = no substitute data"),
    ] = None
    optional: bool | None = False


class Entry11(Entry4, Entry7):
    """
    source registry entry (data-model §5.1)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    kind: Literal["real", "synthetic"]
    title: Annotated[str, Field(max_length=300, min_length=1)]
    landing_url: HttpsUrl
    access: Literal["direct", "api", "account", "manual"]
    files: Annotated[list[File], Field(max_length=512)]
    spdx: SpdxId
    licence_url: HttpsUrl
    licence_class: LicenceClass
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    citation: Annotated[str, Field(max_length=1000, min_length=1)]
    card: Annotated[str, Field(max_length=80, pattern="^data/cards/[a-z0-9-]{1,64}\\.md$")]
    account: Annotated[
        Account,
        Field(description="`env_var` is the name of the variable holding the key, never a credential value"),
    ]
    fallback: Annotated[
        Fallback | None,
        Field(description="substitute sources in order of preference; [] = no substitute data"),
    ] = None
    optional: bool | None = False


class Entry12(Entry5, Entry7):
    """
    source registry entry (data-model §5.1)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    kind: Literal["real", "synthetic"]
    title: Annotated[str, Field(max_length=300, min_length=1)]
    landing_url: HttpsUrl
    access: Literal["direct", "api", "account", "manual"]
    files: Annotated[list[File], Field(max_length=512)]
    spdx: SpdxId
    licence_url: HttpsUrl
    licence_class: LicenceClass
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    citation: Annotated[str, Field(max_length=1000, min_length=1)]
    card: Annotated[str, Field(max_length=80, pattern="^data/cards/[a-z0-9-]{1,64}\\.md$")]
    account: Annotated[
        Account,
        Field(description="`env_var` is the name of the variable holding the key, never a credential value"),
    ]
    fallback: Annotated[
        Fallback | None,
        Field(description="substitute sources in order of preference; [] = no substitute data"),
    ] = None
    optional: bool | None = False


class Entry13(Entry6, Entry7):
    """
    source registry entry (data-model §5.1)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    kind: Literal["real", "synthetic"]
    title: Annotated[str, Field(max_length=300, min_length=1)]
    landing_url: HttpsUrl
    access: Literal["direct", "api", "account", "manual"]
    files: Annotated[list[File], Field(max_length=512)]
    spdx: SpdxId
    licence_url: HttpsUrl
    licence_class: LicenceClass
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    citation: Annotated[str, Field(max_length=1000, min_length=1)]
    card: Annotated[str, Field(max_length=80, pattern="^data/cards/[a-z0-9-]{1,64}\\.md$")]
    account: Annotated[
        Account,
        Field(description="`env_var` is the name of the variable holding the key, never a credential value"),
    ]
    fallback: Annotated[
        Fallback | None,
        Field(description="substitute sources in order of preference; [] = no substitute data"),
    ] = None
    optional: bool | None = False


class Entry(RootModel[Entry8 | Entry9 | Entry10 | Entry11 | Entry12 | Entry13]):
    """
    source registry entry (data-model §5.1)
    """

    root: Annotated[
        Entry8 | Entry9 | Entry10 | Entry11 | Entry12 | Entry13,
        Field(description="source registry entry (data-model §5.1)"),
    ]


class Redistribution(RootModel[Literal["redistributable", "derived-only", "no-redistribution"]]):
    root: Literal["redistributable", "derived-only", "no-redistribution"]


class UtcTimestamp(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=32,
            pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\\.[0-9]{1,6})?Z$",
        ),
    ]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]{1,4}$")]


class FileBytes(RootModel[int]):
    root: Annotated[int, Field(ge=1, le=68719476736)]


class FetchRecord(BaseModel):
    """
    One record per registry file written by s00_download (DC-008-02, spec 008-data-pipeline).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    source: Slug
    name: Annotated[Relpath, Field(description="Local file name.")]
    url: HttpsUrl
    final_url: HttpsUrl | None
    stored_as: Annotated[Relpath | None, Field(description="Path relative to the data root.")]
    bytes: FileBytes | None
    expected_bytes: FileBytes | None
    sha256: Sha256 | None
    expected_sha256: Sha256 | None
    publisher_checksum: PublisherChecksum | None
    publisher_checksum_status: Literal["match", "mismatch", "not-declared", "not-checked"]
    spdx: SpdxId
    licence_class: LicenceClass
    redistribution: Redistribution
    retrieved: UtcTimestamp | None
    status: Literal["verified", "fallback-used", "unavailable", "skipped-no-account", "pin-proposed"]
    fallback_sources: Annotated[list[Slug], Field(max_length=8)]
    attempts: Annotated[int, Field(ge=0, le=6)]
