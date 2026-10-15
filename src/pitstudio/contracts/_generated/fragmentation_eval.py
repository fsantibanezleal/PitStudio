# Generated from contracts/fragmentation-eval.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class FoldIouItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1.0)]


class Trtr(BaseModel):
    """
    U-Net trained on real training lists, per fold
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["succeeded", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    fold_iou: Annotated[
        list[FoldIouItem] | None,
        Field(description="one value per fold, fold order", max_length=5, min_length=5),
    ] = None


class RhoItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=100.0)]


class Tstr(BaseModel):
    """
    U-Net trained on synthetic tiles only, scored on the real test originals
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["succeeded", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    fold_iou: Annotated[
        list[FoldIouItem] | None,
        Field(description="one value per fold, fold order", max_length=5, min_length=5),
    ] = None
    rho: Annotated[
        list[RhoItem] | None,
        Field(description="IoU_TSTR / IoU_TRTR per fold", max_length=5, min_length=5),
    ] = None
    rho_mean: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    rho_min: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    rho_std: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    threshold: float = None
    verdict: Literal["pass", "fail"] | None = None


class Parameter(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sigma_g_px: Literal[1, 2] | float
    min_distance_px: Literal[3, 5, 7, 9]
    offset: Literal[0] | float


class Watershed(BaseModel):
    """
    classical watershed + Swebrec baseline on the real test originals
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["succeeded", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    fold_iou: Annotated[
        list[FoldIouItem] | None,
        Field(description="one value per fold, fold order", max_length=5, min_length=5),
    ] = None
    parameters: Annotated[
        list[Parameter] | None,
        Field(
            description="parameters chosen per fold on its training originals",
            max_length=5,
            min_length=5,
        ),
    ] = None


class MreUnetIntervalItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000.0)]


class SyntheticX50(BaseModel):
    """
    x50 mean relative error of the TSTR U-Net on synthetic held-out views
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["succeeded", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    held_out_piles: Annotated[int | None, Field(ge=50, le=100000)] = None
    views: Annotated[int | None, Field(ge=1, le=1000000)] = None
    mre_unet: Annotated[float | None, Field(ge=0.0, le=1000.0)] = None
    mre_unet_interval: Annotated[
        list[MreUnetIntervalItem] | None,
        Field(description="95 % pile-bootstrap interval", max_length=2, min_length=2),
    ] = None
    mre_watershed: Annotated[float | None, Field(ge=0.0, le=1000.0)] = None
    occlusion_bias_mean: Annotated[float | None, Field(ge=-1.0, le=1000.0)] = None
    threshold: float = None
    verdict: Literal["pass", "fail"] | None = None


class Shift(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    corruption: Literal["dust"]
    severity: Literal[3]
    depth_m: Literal[100]


class Duplicates(BaseModel):
    """
    duplicate scan over all synthetic tiles and the 960 real files
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["succeeded", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    phash_hamming_max: Literal[4] | None = None
    cosine_min: float = None
    synthetic_tiles: Annotated[int | None, Field(ge=0, le=10000000)] = None
    real_files: Literal[960] | None = None
    synthetic_real_flags: Annotated[int | None, Field(ge=0, le=1000000)] = None
    train_test_flags: Annotated[int | None, Field(ge=0, le=1000000)] = None
    cross_group_leaks: Annotated[Literal[0] | None, Field(description="a leak stops the run with split-leak")] = None


class AucIntervalItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1.0)]


class AucInterval(RootModel[list[AucIntervalItem]]):
    """
    95 % cluster-bootstrap interval
    """

    root: Annotated[
        list[AucIntervalItem],
        Field(description="95 % cluster-bootstrap interval", max_length=2, min_length=2),
    ]


class Family(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    family: Literal["logistic", "mlp"]
    auc: Annotated[float, Field(ge=0.0, le=1.0)]
    auc_interval: AucInterval
    real_vs_real_auc: Annotated[float, Field(ge=0.0, le=1.0)]
    real_vs_real_interval: AucInterval
    auc_minus_real_vs_real: Annotated[float, Field(ge=-1.0, le=1.0)]
    shift_auc: Annotated[float, Field(ge=0.0, le=1.0)]
    train_vs_test_auc: Annotated[float, Field(ge=0.0, le=1.0)]


class IntervalItem(RootModel[float]):
    root: Annotated[float, Field(ge=-1000.0, le=1000.0)]


class Interval(RootModel[list[IntervalItem]]):
    """
    95 % percentile interval: lower, upper
    """

    root: Annotated[
        list[IntervalItem],
        Field(
            description="95 % percentile interval: lower, upper",
            max_length=2,
            min_length=2,
        ),
    ]


class NoFit(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    unet: Annotated[int, Field(ge=0, le=1000000)]
    watershed: Annotated[int, Field(ge=0, le=1000000)]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class RealComparison(BaseModel):
    """
    paired cluster bootstrap on the 240 real test originals
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["succeeded", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    pairing_unit: Literal["original"] | None = None
    units: Literal[240] | None = None
    clusters: Literal[72] | None = None
    bootstrap_b: Literal[10000] | None = None
    mean_difference: Annotated[
        float | None,
        Field(description="mean of e_watershed - e_unet", ge=-1000.0, le=1000.0),
    ] = None
    interval: Interval | None = None
    verdict: Annotated[
        Literal["better", "no significant difference", "worse"] | None,
        Field(description="U-Net against watershed + Swebrec"),
    ] = None
    no_fit: NoFit | None = None


class SyntheticComparison(BaseModel):
    """
    paired bootstrap over synthetic held-out piles
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["succeeded", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    pairing_unit: Literal["pile"] | None = None
    units: Annotated[int | None, Field(ge=50, le=100000)] = None
    bootstrap_b: Literal[10000] | None = None
    mean_difference: Annotated[
        float | None,
        Field(description="mean of e_watershed - e_unet", ge=-1000.0, le=1000.0),
    ] = None
    interval: Interval | None = None
    verdict: Annotated[
        Literal["better", "no significant difference", "worse"] | None,
        Field(description="U-Net against watershed + Swebrec"),
    ] = None
    no_fit: NoFit | None = None


class Embedding(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Literal["dinov2-vitb14"]
    weights_sha256: Sha256
    input_px: Literal[224]
    token: Literal["cls"]


class C2st(BaseModel):
    """
    classifier two-sample test, real-versus-real baseline, injected shift and train-versus-test
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["succeeded", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    embedding: Embedding | None = None
    n_synthetic: Annotated[int | None, Field(ge=100, le=100000)] = None
    n_real: Annotated[int | None, Field(ge=100, le=240)] = None
    bootstrap_b: Literal[1000] | None = None
    shift: Shift | None = None
    families: Annotated[list[Family] | None, Field(max_length=2, min_length=2)] = None
    powered: Annotated[bool | None, Field(description="both injected-shift AUCs >= 0.80")] = None
    verdict: Literal["pass", "fail", "inconclusive (no power)"] | None = None


class FragmentationEvaluationReport(BaseModel):
    """
    Evaluation report of case D1 written by s50_evaluate: TSTR / TRTR per fold, x50 errors, paired comparisons, realism checks and statuses (DC-012-03, spec 012-fragmentation).
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
    run_id: RunId
    archive_status: Literal["verified", "unavailable", "sha256-mismatch"]
    isaac_sim: Annotated[
        Literal["passing", "not-passing"],
        Field(description="Isaac Sim status in the capability report"),
    ]
    trtr: Annotated[Trtr, Field(description="U-Net trained on real training lists, per fold")]
    tstr: Annotated[
        Tstr,
        Field(description="U-Net trained on synthetic tiles only, scored on the real test originals"),
    ]
    watershed: Annotated[
        Watershed,
        Field(description="classical watershed + Swebrec baseline on the real test originals"),
    ]
    synthetic_x50: Annotated[
        SyntheticX50,
        Field(description="x50 mean relative error of the TSTR U-Net on synthetic held-out views"),
    ]
    real_comparison: Annotated[
        RealComparison,
        Field(description="paired cluster bootstrap on the 240 real test originals"),
    ]
    synthetic_comparison: Annotated[
        SyntheticComparison,
        Field(description="paired bootstrap over synthetic held-out piles"),
    ]
    c2st: Annotated[
        C2st,
        Field(
            description="classifier two-sample test, real-versus-real baseline, injected shift and train-versus-test"
        ),
    ]
    duplicates: Annotated[
        Duplicates,
        Field(description="duplicate scan over all synthetic tiles and the 960 real files"),
    ]
    attribution: Annotated[
        Literal[
            "Si, Zhu, Di, Wang (2019). Rock fragment image segmentation combining CNN and watershed algorithm. Mendeley Data, V1. https://doi.org/10.17632/78ht3pjsr4.1. Licensed under CC BY 4.0."
        ],
        Field(description="dataset-card attribution, verbatim"),
    ]
    label: Literal["TRTR only — synthetic arm not run"] | None = None
    d1_statement: Literal["synthetic-only U-Net claim; no measured sim-to-real"] | None = None
