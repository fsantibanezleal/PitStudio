# SPDX-License-Identifier: Apache-2.0
"""The sensor stage runner (`st53_sensors`, `st57_rain_lidar`): recipe and envelope guards, frame loop, shards.

All guards live here, not in a backend, so every backend (ovrtx, isaac, fake) gets the same ones:

- recipe validation against `contracts/sensor-recipe.schema.json` plus the checker rules (FR-013-04, exit 2);
- the lidar-envelope guard (FR-013-05, exit 2) and the rain / fixture refusals (FR-013-30, FR-013-43, exit 2);
- warm-up frames rendered and discarded (FR-013-07), the point-count guard (FR-013-08, exit 1 `lidar-zero-points`)
  and output validation (FR-013-09, exit 1 `backend-output-invalid`);
- shards written by `shards.ShardWriter` into a work folder that is promoted to `out_dir` only on success (nothing is
  left behind on failure) and the manifest marker fields `performance: local-only` (FR-013-32).

Exit codes of `StageOutcome`: 0 success or "not run", 1 runtime failure, 2 refusal before rendering.
"""

from __future__ import annotations

import copy
import functools
import json
import math
import os
import shutil
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_rtx.backend import RuntimeIsolationError, SensorBackend, create_backend
from pitstudio_rtx.shards import ShardWriter, image_record

STAGES = ("st53_sensors", "st57_rain_lidar")
STAGE_SCENARIOS = {"st53_sensors": ("S1", "S2", "S3", "S4a"), "st57_rain_lidar": ("rain",)}
REPLACEMENT = "measured locally, not published (licence)"
DEFAULT_RAIN_RATES = (0, 2, 10, 50)
RAIN_ONLY_ISAAC = "rain is available only on the isaac backend"
VALID_BIT = 0x40
_CONTRACTS = Path(__file__).resolve().parents[4] / "contracts"
_RECIPE_ID = "https://fsantibanezleal.github.io/PitStudio/contracts/sensor-recipe.schema.json"
_LIDAR_FIELDS = {
    "x": np.float32,
    "y": np.float32,
    "z": np.float32,
    "range_m": np.float32,
    "intensity": np.float32,
    "flags": np.uint8,
    "material_class": np.uint8,
    "object_id": np.uint32,
    "beam": np.uint32,
    "echo": np.uint8,
}
_FINITE_LIDAR = ("x", "y", "z", "range_m", "intensity")
_RADAR_FIELDS = {
    "x": np.float32,
    "y": np.float32,
    "z": np.float32,
    "rcs_dbsm": np.float32,
    "radial_velocity_native": np.float32,
    "object_id": np.uint32,
}
_CAMERA_VARS = {
    "HdrColor": ("hdr", np.float16, True),
    "DistanceToCameraSD": ("distance", np.float32, False),
    "DistanceToImagePlaneSD": ("distance", np.float32, False),
    "SemanticSegmentation": ("semantic", np.uint32, False),
    "LdrColor": ("ldr", np.uint8, True),
}
_OPTICAL_FROM_PLATFORM = np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])


class RecipeError(ValueError):
    """A recipe violation: `pointer` is the RFC 6901 JSON pointer of the first offending value."""

    def __init__(self, pointer: str, message: str) -> None:
        super().__init__(f"{pointer or '/'}: {message}")
        self.pointer, self.message = pointer, message


class EnvelopeError(ValueError):
    """A lidar configuration the probe did not validate: `sensor` is its id, `configuration` its key."""

    def __init__(self, sensor: str, configuration: dict[str, Any], message: str) -> None:
        super().__init__(message)
        self.sensor, self.configuration = sensor, configuration


@dataclass
class StageOutcome:
    """Result of `run_stage`; see the module docstring for the exit codes."""

    status: str
    exit_code: int
    error_class: str | None = None
    message: str = ""
    pointer: str | None = None
    reason: str | None = None
    index: dict[str, Any] | None = None
    outputs: list[str] = field(default_factory=list)
    manifest_fields: dict[str, Any] = field(default_factory=dict)
    publishable: bool = False


class _Failure(Exception):
    def __init__(self, error_class: str, message: str) -> None:
        super().__init__(message)
        self.error_class, self.message = error_class, message


class _NotRun(Exception):
    pass


# -------------------------------------------------------------------------------------------------- recipe validation
@functools.lru_cache(maxsize=1)
def _registry() -> Any:
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    for path in sorted(_CONTRACTS.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resources.append((doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012)))
    return Registry().with_resources(resources)


def _validator(name: str) -> Any:
    import jsonschema

    schema = json.loads((_CONTRACTS / name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, registry=_registry())


def _def_validator(def_name: str) -> Any:
    import jsonschema

    return jsonschema.Draft202012Validator({"$ref": f"{_RECIPE_ID}#/$defs/{def_name}"}, registry=_registry())


def _pointer(path: Iterable[Any]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in path)


def _non_finite(node: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    if isinstance(node, float) and not math.isfinite(node):
        yield path
    elif isinstance(node, Mapping):
        for key, value in node.items():
            yield from _non_finite(value, (*path, key))
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _non_finite(value, (*path, i))


def _order(path: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple((0, p, "") if isinstance(p, int) else (1, 0, str(p)) for p in path)


def _schema_violations(params: Mapping[str, Any]) -> list[tuple[tuple[Any, ...], str]]:
    """Schema violations as (path, message); a failed `oneOf` is re-checked against the sensor's kind."""
    found: list[tuple[tuple[Any, ...], str]] = []
    for error in _validator("sensor-recipe.schema.json").iter_errors(params):
        path = tuple(error.absolute_path)
        if error.validator == "oneOf" and len(path) == 2 and path[0] == "sensors":
            sensor = params["sensors"][path[1]]
            kind = sensor.get("kind") if isinstance(sensor, Mapping) else None
            if kind in ("lidar", "camera", "radar"):
                found += [(path + tuple(e.absolute_path), e.message) for e in _def_validator(kind).iter_errors(sensor)]
            else:
                found.append(((*path, "kind"), f"unknown sensor kind {kind!r}"))
        else:
            found.append((path, error.message))
    return found


def validate_recipe(stage: str, params: Mapping[str, Any], declared_inputs: Iterable[str]) -> None:
    """Return None when the recipe block is valid for `stage`, else raise `RecipeError` at the first fault."""
    if stage not in STAGES:
        raise ValueError(f"unknown sensor stage {stage!r}")
    for path in _non_finite(params):
        raise RecipeError(_pointer(path), "a number is not finite")
    faults = _schema_violations(params)
    if faults:
        path, message = min(faults, key=lambda f: _order(f[0]))
        pointer = _pointer(path)
        if pointer.startswith("/rain_rates_mm_h") and params.get("backend") != "isaac":
            message = f"{RAIN_ONLY_ISAAC} ({message})"
        raise RecipeError(pointer, message)
    if params["scenario"] not in STAGE_SCENARIOS[stage]:
        raise RecipeError("/scenario", f"scenario {params['scenario']!r} does not belong to stage {stage}")
    ids: set[str] = set()
    for i, sensor in enumerate(params["sensors"]):
        base = f"/sensors/{i}"
        if sensor["id"] in ids:
            raise RecipeError(f"{base}/id", f"duplicate sensor id {sensor['id']!r}")
        ids.add(sensor["id"])
        if sensor["kind"] == "lidar":
            for key in ("elevation_fan_deg", "azimuth_fan_deg"):
                if not sensor[key][0] < sensor[key][1]:
                    raise RecipeError(f"{base}/{key}", f"{key} must satisfy minimum < maximum, got {sensor[key]}")
            if not sensor["min_range_m"] < sensor["max_range_m"]:
                raise RecipeError(f"{base}/max_range_m", "min_range_m must be less than max_range_m")
    declared = set(declared_inputs)
    wanted = [("/poses", params["poses"])]
    wanted += [
        (f"/dust/extinction_fields/{i}", f)
        for i, f in enumerate((params.get("dust") or {}).get("extinction_fields", []))
    ]
    if (params.get("haze") or {}).get("extinction_field") is not None:
        wanted.append(("/haze/extinction_field", params["haze"]["extinction_field"]))
    for pointer, relpath in wanted:
        if relpath not in declared:
            raise RecipeError(pointer, f"{relpath!r} is not a declared stage input")


# ------------------------------------------------------------------------------------------------ envelope guard
def _configuration(sensor: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("scan_type", "elevation_fan_deg", "azimuth_fan_deg", "mount_rotation_deg")
    return {k: sensor[k] for k in keys}


def check_envelope(params: Mapping[str, Any], envelope: Mapping[str, Any], versions: Mapping[str, str]) -> None:
    """Raise `EnvelopeError` unless every lidar configuration of the recipe is listed as `pass` for these versions."""
    lidars = [s for s in params["sensors"] if s["kind"] == "lidar"]
    for sensor in lidars:
        config = _configuration(sensor)
        recorded = envelope.get("versions", {})
        for key in ("ovrtx", "ovstage"):
            if recorded.get(key) != versions.get(key):
                raise EnvelopeError(
                    sensor["id"],
                    config,
                    f"sensor {sensor['id']}: the lidar envelope was probed with {key} {recorded.get(key)!r}, "
                    f"but the backend runs {versions.get(key)!r}; run the probe again",
                )
        matches = [c for c in envelope.get("configurations", []) if all(c.get(k) == v for k, v in config.items())]
        if not matches or any(c.get("status") != "pass" for c in matches):
            raise EnvelopeError(
                sensor["id"],
                config,
                f"sensor {sensor['id']}: lidar configuration not validated by the probe "
                f"(scan_type={config['scan_type']}, elevation_fan_deg={config['elevation_fan_deg']}, "
                f"azimuth_fan_deg={config['azimuth_fan_deg']}, mount_rotation_deg={config['mount_rotation_deg']})",
            )


def _read_envelope(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        raise _Failure("envelope-invalid", "the recipe holds a lidar but no lidar envelope was given")
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _Failure("envelope-invalid", f"the lidar envelope {Path(path).name} is unreadable: {exc}") from exc
    errors = sorted(e.message for e in _validator("lidar-envelope.schema.json").iter_errors(doc))
    if errors:
        raise _Failure("envelope-invalid", f"the lidar envelope is invalid: {errors[0]}")
    return doc


# ---------------------------------------------------------------------------------------------------- manifest markers
def manifest_fields(stage: str) -> dict[str, Any]:
    """The run-manifest fields of a sensor stage: `performance: local-only`, outputs own CC-BY-4.0."""
    if stage not in STAGES:
        raise ValueError(f"not a sensor stage: {stage!r}")
    return {
        "performance": "local-only",
        "artefact": {"licence_class": "own", "spdx": "CC-BY-4.0"},
        "runtime_licence_class": "reference-only",
    }


def scrub_performance(entry: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of a run-manifest stage entry without performance values; telemetry replaced."""
    out = copy.deepcopy(dict(entry))
    out.pop("wall_s", None)
    out.pop("throughput", None)
    out["telemetry"] = REPLACEMENT
    if "attempts" in out:
        out["attempts"] = [{k: v for k, v in a.items() if k != "duration_s"} for a in out["attempts"]]
    return out


def check_published_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Violations of a published run manifest: performance data or a wrong licence."""
    problems: list[str] = []
    for stage in manifest.get("stages", []):
        stage_id = (stage.get("key") or {}).get("id")
        if stage_id not in STAGES:
            continue
        if stage.get("performance") != "local-only":
            problems.append(f"{stage_id}: performance is {stage.get('performance')!r}, expected 'local-only'")
        problems += [f"{stage_id}: {key} must not be published" for key in ("wall_s", "throughput") if key in stage]
        if "telemetry" in stage and stage["telemetry"] != REPLACEMENT:
            problems.append(f"{stage_id}: telemetry must read {REPLACEMENT!r}")
        problems += [
            f"{stage_id}: attempt {a.get('n')} holds duration_s" for a in stage.get("attempts", []) if "duration_s" in a
        ]
    for art in manifest.get("artefacts", []):
        if ((art.get("producer") or {}).get("stage") or {}).get("id") in STAGES and (
            art.get("licence_class") != "own" or art.get("spdx") != "CC-BY-4.0"
        ):
            problems.append(
                f"artefact {art.get('id')}: licence_class {art.get('licence_class')!r} / spdx {art.get('spdx')!r}, "
                "expected 'own' / 'CC-BY-4.0'"
            )
    return problems


def check_published_manifests(runs_dir: str | Path) -> dict[str, list[str]]:
    """The violations of every `<runs_dir>/*/manifest.json`; an empty dict when none exists or all are clean."""
    found: dict[str, list[str]] = {}
    for path in sorted(Path(runs_dir).glob("*/manifest.json")):
        problems = check_published_manifest(json.loads(path.read_text(encoding="utf-8")))
        if problems:
            found[path.parent.name] = problems
    return found


# ----------------------------------------------------------------------------------------------------- frame outputs
def _array(out: Mapping[str, Any], name: str, dtype: Any, where: str) -> np.ndarray:
    if name not in out:
        raise _Failure("backend-output-invalid", f"{where}: field {name} is missing")
    arr = out[name]
    if not isinstance(arr, np.ndarray) or arr.dtype != np.dtype(dtype):
        got = arr.dtype if isinstance(arr, np.ndarray) else type(arr).__name__
        raise _Failure("backend-output-invalid", f"{where}: field {name} must be a {np.dtype(dtype)} array, got {got}")
    return arr


def _check_lidar(out: Mapping[str, Any], where: str) -> np.ndarray:
    """Validate one lidar frame (FR-013-09); return the boolean mask of the valid entries."""
    arrays = {name: _array(out, name, dtype, where) for name, dtype in _LIDAR_FIELDS.items()}
    for name, arr in arrays.items():
        if arr.ndim != 1:
            raise _Failure("backend-output-invalid", f"{where}: field {name} must be 1-D, got shape {arr.shape}")
        if len(arr) != len(arrays["x"]):
            raise _Failure(
                "backend-output-invalid", f"{where}: field {name} has {len(arr)} entries, x has {len(arrays['x'])}"
            )
    mask = (arrays["flags"] & VALID_BIT) != 0
    n_valid = int(mask.sum())
    count = out.get("valid_count")
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)) or int(count) != n_valid:
        raise _Failure(
            "backend-output-invalid", f"{where}: field valid_count is {count!r}, {n_valid} entries are flagged valid"
        )
    beams = out.get("beams_emitted")
    if isinstance(beams, bool) or not isinstance(beams, (int, np.integer)) or not n_valid <= int(beams) <= 10_000_000:
        raise _Failure(
            "backend-output-invalid", f"{where}: field beams_emitted is {beams!r}, expected at least {n_valid}"
        )
    for name in _FINITE_LIDAR:
        if not np.all(np.isfinite(arrays[name][mask])):
            raise _Failure("backend-output-invalid", f"{where}: field {name} holds a non-finite value on a valid entry")
    if not np.all(np.isin(arrays["material_class"][mask], (0, 1))):
        raise _Failure("backend-output-invalid", f"{where}: field material_class must be 0 or 1")
    return mask


def _lidar_columns(out: Mapping[str, Any], mask: np.ndarray, frame: int) -> dict[str, np.ndarray]:
    pick = {k: np.asarray(out[k])[mask] for k in _LIDAR_FIELDS}
    return {
        "frame": np.full(int(mask.sum()), frame, dtype=np.uint32),
        "beam": pick["beam"],
        "echo": pick["echo"],
        "x_m": pick["x"],
        "y_m": pick["y"],
        "z_m": pick["z"],
        "range_m": pick["range_m"],
        "intensity": pick["intensity"],
        "flags": pick["flags"],
        "material_class": np.where(pick["material_class"] == 1, "retro", "diffuse"),
        "object_id": pick["object_id"],
    }


def _radar_columns(out: Mapping[str, Any], where: str, frame: int) -> dict[str, np.ndarray]:
    arrays = {name: _array(out, name, dtype, where) for name, dtype in _RADAR_FIELDS.items()}
    for name, arr in arrays.items():
        if arr.ndim != 1 or len(arr) != len(arrays["x"]):
            raise _Failure("backend-output-invalid", f"{where}: field {name} must be 1-D and as long as x")
        if arr.dtype.kind == "f" and not np.all(np.isfinite(arr)):
            raise _Failure("backend-output-invalid", f"{where}: field {name} holds a non-finite value")
    sign = out.get("native_sign")
    if sign not in ("approaching-positive", "approaching-negative"):
        raise _Failure("backend-output-invalid", f"{where}: field native_sign is {sign!r}")
    velocity = -arrays["radial_velocity_native"] if sign == "approaching-positive" else arrays["radial_velocity_native"]
    return {
        "frame": np.full(len(arrays["x"]), frame, dtype=np.uint32),
        "x_m": arrays["x"],
        "y_m": arrays["y"],
        "z_m": arrays["z"],
        "rcs_dbsm": arrays["rcs_dbsm"],
        "radial_velocity_m_per_s": velocity,
        "object_id": arrays["object_id"],
    }


def _check_camera(out: Mapping[str, Any], sensor: Mapping[str, Any], where: str) -> dict[str, np.ndarray]:
    h, w = int(sensor["height_px"]), int(sensor["width_px"])
    images: dict[str, np.ndarray] = {}
    for product in sensor["outputs"]:
        name, dtype, colour = _CAMERA_VARS[product]
        arr = _array(out, name, dtype, where)
        want = (h, w, 3) if colour else (h, w)
        if arr.shape != want:
            raise _Failure("backend-output-invalid", f"{where}: field {name} has shape {arr.shape}, expected {want}")
        if name == "hdr" and not np.all(np.isfinite(arr)):
            raise _Failure("backend-output-invalid", f"{where}: field hdr holds a non-finite value")
        images[name] = arr
    return images


# ------------------------------------------------------------------------------------------------------------ poses
def _rotation(deg: Sequence[float]) -> np.ndarray:
    ax, ay, az = (math.radians(v) for v in deg)
    rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]])
    ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    rz = np.array([[math.cos(az), -math.sin(az), 0], [math.sin(az), math.cos(az), 0], [0, 0, 1]])
    return rz @ ry @ rx


def mount_matrix(sensor: Mapping[str, Any]) -> np.ndarray:
    """Platform-from-sensor 4 x 4 (column vectors): rotation about x, y, z (Rz Ry Rx), then the mount translation."""
    mount = np.eye(4)
    mount[:3, :3] = _rotation(sensor["mount_rotation_deg"])
    mount[:3, 3] = sensor["mount_position_m"]
    return mount


def _world_from_camera(platform: Sequence[float], sensor: Mapping[str, Any]) -> list[float]:
    """Platform pose times the mount times the pinhole optical frame (x right, y down, z forward)."""
    optical = np.eye(4)
    optical[:3, :3] = _OPTICAL_FROM_PLATFORM
    pose = np.asarray(platform, dtype=np.float64).reshape(4, 4) @ mount_matrix(sensor) @ optical
    return [float(v) for v in pose.reshape(16)]


def _read_poses(path: str | Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    for name in ("frame", "t_s", "world_from_platform"):
        if name not in table.column_names:
            raise ValueError(f"the pose trace has no column {name}")
    rows = table.to_pydict()
    poses = [
        {"frame": int(f), "t_s": float(t), "world_from_platform": [float(v) for v in m]}
        for f, t, m in zip(rows["frame"], rows["t_s"], rows["world_from_platform"], strict=True)
    ]
    if not poses:
        raise ValueError("the pose trace holds no frame")
    if any(len(p["world_from_platform"]) != 16 or not all(map(math.isfinite, p["world_from_platform"])) for p in poses):
        raise ValueError("the pose trace holds a pose that is not 16 finite numbers")
    return poses


# --------------------------------------------------------------------------------------------------------------- run
def _refusal(message: str, pointer: str | None = None, error_class: str = "refused") -> StageOutcome:
    return StageOutcome(status="failed", exit_code=2, error_class=error_class, message=message, pointer=pointer)


def run_stage(
    stage: str,
    params: Mapping[str, Any],
    *,
    out_dir: str | Path,
    inputs: Mapping[str, str | Path],
    envelope_path: str | Path | None = None,
    backend: SensorBackend | None = None,
    capabilities: Mapping[str, Any] | None = None,
    run_id: str = "20261011T120000Z-test",
    fixture: bool = False,
    seed: int = 0,
) -> StageOutcome:
    """Run one sensor stage; see the module docstring. `seed` is reserved for the post-models (it is not rendered)."""
    del seed
    try:
        # The haze extinction field is read by the post-model, not by the renderer: it is declared by the stage
        # (`inputs` maps what the render itself reads), so the lane does not require it in `inputs`.
        haze = (params.get("haze") or {}).get("extinction_field") if isinstance(params, Mapping) else None
        validate_recipe(stage, params, [*inputs, *([haze] if isinstance(haze, str) else [])])
    except RecipeError as exc:
        return _refusal(exc.args[0], exc.pointer, "params-invalid")
    if fixture and backend is None:
        return _refusal("contract fixtures run on the fake backend only", error_class="fixture-on-real-backend")
    try:
        be = backend if backend is not None else create_backend(params["backend"])
    except RuntimeIsolationError as exc:
        return _refusal(str(exc), error_class="runtime-isolation")
    info = be.describe()
    if fixture and info.name != "fake":
        return _refusal(
            f"fixture inputs run on the fake backend only, not on {info.name!r}", error_class="fixture-on-real-backend"
        )
    if stage == "st57_rain_lidar":
        status = ((capabilities or {}).get("probes", {}).get("isaacsim") or {}).get("status")
        if status != "pass":
            return StageOutcome(
                status="not_run", exit_code=0, reason=f"the isaacsim probe is {status or 'absent'}, not pass"
            )
    try:
        poses = _read_poses(inputs[params["poses"]])
        lidars = [s for s in params["sensors"] if s["kind"] == "lidar"]
        if lidars:
            check_envelope(params, _read_envelope(envelope_path), info.versions)
    except EnvelopeError as exc:
        return _refusal(str(exc), error_class="envelope-untested")
    except _Failure as exc:
        return _refusal(exc.message, error_class=exc.error_class)
    except (OSError, ValueError, KeyError) as exc:
        return _refusal(f"the pose trace is unreadable: {exc}", "/poses", "inputs-invalid")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".sensors-", dir=out_dir.parent))
    try:
        index = _render(stage, params, be, info.name, info.capabilities, poses, inputs, work, run_id, fixture)
        outputs = _promote(work, out_dir)
    except _Failure as exc:
        return StageOutcome(status="failed", exit_code=1, error_class=exc.error_class, message=exc.message)
    except _NotRun as exc:
        return StageOutcome(status="not_run", exit_code=0, reason=str(exc))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return StageOutcome(
        status="succeeded",
        exit_code=0,
        index=index,
        outputs=outputs,
        manifest_fields={**manifest_fields(stage), "publish": not fixture},
        publishable=not fixture,
    )


def _promote(work: Path, out_dir: Path) -> list[str]:
    moved = []
    for path in sorted(p for p in work.rglob("*") if p.is_file()):
        rel = path.relative_to(work)
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, out_dir / rel)
        moved.append(rel.as_posix())
    return moved


def _scene(inputs: Mapping[str, str | Path]) -> str | None:
    return next((str(p) for k, p in inputs.items() if k.lower().endswith((".usd", ".usda", ".usdc", ".usdz"))), None)


def _render(
    stage: str,
    params: Mapping[str, Any],
    be: SensorBackend,
    backend_name: str,
    capabilities: Mapping[str, Any],
    poses: list[dict[str, Any]],
    inputs: Mapping[str, str | Path],
    work: Path,
    run_id: str,
    fixture: bool,
) -> dict[str, Any]:
    writer = ShardWriter(
        work, run_id=run_id, stage=stage, scenario=params["scenario"], backend=backend_name, fixture=fixture
    )
    warmup = int(capabilities.get("warmup_frames", 0))
    rain = stage == "st57_rain_lidar"
    rates: list[float | None] = list(params.get("rain_rates_mm_h", DEFAULT_RAIN_RATES)) if rain else [None]
    frame = 0
    for rate in rates:
        sensors = [dict(s, rain_rate_mm_h=rate) if rain else dict(s) for s in params["sensors"]]
        session = be.open(_scene(inputs), sensors)
        try:
            for _ in range(warmup):
                be.step(session, poses[0])  # rendered and discarded: no guard, no shard
            for pose in poses:
                outputs = be.step(session, pose)
                for sensor in params["sensors"]:
                    _record(writer, sensor, outputs.get(sensor["id"]), frame, rate, pose)
                frame += 1
        finally:
            be.close(session)
    return writer.finish()


def _record(
    writer: ShardWriter, sensor: Mapping[str, Any], out: Any, frame: int, rate: float | None, pose: Mapping[str, Any]
) -> None:
    where = f"sensor {sensor['id']}, frame {frame}"
    if not isinstance(out, Mapping) or out.get("kind") != sensor["kind"]:
        raise _Failure("backend-output-invalid", f"{where}: the backend returned no {sensor['kind']} output")
    if sensor["kind"] == "lidar":
        mask = _check_lidar(out, where)
        if not mask.any():
            raise _Failure("lidar-zero-points", f"{where}: the clean frame holds no valid lidar return")
        applied = out.get("applied_rain_rate_mm_h")
        if rate is not None and (applied is None or float(applied) != float(rate)):
            raise _NotRun(
                f"sensor {sensor['id']}: rain rate {rate} mm/h was requested but the backend applied {applied!r} mm/h"
            )
        writer.add_lidar_frame(
            sensor["id"],
            frame,
            _lidar_columns(out, mask, frame),
            beams_emitted=int(out["beams_emitted"]),
            rain_rate_mm_h=rate,
        )
    elif sensor["kind"] == "radar":
        writer.add_radar_frame(sensor["id"], frame, _radar_columns(out, where, frame))
    else:
        images = _check_camera(out, sensor, where)
        record = image_record(
            sensor, image=frame, file="-", world_from_camera=_world_from_camera(pose["world_from_platform"], sensor)
        )
        for key in ("image", "sensor", "file"):
            del record[key]
        writer.add_image(sensor["id"], frame, images, record)
