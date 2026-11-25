# Generated from contracts/ttf-results.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Multiplicity(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    comparisons: Literal[8]
    family_wise_claim: Literal[False]


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Seed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9223372036854775807)]


class TimeH(RootModel[float]):
    root: Annotated[float, Field(ge=-10000000.0, le=10000000.0)]


class DurationH(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=10000000.0)]


class SignedH(RootModel[float]):
    root: Annotated[float, Field(ge=-10000000.0, le=10000000.0)]


class RelError(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000000.0)]


class Snr(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000000000.0)]


class Reason(RootModel[str]):
    root: Annotated[str, Field(max_length=300, min_length=1)]


class Method(
    RootModel[
        Literal[
            "inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"
        ]
    ]
):
    root: Literal[
        "inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"
    ]


class LearnedMethod(RootModel[Literal["tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"]]):
    root: Literal["tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"]


class Cutoff(RootModel[float]):
    root: float


class Stratum(
    RootModel[
        Literal[
            "snr_obs",
            "half_snr_obs",
            "double_snr_obs",
            "snr_obs_atmospheric",
            "nominal_10",
            "nominal_30",
            "nominal_100",
        ]
    ]
):
    root: Literal[
        "snr_obs", "half_snr_obs", "double_snr_obs", "snr_obs_atmospheric", "nominal_10", "nominal_30", "nominal_100"
    ]


class Verdict(RootModel[Literal["better", "worse", "no significant difference"]]):
    root: Literal["better", "worse", "no significant difference"]


class TimeInterval(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lower_h: TimeH
    upper_h: TimeH


class RelInterval(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lower: RelError
    upper: RelError


class DifferenceInterval(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lower: Annotated[float, Field(ge=-1000000.0, le=1000000.0)]
    upper: Annotated[float, Field(ge=-1000000.0, le=1000000.0)]


class EventResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    event_id: ArtefactId
    stratum: Stratum
    method: Method
    cutoff: Cutoff
    t_c_h: TimeH
    t_f_h: TimeH
    outcome: Literal["predicted", "no failure predicted", "no forecast"]
    t_hat_f_h: TimeH | None = None
    interval_80_h: TimeInterval | None = None
    rel_error: RelError | None = None
    error_h: SignedH | None = None
    scored_at_cap: bool | None = None
    reason: Reason | None = None


class Alarm(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    event_id: ArtefactId
    stratum: Stratum
    method: Method
    alarmed: bool
    alarm_cutoff: Annotated[float | None, Field(ge=0.3, le=0.99)] = None
    lead_time_h: DurationH | None = None


class Summary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: Method
    stratum: Stratum
    cutoff: Cutoff
    n_events: Annotated[int, Field(ge=1, le=100000)]
    median_rel_error: RelError
    mean_rel_error: RelError
    p90_rel_error: RelError
    median_abs_error_h: DurationH


class AlarmSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: Method
    stratum: Stratum
    n_events: Annotated[int, Field(ge=1, le=100000)]
    never_alarmed_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    median_lead_time_h: DurationH | None = None


class BootstrapPercentile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    resamples: Literal[10000]
    method: Literal["percentile"]
    level: float
    seed: Seed


class BootstrapPaired(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    resamples: Literal[10000]
    method: Literal["paired-percentile"]
    resample_unit: Literal["sorted-event-id"]
    level: float
    seed: Seed


class Acceptance(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    criterion: Literal["SC-010-01"]
    method: LearnedMethod
    cutoff: Cutoff
    stratum: Literal["snr_obs"]
    n_events: Annotated[int | None, Field(ge=1, le=100000)] = None
    median_rel_error: RelError | None = None
    interval: RelInterval | None = None
    bootstrap: BootstrapPercentile | None = None
    threshold: float
    verdict: Literal["pass", "fail", "not run"]
    reason: Reason | None = None


class Comparison(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseline: Literal["inverse_velocity"]
    method: LearnedMethod
    cutoff: Cutoff
    stratum: Literal["snr_obs"]
    n_pairs: Annotated[int, Field(ge=2, le=100000)]
    mean_difference: Annotated[float, Field(ge=-1000000.0, le=1000000.0)]
    interval: DifferenceInterval
    bootstrap: BootstrapPaired
    verdict: Verdict


class RealRow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    cutoff: Cutoff
    method: Method
    t_c_h: TimeH
    outcome: Literal["predicted", "no failure predicted", "no forecast", "not run"]
    t_hat_f_h: TimeH | None = None
    signed_error_h: SignedH | None = None
    error_ratio: Annotated[float | None, Field(ge=-1000000.0, le=1000000.0)] = None
    scored_at_cap: bool | None = None
    reason: Reason | None = None


class RealEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    event_id: ArtefactId
    status: Literal["run", "not run"]
    reason: Reason | None = None
    label: Literal["single real event — no significance test"]
    snr_obs: Snr | None = None
    t_0_h: TimeH | None = None
    t_f_h: TimeH | None = None
    rows: Annotated[list[RealRow] | None, Field(max_length=12, min_length=12)] = None


class S4b(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    psi_deg: Literal[0, 45, 70]
    cutoff: Cutoff
    method: Method
    series: Literal["los", "full-vector-noise-free"]
    n_events: Annotated[int, Field(ge=1, le=100000)]
    median_rel_error: RelError
    excluded_ambiguous_pixels: Annotated[int, Field(ge=0, le=1000000)]


class C1TimeToFailureResults(BaseModel):
    """
    Time-to-failure results of s50_evaluate for case C1 (per event, method and cut-off; summaries; SC-010-01 statements; paired comparisons with inverse velocity; the descriptive real-event block without intervals; the S4b block) (DC-010-03, spec 010-slope).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    run_id: RunId
    snr_basis: Literal["observed", "nominal"]
    snr_obs: Snr | None = None
    t_alarm_h: Annotated[float, Field(gt=0.0, le=8760.0)]
    horizon_cap_steps: Literal[1024]
    events: Annotated[list[EventResult], Field(max_length=100000)]
    alarms: Annotated[list[Alarm], Field(max_length=50000)]
    summary: Annotated[list[Summary], Field(max_length=500)]
    alarm_summary: Annotated[list[AlarmSummary], Field(max_length=500)]
    acceptance: Annotated[list[Acceptance], Field(max_length=8)]
    comparisons: Annotated[list[Comparison], Field(max_length=8)]
    multiplicity: Multiplicity
    real_event: RealEvent
    s4b: Annotated[list[S4b] | None, Field(max_length=500)] = None
    fixture: Annotated[
        bool | None,
        Field(
            description="true while the results were computed from a contract-fixture series or section: the stages run against it, write fixture: true on every artefact and publish no lead-time claim or other result computed from it (FR-010-46)"
        ),
    ] = False
    status: Annotated[
        Literal["complete", "partial"] | None,
        Field(
            description="partial when a stratum or the real event that the comparison names is absent: each existing stratum is reported, no pooled claim or SC-010 verdict is computed over the incomplete set (FR-010-47)"
        ),
    ] = None
    missing_strata: Annotated[
        list[
            Literal[
                "snr_obs",
                "half_snr_obs",
                "double_snr_obs",
                "snr_obs_atmospheric",
                "nominal_10",
                "nominal_30",
                "nominal_100",
                "real_event",
            ]
        ]
        | None,
        Field(
            description="each stratum (or the real event) that is `not run (absent)`, in the order the comparison names them (FR-010-47)",
            max_length=8,
        ),
    ] = None
