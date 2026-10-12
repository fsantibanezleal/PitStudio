# Generated from contracts/il-episodes.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr
from typing_extensions import TypeAliasType


class PolicyId(RootModel[Literal["IL-1", "IL-2", "IL-3"]]):
    root: Annotated[Literal["IL-1", "IL-2", "IL-3"], Field(description="Policy id.")]


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class TaskId(RootModel[Literal["Pit-HaulTruck-Ramp", "Pit-Excavator-Dig-FEE", "Pit-Loader-Dig-FEE"]]):
    root: Annotated[
        Literal["Pit-HaulTruck-Ramp", "Pit-Excavator-Dig-FEE", "Pit-Loader-Dig-FEE"],
        Field(description="Isaac Lab task id."),
    ]


class Train(BaseModel):
    """
    Training seed range.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    start: Annotated[int, Field(description="Seed (unsigned 32-bit).", ge=0, le=4294967295)]
    count: Annotated[int, Field(ge=1, le=1000000)]


class Tune(BaseModel):
    """
    Baseline tuning seeds (20).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    start: Annotated[int, Field(description="Seed (unsigned 32-bit).", ge=0, le=4294967295)]
    count: Literal[20]


class Eval(BaseModel):
    """
    Evaluation seeds (100).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    start: Annotated[int, Field(description="Seed (unsigned 32-bit).", ge=0, le=4294967295)]
    count: Literal[100]


class Seeds(BaseModel):
    """
    Seed ranges [start, start + count); pairwise disjointness is a checker rule.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    train: Annotated[Train, Field(description="Training seed range.")]
    tune: Annotated[Tune | None, Field(description="Baseline tuning seeds (20).")] = None
    eval: Annotated[Eval, Field(description="Evaluation seeds (100).")]


class Training(BaseModel):
    """
    rsl_rl PPO settings (FR-014-25).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    num_envs: Annotated[
        int,
        Field(
            description="Parallel environments (from the bench measurement within the VRAM budget).",
            ge=1,
            le=16384,
        ),
    ]
    iterations: Annotated[int, Field(description="PPO iterations.", ge=1, le=100000)]
    checkpoint_every: Annotated[Literal[100], Field(description="Checkpoint cadence (iterations).")]
    hidden_units: Annotated[list[int], Field(description="Actor and critic MLP hidden layers.")]
    gamma: float
    gae_lambda: float
    clip_ratio: float
    steps_per_env: Annotated[Literal[24], Field(description="Steps per environment per update.")]


class Mpm(BaseModel):
    """
    IL-2b MPM evaluation tier (FR-014-22).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    episodes: Annotated[int, Field(description="Paired MPM episodes n.", ge=16, le=64)]
    envs: Annotated[int, Field(description="MPM environments.", ge=16, le=64)]
    material: Annotated[
        ArtefactId,
        Field(description="Dry-sand material of the DEM calibration artefact (spec 011)."),
    ]


class ObservationLayoutItem(BaseModel):
    """
    One observation segment.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    segment: Literal[
        "speed_yaw_rate_pitch",
        "lateral_heading_error",
        "path_points",
        "payload_fraction",
        "ray_ranges",
        "lv_relative_position",
        "lv_relative_velocity",
        "lv_ttc",
    ]
    size: Annotated[int, Field(ge=1, le=63)]


RewardWeightsAdditionalProperty = TypeAliasType(
    "RewardWeightsAdditionalProperty", Annotated[float, Field(ge=0.0, le=10000.0)]
)


class PayloadFractionItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1.0)]


class RollingResistancePctItem(RootModel[float]):
    root: Annotated[float, Field(ge=2.0, le=8.0)]


class FrictionDryItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.55, le=0.75)]


class FrictionWetItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.25, le=0.45)]


class ActuatorDelayStep(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=3)]


class Randomisation(BaseModel):
    """
    IL-1 domain randomisation within the FR-014-13 limits.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    payload_fraction: Annotated[
        list[PayloadFractionItem],
        Field(
            description="Payload fraction of rated [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    rolling_resistance_pct: Annotated[
        list[RollingResistancePctItem],
        Field(
            description="Rolling resistance (%) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    friction_dry: Annotated[
        list[FrictionDryItem],
        Field(
            description="Dry tyre-road friction (-) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    friction_wet: Annotated[
        list[FrictionWetItem],
        Field(
            description="Wet tyre-road friction (-) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    wet_probability: float
    actuator_delay_steps: Annotated[
        list[ActuatorDelayStep],
        Field(
            description="Actuator delay (control steps) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    ray_noise_base_m: Annotated[
        float,
        Field(
            description="Ray noise sigma constant term (m), at most 0.02.",
            ge=0.0,
            le=0.02,
        ),
    ]
    ray_noise_per_range: Annotated[
        float,
        Field(
            description="Ray noise sigma per metre of range (-), at most 0.01.",
            ge=0.0,
            le=0.01,
        ),
    ]
    speed_noise_sd_m_per_s: Annotated[
        float,
        Field(description="Speed noise sigma (m/s), at most 0.1.", ge=0.0, le=0.1),
    ]
    heading_noise_sd_deg: Annotated[
        float,
        Field(description="Heading noise sigma (deg), at most 0.5.", ge=0.0, le=0.5),
    ]


class Budget(BaseModel):
    """
    Budgets (NFR-014-01, NFR-014-02).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    vram_gb: Annotated[
        float,
        Field(description="Device-peak VRAM budget (GB), at most 5.", gt=0.0, le=5.0),
    ]
    gpu_hours: Annotated[
        float,
        Field(
            description="GPU-time stop limit (h), at most 8 (2 x the upper estimate).",
            gt=0.0,
            le=8.0,
        ),
    ]


class Evaluation(BaseModel):
    """
    IL-1 evaluation protocol (FR-014-14, FR-014-32).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    episodes: Literal[100]
    deterministic_actions: Literal[True]
    light_vehicle_mix: Annotated[list[int], Field(description="Episodes with 0, 1, 2 and 3 light vehicles.")]


class HaulTruckTask(BaseModel):
    """
    IL-1 haul truck task parameters.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    policy: Literal["IL-1"]
    task: Literal["Pit-HaulTruck-Ramp"]
    stage: Annotated[Literal["st60_il_train"], Field(description="IL-1 has no MPM tier.")]
    observation_size: Literal[63]
    action_size: Literal[2]
    control_hz: Literal[20]
    observation_layout: Annotated[
        list[ObservationLayoutItem],
        Field(
            description="Observation layout in order; sizes sum to observation_size (checker rule).",
            max_length=16,
            min_length=1,
        ),
    ]
    reward_weights: Annotated[
        dict[
            constr(
                pattern=r"^(progress|lateral_error|heading_error|overspeed|jerk|collision|ttc|energy)$", max_length=32
            ),
            RewardWeightsAdditionalProperty,
        ],
        Field(
            description="Reward-term weights (terms are already signed).",
            max_length=8,
            min_length=1,
        ),
    ]
    site_speed_limit_km_h: Annotated[
        float | None,
        Field(description="Site speed limit (km/h), default 40.", gt=0.0, le=60.0),
    ] = None
    randomisation: Annotated[
        Randomisation,
        Field(description="IL-1 domain randomisation within the FR-014-13 limits."),
    ]
    seeds: Seeds
    training: Training
    budget: Annotated[Budget, Field(description="Budgets (NFR-014-01, NFR-014-02).")]
    evaluation: Annotated[
        Evaluation,
        Field(description="IL-1 evaluation protocol (FR-014-14, FR-014-32)."),
    ]


class ObservationLayoutItem1(BaseModel):
    """
    One observation segment.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    segment: Literal[
        "joint_positions", "joint_velocities", "joint_torques", "bucket_tip_pose", "terrain_heights", "fill_estimate"
    ]
    size: Annotated[int, Field(ge=1, le=46)]


class BulkDensityKgM3Item(RootModel[float]):
    root: Annotated[float, Field(ge=1500.0, le=2100.0)]


class CohesionKpaItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=20.0)]


class AdhesionRatioItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=0.5)]


class FrictionAngleDegItem(RootModel[float]):
    root: Annotated[float, Field(ge=25.0, le=40.0)]


class SoilToolFrictionDegItem(RootModel[float]):
    root: Annotated[float, Field(ge=10.0, le=25.0)]


class Randomisation1(BaseModel):
    """
    IL-2 / IL-3 soil randomisation within the FR-014-19 limits.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    bulk_density_kg_m3: Annotated[
        list[BulkDensityKgM3Item],
        Field(
            description="Bulk density (kg/m3) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    cohesion_kpa: Annotated[
        list[CohesionKpaItem],
        Field(
            description="Cohesion (kPa) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    adhesion_ratio: Annotated[
        list[AdhesionRatioItem],
        Field(
            description="Adhesion c_a as a fraction of c (-) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    friction_angle_deg: Annotated[
        list[FrictionAngleDegItem],
        Field(
            description="Friction angle (deg) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    soil_tool_friction_deg: Annotated[
        list[SoilToolFrictionDegItem],
        Field(
            description="Soil-tool friction (deg); upper <= friction-angle lower is a checker rule [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    surcharge_kpa: Literal[0]
    face_height_noise_m: Annotated[
        float,
        Field(
            description="Initial face height noise amplitude (m), at most 0.3.",
            ge=0.0,
            le=0.3,
        ),
    ]


class Budget1(BaseModel):
    """
    Budgets (NFR-014-01, NFR-014-02).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    vram_gb: Annotated[
        float,
        Field(description="Device-peak VRAM budget (GB), at most 6.", gt=0.0, le=6.0),
    ]
    gpu_hours: Annotated[
        float,
        Field(
            description="GPU-time stop limit (h), at most 16 (2 x the upper estimate).",
            gt=0.0,
            le=16.0,
        ),
    ]


class Evaluation1(BaseModel):
    """
    IL-2 / IL-3 evaluation protocol (FR-014-32, FR-014-35).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    episodes: Literal[100]
    deterministic_actions: Literal[True]
    time_limit_s: Literal[30]


class DigTask(BaseModel):
    """
    IL-2 excavator / IL-3 loader dig task parameters.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    policy: Literal["IL-2", "IL-3"]
    task: Literal["Pit-Excavator-Dig-FEE", "Pit-Loader-Dig-FEE"]
    stage: Literal["st60_il_train", "st61_il_mpm_eval"]
    observation_size: Literal[46]
    action_size: Literal[4]
    control_hz: Annotated[float, Field(description="Policy rate (Hz).", gt=0.0, le=100.0)]
    observation_layout: Annotated[
        list[ObservationLayoutItem1],
        Field(
            description="Observation layout in order; sizes sum to observation_size (checker rule).",
            max_length=16,
            min_length=1,
        ),
    ]
    reward_weights: Annotated[
        dict[
            constr(
                pattern=r"^(fill_gain|target_fill|stall|lift_off|joint_limit|action_rate|cycle_time)$", max_length=32
            ),
            RewardWeightsAdditionalProperty,
        ],
        Field(
            description="Reward-term weights (terms are already signed).",
            max_length=7,
            min_length=1,
        ),
    ]
    randomisation: Annotated[
        Randomisation1,
        Field(description="IL-2 / IL-3 soil randomisation within the FR-014-19 limits."),
    ]
    seeds: Seeds
    training: Training | None = None
    budget: Annotated[Budget1, Field(description="Budgets (NFR-014-01, NFR-014-02).")]
    evaluation: Annotated[
        Evaluation1,
        Field(description="IL-2 / IL-3 evaluation protocol (FR-014-32, FR-014-35)."),
    ]
    mpm: Mpm | None = None


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


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


class SchemaVersion(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Contract version (major 1).",
            max_length=8,
            pattern="^1\\.[0-9]+$",
        ),
    ]


class Il1Episode(BaseModel):
    """
    One row of an IL-1 episode table (Parquet).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    seed: Annotated[int, Field(description="Episode seed.", ge=0, le=4294967295)]
    light_vehicles: Annotated[int, Field(description="Light vehicles in the scenario.", ge=0, le=3)]
    termination: Literal["success", "collision", "lateral_error", "time_limit", "invalid_value"]
    success: Annotated[bool, Field(description="Reached L_route - 2 m without collision.")]
    collision: bool
    steps: Annotated[int, Field(description="Control steps.", ge=0, le=10000000)]
    sum_sq_lateral_error_m2: Annotated[
        float,
        Field(
            description="Sum of squared lateral errors over the steps (m2).",
            ge=0.0,
            le=1000000000000.0,
        ),
    ]
    rms_lateral_error_m: Annotated[float, Field(description="Per-episode RMS lateral error (m).", ge=0.0, le=100.0)]
    max_lateral_error_m: Annotated[
        float,
        Field(description="Per-episode maximum lateral error (m).", ge=0.0, le=100.0),
    ]
    min_ttc_s: Annotated[
        float,
        Field(description="Minimum TTC (s); +inf (Parquet) when never closing.", ge=0.0),
    ]
    energy_kwh_per_t_km: Annotated[
        float,
        Field(
            description="Traction energy per gross tonne-kilometre (kWh/(t km)).",
            ge=0.0,
            le=100.0,
        ),
    ]
    frac_within_v_lim: Annotated[float, Field(description="Fraction of steps within v_lim.", ge=0.0, le=1.0)]


class DigEpisode(BaseModel):
    """
    One row of an IL-2 / IL-3 episode table (Parquet).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    seed: Annotated[int, Field(description="Episode seed.", ge=0, le=4294967295)]
    termination: Literal["completed", "time_limit", "invalid_value"]
    fill_factor: Annotated[
        float,
        Field(
            description="Fill factor k_f at dig completion or at the time limit (-).",
            ge=0.0,
            le=3.0,
        ),
    ]
    cycle_time_s: Annotated[
        float,
        Field(description="Cycle time t_c (s); 30 if not completed.", gt=0.0, le=30.0),
    ]
    productivity_per_s: Annotated[float, Field(description="Productivity P = k_f / t_c (1/s).", ge=0.0, le=100.0)]
    stalled: Annotated[bool, Field(description="At least one stall event.")]
    lift_off: Annotated[
        bool,
        Field(description="Bucket lifted >= 0.5 m above the local terrain after cutting."),
    ]


class Controller(BaseModel):
    """
    Controller that produced the episodes.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["policy", "pure-pursuit-pid", "scripted-dig"]
    sha256: Annotated[
        Sha256,
        Field(description="Checkpoint digest, or digest of the frozen baseline parameters."),
    ]


class Table(BaseModel):
    """
    Parquet episode table.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    bytes: Annotated[int, Field(ge=0, le=10000000)]
    sha256: Sha256
    rows: Annotated[int, Field(description="Episodes in the table.", ge=1, le=10000)]


class PitstudioIlEpisodeTable(BaseModel):
    """
    JSON sidecar of an IL episode table, with the IL-1 and IL-2 / IL-3 row column sets as $defs (DC-014-04, spec 014-robot-learning).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    policy: PolicyId
    arm: Annotated[
        Literal["policy", "baseline", "twin", "mpm"],
        Field(description="Arm of the paired comparison."),
    ]
    run_id: RunId
    controller: Annotated[Controller, Field(description="Controller that produced the episodes.")]
    deterministic_actions: Annotated[Literal[True], Field(description="Mean action, no sampling.")]
    seed_set_sha256: Annotated[Sha256, Field(description="SHA-256 of the sorted seed list (pairing check).")]
    column_set: Literal["il1-episode", "dig-episode"]
    table: Annotated[Table, Field(description="Parquet episode table.")]
