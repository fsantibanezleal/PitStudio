"""Per-frame frame-state files of `st55_sdg` (FR-009-44, FR-009-45).

The Isaac stage reads a frame's stage data (transforms in stage units) and calls `write_frame_state`; this module
converts them to metres with the stage's own `metersPerUnit`, adds the SHA-256 of the frame's files and writes one
document
valid against `contracts/frame-state.schema.json` (DC-015-01, owned by spec 015-vlm; not redefined here). Stage data
that
cannot give a valid frame state is refused with a coded `FrameStateError`: the frame writes nothing, stays out of the
dataset index and is counted by `process_frames`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio_studio.sdg._schemas import schema_errors

_SCHEMA = "frame-state"
_CLASSES = frozenset({"haul_truck", "shovel", "light_vehicle", "person", "boulder"})
_FRAME_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")


class FrameStateError(ValueError):
    """Stage data cannot give a valid frame state: `code` (stage-units-missing, stage-axis-missing, prim-id-duplicate,
    class-unknown, transform-non-finite, file-missing or schema), the frame id when known and the reason."""

    def __init__(self, code: str, frame_id: str | None, reason: str) -> None:
        self.code, self.frame_id, self.reason = code, frame_id, reason
        super().__init__(f"{code}: frame {frame_id or '<unknown>'}: {reason}")


def _is_real(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _finite(values: object) -> bool:
    """True when `values` is a number or a flat sequence of numbers and all of them are finite."""
    if isinstance(values, Mapping | str):
        return False
    items = values if isinstance(values, Sequence) else [values]
    return all(_is_real(v) and math.isfinite(v) for v in items)


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _scaled(values: Sequence[float], mpu: float) -> list[float]:
    return [float(v) * mpu for v in values]


def _check(frame: Mapping[str, Any], root: Path) -> float:
    """Run the refusals in their order; return the stage's metres per unit."""
    fid = frame.get("frame_id") if isinstance(frame.get("frame_id"), str) else None
    stage = frame.get("stage")
    mpu = stage.get("metersPerUnit") if isinstance(stage, Mapping) else None
    if not _is_real(mpu) or not math.isfinite(mpu) or mpu <= 0:  # type: ignore[operator]
        raise FrameStateError("stage-units-missing", fid, f"the stage has no usable metersPerUnit (got {mpu!r})")
    axis = stage.get("upAxis") if isinstance(stage, Mapping) else None
    if axis not in ("Y", "Z"):
        raise FrameStateError("stage-axis-missing", fid, f"the stage has no usable upAxis (got {axis!r})")
    objects = frame.get("objects")
    objects = objects if isinstance(objects, list) else []
    seen: set[str] = set()
    for obj in objects:
        prim = obj.get("prim_id") if isinstance(obj, Mapping) else None
        if isinstance(prim, str):
            if prim in seen:
                raise FrameStateError("prim-id-duplicate", fid, f"two objects share the prim id {prim}")
            seen.add(prim)
    for obj in objects:
        if not isinstance(obj, Mapping):
            continue
        label = obj.get("class")
        if not isinstance(label, str) or label not in _CLASSES:
            raise FrameStateError(
                "class-unknown", fid, f"class {label!r} of prim {obj.get('prim_id')} is not one of {sorted(_CLASSES)}"
            )
    for obj in objects:
        if not isinstance(obj, Mapping):
            continue
        footprint = obj.get("footprint") if isinstance(obj.get("footprint"), Mapping) else {}
        for name, values in (
            ("translation", obj.get("translation")),
            ("rotation_xyzw", obj.get("rotation_xyzw")),
            ("footprint centre", footprint.get("centre")),
            ("footprint half_extents", footprint.get("half_extents")),
            ("footprint heading_deg", footprint.get("heading_deg")),
        ):
            if values is not None and not _finite(values):
                raise FrameStateError("transform-non-finite", fid, f"{name} of prim {obj.get('prim_id')} is not finite")
    camera = frame.get("camera") if isinstance(frame.get("camera"), Mapping) else {}
    for name in ("translation", "rotation_xyzw"):
        if camera.get(name) is not None and not _finite(camera[name]):
            raise FrameStateError("transform-non-finite", fid, f"camera {name} is not finite")
    for key in ("image", "depth", "dust_field", "terrain"):
        ref = frame.get(key)
        if isinstance(ref, Mapping) and isinstance(ref.get("path"), str) and not (root / ref["path"]).is_file():
            raise FrameStateError("file-missing", fid, f"{key} file {ref['path']} does not exist under the root")
    return float(mpu)  # type: ignore[arg-type]


def build_frame_state(frame: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """The DC-015-01 document of one frame: units converted to metres, file digests added; `FrameStateError` if not."""
    root = Path(root)
    mpu = _check(frame, root)
    fid = frame["frame_id"] if isinstance(frame.get("frame_id"), str) else None
    try:
        camera = frame["camera"]
        doc: dict[str, Any] = {
            "schema_version": "1.0",
            "frame_id": frame["frame_id"],
            "run_id": frame["run_id"],
            "synthetic": True,
            "case": frame["case"],
            "location": frame["location"],
            "condition": frame["condition"],
            "metersPerUnit": mpu,
            "upAxis": frame["stage"]["upAxis"],
            "image": {**frame["image"], "sha256": _digest(root / frame["image"]["path"])},
            "depth": {"path": frame["depth"]["path"], "sha256": _digest(root / frame["depth"]["path"])},
            "dust_field": None,
            "terrain": {"path": frame["terrain"]["path"], "sha256": _digest(root / frame["terrain"]["path"])},
            "camera": {
                "intrinsics": dict(camera["intrinsics"]),
                "pose": {
                    "translation_m": _scaled(camera["translation"], mpu),
                    "rotation_xyzw": list(camera["rotation_xyzw"]),
                },
            },
            "objects": [],
            "bench_edges": [dict(e) for e in frame["bench_edges"]],
        }
        if frame.get("dust_field") is not None:
            doc["dust_field"] = {
                "path": frame["dust_field"]["path"],
                "sha256": _digest(root / frame["dust_field"]["path"]),
            }
        for obj in frame["objects"]:
            fp = obj["footprint"]
            out_obj: dict[str, Any] = {
                "prim_id": obj["prim_id"],
                "class": obj["class"],
                "pose": {
                    "translation_m": _scaled(obj["translation"], mpu),
                    "rotation_xyzw": list(obj["rotation_xyzw"]),
                },
                "footprint": {
                    "centre_m": _scaled(fp["centre"], mpu),
                    "half_extents_m": _scaled(fp["half_extents"], mpu),
                    "heading_deg": fp["heading_deg"],
                },
                "visible_px": obj["visible_px"],
                "in_frustum": obj["in_frustum"],
            }
            if obj.get("asset_id") is not None:
                out_obj["asset_id"] = obj["asset_id"]
            doc["objects"].append(out_obj)
    except (KeyError, TypeError, AttributeError) as exc:
        raise FrameStateError(
            "schema", fid, f"the frame is incomplete or malformed ({type(exc).__name__}: {exc})"
        ) from None
    errors = schema_errors(_SCHEMA, doc)
    if errors:
        pointer, message = errors[0]
        raise FrameStateError("schema", fid, f"{pointer or '<root>'}: {message}")
    return doc


def write_frame_state(frame: Mapping[str, Any], root: Path, out_relpath: str) -> dict[str, Any]:
    """Write the frame's document to `root / out_relpath`; return the `frame_state` entry of its dataset-index record.

    Nothing is written, and no folder is made, when `build_frame_state` raises.
    """
    doc = build_frame_state(frame, root)
    data = (json.dumps(doc, indent=2, allow_nan=False) + "\n").encode("utf-8")
    target = Path(root) / out_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return {"path": out_relpath, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


@dataclass(frozen=True)
class Exclusion:
    """A frame kept out of the dataset index: its id (None when unusable), the error code and the reason."""

    frame_id: str | None
    code: str
    reason: str


@dataclass(frozen=True)
class FrameStateReport:
    """The written frames (input order), the exclusions and their counts (`written`, `excluded`, `by_code`)."""

    written: tuple[dict[str, Any], ...]
    excluded: tuple[Exclusion, ...]
    counts: dict[str, Any]


def process_frames(frames: Sequence[Mapping[str, Any]], root: Path, *, out_dir: str) -> FrameStateReport:
    """Write the frame state of every frame; a refused frame is excluded and counted, never raised."""
    written: list[dict[str, Any]] = []
    excluded: list[Exclusion] = []
    for frame in frames:
        fid = frame.get("frame_id") if isinstance(frame, Mapping) else None
        if not isinstance(fid, str) or not _FRAME_ID.match(fid):
            excluded.append(Exclusion(None, "schema", "the frame is not a mapping with a usable frame_id"))
            continue
        try:
            entry = write_frame_state(frame, root, f"{out_dir}/{fid}.json")
        except FrameStateError as exc:
            excluded.append(Exclusion(fid, exc.code, exc.reason))
            continue
        written.append({"frame_id": fid, "frame_state": entry})
    by_code: dict[str, int] = {}
    for e in excluded:
        by_code[e.code] = by_code.get(e.code, 0) + 1
    return FrameStateReport(
        tuple(written), tuple(excluded), {"written": len(written), "excluded": len(excluded), "by_code": by_code}
    )
