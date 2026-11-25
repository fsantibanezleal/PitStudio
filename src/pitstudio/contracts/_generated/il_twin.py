# Generated from contracts/il-twin.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


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


class PolicyAsset(BaseModel):
    """
    Exported ONNX policy.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: ArtefactId
    path: Relpath
    sha256: Sha256
    bytes: Annotated[int, Field(description="ONNX size (bytes), below 1 MB.", ge=1, le=999999)]


class Goldens(BaseModel):
    """
    Golden sequences from the Python reference twin (parity).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    bytes: Annotated[int, Field(ge=1, le=10000000)]
    sequences: Annotated[int, Field(description="Golden action sequences.", ge=1, le=64)]
    steps: Annotated[Literal[2000], Field(description="Steps per golden sequence.")]
    policy_check_steps: Annotated[
        Literal[200],
        Field(description="Closed-loop steps checked against ONNX Runtime CPU."),
    ]


class EnvelopeItem(BaseModel):
    """
    Envelope sample.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    speed_m_per_s: Annotated[float, Field(ge=0.0, le=40.0)]
    rimpull_n: Annotated[float, Field(ge=0.0, le=10000000.0)]
    retarder_n: Annotated[float, Field(ge=0.0, le=10000000.0)]


class Parameters(BaseModel):
    """
    Dynamic-bicycle twin parameters (FR-014-40).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    machine: Annotated[Slug, Field(description="Machine parameter file the values were mapped from.")]
    mass_kg: Annotated[float, Field(description="Empty mass (kg).", gt=0.0, le=1000000.0)]
    rated_payload_kg: Annotated[float, Field(description="Rated payload (kg).", gt=0.0, le=1000000.0)]
    yaw_inertia_kg_m2: Annotated[float, Field(description="Yaw inertia (kg m2).", gt=0.0, le=10000000000.0)]
    cg_to_front_axle_m: Annotated[float, Field(description="CG to front axle (m).", gt=0.0, le=20.0)]
    cg_to_rear_axle_m: Annotated[float, Field(description="CG to rear axle (m).", gt=0.0, le=20.0)]
    cornering_stiffness_front_n_per_rad: Annotated[
        float,
        Field(description="Front cornering stiffness (N/rad).", gt=0.0, le=100000000.0),
    ]
    cornering_stiffness_rear_n_per_rad: Annotated[
        float,
        Field(description="Rear cornering stiffness (N/rad).", gt=0.0, le=100000000.0),
    ]
    max_steer_deg: Annotated[float, Field(description="Maximum steering angle (deg).", gt=0.0, le=60.0)]
    max_steer_rate_deg_per_s: Annotated[float, Field(description="Maximum steering rate (deg/s).", gt=0.0, le=180.0)]
    envelope: Annotated[
        list[EnvelopeItem],
        Field(
            description="Rimpull and retarder envelope samples by speed (increasing speed is a checker rule).",
            max_length=64,
            min_length=2,
        ),
    ]
    dt_s: Annotated[float, Field(description="Semi-implicit Euler step (s).")]
    kinematic_below_m_per_s: Annotated[Literal[1], Field(description="Kinematic-bicycle switch speed (m/s).")]
    substeps: Annotated[Literal[5], Field(description="Physics substeps per animation frame.")]


class PayloadFractionItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1.0)]


class LightVehicleSpeedKmHItem(RootModel[float]):
    root: Annotated[float, Field(ge=20.0, le=40.0)]


class InputRanges(BaseModel):
    """
    Training ranges the panel clamps visitor inputs to.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    payload_fraction: Annotated[
        list[PayloadFractionItem],
        Field(
            description="Payload fraction clamp range [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    light_vehicle_speed_km_h: Annotated[
        list[LightVehicleSpeedKmHItem],
        Field(
            description="Light-vehicle speed clamp range (km/h) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]


class TruckTwin(BaseModel):
    """
    IL-1 truck twin bundle.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    label: Literal["sim-to-sim"]
    disclaimer: Literal["simulation only — compared with a classical controller on the same simulator; no field claim"]
    policy_asset: PolicyAsset
    replay: Annotated[
        ArtefactId,
        Field(description="Isaac Lab rollouts shown as REPLAY and used as the fallback."),
    ]
    goldens: Goldens
    policy: Literal["IL-1"]
    twin: Literal["dynamic-bicycle"]
    observation_size: Literal[63]
    action_size: Literal[2]
    parameters: Annotated[Parameters, Field(description="Dynamic-bicycle twin parameters (FR-014-40).")]
    input_ranges: Annotated[
        InputRanges,
        Field(description="Training ranges the panel clamps visitor inputs to."),
    ]


class BoomPivotMItem(RootModel[float]):
    root: Annotated[float, Field(ge=-20.0, le=20.0)]


class Boom(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    length_m: Annotated[float, Field(description="Link length (m).", gt=0.0, le=30.0)]


class Stick(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    length_m: Annotated[float, Field(description="Link length (m).", gt=0.0, le=30.0)]


class Bucket(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    length_m: Annotated[float, Field(description="Link length (m).", gt=0.0, le=30.0)]


class Links(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boom: Boom
    stick: Stick
    bucket: Bucket


class CohesionKpaItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=20.0)]


class FrictionAngleDegItem(RootModel[float]):
    root: Annotated[float, Field(ge=25.0, le=40.0)]


class InputRanges1(BaseModel):
    """
    Training ranges the panel clamps visitor inputs to.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    cohesion_kpa: Annotated[
        list[CohesionKpaItem],
        Field(
            description="Cohesion clamp range (kPa) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]
    friction_angle_deg: Annotated[
        list[FrictionAngleDegItem],
        Field(
            description="Friction-angle clamp range (deg) [low, high]; low <= high is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]


class Joint(BaseModel):
    """
    Revolute joint.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    lower_deg: Annotated[
        float,
        Field(
            description="Lower joint limit (deg); lower < upper is a checker rule.",
            ge=-360.0,
            le=360.0,
        ),
    ]
    upper_deg: Annotated[float, Field(description="Upper joint limit (deg).", ge=-360.0, le=360.0)]
    torque_max_n_m: Annotated[
        float,
        Field(description="Torque limit tau_max (N m), > 0.", gt=0.0, le=100000000.0),
    ]
    velocity_max_deg_per_s: Annotated[
        float,
        Field(description="Maximum joint velocity (deg/s), > 0.", gt=0.0, le=360.0),
    ]


class HttpsUrl(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=2048,
            pattern="^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$",
        ),
    ]


class Link(BaseModel):
    """
    Rigid link.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    length_m: Annotated[float, Field(description="Link length (m).", gt=0.0, le=30.0)]
    mass_kg: Annotated[float, Field(description="Link mass (kg).", gt=0.0, le=100000.0)]


class Source1(BaseModel):
    """
    Published academic source.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    citation: Annotated[
        str,
        Field(description="Authors, year, title, venue.", max_length=300, min_length=1),
    ]
    doi: Annotated[
        str,
        Field(
            description="DOI.",
            max_length=220,
            min_length=1,
            pattern="^10\\.[0-9]{4,9}/[-._;()/:A-Za-z0-9]{1,200}$",
        ),
    ]
    url: HttpsUrl | None = None
    locator: Annotated[
        str | None,
        Field(
            description="Table, figure or page of the value.",
            max_length=64,
            min_length=1,
        ),
    ] = None


class Source2(BaseModel):
    """
    Published academic source.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    citation: Annotated[
        str,
        Field(description="Authors, year, title, venue.", max_length=300, min_length=1),
    ]
    doi: Annotated[
        str | None,
        Field(
            description="DOI.",
            max_length=220,
            min_length=1,
            pattern="^10\\.[0-9]{4,9}/[-._;()/:A-Za-z0-9]{1,200}$",
        ),
    ] = None
    url: HttpsUrl
    locator: Annotated[
        str | None,
        Field(
            description="Table, figure or page of the value.",
            max_length=64,
            min_length=1,
        ),
    ] = None


class Source(RootModel[Source1 | Source2]):
    root: Annotated[Source1 | Source2, Field(description="Published academic source.")]


class Provenance(BaseModel):
    """
    Source of one field.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    source: Slug
    class_: Annotated[Literal["published", "derived"], Field(alias="class")]


class HaulTruck(BaseModel):
    """
    Rigid-frame haul truck: chassis, six wheels (two steered front, four driven rear), steering joint.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    id: Slug
    name: Annotated[
        str,
        Field(
            description="Display name (generic, never a manufacturer's model).",
            max_length=100,
            min_length=1,
        ),
    ]
    sources: Annotated[
        list[Source],
        Field(
            description="Published academic sources of the dimensions.",
            max_length=16,
            min_length=1,
        ),
    ]
    provenance: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), Provenance],
        Field(
            description="Field name to its source id; every dimension is cited (checker rule).",
            max_length=64,
            min_length=1,
        ),
    ]
    meshes: Annotated[
        dict[constr(pattern=r"^(chassis|wheel|base|boom|stick|bucket|arm)$", max_length=16), Relpath] | None,
        Field(
            description="Part to mesh file inside the generated asset folder.",
            max_length=8,
            min_length=1,
        ),
    ] = None
    kind: Literal["haul-truck"]
    empty_mass_kg: Annotated[float, Field(description="Empty mass (kg).", gt=0.0, le=1000000.0)]
    rated_payload_kg: Annotated[float, Field(description="Rated payload (kg).", gt=0.0, le=1000000.0)]
    wheel_mass_kg: Annotated[float, Field(description="Mass of one wheel (kg).", gt=0.0, le=100000.0)]
    wheelbase_m: Annotated[float, Field(description="Wheelbase (m).", gt=0.0, le=20.0)]
    track_width_m: Annotated[float, Field(description="Track width (m).", gt=0.0, le=15.0)]
    wheel_radius_m: Annotated[float, Field(description="Wheel radius (m).", gt=0.0, le=3.0)]
    wheel_width_m: Annotated[float, Field(description="Wheel width (m).", gt=0.0, le=3.0)]
    chassis_length_m: Annotated[float, Field(description="Chassis length (m).", gt=0.0, le=30.0)]
    chassis_width_m: Annotated[float, Field(description="Chassis width (m).", gt=0.0, le=15.0)]
    chassis_height_m: Annotated[float, Field(description="Chassis height (m).", gt=0.0, le=15.0)]
    cg_to_front_axle_m: Annotated[
        float,
        Field(description="Centre of gravity to front axle (m).", gt=0.0, le=20.0),
    ]
    cg_height_m: Annotated[float, Field(description="Centre-of-gravity height (m).", gt=0.0, le=10.0)]
    yaw_inertia_kg_m2: Annotated[
        float,
        Field(description="Yaw moment of inertia (kg m2).", gt=0.0, le=10000000000.0),
    ]
    cornering_stiffness_front_n_per_rad: Annotated[
        float,
        Field(
            description="Front-axle cornering stiffness (N/rad).",
            gt=0.0,
            le=100000000.0,
        ),
    ]
    cornering_stiffness_rear_n_per_rad: Annotated[
        float,
        Field(description="Rear-axle cornering stiffness (N/rad).", gt=0.0, le=100000000.0),
    ]
    max_steer_deg: Annotated[float, Field(description="Maximum steering angle (deg).", gt=0.0, le=60.0)]
    max_steer_rate_deg_per_s: Annotated[float, Field(description="Maximum steering rate (deg/s).", gt=0.0, le=180.0)]
    max_rimpull_n: Annotated[float, Field(description="Maximum rimpull (N).", gt=0.0, le=10000000.0)]
    max_retarder_n: Annotated[float, Field(description="Maximum retarder force (N).", gt=0.0, le=10000000.0)]


class Links1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boom: Link
    stick: Link
    bucket: Link


class Joints1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    swing: Joint
    boom: Joint
    stick: Joint
    bucket: Joint


class Excavator(BaseModel):
    """
    Excavator: four revolute joints (swing, boom, stick, bucket).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    id: Slug
    name: Annotated[
        str,
        Field(
            description="Display name (generic, never a manufacturer's model).",
            max_length=100,
            min_length=1,
        ),
    ]
    sources: Annotated[
        list[Source],
        Field(
            description="Published academic sources of the dimensions.",
            max_length=16,
            min_length=1,
        ),
    ]
    provenance: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), Provenance],
        Field(
            description="Field name to its source id; every dimension is cited (checker rule).",
            max_length=64,
            min_length=1,
        ),
    ]
    meshes: Annotated[
        dict[constr(pattern=r"^(chassis|wheel|base|boom|stick|bucket|arm)$", max_length=16), Relpath] | None,
        Field(
            description="Part to mesh file inside the generated asset folder.",
            max_length=8,
            min_length=1,
        ),
    ] = None
    kind: Literal["excavator"]
    operating_mass_kg: Annotated[float, Field(description="Operating mass (kg).", gt=0.0, le=1000000.0)]
    base_mass_kg: Annotated[
        float,
        Field(description="Undercarriage and house mass (kg).", gt=0.0, le=1000000.0),
    ]
    boom_pivot_m: Annotated[
        list[BoomPivotMItem],
        Field(
            description="Pivot position (x, z) in the machine frame (m).",
            max_length=2,
            min_length=2,
        ),
    ]
    links: Links1
    joints: Joints1
    bucket_width_m: Annotated[float, Field(description="Bucket width w (m).", gt=0.0, le=10.0)]
    heaped_volume_m3: Annotated[
        float,
        Field(description="Rated heaped bucket volume V_h (m3).", gt=0.0, le=100.0),
    ]


class ArmPivotMItem(RootModel[float]):
    root: Annotated[float, Field(ge=-20.0, le=20.0)]


class Links2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    arm: Link
    bucket: Link


class Joints2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lift: Joint
    tilt: Joint


class Loader(BaseModel):
    """
    Wheel loader (IL-3): lift and tilt joints.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    id: Slug
    name: Annotated[
        str,
        Field(
            description="Display name (generic, never a manufacturer's model).",
            max_length=100,
            min_length=1,
        ),
    ]
    sources: Annotated[
        list[Source],
        Field(
            description="Published academic sources of the dimensions.",
            max_length=16,
            min_length=1,
        ),
    ]
    provenance: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), Provenance],
        Field(
            description="Field name to its source id; every dimension is cited (checker rule).",
            max_length=64,
            min_length=1,
        ),
    ]
    meshes: Annotated[
        dict[constr(pattern=r"^(chassis|wheel|base|boom|stick|bucket|arm)$", max_length=16), Relpath] | None,
        Field(
            description="Part to mesh file inside the generated asset folder.",
            max_length=8,
            min_length=1,
        ),
    ] = None
    kind: Literal["loader"]
    operating_mass_kg: Annotated[float, Field(description="Operating mass (kg).", gt=0.0, le=1000000.0)]
    wheelbase_m: Annotated[float, Field(description="Wheelbase (m).", gt=0.0, le=20.0)]
    track_width_m: Annotated[float, Field(description="Track width (m).", gt=0.0, le=15.0)]
    wheel_radius_m: Annotated[float, Field(description="Wheel radius (m).", gt=0.0, le=3.0)]
    max_steer_deg: Annotated[float, Field(description="Maximum articulation angle (deg).", gt=0.0, le=60.0)]
    max_rimpull_n: Annotated[float, Field(description="Maximum rimpull (N).", gt=0.0, le=10000000.0)]
    arm_pivot_m: Annotated[
        list[ArmPivotMItem],
        Field(
            description="Pivot position (x, z) in the machine frame (m).",
            max_length=2,
            min_length=2,
        ),
    ]
    links: Links2
    joints: Joints2
    bucket_width_m: Annotated[float, Field(description="Bucket width w (m).", gt=0.0, le=10.0)]
    heaped_volume_m3: Annotated[
        float,
        Field(description="Rated heaped bucket volume V_h (m3).", gt=0.0, le=100.0),
    ]


class Joints(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boom: Joint
    stick: Joint
    bucket: Joint


class Parameters1(BaseModel):
    """
    Planar arm twin parameters, swing fixed (FR-014-41).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    machine: Annotated[Slug, Field(description="Machine parameter file the values were mapped from.")]
    boom_pivot_m: Annotated[
        list[BoomPivotMItem],
        Field(description="Boom pivot (x, z) (m).", max_length=2, min_length=2),
    ]
    links: Links
    joints: Joints
    bucket_width_m: Annotated[float, Field(description="Bucket width w (m).", gt=0.0, le=10.0)]
    heaped_volume_m3: Annotated[float, Field(description="Rated heaped volume V_h (m3).", gt=0.0, le=100.0)]
    fill_cap: Annotated[float, Field(description="Fill cap as a multiple of V_h.")]
    gravity_m_per_s2: float
    dt_s: Annotated[float, Field(description="Twin step (s).", gt=0.0, le=0.05)]


class ArmTwin(BaseModel):
    """
    IL-2 excavator twin bundle.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    label: Literal["sim-to-sim"]
    disclaimer: Literal["simulation only — compared with a classical controller on the same simulator; no field claim"]
    policy_asset: PolicyAsset
    replay: Annotated[
        ArtefactId,
        Field(description="Isaac Lab rollouts shown as REPLAY and used as the fallback."),
    ]
    goldens: Goldens
    policy: Literal["IL-2"]
    twin: Literal["planar-arm"]
    observation_size: Literal[46]
    action_size: Literal[4]
    parameters: Annotated[
        Parameters1,
        Field(description="Planar arm twin parameters, swing fixed (FR-014-41)."),
    ]
    input_ranges: Annotated[
        InputRanges1,
        Field(description="Training ranges the panel clamps visitor inputs to."),
    ]


class PitstudioWebTwinBundle(RootModel[TruckTwin | ArmTwin]):
    root: Annotated[
        TruckTwin | ArmTwin,
        Field(
            description="Web twin bundle written by s60_export: twin parameters, policy asset and golden sequences (DC-014-05, spec 014-robot-learning).",
            title="PitStudio web twin bundle",
        ),
    ]
