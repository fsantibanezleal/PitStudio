# Generated from contracts/physics-scenario.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Solver(RootModel[Literal["dem", "mpm-newton", "mlsmpm2d", "swe", "dust", "vehicles", "rigid-newton"]]):
    root: Annotated[
        Literal["dem", "mpm-newton", "mlsmpm2d", "swe", "dust", "vehicles", "rigid-newton"],
        Field(
            description="own Warp DEM, Newton implicit MPM, own explicit 2-D MLS-MPM twin, own shallow water, own Lagrangian dust, reduced-order vehicles, Newton rigid bodies"
        ),
    ]


class BenchmarkId(
    RootModel[
        Literal[
            "dem-contact-law",
            "dem-impact",
            "dem-restitution",
            "dem-rolling",
            "dem-slide-roll",
            "dem-beverloo-silo",
            "dem-beverloo-slot",
            "dem-repose",
            "dem-collapse-axi",
            "dem-mass",
            "mpm-newton-collapse-axi",
            "mpm-newton-silo",
            "mpm-newton-mass",
            "mpm-newton-rerun",
            "mlsmpm2d-p2g",
            "mlsmpm2d-collapse-planar",
            "mlsmpm2d-mass",
            "swe-ritter",
            "swe-stoker",
            "swe-lake-at-rest",
            "swe-volume",
            "swe-bingham-sheet",
            "swe-hydrograph",
            "dust-stokes",
            "dust-diffusion",
            "dust-plume",
            "dust-mass-budget",
            "vehicles-steady-speed",
            "vehicles-energy",
            "rigid-newton-incline",
        ]
    ]
):
    root: Annotated[
        Literal[
            "dem-contact-law",
            "dem-impact",
            "dem-restitution",
            "dem-rolling",
            "dem-slide-roll",
            "dem-beverloo-silo",
            "dem-beverloo-slot",
            "dem-repose",
            "dem-collapse-axi",
            "dem-mass",
            "mpm-newton-collapse-axi",
            "mpm-newton-silo",
            "mpm-newton-mass",
            "mpm-newton-rerun",
            "mlsmpm2d-p2g",
            "mlsmpm2d-collapse-planar",
            "mlsmpm2d-mass",
            "swe-ritter",
            "swe-stoker",
            "swe-lake-at-rest",
            "swe-volume",
            "swe-bingham-sheet",
            "swe-hydrograph",
            "dust-stokes",
            "dust-diffusion",
            "dust-plume",
            "dust-mass-budget",
            "vehicles-steady-speed",
            "vehicles-energy",
            "rigid-newton-incline",
        ],
        Field(description="physics benchmark ids; the prefix is the solver id"),
    ]


class Twin(RootModel[Literal["dem-pile", "mlsmpm2d-collapse", "swe-dam-break", "dust-release"]]):
    root: Annotated[
        Literal["dem-pile", "mlsmpm2d-collapse", "swe-dam-break", "dust-release"],
        Field(description="browser-twin scenario of FR-005-22"),
    ]


class Status(RootModel[Literal["verified", "unverified", "calibrated", "reduced", "assumed"]]):
    root: Annotated[
        Literal["verified", "unverified", "calibrated", "reduced", "assumed"],
        Field(
            description="verification status of a value: verified (primary source read), unverified (secondary or unreadable source), calibrated (fitted), reduced (deliberately lowered Young's modulus, FR-005-09), assumed (modelling choice)"
        ),
    ]


class Vec3MItem(RootModel[float]):
    root: Annotated[float, Field(ge=-100000.0, le=100000.0)]


class Vec3M(RootModel[list[Vec3MItem]]):
    root: Annotated[list[Vec3MItem], Field(max_length=3, min_length=3)]


class OrificeMItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000.0)]


class AspectRatio(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=50.0)]


class Geometry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    shape: Literal[
        "two-body",
        "plane",
        "incline",
        "silo-cylinder",
        "slot-quasi2d",
        "column-axisymmetric",
        "column-planar",
        "box",
        "channel",
        "benched-crop",
        "terrain-crop",
        "open-field",
        "grade-segment",
        "road-network",
    ]
    domain_min_m: Vec3M
    domain_max_m: Vec3M
    diameter_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    height_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    width_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    thickness_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    length_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    orifice_m: Annotated[list[OrificeMItem] | None, Field(max_length=16, min_length=1)] = None
    aspect_ratios: Annotated[list[AspectRatio] | None, Field(max_length=16, min_length=1)] = None
    incline_deg: Annotated[float | None, Field(ge=0.0, lt=90.0)] = None
    bed_slope: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    grade_pct: Annotated[float | None, Field(ge=-30.0, le=30.0)] = None
    periodic_axes: Annotated[list[Literal["x", "y", "z"]] | None, Field(max_length=3)] = None
    outflow: Annotated[
        list[Literal["x-min", "x-max", "y-min", "y-max", "z-min", "z-max", "orifice"]] | None,
        Field(max_length=7),
    ] = None


class Counts(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    particles: Annotated[int | None, Field(ge=1, le=100000000)] = None
    cells_x: Annotated[int | None, Field(ge=1, le=16384)] = None
    cells_y: Annotated[int | None, Field(ge=1, le=16384)] = None
    cells_z: Annotated[int | None, Field(ge=1, le=1024)] = None
    vehicles: Annotated[int | None, Field(ge=1, le=4096)] = None


class TimeStep1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dt_s: Annotated[
        float | None,
        Field(
            description="fixed step; the shallow-water solver uses the CFL step instead (FR-005-23)",
            gt=0.0,
            le=10.0,
        ),
    ] = None
    steps: Annotated[int, Field(ge=1, le=1000000000)]
    end_time_s: Annotated[float | None, Field(gt=0.0, le=10000000.0)] = None


class TimeStep2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dt_s: Annotated[
        float | None,
        Field(
            description="fixed step; the shallow-water solver uses the CFL step instead (FR-005-23)",
            gt=0.0,
            le=10.0,
        ),
    ] = None
    steps: Annotated[int | None, Field(ge=1, le=1000000000)] = None
    end_time_s: Annotated[float, Field(gt=0.0, le=10000000.0)]


class TimeStep(RootModel[TimeStep1 | TimeStep2]):
    root: TimeStep1 | TimeStep2


class Output(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    every_steps: Annotated[int, Field(ge=1, le=1000000000)]
    fields: bool
    replay: bool
    replay_fps: Annotated[float | None, Field(gt=0.0, le=240.0)] = None
    shard_bytes_max: Annotated[int | None, Field(description="replay shard cap (FR-005-45)", ge=1, le=10000000)] = None


class Hydrograph(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    volume_m3: Annotated[float, Field(gt=0.0, le=10000000000.0)]
    peak_m3_s: Annotated[float, Field(gt=0.0, le=10000000.0)]
    peak_fraction: Annotated[float, Field(gt=0.0, lt=1.0)]


class Breach(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    y_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    width_m: Annotated[float, Field(gt=0.0, le=10000.0)]


class DustSource(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["continuous", "instantaneous"]
    x_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    y_m: Annotated[float, Field(ge=-100000.0, le=100000.0)]
    z_m: Annotated[float, Field(ge=-5000.0, le=5000.0)]
    rate_kg_s: Annotated[float | None, Field(ge=0.0, le=1000000.0)] = None
    mass_kg: Annotated[float | None, Field(ge=0.0, le=1000000000.0)] = None
    start_s: Annotated[float, Field(ge=0.0, le=10000000.0)]
    end_s: Annotated[float | None, Field(gt=0.0, le=10000000.0)] = None


class WindM(RootModel[float]):
    root: Annotated[float, Field(ge=-100.0, le=100.0)]


class SizeMItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=100.0)]


class RigidNewtonBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    friction_coefficient: Annotated[float, Field(ge=0.0, le=10.0)]
    mass_kg: Annotated[float, Field(gt=0.0, le=2000000.0)]
    size_m: Annotated[list[SizeMItem], Field(max_length=3, min_length=3)]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class HttpsUrl(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=2048,
            pattern="^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$",
        ),
    ]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Quantity(BaseModel):
    """
    a material or vehicle value with its citation and verification status; the unit is the suffix of the field name
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    value: float
    status: Status
    source: Annotated[
        str | None,
        Field(description="citation with table or page", max_length=300, min_length=3),
    ] = None
    url: HttpsUrl | None = None
    note: Annotated[str | None, Field(max_length=300, min_length=3)] = None


class DensityKgM3(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=25000.0)]


class YoungsModulusPa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1000000000000.0)]


class YoungsModulusRealPa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1000000000000.0)]


class PoissonRatio(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=-1.0, lt=0.5)]


class Restitution(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class FrictionStatic(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=10.0)]


class FrictionRolling(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=10.0)]


class DiameterM(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=10.0)]


class DiameterMinM(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=10.0)]


class DiameterMaxM(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=10.0)]


class ReposeTargetDeg(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, lt=90.0)]


class FrictionCoefficient(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=10.0)]


class YieldPressurePa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000000000.0)]


class ViscosityPaS(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000000.0)]


class FrictionAngleDeg(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, lt=90.0)]


class CohesionPa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000000.0)]


class YieldStressPa(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000.0)]


class BinghamViscosityPaS(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=1000000.0)]


class ParticleRadiusM(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=0.001)]


class DynamicViscosityPaS(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class MaterialCard(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: Annotated[str | None, Field(max_length=120, min_length=1)] = None
    model: Literal["dem-sphere", "mpm-granular", "mpm-drucker-prager-2d", "bingham-tailings", "dust-particle", "air"]
    density_kg_m3: DensityKgM3 | None = None
    youngs_modulus_pa: YoungsModulusPa | None = None
    youngs_modulus_real_pa: YoungsModulusRealPa | None = None
    poisson_ratio: PoissonRatio | None = None
    restitution: Restitution | None = None
    friction_static: FrictionStatic | None = None
    friction_rolling: FrictionRolling | None = None
    diameter_m: DiameterM | None = None
    diameter_min_m: DiameterMinM | None = None
    diameter_max_m: DiameterMaxM | None = None
    repose_target_deg: ReposeTargetDeg | None = None
    repose_method: Literal["lifted-cylinder", "poured-cone"] | None = None
    friction_coefficient: FrictionCoefficient | None = None
    yield_pressure_pa: YieldPressurePa | None = None
    viscosity_pa_s: ViscosityPaS | None = None
    friction_angle_deg: FrictionAngleDeg | None = None
    cohesion_pa: CohesionPa | None = None
    yield_stress_pa: YieldStressPa | None = None
    bingham_viscosity_pa_s: BinghamViscosityPaS | None = None
    particle_radius_m: ParticleRadiusM | None = None
    dynamic_viscosity_pa_s: DynamicViscosityPaS | None = None


class MassKg(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=2000000.0)]


class PowerW(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=20000000.0)]


class Efficiency(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class TractionCoefficient(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=2.0)]


class DriveWeightFraction(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class RollingResistancePct(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=30.0)]


class RetarderPowerW(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=20000000.0)]


class RetarderEfficiency(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(gt=0.0, le=1.0)]


class DragCoefficient(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=5.0)]


class FrontalAreaM2(Quantity):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0, le=200.0)]


class VehicleCard(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: Annotated[str | None, Field(max_length=120, min_length=1)] = None
    mass_kg: MassKg
    power_w: PowerW
    efficiency: Efficiency
    traction_coefficient: TractionCoefficient
    drive_weight_fraction: DriveWeightFraction
    rolling_resistance_pct: RollingResistancePct
    retarder_power_w: RetarderPowerW
    retarder_efficiency: RetarderEfficiency
    drag_coefficient: DragCoefficient
    frontal_area_m2: FrontalAreaM2


class DemBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    material: Slug
    contact_capacity: Annotated[
        int,
        Field(
            description="per-particle contact-list capacity (FR-005-06, default 12)",
            ge=1,
            le=64,
        ),
    ]
    rayleigh_fraction: Annotated[
        float,
        Field(
            description="f_R of the time-step guard (FR-005-08, default 0.2)",
            gt=0.0,
            le=1.0,
        ),
    ]


class MpmNewtonBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    material: Slug
    voxel_size_m: Annotated[float, Field(gt=0.0, le=10.0)]
    grid_type: Literal["sparse", "fixed", "dense"]
    max_iterations: Annotated[int, Field(ge=1, le=100000)]
    tolerance: Annotated[float, Field(gt=0.0, lt=1.0)]


class Mlsmpm2dBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    material: Slug
    grid_cells: Annotated[int, Field(description="cells per axis of the square grid", ge=16, le=4096)]
    particles_per_cell: Annotated[int, Field(ge=1, le=64)]


class SweBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rheology: Literal["frictionless", "bingham"]
    material: Slug | None = None
    cfl: Annotated[
        float,
        Field(description="C_CFL in (0, 0.5] (FR-005-23, default 0.45)", gt=0.0, le=0.5),
    ]
    h_dry_m: Annotated[float, Field(gt=0.0, le=1.0)]
    h_thr_m: Annotated[float, Field(gt=0.0, le=100.0)]
    boundary: Literal["closed", "open"]
    initial: Literal["dam-break", "lake-at-rest", "dry", "sheet-flow"]
    dam_x_m: Annotated[float | None, Field(ge=-100000.0, le=100000.0)] = None
    depth_left_m: Annotated[float | None, Field(ge=0.0, le=1000.0)] = None
    depth_right_m: Annotated[float | None, Field(ge=0.0, le=1000.0)] = None
    surface_z_m: Annotated[float | None, Field(ge=-5000.0, le=5000.0)] = None
    inflow_depth_m: Annotated[float | None, Field(ge=0.0, le=1000.0)] = None
    hydrograph: Hydrograph | None = None
    breach: Breach | None = None


class DustBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    particle_material: Slug
    air_material: Slug
    diffusivity_m2_s: Annotated[float, Field(description="K >= 0 (FR-005-39)", ge=0.0, le=10000.0)]
    settling: bool
    ground: Literal["terrain", "reflecting", "none"]
    wind: Literal["uniform", "gridded"]
    wind_m_s: Annotated[list[WindM] | None, Field(max_length=3, min_length=3)] = None
    sources: Annotated[list[DustSource], Field(max_length=64, min_length=1)]


class VehiclesBlock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    road: Annotated[
        Literal["grade-segment", "network"],
        Field(description="a constant-grade segment (geometry.grade_pct) or the road network (DC-004-06)"),
    ]
    air_density_kg_m3: Annotated[float, Field(gt=0.0, le=2.0)]
    fleet: Annotated[list[Slug], Field(max_length=64, min_length=1)]


class PhysicsScenario(BaseModel):
    """
    Physics scenario parameters that st50_physics reads from a recipe stage's params (DC-005-01, spec 005-physics).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: SchemaVersion
    scenario: Slug
    description: Annotated[str | None, Field(max_length=300)] = None
    kind: Annotated[
        Literal["benchmark", "parity-golden", "production"],
        Field(
            description="benchmark run, browser-twin parity golden, or production rollout (any scenario that is not a benchmark)"
        ),
    ]
    solver: Solver
    device: Annotated[
        Literal["cpu", "cuda"],
        Field(description="cpu hides CUDA from the process (FR-005-49)"),
    ]
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    deterministic: Annotated[
        bool,
        Field(description="Warp deterministic execution mode for atomic operations (FR-005-48)"),
    ]
    benchmarks: Annotated[list[BenchmarkId] | None, Field(max_length=32)] = None
    twin: Twin | None = None
    geometry: Geometry
    counts: Counts
    time_step: TimeStep
    output: Output
    materials: Annotated[list[MaterialCard], Field(max_length=16)]
    vehicle_cards: Annotated[list[VehicleCard] | None, Field(max_length=16)] = None
    dem: DemBlock | None = None
    mpm_newton: MpmNewtonBlock | None = None
    mlsmpm2d: Mlsmpm2dBlock | None = None
    swe: SweBlock | None = None
    dust: DustBlock | None = None
    vehicles: VehiclesBlock | None = None
    rigid_newton: RigidNewtonBlock | None = None
