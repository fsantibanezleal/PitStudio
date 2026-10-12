# Generated from contracts/haul-energy.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Honesty(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: Literal["calibrated synthetic — not validated against real data"]
    bias_note: Literal[
        "Known DES bias: simulated truck cycle times tend to underestimate short hauls and overestimate long hauls; no real haul telemetry exists to correct it."
    ]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Semver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+\\.[0-9]+\\.[0-9]+$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]{1,4}$")]


class Engine(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    package: Literal["minehaulsim"]
    version: Semver
    pin_sha256: Sha256


class LpStatus(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["optimal", "infeasible", "unbounded", "invalid-input"]
    fallback: Literal["none", "sptf"]


class Variates(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    generator: Literal["philox4x64-10"]
    key_hash: Literal["fnv-1a-64"]


class DispatcherId(
    RootModel[Literal["fixed", "nearest", "sptf", "sq", "random", "min-idle", "lp", "ppo", "attention"]]
):
    root: Literal["fixed", "nearest", "sptf", "sq", "random", "min-idle", "lp", "ppo", "attention"]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class NodeId(RootModel[int]):
    root: Annotated[int, Field(description="Node id of the road network.", ge=0, le=2147483647)]


class Point3MItem(RootModel[float]):
    root: Annotated[float, Field(ge=-10000000.0, le=10000000.0)]


class Point3M(RootModel[list[Point3MItem]]):
    """
    World position (x, y, z) in metres.
    """

    root: Annotated[
        list[Point3MItem],
        Field(
            description="World position (x, y, z) in metres.",
            max_length=3,
            min_length=3,
        ),
    ]


class Node(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: NodeId
    kind: Literal["face", "dump", "crusher", "junction", "portal", "bay", "chute", "bin", "waypoint"]
    pos_m: Point3M


class ZoneId(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=2147483647)]


class Segment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[int, Field(ge=0, le=2147483647)]
    a: NodeId
    b: NodeId
    polyline_m: Annotated[list[Point3M], Field(max_length=512, min_length=2)]
    length_m: Annotated[float, Field(gt=0.0, le=100000.0)]
    grade_pct: Annotated[
        float,
        Field(description="Signed grade in the a -> b direction (%).", gt=-100.0, lt=100.0),
    ]
    width_class: Literal[1, 2]
    one_way: bool
    speed_limit_kmh: Annotated[float, Field(gt=0.0, le=120.0)]
    rolling_resistance_pct: Annotated[float, Field(ge=0.0, le=30.0)]
    zone_id: ZoneId | None
    single_lane_op: bool


class SegmentId(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=2147483647)]


class Zone(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[int, Field(ge=0, le=2147483647)]
    segment_ids: Annotated[list[SegmentId], Field(max_length=256, min_length=1)]
    policy: Literal["lockout", "loaded_priority", "group_batching"]
    max_in_zone: Annotated[int, Field(ge=1, le=64)]
    batch_k: Annotated[int, Field(ge=1, le=64)]
    max_hold_s: Annotated[float, Field(ge=0.0, le=86400.0)]


class Junction(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    node: NodeId
    capacity: Annotated[int, Field(ge=1, le=16)]
    cross_s: Annotated[float, Field(ge=0.0, le=3600.0)]


class Network(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    nodes: Annotated[list[Node], Field(max_length=10000, min_length=2)]
    segments: Annotated[list[Segment], Field(max_length=10000, min_length=1)]
    zones: Annotated[list[Zone], Field(max_length=256)]
    junctions: Annotated[list[Junction], Field(max_length=1024)]


class TruckClassName(RootModel[Literal["CAT_777G", "CAT_785D", "CAT_793F", "UG_TRUCK_50", "UG_TRUCK_63"]]):
    root: Annotated[
        Literal["CAT_777G", "CAT_785D", "CAT_793F", "UG_TRUCK_50", "UG_TRUCK_63"],
        Field(description="Truck class of the pinned reference-engine catalog."),
    ]


class LoaderClassName(
    RootModel[Literal["SHOVEL_25", "SHOVEL_45", "WHEEL_LOADER_18", "CHUTE", "LHD_14_LOADING", "LHD_18_LOADING"]]
):
    root: Annotated[
        Literal["SHOVEL_25", "SHOVEL_45", "WHEEL_LOADER_18", "CHUTE", "LHD_14_LOADING", "LHD_18_LOADING"],
        Field(description="Loader class of the pinned reference-engine catalog."),
    ]


class CurvePoint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    speed_kmh: Annotated[float, Field(gt=0.0, le=120.0)]
    force_kn: Annotated[float, Field(ge=0.0, le=100000.0)]


class TruckClass(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: TruckClassName
    kind: Literal["rigid", "articulated-ug"]
    payload_mean_t: Annotated[float, Field(gt=0.0, le=500.0)]
    payload_sd_t: Annotated[float, Field(ge=0.0, le=100.0)]
    empty_t: Annotated[float, Field(gt=0.0, le=1000.0)]
    width_class: Literal[1, 2]
    power_kw: Annotated[float, Field(gt=0.0, le=10000.0)]
    max_speed_kmh: Annotated[float, Field(gt=0.0, le=120.0)]
    rimpull_kn: Annotated[list[CurvePoint], Field(max_length=32, min_length=2)]
    retarder_kn: Annotated[list[CurvePoint], Field(max_length=32, min_length=2)]


class LoaderClass(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: LoaderClassName
    pass_t: Annotated[float, Field(gt=0.0, le=200.0)]
    pass_time_s: Annotated[float, Field(gt=0.0, le=3600.0)]
    time_cv: Annotated[float, Field(ge=0.0, le=2.0)]
    spot_time_s: Annotated[float, Field(ge=0.0, le=3600.0)]


class Equipment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    truck_classes: Annotated[list[TruckClass], Field(max_length=8, min_length=1)]
    loader_classes: Annotated[list[LoaderClass], Field(max_length=8, min_length=1)]


class Truck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[int, Field(ge=0, le=2147483647)]
    truck_class: TruckClassName
    start_loader: NodeId


class Loader(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    node: NodeId
    loader_class: LoaderClassName
    n_spots: Annotated[int, Field(ge=1, le=8)]
    destination_dump: Annotated[
        int | None,
        Field(
            description="Declared destination dump; absent = the first dump.",
            ge=0,
            le=2147483647,
        ),
    ] = None


class VariateProfile(RootModel[Literal["engine", "exponential", "deterministic"]]):
    root: Literal["engine", "exponential", "deterministic"]


class Term(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    loader: NodeId
    coef: Annotated[float, Field(ge=-1000000.0, le=1000000.0)]


class BlendFloor(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    terms: Annotated[list[Term], Field(max_length=64, min_length=1)]
    min: Annotated[float, Field(ge=-1000000000.0, le=1000000000.0)]


class LpConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    blend_floors: Annotated[list[BlendFloor], Field(max_length=16)]


class PolicyRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    artefact_id: ArtefactId
    onnx_sha256: Sha256
    layout_version: Literal[1]


class Dispatcher(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: DispatcherId
    lp: LpConfig | None = None
    policy: PolicyRef | None = None


class QuantileTable(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    family: Literal["uniform", "normal", "exponential", "lognormal-unit-mean"]
    sigma: Annotated[float | None, Field(ge=0.05, le=1.0)] = None
    bins: Literal[4096]
    encoding: Literal["float64-le-base64"]
    knots_f64le_b64: Annotated[
        str,
        Field(
            description="4097 knots (float64, little-endian), base64.",
            max_length=43704,
            min_length=43704,
            pattern="^[A-Za-z0-9+/]*={0,2}$",
        ),
    ]
    knots_sha256: Sha256


class EngineConstants(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    stagger_window_s: Annotated[float, Field(ge=0.0, le=3600.0)]
    dump_mean_s: Annotated[float, Field(gt=0.0, le=3600.0)]
    dump_cv: Annotated[float, Field(ge=0.0, le=2.0)]
    closure_retry_s: Annotated[float, Field(gt=0.0, le=86400.0)]
    headway_m: Annotated[float, Field(gt=0.0, le=1000.0)]
    headway_s: Annotated[float, Field(ge=0.0, le=600.0)]
    payload_min_frac_of_mean: Annotated[float, Field(ge=0.0, le=1.0)]
    payload_max_t: Annotated[float, Field(gt=0.0, le=1000.0)]


class Closure(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    start_s: Annotated[float, Field(ge=0.0, le=604800.0)]
    duration_s: Annotated[float, Field(gt=0.0, le=604800.0)]
    segment_ids: Annotated[list[SegmentId], Field(max_length=256, min_length=1)]


class Failures(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    truck_mtbf_h: Annotated[float, Field(gt=0.0, le=100000.0)]
    truck_repair_mean_s: Annotated[float, Field(gt=0.0, le=604800.0)]
    truck_repair_cv: Annotated[float, Field(ge=0.0, le=2.0)]
    loader_mtbf_h: Annotated[float, Field(gt=0.0, le=100000.0)]
    loader_repair_mean_s: Annotated[float, Field(gt=0.0, le=604800.0)]
    loader_repair_cv: Annotated[float, Field(ge=0.0, le=2.0)]
    closures: Annotated[list[Closure], Field(max_length=256)]


class KpiWindow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    warmup_s: Annotated[float, Field(ge=0.0, le=604800.0)]


class CostRates(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    truck_per_h: Annotated[float, Field(ge=0.0, le=1000000.0)]
    loader_per_h: Annotated[float, Field(ge=0.0, le=1000000.0)]
    currency: Annotated[str, Field(max_length=3, min_length=3, pattern="^[A-Z]{3}$")]


class Lhd(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[int, Field(ge=0, le=2147483647)]
    lhd_class: Literal["LHD_14", "LHD_18"]
    drawpoints: Annotated[list[NodeId], Field(max_length=16, min_length=1)]
    tip_node: NodeId
    pass_id: Annotated[int, Field(ge=0, le=2147483647)]


class OrePass(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[int, Field(ge=0, le=2147483647)]
    chute_node: NodeId
    capacity_t: Annotated[float, Field(gt=0.0, le=1000000.0)]


class ShaftBin(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    node: NodeId
    capacity_t: Annotated[float, Field(gt=0.0, le=1000000.0)]
    hoist_t_per_h: Annotated[float, Field(gt=0.0, le=100000.0)]


class PlanningOverlay(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256


class ReferenceOnly(BaseModel):
    """
    Reference-engine features outside the twin's feature set (FR-007-12).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    lhds: Annotated[list[Lhd] | None, Field(max_length=64)] = None
    ore_passes: Annotated[list[OrePass] | None, Field(max_length=16)] = None
    shaft_bin: ShaftBin | None = None
    planning_overlay: PlanningOverlay | None = None
    zone_penalty_s: Annotated[float | None, Field(ge=0.0, le=3600.0)] = None


class Truck1(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=2147483647)]


class Event(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    t_s: Annotated[float, Field(ge=0.0, le=604800.0)]
    seq: Annotated[int, Field(ge=1, le=9007199254740991)]
    kind: Literal[
        "arrive-loader",
        "load-end",
        "depart-loaded",
        "arrive-dump",
        "dump-end",
        "dispatch",
        "loader-repair-end",
        "segment-exit",
        "junction-cross-end",
        "zone-probe",
        "bin-dump",
        "lhd-start",
        "lhd-dig",
        "lhd-to-tip",
        "lhd-at-tip",
        "lhd-after-tip",
    ]
    truck: Truck1 | None
    node: NodeId | None


class CyclelogRow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    t_s: Annotated[float, Field(ge=0.0, le=604800.0)]
    truck: Annotated[int, Field(ge=0, le=2147483647)]
    node: NodeId
    event: Literal["load", "haul", "dump", "return"]
    payload_t: Annotated[float, Field(ge=0.0, le=1000.0)]


class LoaderWait(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    loader: NodeId
    wait_s: Annotated[float, Field(ge=0.0, le=1000000000.0)]


class Truck2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    truck: Annotated[int, Field(ge=0, le=2147483647)]
    downtime_s: Annotated[float, Field(gt=0.0, le=604800.0)]


class Loader1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    loader: NodeId
    downtime_s: Annotated[float, Field(gt=0.0, le=604800.0)]


class Downtime(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    truck_s: Annotated[list[Truck2], Field(max_length=400)]
    loader_s: Annotated[list[Loader1], Field(max_length=64)]


class Results(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    tonnes_t: Annotated[float, Field(ge=0.0, le=1000000000.0)]
    cycles: Annotated[int, Field(ge=0, le=2000000)]
    truck_wait_s: Annotated[float, Field(ge=0.0, le=1000000000.0)]
    loader_wait_s: Annotated[list[LoaderWait], Field(max_length=64)]
    events_executed: Annotated[int, Field(ge=0, le=2000000)]
    downtime: Downtime | None


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class KnowledgeRowId(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


class RouteSegment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    length_m: Annotated[float, Field(gt=0.0, le=100000.0)]
    grade_pct: Annotated[float, Field(gt=-100.0, lt=100.0)]
    rolling_resistance_pct: Annotated[float, Field(ge=0.0, le=30.0)]
    trolley: bool


class Route(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    length_m: Annotated[
        float,
        Field(description="Along-road length (the per-km basis).", gt=0.0, le=1000000.0),
    ]
    segments: Annotated[list[RouteSegment], Field(max_length=2048, min_length=1)]
    grade_limit_frac: Annotated[float | None, Field(gt=0.0, le=1.0)] = None
    dp_tolerance_m: Annotated[float | None, Field(gt=0.0, le=1000.0)] = None
    dem_sha256: Sha256 | None = None


class FuelLPerTKm(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000.0)]


class Basis(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    per_tonne: Literal["payload-t"]
    per_km: Literal["along-road-km"]


class Row(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    route: Slug
    drivetrain: Literal["diesel", "trolley", "bev"]
    leg: Literal["loaded", "empty"]
    empty_mass_t: Annotated[float, Field(gt=0.0, le=1000.0)]
    payload_t: Annotated[float, Field(gt=0.0, le=1000.0)]
    wheel_energy_kwh: Annotated[float, Field(ge=0.0, le=10000000.0)]
    source_energy_kwh: Annotated[float, Field(ge=0.0, le=10000000.0)]
    regenerated_kwh: Annotated[float, Field(ge=0.0, le=10000000.0)]
    source_energy_kwh_per_t: Annotated[float, Field(ge=0.0, le=100000.0)]
    fuel_l_per_t_km: FuelLPerTKm | None
    co2e_kg_per_t: Annotated[float, Field(ge=0.0, le=100000.0)]
    basis: Basis
    knowledge_rows: Annotated[list[KnowledgeRowId], Field(max_length=64, min_length=1)]
    unverified_rows: Annotated[list[KnowledgeRowId], Field(max_length=64)]


class Knowledge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    package: Literal["minephys"]
    version: Version


class RouteEnergyTable(BaseModel):
    """
    Energy, fuel and CO2e per tonne by drivetrain and route, written by the route-energy engine (DC-007-05, spec 007-haulage-dispatch).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    id: Slug
    knowledge: Knowledge
    routes: Annotated[list[Route], Field(max_length=256, min_length=1)]
    rows: Annotated[list[Row], Field(max_length=4096, min_length=1)]
    honesty: Honesty


class Header(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    scenario_id: Slug
    bundle_sha256: Sha256
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    dispatcher: DispatcherId
    variate_profile: VariateProfile
    mode: Literal["fast", "traffic"]
    horizon_s: Annotated[float, Field(gt=0.0, le=604800.0)]
    kpi_window: KpiWindow
    engine: Engine
    variates: Variates
    producer: Literal["python-reference", "typescript-twin"]
    lp: LpStatus | None = None
    policy: PolicyRef | None = None
    synthetic: Literal[True]
    honesty: Honesty
