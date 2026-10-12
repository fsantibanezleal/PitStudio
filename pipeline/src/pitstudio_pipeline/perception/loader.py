"""Dataset-index and COCO loaders of the perception pipeline: validate, reject, never coerce (FR-009-14 ... FR-009-15,
FR-009-42, FR-009-46, FR-009-47, FR-009-48).

`validate_index_record` / `read_index` check DC-009-01 records, `load_coco` checks a DC-009-02 COCO file and rejects the
whole file for the first problem, `check_frame` / `filter_frames` check handed-off frames file by file. Every rejection
names the record and the reason; a rejected record or file is never repaired.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pitstudio.contracts.io import pointer_of

from pitstudio_pipeline._contracts import best_error

_INDEX_SCHEMA = "perception-dataset.schema.json"
_COCO_SCHEMA = "coco-instances.schema.json"
_MARGIN_PX = 0.5  # a box may extend this far beyond its image (FR-009-15)
_AREA_TOLERANCE_PX2 = 1.0  # stored area against the polygon area (FR-009-47)
_DEVICE_NAMES = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))})
_DRIVE = re.compile(r"^[A-Za-z]:")
CLASS_VALUES = frozenset(range(6))


# ----------------------------------------------------------------------------------------------------------------
# dataset-index records (DC-009-01)
# ----------------------------------------------------------------------------------------------------------------
class IndexRecordError(ValueError):
    """A dataset-index record is invalid: `line` (1-based, 0 for a record not read from a file), id, pointer, reason."""

    def __init__(self, line: int, record_id: str | None, pointer: str, reason: str) -> None:
        self.line, self.record_id, self.pointer, self.reason = line, record_id, pointer, reason
        where = f"line {line}: " if line else ""
        super().__init__(f"{where}record {record_id or '<unknown>'} at {pointer or '<root>'}: {reason}")


class DatasetIndexError(ValueError):
    """The whole index is rejected: a `record_id` occurs more than once (`index-duplicate-record`)."""

    code = "index-duplicate-record"

    def __init__(self, record_id: str, lines: Sequence[int] = ()) -> None:
        self.record_id = record_id
        self.lines = tuple(lines)
        where = f" on lines {', '.join(str(n) for n in self.lines)}" if self.lines else ""
        super().__init__(f"{self.code}: record_id {record_id!r} occurs more than once{where}")


@dataclass(frozen=True)
class IndexReadResult:
    """The valid records of an index file (file order, unchanged) and the rejected lines."""

    records: tuple[dict[str, Any], ...]
    rejected: tuple[IndexRecordError, ...]


def _record_id(record: object) -> str | None:
    rid = record.get("record_id") if isinstance(record, Mapping) else None
    return rid if isinstance(rid, str) else None


def validate_index_record(record: object, *, _line: int = 0) -> None:
    """Raise `IndexRecordError` for the first schema error of `record` against DC-009-01."""
    first = best_error(_INDEX_SCHEMA, record)
    if first is not None:
        raise IndexRecordError(_line, _record_id(record), first[0], first[1])


def check_unique_record_ids(records: Sequence[object]) -> None:
    """Raise `DatasetIndexError` naming the first id (in index order) that occurs more than once."""
    seen: set[str] = set()
    for record in records:
        rid = _record_id(record)
        if rid is None:
            continue
        if rid in seen:
            raise DatasetIndexError(rid)
        seen.add(rid)


def read_index(path: Path) -> IndexReadResult:
    """Read a JSON Lines index; bad lines are rejected one by one, a repeated `record_id` rejects the whole index."""
    raw = Path(path).read_bytes()  # FileNotFoundError for a missing file
    records: list[dict[str, Any]] = []
    rejected: list[IndexRecordError] = []
    ids: dict[str, list[int]] = {}
    first_repeat: str | None = None
    for number, line in enumerate(raw.split(b"\n"), start=1):
        if not line.strip():
            continue
        try:
            doc = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            rejected.append(IndexRecordError(number, None, "", "the line is not UTF-8 JSON"))
            continue
        rid = _record_id(doc)
        if rid is not None:
            ids.setdefault(rid, []).append(number)
            if len(ids[rid]) == 2 and first_repeat is None:
                first_repeat = rid
        try:
            validate_index_record(doc, _line=number)
        except IndexRecordError as exc:
            rejected.append(exc)
            continue
        records.append(doc)
    if first_repeat is not None:
        raise DatasetIndexError(first_repeat, ids[first_repeat])
    return IndexReadResult(tuple(records), tuple(rejected))


# ----------------------------------------------------------------------------------------------------------------
# COCO files (DC-009-02)
# ----------------------------------------------------------------------------------------------------------------
class CocoError(ValueError):
    """A COCO file is rejected whole: `record_id` ("image:<id>", "annotation:<id>", "category:<id>", "file"), pointer,
    reason, error `code`, and `entries` (the file names of a `coco-path-invalid` error, else empty)."""

    def __init__(
        self,
        record_id: str,
        pointer: str,
        reason: str,
        *,
        code: str = "coco-schema",
        entries: Sequence[str] = (),
    ) -> None:
        self.record_id, self.pointer, self.reason, self.code = record_id, pointer, reason, code
        self.entries = tuple(entries)
        shown = f" [{', '.join(self.entries)}]" if self.entries else ""
        super().__init__(f"{code}: {record_id} at {pointer or '<root>'}: {reason}{shown}")


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _item_id(doc: Mapping[str, Any], kind: str, index: int) -> str:
    items = doc.get(kind)
    if isinstance(items, list) and index < len(items) and isinstance(items[index], Mapping):
        ident = items[index].get("id")
        if isinstance(ident, int) and not isinstance(ident, bool):
            return f"{kind.rstrip('s') if kind != 'categories' else 'category'}:{ident}"
    label = {"images": "image", "annotations": "annotation", "categories": "category"}[kind]
    return f"{label}:index-{index}"


def _owner(doc: Any, parts: list[Any]) -> str:
    """Record id of the COCO item that holds the JSON path `parts` ("file" outside images, annotations, categories)."""
    if len(parts) >= 2 and parts[0] in ("images", "annotations", "categories") and isinstance(parts[1], int):
        return _item_id(doc, parts[0], parts[1]) if isinstance(doc, Mapping) else "file"
    return "file"


def _non_finite(node: Any, path: list[Any]) -> list[Any] | None:
    if isinstance(node, float) and not math.isfinite(node):
        return path
    if isinstance(node, dict):
        for key, value in node.items():
            found = _non_finite(value, [*path, key])
            if found is not None:
                return found
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found = _non_finite(value, [*path, i])
            if found is not None:
                return found
    return None


def _parse_pointer(pointer: str) -> list[Any]:
    parts: list[Any] = []
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        parts.append(int(token) if token.isdigit() else token)
    return parts


def _polygon_problem(segmentation: object, width: int, height: int) -> str | None:
    """First problem of the polygon rings of an annotation (parity, vertex count, numbers, bounds), else `None`."""
    if not isinstance(segmentation, list) or not segmentation:
        return "segmentation must hold at least one polygon ring (vertices)"
    for r, ring in enumerate(segmentation):
        if not isinstance(ring, list):
            return f"ring {r} is not a list of coordinates (vertices)"
        if len(ring) % 2 == 1:
            return f"ring {r} has an odd number of coordinates ({len(ring)})"
        if len(ring) < 6:
            return f"ring {r} has fewer than 3 vertices ({len(ring) // 2})"
        for i, value in enumerate(ring):
            if not _is_number(value) or not math.isfinite(value):
                return f"ring {r} coordinate {i} is not a finite number"
        for i in range(0, len(ring), 2):
            x, y = ring[i], ring[i + 1]
            if not (0.0 <= x <= width and 0.0 <= y <= height):
                return f"ring {r} vertex {i // 2} ({x}, {y}) is outside the {width} x {height} px image"
    return None


def _ring_area(ring: Sequence[float]) -> float:
    xs, ys = ring[0::2], ring[1::2]
    twice = sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs)))
    return abs(twice) / 2.0


def _unsafe_file_name(name: str) -> bool:
    return name.startswith(("/", "\\")) or "\\" in name or bool(_DRIVE.match(name)) or ".." in name.split("/")


def _device_segment(name: str) -> bool:
    return any(seg.split(".", 1)[0].casefold() in _DEVICE_NAMES for seg in name.split("/"))


def load_coco(path: Path) -> dict[str, Any]:
    """Read a DC-009-02 COCO file; reject the WHOLE file (raise `CocoError`) for the first problem, else return it."""
    raw = Path(path).read_bytes()  # FileNotFoundError for a missing file
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CocoError("file", "", "the file is not UTF-8", code="coco-file-invalid") from None
    if not text.strip():
        raise CocoError("file", "", "the file is empty", code="coco-file-invalid")
    try:
        doc = json.loads(text, parse_constant=float)  # NaN / Infinity tokens become floats and are caught below
    except (ValueError, RecursionError):
        raise CocoError("file", "", "the file is not valid JSON", code="coco-file-invalid") from None
    bad = _non_finite(doc, [])
    if bad is not None:
        raise CocoError(_owner(doc, bad), pointer_of(bad), "non-finite number", code="coco-non-finite")
    first = best_error(_COCO_SCHEMA, doc)
    if first is not None:
        pointer, message = first
        parts = _parse_pointer(pointer)
        owner = _owner(doc, parts)
        if len(parts) >= 3 and parts[0] == "annotations" and parts[2] in ("segmentation", "area"):
            ann = doc["annotations"][parts[1]]
            problem = None
            image = next((i for i in doc.get("images", []) if isinstance(i, Mapping) and i.get("id") == ann.get("image_id")), None)
            if parts[2] == "segmentation" and isinstance(image, Mapping):
                problem = _polygon_problem(ann.get("segmentation"), image.get("width", 0), image.get("height", 0))
            raise CocoError(owner, pointer, problem or f"schema: {message}", code="coco-polygon-invalid")
        raise CocoError(owner, pointer, f"schema: {pointer or '<root>'}: {message}", code="coco-schema")
    _semantic_checks(doc)
    return doc  # type: ignore[no-any-return]


def _semantic_checks(doc: dict[str, Any]) -> None:
    images: dict[int, dict[str, Any]] = {}
    for n, image in enumerate(doc["images"]):
        if image["id"] in images:
            raise CocoError(f"image:{image['id']}", f"/images/{n}/id", f"duplicate image id {image['id']}", code="coco-id-duplicate")
        images[image["id"]] = image
    seen_annotations: set[int] = set()
    for n, ann in enumerate(doc["annotations"]):
        owner = f"annotation:{ann['id']}"
        if ann["id"] in seen_annotations:
            raise CocoError(owner, f"/annotations/{n}/id", f"duplicate annotation id {ann['id']}", code="coco-id-duplicate")
        seen_annotations.add(ann["id"])
    for n, ann in enumerate(doc["annotations"]):
        owner = f"annotation:{ann['id']}"
        image = images.get(ann["image_id"])
        if image is None:
            raise CocoError(owner, f"/annotations/{n}/image_id", f"annotation points to a missing image {ann['image_id']}", code="coco-image-missing")
        x, y, w, h = ann["bbox"]
        if w <= 0 or h <= 0:
            raise CocoError(owner, f"/annotations/{n}/bbox", f"box size must be positive, got {w} x {h}", code="coco-box-invalid")
        if x < -_MARGIN_PX or y < -_MARGIN_PX or x + w > image["width"] + _MARGIN_PX or y + h > image["height"] + _MARGIN_PX:
            raise CocoError(
                owner,
                f"/annotations/{n}/bbox",
                f"box [{x}, {y}, {w}, {h}] extends beyond image {image['id']} ({image['width']} x {image['height']}) by more than {_MARGIN_PX} px",
                code="coco-box-invalid",
            )
        problem = _polygon_problem(ann["segmentation"], image["width"], image["height"])
        if problem is not None:
            raise CocoError(owner, f"/annotations/{n}/segmentation", problem, code="coco-polygon-invalid")
        polygon_area = sum(_ring_area(ring) for ring in ann["segmentation"])
        if abs(ann["area"] - polygon_area) > _AREA_TOLERANCE_PX2:
            raise CocoError(
                owner,
                f"/annotations/{n}/area",
                f"area {ann['area']} differs from the polygon area {polygon_area} by more than {_AREA_TOLERANCE_PX2} px2",
                code="coco-polygon-invalid",
            )
    folded: dict[str, str] = {}
    for n, image in enumerate(doc["images"]):
        name = image["file_name"]
        owner = f"image:{image['id']}"
        if _device_segment(name):
            raise CocoError(owner, f"/images/{n}/file_name", f"file_name {name!r} has a Windows device name", code="coco-path-invalid", entries=(name,))
        key = name.casefold()
        if key in folded:
            raise CocoError(
                owner,
                f"/images/{n}/file_name",
                f"file_name {name!r} equals {folded[key]!r} after case folding",
                code="coco-path-invalid",
                entries=(folded[key], name),
            )
        folded[key] = name


# ----------------------------------------------------------------------------------------------------------------
# handed-off frames (FR-009-42)
# ----------------------------------------------------------------------------------------------------------------
class FrameRejected(ValueError):
    """A frame is kept out of every split: `code` is path-unsafe, schema, file-missing, sha256-mismatch, mask-size or
    class-value."""

    def __init__(self, record_id: str, code: str, reason: str) -> None:
        self.record_id, self.code, self.reason = record_id, code, reason
        super().__init__(f"frame {record_id} rejected ({code}): {reason}")


@dataclass(frozen=True)
class FrameFilterResult:
    """The frames that passed `check_frame` (input order) and the rejections."""

    accepted: tuple[Mapping[str, Any], ...]
    rejected: tuple[FrameRejected, ...]


def _file_refs(record: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    """Every object of the record with a "path" key, labelled by the record key that holds it."""
    refs: list[tuple[str, Mapping[str, Any]]] = []

    def walk(node: Any, label: str) -> None:
        if isinstance(node, Mapping):
            if "path" in node:
                refs.append((label, node))
            for key, value in node.items():
                walk(value, label if label else str(key))
        elif isinstance(node, list):
            for value in node:
                walk(value, label)

    for key, value in record.items():
        walk(value, str(key))
    return refs


def _png_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as img:
        return img.size


def check_frame(record: Mapping[str, Any], root: Path) -> None:
    """Check one handed-off frame whose files live under `root`; raise `FrameRejected` for the first failure."""
    rid = _record_id(record) or "<unknown>"
    refs = _file_refs(record)
    for label, ref in refs:
        p = ref["path"]
        if not isinstance(p, str) or p == "" or _unsafe_file_name(p):
            raise FrameRejected(rid, "path-unsafe", f"{label} path {p!r} is absolute, has '..', a drive letter or a backslash")
    first = best_error(_INDEX_SCHEMA, record)
    if first is not None:
        pointer, message = first
        raise FrameRejected(rid, "schema", f"{pointer or '<root>'}: {message}")
    base = Path(root)
    for label, ref in refs:
        if not (base / ref["path"]).is_file():
            raise FrameRejected(rid, "file-missing", f"{label} file {ref['path']} does not exist")
    for label, ref in refs:
        digest = ref.get("sha256")
        if digest is not None and hashlib.sha256((base / ref["path"]).read_bytes()).hexdigest() != digest:
            raise FrameRejected(rid, "sha256-mismatch", f"{label} file {ref['path']} differs from the SHA-256 in the record")
    image = record.get("image")
    if isinstance(image, Mapping):
        size = _png_size(base / image["path"])
        for label in ("semantic_mask", "instance_mask"):
            mask = record.get(label)
            if isinstance(mask, Mapping) and _png_size(base / mask["path"]) != size:
                raise FrameRejected(rid, "mask-size", f"{label} size differs from the {size[0]} x {size[1]} px image")
    semantic = record.get("semantic_mask")
    if isinstance(semantic, Mapping):
        from PIL import Image

        with Image.open(base / semantic["path"]) as img:
            values = {int(v) for v in np.unique(np.asarray(img))}
        outside = sorted(values - CLASS_VALUES)
        if outside:
            raise FrameRejected(rid, "class-value", f"semantic mask holds values outside 0..5: {outside}")


def filter_frames(records: Sequence[Mapping[str, Any]], root: Path) -> FrameFilterResult:
    """`check_frame` on each record; rejected frames stay out of `accepted` (so out of every split)."""
    accepted: list[Mapping[str, Any]] = []
    rejected: list[FrameRejected] = []
    for record in records:
        try:
            check_frame(record, root)
        except FrameRejected as exc:
            rejected.append(exc)
        else:
            accepted.append(record)
    return FrameFilterResult(tuple(accepted), tuple(rejected))
