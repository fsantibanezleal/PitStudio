"""Task-A query builder (FR-015-16, DC-015-02): balanced, seeded, one query per (frame, question type).

The builder validates every frame state through `load_frame_state`, keeps the frames of the B2 scenes, asks the ground
truth for every (frame, type) and draws the quota of each type: equal counts per answer class, spread as evenly as the
pool allows over the four conditions. At full size (1,080 per type) it also flags the 500-query agreement-gate subset
(FR-015-14) and the 300-query reasoning-on subset (FR-015-24). A pool that cannot supply a quota is not an error: the
builder returns what it can, still balanced across classes, and reports the shortfall per type.
"""

from __future__ import annotations

import hashlib
import io
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.reason import truth as truth_mod
from pitstudio.reason.frames import canonical_sha256, load_frame_state

CASE = "B2"
SCHEMA_VERSION = "1.0"
FULL_PER_TYPE = 1080
GATE_PER_TYPE = 100
REASONING_PER_TYPE = 50
BINARY_TYPES = (1, 2, 4, 5, 6)
QUESTION_TYPES = (1, 2, 3, 4, 5, 6)
CONDITIONS = ("day", "night", "dust", "rain")
CLASSES = {3: ("0", "1", "2", "3+")}
BINARY_CLASSES = ("yes", "no")
MAX_ID = 96
NO_RUN_ID = "00000000T000000Z-none"

TruthFn = Callable[[Mapping[str, Any], int], str | None]


def classes_of(qtype: int) -> tuple[str, ...]:
    return CLASSES.get(qtype, BINARY_CLASSES)


@dataclass(frozen=True)
class Rejection:
    """A frame the builder refused: its position in the input, its id (None when unreadable) and the reason."""

    index: int
    frame_id: str | None
    reason: str


@dataclass
class QueryBuild:
    queries: list[dict[str, Any]]
    rejected: list[Rejection]
    seed: int
    source_run_id: str = NO_RUN_ID
    shortfall: dict[int, int] = field(default_factory=dict)  # type -> queries missing from the requested quota

    def to_document(self) -> dict[str, Any]:
        """The whole query set (`contracts/vlm-queries.schema.json`)."""
        return {
            "schema_version": SCHEMA_VERSION,
            "seed": self.seed,
            "source_run_id": self.source_run_id,
            "queries": list(self.queries),
        }


class TruthInputError(ValueError):
    """A file the ground truth needs (depth, dust field, terrain) is missing, altered or malformed."""


class GridTerrain:
    """Bilinear terrain height from a grid `z_m[iy, ix]` (lower corner `x0_m`, `y0_m`, cell size `spacing_m`)."""

    def __init__(self, x0_m: float, y0_m: float, spacing_m: float, z_m: np.ndarray) -> None:
        z = np.asarray(z_m, dtype=float)
        if z.ndim != 2 or min(z.shape) < 2 or not np.isfinite(z).all() or not spacing_m > 0:
            raise TruthInputError(
                "terrain grid must be a finite 2-D array of at least 2 x 2 cells with positive spacing"
            )
        self.x0, self.y0, self.h, self.z = float(x0_m), float(y0_m), float(spacing_m), z

    def __call__(self, x: float, y: float) -> float:
        fx, fy = (x - self.x0) / self.h, (y - self.y0) / self.h
        ny, nx = self.z.shape
        if not (0 <= fx <= nx - 1 and 0 <= fy <= ny - 1):
            raise TruthInputError(f"terrain does not cover the point ({x:.2f}, {y:.2f})")
        ix, iy = min(int(fx), nx - 2), min(int(fy), ny - 2)
        tx, ty = fx - ix, fy - iy
        z = self.z
        return float(
            z[iy, ix] * (1 - tx) * (1 - ty)
            + z[iy, ix + 1] * tx * (1 - ty)
            + z[iy + 1, ix] * (1 - tx) * ty
            + z[iy + 1, ix + 1] * tx * ty
        )


def _read_verified(root: Path, ref: Mapping[str, str]) -> bytes:
    path = root / ref["path"]
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TruthInputError(f"cannot read {ref['path']}: {exc.strerror}") from exc
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise TruthInputError(f"{ref['path']}: sha256 differs from the frame state")
    return data


class SceneTruth:
    """The module's own ground truth of a frame (the default of `build_queries`).

    Types 1 to 3 come from the frame state alone. Types 4 to 6 read what the frame state references, in the formats of
    specs/015-vlm/data-model.md (depth `.npy`, dust field `.npz`, terrain `.npz`), or what the caller supplies:
    `blind_zones` (asset id to body-frame polygon) and `terrain` (a callable per frame). Whatever is missing leaves the
    type unaskable for that frame; nothing is guessed.
    """

    def __init__(
        self,
        root: Path,
        *,
        blind_zones: Mapping[str, Sequence[Sequence[float]]] | None = None,
        terrain: Callable[[Mapping[str, Any]], Callable[[float, float], float] | None] | None = None,
    ) -> None:
        self.root = Path(root)
        self.blind_zones = dict(blind_zones or {})
        self.terrain = terrain or self._grid_terrain

    def _grid_terrain(self, frame: Mapping[str, Any]) -> Callable[[float, float], float] | None:
        ref = frame["terrain"]
        if not ref["path"].endswith(".npz"):
            return None
        data = np.load(_to_buffer(_read_verified(self.root, ref)), allow_pickle=False)
        return GridTerrain(float(data["x0_m"]), float(data["y0_m"]), float(data["spacing_m"]), data["z_m"])

    def _type4(self, frame: Mapping[str, Any]) -> str | None:
        ref = frame["depth"]
        if not ref["path"].endswith(".npy"):
            return None
        depth = np.load(_to_buffer(_read_verified(self.root, ref)), allow_pickle=False)
        dust = None
        if frame["dust_field"] is not None:
            blob = np.load(_to_buffer(_read_verified(self.root, frame["dust_field"])), allow_pickle=False)
            dust = {
                "origin_m": blob["origin_m"],
                "spacing_m": float(blob["spacing_m"]),
                "sigma_per_m": blob["sigma_per_m"],
            }
        return truth_mod.truth_type4(frame, depth_m=depth, dust=dust)

    def __call__(self, frame: Mapping[str, Any], qtype: int) -> str | None:
        if qtype == 1:
            return truth_mod.truth_type1(frame)
        if qtype == 2:
            return truth_mod.truth_type2(frame)
        if qtype == 3:
            return truth_mod.truth_type3(frame)
        if qtype == 4:
            return self._type4(frame)
        if qtype == 5:
            return truth_mod.truth_type5(frame, blind_zones=self.blind_zones)
        if qtype == 6:
            terrain = self.terrain(frame)
            return None if terrain is None else truth_mod.truth_type6(frame, terrain=terrain)
        raise ValueError(f"unknown question type {qtype}")


def _to_buffer(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


def _query_id(frame_id: str, qtype: int) -> str:
    qid = f"{frame_id}-t{qtype}"
    if len(qid) <= MAX_ID:
        return qid
    return f"q-{hashlib.sha256(frame_id.encode()).hexdigest()[:24]}-t{qtype}"


def _spread(cells: Mapping[str, list[Any]], quota: int, order: Sequence[str]) -> list[Any]:
    """Take `quota` items from the (shuffled) cells, as evenly as availability allows: round robin over `order`."""
    taken: list[Any] = []
    pos = dict.fromkeys(cells, 0)
    while len(taken) < quota:
        progressed = False
        for key in order:
            if len(taken) >= quota:
                break
            if pos[key] < len(cells[key]):
                taken.append(cells[key][pos[key]])
                pos[key] += 1
                progressed = True
        if not progressed:
            break
    return taken


def _draw(
    items: Sequence[dict[str, Any]], labels: Sequence[str], quota_total: int, rng: random.Random
) -> list[dict[str, Any]]:
    """Draw `quota_total` items, an equal number per label (balanced down to what the scarcest label can give), spread
    evenly over the conditions inside each label. `items` carry `truth` and `condition`."""
    by_label: dict[str, dict[str, list[dict[str, Any]]]] = {lab: {c: [] for c in CONDITIONS} for lab in labels}
    for it in items:
        by_label[it["truth"]][it["condition"]].append(it)
    for cells in by_label.values():
        for lst in cells.values():
            rng.shuffle(lst)
    per_label = quota_total // len(labels)
    order = {lab: rng.sample(list(CONDITIONS), len(CONDITIONS)) for lab in labels}
    chosen = {lab: _spread(by_label[lab], per_label, order[lab]) for lab in labels}
    n = min(len(v) for v in chosen.values())
    if n < per_label:  # keep the classes equal: trim every label to the scarcest one, evenly over conditions
        chosen = {lab: _spread(by_label[lab], n, order[lab]) for lab in labels}
    return [it for lab in labels for it in chosen[lab]]


def _split_total(total: int, parts: int, rng: random.Random) -> list[int]:
    base, extra = divmod(total, parts)
    sizes = [base + (1 if i < extra else 0) for i in range(parts)]
    rng.shuffle(sizes)
    return sizes


def _subset(
    selected: Sequence[dict[str, Any]], labels: Sequence[str], total: int, rng: random.Random
) -> list[dict[str, Any]]:
    """A stratified subset of `total` queries of one type: labels equal (or differing by one), conditions even."""
    out: list[dict[str, Any]] = []
    for lab, size in zip(labels, _split_total(total, len(labels), rng), strict=True):
        pool = [q for q in selected if q["truth"] == lab]
        out.extend(_draw(pool, [lab], size, rng))
    return out


def build_queries(
    frames: Sequence[Mapping[str, Any] | str | Path],
    *,
    root: Path,
    seed: int,
    per_type: int = FULL_PER_TYPE,
    subsets: bool = True,
    truth_fn: TruthFn | None = None,
) -> QueryBuild:
    """Build the task-A query set from frame states.

    `frames` are frame-state mappings or JSON file paths; invalid ones are listed in `.rejected` and never queried.
    `truth_fn(frame, qtype)` returns the exact label or None (not asked); the default is `SceneTruth(root)`.
    """
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if per_type < 4 or per_type % 4:
        raise ValueError("per_type must be a positive multiple of 4 (equal counts per answer class)")
    truth = truth_fn or SceneTruth(root)
    rejected: list[Rejection] = []
    valid: dict[str, dict[str, Any]] = {}
    position: dict[str, int] = {}
    for index, source in enumerate(frames):
        frame_id = source.get("frame_id") if isinstance(source, Mapping) else None
        try:
            doc = load_frame_state(source, root=root)
        except ValueError as exc:
            rejected.append(Rejection(index, frame_id if isinstance(frame_id, str) else None, str(exc)))
            continue
        if doc["case"] != CASE:
            continue
        if doc["frame_id"] in valid:
            rejected.append(Rejection(index, doc["frame_id"], "duplicate frame_id"))
            continue
        valid[doc["frame_id"]] = doc
        position[doc["frame_id"]] = index
    ordered = [valid[k] for k in sorted(valid)]
    full = subsets and per_type == FULL_PER_TYPE
    queries: list[dict[str, Any]] = []
    shortfall: dict[int, int] = {}
    for qtype in QUESTION_TYPES:
        rng = random.Random(f"pitstudio-015|{seed}|{qtype}")
        labels = classes_of(qtype)
        cands = []
        for doc in ordered:
            try:
                label = truth(doc, qtype)
            except ValueError as exc:
                rejected.append(Rejection(position[doc["frame_id"]], doc["frame_id"], f"type {qtype}: {exc}"))
                continue
            if label is None:
                continue
            if label not in labels:
                raise ValueError(f"truth_fn returned {label!r} for type {qtype}; allowed: {labels}")
            cands.append(
                {
                    "query_id": _query_id(doc["frame_id"], qtype),
                    "frame_id": doc["frame_id"],
                    "frame_state_sha256": canonical_sha256(doc),
                    "type": qtype,
                    "condition": doc["condition"],
                    "location": doc["location"],
                    "truth": label,
                    "gate_subset": False,
                    "reasoning_subset": False,
                }
            )
        chosen = _draw(cands, labels, per_type, rng)
        shortfall[qtype] = per_type - len(chosen)
        if full:
            if qtype in BINARY_TYPES:
                for q in _subset(chosen, labels, GATE_PER_TYPE, rng):
                    q["gate_subset"] = True
            for q in _subset(chosen, labels, REASONING_PER_TYPE, rng):
                q["reasoning_subset"] = True
        rng.shuffle(chosen)
        queries.extend(chosen)
    run_ids = {q["frame_id"]: valid[q["frame_id"]]["run_id"] for q in queries}
    first = min(run_ids) if run_ids else (min(valid) if valid else None)
    source_run_id = (run_ids.get(first) or valid[first]["run_id"]) if first else NO_RUN_ID
    return QueryBuild(queries, rejected, seed, source_run_id, shortfall)
