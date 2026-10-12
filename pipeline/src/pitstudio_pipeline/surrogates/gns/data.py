"""GNS data (s10_preprocess): rollout files, the geometry split, the packing plan and the 30 d selection (FR-011-03, FR-011-14).

- `s10_preprocess` reads one rollout (DC-011-01 metadata plus its Parquet or Zarr payload), validates everything and never
  coerces: a number given as a string, a path that is absolute or climbs with `..`, a digest that differs, a payload whose
  particle or frame count disagrees with the metadata all raise `RolloutFileError` naming the key or the class.
- `make_geometry_split` splits 100 geometries into 70 / 10 / 20 by geometry id, the test geometries lying inside the
  training envelope and at a normalised parameter distance >= 0.05 from every training geometry (8 collapses, 6 piles,
  6 dumps).
- `select_geometries` takes the first n candidates whose reference pile at rest is at least 30 d high and counts the rest.
"""

from __future__ import annotations

import math
import re
from collections import OrderedDict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from pitstudio.granular.errors import RolloutError
from pitstudio.granular.loader import validate_rollout_metadata
from pitstudio_pipeline.surrogates.digest import file_sha256, load_schema, zarr_digest
from pitstudio_pipeline.surrogates.errors import DatasetError, RolloutFileError

FAMILIES = ("column-collapse", "pile-formation", "dump-over-crest")
# the training envelope of DC-011-02: parameter -> (min, max), per family
FAMILY_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "column-collapse": {"aspect_ratio": (0.5, 4.0), "column_width_m": (0.1, 0.4)},
    "pile-formation": {"pour_height_m": (0.2, 0.6), "pour_rate_m2_per_s": (0.002, 0.01)},
    "dump-over-crest": {"crest_height_m": (0.1, 0.4), "dump_rate_m2_per_s": (0.002, 0.01)},
}
TEST_QUOTA = {"column-collapse": 8, "pile-formation": 6, "dump-over-crest": 6}
N_GEOMETRIES, N_TRAIN, N_VAL, N_TEST = 100, 70, 10, 20
MIN_DISTANCE = 0.05
SEEDS_PER_GEOMETRY = 3
RADIUS_FACTOR = 2.5  # R = 2.5 d (FR-011-02)
_SPLIT_ATTEMPTS = 400


# ------------------------------------------------------------------ geometry split (FR-011-03)


@dataclass(frozen=True)
class GeometrySplit:
    train: list[str]
    val: list[str]
    test: list[str]


@dataclass(frozen=True)
class SelectionResult:
    geometries: list[dict[str, Any]]
    replaced: int


def _normalised(geometry: Mapping[str, Any], ranges: Mapping[str, Mapping[str, tuple[float, float]]]) -> np.ndarray:
    family = geometry["family"]
    params = geometry.get("params", {})
    out = []
    for name, (lo, hi) in ranges[family].items():
        value = params.get(name)
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
            raise DatasetError(f"geometry {geometry['geometry_id']!r}: parameter {name!r} is missing or not finite")
        out.append((float(value) - lo) / (hi - lo))
    return np.array(out)


def make_geometry_split(
    geometries: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    min_distance: float = MIN_DISTANCE,
    ranges: Mapping[str, Mapping[str, tuple[float, float]]] | None = None,
) -> GeometrySplit:
    """Split exactly 100 geometries into train (70), val (10) and test (20: 8 collapses, 6 piles, 6 dumps) id lists.

    Test geometries lie inside the training envelope (per parameter between the training minimum and maximum of their
    family) and at a distance >= `min_distance` (Euclidean, on parameters normalised by their range, same family) from every
    training geometry; geometries closer than that to a test geometry go to validation. Reproducible by `seed`.
    """
    ranges = ranges or FAMILY_RANGES
    if len(geometries) != N_GEOMETRIES:
        raise DatasetError(f"exactly {N_GEOMETRIES} geometries are required, got {len(geometries)}")
    ids = [g["geometry_id"] for g in geometries]
    if len(set(ids)) != len(ids):
        raise DatasetError("geometry ids must be unique: duplicate geometry_id found")
    for g in geometries:
        if g.get("family") not in FAMILIES:
            raise DatasetError(f"geometry {g['geometry_id']!r}: unknown family {g.get('family')!r}")
    by_family = {f: [g for g in geometries if g["family"] == f] for f in FAMILIES}
    for family, quota in TEST_QUOTA.items():
        if len(by_family[family]) < quota + 1:
            raise DatasetError(f"family {family}: {len(by_family[family])} geometries cannot fill {quota} test geometries")
    vec = {g["geometry_id"]: _normalised(g, ranges) for g in geometries}
    fam_of = {g["geometry_id"]: g["family"] for g in geometries}

    def near(a: str, b: str) -> bool:
        return fam_of[a] == fam_of[b] and a != b and float(np.linalg.norm(vec[a] - vec[b])) < min_distance

    neighbours = {a: {b for b in ids if near(a, b)} for a in ids}
    extreme = _extremes(by_family, vec)
    rng_root = np.random.SeedSequence(seed)
    failure = "no admissible test set found"
    for attempt in range(_SPLIT_ATTEMPTS):
        rng = np.random.default_rng(rng_root.spawn(1)[0])
        test: list[str] = []
        forced: set[str] = set()
        ok = True
        for family, quota in TEST_QUOTA.items():
            pool = [g["geometry_id"] for g in by_family[family] if g["geometry_id"] not in extreme]
            rng.shuffle(pool)
            picked = 0
            for gid in pool:
                if picked == quota:
                    break
                new_forced = (forced | neighbours[gid]) - set(test) - {gid}
                if len(new_forced) <= N_VAL:
                    test.append(gid)
                    forced = new_forced
                    picked += 1
            if picked < quota:
                ok = False
                failure = (
                    f"family {family}: fewer than {quota} geometries are inside the training envelope "
                    f"and at a normalised distance >= {min_distance} from the training set"
                )
                break
        if not ok:
            continue
        forced = {f for f in forced if f not in set(test)}
        remaining = [i for i in ids if i not in set(test) and i not in forced]
        rng.shuffle(remaining)
        remaining.sort(key=lambda i: i in extreme)  # keep the envelope-defining geometries in training
        val = sorted(forced) + remaining[: N_VAL - len(forced)]
        train = [i for i in ids if i not in set(test) and i not in set(val)]
        if len(train) != N_TRAIN or len(val) != N_VAL:
            continue
        if _split_valid(train, test, vec, fam_of, min_distance, by_family):
            return GeometrySplit(train=train, val=sorted(val), test=sorted(test))
        failure = "the test geometries are not inside the training envelope or too near a training geometry (distance, envelope)"
    raise DatasetError(f"cannot split the geometries: {failure}")


def _extremes(by_family: Mapping[str, Sequence[Mapping[str, Any]]], vec: Mapping[str, np.ndarray]) -> set[str]:
    out: set[str] = set()
    for members in by_family.values():
        stack = np.array([vec[g["geometry_id"]] for g in members])
        for col in range(stack.shape[1]):
            out |= {members[i]["geometry_id"] for i in np.flatnonzero(np.isclose(stack[:, col], stack[:, col].min()))}
            out |= {members[i]["geometry_id"] for i in np.flatnonzero(np.isclose(stack[:, col], stack[:, col].max()))}
    return out


def _split_valid(
    train: Sequence[str],
    test: Sequence[str],
    vec: Mapping[str, np.ndarray],
    fam_of: Mapping[str, str],
    min_distance: float,
    by_family: Mapping[str, Sequence[Mapping[str, Any]]],
) -> bool:
    for t in test:
        same = [r for r in train if fam_of[r] == fam_of[t]]
        if not same:
            return False
        stack = np.array([vec[r] for r in same])
        if float(np.linalg.norm(stack - vec[t], axis=1).min()) < min_distance:
            return False
        if ((vec[t] < stack.min(axis=0) - 1e-12) | (vec[t] > stack.max(axis=0) + 1e-12)).any():
            return False
    return True


def packing_plan(geometry_ids: Sequence[str], *, seed: int, seeds_per_geometry: int = SEEDS_PER_GEOMETRY) -> list[dict[str, Any]]:
    """`seeds_per_geometry` packing seeds per geometry, all distinct over the dataset, reproducible by `seed`."""
    total = len(geometry_ids) * seeds_per_geometry
    seeds = np.random.default_rng(seed).choice(2**32, size=total, replace=False)
    return [
        {"geometry_id": gid, "packing_seed": int(seeds[i * seeds_per_geometry + k])}
        for i, gid in enumerate(geometry_ids)
        for k in range(seeds_per_geometry)
    ]


def select_geometries(
    candidates: Sequence[Mapping[str, Any]], *, n: int = N_GEOMETRIES, min_pile_height_d: float = 30.0
) -> SelectionResult:
    """The first `n` candidates (in order) whose reference pile at rest is >= `min_pile_height_d` x d; count the others."""
    chosen: list[dict[str, Any]] = []
    replaced = 0
    for cand in candidates:
        if len(chosen) == n:
            break
        if cand["rest_height_m"] >= min_pile_height_d * cand["particle_diameter_m"]:
            chosen.append(dict(cand))
        else:
            replaced += 1
    if len(chosen) < n:
        raise DatasetError(f"only {len(chosen)} of {n} candidates have a reference pile at least {min_pile_height_d} d high")
    return SelectionResult(geometries=chosen, replaced=replaced)


# ------------------------------------------------------------------ rollout files (FR-011-14)


@dataclass
class PreprocessedRollout:
    meta: dict[str, Any]
    positions: np.ndarray  # float32 [T, N, 2]
    particle_types: np.ndarray  # int64 [N]
    digest: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


def _first_non_finite(node: Any, path: str = "") -> str | None:
    if isinstance(node, float):
        return None if math.isfinite(node) else path or "<root>"
    if isinstance(node, Mapping):
        for key, value in node.items():
            found = _first_non_finite(value, f"{path}/{key}" if path else str(key))
            if found:
                return found
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found = _first_non_finite(value, f"{path}[{i}]")
            if found:
                return found
    return None


def read_metadata(meta_path: str | Path) -> dict[str, Any]:
    """Parse a metadata file strictly: unreadable, not JSON, not an object -> RolloutFileError."""
    import json

    try:
        text = Path(meta_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RolloutFileError(f"metadata file unreadable: {exc}") from None
    try:
        meta = json.loads(text)
    except ValueError as exc:
        raise RolloutFileError(f"metadata is not valid JSON: {exc}") from None
    if not isinstance(meta, dict):
        raise RolloutFileError("metadata must be a JSON object")
    return meta


_ABSOLUTE = re.compile(r"^([A-Za-z]:|[\\/])")


def check_store_path(path: Any) -> None:
    """The store path must be relative and free of `..` segments (FR-011-14, FR-011-41)."""
    if not isinstance(path, str) or not path:
        raise RolloutFileError("store/path: must be a non-empty relative path")
    if "\x00" in path or _ABSOLUTE.match(path) or "\\" in path or any(seg == ".." for seg in path.split("/")):
        raise RolloutFileError("store/path: an absolute path or one containing '..' is not allowed")


def validate_metadata(meta: dict[str, Any]) -> None:
    """DC-011-01 checks without touching the payload; raises RolloutFileError naming the key."""
    bad = _first_non_finite(meta)
    if bad:
        raise RolloutFileError(f"{bad}: non-finite value")
    store = meta.get("store")
    if isinstance(store, dict):
        check_store_path(store.get("path"))
    errors = sorted(Draft202012Validator(load_schema("granular-rollout")).iter_errors(meta), key=lambda e: list(map(str, e.path)))
    if errors:
        e = errors[0]
        where = "/".join(str(p) for p in e.path) or "<root>"
        raise RolloutFileError(f"{where}: {e.message}")
    try:
        validate_rollout_metadata(meta)
    except RolloutError as exc:
        raise RolloutFileError(str(exc)) from None
    d, radius = meta["particle_diameter_m"], meta["connectivity_radius_m"]
    if not math.isclose(radius, RADIUS_FACTOR * d, rel_tol=1e-6):
        raise RolloutFileError(f"connectivity_radius_m: {radius} is not {RADIUS_FACTOR} x particle_diameter_m ({RADIUS_FACTOR * d})")
    times = meta["frame_times_s"]
    for i in range(1, len(times)):
        if not times[i] > times[i - 1]:
            raise RolloutFileError(f"frame_times_s: not strictly increasing at index {i} ({times[i - 1]} then {times[i]})")


def s10_preprocess(meta_path: str | Path, *, root: str | Path) -> PreprocessedRollout:
    """Validate one rollout file and return its frames; the payload is read only after the metadata and path are valid."""
    meta = read_metadata(meta_path)
    validate_metadata(meta)
    store = meta["store"]
    payload = Path(root) / store["path"]
    if not payload.exists():
        raise RolloutFileError(f"store/path: payload {store['path']} does not exist")
    if store["format"] == "parquet":
        if not payload.is_file():
            raise RolloutFileError("store/path: a Parquet payload must be a file")
        actual = file_sha256(payload)
    else:
        if not payload.is_dir():
            raise RolloutFileError("store/path: a Zarr payload must be a directory")
        actual = zarr_digest(payload)
    if actual != store["sha256"]:
        raise RolloutFileError(f"store/sha256: recorded {store['sha256']} but the payload digest is {actual}")
    positions, types = _read_parquet(payload, meta) if store["format"] == "parquet" else _read_zarr(payload, meta)
    _check_payload(positions, types, meta)
    return PreprocessedRollout(meta=meta, positions=positions, particle_types=types, digest=actual)


def _read_parquet(path: Path, meta: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    import pyarrow.parquet as pq

    try:
        table = pq.read_table(path)
    except Exception as exc:
        raise RolloutFileError(f"payload unreadable as Parquet: {exc}") from None
    missing = [c for c in ("frame", "particle", "type", "x", "y") if c not in table.column_names]
    if missing:
        raise RolloutFileError(f"payload lacks the columns {missing}")
    cols = {c: table.column(c).to_numpy() for c in ("frame", "particle", "type", "x", "y")}
    for c in ("frame", "particle", "type"):
        if not np.issubdtype(cols[c].dtype, np.integer):
            raise RolloutFileError(f"payload column {c} must hold integers, got {cols[c].dtype}")
    for c in ("x", "y"):
        if not np.issubdtype(cols[c].dtype, np.floating):
            raise RolloutFileError(f"payload column {c} must hold floats, got {cols[c].dtype}")
        if not np.isfinite(cols[c]).all():
            raise RolloutFileError(f"payload column {c} holds a non-finite value")
    frames, counts = np.unique(cols["frame"], return_counts=True)
    if len(frames) == 0:
        raise RolloutFileError("payload has no rows")
    if len(set(counts.tolist())) != 1:
        raise RolloutFileError(f"particle count changes between frames ({sorted(set(counts.tolist()))})")
    n, t = int(counts[0]), len(frames)
    if n != meta["particle_count"]:
        raise RolloutFileError(f"particle_count: metadata says {meta['particle_count']} but the payload has {n} per frame")
    if t != len(meta["frame_times_s"]):
        raise RolloutFileError(f"frame_times_s has {len(meta['frame_times_s'])} entries but the payload has {t} frames")
    order = np.lexsort((cols["particle"], cols["frame"]))
    particle = cols["particle"][order].reshape(t, n)
    if not (particle == np.arange(n)[None, :]).all():
        raise RolloutFileError("payload particle ids must be 0 ... N-1 in every frame")
    positions = np.stack([cols["x"][order].reshape(t, n), cols["y"][order].reshape(t, n)], axis=-1).astype(np.float32)
    types = cols["type"][order].reshape(t, n)
    if not (types == types[0][None, :]).all():
        raise RolloutFileError("type: a particle changes type between frames")
    return positions, types[0].astype(np.int64)


def _read_zarr(path: Path, meta: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    import zarr

    try:
        group = zarr.open_group(str(path), mode="r")
        positions = np.asarray(group["positions"][:])
        types = np.asarray(group["type_index"][:])
        times = np.asarray(group["frame_times_s"][:])
    except Exception as exc:
        raise RolloutFileError(f"payload unreadable as Zarr: {exc}") from None
    if positions.ndim != 3 or positions.shape[2] != 2:
        raise RolloutFileError(f"payload positions must have shape [T, N, 2], got {list(positions.shape)}")
    if not np.issubdtype(positions.dtype, np.floating) or not np.isfinite(positions).all():
        raise RolloutFileError("payload positions hold a non-finite value")
    if positions.shape[1] != meta["particle_count"]:
        raise RolloutFileError(f"particle_count: metadata says {meta['particle_count']} but the payload has {positions.shape[1]}")
    if positions.shape[0] != len(meta["frame_times_s"]):
        raise RolloutFileError(f"frame_times_s has {len(meta['frame_times_s'])} entries but the payload has {positions.shape[0]} frames")
    if types.shape != (positions.shape[1],):
        raise RolloutFileError(f"payload type_index must have shape [{positions.shape[1]}], got {list(types.shape)}")
    if times.shape != (positions.shape[0],) or not np.allclose(times, meta["frame_times_s"], rtol=0, atol=1e-6):
        raise RolloutFileError("frame_times_s: the payload frame times differ from the metadata")
    return positions.astype(np.float32), types.astype(np.int64)


def _check_payload(positions: np.ndarray, types: np.ndarray, meta: dict[str, Any]) -> None:
    n_types = len(meta["particle_types"])
    if types.min() < 0 or types.max() >= n_types:
        raise RolloutFileError(f"type: a particle type index is outside [0, {n_types}) (declared {meta['particle_types']})")


# ------------------------------------------------------------------ training and evaluation views


def to_training_rollout(pre: PreprocessedRollout) -> dict[str, Any]:
    """The rollout dict of `train_gns`: positions [T, N, 2], particle_types, bounds [4], d, dt, plus ids."""
    meta = pre.meta
    return {
        "positions": pre.positions,
        "particle_types": pre.particle_types,
        "bounds": np.asarray(meta["bounds_m"], dtype=np.float32),
        "d": meta["particle_diameter_m"],
        "dt": meta["frame_interval_s"],
        "geometry_id": meta["geometry_id"],
        "family": meta["family"],
        "seed": meta["packing_seed"],
    }


class RolloutSet(Sequence):
    """A lazy list of training rollouts: files are read (and validated) on first access, a few are kept in memory."""

    def __init__(self, meta_paths: Sequence[Path], *, root: Path, cache_size: int = 4) -> None:
        self.meta_paths = list(meta_paths)
        self.root = Path(root)
        self._cache: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._cache_size = cache_size

    def __len__(self) -> int:
        return len(self.meta_paths)

    def __getitem__(self, i: int) -> dict[str, Any]:  # type: ignore[override]
        if i < 0:
            i += len(self)
        if not 0 <= i < len(self):
            raise IndexError(i)
        if i not in self._cache:
            self._cache[i] = to_training_rollout(s10_preprocess(self.meta_paths[i], root=self.root))
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        self._cache.move_to_end(i)
        return self._cache[i]

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for i in range(len(self)):
            yield self[i]


class DirectorySplits:
    """`splits.rollouts(name)` over a directory of metadata files, grouped by geometry id (train | val | test)."""

    def __init__(self, meta_dir: Path, *, root: Path, split: Mapping[str, Sequence[str]]) -> None:
        self.meta_dir, self.root, self.split = Path(meta_dir), Path(root), {k: list(v) for k, v in split.items()}
        self.by_geometry: dict[str, list[Path]] = {}
        for path in sorted(self.meta_dir.glob("*.json")):
            meta = read_metadata(path)
            self.by_geometry.setdefault(str(meta.get("geometry_id")), []).append(path)

    def rollouts(self, name: str) -> RolloutSet:
        if name not in self.split:
            raise DatasetError(f"unknown split {name!r}; expected one of {sorted(self.split)}")
        paths = [p for gid in self.split[name] for p in self.by_geometry.get(gid, [])]
        return RolloutSet(paths, root=self.root)


def evaluation_geometries(
    meta_dir: Path, *, root: Path, geometry_ids: Sequence[str]
) -> list[dict[str, Any]]:
    """The `geometries` argument of `evaluate_held_out` for the given held-out ids (references in seed order)."""
    out = []
    for gid in geometry_ids:
        refs = []
        base: dict[str, Any] | None = None
        for path in sorted(Path(meta_dir).glob("*.json")):
            meta = read_metadata(path)
            if meta.get("geometry_id") != gid:
                continue
            pre = s10_preprocess(path, root=root)
            base = base or {
                "geometry_id": gid,
                "family": meta["family"],
                "geometry": meta["geometry"],
                "d": meta["particle_diameter_m"],
                "dt": meta["frame_interval_s"],
                "bounds": list(meta["bounds_m"]),
            }
            refs.append({"seed": meta["packing_seed"], "positions": pre.positions, "particle_types": pre.particle_types})
        if base is not None:
            refs.sort(key=lambda r: r["seed"])
            out.append({**base, "references": refs})
    return out
