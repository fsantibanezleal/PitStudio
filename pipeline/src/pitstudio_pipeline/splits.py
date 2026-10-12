"""Splits fixed at ingestion, by source group (FR-008-27 ... FR-008-31, FR-008-47).

Every record belongs to exactly one group and every split is made at group level; the result is a split file valid
against `contracts/split.schema.json` with the SHA-256 of its membership lists. Later stages read splits only from that
file (`load_split`), which refuses a file whose schema, digest or fold structure is wrong.

Record ids are strings. The Mendeley files are numbered 1 ... 960 and their ids are the zero-padded numbers `001` ...
`960`, as in the archive's file names.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pitstudio.contracts.jcs import canonicalize
from pitstudio_pipeline.errors import LinksInvalid, SplitIntegrityError

MENDELEY_ID = "mendeley-78ht3pjsr4"
MENDELEY_LINKS: tuple[tuple[int, int], ...] = (
    (29, 39),
    (34, 41),
    (36, 37),
    (41, 49),
    (59, 60),
    (189, 199),
    (192, 196),
    (196, 198),
    (196, 201),
)
N_ORIGINALS, N_SCENES, N_FILES, N_FOLDS = 240, 80, 960, 5
SPLIT_SCHEMA_VERSION = "1.0"
MAX_SEED = 2**63 - 1


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def record_id(number: int) -> str:
    """The id of Mendeley file `number`: three digits, zero-padded."""
    return f"{number:03d}"


def scene_of(k: int) -> int:
    """Scene s(k) = ((k - 1) mod 80) + 1 of file k (files k, k + 80 and k + 160 are crops of one photograph)."""
    return ((k - 1) % N_SCENES) + 1


def original_of(k: int) -> int:
    """Original o(k) = ((k - 1) mod 240) + 1 of file k (the other three versions are its flips and rotation)."""
    return ((k - 1) % N_ORIGINALS) + 1


def validate_links(links: Any) -> list[tuple[int, int]]:
    """The links as integer pairs, or `LinksInvalid`: two different original-file numbers in 1 ... 240 each."""
    if not isinstance(links, list | tuple):
        raise LinksInvalid("the links must be a list of pairs")
    out = []
    for position, link in enumerate(links):
        if not isinstance(link, list | tuple) or len(link) != 2:
            raise LinksInvalid(f"link {position} is not a pair")
        a, b = link
        if not (_is_int(a) and _is_int(b)):
            raise LinksInvalid(f"link {position} does not name two integers")
        if not (1 <= a <= N_ORIGINALS and 1 <= b <= N_ORIGINALS):
            raise LinksInvalid(f"link {position} names a file outside 1 ... {N_ORIGINALS}")
        if a == b:
            raise LinksInvalid(f"link {position} links a file to itself")
        out.append((a, b))
    return out


def _scene_components(links: Sequence[tuple[int, int]]) -> dict[int, int]:
    """Scene -> smallest scene of its component under the links mapped to scenes (plain union-find)."""
    parent = {s: s for s in range(1, N_SCENES + 1)}

    def find(s: int) -> int:
        while parent[s] != s:
            parent[s] = parent[parent[s]]
            s = parent[s]
        return s

    for a, b in links:
        ra, rb = find(scene_of(a)), find(scene_of(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return {s: find(s) for s in parent}


def group_mendeley(files: Iterable[int], links: Sequence[tuple[int, int]] | None = None) -> dict[int, int]:
    """File number k (1 ... 960) -> group id: the smallest original of its component (FR-008-28, 72 groups).

    The group of file k is the connected component of g(k) = s(((k - 1) mod 240) + 1) under the links mapped to scenes.
    The smallest original of a scene is the scene number itself, so the group id is the smallest scene of the component.
    """
    pairs = validate_links(list(MENDELEY_LINKS) if links is None else links)
    component = _scene_components(pairs)
    out = {}
    for k in files:
        if not _is_int(k) or not 1 <= k <= N_FILES:
            raise ValueError(f"file number {k!r} is outside 1 ... {N_FILES}")
        out[k] = component[scene_of(k)]
    return out


def _check_seed(seed: Any) -> int:
    if not _is_int(seed):
        raise TypeError(f"the seed must be an integer, not {type(seed).__name__}")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"the seed must be in 0 ... {MAX_SEED}")
    return int(seed)


def greedy_folds(sizes: Mapping[str, int], seed: int, n_folds: int) -> list[list[str]]:
    """Group ids per fold (FR-008-30): a seeded permutation, a stable sort by size (descending), then each group goes to
    the fold with the fewest records so far, the lowest index on ties."""
    order = sorted(sizes)
    random.Random(seed).shuffle(order)
    order.sort(key=lambda g: -sizes[g])
    load = [0] * n_folds
    folds: list[list[str]] = [[] for _ in range(n_folds)]
    for group in order:
        target = min(range(n_folds), key=lambda i: (load[i], i))
        load[target] += sizes[group]
        folds[target].append(group)
    return folds


def membership_sha256(groups: Any, folds: Any) -> str:
    """SHA-256 of the RFC 8785 canonical JSON of `{groups, folds}` (DC-008-04)."""
    return hashlib.sha256(canonicalize({"groups": groups, "folds": folds})).hexdigest()


def _assemble(
    *,
    dataset: dict[str, str],
    group_key: dict[str, Any],
    links: list[dict[str, str]],
    groups: dict[str, list[str]],
    seed: int | None,
    fold_groups: list[list[str]],
    all_records: list[str],
    test_filter: Any = None,
) -> dict[str, Any]:
    group_docs = [{"id": gid, "members": sorted(groups[gid])} for gid in sorted(groups)]
    folds = []
    for index, chosen in enumerate(fold_groups):
        in_fold = {m for gid in chosen for m in groups[gid]}
        test = sorted(m for m in in_fold if test_filter is None or test_filter(m))
        folds.append({"index": index, "test": test, "train_pool": sorted(set(all_records) - in_fold)})
    doc: dict[str, Any] = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "id": f"{dataset['id']}-grouped-{len(fold_groups)}fold" if fold_groups else f"{dataset['id']}-single-group",
        "dataset": dataset,
        "group_key": group_key,
        "links": links,
        "groups": group_docs,
        "method": "seeded-greedy-grouped-kfold" if fold_groups else "none",
        "seed": seed,
        "folds": folds,
    }
    doc["membership_sha256"] = membership_sha256(group_docs, folds)
    return doc


def build_mendeley_split(
    seed: int, *, links: Sequence[tuple[int, int]] | None = None, files: Iterable[int] | None = None
) -> dict[str, Any]:
    """The Mendeley split document: 72 groups, 5 grouped folds of 48 originals each (FR-008-27, -28, -30).

    A test list holds only the originals (001 ... 240) of its groups; the training pool holds every version of the other
    folds' groups. The same seed gives the same document, byte for byte once written.
    """
    seed = _check_seed(seed)
    pairs = validate_links(list(MENDELEY_LINKS) if links is None else links)
    numbers = sorted(set(range(1, N_FILES + 1) if files is None else files))
    group_of = group_mendeley(numbers, pairs)
    members: dict[str, list[str]] = {}
    for k in numbers:
        members.setdefault(record_id(group_of[k]), []).append(record_id(k))
    originals = {gid: sum(1 for m in ms if int(m) <= N_ORIGINALS) for gid, ms in members.items()}
    unique_links = sorted({tuple(sorted(p)) for p in pairs})
    return _assemble(
        dataset={"id": MENDELEY_ID, "version": "1", "kind": "real"},
        group_key={"rule": "mendeley-original-component"},
        links=[{"a": record_id(a), "b": record_id(b)} for a, b in unique_links],
        groups=members,
        seed=seed,
        fold_groups=greedy_folds(originals, seed, N_FOLDS),
        all_records=[record_id(k) for k in numbers],
        test_filter=lambda m: int(m) <= N_ORIGINALS,
    )


def write_split(doc: Mapping[str, Any], path: Path | str) -> None:
    """Write a split document (UTF-8, no BOM, LF, 2-space indent, trailing newline): same document, same bytes."""
    from pitstudio.contracts.io import dump_json

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(dump_json(doc))


def write_mendeley_split(
    path: Path | str, *, seed: int, links: Sequence[tuple[int, int]] | None = None, files: Iterable[int] | None = None
) -> dict[str, Any]:
    """Validate the links, build the Mendeley split and write it; invalid links stop here and write no file."""
    pairs = validate_links(
        list(MENDELEY_LINKS) if links is None else links
    )  # raises LinksInvalid before any file exists
    doc = build_mendeley_split(seed, links=pairs, files=files)
    write_split(doc, path)
    return doc


def _first_integrity_problem(doc: Mapping[str, Any]) -> tuple[str, str | None] | None:
    """(message, first offending record) of the first structural problem of a schema-valid split, or None."""
    group_of: dict[str, str] = {}
    for group in doc["groups"]:
        for member in group["members"]:
            if member in group_of:
                return "a record is in two groups", member
            group_of[member] = group["id"]
    members_of = {g["id"]: g["members"] for g in doc["groups"]}
    seen_in_test: set[str] = set()
    for fold in doc["folds"]:
        pool = set(fold["train_pool"])
        for record in fold["test"]:
            if record in seen_in_test:
                return "a record is in two test lists", record
            seen_in_test.add(record)
            if record in pool:
                return "a record is in both the test list and the training pool of one fold", record
            if record not in group_of:
                return "a test record belongs to no group", record
            if any(member in pool for member in members_of[group_of[record]]):
                return "a group is in both the test list and the training pool of one fold", record
    return None


def load_split(path: Path | str) -> dict[str, Any]:
    """Parse and check a split file; `SplitIntegrityError` unless its schema, structure and digest are all intact.

    Every consumer of a split (`s20`, `s30`, `s50`) reads it through this function (FR-008-47). The error names the
    first offending record when one exists.
    """
    from pitstudio.contracts.io import ContractError, load_json
    from pitstudio_pipeline._contracts import schema_errors

    try:
        doc = load_json(Path(path))
    except ContractError as exc:
        raise SplitIntegrityError(f"the split file cannot be read: {exc.reason}") from None
    failures = schema_errors("split.schema.json", doc)
    if failures:
        pointer, message = failures[0]
        raise SplitIntegrityError(f"the split file fails its schema at {pointer or '/'}: {message}")
    problem = _first_integrity_problem(doc)
    if problem is not None:
        raise SplitIntegrityError(*problem)
    if membership_sha256(doc["groups"], doc["folds"]) != doc["membership_sha256"]:
        raise SplitIntegrityError("the membership SHA-256 differs from the lists")
    assert isinstance(doc, dict)
    return doc


def carve_validation(doc: Mapping[str, Any], fold: int, *, fraction: float, seed: int) -> dict[str, list[str]]:
    """A validation subset carved from the training pool of `fold`, by group: a group is wholly on one side (FR-008-30).

    Groups are drawn in a seeded order until about `fraction` of the pool's records are taken; at least one group
    stays in the training side.
    """
    if not isinstance(fraction, int | float) or not 0.0 < fraction < 1.0:
        raise ValueError("fraction must be strictly between 0 and 1")
    seed = _check_seed(seed)
    folds = doc["folds"]
    if not _is_int(fold) or not 0 <= fold < len(folds):
        raise ValueError(f"fold {fold!r} does not exist")
    pool = set(folds[fold]["train_pool"])
    by_group = {g["id"]: sorted(m for m in g["members"] if m in pool) for g in doc["groups"]}
    by_group = {gid: ms for gid, ms in by_group.items() if ms}
    order = sorted(by_group)
    random.Random(seed).shuffle(order)
    target = max(1, round(fraction * len(pool)))
    validation: list[str] = []
    for position, gid in enumerate(order):
        if len(validation) >= target or position == len(order) - 1:
            break
        validation.extend(by_group[gid])
    taken = set(validation)
    return {"train": sorted(pool - taken), "validation": sorted(taken)}


_RECORD_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
SEEDED_RULES = {  # FR-008-31: rule -> (record field, key prefix)
    "scenario-seed": ("scenario_seed", "seed"),
    "event-seed": ("event_seed", "event"),
    "muck-pile-id": ("muck_pile_id", "muck"),
    "pit-layout-id": ("pit_layout_id", "layout"),
    "scene-seed": ("scene_seed", "scene"),
}
SPATIAL_RULE, SINGLE_RULE = "project-spatial-block", "single-group"
MAX_BLOCK_M = 1_000_000.0


def _key_text(value: Any, what: str) -> str:
    """A key value as text; it must make a valid group id, and equal values give equal text."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{what}: {value!r} is not a usable key value")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{what}: {value!r} is not a usable key value")
        value = int(value)
    text = str(value)
    if not _RECORD_ID.match(text):
        raise ValueError(f"{what}: {text[:40]!r} cannot be part of a group id")
    return text


def group_key(rule: str, record: Mapping[str, Any], *, block_size_m: float | None = None) -> str:
    """The group of `record` under `rule` (FR-008-31). Equal keys exactly when the defining values are equal.

    Seeded types key on their seed or id field; real terrain tiles on (project, spatial block), the block being the
    integer floor division of the coordinates by `block_size_m`; the single real slope-failure series is one group.
    """
    if rule == SINGLE_RULE:
        return "single"
    if rule in SEEDED_RULES:
        field, prefix = SEEDED_RULES[rule]
        if field not in record:
            raise ValueError(f"the record has no field {field!r} (rule {rule})")
        return f"{prefix}-{_key_text(record[field], field)}"
    if rule == SPATIAL_RULE:
        size = block_size_m
        if size is None or not isinstance(size, int | float) or not math.isfinite(size) or size <= 0:
            raise ValueError("the spatial block size must be declared, positive and finite")
        for field in ("project", "x", "y"):
            if field not in record:
                raise ValueError(f"the record has no field {field!r} (rule {rule})")
        x, y = record["x"], record["y"]
        if not (isinstance(x, int | float) and isinstance(y, int | float) and math.isfinite(x) and math.isfinite(y)):
            raise ValueError("the coordinates must be finite numbers")
        project = _key_text(record["project"], "project")
        if "__" in project:
            raise ValueError("a project name cannot contain a double underscore")
        return f"{project}__{int(x // size)}_{int(y // size)}"
    raise ValueError(f"unknown group-key rule {rule!r}")


def build_split(
    dataset_id: str,
    version: str,
    kind: str,
    rule: str,
    records: Sequence[Mapping[str, Any]],
    *,
    seed: int | None = None,
    n_folds: int = 5,
    block_size_m: float | None = None,
) -> dict[str, Any]:
    """A split document over `records` (mappings with an `id` and the key field of `rule`), at group level.

    One group per key; `n_folds` seeded greedy folds by record count (FR-008-30 rule), the test list holding the fold's
    records and the training pool all the others. `single-group` gives one group, method `none` and no folds.
    """
    if not isinstance(dataset_id, str) or not _SLUG.match(dataset_id):
        raise ValueError("the dataset id must be a lowercase slug")
    if not isinstance(version, str) or not _VERSION.match(version):
        raise ValueError("the dataset version has an invalid form")
    if kind not in ("real", "synthetic"):
        raise ValueError("kind must be `real` or `synthetic`")
    if not records:
        raise ValueError("a split needs at least one record")
    ids = []
    for record in records:
        rid = record.get("id")
        if not isinstance(rid, str) or not _RECORD_ID.match(rid):
            raise ValueError(f"record id {str(rid)[:40]!r} is not a valid split record id")
        ids.append(rid)
    if len(set(ids)) != len(ids):
        raise ValueError("record ids must be unique")
    groups: dict[str, list[str]] = {}
    for record in records:
        groups.setdefault(group_key(rule, record, block_size_m=block_size_m), []).append(record["id"])
    key_doc: dict[str, Any] = {"rule": rule}
    if rule == SPATIAL_RULE:
        key_doc["block_size_m"] = float(block_size_m)  # type: ignore[arg-type]  # group_key rejected None above
    dataset = {"id": dataset_id, "version": version, "kind": kind}
    if rule == SINGLE_RULE:
        doc = _assemble(
            dataset=dataset, group_key=key_doc, links=[], groups=groups, seed=None, fold_groups=[], all_records=ids
        )
    else:
        folds_n = n_folds
        if not _is_int(folds_n) or not 2 <= folds_n <= 20:
            raise ValueError("n_folds must be an integer in 2 ... 20")
        if len(groups) < folds_n:
            raise ValueError(f"{len(groups)} groups cannot fill {folds_n} folds")
        if seed is None:
            raise ValueError("a seed is required for a seeded split")
        doc = _assemble(
            dataset=dataset,
            group_key=key_doc,
            links=[],
            groups=groups,
            seed=_check_seed(seed),
            fold_groups=greedy_folds({g: len(ms) for g, ms in groups.items()}, _check_seed(seed), folds_n),
            all_records=ids,
        )
    from pitstudio_pipeline._contracts import schema_errors

    failures = schema_errors("split.schema.json", doc)
    if failures:
        raise ValueError(f"the split would not satisfy its schema at {failures[0][0] or '/'}: {failures[0][1]}")
    return doc


__all__ = [
    "MENDELEY_LINKS",
    "build_mendeley_split",
    "build_split",
    "carve_validation",
    "greedy_folds",
    "group_key",
    "group_mendeley",
    "load_split",
    "membership_sha256",
    "validate_links",
    "write_mendeley_split",
    "write_split",
]
