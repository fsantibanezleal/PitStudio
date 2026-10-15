# Generated from contracts/data-card.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


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


class ModulePath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=200,
            pattern="^[a-z_][a-z0-9_]{0,63}(\\.[a-z_][a-z0-9_]{0,63}){0,7}$",
        ),
    ]


class StageId(
    RootModel[
        Literal[
            "s00_download",
            "s05_synthesize",
            "s10_preprocess",
            "s20_feature_extraction",
            "s30_train",
            "s40_infer",
            "s50_evaluate",
            "s60_export",
            "s62_accel",
            "s64_bench",
            "st10_terrain",
            "st20_pit_design",
            "st30_assets",
            "st40_compose",
            "st45_validate",
            "st45b_kit_validate",
            "st50_physics",
            "st52_rtx_render",
            "st53_sensors",
            "st54_vehicles",
            "st55_sdg",
            "st56_encode",
            "st57_rain_lidar",
            "st58_kit_capture",
            "st58b_capture_splat",
            "st59_reason_bench",
            "st59a_vqa",
            "st59b_plausibility",
            "st59c_captions",
            "st60_il_train",
            "st61_il_mpm_eval",
        ]
    ]
):
    root: Literal[
        "s00_download",
        "s05_synthesize",
        "s10_preprocess",
        "s20_feature_extraction",
        "s30_train",
        "s40_infer",
        "s50_evaluate",
        "s60_export",
        "s62_accel",
        "s64_bench",
        "st10_terrain",
        "st20_pit_design",
        "st30_assets",
        "st40_compose",
        "st45_validate",
        "st45b_kit_validate",
        "st50_physics",
        "st52_rtx_render",
        "st53_sensors",
        "st54_vehicles",
        "st55_sdg",
        "st56_encode",
        "st57_rain_lidar",
        "st58_kit_capture",
        "st58b_capture_splat",
        "st59_reason_bench",
        "st59a_vqa",
        "st59b_plausibility",
        "st59c_captions",
        "st60_il_train",
        "st61_il_mpm_eval",
    ]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class Redistribution(RootModel[Literal["redistributable", "derived-only", "no-redistribution"]]):
    root: Literal["redistributable", "derived-only", "no-redistribution"]


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
    fixture: Annotated[
        bool | None,
        Field(
            description="true = a fixture source: the entry stands for files under data/samples/ or a generated stand-in; every output derived from it is marked fixture (FR-008-49, spec 008)"
        ),
    ] = False


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
    fixture: Annotated[
        bool | None,
        Field(
            description="true = a fixture source: the entry stands for files under data/samples/ or a generated stand-in; every output derived from it is marked fixture (FR-008-49, spec 008)"
        ),
    ] = False


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
    fixture: Annotated[
        bool | None,
        Field(
            description="true = a fixture source: the entry stands for files under data/samples/ or a generated stand-in; every output derived from it is marked fixture (FR-008-49, spec 008)"
        ),
    ] = False


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
    fixture: Annotated[
        bool | None,
        Field(
            description="true = a fixture source: the entry stands for files under data/samples/ or a generated stand-in; every output derived from it is marked fixture (FR-008-49, spec 008)"
        ),
    ] = False


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
    fixture: Annotated[
        bool | None,
        Field(
            description="true = a fixture source: the entry stands for files under data/samples/ or a generated stand-in; every output derived from it is marked fixture (FR-008-49, spec 008)"
        ),
    ] = False


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
    fixture: Annotated[
        bool | None,
        Field(
            description="true = a fixture source: the entry stands for files under data/samples/ or a generated stand-in; every output derived from it is marked fixture (FR-008-49, spec 008)"
        ),
    ] = False


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
    fixture: Annotated[
        bool | None,
        Field(
            description="true = a fixture source: the entry stands for files under data/samples/ or a generated stand-in; every output derived from it is marked fixture (FR-008-49, spec 008)"
        ),
    ] = False


class Entry(RootModel[Entry8 | Entry9 | Entry10 | Entry11 | Entry12 | Entry13]):
    """
    source registry entry (data-model §5.1)
    """

    root: Annotated[
        Entry8 | Entry9 | Entry10 | Entry11 | Entry12 | Entry13,
        Field(description="source registry entry (data-model §5.1)"),
    ]


class Generator(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    module: ModulePath
    stage: StageId
    version: Version
    git_sha: GitSha


class Seed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9223372036854775807)]


class Prior(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(max_length=100, min_length=1)]
    citation: Annotated[str, Field(max_length=300, min_length=1)]
    page: Annotated[str, Field(max_length=32, min_length=1)]


class Asset(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(max_length=200, min_length=1)]
    spdx: SpdxId
    licence_class: LicenceClass
    sha256: Sha256


class Metric(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["auc", "auc-minus-real-baseline", "tstr-trtr-ratio"]
    value: Annotated[float, Field(ge=0.0, le=10.0)]
    ci95_low: Annotated[float, Field(ge=0.0, le=10.0)]
    ci95_high: Annotated[float, Field(ge=0.0, le=10.0)]


class ValidationTest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    test: Literal["c2st", "tstr"]
    verdict: Literal["pending", "pass", "warn", "fail"]
    metric: Metric | None


class PhysicsBenchmark(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    benchmark: Annotated[str, Field(max_length=100, min_length=1)]
    verdict: Literal["pending", "pass", "fail"]


class Validation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[
        Literal["validated-against-real", "descriptive-only", "unvalidated"],
        Field(alias="class"),
    ]
    real_reference: Slug | None = None
    tests: Annotated[list[ValidationTest] | None, Field(max_length=16, min_length=1)] = None
    label: Literal["calibrated synthetic — not validated against real data"] | None = None
    c2st_tstr: Literal["not-applicable"] | None = None
    basis: Literal["single real event"] | None = None
    physics_benchmarks: Annotated[list[PhysicsBenchmark] | None, Field(max_length=32)] = None


class RealCard(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    id: Slug
    title: Annotated[str, Field(max_length=300, min_length=1)]
    spdx: SpdxId
    licence_class: LicenceClass
    redistribution: Redistribution
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    files_sha256: Annotated[list[Sha256 | None], Field(max_length=512)]
    kind: Literal["real"]
    landing_url: HttpsUrl
    citation: Annotated[str, Field(max_length=1000, min_length=1)]


class SyntheticCard(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    id: Slug
    title: Annotated[str, Field(max_length=300, min_length=1)]
    spdx: SpdxId
    licence_class: LicenceClass
    redistribution: Redistribution
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    files_sha256: Annotated[list[Sha256 | None], Field(max_length=512)]
    kind: Literal["synthetic"]
    synthetic: Literal[True]
    generator: Generator
    config_sha256: Sha256
    seeds: Annotated[list[Seed], Field(max_length=1024, min_length=1)]
    priors: Annotated[list[Prior], Field(max_length=256)]
    assets: Annotated[list[Asset], Field(max_length=1024)]
    validation: Validation


class DataCardFrontMatter(RootModel[RealCard | SyntheticCard]):
    root: Annotated[
        RealCard | SyntheticCard,
        Field(
            description="Front matter of data/cards/<id>.md for real and synthetic sets (DC-008-05, spec 008-data-pipeline).",
            title="Data-card front matter",
        ),
    ]
