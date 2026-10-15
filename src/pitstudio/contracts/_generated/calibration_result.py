# Generated from contracts/calibration-result.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Term(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["repose", "discharge"]
    weight: Annotated[float, Field(gt=0.0, le=1000000.0)]
    value: Annotated[float, Field(ge=0.0, le=1000000000.0)]


class Loss(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    observable: Literal["smooth-envelope"]
    softmax_beta_per_d: Literal[10]
    bin_width_d: Literal[2]
    bin_range_pct: list[int]
    terms: Annotated[list[Term], Field(max_length=2, min_length=1)]
    total: Annotated[float, Field(ge=0.0, le=1000000000.0)]
    smooth_theta_deg: Annotated[float, Field(ge=0.0, le=90.0)]
    hard_theta_deg: Annotated[float, Field(ge=0.0, le=90.0)]


class GradientCheck(BaseModel):
    """
    tape gradient against the 4 + 4 run central finite difference
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    iterate: Literal["first", "final"]
    parameter: Literal["sliding_friction", "rolling_friction"]
    mu: Annotated[float, Field(ge=0.05, le=2.0)]
    tape_gradient: Annotated[float, Field(ge=-1000000000.0, le=1000000000.0)]
    fd_gradient: Annotated[float, Field(ge=-1000000000.0, le=1000000000.0)]
    se_fd: Annotated[float, Field(ge=0.0, le=1000000000.0)]
    runs_per_side: Literal[4]
    dof: Literal[6]
    trusted: bool
    failure: Literal["none", "fd-not-significant", "sign-mismatch", "disagreement"]


class Bound(RootModel[float]):
    root: Annotated[float, Field(ge=0.05, le=2.0)]


class SlopeIntervalDegPerUnitItem(RootModel[float]):
    root: Annotated[float, Field(ge=-10000.0, le=10000.0)]


class Interval(BaseModel):
    """
    seed-ensemble delta interval; bounds null when not identified
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    level: float
    lower: Annotated[float | None, Field(ge=-100.0, le=100.0)]
    upper: Annotated[float | None, Field(ge=-100.0, le=100.0)]
    t_quantile: Annotated[
        float,
        Field(
            description="Student t 0.975 quantile with R - 1 degrees of freedom",
            gt=0.0,
            le=100.0,
        ),
    ]
    sigma_theta_deg: Annotated[float, Field(ge=0.0, le=90.0)]
    slope_deg_per_unit: Annotated[
        float,
        Field(
            description="central-difference slope of the seed means",
            ge=-10000.0,
            le=10000.0,
        ),
    ]
    slope_interval_deg_per_unit: Annotated[list[SlopeIntervalDegPerUnitItem], Field(max_length=2, min_length=2)]


class ParameterResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["sliding_friction", "rolling_friction"]
    truth: Annotated[
        float | None,
        Field(description="synthetic truth (synthetic trials only)", ge=0.05, le=2.0),
    ] = None
    start: Annotated[float, Field(ge=0.05, le=2.0)]
    bounds: Annotated[list[Bound], Field(description="lower, upper", max_length=2, min_length=2)]
    estimate: Annotated[float, Field(ge=0.05, le=2.0)]
    fd_step: Annotated[float, Field(description="h = 0.05 x estimate", gt=0.0, le=1.0)]
    interval: Annotated[
        Interval,
        Field(description="seed-ensemble delta interval; bounds null when not identified"),
    ]
    identification: Literal["identified", "not-identified", "weakly-identified"]
    covers_truth: bool | None = None


class Seed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=4294967295)]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class Target(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    theta_deg: Annotated[float, Field(description="target repose angle", ge=5.0, le=60.0)]
    discharge_rate_kg_per_s: Annotated[float | None, Field(description="secondary arm only", gt=0.0, le=10000.0)] = None
    packing_seed: Seed | None = None
    material: Slug | None = None
    knowledge_row: Annotated[
        str | None,
        Field(
            description="knowledge-table row id or calibration trial id",
            max_length=128,
            min_length=1,
            pattern="^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        ),
    ] = None
    verification: Literal["verified", "UNVERIFIED"] | None = None


class Seeds(BaseModel):
    """
    pairwise disjoint seed sets
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    target: Annotated[list[Seed], Field(max_length=64, min_length=1)]
    optimisation: Annotated[list[Seed], Field(max_length=64, min_length=1)]
    interval: Annotated[list[Seed], Field(max_length=64, min_length=1)]
    gradient_check: Annotated[list[Seed] | None, Field(max_length=64)] = None


class Cmaes(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sigma0: float
    population: Annotated[int, Field(ge=2, le=64)]
    cma_version: Version | None = None


class DemCalibrationResult(BaseModel):
    """
    One calibration trial or literature-target calibration of the Warp DEM written by the calibration driver (DC-011-04, spec 011-surrogates).
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
    kind: Literal["synthetic-trial", "literature-target"]
    arm: Literal["gradient", "cma-es"]
    trial_id: Slug
    solver: Literal["warp-dem", "newton-mpm"]
    solver_version: Version
    secondary_arm: Annotated[bool, Field(description="true: (sliding, rolling) from repose and discharge")]
    particle_count: Annotated[int, Field(ge=1, le=20000)]
    oom_fallback: Annotated[bool, Field(description="particle count halved once after out-of-memory")]
    target: Target
    parameters: Annotated[list[ParameterResult], Field(max_length=2, min_length=1)]
    loss: Loss
    window_steps: Annotated[int, Field(description="W, recorded steps", ge=100, le=5000)]
    settling_steps: Annotated[int, Field(ge=0, le=10000000)]
    packing_seeds: Annotated[int, Field(description="S", ge=2, le=64)]
    interval_runs: Annotated[int, Field(description="R", ge=2, le=64)]
    seeds: Annotated[Seeds, Field(description="pairwise disjoint seed sets")]
    budget_simulations: Annotated[
        int,
        Field(
            description="forward-equivalent budget (one adjoint pass = 2)",
            ge=1,
            le=10000,
        ),
    ]
    simulations: Annotated[int, Field(ge=0, le=10000)]
    interval_simulations: Annotated[int, Field(ge=0, le=10000)]
    check_simulations: Annotated[
        int,
        Field(description="gradient-check runs, outside the budget", ge=0, le=10000),
    ]
    stop_reason: Literal["loss-tolerance", "budget"]
    wall_time_s: Annotated[float, Field(ge=0.0, le=10000000.0)]
    deterministic_accumulation: bool
    gradient_check: Annotated[list[GradientCheck] | None, Field(max_length=4, min_length=2)] = None
    gradient_status: Literal["reliable", "unreliable"] | None = None
    cmaes: Cmaes | None = None
    label: Literal["calibrated synthetic — not validated against real data"]
